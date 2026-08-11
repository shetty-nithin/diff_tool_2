"""
launcher.py
===========
Desktop application for the Semantic Diff Tool.

Requirements
------------
    pip install PyQt6
    pip install pyinstaller

Build (macOS/Linux):
--------------------
    pyinstaller --windowed --name "SemanticDiffTool" --collect-all PyQt6 launcher.py

Build (Windows):
----------------
    pyinstaller --noconfirm --clean --windowed --name "SemanticDiffTool" --collect-all PyQt6 launcher.py
"""
import os
import sys
import shutil
import subprocess
from PyQt6.QtWidgets import (
    QApplication, QWidget, QStackedWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog, QLineEdit, QFrame, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, QTimer
from PyQt6.QtGui import QFont, QColor, QPalette

# ── project root ──────────────────────────────────────────────────────────────
if getattr(sys, "frozen", False):
    ROOT = os.path.dirname(
        os.path.dirname(
            os.path.dirname(
                os.path.dirname(
                    os.path.dirname(os.path.abspath(sys.executable))
                )
            )
        )
    )
else:
    ROOT = os.path.dirname(os.path.abspath(__file__))

# Normalize root path for OS consistency
ROOT = os.path.normpath(ROOT)

# ── find Python interpreter (Cross-Platform) ──────────────────────────────────
def _find_python():
    """
    Finds the correct Python executable across macOS, Windows, and Linux.
    Prioritizes the active Python environment running this launcher.
    """
    # 1. ALWAYS use the currently running interpreter if NOT frozen by PyInstaller
    if not getattr(sys, "frozen", False) and sys.executable and os.path.isfile(sys.executable):
        return sys.executable

    # 2. If running inside an active virtualenv / conda environment
    is_venv = sys.prefix != sys.base_prefix or "conda" in sys.prefix.lower()
    if is_venv:
        if sys.platform == "win32":
            venv_python = os.path.join(sys.prefix, "Scripts", "python.exe")
        else:
            venv_python = os.path.join(sys.prefix, "bin", "python")
        if os.path.isfile(venv_python):
            return venv_python

    # 3. Search PATH using shutil
    cmd_name = "python" if sys.platform == "win32" else "python3"
    found = shutil.which(cmd_name) or shutil.which("python")
    if found:
        return found

    # 4. OS-specific fallback candidates for PyInstaller standalone builds
    if sys.platform == "win32":
        candidates = [
            os.path.expanduser(r"~\AppData\Local\Programs\Python\Python312\python.exe"),
            os.path.expanduser(r"~\AppData\Local\Programs\Python\Python311\python.exe"),
            os.path.expanduser(r"~\AppData\Local\Programs\Python\Python310\python.exe"),
            r"C:\Python312\python.exe",
            r"C:\Python311\python.exe",
        ]
    else:
        candidates = [
            "/opt/anaconda3/bin/python3",
            "/usr/local/bin/python3",
            "/usr/bin/python3",
            os.path.expanduser("~/anaconda3/bin/python3"),
            os.path.expanduser("~/miniconda3/bin/python3"),
        ]

    for c in candidates:
        if os.path.isfile(c):
            return c

    return cmd_name

PYTHON = _find_python()

# ══════════════════════════════════════════════════════════════════════════════
# Worker
# ══════════════════════════════════════════════════════════════════════════════
class Worker(QObject):
    finished = pyqtSignal(bool, str)
    def __init__(self, cmd):
        super().__init__()
        self.cmd = cmd
        self._proc = None
        self._error_detail = ""

    def run(self):
        self._error_detail = ""
        try:
            # Inject ROOT into PYTHONPATH so sub-processes find local imports
            env = os.environ.copy()
            env["PYTHONPATH"] = ROOT + os.pathsep + env.get("PYTHONPATH", "")

            # Prevent CMD window popup on Windows when running subprocesses
            kwargs = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
                "cwd": ROOT,
                "env": env,
                "text": True,
                "encoding": "utf-8",
                "errors": "replace"
            }
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                kwargs["startupinfo"] = startupinfo

            self._proc = subprocess.Popen(self.cmd, **kwargs)
            out, _ = self._proc.communicate()
            ok = self._proc.returncode == 0
            if not ok:
                lines = [l for l in (out or "").splitlines() if l.strip()]
                self._error_detail = "\n".join(lines[-20:])
        except Exception as e:
            ok = False
            self._error_detail = str(e)
        output_dir = os.path.join(ROOT, "outputs")
        self.finished.emit(ok, output_dir)

    def stop(self):
        if self._proc:
            self._proc.terminate()

# ══════════════════════════════════════════════════════════════════════════════
# Styling
# ══════════════════════════════════════════════════════════════════════════════
BG = "#0f1117"
SURFACE = "#1a1d27"
SURFACE2 = "#222635"
BORDER = "#2d3148"
ACCENT = "#5b6cf9"
ACCENT_DARK = "#3d4db8"
TEXT = "#e2e4ef"
TEXT_DIM = "#7880a4"
SUCCESS = "#4caf82"
ERROR = "#e05c5c"
RADIUS = "12px"
RADIUS_SM = "8px"

def stylesheet():
    return f"""
    QWidget {{
        background: {BG};
        color: {TEXT};
        font-family: 'Inter', 'Segoe UI', 'SF Pro Text', system-ui, sans-serif;
        font-size: 13px;
    }}
    QPushButton#tab_diff, QPushButton#tab_cluster, QPushButton#tab_validate {{
        background: {SURFACE2};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_SM};
        color: {TEXT_DIM};
        font-size: 12px;
        font-weight: 600;
        padding: 10px 0;
        letter-spacing: 0.04em;
    }}
    QPushButton#tab_diff:checked, QPushButton#tab_cluster:checked, QPushButton#tab_validate:checked {{
        background: {ACCENT};
        border-color: {ACCENT};
        color: white;
    }}
    QPushButton#tab_diff:hover:!checked, QPushButton#tab_cluster:hover:!checked, QPushButton#tab_validate:hover:!checked {{
        border-color: {ACCENT};
        color: {TEXT};
    }}
    QPushButton#tab_diff:disabled, QPushButton#tab_cluster:disabled, QPushButton#tab_validate:disabled {{
        background: {SURFACE2};
        border-color: {BORDER};
        color: {TEXT_DIM};
    }}
    QLineEdit {{
        background: {SURFACE2};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_SM};
        color: {TEXT};
        padding: 10px 14px;
        font-size: 12px;
        selection-background-color: {ACCENT};
    }}
    QLineEdit:focus {{
        border-color: {ACCENT};
    }}
    QLineEdit::placeholder {{
        color: {TEXT_DIM};
    }}
    QPushButton#browse {{
        background: {SURFACE2};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_SM};
        color: {TEXT_DIM};
        padding: 10px 16px;
        font-size: 12px;
        font-weight: 500;
        min-width: 72px;
    }}
    QPushButton#browse:hover {{
        border-color: {ACCENT};
        color: {TEXT};
    }}
    QPushButton#browse:pressed {{
        background: {SURFACE};
    }}
    QPushButton#run {{
        background: {ACCENT};
        border: none;
        border-radius: {RADIUS_SM};
        color: white;
        font-size: 14px;
        font-weight: 700;
        padding: 14px 0;
        letter-spacing: 0.03em;
    }}
    QPushButton#run:hover {{
        background: {ACCENT_DARK};
    }}
    QPushButton#run:pressed {{
        background: #2e3a9e;
    }}
    QPushButton#run:disabled {{
        background: {SURFACE2};
        color: {TEXT_DIM};
    }}
    QLabel#section_label {{
        color: {TEXT_DIM};
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.10em;
    }}
    QFrame#divider {{
        background: {BORDER};
        border: none;
        max-height: 1px;
    }}
    QWidget#card {{
        background: {SURFACE};
        border: 1px solid {BORDER};
        border-radius: {RADIUS};
    }}
    """

# ══════════════════════════════════════════════════════════════════════════════
# Main window
# ══════════════════════════════════════════════════════════════════════════════
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self._worker = None
        self._thread = None
        self._mode = "diff"
        self._last_dir = ROOT
        self.setWindowTitle("Semantic Diff Tool")
        self.setFixedSize(520, 460)
        self.setStyleSheet(stylesheet())
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.center().x() - self.width() // 2, screen.center().y() - self.height() // 2)
        self._build_ui()

    # ── build ─────────────────────────────────────────────────────────────────
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.setSpacing(20)

        header = QVBoxLayout()
        header.setSpacing(4)
        title = QLabel("Semantic Diff")
        title.setFont(QFont("Inter", 22, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {TEXT}; font-size: 22px; font-weight: 700;")
        sub = QLabel("Compare log files or cluster an entire directory")
        sub.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
        header.addWidget(title)
        header.addWidget(sub)
        outer.addLayout(header)

        # ── mode tabs ──
        tabs = QHBoxLayout()
        tabs.setSpacing(6)
        self.tab_diff = QPushButton("⇄   Diff Two Files")
        self.tab_cluster = QPushButton("◎   Cluster Directory")
        self.tab_validate = QPushButton("✓   Validate")
        for btn, name in [(self.tab_diff, "tab_diff"), (self.tab_cluster, "tab_cluster"), (self.tab_validate, "tab_validate")]:
            btn.setObjectName(name)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(40)
            tabs.addWidget(btn)
        self.tab_diff.setChecked(True)
        self.tab_diff.clicked.connect(lambda: self._switch_mode("diff"))
        self.tab_cluster.clicked.connect(lambda: self._switch_mode("cluster"))
        self.tab_validate.clicked.connect(self._validate)
        outer.addLayout(tabs)

        # ── input card ──
        self.card = QWidget()
        self.card.setObjectName("card")
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(14)

        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background: transparent; border: none;")

        # PAGE 0 — diff
        diff_page = QWidget()
        diff_page.setStyleSheet("background: transparent;")
        diff_layout = QVBoxLayout(diff_page)
        diff_layout.setContentsMargins(0, 0, 0, 0)
        diff_layout.setSpacing(12)
        self.input_a = self._path_row(diff_layout, "ORIGINAL FILE (A)", "inputs/kern-1.log", "file")
        self._spacer(diff_layout)
        self.input_b = self._path_row(diff_layout, "NEW FILE (B)", "inputs/kern-2.log", "file")
        self.stack.addWidget(diff_page)

        # PAGE 1 — cluster
        cluster_page = QWidget()
        cluster_page.setStyleSheet("background: transparent;")
        cluster_layout = QVBoxLayout(cluster_page)
        cluster_layout.setContentsMargins(0, 0, 0, 0)
        cluster_layout.setSpacing(12)
        self.input_dir = self._path_row(cluster_layout, "LOG DIRECTORY", "inputs/", "dir")
        cluster_layout.addStretch()
        hint = QLabel("Every .log file in this folder will be compared\nagainst every other file, then clustered automatically.")
        hint.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px; line-height: 1.5;")
        hint.setWordWrap(True)
        cluster_layout.addWidget(hint)
        self.stack.addWidget(cluster_page)

        # PAGE 2 — validate
        validate_page = QWidget()
        validate_page.setStyleSheet("background: transparent;")
        validate_layout = QVBoxLayout(validate_page)
        validate_layout.setContentsMargins(0, 0, 0, 0)
        validate_layout.addStretch()
        validate_layout.addStretch()
        self.stack.addWidget(validate_page)

        card_layout.addWidget(self.stack)
        outer.addWidget(self.card)

        # ── run button ──
        self.run_btn = QPushButton("▶   Run")
        self.run_btn.setObjectName("run")
        self.run_btn.setFixedHeight(50)
        self.run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.run_btn.clicked.connect(self._run)
        outer.addWidget(self.run_btn)

    # ── path row helper ───────────────────────────────────────────────────────
    def _path_row(self, layout, label_text, placeholder, kind):
        lbl = QLabel(label_text)
        lbl.setObjectName("section_label")
        layout.addWidget(lbl)
        box = QFrame()
        box.setStyleSheet(f"QFrame {{ border: 1px solid {BORDER}; border-radius: 8px; background: {SURFACE2}; padding: 2px; }}")
        row = QHBoxLayout(box)
        row.setContentsMargins(4, 2, 4, 2)
        box.setFixedHeight(44)
        row.setSpacing(6)
        field = QLineEdit()
        field.setPlaceholderText(placeholder)
        field.setFixedHeight(28)
        field.setStyleSheet("QLineEdit { border: none; background: transparent; color: " + TEXT + "; font-size: 12px; padding: 0 6px; qproperty-alignment: AlignVCenter; }")
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setFixedWidth(1)
        divider.setStyleSheet(f"background: {BORDER}; border: none;")
        browse = QPushButton("Browse")
        browse.setObjectName("browse")
        browse.setFixedHeight(32)
        browse.setFixedWidth(72)
        browse.setCursor(Qt.CursorShape.PointingHandCursor)
        browse.clicked.connect(lambda: self._browse(field, kind))
        row.addWidget(field)
        row.addWidget(divider)
        row.addWidget(browse)
        layout.addWidget(box)
        return field

    def _spacer(self, layout):
        line = QFrame()
        line.setObjectName("divider")
        line.setFixedHeight(1)
        layout.addWidget(line)

    # ── mode switching ────────────────────────────────────────────────────────
    def _switch_mode(self, mode):
        if mode == "validate":
            self._validate()
            return
        self._mode = mode
        self.tab_diff.setChecked(mode == "diff")
        self.tab_cluster.setChecked(mode == "cluster")
        self.tab_validate.setChecked(False)
        self.stack.setCurrentIndex(0 if mode == "diff" else 1)
        self.run_btn.setVisible(True)
        self.run_btn.setEnabled(True)
        self.run_btn.setText("▶   Run")

    # ── browse ────────────────────────────────────────────────────────────────
    def _browse(self, field, kind):
        start_dir = self._last_dir
        if kind == "dir":
            path = QFileDialog.getExistingDirectory(self, "Select Log Directory", start_dir)
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Select Log File", start_dir, "Log Files (*.log);;All Files (*)")
        if path:
            path = os.path.normpath(path)
            self._last_dir = path if os.path.isdir(path) else os.path.dirname(path)
            if field is self.input_a and not self.input_b.text().strip():
                self.input_b.setPlaceholderText(self._last_dir)
            try:
                path = os.path.relpath(path, ROOT)
            except ValueError:
                pass  # Handles cases on Windows where paths are on different drives
            field.setText(path)

    # ── run ───────────────────────────────────────────────────────────────────
    def _run(self):
        py = PYTHON
        if self._mode == "diff":
            fa = self.input_a.text().strip()
            fb = self.input_b.text().strip()
            if not fa or not fb:
                self._alert("Please select both log files before running.", error=True)
                return
            fa = fa if os.path.isabs(fa) else os.path.join(ROOT, fa)
            fb = fb if os.path.isabs(fb) else os.path.join(ROOT, fb)
            fa, fb = os.path.normpath(fa), os.path.normpath(fb)
            if not os.path.isfile(fa):
                self._alert(f"File A not found:\n{fa}", error=True)
                return
            if not os.path.isfile(fb):
                self._alert(f"File B not found:\n{fb}", error=True)
                return
            cmd = [py, "main.py", fa, fb]
        elif self._mode == "cluster":
            d = self.input_dir.text().strip()
            if not d:
                self._alert("Please select a log directory before running.", error=True)
                return
            d = d if os.path.isabs(d) else os.path.join(ROOT, d)
            d = os.path.normpath(d)
            if not os.path.isdir(d):
                self._alert(f"Directory not found:\n{d}", error=True)
                return
            cmd = [py, "main.py", d]
        else:
            return

        self.run_btn.setEnabled(False)
        self.run_btn.setText("⏳   Running…")
        self.tab_diff.setEnabled(False)
        self.tab_cluster.setEnabled(False)
        self.tab_validate.setEnabled(False)
        self._worker = Worker(cmd)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_done)
        self._worker.finished.connect(self._thread.quit)
        self._thread.start()

    # ── normal run done ───────────────────────────────────────────────────────
    def _on_done(self, ok, output_dir):
        self.run_btn.setEnabled(True)
        self.run_btn.setText("▶   Run")
        self.tab_diff.setEnabled(True)
        self.tab_cluster.setEnabled(True)
        self.tab_validate.setEnabled(True)
        if ok:
            self._show_success(output_dir)
        else:
            detail = getattr(self._worker, "_error_detail", "")
            msg = f"ROOT:    {ROOT}\nPython:  {PYTHON}\n\n"
            msg += f"Error output:\n{detail}" if detail else "No output captured — check that main.py exists in the project folder."
            self._alert(msg, error=True)

    # ── validate ──────────────────────────────────────────────────────────────
    def _validate(self):
        if self._worker is not None and self._thread is not None and self._thread.isRunning():
            return

        script = os.path.normpath(os.path.join(ROOT, "test_datasets", "validate_results.py"))
        if not os.path.isfile(script):
            self._alert(f"validate_results.py not found at:\n{script}\n\nMake sure that test_datasets/ is in your project root.", error=True)
            self.tab_validate.setChecked(False)
            self.tab_diff.setChecked(self._mode == "diff")
            self.tab_cluster.setChecked(self._mode == "cluster")
            return

        previous_mode = self._mode
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Validate", os.path.join(ROOT, "test_datasets"))
        if not folder:
            self.tab_validate.setChecked(False)
            self.tab_diff.setChecked(previous_mode == "diff")
            self.tab_cluster.setChecked(previous_mode == "cluster")
            return

        folder = os.path.normpath(os.path.abspath(folder))
        if not os.path.isdir(folder):
            self._alert(f"Selected folder does not exist:\n{folder}", error=True)
            self.tab_validate.setChecked(False)
            self.tab_diff.setChecked(previous_mode == "diff")
            self.tab_cluster.setChecked(previous_mode == "cluster")
            return

        self._mode = "validate"
        self.tab_diff.setChecked(False)
        self.tab_cluster.setChecked(False)
        self.tab_validate.setChecked(True)
        self.tab_diff.setEnabled(False)
        self.tab_cluster.setEnabled(False)
        self.tab_validate.setEnabled(False)
        self.tab_validate.setText("⏳   Running…")
        self.stack.setCurrentIndex(2)
        self.run_btn.setVisible(False)

        self._worker = Worker([PYTHON, script, folder])
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_validate_done)
        self._worker.finished.connect(self._thread.quit)
        self._thread.start()

    def _on_validate_done(self, ok, output_dir):
        self.tab_diff.setEnabled(True)
        self.tab_cluster.setEnabled(True)
        self.tab_validate.setEnabled(True)
        self.tab_validate.setText("✓   Validate")
        self.tab_validate.setChecked(True)
        self.tab_diff.setChecked(False)
        self.tab_cluster.setChecked(False)
        self.stack.setCurrentIndex(2)
        self.run_btn.setVisible(False)
        if ok:
            self._alert("Validation completed successfully.\n\nThe validation report has been saved in the test_datasets folder.")
        else:
            detail = getattr(self._worker, "_error_detail", "")
            msg = "Validation failed."
            if detail:
                msg += f"\n\nError output:\n{detail}"
            else:
                msg += "\n\nPlease check the validation report for details."
            self._alert(msg, error=True)

    # ── success overlay ──────────────────────────────────────────────────────
    def _show_success(self, output_dir):
        while self.layout().count():
            item = self.layout().takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        layout = self.layout()
        layout.setContentsMargins(40, 50, 40, 40)
        layout.setSpacing(16)
        tick = QLabel("✓")
        tick.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tick.setStyleSheet(f"color: {SUCCESS}; font-size: 52px; font-weight: 700;")
        layout.addWidget(tick)
        h = QLabel("Completed Successfully!")
        h.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h.setStyleSheet(f"color: {TEXT}; font-size: 20px; font-weight: 700;")
        layout.addWidget(h)
        try:
            rel = os.path.relpath(output_dir, ROOT)
        except ValueError:
            rel = output_dir
        sub = QLabel(f"Output saved to   {rel}/")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
        layout.addWidget(sub)
        layout.addSpacing(4)
        self._countdown = 3
        self._cdown_lbl = QLabel(f"Closing in {self._countdown}s...")
        self._cdown_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cdown_lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        layout.addWidget(self._cdown_lbl)
        layout.addSpacing(8)
        open_btn = QPushButton("Open Output Folder")
        open_btn.setObjectName("run")
        open_btn.setFixedHeight(46)
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.clicked.connect(lambda: self._open_folder(output_dir))
        layout.addWidget(open_btn)
        layout.addStretch()
        self._close_timer = QTimer(self)
        self._close_timer.setInterval(1000)
        self._close_timer.timeout.connect(self._tick_close)
        self._close_timer.start()

    def _tick_close(self):
        self._countdown -= 1
        if self._countdown <= 0:
            self._close_timer.stop()
            self.close()
        else:
            self._cdown_lbl.setText(f"Closing in {self._countdown}s...")

    def _open_folder(self, path):
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", path])
            elif sys.platform == "win32":
                os.startfile(path)
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            pass

    def _restart(self):
        while self.layout().count():
            item = self.layout().takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                pass
        self.layout().setContentsMargins(28, 28, 28, 28)
        self.layout().setSpacing(20)
        self._build_ui()
        self._switch_mode(self._mode)

    # ── alert ─────────────────────────────────────────────────────────────────
    def _alert(self, message, error=False):
        box = QMessageBox(self)
        box.setWindowTitle("Error" if error else "Info")
        box.setText(message)
        box.setIcon(QMessageBox.Icon.Critical if error else QMessageBox.Icon.Information)
        box.setStyleSheet(stylesheet())
        box.exec()

# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════
def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("Semantic Diff Tool")
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BG))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Base, QColor(SURFACE))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(SURFACE2))
    palette.setColor(QPalette.ColorRole.Button, QColor(SURFACE2))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
