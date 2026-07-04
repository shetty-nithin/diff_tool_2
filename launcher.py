"""
launcher.py
===========
Desktop application for the Semantic Diff Tool.

Requirements
------------
    pip install PyQt6
    pip install pyinstaller

Build: 
------
    pyinstaller --windowed --name "SemanticDiffTool" --collect-all PyQt6 launcher.py

"""

import os
import sys
import subprocess
import threading

from PyQt6.QtWidgets import (
    QApplication, QWidget, QStackedWidget,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QLineEdit, QFrame, QMessageBox,
    QSizePolicy
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, QTimer
from PyQt6.QtGui import QFont, QFontDatabase, QColor, QPalette, QIcon

# ── project root ──────────────────────────────────────────────────────────────
# When bundled by PyInstaller, __file__ points inside the .app bundle.
# We need the folder where the .app itself lives (next to inputs/, outputs/).
if getattr(sys, "frozen", False):
    # sys.executable is:  <project>/dist/SemanticDiffTool.app/Contents/MacOS/SemanticDiffTool
    # We need:            <project>/
    # So go up 5 levels:  MacOS → Contents → SemanticDiffTool.app → dist → <project>
    ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(sys.executable))
    ))))
else:
    ROOT = os.path.dirname(os.path.abspath(__file__))

# ── find Python interpreter ───────────────────────────────────────────────────
# sys.executable inside a PyInstaller bundle points to the bundled app, not Python.
# We need the real Python to run main.py as a subprocess.
def _find_python():
    if not getattr(sys, "frozen", False):
        return sys.executable          # running normally — sys.executable is Python

    # Running bundled — search for python3 in common locations
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

    # Last resort — ask the shell
    import shutil
    found = shutil.which("python3")
    if found:
        return found

    return "python3"   # hope it's on PATH

PYTHON = _find_python()


# ══════════════════════════════════════════════════════════════════════════════
# Worker — runs main.py in a background thread, emits signals
# ══════════════════════════════════════════════════════════════════════════════

class Worker(QObject):
    finished = pyqtSignal(bool, str)   # success, output_dir

    def __init__(self, cmd):
        super().__init__()
        self.cmd  = cmd
        self._proc = None

    def run(self):
        self._error_detail = ""
        try:
            self._proc = subprocess.Popen(
                self.cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=ROOT,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            out, _ = self._proc.communicate()
            ok = self._proc.returncode == 0
            if not ok:
                # keep last 20 lines of output for the error dialog
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
# Styling constants
# ══════════════════════════════════════════════════════════════════════════════

BG          = "#0f1117"
SURFACE     = "#1a1d27"
SURFACE2    = "#222635"
BORDER      = "#2d3148"
ACCENT      = "#5b6cf9"        # indigo — distinct from both terminal green and claude amber
ACCENT_DARK = "#3d4db8"
TEXT        = "#e2e4ef"
TEXT_DIM    = "#7880a4"
SUCCESS     = "#4caf82"
ERROR       = "#e05c5c"
RADIUS      = "12px"
RADIUS_SM   = "8px"


def stylesheet():
    return f"""
    QWidget {{
        background: {BG};
        color: {TEXT};
        font-family: 'Inter', 'Segoe UI', 'SF Pro Text', system-ui, sans-serif;
        font-size: 13px;
    }}

    /* ── mode selector tabs ── */
    QPushButton#tab_diff, QPushButton#tab_cluster {{
        background: {SURFACE2};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_SM};
        color: {TEXT_DIM};
        font-size: 12px;
        font-weight: 600;
        padding: 10px 0;
        letter-spacing: 0.04em;
    }}
    QPushButton#tab_diff:checked, QPushButton#tab_cluster:checked {{
        background: {ACCENT};
        border-color: {ACCENT};
        color: white;
    }}
    QPushButton#tab_diff:hover:!checked, QPushButton#tab_cluster:hover:!checked {{
        border-color: {ACCENT};
        color: {TEXT};
    }}

    /* ── path inputs ── */
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

    /* ── browse button ── */
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

    /* ── run button ── */
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

    /* ── section labels ── */
    QLabel#section_label {{
        color: {TEXT_DIM};
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.10em;
    }}

    /* ── divider ── */
    QFrame#divider {{
        background: {BORDER};
        border: none;
        max-height: 1px;
    }}

    /* ── card (the white area around inputs) ── */
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
        self._worker   = None
        self._thread   = None
        self._mode     = "diff"
        self._last_dir = ROOT   # remembers last browsed folder

        self.setWindowTitle("Semantic Diff Tool")
        self.setFixedSize(520, 460)
        self.setStyleSheet(stylesheet())

        # centre on screen
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            screen.center().x() - self.width() // 2,
            screen.center().y() - self.height() // 2
        )

        self._build_ui()

    # ── build ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.setSpacing(20)

        # ── header ──
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

        self.tab_diff    = QPushButton("⇄   Diff Two Files")
        self.tab_cluster = QPushButton("◎   Cluster Directory")

        for btn in (self.tab_diff, self.tab_cluster):
            btn.setObjectName("tab_diff" if btn is self.tab_diff else "tab_cluster")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(40)
            tabs.addWidget(btn)

        self.tab_diff.setChecked(True)
        self.tab_diff.clicked.connect(lambda: self._switch_mode("diff"))
        self.tab_cluster.clicked.connect(lambda: self._switch_mode("cluster"))

        outer.addLayout(tabs)

        # ── input card ──
        card = QWidget()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(14)

        # diff inputs (stacked)
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

        card_layout.addWidget(self.stack)
        outer.addWidget(card)

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

        # bordered box wrapping the field + browse button
        box = QFrame()
        box.setStyleSheet(
            f"QFrame {{ border: 1px solid {BORDER}; border-radius: 8px; "
            f"background: {SURFACE2}; padding: 2px; }}"
        )
        row = QHBoxLayout(box)
        row.setContentsMargins(4, 2, 4, 2)
        box.setFixedHeight(44)
        row.setSpacing(6)

        field = QLineEdit()
        field.setPlaceholderText(placeholder)
        field.setFixedHeight(28)
        field.setStyleSheet(
            "QLineEdit { border: none; background: transparent; "
            f"color: {TEXT}; font-size: 12px; padding: 0 6px; "
            "qproperty-alignment: AlignVCenter; }"
        )

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
        self._mode = mode
        self.tab_diff.setChecked(mode == "diff")
        self.tab_cluster.setChecked(mode == "cluster")
        self.stack.setCurrentIndex(0 if mode == "diff" else 1)

    # ── browse ────────────────────────────────────────────────────────────────

    def _browse(self, field, kind):
        # open dialog starting from the last used directory
        start_dir = self._last_dir

        if kind == "dir":
            path = QFileDialog.getExistingDirectory(self, "Select Log Directory", start_dir)
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, "Select Log File", start_dir, "Log Files (*.log);;All Files (*)"
            )

        if path:
            # remember this folder for the next browse call
            self._last_dir = path if os.path.isdir(path) else os.path.dirname(path)

            # if File A was just filled and File B is empty, pre-fill File B
            # with the same directory so the user only needs one more click
            if field is self.input_a and not self.input_b.text().strip():
                self.input_b.setPlaceholderText(self._last_dir)

            # show relative path if inside project root
            try:
                path = os.path.relpath(path, ROOT)
            except ValueError:
                pass
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
            # resolve to absolute paths
            fa = fa if os.path.isabs(fa) else os.path.join(ROOT, fa)
            fb = fb if os.path.isabs(fb) else os.path.join(ROOT, fb)
            if not os.path.isfile(fa):
                self._alert(f"File A not found:\n{fa}", error=True)
                return
            if not os.path.isfile(fb):
                self._alert(f"File B not found:\n{fb}", error=True)
                return
            cmd = [py, "main.py", fa, fb]
        else:
            d = self.input_dir.text().strip()
            if not d:
                self._alert("Please select a log directory before running.", error=True)
                return
            d = d if os.path.isabs(d) else os.path.join(ROOT, d)
            if not os.path.isdir(d):
                self._alert(f"Directory not found:\n{d}", error=True)
                return
            cmd = [py, "main.py", d]

        # disable UI while running
        self.run_btn.setEnabled(False)
        self.run_btn.setText("⏳   Running…")
        self.tab_diff.setEnabled(False)
        self.tab_cluster.setEnabled(False)

        # launch worker thread
        self._worker = Worker(cmd)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_done)
        self._worker.finished.connect(self._thread.quit)
        self._thread.start()

    # ── done ──────────────────────────────────────────────────────────────────

    def _on_done(self, ok, output_dir):
        # re-enable UI
        self.run_btn.setEnabled(True)
        self.run_btn.setText("▶   Run")
        self.tab_diff.setEnabled(True)
        self.tab_cluster.setEnabled(True)

        if ok:
            self._show_success(output_dir)
        else:
            detail = getattr(self._worker, "_error_detail", "")

            # show a debug-friendly message so you can see what went wrong
            msg = (
                f"ROOT:    {ROOT}\n"
                f"Python:  {PYTHON}\n\n"
            )
            if detail:
                msg += f"Error output:\n{detail}"
            else:
                msg += "No output captured — check that main.py exists in the project folder."

            self._alert(msg, error=True)

    # ── success overlay ───────────────────────────────────────────────────────

    def _show_success(self, output_dir):
        """Replace the window content with a success screen, then auto-close."""
        # clear existing layout
        while self.layout().count():
            item = self.layout().takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        layout = self.layout()
        layout.setContentsMargins(40, 50, 40, 40)
        layout.setSpacing(16)

        # tick icon
        tick = QLabel("✓")
        tick.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tick.setStyleSheet(f"color: {SUCCESS}; font-size: 52px; font-weight: 700;")
        layout.addWidget(tick)

        # headline
        h = QLabel("Completed Successfully!")
        h.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h.setStyleSheet(f"color: {TEXT}; font-size: 20px; font-weight: 700;")
        layout.addWidget(h)

        # sub text — output location
        rel = os.path.relpath(output_dir, ROOT)
        sub = QLabel(f"Output saved to   {rel}/")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
        layout.addWidget(sub)

        layout.addSpacing(4)

        # countdown label
        self._countdown = 3
        self._cdown_lbl = QLabel(f"Closing in {self._countdown}s...")
        self._cdown_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cdown_lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        layout.addWidget(self._cdown_lbl)

        layout.addSpacing(8)

        # open folder button
        open_btn = QPushButton("Open Output Folder")
        open_btn.setObjectName("run")
        open_btn.setFixedHeight(46)
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.clicked.connect(lambda: self._open_folder(output_dir))
        layout.addWidget(open_btn)

        layout.addStretch()

        # auto-close timer — ticks every second, closes at 0
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
        import subprocess, sys
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
        """Rebuild the UI from scratch (Run Again)."""
        # clear layout
        while self.layout().count():
            item = self.layout().takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                # nested layouts
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
    # High-DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("Semantic Diff Tool")
    app.setStyle("Fusion")

    # dark palette for native widgets (dialogs etc.)
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window,          QColor(BG))
    palette.setColor(QPalette.ColorRole.WindowText,      QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Base,            QColor(SURFACE))
    palette.setColor(QPalette.ColorRole.AlternateBase,   QColor(SURFACE2))
    palette.setColor(QPalette.ColorRole.Button,          QColor(SURFACE2))
    palette.setColor(QPalette.ColorRole.ButtonText,      QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Highlight,       QColor(ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
