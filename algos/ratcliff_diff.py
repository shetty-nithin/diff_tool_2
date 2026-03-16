"""Python in-build SequencMatcher"""

from collections import Counter, defaultdict
from difflib import SequenceMatcher
from utils.normalization import normalize_line

def ratcliff_diff(file_a, file_b, output_file):
    def load_file(path: str):
        original = []
        normalized = []

        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.rstrip("\n")
                norm = normalize_line(line)

                if norm:
                    original.append(line)
                    normalized.append(norm)

        return original, normalized

    orig_a, norm_a = load_file(file_a)
    orig_b, norm_b = load_file(file_b)

    matcher = SequenceMatcher(None, norm_a, norm_b)

    if matcher.ratio() == 1.0:
        with open(output_file, "w", encoding="utf-8") as out:
            out.write("Files are semantically identical.")
        return

    added = []
    removed = []
    updated = []
    unchanged = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for i, j in zip(range(i1, i2), range(j1, j2)):
                unchanged.append((i, j))

        elif tag == "delete":
            for i in range(i1, i2):
                removed.append(i)

        elif tag == "insert":
            for j in range(j1, j2):
                added.append(j)

        elif tag == "replace":
            len_a = i2 - i1
            len_b = j2 - j1
            min_len = min(len_a, len_b)

            for k in range(min_len):
                updated.append((i1 + k, j1 + k))

            for i in range(i1 + min_len, i2):
                removed.append(i)

            for j in range(j1 + min_len, j2):
                added.append(j)

    # ---------------- MOVE DETECTION ---------------- #
    removed_norm = defaultdict(list)
    for i in removed:
        removed_norm[norm_a[i]].append(i)

    moved = []
    still_added = []
    still_removed = []

    for j in added:
        norm = norm_b[j]

        if norm in removed_norm and removed_norm[norm]:
            i = removed_norm[norm].pop(0)
            moved.append((i, j)) # Final moved list
        else:
            still_added.append(j) # Final added list

    for norm in removed_norm:
        for i in removed_norm[norm]:
            still_removed.append(i) # Final removed list

    with open(output_file, "w", encoding="utf-8") as out:
        out.write("-----------------------------------------\n")
        out.write("Diff Summary\n")
        out.write("-----------------------------------------\n")
        out.write(f"Lines compared : {max(len(norm_a), len(norm_b))}\n")
        out.write(f"Inserted       : {len(still_added)}\n")
        out.write(f"Deleted        : {len(still_removed)}\n")
        out.write(f"Updated        : {len(updated)}\n")
        out.write(f"Moved          : {len(moved)}\n")
        out.write("-----------------------------------------\n\n")

        for i in still_removed:
            out.write(f"[DELETED]  {orig_a[i]}\n")
        for j in still_added:
            out.write(f"[INSERTED] {orig_b[j]}\n")
        for i, j in updated:
            line_sim = SequenceMatcher(None, norm_a[i], norm_b[j]).ratio()
            out.write(f"[UPDATED][Similarity: {line_sim:.3f}] {orig_a[i]}  ->  {orig_b[j]}\n")
        for i, j in moved:
            out.write(f"[MOVED] {orig_a[i]}\n")
