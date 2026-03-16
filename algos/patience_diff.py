"""
from utils.normalization import normalize_line
import hashlib
from collections import defaultdict

def patience_diff(file_a, file_b, output_file):
    def hash_line(line):
        return hashlib.sha1(line.encode()).hexdigest()

    def load_file(path):
        lines = []

        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                original = line.rstrip()
                normalized = normalize_line(line)
                h = hash_line(normalized)

                lines.append((original, h))

        return lines

    def lcs_diff(a, b):
        n = len(a)
        m = len(b)

        dp = [[0]*(m+1) for _ in range(n+1)]

        for i in range(n):
            for j in range(m):
                if a[i][1] == b[j][1]:
                    dp[i+1][j+1] = dp[i][j] + 1
                else:
                    dp[i+1][j+1] = max(dp[i][j+1], dp[i+1][j])

        i = n
        j = m
        ops = []

        while i > 0 and j > 0:
            if a[i-1][1] == b[j-1][1]:
                ops.append(("UNCHANGED", a[i-1][0]))
                i -= 1
                j -= 1
            elif dp[i-1][j] >= dp[i][j-1]:
                ops.append(("DELETED", a[i-1][0]))
                i -= 1
            else:
                ops.append(("INSERTED", b[j-1][0]))
                j -= 1

        while i > 0:
            ops.append(("DELETED", a[i-1][0]))
            i -= 1
        while j > 0:
            ops.append(("INSERTED", b[j-1][0]))
            j -= 1

        ops.reverse()
        return ops

    def detect_moves(ops):
        delete_map = defaultdict(list)
        insert_map = defaultdict(list)

        for i, (op, line) in enumerate(ops):
            if op == "DELETED":
                delete_map[line].append(i)
            elif op == "INSERTED":
                insert_map[line].append(i)

        for line in delete_map:
            if line in insert_map:
                for d in delete_map[line]:
                    for ins in insert_map[line]:
                        ops[d] = ("MOVE", line)
                        ops[ins] = ("MOVE_TARGET", line)

        return ops
    
    a = load_file(file_a) 
    b = load_file(file_b) 

    ops = lcs_diff(a, b)
    ops = detect_moves(ops)

    with open(output_file, "w", encoding="utf-8") as out:
        for op, line in ops:
            if op == "INSERTED":
                out.write("[INSERTED] " + line + "\n")
            elif op == "DELETED":
                out.write("[DELETED]  " + line + "\n")
            elif op == "MOVE":
                out.write("[MOVED] " + line + "\n")
"""


from utils.normalization import normalize_line
import hashlib
from collections import defaultdict
from difflib import SequenceMatcher

def patience_diff(file_a, file_b, output_file):
    is_updated_required = True

    def hash_line(line):
        return hashlib.sha1(line.encode()).hexdigest()

    def load_file(path):
        lines = []

        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                original = line.rstrip()
                normalized = normalize_line(line)

                if normalized:
                    h = hash_line(normalized)
                    lines.append((original, normalized, h))

        return lines

    def lcs_diff(a, b):
        n = len(a)
        m = len(b)

        dp = [[0]*(m+1) for _ in range(n+1)]

        for i in range(n):
            for j in range(m):
                if a[i][2] == b[j][2]:
                    dp[i+1][j+1] = dp[i][j] + 1
                else:
                    dp[i+1][j+1] = max(dp[i][j+1], dp[i+1][j])

        i = n
        j = m
        ops = []

        while i > 0 and j > 0:
            if a[i-1][2] == b[j-1][2]:
                ops.append(("UNCHANGED", a[i-1], b[j-1]))
                i -= 1
                j -= 1
            elif dp[i-1][j] >= dp[i][j-1]:
                ops.append(("DELETED", a[i-1], None))
                i -= 1
            else:
                ops.append(("INSERTED", None, b[j-1]))
                j -= 1

        while i > 0:
            ops.append(("DELETED", a[i-1], None))
            i -= 1
        while j > 0:
            ops.append(("INSERTED", None, b[j-1]))
            j -= 1

        ops.reverse()
        return ops

    def classify_changes(ops):
        inserted = []
        deleted = []
        moved = []
        updated = []

        for op, a, b in ops:
            if op == "INSERTED":
                inserted.append(b)
            elif op == "DELETED":
                deleted.append(a)
        
        insert_map = defaultdict(list)
        for ins in inserted:
            insert_map[ins[2]].append(ins)

        remaining_deleted = []
        for d in deleted:
            if insert_map[d[2]]:
                moved.append(d[0])
                insert_map[d[2]].pop()
            else:
                remaining_deleted.append(d)

        remaining_inserted = []
        for h in insert_map:
            remaining_inserted.extend(insert_map[h])
    
        final_deleted = []

        if is_updated_required:
            for d in remaining_deleted:
                best_ratio = 0
                best_match = None

                for ins in remaining_inserted:
                    sim = SequenceMatcher(None, d[1], ins[1]).ratio()

                    if sim > 0.75:
                        best_ratio = sim
                        best_match = ins
                        break
            
                if best_match is not None:
                    updated.append((d[0], best_match[0], best_ratio))
                    remaining_inserted.remove(best_match)
                else:
                    final_deleted.append(d)
        else:
            final_deleted = remaining_deleted

        return moved, updated, final_deleted, remaining_inserted
    
    a = load_file(file_a) 
    b = load_file(file_b) 

    ops = lcs_diff(a, b)
    moved, updated, deleted, inserted = classify_changes(ops)

    with open(output_file, "w", encoding="utf-8") as out:
        out.write("-----------------------------------------\n")
        out.write("Diff Summary\n")
        out.write("-----------------------------------------\n")
        out.write(f"Lines compared : {max(len(a), len(b))}\n")
        out.write(f"Inserted       : {len(inserted)}\n")
        out.write(f"Deleted        : {len(deleted)}\n")
        if is_updated_required:
            out.write(f"Updated        : {len(updated)}\n")
        out.write(f"Moved          : {len(moved)}\n")
        out.write("-----------------------------------------\n\n")

        for line in moved:
            out.write(f"[MOVED] {line}\n")
        for old, new, sim in updated:
            out.write(f"[UPDATED] [Similarity: {sim:.2f}] {old} -> {new}\n")
        for d in deleted:
            out.write(f"[DELETED] {d}\n")
        for ins in inserted:
            out.write(f"[INSERTED] {ins}\n")
