"""
Validates clustering results against ground truth.

Metrics:
    1. Cluster Purity
    2. Silhouette Score
    3. TP / FP / FN / TN
    4. Precision / Recall / F1
    5. Cluster-to-cluster distances
    6. Expected cluster behavior

Usage:
    python validate_results.py
"""

import json
import os
import sys
import numpy as np
from collections import defaultdict, Counter
from sklearn.metrics import silhouette_score
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from main import run_multi_file_cluster


# ============================================================================
# Configuration
# ============================================================================

GROUPS = [
    "test_datasets/group_a",
    "test_datasets/group_b",
    "test_datasets/group_c",
    "test_datasets/group_d",
    "test_datasets/group_e"
]

CLUSTERS_JSON = "outputs/clusters.json"
REPORT_PATH = "test_datasets/validation_report.txt"

PURITY_THRESHOLD = 0.80


# ============================================================================
# Utility functions
# ============================================================================

def load_json(path, label):
    if not os.path.exists(path):
        raise FileNotFoundError(f"[ERROR] {label} not found at: {path}")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def is_anomaly(label):
    """
    Normal: normal, cfg_*
    Anomaly: warn_*, fail_*, contaminated
    """
    return (
        label.startswith("warn_")
        or label.startswith("fail_")
        or label == "contaminated"
    )

def is_configuration(label):
    return label.startswith("cfg_")

def is_normal(label):
    return label == "normal" or is_configuration(label)


# ============================================================================
# Cluster helpers
# ============================================================================

def build_file_to_cluster(clusters):
    """
    Convert:
        {
            "0": [{"filename": "a.log"}, {"filename": "b.log"}],
            "1": [{"filename": "c.log"}]
        }

    into:
        {
            "a.log": "0",
            "b.log": "0",
            "c.log": "1"
        }
    """

    file_to_cluster = {}

    for cluster_id, entries in clusters.items():
        for entry in entries:
            filename = os.path.basename(entry["filename"])
            file_to_cluster[filename] = str(cluster_id)

    return file_to_cluster


def get_real_cluster_ids(clusters):
    """
    Return actual clusters excluding DBSCAN noise (-1).
    """

    return [
        str(cid)
        for cid in clusters.keys()
        if str(cid) != "-1"
    ]


# ============================================================================
# Cluster Purity
# ============================================================================

def calculate_purity(rows):
    """
    Paper: Rosenberg, A. & Hirschberg, J. (2007). V-Measure: A Conditional Entropy-Based External Cluster Evaluation Measure.

    Calculate standard clustering purity using ground-truth labels.
    Purity = (1 / N) * sum_k max_j(n_kj)
    where:
        N    = total number of assigned files
        n_kj = number of files in predicted cluster k
               belonging to ground-truth class j

    For each predicted cluster, only the majority ground-truth
    class contributes to the numerator.

    Returns:
        purity
        cluster_labels
    """
    cluster_labels = defaultdict(list)
    for filename, gt_label, cluster_id in rows:
        if cluster_id == "NOT FOUND":
            continue
        cluster_labels[str(cluster_id)].append(gt_label)

    total_files = sum(len(labels) for labels in cluster_labels.values())
    if total_files == 0:
        return 0.0, cluster_labels

    majority_correct = 0
    for cluster_id, labels in cluster_labels.items():
        label_counts = Counter(labels)
        majority_count = max(label_counts.values())
        majority_correct += majority_count
    purity = majority_correct / total_files

    return purity, cluster_labels

# ============================================================================
# Silhouette Score
# ============================================================================

def calculate_silhouette(clusters_json):
    """
    Calculate Silhouette Score using the ORIGINAL pairwise overall_distance matrix.
    This is important because the clustering system is based on pairwise log distances.
    Returns None if the score cannot be calculated.
    """

    if "distance_matrix" not in clusters_json: return None
    if "filenames" not in clusters_json: return None

    D = np.asarray(
        clusters_json["distance_matrix"],
        dtype=float
    )

    filenames = [
        os.path.basename(f)
        for f in clusters_json["filenames"]
    ]

    clusters = clusters_json.get("clusters", {})

    file_to_cluster = build_file_to_cluster(clusters)

    labels = []

    for filename in filenames:
        cluster_id = file_to_cluster.get(filename, None)

        if cluster_id is None: return None
        if cluster_id == "-1": return None  # Ignore DBSCAN noise for silhouette.

        labels.append(int(cluster_id))

    labels = np.asarray(labels)

    # Silhouette requires at least 2 clusters.
    unique_labels = set(labels)

    if len(unique_labels) < 2: return None
    if len(labels) <= len(unique_labels): return None # Every cluster must contain at least one sample.

    try:
        score = silhouette_score(D, labels, metric="precomputed")
        return float(score)

    except Exception as e:
        print(f"  [WARNING] Silhouette calculation failed: {e}")

        return None


# ============================================================================
# Cluster-to-cluster distances
# ============================================================================

def calculate_cluster_distances(clusters_json, file_to_cluster):
    """
    Calculate average distance BETWEEN clusters.
    This is different from avg_distance inside a cluster.

    Example:
        Cluster 0 internal avg distance = 0.0020
        Cluster 1 internal avg distance = 0.0020

    does NOT tell us:
        Cluster 0 ↔ Cluster 1 = ???

    This function calculates that missing value.
    """

    if "distance_matrix" not in clusters_json: return {}
    if "filenames" not in clusters_json: return {}

    D = np.asarray(
        clusters_json["distance_matrix"],
        dtype=float
    )

    filenames = [
        os.path.basename(f)
        for f in clusters_json["filenames"]
    ]

    index = {
        filename: i
        for i, filename in enumerate(filenames)
    }

    cluster_files = defaultdict(list)

    for filename, cluster_id in file_to_cluster.items():
        if cluster_id == "NOT FOUND":
            continue
        if filename in index:
            cluster_files[cluster_id].append(filename)

    cluster_ids = sorted(
        cluster_files.keys(),
        key=lambda x: int(x)
    )

    distances = {}

    for i in range(len(cluster_ids)):
        for j in range(i + 1, len(cluster_ids)):
            c1 = cluster_ids[i]
            c2 = cluster_ids[j]

            values = []

            for file_a in cluster_files[c1]:
                for file_b in cluster_files[c2]:
                    ia = index[file_a]
                    ib = index[file_b]

                    values.append(D[ia][ib])

            if values:
                distances[f"{c1}<->{c2}"] = float(np.mean(values))

    return distances


# ============================================================================
# Group-specific validation
# ============================================================================

def validate_expected_behavior(group_name, gt_files, rows, cluster_labels):
    result = {
        "expected_behavior": "",
        "behavior_pass": False
    }

    # GROUP A
    if group_name == "group_a":
        result["expected_behavior"] = ("All normal files should belong to one cluster.")

        clusters_for_normal = set()

        for fname, gt, cluster in rows:
            if gt == "normal" and cluster != "NOT FOUND":
                clusters_for_normal.add(cluster)

        result["behavior_pass"] = (len(clusters_for_normal) == 1)

    # GROUP B
    elif group_name == "group_b":

        result["expected_behavior"] = ("Configuration variations may form separate sub-clusters but must remain non-anomalous.")

        # Find whether any cfg_* file was assigned to an anomaly cluster.
        anomaly_clusters = set()

        for cluster_id, labels in cluster_labels.items():
            anomaly_count = sum(is_anomaly(label) for label in labels)

            if labels and anomaly_count / len(labels) > 0.5:
                anomaly_clusters.add(cluster_id)

        config_in_anomaly = any(
            is_configuration(gt)
            and cluster in anomaly_clusters
            for _, gt, cluster in rows
        )

        result["behavior_pass"] = not config_in_anomaly

    # GROUP C
    elif group_name == "group_c":

        result["expected_behavior"] = ("Warning logs should be distinguishable from normal operation.")

        normal_clusters = {
            cluster
            for _, gt, cluster in rows
            if gt == "normal" and cluster != "NOT FOUND"
        }

        warning_clusters = {
            cluster
            for _, gt, cluster in rows
            if gt.startswith("warn") and cluster != "NOT FOUND"
        }

        result["behavior_pass"] = bool(warning_clusters - normal_clusters)

    # GROUP D
    elif group_name == "group_d":

        result["expected_behavior"] = ("Failure logs should be distinguishable from normal operation.")

        normal_clusters = {
            cluster
            for _, gt, cluster in rows
            if gt == "normal"
            and cluster != "NOT FOUND"
        }

        failure_clusters = {
            cluster
            for _, gt, cluster in rows
            if gt.startswith("fail")
            and cluster != "NOT FOUND"
        }

        result["behavior_pass"] = bool(failure_clusters - normal_clusters)

    # GROUP E
    elif group_name == "group_e":

        result["expected_behavior"] = ("Contaminated logs should be distinguishable from normal kernel logs.")

        normal_clusters = {
            cluster
            for _, gt, cluster in rows
            if gt == "normal"
            and cluster != "NOT FOUND"
        }

        contamination_clusters = {
            cluster
            for _, gt, cluster in rows
            if gt.startswith("contamination") and cluster != "NOT FOUND"
        }

        result["behavior_pass"] = bool(contamination_clusters - normal_clusters)

    return result


# ============================================================================
# Main validation
# ============================================================================

def validate(group_folder, clusters_json_path):
    gt_path = os.path.join(group_folder, "ground_truth.json")
    gt = load_json(gt_path, "ground_truth.json")
    clus = load_json(clusters_json_path, "clusters.json")
    gt_files = gt["files"]
    description = gt.get("_description", "")
    expected_clusters = gt.get("expected_num_clusters", "?")
    group_name = os.path.basename(os.path.abspath(group_folder))

    # Build mapping
    raw_clusters = clus.get("clusters", {})
    file_to_cluster = build_file_to_cluster(raw_clusters)
    algorithm_used = clus.get("algorithm", "unknown")

    rows = []

    for fname, gt_label in gt_files.items():
        assigned = file_to_cluster.get(fname, "NOT FOUND")
        rows.append((fname, gt_label, assigned))

    # Header
    sep = "=" * 75
    print("\n" + sep)
    print(f"VALIDATION REPORT — {group_name.upper()}")
    print(sep)
    print(f"Description       : {description}")
    print(f"Algorithm         : {algorithm_used}")
    print(f"Expected clusters : {expected_clusters}")

    real_clusters = get_real_cluster_ids(raw_clusters)
    noise_count = len(raw_clusters.get("-1", []))

    print(
        f"Found clusters    : {len(real_clusters)}"
        f"   noise/outliers: {noise_count}"
    )

    # File assignment table
    print("\nFile assignments:")
    print(
        f"{'File':<45}"
        f"{'Ground Truth':<25}"
        f"{'Cluster':<10}"
    )
    print("-" * 85)

    for fname, gt_label, assigned in rows:
        print(
            f"{fname:<45}"
            f"{gt_label:<25}"
            f"{assigned:<10}"
        )

    # Cluster Purity
    purity, cluster_labels = calculate_purity(rows)

    print("\n" + "-" * 75)
    print(f"Cluster Purity : {purity:.6f}")
    print("                 1.000000 = perfect")

    print("\nCluster composition:")
    for cluster_id in sorted(cluster_labels.keys(), key=lambda x: int(x)):
        counts = Counter(cluster_labels[cluster_id])
        majority = counts.most_common(1)[0][0]
        print(
            f"  Cluster {cluster_id}: "
            f"{dict(counts)}"
            f"   majority={majority}"
        )

    # Silhouette
    silhouette = calculate_silhouette(clus)
    print("\nSilhouette Score:")
    if silhouette is None:
        print("  Not available")
    else:
        print(f"  {silhouette:.6f}")
        print("  Range: -1 to +1")

    # Cluster-to-cluster distances
    print("\nCluster-to-cluster distances:")
    inter_cluster = calculate_cluster_distances(clus, file_to_cluster)
    if not inter_cluster:
        print("  Not available")
    else:
        for pair, distance in sorted(inter_cluster.items()):
            print(
                f"  {pair:<15} = "
                f"{distance:.10f}"
            )

    # Binary anomaly classification
    anomaly_clusters = set()

    for cluster_id, labels in cluster_labels.items():
        if not labels: continue

        anomaly_fraction = sum(is_anomaly(label) for label in labels) / len(labels)

        if anomaly_fraction > 0.5:
            anomaly_clusters.add(cluster_id)

    TP = FP = FN = TN = 0

    for fname, gt_label, assigned in rows:
        if assigned == "NOT FOUND": continue

        true_anomaly = is_anomaly(gt_label)
        predicted_anomaly = (assigned in anomaly_clusters)

        if true_anomaly and predicted_anomaly:
            TP += 1
        elif not true_anomaly and predicted_anomaly:
            FP += 1
        elif true_anomaly and not predicted_anomaly:
            FN += 1
        else:
            TN += 1

    precision = (TP / (TP + FP)
        if TP + FP > 0
        else 0.0
    )

    recall = (TP / (TP + FN)
        if TP + FN > 0
        else 0.0
    )

    f1 = (2 * precision * recall / (precision + recall)
        if precision + recall > 0
        else 0.0
    )

    print("\nAnomaly Detection:")
    print(f"  TP        : {TP}")
    print(f"  FP        : {FP}")
    print(f"  FN        : {FN}")
    print(f"  TN        : {TN}")
    print(f"  Precision : {precision:.6f}")
    print(f"  Recall    : {recall:.6f}")
    print(f"  F1        : {f1:.6f}")

    # ------------------------------------------------------------------------
    # Group-specific expected behavior
    # ------------------------------------------------------------------------

    behavior = validate_expected_behavior(
        group_name,
        gt_files,
        rows,
        cluster_labels
    )

    print("\nExpected behavior:")
    print(f"  {behavior['expected_behavior']}")
    print(
        f"  Result: "
        f"{'PASS' if behavior['behavior_pass'] else 'FAIL'}"
    )

    # Final verdict
    purity_pass = (purity >= PURITY_THRESHOLD)

    behavior_pass = behavior["behavior_pass"]

    if silhouette is not None:
        silhouette_available = True
    else:
        silhouette_available = False

    verdict = ("PASS"
        if purity_pass and behavior_pass
        else "FAIL"
    )

    print("\n" + "-" * 75)
    print(
        f"Purity threshold : "
        f"{'PASS' if purity_pass else 'FAIL'}"
    )
    print(
        f"Expected behavior: "
        f"{'PASS' if behavior_pass else 'FAIL'}"
    )
    print(f"FINAL VERDICT    : {verdict}")
    print(sep)

    # ------------------------------------------------------------------------
    # Return results for combined report
    # ------------------------------------------------------------------------

    return {
        "group": group_name,
        "algorithm": algorithm_used,
        "expected_clusters": expected_clusters,
        "found_clusters": len(real_clusters),
        "purity": purity,
        "silhouette": silhouette,

        "TP": TP,
        "FP": FP,
        "FN": FN,
        "TN": TN,

        "precision": precision,
        "recall": recall,
        "f1": f1,
        "behavior_pass": behavior_pass,
        "purity_pass": purity_pass,
        "verdict": verdict,
        "cluster_distances": inter_cluster,
    }


if __name__ == "__main__":

    if len(sys.argv) != 2:
        print("\nUsage:")
        print("  python test_datasets/validate_results.py <folder>")
        print("\nExample:")
        print(
            "  python test_datasets/validate_results.py "
            "test_datasets/group_c"
        )
        sys.exit(1)

    # Get selected folder
    dataset_folder = os.path.abspath(sys.argv[1])

    # Check folder
    if not os.path.isdir(dataset_folder):
        print(
            f"\n[ERROR] Folder does not exist:"
            f"\n{dataset_folder}"
        )
        sys.exit(1)

    # Folder name
    folder_name = os.path.basename(os.path.normpath(dataset_folder))
    report_path = os.path.join(
        dataset_folder,
        f"validation_report_{folder_name}.txt"
    )

    print("\n"+ "=" * 85)
    print("VALIDATION")
    print("=" * 85)
    print(f"Dataset folder : {dataset_folder}")
    print(f"Report         : {report_path}")
    print("=" * 85)

    all_results = []

    with open(report_path,"w",encoding="utf-8") as report:
        try:
            print(
                f"\nRunning clustering for:"
                f"\n{dataset_folder}"
            )

            run_multi_file_cluster(dataset_folder)

            print("\nRunning validation...")

            result = validate(dataset_folder,CLUSTERS_JSON)
            all_results.append(result)

            # Write validation result
            report.write("=" * 85 + "\n")
            report.write(f"VALIDATION RESULT: {folder_name}\n")
            report.write("=" * 85 + "\n")
            report.write(f"Dataset folder       : {dataset_folder}\n")
            report.write(f"Algorithm            : " f"{result.get('algorithm', 'N/A')}\n")
            report.write(f"Expected clusters    : " f"{result.get('expected_clusters', 'N/A')}\n")
            report.write(f"Found clusters       : " f"{result.get('found_clusters', 'N/A')}\n")
            report.write(f"Purity               : " f"{result.get('purity', 'N/A')}\n")
            report.write(f"Silhouette           : " f"{result.get('silhouette', 'N/A')}\n")
            report.write(f"TP                   : " f"{result.get('TP', 'N/A')}\n")
            report.write(f"FP                   : " f"{result.get('FP', 'N/A')}\n")
            report.write(f"FN                   : " f"{result.get('FN', 'N/A')}\n")
            report.write(f"TN                   : " f"{result.get('TN', 'N/A')}\n")
            report.write(f"Precision            : " f"{result.get('precision', 'N/A')}\n")
            report.write(f"Recall               : " f"{result.get('recall', 'N/A')}\n")
            report.write(f"F1                   : " f"{result.get('f1', 'N/A')}\n")
            report.write(f"Behavior pass        : " f"{result.get('behavior_pass', 'N/A')}\n")
            report.write(f"Purity pass          : " f"{result.get('purity_pass', 'N/A')}\n")
            report.write(f"Verdict              : " f"{result.get('verdict', 'N/A')}\n")
            report.write(f"Cluster distances    : " f"{result.get('cluster_distances', 'N/A')}\n")
            report.write("\n")
            report.write("=" * 85 + "\n")
            report.write("VALIDATION COMPLETED SUCCESSFULLY\n")
            report.write("=" * 85 + "\n")
            report.flush()

            print("\n"+ "=" * 85)
            print("VALIDATION COMPLETED SUCCESSFULLY")
            print(f"Report saved to:" f"\n{report_path}")
            print("=" * 85)

        except Exception as e:
            # Validation failed
            print(f"\n[ERROR] Validation failed:" f"\n{e}")
            report.write("=" * 85 + "\n")
            report.write("VALIDATION FAILED\n")
            report.write("=" * 85 + "\n")
            report.write(f"Dataset folder : {dataset_folder}\n")
            report.write(f"Error          : {e}\n")
            report.write("\n")
            raise
