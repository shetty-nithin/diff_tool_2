# Semantic Log Diff and NED-Based Clustering Tool

This project provides a semantic log comparison and multi-file clustering solution.

The system compares log files using the Patience Diff algorithm and performs clustering based on the overall normalized difference between log files.

The baseline implementation uses Normalized Edit Distance (NED) to calculate the distance between log files.

# Motivation

The objective of the baseline approach is to measure the overall difference between log files and group similar files automatically.

The system performs pairwise comparison between all input log files. The differences identified by the Patience Diff algorithm are used to calculate the NED distance between each pair of files.

The resulting pairwise distances are stored in a distance matrix, which is used as input for clustering.

# Architecture

```text
             TWO LOG FILES
                  │
                  ↓
             PATIENCE DIFF
                  │
          ┌───────┴────────┐
          ↓                ↓
    PAIRWISE DIFF     NED DISTANCE
          │                │
          ↓                ↓
      DIFF HTML     DISTANCE MATRIX
                           │
                           ↓
                       CLUSTERING
                 ┌─────────┼─────────┐
                 ↓         ↓         ↓
              DBSCAN      GMM   AGGLOMERATIVE
```

# Pairwise Comparison

For a set of `N` log files, every file is compared against every other file.

The total number of comparisons is:

```text
N × (N - 1) / 2
```

# Patience Diff

The project uses the Patience Diff algorithm to identify meaningful structural differences between two log files.

The pairwise comparison detects differences such as:

- Inserted lines
- Deleted lines
- Moved lines
- Updated lines

The output is used for both pairwise diff reporting and distance calculation.

# NED Distance

The Normalized Edit Distance (NED) represents the overall difference between two log files.

The distance is normalized so that log files of different sizes can be compared.

Conceptually:

```text
Distance = 0
→ Files are identical or highly similar

Distance approaching 1
→ Files are increasingly different
```

The NED distance is calculated for every pair of input files.

# Distance Matrix

The pairwise NED distances are combined into a distance matrix.

Example:

```text
        File A   File B   File C

File A    0.00     0.05     0.42
File B    0.05     0.00     0.39
File C    0.42     0.39     0.00
```

The distance matrix is used as input for clustering.

# Clustering

The project evaluates multiple clustering algorithms.

## DBSCAN

DBSCAN does not require the number of clusters to be predefined.

Features include:

- Automatic `eps` selection
- No predefined cluster count
- Potential identification of outlier files as noise

## Gaussian Mixture Model

GMM evaluates different possible numbers of clusters.

Different values of `k` are evaluated, and the best configuration is selected using the Bayesian Information Criterion (BIC).

## Agglomerative Clustering

Agglomerative clustering groups log files hierarchically based on their distance.

Different possible cluster counts can be evaluated.

# Clustering Evaluation

The clustering results are evaluated using:

- Silhouette Score
- Davies-Bouldin Score
- Calinski-Harabasz Score

These metrics are used to evaluate and compare clustering quality.

# Outputs

```text
outputs/
├── pairwise_diffs/
│   ├── file_a_vs_file_b.html
│   ├── file_a_vs_file_c.html
│   └── ...
│
├── clusters.json
│
└── graphs/
    └── scatter.png
```

# Installation

## Clone the Repository

```bash
git clone https://github.com/shetty-nithin/diff_tool_2.git
cd diff_tool_2
```

## Switch to the Main Branch

```bash
git checkout main
```

## Create a Virtual Environment

```bash
python -m venv venv
```

### macOS / Linux

```bash
source venv/bin/activate
```

### Windows

```bash
venv\Scripts\activate
```

## Install Dependencies

```bash
pip install -r requirements.txt
```

# Running

Run the tool using:

```bash
python main.py <folder_path>
```

Generated results are stored under:

```text
outputs/
```
