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
    # Lines whose normalised form is empty (blank lines, whitespace-only) are skipped entirely so they never affect the diff logic.

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

    # =========================================================================
    # SECTION 2 — SLICE DATA STRUCTURE
    # =========================================================================
    # A Slice describes a rectangular window into both files simultaneously.
    # a_low - a_high is the range of indices in File-A we are currently examining.
    # b_low - b_high is the corresponding range in File-B.
    # The diff algorithm is recursive: it repeatedly narrows the slice until no more unique matching lines can be found.

    class Slice:
        def __init__(self, a_low, a_high, b_low, b_high):
            self.a_low  = a_low
            self.a_high = a_high
            self.b_low  = b_low
            self.b_high = b_high

        def not_empty(self):
            return self.a_low < self.a_high and self.b_low < self.b_high

    # =========================================================================
    # SECTION 3 — UNIQUE MATCHES
    # =========================================================================
    # For the current slice, find every normalised line that appears EXACTLY
    # ONCE in the A-side AND EXACTLY ONCE in the B-side.
    #
    # The result is a list of (a_index, b_index) pairs sorted by a_index.

    def unique_matches(s):
        counts = {}     # counts[key] = [count_in_A, count_in_B, first_a_index, first_b_index]

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
    # Reason:
    #   A pair (a_i, b_j) can be a stable "unchanged" anchor only if there
    #   exists an overall ordering where both files agree on the sequence.
    #   The LIS on b_j values (when pairs are already sorted by a_i) gives
    #   exactly the largest set of anchors that are consistent in both files.
    #
    # Algorithm: patience sort (O(n log n)).

    def longest_increasing_sequence(matches):
        stacks     = []          # current top value of each stack
        parent     = [None] * len(matches)  # for back-tracing
        stack_tops = []          # index into `matches` of each stack's top

        for i, (_, b_j) in enumerate(matches):
            pos = bisect.bisect_left(stacks, b_j)  # Finds the leftmost stack whose top is >= b_j (binary search)

            if pos == len(stacks):
                stacks.append(b_j)      # start a new stack
                stack_tops.append(i)
            else:
                stacks[pos] = b_j       # replace top of existing stack
                stack_tops[pos] = i

            if pos > 0:
                parent[i] = stack_tops[pos - 1]  # This element extends the subsequence ending at stack pos-1

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
    # any anchor.  We fall back to Python's built-in SequenceMatcher to diff the slice.
    # The output is translated into the same (tag, index…) tuples.

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
    #   4. Recurse on the sub-slice BEFORE each anchor (lines between the previous anchor and this one)
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

            # The anchor is unchanged in both files
            result.append(("UNCHANGED", a_i, b_j))

            a_curr = a_i + 1
            b_curr = b_j + 1

        # Recurse on the region after the last anchor
        sub = Slice(a_curr, s.a_high, b_curr, s.b_high)
        result.extend(diff(sub))

        return result

    ops = diff(Slice(0, len(norm_a), 0, len(norm_b)))

    # =========================================================================
    # SECTION 7 — COLLECT INITIAL INSERTS / DELETES
    # =========================================================================
    # Walk the ops list once to separate out which A-indices were deleted and which B-indices were inserted.
    # These are the "remaining" lines that the Patience Diff could not place as stable anchors — they are candidates for move detection in the next section.

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
    #   Take the residual deleted lines (from A) and residual inserted lines (from B).
    #   Run the Patience Diff algorithm on just these lines.
    #   Any line that matches in this second pass is a MOVED line — it existed in both files but at a different position relative to its stable neighbours.
    #   Repeat until no more matches are found.

    def patience_diff_plus(a_indices, b_indices):
        """
        Runnign PatienceDiffPlus on the given residual index lists.

        a_indices: list of A-file indices that are currently unmatched (DELETE)
        b_indices: list of B-file indices that are currently unmatched (INSERT)

        Returns:
            matched:   list of (a_idx, b_idx) pairs confirmed as moves
            new_del:   remaining A-indices still unmatched after this pass
            new_ins:   remaining B-indices still unmatched after this pass
        """
        if not a_indices or not b_indices:
            return [], a_indices, b_indices

        # [list of positions] maps for residual lines
        a_content = defaultdict(list)   # {normalised_line: [a_indices]}
        b_content = defaultdict(list)   # {normalised_line: [b_indices]}

        for i in a_indices:
            a_content[norm_a[i]].append(i)
        for j in b_indices:
            b_content[norm_b[j]].append(j)

        # Find content that appears EXACTLY ONCE in both residual sets.
        # This is same as unique_matches step of the main Patience Diff.
        unique_pairs = []
        for key in a_content:
            if key in b_content and len(a_content[key]) == 1 and len(b_content[key]) == 1:
                unique_pairs.append((a_content[key][0], b_content[key][0]))

        if not unique_pairs:
            return [], a_indices, b_indices

        unique_pairs.sort(key=lambda p: p[0]) # Sort by A-position
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

        # Removing matched indices from the residual pools
        matched_a = {i for i, _ in matched}
        matched_b = {j for _, j in matched}

        new_del = [i for i in a_indices if i not in matched_a]
        new_ins = [j for j in b_indices if j not in matched_b]

        return matched, new_del, new_ins

    # Iteratively running PatienceDiffPlus passes until no more moves are found.
    # Each pass may surface new unique matches among the still-unmatched lines.
    all_moves    = []   # confirmed (a_idx, b_idx) move pairs
    cur_deleted  = list(deleted)
    cur_inserted = list(inserted)

    while True:
        matched, cur_deleted, cur_inserted = patience_diff_plus(cur_deleted, cur_inserted)
        if not matched:
            break           # no more moves found
        all_moves.extend(matched)

    remaining_deleted  = cur_deleted
    remaining_inserted = cur_inserted

    moved_a  = {i for i, _ in all_moves}    # set of A-indices that moved
    moved_b  = {j for _, j in all_moves}    # set of B-indices that moved
    move_map = {i: j for i, j in all_moves} # origin A-index → destination B-index

    # =========================================================================
    # SECTION 9 — UPDATED DETECTION (optional, disabled by default)
    # =========================================================================
    # If "is_updated_required" is True, try to pair remaining deleted lines with remaining inserted lines that have similar content (ratio > 0.75).
    # These are shown as "updated" (red on left, green on right) rather than as separate delete + insert.

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
    # Each tuple is (tag, left_content, right_content).
    #
    # Special handling for MOVED lines:
    #   Instead of emitting a plain "MOVED" tag, im emitting two internal markers:
    #
    #   MOVED_SRC — at the DELETE op position (where the line used to be).
    #               Carries the destination B-index as metadata so the second
    #               pass can find its matching MOVED_DST.
    #   MOVED_DST — at the INSERT op position (where the line now appears).
    #               Also carries the B-index as metadata.

    ops_html = []
    used_a   = set()
    used_b   = set()

    for op in ops:
        tag = op[0]

        if tag == "UNCHANGED":
            _, i, j = op
            ops_html.append(("UNCHANGED", (orig_a[i],), (orig_b[j],)))
            used_a.add(i)
            used_b.add(j)

        elif tag == "DELETE":
            i = op[1]

            if i in update_map:
                j, sim = update_map[i]
                ops_html.append(("UPDATED", (orig_a[i],), (orig_b[j],)))
                used_a.add(i)
                used_b.add(j)
                continue

            if i in moved_a:
                j = move_map[i]
                ops_html.append(("MOVED_LINE_SRC", (orig_a[i],), None, j))
                used_a.add(i)
                continue

            ops_html.append(("DELETED", (orig_a[i],), None))
            used_a.add(i)

        elif tag == "INSERT":
            j = op[1]

            if j in used_b:
                continue # Already emitted via UPDATED path

            if j in moved_b:
                ops_html.append(("MOVED_LINE_DST", None, (orig_b[j],), j))
                used_b.add(j)
                continue

            ops_html.append(("INSERTED", None, (orig_b[j],)))
            used_b.add(j)

    # =========================================================================
    # SECTION 11 — TO HIGHLIGHT THE 'MOVED AREA' (SECOND PASS)
    # =========================================================================
    # ops_html is now a flat list in display order.  For each move we have:
    #   MOVED_SRC at index src_pos  (old display position of the moved line)
    #   MOVED_DST at index dst_pos  (new display position of the moved line)
    #
    # We paint every row in [min(src_pos, dst_pos) .. max(src_pos, dst_pos)]
    # as MOVED (yellow background), regardless of its original tag.
    #
    # Step 1: build a dict   j_b → display_index   for every MOVED_DST row.
    # Step 2: for every MOVED_SRC, look up its dst_pos and paint the band.
    # Step 3: normalise all remaining MOVED_SRC / MOVED_DST tags and strip
    #         the j_b metadata so the renderer only ever sees 3-tuples.

    # Step 1
    dst_pos_by_jb = {}
    for idx, entry in enumerate(ops_html):
        if entry[0] == "MOVED_LINE_DST":
            dst_pos_by_jb[entry[3]] = idx   # entry[3] is the j_b metadata

    # Step 2
    for idx, entry in enumerate(ops_html):
        if entry[0] == "MOVED_LINE_SRC":
            j_b     = entry[3]
            dst_pos = dst_pos_by_jb.get(j_b)

            if dst_pos is not None:
                lo = min(idx, dst_pos)
                hi = max(idx, dst_pos)

                for k in range(lo, hi + 1):
                    # Force the tag to MOVED; keep the two content columns.
                    # entry[1:3] slices out (left_content, right_content).
                    if ops_html[k][0] not in ("MOVED_LINE_SRC", "MOVED_LINE_DST"):
                        ops_html[k] = ("MOVED",) + ops_html[k][1:3]

    # Step 3 — strip metadata and normalise any leftover internal tags
    final_ops_html = []
    for entry in ops_html:
        if entry[0] in ("MOVED_LINE_SRC", "MOVED_LINE_DST"):
            # Wasn't covered by a band (edge case) — still show as MOVED
            final_ops_html.append(("MOVED_LINE",) + entry[1:3])
        else:
            final_ops_html.append(entry[:3])

    stats = {
        "ins": len(remaining_inserted),
        "del": len(final_deleted)
    }

    # =========================================================================
    # SECTION 12 — TEXT OUTPUT (alternative to HTML)
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
    # SECTION 13 — OUTPUT
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
