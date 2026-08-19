# Semantic Log Diff and Domain-Aware Clustering Tool

This project provides a semantic log comparison and multi-file clustering solution with domain-aware distance calculation.

The system compares log files using the Patience Diff algorithm and performs clustering based not only on the overall difference between logs, but also on domain-relevant characteristics such as:

- Warning changes
- Failure changes
- Contamination changes

# Motivation

The baseline approach uses a Normalized Edit Distance (NED) to measure the overall difference between two log files.

However, NED treats all differences as generic changes and does not explicitly consider whether those differences represent warnings, failures, or contamination.

The domain-aware approach introduces separate sensitivity measures for warning, failure, and contamination changes. These measures are combined with the base distance to calculate a composite distance, which is then used for clustering.

# Architecture

```text
                     TWO LOG FILES
                          │
                          ↓
                     PATIENCE DIFF
                          │
             ┌────────────┴────────────┐
             │                         │
             ↓                         ↓
        PAIRWISE DIFF         DOMAIN-AWARE DISTANCE
             │                         │
             ↓              ┌──────────┼──────────┐
         DIFF HTML           ↓          ↓          ↓
                         WARNING     FAILURE   CONTAMINATION
                       SENSITIVITY  SENSITIVITY  SENSITIVITY
                             │          │          │
                             └──────────┼──────────┘
                                        ↓
                                COMPOSITE DISTANCE
                                        │
                                        ↓
                                DISTANCE MATRIX
                                        │
                                        ↓
                              ┌─────────┼─────────┐
                              ↓         ↓         ↓
                           DBSCAN      GMM   AGGLOMERATIVE
```

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

## Switch to the Domain-Aware Distance Branch

```bash
git checkout domain-aware-distance
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
