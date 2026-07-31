"""
validate_results.py
-------------------
Validates tool's clusters.json output against a group's ground_truth.json.

Usage:
    python validate_results.py <group_folder> <clusters_json>

Examples:
    python validate_results.py test_datasets/group_a outputs/clusters.json

Format of clusters.json (tool output):
{
  "algorithm": "...",
  "clusters": {
    "0": [ {"filename": "file1.log", "overall_distance": 0.05, ...}, ... ],
    "1": [ {"filename": "file2.log", ...} ],
    "-1": [ ... ]   <- DBSCAN noise points
  }
}
"""

import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from main import run_multi_file_cluster
from collections import defaultdict, Counter

# ─────────────────────────────────────────────────────────────────────────────
def load_json(path, label):
    if not os.path.exists(path):
        sys.exit(f"[ERROR] {label} not found at: {path}")
    with open(path) as f:
        return json.load(f)

def is_anomaly(label):
    """Normal = 'normal' or 'cfg_*'.  Anomaly = warn_*, fail_*, contaminated."""
    return any(label.startswith(p) for p in ("warn_", "fail_", "contaminated"))

# ─────────────────────────────────────────────────────────────────────────────
def validate(group_folder, clusters_json_path):

    gt   = load_json(os.path.join(group_folder, "ground_truth.json"), "ground_truth.json")
    clus = load_json(clusters_json_path, "clusters.json")

    gt_files          = gt["files"]            # {filename: gt_label}
    expected_clusters = gt.get("expected_num_clusters", "?")
    description       = gt.get("_description", "")

    # ── Build {filename: cluster_id} map from tool's output format ──
    file_to_cluster = {}
    raw_clusters = clus.get("clusters", {})
    for cluster_id, file_list in raw_clusters.items():
        for entry in file_list:
            fname = os.path.basename(entry["filename"])
            file_to_cluster[fname] = cluster_id

    algorithm_used = clus.get("algorithm", "unknown")

    # ── Header ────────────────────────────────────────────────────────────────
    group_name = os.path.basename(os.path.abspath(group_folder))
    sep = "=" * 65
    print(f"\n{sep}")
    print(f"  VALIDATION REPORT — {group_name.upper()}")
    print(f"{sep}")
    print(f"  Description : {description}")
    print(f"  Algorithm   : {algorithm_used}")
    print(f"  Expected #clusters : {expected_clusters}")
    print(f"  Found    #clusters : {len([k for k in raw_clusters if k != '-1'])}"
          f"  (+{len(raw_clusters.get('-1',[]))} noise/outlier in cluster -1)")

    # ── Per-file table ────────────────────────────────────────────────────────
    print(f"\n  {'File':<42} {'Ground Truth':<26} {'Tool Output':<12}")
    print(f"  {'─'*42} {'─'*26} {'─'*12}")

    rows = []
    for fname, gt_label in gt_files.items():
        assigned = file_to_cluster.get(fname, "NOT FOUND")
        rows.append((fname, gt_label, assigned))

        match = "-" if assigned != "NOT FOUND" else f"File not found in {group_name}"
        print(f"  {fname:<42} {gt_label:<26} {assigned:<12}")

    # ── Cluster Purity ────────────────────────────────────────────────────────
    cluster_to_gt_labels = defaultdict(list)
    for fname, gt_label, assigned in rows:
        if assigned != "NOT FOUND":
            cluster_to_gt_labels[assigned].append(gt_label)

    total_assigned   = sum(len(v) for v in cluster_to_gt_labels.values())
    majority_correct = sum(
        Counter(labels).most_common(1)[0][1]
        for labels in cluster_to_gt_labels.values() if labels
    )

    """Within each cluster your tool produced, are all the files of the same type?"""
    purity = majority_correct / total_assigned if total_assigned > 0 else 0.0

    print(f"\n  {'─'*60}")
    print(f"  Cluster Purity : {purity:.3f}   (1.0 = perfect, ≥0.80 = pass)")

    print(f"\n  Cluster contents:")
    for cid in sorted(cluster_to_gt_labels):
        counts  = Counter(cluster_to_gt_labels[cid])
        majority = counts.most_common(1)[0][0]
        marker  = "⚠️  NOISE" if cid == "-1" else ""
        print(f"    cluster {cid}: {dict(counts)}  ← majority GT label: '{majority}' {marker}")

    # ── TP / FP / FN  (binary: normal vs anomaly) ────────────────────────────
    # Decide which clusters are "anomaly clusters":
    # a cluster is anomalous if >50% of its GT-labelled files are anomalies
    anomaly_clusters = {
        cid for cid, labels in cluster_to_gt_labels.items()
        if labels and
        sum(1 for l in labels if is_anomaly(l)) / len(labels) > 0.5
    }

    TP = FP = FN = TN = 0
    for fname, gt_label, assigned in rows:
        if assigned == "NOT FOUND":
            continue
        pred_anom = assigned in anomaly_clusters
        true_anom = is_anomaly(gt_label)
        if true_anom  and pred_anom:      TP += 1
        elif not true_anom and pred_anom: FP += 1
        elif true_anom and not pred_anom: FN += 1
        else:                             TN += 1

    denom_p  = TP + FP
    denom_r  = TP + FN
    precision = TP / denom_p if denom_p > 0 else 0.0
    recall    = TP / denom_r if denom_r > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)
          if (precision + recall) > 0 else 0.0)

    print(f"\n  Anomaly Detection (normal files vs anomalous files):")
    print(f"    TP  anomalous file → anomaly cluster : {TP}")
    print(f"    FP  normal file   → anomaly cluster  : {FP}  ← false alarm")
    print(f"    FN  anomalous file → normal cluster  : {FN}  ← missed anomaly")
    print(f"    TN  normal file   → normal cluster   : {TN}")
    print(f"    Precision : {precision:.3f}")
    print(f"    Recall    : {recall:.3f}")
    print(f"    F1 Score  : {f1:.3f}")

    # ── Verdict ───────────────────────────────────────────────────────────────
    cluster_count_ok = (
        expected_clusters == "?" or
        abs(len(raw_clusters) - expected_clusters) <= 1   # allow ±1 tolerance
    )
    verdict = "PASS ✅" if (purity >= 0.80 and cluster_count_ok) else "FAIL ❌"

    print(f"\n  {'─'*60}")
    print(f"  FINAL VERDICT : {verdict}   (threshold: purity ≥ 0.80)")
    print(f"{sep}\n")

    # ── Return dict for report aggregation ───────────────────────────────────
    return {
        "group": group_name,
        "algorithm": algorithm_used,
        "purity": round(purity, 3),
        "expected_clusters": expected_clusters,
        "found_clusters": len(raw_clusters),
        "TP": TP, "FP": FP, "FN": FN, "TN": TN,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "verdict": verdict
    }

# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    """
    if len(sys.argv) != 3:
        print("Usage  : python validate_results.py <group_folder> <clusters_json>")
        print("Example: python validate_results.py test_datasets/group_a outputs/clusters.json")
        sys.exit(1)
    validate(sys.argv[1], sys.argv[2])
    """

    tool_output_path = "outputs/clusters.json"
    groups = ["test_datasets/group_a", "test_datasets/group_b", "test_datasets/group_c", "test_datasets/group_d", "test_datasets/group_e"]
    
    with open("test_datasets/validation_report.txt", "w") as f:
        for g in groups:
            run_multi_file_cluster(g)
            result = validate(g, tool_output_path)

            f.write("=" * 50 + "\n")
            f.write(f"{g}\n")
            f.write("=" * 50 + "\n")

            for key, value in result.items():
                f.write(f"{key:20}: {value}\n")

            f.write("\n")

