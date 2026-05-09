def render_diff_to_html(ops, file_a, file_b, output_path, stats):
    html_template = """
    <html>
        <head>
            <style>
                body {{
                    font-family: 'Segoe UI', 
                    sans-serif; margin: 30px;
                    background: #f0f2f5;
                    color: #333;
                }}
                .header-card {{ 
                    background: #eef2f6;
                    padding: 10 20px;
                    border-radius: 10px;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                    margin-bottom: 30px;
                    position: sticky;
                    top: 0px;
                    z-index: 100
                }}
                .diff-table {{
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 1px;
                    background: #ccc;
                    border: 1px solid #bbb;
                }}
                .cell {{
                    padding: 6px 12px;
                    white-space: pre-wrap;
                    font-family: 'Consolas', monospace;
                    font-size: 13px;
                    background: white;
                    min-height: 1.5em;
                }}
                .added {{
                    background-color: #e6ffec;
                    border-left: 4px solid #2da44e;
                }}
                .deleted {{
                    background-color: #ffebe9;
                    border-left: 4px solid #cf222e;
                }}
                .empty {{
                    background-color: #fafafa;
                }}
                .moved {{
                    background-color: #FFF9C4;
                    border-left: 4px solid #e6b800;
                }}
                .title-bar {{
                    font-weight: bold;
                    background: #f6f8fa;
                    padding: 12px;
                    border-bottom: 2px solid #ddd;
                }}
            </style>
        </head>
        <body>
            <div class="header-card">
                <h1>Diff Analysis: Using Patience Algorithm</h1>
                <p><b>Original:</b> {fa} | <b>New:</b> {fb}</p>
                <p>Deleted: <span style="color:#cf222e">{rem}</span> | Inserted: <span style="color:#2da44e">{ins}</span></p>
            </div>
            <div class="diff-table">
                <div class="title-bar">{fa}</div><div class="title-bar">{fb}</div>
                {rows}
            </div>
        </body>
    </html>"""

    rows = []
    for op, old_node, new_node in ops:
        txt_a = old_node[0] if old_node else ""
        txt_b = new_node[0] if new_node else ""
        
        if op == "UNCHANGED":
            rows.append(f'<div class="cell">{txt_a}</div><div class="cell">{txt_b}</div>')
        elif op == "DELETED":
            rows.append(f'<div class="cell deleted">{txt_a}</div><div class="cell empty"></div>')
        elif op == "INSERTED":
            rows.append(f'<div class="cell empty"></div><div class="cell added">{txt_b}</div>')
        elif op == "UPDATED":
            rows.append(f'<div class="cell deleted">{txt_a}</div><div class="cell added">{txt_b}</div>')
        elif op == "MOVED":
            class_a = "cell moved" if txt_a else "cell empty"
            class_b = "cell moved" if txt_b else "cell empty"
            rows.append(
                f'<div class="{class_a}">{txt_a}</div>'
                f'<div class="{class_b}">{txt_b}</div>'
            )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_template.format(fa=file_a, fb=file_b, ins=stats['ins'], rem=stats['del'], rows="".join(rows)))
