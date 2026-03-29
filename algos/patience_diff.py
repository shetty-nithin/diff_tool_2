from utils.normalization import normalize_line
from utils.html_renderer import render_diff_to_html
from difflib import SequenceMatcher
from collections import defaultdict
import bisect

def patience_diff(file_a, file_b, output_file):
    is_updated_required = True
    is_html_output = True

    def load_file(path):
        orig = []
        norm = []

        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.rstrip("\n")
                n = normalize_line(line)

                if n:
                    orig.append(line)
                    norm.append(n)

        return orig, norm

    orig_a, norm_a = load_file(file_a)
    orig_b, norm_b = load_file(file_b)

    class Slice:
        def __init__(self, a_low, a_high, b_low, b_high):
            self.a_low = a_low
            self.a_high = a_high
            self.b_low = b_low
            self.b_high = b_high

        def not_empty(self):
            return self.a_low < self.a_high and self.b_low < self.b_high

    def unique_matches(s):
        counts = {}

        for i in range(s.a_low, s.a_high):
            key = norm_a[i]
            if key not in counts:
                counts[key] = [0, 0, None, None] # a_count, b_count, first_occurence_in_a, first_occurence_in_b
            counts[key][0] += 1
            if counts[key][2] is None:
                counts[key][2] = i

        for j in range(s.b_low, s.b_high):
            key = norm_b[j]
            if key not in counts:
                counts[key] = [0, 0, None, None]
            counts[key][1] += 1
            if counts[key][3] is None:
                counts[key][3] = j

        matches = []
        for key, (c_a, c_b, a_i, b_j) in counts.items():
            if c_a == 1 and c_b == 1:
                matches.append((a_i, b_j))

        return sorted(matches)

    def longest_increasing_sequence(matches): # Patience Sorting
        stacks = []
        parent = [None]*len(matches)
        stack_tops = []

        for i, (_, b_j) in enumerate(matches):
            pos = bisect.bisect_left(stacks, b_j)

            if pos == len(stacks):
                stacks.append(b_j)
                stack_tops.append(i)
            else:
                stacks[pos] = b_j
                stack_tops[pos] = i

            if pos > 0:
                parent[i] = stack_tops[pos - 1]
            
        result = []
        k = stack_tops[-1] if stack_tops else None

        while k is not None:
            result.append(matches[k])
            k = parent[k]

        return list(reversed(result))

    def match_head(s, head):
        while s.not_empty() and norm_a[s.a_low] == norm_b[s.b_low]:
            head.append(("UNCHANGED", s.a_low, s.b_low))
            s.a_low += 1 
            s.b_low += 1 

    def match_tail(s, tail):
        temp = []
        while s.not_empty() and norm_a[s.a_high - 1] == norm_b[s.b_high - 1]:
            s.a_high -= 1
            s.b_high -= 1
            temp.append(("UNCHANGED", s.a_high, s.b_high))
        tail.extend(reversed(temp))

    def fallback(s):
        sm = SequenceMatcher(None, norm_a[s.a_low:s.a_high], norm_b[s.b_low:s.b_high])
        ops = []

        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                for i, j in zip(range(i1, i2), range(j1, j2)):
                    ops.append(("UNCHANGED", s.a_low + i, s.b_low + j))
            elif tag == "delete":
                for i in range(i1, i2):
                    ops.append(("DELETE", s.a_low + i))
            elif tag == "insert":
                for j in range(j1, j2):
                    ops.append(("INSERT", s.b_low + j))
            elif tag == "replace":
                for i in range(i1, i2):
                    ops.append(("DELETE", s.a_low + i))
                for j in range(j1, j2):
                    ops.append(("INSERT", s.b_low + j))
        return ops

    def diff(s):
        head = []
        tail = []

        match_head(s, head)
        match_tail(s, tail)
        if not s.not_empty(): # if all the lines are matching
            return head + tail

        result = []
        matches = unique_matches(s)
        if not matches: # if no matches found, send for diff generation using python's inbuilt SequenceMatcher
            result.extend(fallback(s))
            return head + result + tail

        anchors = longest_increasing_sequence(matches)
        
        a_curr = s.a_low # first line of the slice/document
        b_curr = s.b_low

        for a_i, b_j in anchors:
            sub = Slice(a_curr, a_i, b_curr, b_j)
            result.extend(diff(sub))

            result.append(("UNCHANGED", a_i, b_j)) # anchor line

            a_curr = a_i + 1
            b_curr = b_j + 1

        sub = Slice(a_curr, s.a_high, b_curr, s.b_high) # from last anchor to last line of the slice/document
        result.extend(diff(sub))

        return head + result + tail

    ops = diff(Slice(0, len(norm_a), 0, len(norm_b)))

    # Classification -----------------------------------------------------------
    inserted = []
    deleted = []
    moved = []
    updated = []

    for op in ops:
        if op[0] == "INSERT":
            inserted.append(op[1])
        elif op[0] == "DELETE":
            deleted.append(op[1])

    insert_map = defaultdict(list)
    for j in inserted:
        insert_map[norm_b[j]].append(j)

    remaining_deleted = []
    for i in deleted:
        if insert_map[norm_a[i]]:
            j = insert_map[norm_a[i]].pop(0)
            moved.append((i, j))
        else:
            remaining_deleted.append(i)

    remaining_inserted = []
    for v in insert_map.values():
        remaining_inserted.extend(v)

    final_deleted = []

    if is_updated_required:
        for i in remaining_deleted:
            best_ratio = 0
            best_j = None

            for j in remaining_inserted:
                sim = SequenceMatcher(None, norm_a[i], norm_b[j]).ratio()
                if sim > best_ratio:
                    best_ratio = sim
                    best_j = j

            if best_j is not None and best_ratio > 0.75:
                updated.append((i, best_j, best_ratio))
                remaining_inserted.remove(best_j)
            else:
                final_deleted.append(i)
    else:
        final_deleted = remaining_deleted

    # ------------------------------------------------------------------------------

    ops_html = []
    used_a, used_b = set(), set()
    update_map = {i: (j, sim) for i, j, sim in updated}
    move_map = {i: j for i, j in moved}

    for op in ops:
        if op[0] == "UNCHANGED":
            _, i, j = op
            ops_html.append(("UNCHANGED", (orig_a[i],), (orig_b[j],)))
            used_a.add(i)
            used_b.add(j)

        elif op[0] == "DELETE":
            i = op[1]

            if i in update_map:
                j, sim = update_map[i]
                ops_html.append(("UPDATED", (orig_a[i],), (orig_b[j],)))
                used_a.add(i)
                used_b.add(j)
                continue
            if i in move_map:
                j = move_map[i]
                ops_html.append(("MOVED", (orig_a[i],), (orig_b[j],)))
                used_a.add(i)
                used_b.add(j)
                continue

            ops_html.append(("DELETED", (orig_a[i],), None))
            used_a.add(i)

        elif op[0] == "INSERT":
            j = op[1]

            if j in used_b:
                continue

            ops_html.append(("INSERTED", None, (orig_b[j],)))
            used_b.add(j)

    stats = {
        "ins": len(remaining_inserted),
        "del": len(final_deleted)
    }

    def render_diff_to_text(ops_html, output_file):
        with open(output_file + ".txt", "w", encoding="utf-8") as f:
            for tag, a, b in ops_html:
                if tag == "UNCHANGED":
                    #f.write(f"[UNCHANGED]: {a[0]}\n")
                    continue

                elif tag == "DELETED":
                    f.write(f"[DELETED]: {a[0]}\n")

                elif tag == "INSERTED":
                    f.write(f"[INSERTED]: {b[0]}\n")

                elif tag == "MOVED":
                    f.write(f"[MOVED]: {a[0]} -> {b[0]}\n")

                elif tag == "UPDATED":
                    f.write(f"[UPDATED]: {a[0]} -> {b[0]}\n")

    if is_html_output: 
        render_diff_to_html(
            ops_html,
            file_a,
            file_b,
            output_file + ".html",
            stats
        )
    else:
        render_diff_to_text(ops_html, output_file)
