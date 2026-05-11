"""
log_comparator.py
=================
Compare N log files against a single baseline using patience_diff.
Rank every file by how different it is from the baseline.

Cluster N log files into groups using KMeans.
Files that behaved similarly land in the same cluster.
"""

import os
import json
import importlib.util
import sys

def _require_sklearn():
    if importlib.util.find_spec("sklearn") is None:
        raise ImportError(
            "scikit-learn is required for clustering.\n"
            "Install it with:  pip install scikit-learn"
        )
    if importlib.util.find_spec("numpy") is None:
        raise ImportError(
            "numpy is required for clustering.\n"
            "Install it with:  pip install numpy"
        )

class LogComparator:
    """
    Attributes
    ----------
    baseline   : path to the reference / known-good log file
    output_dir : directory where per-pair HTML diff files are written
    results    : dict  { filename -> DiffVector }  populated by compare_all() through patience_diff()
    clusters   : dict  { filename -> cluster_label }  populated by cluster()
    """

    def __init__(self, baseline: str, output_dir: str = "outputs/"):
        self.baseline   = baseline
        self.output_dir = output_dir
        self.results    = {}   # { filename: DiffVector }
        self.clusters   = {}   # { filename: cluster_label }

        os.makedirs(output_dir, exist_ok=True)

    # =========================================================================
    # Compare all files in a "inputs" directory against the baseline
    # =========================================================================

    def compare_all(self, log_dir: str, extension: str = ".log"):
        """
        Run patience_diff(baseline, each_file) for every .log file in log_dir.
        Stores the resulting DiffVector in self.results.

        Parameters
        ----------
        log_dir   : directory containing the log files to compare
        extension : only files ending with this suffix are processed
        """
        from patience_diff import patience_diff

        log_files = [
            f for f in os.listdir(log_dir)
            if f.endswith(extension)
            and os.path.abspath(os.path.join(log_dir, f)) != os.path.abspath(self.baseline)
        ]

        if not log_files:
            print(f"[LogComparator] No {extension} files found in {log_dir}")
            return

        print(f"[LogComparator] Comparing {len(log_files)} files against baseline: {self.baseline}\n")

        for filename in sorted(log_files):
            file_b      = os.path.join(log_dir, filename)
            output_stem = os.path.join(self.output_dir, filename.replace(extension, ""))

            print(f"  Diffing: {filename} ...", end=" ", flush=True)

            try:
                vec = patience_diff(self.baseline, file_b, output_stem)
                self.results[filename] = vec
                print(f"done  (distance={vec.overall_distance:.4f})")

            except Exception as e:
                print(f"ERROR: {e}")

        print(f"\n[LogComparator] Done. {len(self.results)} files processed.")

    # =========================================================================
    # Ranking and Reporting
    # =========================================================================
    def get_ranking(self) -> list:
        return sorted(self.results.items(), key=lambda x: x[1].overall_distance)

    def print_ranking(self):
        """
        Example output
        --------------
        Rank  File                         Distance  Similarity  Churn   Moved
        ----  ---------------------------  --------  ----------  ------  ------
           1  kern-2-jan.log                0.0312     96.88%    1.20%   0.00%
           2  kern-4.feb.log                0.1847     81.53%    12.00%  0.00%
           3  kern-2.mar.log                0.4521     54.79%    31.00%  2.10%
        """
        ranking = self.get_ranking()

        if not ranking:
            print("[LogComparator] No results to display. Run compare_all() first.")
            return

        def status(dist):
            if dist == 0.0:       return "IDENTICAL"
            elif dist < 0.10:     return "NORMAL"
            elif dist < 0.30:     return "DRIFT"
            else:                 return "ANOMALY"

        header = f"{'Rank':>4}  {'File':<35}  {'Distance':>8}  {'Similarity':>10}  {'Churn':>6}  {'Moved':>6}  {'Status'}"
        print(header)
        print("-" * len(header))

        for rank, (filename, vec) in enumerate(ranking, start=1):
            print(
                f"{rank:>4}  {filename:<35}  "
                f"{vec.overall_distance:>8.4f}  "
                f"{vec.similarity_ratio * 100:>9.2f}%  "
                f"{vec.churn_ratio * 100:>5.2f}%  "
                f"{vec.move_ratio * 100:>5.2f}%  "
                f"{status(vec.overall_distance)}"
            )

    def save_ranking(self, output_path: str):
        """
        Saves the ranking as a JSON file.
        Each entry contains the filename and all ratio metrics.
        """
        ranking = self.get_ranking()

        data = []
        for rank, (filename, vec) in enumerate(ranking, start=1):
            entry = vec.to_dict() if hasattr(vec, "to_dict") else {}
            entry["rank"]     = rank
            entry["filename"] = filename
            data.append(entry)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        print(f"[LogComparator] Ranking saved to: {output_path}")

    # =========================================================================
    # Unsupervised Clustering
    # =========================================================================

    def cluster(self, n_clusters: int = 3, random_state: int = 42):
        """
        Cluster all compared files into n_clusters groups using KMeans.
        Files with similar diff vectors land in the same cluster.

        Parameters
        ----------
        n_clusters   : number of clusters (groups) to form
        random_state : random seed for reproducibility

        How it works
        ------------
        1. Each file's DiffVector is converted to a plain list of 6 floats
           via to_cluster_array().
        2. The feature matrix is standardised (zero mean, unit variance) so
           no single feature dominates just because of its scale.
        3. KMeans finds n_clusters centroids and assigns each file to the
           nearest one.
        4. Results are stored in self.clusters  { filename: label }.
        """
        _require_sklearn()
        import numpy as np
        from sklearn.cluster import KMeans
        from sklearn.preprocessing import StandardScaler

        if not self.results:
            print("[LogComparator] No results to cluster. Run compare_all() first.")
            return
        
        if len(self.results) < n_clusters:
            print(
                f"[LogComparator] Not enough files ({len(self.results)}) "
                f"to form {n_clusters} clusters."
            )
            return

        # Step 1 — build feature matrix
        # Each row is one file's 6-float feature vector
        filenames = list(self.results.keys())
        X = [self.results[f].to_cluster_array() for f in filenames]
        X = [[float(v) for v in row] for row in X]   # ensure plain floats

        import numpy as np
        X_np = np.array(X)

        # Step 2 — standardise
        # StandardScaler subtracts the mean and divides by std for each feature.
        # This prevents similarity_ratio (which varies 0–1 a lot) from dominating over move_ratio (which is usually close to 0).
        scaler   = StandardScaler()
        X_scaled = scaler.fit_transform(X_np)
        # Step 3 — KMeans clustering
        kmeans = KMeans(n_clusters=n_clusters, random_state=random_state, n_init=10)
        labels = kmeans.fit_predict(X_scaled)

        # Step 4 — store results
        self.clusters = {filename: int(label) for filename, label in zip(filenames, labels)}

        # Compute per-cluster stats for interpretation
        self._cluster_stats = {}
        for label in range(n_clusters):
            members = [f for f, l in self.clusters.items() if l == label]
            vecs    = [self.results[f] for f in members]

            self._cluster_stats[label] = {
                "count":            len(members),
                "avg_distance":     round(sum(v.overall_distance for v in vecs) / len(vecs), 4) if vecs else 0.0,
                "avg_similarity":   round(sum(v.similarity_ratio  for v in vecs) / len(vecs), 4) if vecs else 0.0,
                "avg_churn":        round(sum(v.churn_ratio        for v in vecs) / len(vecs), 4) if vecs else 0.0,
                "avg_move":         round(sum(v.move_ratio         for v in vecs) / len(vecs), 4) if vecs else 0.0,
            }

        print(f"[LogComparator] Clustering complete. {n_clusters} clusters formed.")

    def print_clusters(self):
        """
        Example output
        --------------
        Cluster 0  (3 files)  avg_distance=0.0201  avg_similarity=97.99%
          → kern-1_jan.log
          → kern-2_mar.log
          → kern-2_feb.log
        """
        if not self.clusters:
            print("[LogComparator] No clusters yet. Run cluster() first.")
            return

        # Group filenames by cluster label
        groups = {}
        for filename, label in self.clusters.items():
            groups.setdefault(label, []).append(filename)

        for label in sorted(groups.keys()):
            stats   = self._cluster_stats[label]
            members = sorted(groups[label])

            print(
                f"\nCluster {label}  ({stats['count']} files)  "
                f"avg_distance={stats['avg_distance']:.4f}  "
                f"avg_similarity={stats['avg_similarity'] * 100:.2f}%  "
                f"avg_churn={stats['avg_churn'] * 100:.2f}%  "
                f"avg_move={stats['avg_move'] * 100:.2f}%"
            )

            for f in members:
                vec = self.results[f]
                print(f"    → {f:<35}  distance={vec.overall_distance:.4f}")

    def save_clusters(self, output_path: str):
        """
        Saves cluster assignments and per-cluster stats to a JSON file.
        """
        if not self.clusters:
            print("[LogComparator] No clusters yet. Run cluster() first.")
            return

        groups = {}
        for filename, label in self.clusters.items():
            groups.setdefault(str(label), []).append({
                "filename":        filename,
                "overall_distance": self.results[filename].overall_distance,
                "similarity_ratio": self.results[filename].similarity_ratio,
                "churn_ratio":      self.results[filename].churn_ratio,
                "move_ratio":       self.results[filename].move_ratio,
            })

        output = {
            "cluster_stats": {
                str(k): v for k, v in self._cluster_stats.items()
            },
            "clusters": groups
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)

        print(f"[LogComparator] Clusters saved to: {output_path}")


    # =========================================================================
    # Graphs
    # =========================================================================

    def plot_scatter(self, output_path="outputs/scatter.png"):
        """
        Scatter plot (2D projection of 6D feature vectors).

        Each dot is one log file.
        Colour  = which cluster it belongs to.
        Position = where it sits in the 6D feature space projected to 2D via PCA.

        What to look for
        ----------------
        Dots far apart    → files are very different
        Dots close        → files behaved similarly
        Tight cluster     → consistent behaviour in that group
        Dot far from all  → outlier / anomaly
        """
        _require_sklearn()
        import numpy as np
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        from sklearn.decomposition import PCA
        from sklearn.preprocessing import StandardScaler

        if not self.clusters:
            print("[LogComparator] Run cluster() before plot_scatter().")
            return

        filenames  = list(self.results.keys())
        X          = [self.results[f].to_cluster_array() for f in filenames]
        labels     = [self.clusters[f] for f in filenames]
        X_scaled   = StandardScaler().fit_transform(X)
        X_2d       = PCA(n_components=2).fit_transform(X_scaled)
        pca_obj    = PCA(n_components=2).fit(X_scaled)
        var        = pca_obj.explained_variance_ratio_
        n_clusters = max(labels) + 1
        palette    = plt.cm.get_cmap("tab10", n_clusters)

        fig, ax = plt.subplots(figsize=(10, 7))
        fig.patch.set_facecolor("#F8F9FA")
        ax.set_facecolor("#F8F9FA")

        for i, (fname, label) in enumerate(zip(filenames, labels)):
            x, y  = X_2d[i]
            color = palette(label)
            vec   = self.results[fname]
            size  = 80 + vec.overall_distance * 400
            ax.scatter(x, y, color=color, s=size, alpha=0.85,
                       edgecolors="white", linewidths=1.5, zorder=3)
            short = fname.replace(".log", "")
            if len(short) > 18:
                short = short[:16] + ".."
            ax.annotate(short, xy=(x, y), xytext=(6, 4),
                        textcoords="offset points", fontsize=8, color="#333333")

        legend_patches = [
            mpatches.Patch(
                color=palette(lbl),
                label=f"Cluster {lbl}  (avg dist={self._cluster_stats[lbl]['avg_distance']:.3f})"
            )
            for lbl in range(n_clusters)
        ]
        ax.legend(handles=legend_patches, loc="upper right", fontsize=9, framealpha=0.9)
        ax.set_xlabel(f"PC1  ({var[0]*100:.1f}% variance)", fontsize=10)
        ax.set_ylabel(f"PC2  ({var[1]*100:.1f}% variance)", fontsize=10)
        ax.set_title(
            f"Log File Clustering — Scatter Plot\n"
            f"Baseline: {os.path.basename(self.baseline)}  |  "
            f"{len(filenames)} files  |  {n_clusters} clusters\n"
            "Dot size = overall distance from baseline",
            fontsize=11, pad=14
        )
        ax.grid(True, linestyle="--", alpha=0.4, zorder=0)
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"[LogComparator] Scatter plot saved to: {output_path}")

    def plot_bar(self, output_path="outputs/metrics_bar.png"):
        """
        Horizontal bar chart.

        Shows each file's 4 key metrics side by side.
        Good companion to the text ranking table — same data, visual form.

        What to look for
        ----------------
        Long green bar  → high similarity (file is close to baseline)
        Long red bar    → many deletions
        Long blue bar   → many insertions
        Long orange bar → high churn (lots of adds + removes combined)
        """
        import numpy as np
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        if not self.results:
            print("[LogComparator] Run compare_all() before plot_bar().")
            return

        ranking   = self.get_ranking()
        filenames = [r[0].replace(".log", "")[:25] for r in ranking]
        vecs      = [r[1] for r in ranking]
        n         = len(filenames)
        y         = list(range(n))
        h         = 0.18

        fig, ax = plt.subplots(figsize=(11, max(5, n * 0.55)))
        fig.patch.set_facecolor("#F8F9FA")
        ax.set_facecolor("#F8F9FA")

        ax.barh([yi + h*1.5 for yi in y], [v.similarity_ratio  for v in vecs],
                h, label="Similarity",  color="#2DA44E", alpha=0.85)
        ax.barh([yi + h*0.5 for yi in y], [v.deletion_ratio    for v in vecs],
                h, label="Deletion",    color="#CF222E", alpha=0.85)
        ax.barh([yi - h*0.5 for yi in y], [v.insertion_ratio   for v in vecs],
                h, label="Insertion",   color="#1F6FEB", alpha=0.85)
        ax.barh([yi - h*1.5 for yi in y], [v.churn_ratio       for v in vecs],
                h, label="Churn",       color="#E36209", alpha=0.85)

        ax.set_yticks(y)
        ax.set_yticklabels(filenames, fontsize=9)
        ax.set_xlabel("Ratio  (0.0 = none,  1.0 = all lines)", fontsize=10)
        ax.set_xlim(0, 1.05)
        ax.set_title(
            f"Per-File Diff Metrics\nBaseline: {os.path.basename(self.baseline)}  |  "
            "Sorted by overall distance (top = most similar)",
            fontsize=11, pad=14
        )
        ax.legend(loc="lower right", fontsize=9, framealpha=0.9)
        ax.grid(axis="x", linestyle="--", alpha=0.4)
        ax.invert_yaxis()
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"[LogComparator] Bar chart saved to: {output_path}")

    # ===========================================================================
    # Save / Load — persist results so we don't need to re-run the diff everytime
    # ===========================================================================

    def save_results(self, output_path: str):
        """
        Saves all DiffVectors to JSON so we can reload them later without re-running the full diff on every file.
        """
        from diff_vector import DiffVector
        data = {
            filename: asdict_safe(vec)
            for filename, vec in self.results.items()
        }
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"[LogComparator] Results saved to: {output_path}")

    def load_results(self, input_path: str):
        """
        Loads previously saved DiffVectors from JSON. Lets us skip compare_all() and go straight to cluster().
        """
        from diff_vector import DiffVector
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.results = {}
        for filename, fields in data.items():
            v = DiffVector(**fields)
            self.results[filename] = v

        print(f"[LogComparator] Loaded {len(self.results)} results from: {input_path}")


# ---------------------------------------------------------------------------
# Helper — safe asdict that works even if dataclasses.asdict is not imported
# ---------------------------------------------------------------------------

def asdict_safe(obj):
    try:
        from dataclasses import asdict
        return asdict(obj)
    except Exception:
        return obj.__dict__



if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python log_comparator.py <baseline.log> <log_directory>")
        print("Example: python log_comparator.py logs/kern-1.log logs/")
        sys.exit(1)

    baseline  = sys.argv[1]
    log_dir   = sys.argv[2]
    n_clusters = int(sys.argv[3]) if len(sys.argv) > 3 else 3

    cmp = LogComparator(baseline=baseline, output_dir="outputs/diff_with_baseline")

    print("=" * 60)
    print("Ranking files by difference from baseline")
    print("=" * 60)
    cmp.compare_all(log_dir)
    cmp.print_ranking()
    cmp.save_ranking("outputs/ranking.json")
    cmp.plot_bar("outputs/graphs/metrics_bar.png")

    print("\n" + "=" * 60)
    print(f"Clustering into {n_clusters} groups")
    print("=" * 60)
    cmp.cluster(n_clusters=n_clusters)
    cmp.print_clusters()
    cmp.save_clusters("outputs/clusters.json")
    cmp.plot_scatter("outputs/graphs/scatter.png")
