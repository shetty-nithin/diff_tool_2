"""
from utils.normalization import normalize_line
from utils.html_renderer import render_diff_to_html
from difflib import SequenceMatcher
from collections import defaultdict
import bisect

def patience_diff(file_a, file_b, output_file):
    is_updated_required = False
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
            return (
                self.a_low < self.a_high and
                self.b_low < self.b_high
            )

    def unique_matches(s):
        counts = {}

        for i in range(s.a_low, s.a_high):
            key = norm_a[i]

            if key not in counts:
                counts[key] = [0, 0, None, None]  # a_count, b_count, first_occurence_in_a, first_occurence_in_b

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

    def longest_increasing_sequence(matches): # Patience Sorting: To find the longest set that appears in the same relative order
        stacks = []
        parent = [None] * len(matches)
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

    def fallback(s):
        sm = SequenceMatcher(
            None,
            norm_a[s.a_low:s.a_high],
            norm_b[s.b_low:s.b_high]
        )

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
        result = []

        matches = unique_matches(s)

        if not matches:
            return fallback(s)

        anchors = longest_increasing_sequence(matches)

        a_curr = s.a_low
        b_curr = s.b_low

        for a_i, b_j in anchors:
            sub = Slice(a_curr, a_i, b_curr, b_j)

            result.extend(diff(sub))

            result.append(("UNCHANGED", a_i, b_j))

            a_curr = a_i + 1
            b_curr = b_j + 1

        sub = Slice(a_curr, s.a_high, b_curr, s.b_high)

        result.extend(diff(sub))

        return result

    ops = diff(Slice(0, len(norm_a), 0, len(norm_b)))

# ------------------------------------------------------------------
# CLASSIFICATION
# ------------------------------------------------------------------
    inserted = []
    deleted = []
    updated = []
    for op in ops:
        if op[0] == "INSERT":
            inserted.append(op[1])
        elif op[0] == "DELETE":
            deleted.append(op[1])

    insert_map = defaultdict(list)
    for j in inserted:
        insert_map[norm_b[j]].append(j) #{line: [positions]}

    candidate_moves = []
    remaining_deleted = []
    for i in deleted:
        key = norm_a[i]

        if insert_map[key]:
            j = insert_map[key].pop(0)
            candidate_moves.append((i, j))
        else:
            remaining_deleted.append(i)

    remaining_inserted = []
    for v in insert_map.values():
        remaining_inserted.extend(v)

    candidate_moves.sort(key=lambda x: x[0])

    # LIS on move: Its purpose is to distinguish between lines that stayed in their relative order (even if other things changed around them) and lines that actually jumped to a new position.
    moved = []
    if candidate_moves:
        b_positions = [j for _, j in candidate_moves]
        lis_indices = set()
        lis_stacks = []
        lis_tops = []
        lis_parent = [None] * len(candidate_moves)
        for idx, bj in enumerate(b_positions):
            pos = bisect.bisect_left(lis_stacks, bj)
            if pos == len(lis_stacks):
                lis_stacks.append(bj)
                lis_tops.append(idx)
            else:
                lis_stacks[pos] = bj
                lis_tops[pos] = idx

            if pos > 0:
                lis_parent[idx] = lis_tops[pos - 1]

        k = lis_tops[-1] if lis_tops else None
        while k is not None:
            lis_indices.add(k)
            k = lis_parent[k]

        for idx, (i_a, j_b) in enumerate(candidate_moves):
            if idx in lis_indices:
                remaining_deleted.append(i_a)
                remaining_inserted.append(j_b)
            else:
                moved.append((i_a, j_b))

    # MOVE RANGE DETECTION
    moved_ranges = []
    for a_pos, b_pos in moved:
        if a_pos < b_pos:
            moved_ranges.append((a_pos, b_pos))
        elif a_pos > b_pos:
            moved_ranges.append((b_pos, a_pos))

    moved_ranges.sort()

    # MERGE OVERLAPPING RANGES
    merged_ranges = []
    for start, end in moved_ranges:
        if not merged_ranges:
            merged_ranges.append([start, end])
        else:
            prev_start, prev_end = merged_ranges[-1]

            if start <= prev_end + 1:
                merged_ranges[-1][1] = max(prev_end, end)
            else:
                merged_ranges.append([start, end])

    # UPDATED DETECTION
    final_deleted = []
    if is_updated_required:
        for i in remaining_deleted:
            best_ratio = 0
            best_j = None
            for j in remaining_inserted:
                sim = SequenceMatcher(None, norm_a[i],  norm_b[j]).ratio()

                if sim > best_ratio:
                    best_ratio = sim
                    best_j = j
            if (best_j is not None and best_ratio > 0.75):
                updated.append((i, best_j, best_ratio))
                remaining_inserted.remove(best_j)
            else:
                final_deleted.append(i)
    else:
        final_deleted = remaining_deleted

    # MAPS
    update_map = {i: (j, sim) for i, j, sim in updated}
    moved_a = {i for i, _ in moved}
    moved_b = {j for _, j in moved}

    move_map = {i: j for i, j in moved}

    # BUILD OUTPUT
    ops_html = []
    used_a = set()
    used_b = set()
    current_a_index = -1

    for op in ops:
        tag = op[0]

        # UNCHANGED
        if tag == "UNCHANGED":
            _, i, j = op
            current_a_index += 1
            is_moved = False

            for start, end in merged_ranges:
                if start <= current_a_index <= end:
                    is_moved = True
                    break

            if is_moved:
                ops_html.append(("MOVED", (orig_a[i],), (orig_b[j],)))
            else:
                ops_html.append(("UNCHANGED", (orig_a[i],), (orig_b[j],)))

            used_a.add(i)
            used_b.add(j)

        # DELETE
        elif tag == "DELETE":
            i = op[1]
            current_a_index += 1

            if i in update_map:
                j, sim = update_map[i]
                ops_html.append(("UPDATED", (orig_a[i],), (orig_b[j],)))
                used_a.add(i)
                used_b.add(j)
                continue
            if i in moved_a:
                j = move_map[i]
                ops_html.append(("MOVED", (orig_a[i],), (orig_b[j],)))
                used_a.add(i)
                used_b.add(j)
                continue

            is_moved = False
            for start, end in merged_ranges:
                if start <= current_a_index <= end:
                    is_moved = True
                    break

            if is_moved:
                ops_html.append(("MOVED", (orig_a[i],), None))
            else:
                ops_html.append(("DELETED", (orig_a[i],), None))

            used_a.add(i)

        # INSERT
        elif tag == "INSERT":
            j = op[1]
            if j in used_b:
                continue
            if j in moved_b:
                matching_i = None
                for i_a, j_b in moved:
                    if j_b == j:
                        matching_i = i_a
                        break

                if matching_i is not None:
                    ops_html.append(("MOVED", (orig_a[matching_i],), (orig_b[j],)))
                else:
                    ops_html.append(("MOVED", None, (orig_b[j],)))

                used_b.add(j)
                continue

            ops_html.append(("INSERTED", None, (orig_b[j],)))
            used_b.add(j)

    # STATS
    stats = {
        "ins": len(remaining_inserted),
        "del": len(final_deleted)
    }

    # TEXT OUTPUT
    def render_diff_to_text(ops_html, output_file):
        with open(output_file + ".txt", "w", encoding="utf-8") as f:
            for tag, a, b in ops_html:
                if tag == "UNCHANGED":
                    continue
                elif tag == "DELETED":
                    f.write(f"[DELETED]: {a[0]}\n")
                elif tag == "INSERTED":
                    f.write(f"[INSERTED]: {b[0]}\n")
                elif tag == "MOVED":
                    left = a[0] if a else ""
                    right = b[0] if b else ""
                    f.write(f"[MOVED]: {left} -> {right}\n")
                elif tag == "UPDATED":
                    f.write(f"[UPDATED]: {a[0]} -> {b[0]}\n")

    # OUTPUT
    if is_html_output:
        render_diff_to_html(
            ops_html,
            file_a,
            file_b,
            output_file + ".html",
            stats
        )
    else:
        render_diff_to_text(
            ops_html,
            output_file
        )

from utils.normalization import normalize_line
from utils.html_renderer import render_diff_to_html
from difflib import SequenceMatcher
from collections import defaultdict
import bisect


def patience_diff(file_a, file_b, output_file):
    is_html_output = True

    # ------------------------------------------------------------------
    # LOAD
    # ------------------------------------------------------------------
    def load_file(path):
        orig, norm = [], []
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
    n_a, n_b = len(norm_a), len(norm_b)

    # ------------------------------------------------------------------
    # STEP 1 — ALIGN "lines" (one-to-one match per logical line)
    # Strategy: for each normalized line, pair occurrences in A with
    # occurrences in B in order. 
    # Surplus on A = retries-only-in-A => DELETED.
    # Surplus on B = retries-only-in-B => INSERTED.
    # The paired ones become candidate UNCHANGED/MOVED anchors.
    # ------------------------------------------------------------------
    occ_a = defaultdict(list)
    occ_b = defaultdict(list)
    for i, k in enumerate(norm_a):
        occ_a[k].append(i)
    for j, k in enumerate(norm_b):
        occ_b[k].append(j)

    pairs = []                    # (i_in_a, j_in_b) one-to-one
    extra_a = []                  # indices in A with no partner -> DELETED (retry in A)
    extra_b = []                  # indices in B with no partner -> INSERTED (retry in B)

    keys = set(occ_a) | set(occ_b)
    for k in keys: # k = line
        la, lb = occ_a.get(k, []), occ_b.get(k, []) # la and lb contains positions of line k (could be multiple positins)
        m = min(len(la), len(lb))
        for x in range(m):
            pairs.append((la[x], lb[x]))
        extra_a.extend(la[m:])
        extra_b.extend(lb[m:])

    pairs.sort()                  # sort by position in A

    # ------------------------------------------------------------------
    # STEP 2 — LIS on B-positions of paired works (Patience algorithm)
    # Pairs on the LIS are "in order" -> UNCHANGED.
    # Pairs off the LIS are "moved".
    # ------------------------------------------------------------------
    def lis(seq):
        if not seq:
            return set()
        tails, tops, parent = [], [], [None] * len(seq)
        for idx, val in enumerate(seq):
            pos = bisect.bisect_left(tails, val)
            if pos == len(tails):
                tails.append(val)
                tops.append(idx)
            else:
                tails[pos] = val
                tops[pos] = idx
            if pos > 0:
                parent[idx] = tops[pos - 1]
        keep, k = set(), tops[-1]
        while k is not None:
            keep.add(k)
            k = parent[k]
        return keep
    
    #b_seq = [j for _, j in pairs]
    #in_order = lis(b_seq)

    #unchanged_pairs = []
    #moved_pairs = []
    #for idx, (i, j) in enumerate(pairs):
    #    if idx in in_order:
    #        unchanged_pairs.append((i, j))
    #    else:
    #        moved_pairs.append((i, j))

    unchanged_pairs = []
    moved_pairs = []
    pair_count = len(pairs)
    for idx, (i, j) in enumerate(pairs):
        moved = False

        # --------------------------------------------------------------
        # Check PREVIOUS matched neighbor
        # --------------------------------------------------------------
        if idx > 0:
            prev_i, prev_j = pairs[idx - 1]

            # expected offset in ordered sequence
            expected_a = i - prev_i
            expected_b = j - prev_j

            if expected_a != expected_b:
                moved = True

        # --------------------------------------------------------------
        # Check NEXT matched neighbor
        # --------------------------------------------------------------
        if idx < pair_count - 1:
            next_i, next_j = pairs[idx + 1]

            expected_a = next_i - i
            expected_b = next_j - j

            if expected_a != expected_b:
                moved = True

        # --------------------------------------------------------------
        # Final classification
        # --------------------------------------------------------------
        if moved:
            moved_pairs.append((i, j))
        else:
            unchanged_pairs.append((i, j))

    # ------------------------------------------------------------------
    # STEP 3 — COMPUTE "AFFECTED" RANGES ON BOTH SIDES
    # When a work moves from position p_a in A to p_b in B, every line
    # between its old A-neighbors and its new B-neighbors is "shifted".
    # We highlight the span [min..max] on each side as MOVED context.
    # ------------------------------------------------------------------
    moved_a_span = []
    moved_b_span = []
    # anchor map: for each moved pair, find its nearest unchanged neighbors
    unchanged_a_sorted = sorted(i for i, _ in unchanged_pairs)
    unchanged_b_sorted = sorted(j for _, j in unchanged_pairs)
    a_to_b = dict(unchanged_pairs)
    b_to_a = {j: i for i, j in unchanged_pairs}

    for i, j in moved_pairs:
        # neighbors in A among unchanged anchors
        p = bisect.bisect_left(unchanged_a_sorted, i)
        a_left = unchanged_a_sorted[p - 1] if p > 0 else 0
        a_right = unchanged_a_sorted[p] if p < len(unchanged_a_sorted) else n_a - 1
        # corresponding B span (where this line "should" have been)
        b_left = a_to_b.get(a_left, 0)
        b_right = a_to_b.get(a_right, n_b - 1)

        # the moved line is at i in A and j in B; expand the
        # affected range to cover both old and new positions
        moved_a_span.append((min(i, a_left), max(i, a_right)))
        moved_b_span.append((min(j, b_left), max(j, b_right)))

    def merge(spans):
        spans = sorted(spans)
        out = []
        for s, e in spans:
            if out and s <= out[-1][1] + 1:
                out[-1][1] = max(out[-1][1], e)
            else:
                out.append([s, e])
        return out

    moved_a_span = merge(moved_a_span)
    moved_b_span = merge(moved_b_span)

    def in_span(idx, spans):
        # binary search
        lo, hi = 0, len(spans) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            s, e = spans[mid]
            if idx < s:
                hi = mid - 1
            elif idx > e:
                lo = mid + 1
            else:
                return True
        return False

    # ------------------------------------------------------------------
    # STEP 4 — CLASSIFY EVERY LINE IN A AND B
    # ------------------------------------------------------------------
    moved_a_set = {i for i, _ in moved_pairs}
    moved_b_set = {j for _, j in moved_pairs}
    unchanged_a_set = {i for i, _ in unchanged_pairs}
    unchanged_b_set = {j for _, j in unchanged_pairs}
    extra_a_set = set(extra_a)
    extra_b_set = set(extra_b)

    # We emit a single linear stream of ops by walking A then merging B inserts
    # at their correct relative positions using the unchanged anchors.
    ops_html = []

    # Build a merged walk: for each unchanged anchor (i,j) in order,
    # emit everything in A (i_prev..i) and B (j_prev..j) before it.
    unchanged_pairs.sort()
    walk_anchors = unchanged_pairs + [(n_a, n_b)]   # sentinel

    i_prev, j_prev = 0, 0
    for i_anchor, j_anchor in walk_anchors:
        # emit A-only items in (i_prev .. i_anchor)
        for i in range(i_prev, i_anchor):
            if i in extra_a_set:
                # retry that B never logged
                ops_html.append(("DELETED", (orig_a[i],), None))
            elif i in moved_a_set:
                ops_html.append(("MOVED", (orig_a[i],), None))
            elif in_span(i, moved_a_span):
                ops_html.append(("MOVED", (orig_a[i],), None))
            # unchanged lines are emitted at the anchor step, skip here
        # emit B-only items in (j_prev .. j_anchor)
        for j in range(j_prev, j_anchor):
            if j in extra_b_set:
                ops_html.append(("INSERTED", None, (orig_b[j],)))
            elif j in moved_b_set:
                ops_html.append(("MOVED", None, (orig_b[j],)))
            elif in_span(j, moved_b_span):
                ops_html.append(("MOVED", None, (orig_b[j],)))
        # emit the anchor itself
        if i_anchor < n_a and j_anchor < n_b:
            if in_span(i_anchor, moved_a_span) or in_span(j_anchor, moved_b_span):
                ops_html.append(("MOVED",
                                 (orig_a[i_anchor],),
                                 (orig_b[j_anchor],)))
            else:
                ops_html.append(("UNCHANGED",
                                 (orig_a[i_anchor],),
                                 (orig_b[j_anchor],)))
        i_prev, j_prev = i_anchor + 1, j_anchor + 1

    # ------------------------------------------------------------------
    # STATS + OUTPUT
    # ------------------------------------------------------------------
    stats = {
        "ins": len(extra_b),
        "del": len(extra_a),
        "moved": len(moved_pairs),
    }

    def render_diff_to_text(ops_html, output_file):
        with open(output_file + ".txt", "w", encoding="utf-8") as f:
            for tag, a, b in ops_html:
                if tag == "UNCHANGED":
                    continue
                if tag == "DELETED":
                    f.write(f"[DELETED]: {a[0]}\n")
                elif tag == "INSERTED":
                    f.write(f"[INSERTED]: {b[0]}\n")
                elif tag == "MOVED":
                    left = a[0] if a else ""
                    right = b[0] if b else ""
                    f.write(f"[MOVED]: {left}  ->  {right}\n")

    if is_html_output:
        render_diff_to_html(ops_html, file_a, file_b,
                            output_file + ".html", stats)
    else:
        render_diff_to_text(ops_html, output_file)
"""


from utils.normalization import normalize_line
from utils.html_renderer import render_diff_to_html
from difflib import SequenceMatcher
from collections import defaultdict
import bisect


def patience_diff(file_a, file_b, output_file):
    is_updated_required = False
    is_html_output = True

    # =========================================================================
    # SECTION 1 — LOAD FILES
    # =========================================================================
    # load_file reads a file line by line.
    # For every non-empty normalised line it stores:
    #   orig — the raw line (used for display)
    #   norm — the normalised version (used for comparison)
    # Lines whose normalised form is empty (blank lines, whitespace-only) are
    # skipped entirely so they never affect the diff logic.

    def load_file(path):
        orig = []   # raw lines kept for display
        norm = []   # normalised lines used for all comparisons

        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.rstrip("\n")    # strip the newline character only
                n = normalize_line(line)    # caller-supplied normaliser

                if n:                       # skip blank / whitespace-only lines
                    orig.append(line)
                    norm.append(n)

        return orig, norm

    orig_a, norm_a = load_file(file_a)
    orig_b, norm_b = load_file(file_b)

    # =========================================================================
    # SECTION 2 — SLICE DATA STRUCTURE
    # =========================================================================
    # A Slice describes a rectangular window into both files simultaneously.
    # a_low..a_high is the range of indices in File-A we are currently
    # examining; b_low..b_high is the corresponding range in File-B.
    # The diff algorithm is recursive: it repeatedly narrows the slice until
    # no more unique matching lines can be found.

    class Slice:
        def __init__(self, a_low, a_high, b_low, b_high):
            self.a_low  = a_low
            self.a_high = a_high
            self.b_low  = b_low
            self.b_high = b_high

        def not_empty(self):
            # A slice is non-empty only when BOTH sides have at least one line.
            return self.a_low < self.a_high and self.b_low < self.b_high

    # =========================================================================
    # SECTION 3 — UNIQUE MATCHES (the heart of Patience Diff)
    # =========================================================================
    # For the current slice, find every normalised line that appears EXACTLY
    # ONCE in the A-side AND EXACTLY ONCE in the B-side.
    #
    # Why "exactly once"?
    #   Lines that repeat (e.g. BIOS-e820 entries) cannot be uniquely anchored
    #   — we do not know which copy in A corresponds to which copy in B.
    #   By ignoring them here we avoid creating wrong anchor points.
    #   The fallback (SequenceMatcher) handles the ambiguous repeated regions.
    #
    # The result is a list of (a_index, b_index) pairs sorted by a_index.

    def unique_matches(s):
        # counts[key] = [count_in_A, count_in_B, first_a_index, first_b_index]
        counts = {}

        for i in range(s.a_low, s.a_high):
            key = norm_a[i]
            if key not in counts:
                counts[key] = [0, 0, None, None]
            counts[key][0] += 1
            if counts[key][2] is None:      # record first occurrence in A
                counts[key][2] = i

        for j in range(s.b_low, s.b_high):
            key = norm_b[j]
            if key not in counts:
                counts[key] = [0, 0, None, None]
            counts[key][1] += 1
            if counts[key][3] is None:      # record first occurrence in B
                counts[key][3] = j

        matches = []
        for key, (c_a, c_b, a_i, b_j) in counts.items():
            if c_a == 1 and c_b == 1:       # unique on both sides
                matches.append((a_i, b_j))

        return sorted(matches)              # sort by a_index

    # =========================================================================
    # SECTION 4 — LONGEST INCREASING SUBSEQUENCE (Patience Sorting)
    # =========================================================================
    # Given the unique match pairs sorted by a_index, find the longest
    # subsequence where b_index values are also strictly increasing.
    #
    # Why?
    #   A pair (a_i, b_j) can be a stable "unchanged" anchor only if there
    #   exists an overall ordering where both files agree on the sequence.
    #   The LIS on b_j values (when pairs are already sorted by a_i) gives
    #   exactly the largest set of anchors that are consistent in both files.
    #
    # Algorithm: patience sort (O(n log n)).
    #   We maintain a list of "stacks" (only their top values) and a parent
    #   array to reconstruct the actual subsequence.
    #   bisect_left finds where to place the current b_j value.

    def longest_increasing_sequence(matches):
        stacks     = []          # current top value of each stack
        parent     = [None] * len(matches)  # for back-tracing
        stack_tops = []          # index into `matches` of each stack's top

        for i, (_, b_j) in enumerate(matches):
            # Find the leftmost stack whose top is >= b_j (binary search)
            pos = bisect.bisect_left(stacks, b_j)

            if pos == len(stacks):
                stacks.append(b_j)      # start a new stack
                stack_tops.append(i)
            else:
                stacks[pos] = b_j       # replace top of existing stack
                stack_tops[pos] = i

            if pos > 0:
                # This element extends the subsequence ending at stack pos-1
                parent[i] = stack_tops[pos - 1]

        # Back-trace from the top of the last stack to recover the LIS
        result = []
        k = stack_tops[-1] if stack_tops else None
        while k is not None:
            result.append(matches[k])
            k = parent[k]

        return list(reversed(result))   # back-trace gives reverse order

    # =========================================================================
    # SECTION 5 — FALLBACK: SEQUENCEMATCHER
    # =========================================================================
    # When a slice has no unique matching lines (all lines in the region
    # appear more than once on at least one side), patience diff cannot place
    # any anchor.  We fall back to Python's built-in SequenceMatcher (which
    # uses a variant of the Ratcliff/Obershelp algorithm) to diff the slice.
    #
    # The output is translated into the same (tag, index…) tuples used by
    # the rest of the pipeline.

    def fallback(s):
        sm = SequenceMatcher(
            None,
            norm_a[s.a_low:s.a_high],
            norm_b[s.b_low:s.b_high]
        )

        ops = []
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                # Both sides agree — emit UNCHANGED for each aligned pair
                for i, j in zip(range(i1, i2), range(j1, j2)):
                    ops.append(("UNCHANGED", s.a_low + i, s.b_low + j))
            elif tag == "delete":
                for i in range(i1, i2):
                    ops.append(("DELETE", s.a_low + i))
            elif tag == "insert":
                for j in range(j1, j2):
                    ops.append(("INSERT", s.b_low + j))
            elif tag == "replace":
                # A replace is a delete block followed by an insert block
                for i in range(i1, i2):
                    ops.append(("DELETE", s.a_low + i))
                for j in range(j1, j2):
                    ops.append(("INSERT", s.b_low + j))

        return ops

    # =========================================================================
    # SECTION 6 — RECURSIVE PATIENCE DIFF ENGINE
    # =========================================================================
    # diff(s) processes the slice s and returns a flat list of ops.
    #
    # Logic:
    #   1. Find unique matches in the slice.
    #   2. If none exist, fall back to SequenceMatcher.
    #   3. Otherwise, run LIS to get the stable anchors.
    #   4. Recurse on the sub-slice BEFORE each anchor (lines between the
    #      previous anchor and this one), emit the anchor as UNCHANGED, then
    #      move past it and repeat.
    #   5. Recurse on the trailing sub-slice after the last anchor.

    def diff(s):
        result  = []
        matches = unique_matches(s)

        if not matches:
            return fallback(s)          # no unique lines → use fallback

        anchors = longest_increasing_sequence(matches)

        a_curr = s.a_low    # next unprocessed index in A
        b_curr = s.b_low    # next unprocessed index in B

        for a_i, b_j in anchors:
            # Recurse on the region before this anchor
            sub = Slice(a_curr, a_i, b_curr, b_j)
            result.extend(diff(sub))

            # The anchor itself is unchanged in both files
            result.append(("UNCHANGED", a_i, b_j))

            a_curr = a_i + 1    # advance past the anchor in A
            b_curr = b_j + 1    # advance past the anchor in B

        # Recurse on the region after the last anchor
        sub = Slice(a_curr, s.a_high, b_curr, s.b_high)
        result.extend(diff(sub))

        return result

    # Run the top-level diff on the entire files
    ops = diff(Slice(0, len(norm_a), 0, len(norm_b)))

    # =========================================================================
    # SECTION 7 — COLLECT INITIAL INSERTS / DELETES
    # =========================================================================
    # Walk the ops list once to separate out which A-indices were deleted and
    # which B-indices were inserted.  These are the "residual" lines that the
    # Patience Diff could not place as stable anchors — they are candidates
    # for move detection in the next section.

    inserted = []   # B-indices not matched as UNCHANGED
    deleted  = []   # A-indices not matched as UNCHANGED
    updated  = []   # populated later if is_updated_required is True

    for op in ops:
        if op[0] == "INSERT":
            inserted.append(op[1])
        elif op[0] == "DELETE":
            deleted.append(op[1])

    # =========================================================================
    # SECTION 8 — PATIENCEDIFFPLUS MOVE DETECTION
    # =========================================================================
    # Based on Jon Trent's PatienceDiffPlus (github.com/jonTrent/PatienceDiff).
    #
    # The algorithm:
    #   Take the residual deleted lines (from A) and residual inserted lines
    #   (from B).  Run the Patience Diff algorithm on just these lines.
    #   Any line that matches in this second pass is a MOVED line — it existed
    #   in both files but at a different position relative to its stable
    #   neighbours.  Repeat until no more matches are found.
    #
    # WHY THIS IS CORRECT FOR DUPLICATE LINES:
    #   Consider line X appearing 3 times in A and 4 times in B.
    #   The first diff pass matches as many copies as possible as UNCHANGED
    #   (anchored pairs from unique-match recursion + fallback).  Suppose
    #   3 copies are matched as UNCHANGED.  The 4th copy in B falls out as
    #   INSERT — it is a genuine new insertion, NOT a move.  It never reaches
    #   the move-detection step because there is no corresponding DELETE for it.
    #
    #   By contrast, if 2 copies were matched and 1 A-copy fell out as DELETE
    #   and 2 B-copies fell out as INSERT, the second-pass Patience Diff on
    #   those residuals will only match 1 DELETE with 1 INSERT (the one that
    #   genuinely moved).  The remaining INSERT stays as INSERT.
    #
    # This is fundamentally different from the naive approach (your old code)
    # of pairing every DELETE with any INSERT of the same content using LIS,
    # which incorrectly flagged drifted lines and broke on duplicate content.

    def run_patience_on_lines(a_indices, b_indices):
        """
        Run one pass of PatienceDiffPlus on the given residual index lists.

        a_indices: list of A-file indices that are currently unmatched (DELETE)
        b_indices: list of B-file indices that are currently unmatched (INSERT)

        Returns:
            matched:   list of (a_idx, b_idx) pairs confirmed as moves
            new_del:   remaining A-indices still unmatched after this pass
            new_ins:   remaining B-indices still unmatched after this pass
        """
        if not a_indices or not b_indices:
            return [], a_indices, b_indices

        # Build content → [list of positions] maps for residual lines
        a_content = defaultdict(list)   # normalised content → [a_indices]
        b_content = defaultdict(list)   # normalised content → [b_indices]

        for i in a_indices:
            a_content[norm_a[i]].append(i)
        for j in b_indices:
            b_content[norm_b[j]].append(j)

        # Find content that appears EXACTLY ONCE in both residual sets.
        # This mirrors the unique_matches step of the main Patience Diff.
        # Only unique residual lines can be confirmed as unambiguous moves.
        unique_pairs = []
        for key in a_content:
            if key in b_content and len(a_content[key]) == 1 and len(b_content[key]) == 1:
                unique_pairs.append((a_content[key][0], b_content[key][0]))

        if not unique_pairs:
            # No unique residual matches → no more moves can be found
            return [], a_indices, b_indices

        # Sort by A-position, then run LIS on B-positions.
        # Pairs in the LIS are consistent with the global order → they are
        # genuine moves (their relative order changed vs. the stable anchors).
        # Pairs outside the LIS would be contradictory placements → skip them.
        unique_pairs.sort(key=lambda p: p[0])
        b_seq = [j for _, j in unique_pairs]

        # Standard LIS using patience sort
        tails, tops, par = [], [], [None] * len(unique_pairs)
        for idx, bj in enumerate(b_seq):
            pos = bisect.bisect_left(tails, bj)
            if pos == len(tails):
                tails.append(bj)
                tops.append(idx)
            else:
                tails[pos] = bj
                tops[pos] = idx
            if pos > 0:
                par[idx] = tops[pos - 1]

        # Trace back to get LIS indices
        lis_set, k = set(), tops[-1] if tops else None
        while k is not None:
            lis_set.add(k)
            k = par[k]

        # Pairs in the LIS are confirmed moves for this pass
        matched = [unique_pairs[idx] for idx in sorted(lis_set)]

        # Remove matched indices from the residual pools
        matched_a = {i for i, _ in matched}
        matched_b = {j for _, j in matched}

        new_del = [i for i in a_indices if i not in matched_a]
        new_ins = [j for j in b_indices if j not in matched_b]

        return matched, new_del, new_ins

    # Iteratively run PatienceDiffPlus passes until no more moves are found.
    # Each pass may surface new unique matches among the still-unmatched lines.
    all_moves    = []   # confirmed (a_idx, b_idx) move pairs
    cur_deleted  = list(deleted)
    cur_inserted = list(inserted)

    while True:
        matched, cur_deleted, cur_inserted = run_patience_on_lines(
            cur_deleted, cur_inserted
        )
        if not matched:
            break           # no more moves found — stop iterating
        all_moves.extend(matched)

    # After all passes, whatever remains is truly deleted / inserted
    remaining_deleted  = cur_deleted
    remaining_inserted = cur_inserted

    # Build lookup structures for the output phase
    moved_a  = {i for i, _ in all_moves}    # set of A-indices that moved
    moved_b  = {j for _, j in all_moves}    # set of B-indices that moved
    move_map = {i: j for i, j in all_moves} # A-index → destination B-index

    # =========================================================================
    # SECTION 9 — UPDATED DETECTION (optional, disabled by default)
    # =========================================================================
    # If is_updated_required is True, try to pair remaining deleted lines with
    # remaining inserted lines that have similar content (ratio > 0.75).
    # These are shown as "updated" (red on left, green on right) rather than
    # as separate delete + insert.

    final_deleted = []

    if is_updated_required:
        for i in remaining_deleted:
            best_ratio = 0
            best_j     = None

            for j in remaining_inserted:
                sim = SequenceMatcher(None, norm_a[i], norm_b[j]).ratio()
                if sim > best_ratio:
                    best_ratio = sim
                    best_j     = j

            if best_j is not None and best_ratio > 0.75:
                updated.append((i, best_j, best_ratio))
                remaining_inserted.remove(best_j)
            else:
                final_deleted.append(i)
    else:
        final_deleted = remaining_deleted

    update_map = {i: (j, sim) for i, j, sim in updated}

    # =========================================================================
    # SECTION 10 — BUILD ops_html (FIRST PASS)
    # =========================================================================
    # Walk the ops list produced by the main diff engine and emit display
    # tuples.  Each tuple is (tag, left_content, right_content).
    #
    # Special handling for MOVED lines:
    #   Instead of emitting a plain "MOVED" tag we emit two internal markers:
    #
    #   MOVED_SRC — at the DELETE op position (where the line used to be).
    #               Carries the destination B-index as metadata so the second
    #               pass can find its matching MOVED_DST.
    #
    #   MOVED_DST — at the INSERT op position (where the line now appears).
    #               Also carries the B-index as metadata.
    #
    # CRITICAL DETAIL: we do NOT add j to used_b when emitting MOVED_SRC.
    # If we did, the INSERT op for j would see j in used_b and skip,
    # meaning MOVED_DST would never be emitted and the second pass would
    # find nothing to paint.

    ops_html = []
    used_a   = set()
    used_b   = set()

    for op in ops:
        tag = op[0]

        # ------------------------------------------------------------------
        # UNCHANGED — line is identical in both files at these positions
        # ------------------------------------------------------------------
        if tag == "UNCHANGED":
            _, i, j = op
            ops_html.append(("UNCHANGED", (orig_a[i],), (orig_b[j],)))
            used_a.add(i)
            used_b.add(j)

        # ------------------------------------------------------------------
        # DELETE — line was removed from A
        # ------------------------------------------------------------------
        elif tag == "DELETE":
            i = op[1]

            # Check if this deleted line was similar-enough to an insertion
            # to count as an "update" (only when is_updated_required is True)
            if i in update_map:
                j, sim = update_map[i]
                ops_html.append(("UPDATED", (orig_a[i],), (orig_b[j],)))
                used_a.add(i)
                used_b.add(j)
                continue

            # Check if PatienceDiffPlus identified this as a moved line
            if i in moved_a:
                j = move_map[i]
                # Emit MOVED_SRC marker at the OLD (source) display position.
                # The 4th element `j` is metadata: the B-index of the
                # destination, used by the second pass to find MOVED_DST.
                # DO NOT add j to used_b here — the INSERT op must still fire.
                ops_html.append(("MOVED_SRC", (orig_a[i],), None, j))
                used_a.add(i)
                # NOTE: intentionally NOT doing used_b.add(j)
                continue

            # Plain deletion
            ops_html.append(("DELETED", (orig_a[i],), None))
            used_a.add(i)

        # ------------------------------------------------------------------
        # INSERT — line was added to B
        # ------------------------------------------------------------------
        elif tag == "INSERT":
            j = op[1]

            if j in used_b:
                # Already emitted via UPDATED path — skip
                continue

            if j in moved_b:
                # This is the NEW (destination) position of a moved line.
                # Emit MOVED_DST marker so the second pass can locate it.
                # The 4th element `j` is metadata matching the MOVED_SRC above.
                ops_html.append(("MOVED_DST", None, (orig_b[j],), j))
                used_b.add(j)
                continue

            # Plain insertion
            ops_html.append(("INSERTED", None, (orig_b[j],)))
            used_b.add(j)

    # =========================================================================
    # SECTION 11 — PAINT THE YELLOW BAND (SECOND PASS)
    # =========================================================================
    # ops_html is now a flat list in display order.  For each move we have:
    #   MOVED_SRC at index src_pos  (old display position of the moved line)
    #   MOVED_DST at index dst_pos  (new display position of the moved line)
    #
    # We paint every row in [min(src_pos, dst_pos) .. max(src_pos, dst_pos)]
    # as MOVED (yellow background), regardless of its original tag.
    #
    # This is the simplest correct approach: no rank arithmetic, no index
    # mirrors, no coordinate-space conversions.  We work directly on the
    # final display list where positions are unambiguous.
    #
    # Step 1: build a dict   j_b → display_index   for every MOVED_DST row.
    # Step 2: for every MOVED_SRC, look up its dst_pos and paint the band.
    # Step 3: normalise all remaining MOVED_SRC / MOVED_DST tags and strip
    #         the j_b metadata so the renderer only ever sees 3-tuples.

    # Step 1
    dst_pos_by_jb = {}
    for idx, entry in enumerate(ops_html):
        if entry[0] == "MOVED_DST":
            dst_pos_by_jb[entry[3]] = idx   # entry[3] is the j_b metadata

    # Step 2
    for idx, entry in enumerate(ops_html):
        if entry[0] == "MOVED_SRC":
            j_b     = entry[3]
            dst_pos = dst_pos_by_jb.get(j_b)

            if dst_pos is not None:
                lo = min(idx, dst_pos)
                hi = max(idx, dst_pos)

                for k in range(lo, hi + 1):
                    # Force the tag to MOVED; keep the two content columns.
                    # entry[1:3] slices out (left_content, right_content).
                    ops_html[k] = ("MOVED",) + ops_html[k][1:3]

    # Step 3 — strip metadata and normalise any leftover internal tags
    final_ops_html = []
    for entry in ops_html:
        if entry[0] in ("MOVED_SRC", "MOVED_DST"):
            # Wasn't covered by a band (edge case) — still show as MOVED
            final_ops_html.append(("MOVED",) + entry[1:3])
        else:
            # entry[:3] strips the j_b metadata from any band row that was
            # already rewritten to ("MOVED", left, right, j_b_leftover).
            # For normal rows it is a no-op.
            final_ops_html.append(entry[:3])

    # =========================================================================
    # SECTION 12 — STATS
    # =========================================================================
    stats = {
        "ins": len(remaining_inserted),   # net new lines added to B
        "del": len(final_deleted)          # net lines removed from A
    }

    # =========================================================================
    # SECTION 13 — TEXT OUTPUT (alternative to HTML)
    # =========================================================================
    def render_diff_to_text(ops_html, output_file):
        with open(output_file + ".txt", "w", encoding="utf-8") as f:
            for tag, a, b in ops_html:
                if tag == "UNCHANGED":
                    continue
                elif tag == "DELETED":
                    f.write(f"[DELETED]: {a[0]}\n")
                elif tag == "INSERTED":
                    f.write(f"[INSERTED]: {b[0]}\n")
                elif tag == "MOVED":
                    left  = a[0] if a else ""
                    right = b[0] if b else ""
                    f.write(f"[MOVED]: {left} -> {right}\n")
                elif tag == "UPDATED":
                    f.write(f"[UPDATED]: {a[0]} -> {b[0]}\n")

    # =========================================================================
    # SECTION 14 — OUTPUT
    # =========================================================================
    if is_html_output:
        render_diff_to_html(
            final_ops_html,
            file_a,
            file_b,
            output_file + ".html",
            stats
        )
    else:
        render_diff_to_text(final_ops_html, output_file)
