"""
log_comparator.py
=================
Pairwise comparison of N log files using patience_diff — every file is compared against every other.

Clustering uses three scientific methods:
  1. Agglomerative Clustering  — hierarchical, uses precomputed NED distance matrix
  2. DBSCAN                    — density-based, finds outliers automatically
  3. Gaussian Mixture Model    — probabilistic, soft cluster membership

Optimal k is chosen automatically using:
  - Silhouette Score (Rousseeuw, 1987)  — measures cluster separation
  - Davies-Bouldin Index (1979)         — measures cluster compactness
  - BIC for GMM                         — penalises model complexity

The best algorithm and k are selected by consensus across all three metrics.
"""

import os
import json
import importlib.util


# =========================================================================
# Dependency check
# =========================================================================

def _require_sklearn():
    for pkg, install in [("sklearn", "scikit-learn"), ("numpy", "numpy"), ("scipy", "scipy")]:
        if importlib.util.find_spec(pkg) is None:
            raise ImportError(f"{install} is required.\nInstall: pip install {install}")


# =========================================================================
# LogComparator
# =========================================================================

class LogComparator:
    """
    Pairwise log file comparison and unsupervised clustering.

    Attributes
    ----------
    output_dir      : where per-pair HTML diff files are written
    results         : { (file_a, file_b): DiffVector }   — pairwise diff results
    clusters        : { filename: cluster_label }        — final cluster assignments
    algorithm_used  : name of the algorithm that won the consensus vote
    """

    def __init__(self, output_dir: str):
        self.output_dir     = output_dir
        self.results        = {}
        self.clusters       = {}
        self.algorithm_used = None
        self._cluster_stats = {}
        self._D             = None      # NxN distance matrix (numpy array)
        self._filenames     = []        # ordered list of filenames

        os.makedirs(os.path.join("outputs", "pairwise_diffs"), exist_ok=True)
        os.makedirs(os.path.join("outputs", "graphs"),         exist_ok=True)

    # =========================================================================
    # STEP 1 — Pairwise comparison
    # =========================================================================

    def compare_pairwise(self, log_dir: str, extension: str = ".log"):
        """
        Run patience_diff(file_a, file_b) for every unique pair of log files.
        N files → N*(N-1)/2 comparisons.
        Results stored in self.results as { (file_a, file_b): DiffVector }.
        """
        from patience_diff import patience_diff
        import itertools

        log_files = sorted([
            f for f in os.listdir(log_dir)
            if f.endswith(extension)
        ])

        if len(log_files) < 2:
            print("[LogComparator] Need at least 2 files.")
            return

        n_pairs = len(log_files) * (len(log_files) - 1) // 2
        print(f"[LogComparator] Pairwise comparing {len(log_files)} files "
              f"({n_pairs} pairs)\n")

        self.results = {}

        for file_a, file_b in itertools.combinations(log_files, 2):
            path_a      = os.path.join(log_dir, file_a)
            path_b      = os.path.join(log_dir, file_b)
            output_stem = os.path.join(
                self.output_dir,
                f"{file_a}_vs_{file_b}".replace(".log", "")
            )

            print(f"  {file_a}  vs  {file_b} ...", end=" ", flush=True)
            try:
                vec = patience_diff(path_a, path_b, output_stem)
                self.results[(file_a, file_b)] = vec
                print(f"done  (distance={vec.overall_distance:.4f})")
            except Exception as e:
                print(f"ERROR: {e}")

        print(f"\n[LogComparator] Done. {len(self.results)} pairs compared.")

    # =========================================================================
    # STEP 2 — Build NxN distance matrix
    # =========================================================================

    def build_distance_matrix(self):
        """
        Converts pairwise DiffVectors into a symmetric NxN distance matrix.

        Uses the NED (Normalised Edit Distance) stored in overall_distance.
        NED is proven to satisfy the triangle inequality (Li & Bo, 2007),
        making it a valid metric for all distance-based clustering algorithms.

        Returns
        -------
        D         : numpy ndarray, shape (N, N)
        filenames : list of N filenames in the same order as D's rows/cols
        """
        import numpy as np

        filenames = sorted(set(f for pair in self.results for f in pair))
        n         = len(filenames)
        idx       = {f: i for i, f in enumerate(filenames)}
        D         = np.zeros((n, n))

        for (fa, fb), vec in self.results.items():
            i, j    = idx[fa], idx[fb]
            D[i][j] = vec.overall_distance
            D[j][i] = vec.overall_distance     # symmetric: dist(A,B) == dist(B,A)

        self._D         = D
        self._filenames = filenames
        return D, filenames

    # =========================================================================
    # STEP 3 — Clustering with automatic algorithm and k selection
    # =========================================================================

    def cluster(self, random_state: int = 42):
        """
        Cluster N log files using three algorithms. Select the best result
        by consensus of three scientific validity indices.

        Algorithms tried
        ----------------
        1. Agglomerative Clustering (Ward / Average linkage)
           - Hierarchical, deterministic
           - Works directly on the precomputed NED distance matrix
           - k tested from 2 to N-1, best k chosen by silhouette score

        2. DBSCAN (Density-Based Spatial Clustering of Applications with Noise)
           - No k required — finds clusters by density automatically
           - Marks low-density points as outliers (label = -1)
           - eps tuned automatically using k-nearest-neighbour distance plot elbow
           - Best for: data with noise / irregular cluster shapes

        3. Gaussian Mixture Model (GMM)
           - Probabilistic: each file has a soft membership probability
           - k chosen by BIC (Bayesian Information Criterion) — lower = better
           - Best for: overlapping clusters

        Validity indices used for consensus
        ------------------------------------
        - Silhouette Score (higher = better, range -1 to 1)
          Measures how similar each point is to its own cluster vs others.
          Reference: Rousseeuw (1987)

        - Davies-Bouldin Index (lower = better, range 0 to ∞)
          Measures average ratio of within-cluster scatter to between-cluster
          separation. Reference: Davies & Bouldin (1979)

        - Calinski-Harabasz Score (higher = better)
          Ratio of between-cluster to within-cluster dispersion.
          Also known as the Variance Ratio Criterion.

        Winner selection
        ----------------
        Each algorithm is ranked 1-3 on each index.
        The algorithm with the lowest total rank wins.
        In case of tie, silhouette score breaks it.
        """
        _require_sklearn()
        import numpy as np
        from sklearn.metrics import silhouette_score, davies_bouldin_score, calinski_harabasz_score
        from sklearn.preprocessing import StandardScaler
        from sklearn.decomposition import PCA

        if not self.results:
            print("[LogComparator] No results. Run compare_pairwise() first.")
            return

        D, filenames = self.build_distance_matrix()
        n = len(filenames)

        if n < 3:
            print("[LogComparator] Need at least 3 files to cluster.")
            return

        # Feature matrix for GMM (uses feature vectors, not distance matrix)
        X_raw    = np.array([self._avg_vector(f)[:6] for f in filenames])
        X_scaled = StandardScaler().fit_transform(X_raw)

        candidates = {}   # { algorithm_name: (labels, silhouette, db, ch) }

        # =========================================================================
        # Algorithm 1 — Agglomerative Clustering
        # =========================================================================
        candidates.update(
            self._try_agglomerative(D, filenames, n, random_state)
        )

        # =========================================================================
        # Algorithm 2 — DBSCAN
        # =========================================================================
        candidates.update(
            self._try_dbscan(D, filenames, n)
        )

        # =========================================================================
        # Algorithm 3 — GMM
        # =========================================================================
        candidates.update(
            self._try_gmm(X_scaled, filenames, n, random_state)
        )

        if not candidates:
            print("[LogComparator] No valid clustering found.")
            return

        # =========================================================================
        # Consensus vote — rank each candidate on all three indices
        # =========================================================================
        names = list(candidates.keys())

        sil_scores = {name: candidates[name]["silhouette"] for name in names}
        db_scores  = {name: candidates[name]["davies_bouldin"] for name in names}
        ch_scores  = {name: candidates[name]["calinski_harabasz"] for name in names}

        # Rank: silhouette → higher is better (rank 1 = highest)
        sil_rank = {n: r for r, n in enumerate(
            sorted(names, key=lambda x: sil_scores[x], reverse=True), 1)}
        # Rank: davies-bouldin → lower is better (rank 1 = lowest)
        db_rank  = {n: r for r, n in enumerate(
            sorted(names, key=lambda x: db_scores[x]), 1)}
        # Rank: calinski-harabasz → higher is better (rank 1 = highest)
        ch_rank  = {n: r for r, n in enumerate(
            sorted(names, key=lambda x: ch_scores[x], reverse=True), 1)}

        total_rank = {
            name: sil_rank[name] + db_rank[name] + ch_rank[name]
            for name in names
        }

        winner = min(total_rank, key=lambda x: (total_rank[x], -sil_scores[x]))

        print(f"\n[LogComparator] Clustering comparison:")
        print(f"  {'Algorithm':<35}  {'Silhouette':>10}  {'Davies-Bouldin':>14}  {'Calinski-H':>10}  {'Rank':>5}")
        print(f"  {'-'*35}  {'-'*10}  {'-'*14}  {'-'*10}  {'-'*5}")
        for name in sorted(names, key=lambda x: total_rank[x]):
            marker = " ← winner" if name == winner else ""
            print(
                f"  {name:<35}  "
                f"{sil_scores[name]:>10.4f}  "
                f"{db_scores[name]:>14.4f}  "
                f"{ch_scores[name]:>10.2f}  "
                f"{total_rank[name]:>5}{marker}"
            )

        # =========================================================================
        # Store final result
        # =========================================================================
        self.algorithm_used = winner
        labels              = candidates[winner]["labels"]
        self.clusters       = {f: int(l) for f, l in zip(filenames, labels)}

        unique_labels = sorted(set(l for l in labels if l >= 0))

        print(f"\n[LogComparator] Winner: {winner}")
        print(f"[LogComparator] {len(unique_labels)} clusters formed "
              f"({'including outliers' if -1 in labels else 'no outliers'})")

        self._compute_cluster_stats(filenames, labels, unique_labels)

    # =========================================================================
    # Internal — individual algorithm runners
    # =========================================================================

    def _try_agglomerative(self, D, filenames, n, random_state):
        """
        Try Agglomerative Clustering for k = 2 to n-1.
        Pick the k with the best silhouette score.
        Returns a dict of candidates.
        """
        from sklearn.cluster import AgglomerativeClustering
        from sklearn.metrics import silhouette_score, davies_bouldin_score, calinski_harabasz_score
        import numpy as np

        X_raw    = np.array([self._avg_vector(f)[:6] for f in filenames])

        best_k      = 2
        best_sil    = -1
        best_labels = None
        sil_scores  = {}

        for k in range(2, n):
            model  = AgglomerativeClustering(
                n_clusters=k, metric="precomputed", linkage="average"
            )
            labels = model.fit_predict(D)

            if len(set(labels)) < 2:
                continue

            sil = silhouette_score(D, labels, metric="precomputed")
            sil_scores[k] = round(sil, 4)

            if sil > best_sil:
                best_sil    = sil
                best_k      = k
                best_labels = labels

        if best_labels is None:
            return {}

        print(f"[LogComparator] Agglomerative: best k={best_k}  "
              f"silhouette={best_sil:.4f}  scores={sil_scores}")

        db = davies_bouldin_score(X_raw, best_labels)
        ch = calinski_harabasz_score(X_raw, best_labels)

        return {
            f"Agglomerative (k={best_k})": {
                "labels":            best_labels,
                "silhouette":        round(best_sil, 4),
                "davies_bouldin":    round(db, 4),
                "calinski_harabasz": round(ch, 4),
            }
        }

    def _try_dbscan(self, D, filenames, n):
        """
        DBSCAN with automatic eps selection using the k-distance elbow method.

        The k-distance plot:
          For each point, compute its distance to its k-th nearest neighbour.
          Sort these distances. The 'elbow' in the curve is a good eps value.
          Points with distances above eps are considered noise.

        Reference: Ester et al. (1996). A density-based algorithm for
          discovering clusters in large spatial databases with noise.
          KDD-96, 226-231.
        """
        from sklearn.cluster import DBSCAN
        from sklearn.metrics import silhouette_score, davies_bouldin_score, calinski_harabasz_score
        from sklearn.neighbors import NearestNeighbors
        import numpy as np

        X_raw = np.array([self._avg_vector(f)[:6] for f in filenames])

        # Auto-select eps using 4-NN distance elbow
        k_nn  = min(4, n - 1)
        nbrs  = NearestNeighbors(n_neighbors=k_nn, metric="precomputed").fit(D)
        dists, _ = nbrs.kneighbors(D)
        kth_dist = np.sort(dists[:, -1])

        # Elbow = point of maximum curvature
        # Approximate as the index where second derivative is maximum
        if len(kth_dist) >= 3:
            d1    = np.diff(kth_dist)
            d2    = np.diff(d1)
            elbow = np.argmax(d2) + 1
            eps   = kth_dist[elbow]
        else:
            eps = np.median(kth_dist)

        # Clamp eps to a reasonable range
        eps = float(np.clip(eps, 0.01, 0.99))

        model  = DBSCAN(eps=eps, min_samples=2, metric="precomputed")
        labels = model.fit_predict(D)

        n_clusters = len(set(labels) - {-1})
        n_noise    = list(labels).count(-1)

        print(f"[LogComparator] DBSCAN: eps={eps:.4f}  "
              f"clusters={n_clusters}  noise={n_noise}")

        if n_clusters < 2:
            print("[LogComparator] DBSCAN: fewer than 2 clusters — skipping")
            return {}

        # For validity indices, treat noise points as their own cluster
        # only if there are valid clusters to compare against
        valid_mask = labels >= 0
        if valid_mask.sum() < 2:
            return {}

        try:
            sil = silhouette_score(D[valid_mask][:, valid_mask],
                                   labels[valid_mask], metric="precomputed")
            db  = davies_bouldin_score(X_raw[valid_mask], labels[valid_mask])
            ch  = calinski_harabasz_score(X_raw[valid_mask], labels[valid_mask])
        except Exception:
            return {}

        return {
            f"DBSCAN (eps={eps:.3f}, clusters={n_clusters})": {
                "labels":            labels,
                "silhouette":        round(float(sil), 4),
                "davies_bouldin":    round(float(db), 4),
                "calinski_harabasz": round(float(ch), 4),
            }
        }

    def _try_gmm(self, X_scaled, filenames, n, random_state):
        """
        Gaussian Mixture Model with BIC-based k selection.

        BIC (Bayesian Information Criterion) penalises model complexity.
        The k with the lowest BIC fits the data well without overfitting.

        Reference: Schwarz, G. (1978). Estimating the dimension of a model.
          Annals of Statistics 6(2), 461-464.
        """
        from sklearn.mixture import GaussianMixture
        from sklearn.metrics import silhouette_score, davies_bouldin_score, calinski_harabasz_score
        from sklearn.preprocessing import StandardScaler
        import numpy as np

        best_bic    = float("inf")
        best_k      = 2
        best_labels = None
        bic_scores  = {}

        for k in range(2, n):
            try:
                gmm    = GaussianMixture(
                    n_components=k, random_state=random_state,
                    n_init=5, covariance_type="full"
                )
                gmm.fit(X_scaled)
                bic = gmm.bic(X_scaled)
                bic_scores[k] = round(bic, 2)

                if bic < best_bic:
                    best_bic    = bic
                    best_k      = k
                    best_labels = gmm.predict(X_scaled)
            except Exception:
                continue

        if best_labels is None:
            return {}

        if len(set(best_labels)) < 2:
            return {}

        print(f"[LogComparator] GMM: best k={best_k}  "
              f"BIC={best_bic:.2f}  scores={bic_scores}")

        try:
            # GMM uses feature space (X_scaled), not distance matrix
            # so we use euclidean metric for silhouette
            sil = silhouette_score(X_scaled, best_labels)
            db  = davies_bouldin_score(X_scaled, best_labels)
            ch  = calinski_harabasz_score(X_scaled, best_labels)
        except Exception:
            return {}

        return {
            f"GMM (k={best_k})": {
                "labels":            best_labels,
                "silhouette":        round(float(sil), 4),
                "davies_bouldin":    round(float(db), 4),
                "calinski_harabasz": round(float(ch), 4),
            }
        }

    # =========================================================================
    # Internal — cluster stats
    # =========================================================================

    def _compute_cluster_stats(self, filenames, labels, unique_labels):
        self._cluster_stats = {}

        for label in unique_labels:
            members = [f for f, l in zip(filenames, labels) if l == label]
            pairs   = [
                self.results.get((a, b)) or self.results.get((b, a))
                for a in members for b in members if a != b
            ]
            pairs = [p for p in pairs if p is not None]

            self._cluster_stats[label] = {
                "count":          len(members),
                "avg_distance":   round(sum(p.overall_distance for p in pairs) / len(pairs), 4) if pairs else 0.0,
                "avg_similarity": round(sum(p.similarity_ratio  for p in pairs) / len(pairs), 4) if pairs else 1.0,
                "avg_churn":      round(sum(p.churn_ratio        for p in pairs) / len(pairs), 4) if pairs else 0.0,
                "avg_move":       round(sum(p.move_ratio         for p in pairs) / len(pairs), 4) if pairs else 0.0,
            }

        # Outliers from DBSCAN get their own entry
        if -1 in labels:
            outliers = [f for f, l in zip(filenames, labels) if l == -1]
            self._cluster_stats[-1] = {
                "count":          len(outliers),
                "avg_distance":   0.0,
                "avg_similarity": 0.0,
                "avg_churn":      0.0,
                "avg_move":       0.0,
            }

    # =========================================================================
    # STEP 4 — Print and save results
    # =========================================================================

    def print_clusters(self):
        if not self.clusters:
            print("[LogComparator] No clusters yet. Run cluster() first.")
            return

        groups = {}
        for filename, label in self.clusters.items():
            groups.setdefault(label, []).append(filename)

        print(f"\n[LogComparator] Algorithm used: {self.algorithm_used}\n")

        for label in sorted(groups.keys()):
            stats   = self._cluster_stats.get(label, {})
            members = sorted(groups[label])
            name    = f"OUTLIERS" if label == -1 else f"Cluster {label}"

            print(
                f"{name}  ({stats.get('count', len(members))} files)  "
                f"avg_distance={stats.get('avg_distance', 0):.4f}  "
                f"avg_similarity={stats.get('avg_similarity', 0) * 100:.2f}%  "
                f"avg_churn={stats.get('avg_churn', 0) * 100:.2f}%  "
                f"avg_move={stats.get('avg_move', 0) * 100:.2f}%"
            )

            for f in members:
                pairs    = [v for (fa, fb), v in self.results.items()
                            if fa == f or fb == f]
                avg_dist = round(sum(p.overall_distance for p in pairs) / len(pairs), 4) if pairs else 0.0
                print(f"    → {f:<35}  avg_distance={avg_dist:.4f}")

    def save_clusters(self, output_path: str):
        if not self.clusters:
            print("[LogComparator] No clusters yet. Run cluster() first.")
            return

        groups = {}
        for filename, label in self.clusters.items():
            pairs    = [v for (fa, fb), v in self.results.items()
                        if fa == filename or fb == filename]
            avg = lambda attr: round(sum(getattr(p, attr) for p in pairs) / len(pairs), 4) if pairs else 0.0

            groups.setdefault(str(label), []).append({
                "filename":         filename,
                "overall_distance": avg("overall_distance"),
                "similarity_ratio": avg("similarity_ratio"),
                "churn_ratio":      avg("churn_ratio"),
                "move_ratio":       avg("move_ratio"),
            })

        output = {
            "algorithm":     self.algorithm_used,
            "cluster_stats": {str(k): v for k, v in self._cluster_stats.items()},
            "clusters":      groups,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)

        print(f"[LogComparator] Clusters saved to: {output_path}")

    # =========================================================================
    # STEP 5 — Graphs
    # =========================================================================

    def _avg_vector(self, filename):
        """
        Returns a 7-float list: 6 ratio features + overall_distance.
        Averaged across all pairs involving this file.
        """
        pairs = [v for (fa, fb), v in self.results.items()
                 if fa == filename or fb == filename]
        if not pairs:
            return [0.0] * 7
        attrs = ["similarity_ratio", "structural_change", "deletion_ratio",
                 "insertion_ratio", "churn_ratio", "move_ratio", "overall_distance"]
        return [
            sum(getattr(v, attr) for v in pairs) / len(pairs)
            for attr in attrs
        ]

    def plot_scatter(self, output_path="outputs/graphs/scatter.png"):
        """
        PCA scatter plot. Each dot = one log file. Colour = cluster.
        Dot size = average distance from all other files.
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

        filenames  = list(self.clusters.keys())
        X          = np.array([self._avg_vector(f)[:6] for f in filenames])
        labels     = [self.clusters[f] for f in filenames]
        X_scaled   = StandardScaler().fit_transform(X)
        pca        = PCA(n_components=2)
        X_2d       = pca.fit_transform(X_scaled)
        var        = pca.explained_variance_ratio_

        unique_labels = sorted(set(labels))
        palette       = matplotlib.colormaps["tab10"]

        fig, ax = plt.subplots(figsize=(10, 7))
        fig.patch.set_facecolor("#F8F9FA")
        ax.set_facecolor("#F8F9FA")

        for i, (fname, label) in enumerate(zip(filenames, labels)):
            x, y     = X_2d[i]
            color    = "#888888" if label == -1 else palette(label)
            avg_dist = self._avg_vector(fname)[6]
            size     = 80 + avg_dist * 400
            marker   = "x" if label == -1 else "o"

            ax.scatter(x, y, color=color, s=size, alpha=0.85, marker=marker,
                       edgecolors="white", linewidths=1.5, zorder=3)

            short = fname.replace(".log", "")
            if len(short) > 18:
                short = short[:16] + ".."
            ax.annotate(short, xy=(x, y), xytext=(6, 4),
                        textcoords="offset points", fontsize=8, color="#333333")

        legend_patches = []
        for lbl in unique_labels:
            color = "#888888" if lbl == -1 else palette(lbl)
            name  = "Outliers" if lbl == -1 else f"Cluster {lbl}"
            stats = self._cluster_stats.get(lbl, {})
            legend_patches.append(
                mpatches.Patch(color=color,
                               label=f"{name}  (avg dist={stats.get('avg_distance', 0):.3f})")
            )

        ax.legend(handles=legend_patches, loc="upper right", fontsize=9, framealpha=0.9)
        ax.set_xlabel(f"PC1  ({var[0]*100:.1f}% variance)", fontsize=10)
        ax.set_ylabel(f"PC2  ({var[1]*100:.1f}% variance)", fontsize=10)
        ax.set_title(
            f"Log File Clustering — {self.algorithm_used}\n"
            f"{len(filenames)} files  |  "
            f"{len([l for l in unique_labels if l >= 0])} clusters\n"
            "Dot size = avg pairwise distance  |  ✕ = outlier",
            fontsize=11, pad=14
        )
        ax.grid(True, linestyle="--", alpha=0.4, zorder=0)
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"[LogComparator] Scatter plot saved to: {output_path}")

    def plot_dendrogram(self, output_path="outputs/graphs/dendrogram.png"):
        """
        Hierarchical clustering dendrogram.
        Height of each merge = dissimilarity between merged groups.
        Cut at the largest vertical gap to choose n_clusters.
        """
        import numpy as np
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from scipy.cluster.hierarchy import dendrogram, linkage
        from sklearn.preprocessing import StandardScaler

        if not self.results:
            print("[LogComparator] Run compare_pairwise() first.")
            return

        filenames = list(self.clusters.keys()) if self.clusters else list(
            sorted(set(f for pair in self.results for f in pair))
        )
        X        = np.array([self._avg_vector(f)[:6] for f in filenames])
        X_scaled = StandardScaler().fit_transform(X)
        Z        = linkage(X_scaled, method="ward")
        labels   = [f.replace(".log", "")[:20] for f in filenames]

        fig, ax = plt.subplots(figsize=(max(10, len(filenames) * 1.2), 6))
        fig.patch.set_facecolor("#F8F9FA")
        ax.set_facecolor("#F8F9FA")

        dendrogram(Z, labels=labels, ax=ax, leaf_rotation=45,
                   leaf_font_size=9, color_threshold=0.7 * max(Z[:, 2]))

        ax.set_title(
            f"Log File Clustering — Dendrogram\n"
            f"{len(filenames)} files  |  "
            "Height = dissimilarity  |  "
            "Cut at the largest vertical gap to choose n_clusters",
            fontsize=11, pad=14
        )
        ax.set_xlabel("Log File", fontsize=10)
        ax.set_ylabel("Dissimilarity (Ward linkage)", fontsize=10)
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"[LogComparator] Dendrogram saved to: {output_path}")


# =========================================================================
# Entry point
# =========================================================================
"""
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python log_comparator.py <log_directory>")
        print("Example: python log_comparator.py inputs/")
        sys.exit(1)

    log_dir = sys.argv[1]
    cmp     = LogComparator(output_dir="outputs/pairwise_diffs")

    print("=" * 60)
    print("Pairwise comparing all log files")
    print("=" * 60)
    cmp.compare_pairwise(log_dir)

    print("\n" + "=" * 60)
    print("Clustering — auto-selecting algorithm and k")
    print("=" * 60)
    cmp.cluster()
    cmp.print_clusters()
    cmp.save_clusters("outputs/clusters.json")
    cmp.plot_scatter("outputs/graphs/scatter.png")
    cmp.plot_dendrogram("outputs/graphs/dendrogram.png")
"""
