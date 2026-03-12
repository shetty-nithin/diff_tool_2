"""Paper: Change Detection in Hierarchically Structured Information"""

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
        if new['id'] not in matched_in_new:
            edit_script.append(f"[INSERTED] {new['raw']}")
        """
        partner = next((old for old, n_node in matched_in_old.items() 
                            if n_node['id'] == new['id']), None)
        
        if not partner:
            edit_script.append(f"[INSERTED] {new['raw']}")
        else:
            old_idx = int(partner.split('_')[-1])
            if old_idx != new['pos']:
                edit_script.append(f"[MOVED] {new['raw']} (from line {old_idx} to {new['pos']})")
        """

    for old in old_nodes:
        if old['id'] not in matched_in_old:
            edit_script.append(f"[DELETED] {old['raw']}")

    with open(output_file, "w", encoding="utf-8") as out:
        if not edit_script:
            out.write("Files are semantically identical.")
        else:
            for op in edit_script:
                out.write(op + "\n")
