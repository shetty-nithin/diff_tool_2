# Semantic Log Diff and Clustering Tool

This project provides a semantic log comparison and multi-file clustering solution.

The system compares log files using a Patience diff algorithm, calculates the normalized difference between every pair of files, and automatically groups similar log files using multiple clustering algorithms.

## Overview

The main branch implements the baseline approach based on:

- Log normalization
- Patience Diff
- Pairwise comparison
- Moved line detection
- Normalized Edit Distance (NED)
- Automatic clustering

The clustering is based purely on the calculated distance between log files.

---

# Architecture

```text
             TWO LOG FILES
                  │
                  ↓
             PATIENCE DIFF
                  │
          ┌───────┴────────┐
          ↓                ↓
    PAIRWISE DIFF      NED DISTANCE
          │                │
          ↓                ↓
      DIFF HTML       DISTANCE MATRIX
                           │
                           ↓
                       CLUSTERING
                 ┌─────────┼─────────┐
                 ↓         ↓         ↓
              DBSCAN      GMM   AGGLOMERATIVE
