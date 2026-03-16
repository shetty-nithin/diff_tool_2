"""
import hashlib
from collections import defaultdict
from difflib import SequenceMatcher
from utils.normalization import normalize_line

def hash_diff(file_a, file_b, output_file):

    def get_hash(text: str) -> str:
        return hashlib.md5(text.encode('utf-8')).hexdigest()

    def load_file(path: str):
        original = []
        normalized = []
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.rstrip("\n")
                    if not line.strip(): continue # Skip empty lines
                    norm = normalize_line(line)
                    original.append(line)
                    normalized.append(norm)
        except FileNotFoundError:
            print(f"Error: File {path} not found.")
        return original, normalized

    orig_a, norm_a = load_file(file_a)
    orig_b, norm_b = load_file(file_b)

    # Map File B: {hash_id: [list_of_indices]}
    b_map = defaultdict(list)
    for idx, norm in enumerate(norm_b):
        b_map[get_hash(norm)].append(idx)

    matched_b_indices = set()
    results = []

    # STAGE 1: Process File A against File B
    for i, norm_line_a in enumerate(norm_a):
        h = get_hash(norm_line_a)
        
        if h in b_map and b_map[h]:
            j = b_map[h].pop(0)
            matched_b_indices.add(j)
            #results.append(f"[Unchanged] {orig_a[i]}")
        else:
            best_ratio = 0
            best_match_idx = -1
            
            # Threshold check: Find a line in B that is very similar but not identical
            for j, norm_line_b in enumerate(norm_b):
                if j in matched_b_indices: continue
                
                # Compare original strings for specific line similarity
                sim = SequenceMatcher(None, orig_a[i], orig_b[j]).ratio()
                if sim > 0.7: # Adjust threshold as needed
                    best_ratio = sim
                    best_match_idx = j
                    break 
            
            if best_match_idx != -1:
                results.append(f"[UPDATED] [{best_ratio:.2f}]: {orig_a[i]}  ->  {orig_b[best_match_idx]}")
                matched_b_indices.add(best_match_idx)
            else:
                results.append(f"[DELETED] {orig_a[i]}")

    for j, line_b in enumerate(orig_b):
        if j not in matched_b_indices:
            results.append(f"[INSERTED] {line_b}")

    with open(output_file, "w", encoding="utf-8") as out:
        if not results:
            out.write("Files are semantically identical.")
        else:
            for line in results:
                out.write(line + "\n")

"""


import hashlib
from collections import defaultdict
from difflib import SequenceMatcher
from utils.normalization import normalize_line

def hash_diff(file_a, file_b, output_file):
    def get_hash(text: str) -> str:
        return hashlib.md5(text.encode('utf-8')).hexdigest()


    def load_file(path: str):
        original = []
        normalized = []
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.rstrip("\n")
                    if not line.strip(): continue
                    norm = normalize_line(line)
                    original.append(line)
                    normalized.append(norm)
        except FileNotFoundError:
            print(f"Error: File {path} not found.")
        return original, normalized

    orig_a, norm_a = load_file(file_a)
    orig_b, norm_b = load_file(file_b)

    # Map File B: {hash_id: [list_of_indices]}
    b_map = defaultdict(list)
    for idx, norm in enumerate(norm_b):
        b_map[get_hash(norm)].append(idx)

    matched_b_indices = set()
    results = []

    inserted = 0
    deleted = 0
    moved = 0
    updated = 0
    is_updated_required = True

    for i, norm_line_a in enumerate(norm_a):
        h = get_hash(norm_line_a)
        
        if h in b_map and b_map[h]:
            j = b_map[h].pop(0)
            matched_b_indices.add(j)

            if i != j:
                results.append(f"[MOVED] {orig_a[i]}")
                moved += 1
        elif is_updated_required:
            best_ratio = 0
            best_match_idx = -1
            
            for j, norm_line_b in enumerate(norm_b):
                if j in matched_b_indices: continue
                
                sim = SequenceMatcher(None, norm_a[i], norm_b[j]).ratio()
                if sim > 0.75: # 0 <= sim <= 1(where 1 = exact match)
                    best_ratio = sim
                    best_match_idx = j
                    break 
            
            if best_match_idx != -1:
                results.append(f"[UPDATED] [Similarity: {best_ratio:.2f}]: {orig_a[i]}  ->  {orig_b[best_match_idx]}")
                updated += 1
                matched_b_indices.add(best_match_idx)
            else:
                results.append(f"[DELETED]  {orig_a[i]}")
                deleted += 1
        else:
            results.append(f"[DELETED]  {orig_a[i]}")
            deleted += 1

    for j, line_b in enumerate(orig_b):
        if j not in matched_b_indices:
            results.append(f"[INSERTED] {line_b}")
            inserted += 1

    with open(output_file, "w", encoding="utf-8") as out:
        out.write("-----------------------------------------\n")
        out.write("Diff Summary\n")
        out.write("-----------------------------------------\n")
        out.write(f"Lines compared : {max(len(orig_a), len(orig_b))}\n")
        out.write(f"Inserted       : {inserted}\n")
        out.write(f"Deleted        : {deleted}\n")
        if is_updated_required:
            out.write(f"Updated        : {updated}\n")
        out.write(f"Moved          : {moved}\n")
        out.write("-----------------------------------------\n\n")

        if not results:
            out.write("Files are semantically identical.")
        else:
            for line in results:
                out.write(line + "\n")
