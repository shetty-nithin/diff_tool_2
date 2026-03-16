"""
Paper: Change Detection in Hierarchically Structured Information
"""

"""
from utils.normalization import normalize_line

def la_diff(file_a, file_b, output_file):
    def load_nodes(path):
        nodes = []
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for idx, line in enumerate(f):
                raw_val = line.strip()
                norm_val = normalize_line(raw_val)
                if norm_val:
                    nodes.append({'id': f"{path}_{idx}", 'val': norm_val, 'raw': raw_val, 'pos': idx})
        return nodes

    old_nodes = load_nodes(file_a)
    new_nodes = load_nodes(file_b)
    
    # Phase 1: Finding a good matching
    matched_in_old = {} # old_id -> new_node{id:id, val:val}
    matched_in_new = set() # new_ids that are paired
    
    for old in old_nodes:
        for new in new_nodes:
            if new['id'] not in matched_in_new and old['val'] == new['val']:
                matched_in_old[old['id']] = new
                matched_in_new.add(new['id'])
                break
                
    # Phase 2: Minimum Conforming Edit Script (MCES)
    edit_script = []

    for new in new_nodes:
        #if new['id'] not in matched_in_new:
            #edit_script.append(f"[INSERTED] {new['raw']}")

        partner = next((old for old, n_node in matched_in_old.items() 
                            if n_node['id'] == new['id']), None)
        
        if not partner:
            edit_script.append(f"[INSERTED] {new['raw']}")
        else:
            old_idx = int(partner.split('_')[-1])
            if old_idx != new['pos']:
                edit_script.append(f"[MOVED] {new['raw']} (from line {old_idx} to {new['pos']})")

    for old in old_nodes:
        if old['id'] not in matched_in_old:
            edit_script.append(f"[DELETED] {old['raw']}")

    with open(output_file, "w", encoding="utf-8") as out:
        if not edit_script:
            out.write("Files are semantically identical.")
        else:
            for op in edit_script:
                out.write(op + "\n")

"""

from utils.normalization import normalize_line
from difflib import SequenceMatcher

def la_diff(file_a, file_b, output_file):
    def load_nodes(path):
        nodes = []

        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for idx, line in enumerate(f):
                orig_val = line.strip()
                norm_val = normalize_line(orig_val)

                if norm_val:
                    nodes.append({'id': f"{path}_{idx}", 'norm': norm_val, 'orig': orig_val, 'pos': idx})

        return nodes

    old_nodes = load_nodes(file_a)
    new_nodes = load_nodes(file_b)
    
    # Phase 1: Finding a good matching
    matched_in_old = {} # old_id -> new_node{id:id, norm:norm}
    matched_in_new = set() # new_ids that are paired
    
    for old in old_nodes:
        for new in new_nodes:
            if new['id'] not in matched_in_new and old['norm'] == new['norm']:
                matched_in_old[old['id']] = new
                matched_in_new.add(new['id'])
                break
                
    # Phase 2: Minimum Conforming Edit Script (MCES)
    edit_script = []
    inserted_nodes = []
    deleted_nodes = []
    moved_nodes = []
    updated_nodes = []
    is_updated_required = True

    for new in new_nodes:
        """
        if new['id'] not in matched_in_new:
            edit_script.append(f"[INSERTED] {new['orig']}")
            inserted += 1
        """
        partner = next((old for old, n_node in matched_in_old.items() 
                            if n_node['id'] == new['id']), None)
        
        if not partner:
            #edit_script.append(f"[INSERTED] {new['orig']}")
            #inserted += 1
            inserted_nodes.append(new)
        else:
            old_idx = int(partner.split('_')[-1])
            if old_idx != new['pos']:
                #edit_script.append(f"[MOVED] {new['orig']}")
                #moved += 1
                moved_nodes.append(new)

    for old in old_nodes:
        if old['id'] not in matched_in_old:
            #edit_script.append(f"[DELETED]  {old['orig']}")
            #deleted += 1
            deleted_nodes.append(old)

    if is_updated_required:
        remaining_inserts = inserted_nodes.copy()
        remaining_deletes = []
        
        for old in deleted_nodes:
            best_ratio = 0
            best_match = None

            for new in remaining_inserts:
                sim = SequenceMatcher(None, old['norm'], new['norm']).ratio()
                if sim > 0.75:
                    best_ratio = sim
                    best_match = new
            
            if best_match is not None:
                updated_nodes.append((old, best_match, best_ratio))
                remaining_inserts.remove(best_match)
            else:
                remaining_deletes.append(old)

        inserted_nodes = remaining_inserts
        deleted_nodes = remaining_deletes

    for node in inserted_nodes:
        edit_script.append(f"[INSERTED] {node['orig']}")
    for node in deleted_nodes:
        edit_script.append(f"[DELETED]  {node['orig']}")
    for node in moved_nodes:
        edit_script.append(f"[MOVED] {node['orig']}")
    for old, new, sim in updated_nodes:
        edit_script.append(f"[UPDATED] [Similarity: {sim:.2f}] {old['orig']}  ->  {new['orig']}")

    with open(output_file, "w", encoding="utf-8") as out:
        out.write("-----------------------------------------\n")
        out.write("Diff Summary\n")
        out.write("-----------------------------------------\n")
        out.write(f"Lines compared : {max(len(old_nodes), len(new_nodes))}\n")
        out.write(f"Inserted       : {len(inserted_nodes)}\n")
        out.write(f"Deleted        : {len(deleted_nodes)}\n")
        if is_updated_required:
            out.write(f"Updated        : {len(updated_nodes)}\n")
        out.write(f"Moved          : {len(moved_nodes)}\n")
        out.write("-----------------------------------------\n\n")

        if not edit_script:
            out.write("Files are semantically identical.")
        else:
            for op in edit_script:
                out.write(op + "\n")
