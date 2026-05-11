from dataclasses import dataclass, asdict
import json

@dataclass
class DiffVector:
    similarity_ratio:   float = 0.0  # 1.0 = identical
    structural_change:  float = 0.0  # 1.0 = completely different
    deletion_ratio:     float = 0.0  # deleted / total_a
    insertion_ratio:    float = 0.0  # inserted / total_b
    churn_ratio:        float = 0.0  # (deleted + inserted) / total
    move_ratio:         float = 0.0  # moved lines / total
    overall_distance:   float = 0.0  # single scalar, 0.0=same, 1.0=different

    def to_cluster_array(self):
        return [
            self.similarity_ratio,
            self.structural_change,
            self.deletion_ratio,
            self.insertion_ratio,
            self.churn_ratio,
            self.move_ratio,
        ]

    def to_json(self):
        return json.dumps(asdict(self), indent=2)


def compute_diff_vector(ops_html, orig_a, orig_b):

    unchanged = deleted = inserted = moved = 0

    for tag, left, right in ops_html:
        if tag == "UNCHANGED":    unchanged += 1
        elif tag == "DELETED":    deleted   += 1
        elif tag == "INSERTED":   inserted  += 1
        elif tag == "MOVED_LINE": moved     += 1

    total_a = len(orig_a)
    total_b = len(orig_b)
    total   = total_a + total_b

    v = DiffVector()
    v.similarity_ratio  = (unchanged * 2) / total         if total   > 0 else 1.0
    v.structural_change = 1.0 - v.similarity_ratio
    v.deletion_ratio    = deleted  / total_a              if total_a > 0 else 0.0
    v.insertion_ratio   = inserted / total_b              if total_b > 0 else 0.0
    v.churn_ratio       = (deleted + inserted) / total    if total   > 0 else 0.0
    v.move_ratio        = (moved * 2) / total             if total   > 0 else 0.0
    v.overall_distance  = round(
        0.40 * v.structural_change +
        0.30 * v.churn_ratio       +
        0.30 * v.move_ratio,
        4
    )

    return v
