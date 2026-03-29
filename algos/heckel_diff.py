"""
Paper: A Technique for Isolating Differences Between Files
"""

from utils.normalization import normalize_line
from difflib import SequenceMatcher

def heckel_diff(file_a, file_b, output_file):
    def load_file(path: str):
        orig = []
        norm = []

        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                orig_line = line.rstrip("\n")
                normalized = normalize_line(orig_line)

                if normalized:
                    orig.append(orig_line)
                    norm.append(normalized)

        return orig, norm

    class Symbol:
        def __init__(self):
            self.count_a = 0
            self.count_b = 0
            self.last_a = None
            self.last_b = None

    orig_a, norm_a = load_file(file_a)
    orig_b, norm_b = load_file(file_b)

    table = {}

    # PASS 1 — build symbol table
    for i, line in enumerate(norm_a):
        if line not in table:
            table[line] = Symbol()
        table[line].count_a += 1
        table[line].last_a = i

    for j, line in enumerate(norm_b):
        if line not in table:
            table[line] = Symbol()
        table[line].count_b += 1
        table[line].last_b = j

    # PASS 2 — find unique anchors
    match_a = [-1] * len(norm_a)
    match_b = [-1] * len(norm_b)

    for line, sym in table.items():
        if sym.count_a == 1 and sym.count_b == 1:
            a = sym.last_a
            b = sym.last_b
            match_a[a] = b
            match_b[b] = a

    # PASS 3 — expand matches forward
    for i in range(len(norm_a) - 1):
        if match_a[i] != -1:
            j = match_a[i]
            if i + 1 < len(norm_a) and j + 1 < len(norm_b):
                if norm_a[i + 1] == norm_b[j + 1]:
                    match_a[i + 1] = j + 1
                    match_b[j + 1] = i + 1

    # PASS 4 — expand matches backward
    for i in range(len(norm_a) - 1, 0, -1):
        if match_a[i] != -1:
            j = match_a[i]
            if i - 1 >= 0 and j - 1 >= 0:
                if norm_a[i - 1] == norm_b[j - 1]:
                    match_a[i - 1] = j - 1
                    match_b[j - 1] = i - 1

    # PASS 5 — classify changes
    added = []
    removed = []
    moved = []
    updated = []
    is_updated_required = True

    for i, j in enumerate(match_a):
        if j == -1:
            removed.append(i)
        elif i != j:
            moved.append((i, j))

    for j, i in enumerate(match_b):
        if i == -1:
            added.append(j)

    if is_updated_required: # True => Updated
        new_removed = []
        new_added = added.copy()

        for i in removed:
            best_ratio = 0
            best_match_idx = -1

            for j in new_added:
                sim = SequenceMatcher(None, norm_a[i], norm_b[j]).ratio()
                if sim > 0.75:
                    best_ratio = sim
                    best_match_idx = j
                    break

            if best_match_idx != -1:
                updated.append((i, best_match_idx, best_ratio))
                new_added.remove(best_match_idx)
            else:
                new_removed.append(i)

        removed = new_removed
        added = new_added


    with open(output_file, "w", encoding="utf-8") as out:
        out.write("-----------------------------------------\n")
        out.write("Diff Summary\n")
        out.write("-----------------------------------------\n")
        out.write(f"Lines compared : {max(len(orig_a), len(orig_b))}\n")
        out.write(f"Inserted       : {len(added)}\n")
        out.write(f"Deleted        : {len(removed)}\n")
        if is_updated_required:
            out.write(f"Updated        : {len(updated)}\n")
        out.write(f"Moved          : {len(moved)}\n")
        out.write("-----------------------------------------\n\n")

        if not removed and not added and not moved:
            out.write("Files are semantically identical.")
        else:
            for i in removed:
                out.write(f"[DELETED]  {orig_a[i]}\n")
            for j in added:
                out.write(f"[INSERTED] {orig_b[j]}\n")
            for i, j in moved:
                out.write(f"[MOVED] {orig_a[i]}\n")
            if is_updated_required:
                for i, j, best_ratio in updated:
                    out.write(f"[UPDATED] [Similarity: {best_ratio:.2f}]: {orig_a[i]} -> {orig_b[j]}\n")
