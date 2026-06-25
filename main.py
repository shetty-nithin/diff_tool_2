"""
Usage
-----
Two files — visual diff:
    python main.py inputs/kern-1.log inputs/kern-2.log

One directory — pairwise comparison + clustering:
    python main.py inputs/
"""

import os
import sys
import time


def run_two_file_diff(file_1, file_2):
    """
    MODE 1 — Two specific files.
    Runs patience_diff and shows the HTML diff output.
    """
    from patience_diff import patience_diff

    if not os.path.isfile(file_1):
        print(f"[ERROR] File not found: {file_1}")
        sys.exit(1)
    if not os.path.isfile(file_2):
        print(f"[ERROR] File not found: {file_2}")
        sys.exit(1)

    os.makedirs("outputs", exist_ok=True)

    name_1 = os.path.splitext(os.path.basename(file_1))[0]
    name_2 = os.path.splitext(os.path.basename(file_2))[0]
    output_stem = os.path.join("outputs", f"{name_1}_vs_{name_2}")

    start = time.perf_counter()
    patience_diff(file_1, file_2, output_stem)
    elapsed = time.perf_counter() - start

    print("\n" + "\033[92m" + " Diff generated successfully ".center(50, "-"))
    print(f"{'Algorithm':15}: Patience algorithm")
    print(f"{'File A':15}: {file_1}")
    print(f"{'File B':15}: {file_2}")
    print(f"{'Output':15}: {output_stem}.html")
    print(f"{'Execution time':15}: {elapsed:.6f}s")
    print("-" * 50 + "\033[0m" + "\n")


def run_multi_file_cluster(log_dir):
    """
    MODE 2 — Directory of log files.
    Pairwise compares every file against every other, then clusters them using K-Means, DBSCAN, and GMM.
    """
    from log_comparator import LogComparator

    if not os.path.isdir(log_dir):
        print(f"[ERROR] Directory not found: {log_dir}")
        sys.exit(1)

    log_files = [f for f in os.listdir(log_dir) if f.endswith(".log")]

    if len(log_files) < 2:
        print(f"[ERROR] Need at least 2 .log files in {log_dir}. Found {len(log_files)}.")
        sys.exit(1)

    cmp = LogComparator(output_dir="outputs/pairwise_diffs")

    print("=" * 60)
    print(f"Mode: Multi-files  |  {len(log_files)} files  |  directory: {log_dir}")
    print("=" * 60)

    start = time.perf_counter()
    cmp.compare_pairwise(log_dir)
    elapsed_diff = time.perf_counter() - start

    print("\n" + "=" * 60)
    print("Clustering — auto-selecting algorithm and k")
    print("=" * 60)

    start = time.perf_counter()
    cmp.cluster()
    elapsed_cluster = time.perf_counter() - start

    cmp.print_clusters()
    cmp.save_clusters("outputs/clusters.json")
    cmp.plot_scatter("outputs/graphs/scatter.png")
    cmp.plot_dendrogram("outputs/graphs/dendrogram.png")

    print("\n" + "\033[92m" + " Clustering complete ".center(50, "-"))
    print(f"{'Algorithm':15}: {cmp.algorithm_used}")
    print(f"{'Diff time':15}: {elapsed_diff:.6f}s")
    print(f"{'Cluster time':15}: {elapsed_cluster:.6f}s")
    print(f"{'Clusters':15}: outputs/clusters.json")
    print(f"{'Scatter':15}: outputs/graphs/scatter.png")
    print(f"{'Dendrogram':15}: outputs/graphs/dendrogram.png")
    print("-" * 50 + "\033[0m" + "\n")


def main():
    args = sys.argv[1:]

    if len(args) == 0:
        print("Usage:")
        print("  Two files   → python main.py <file_a> <file_b>")
        print("  Directory   → python main.py <log_directory>")
        print()
        print("Examples:")
        print("  python main.py inputs/kern-1.log inputs/kern-2.log")
        print("  python main.py inputs/")
        sys.exit(0)

    elif len(args) == 1:
        path = args[0]
        if os.path.isdir(path):
            run_multi_file_cluster(path)
        else:
            print(f"[ERROR] '{path}' is not a directory.")
            print("  To compare two files: python main.py <file_a> <file_b>")
            sys.exit(1)

    elif len(args) == 2:
        run_two_file_diff(args[0], args[1])

    else:
        print(f"[ERROR] Too many arguments ({len(args)}).")
        print("  Two files   → python main.py <file_a> <file_b>")
        print("  Directory   → python main.py <log_directory>")
        sys.exit(1)


if __name__ == "__main__":
    main()
