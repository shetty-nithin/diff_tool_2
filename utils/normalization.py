import re

def normalize_line(line: str) -> str:
    # 1. Remove ANSI escape codes (already in your code)
    line = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', line)

    # 2. Syslog Priorities (e.g., <5>1, <12>1) [cite: 328, 1090]
    line = re.sub(r'<\d+>\d+', '<PRI>', line)

    # 3. ISO/System Timestamps (e.g., 2021-01-18T09:02:24.766+00:00) [cite: 328]
    line = re.sub(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}(?:\+\d{2}:\d{2})?', '<TS>', line)
    
    # 4. Standard Date Timestamps (e.g., 2023-12-01 14:23:10) [cite: 2434]
    line = re.sub(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', '<TS>', line)

    # 5. Kernel Uptime Timestamps (e.g., [ 0.000000]) [cite: 328]
    line = re.sub(r'\[\s*\d+\.\d+\s*\]', '[<TIME>]', line)

    # 6. Memory Ranges and Hex Addresses (e.g., [mem 0x...-0x...]) 
    line = re.sub(r'0x[0-9a-fA-F]+', '<HEX>', line)
    
    # 7. IPv4 Addresses and Subnets (e.g., 10.255.2.61/18) [cite: 1884, 887]
    line = re.sub(r'\b(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?\b', '<IP>', line)

    # 8. File Paths (e.g., /public/user/testbench/...) [cite: 2452]
    # Targets strings starting with / that look like paths
    line = re.sub(r'/(?:[\w.-]+/)+[\w.-]*', '<PATH>', line)

    # 9. Hardware IDs (e.g., [8086:1502] or system 00:06) [cite: 744, 71]
    line = re.sub(r'\[[0-9a-fA-F]{4}:[0-9a-fA-F]{4}\]', '[<HWID>]', line)
    line = re.sub(r'\b\d{2}:\d{2}\b', '<ID>', line)

    # 10. Process IDs & Generic Bracketed IDs [cite: 197, 2434]
    line = re.sub(r'\b(pid|tid|thread|handle)[:=]?\s*\d+\b', r'\1:<ID>', line, flags=re.IGNORECASE)
    line = re.sub(r'\[\d+\]', '[<ID>]', line)

    # 11. Leading List/Step Numbers (e.g., " 1. Comment:" or " 1. Step:") [cite: 2434, 2452]
    line = re.sub(r'^\s*\d+\.\s*(?:comment|step)?[:\s]*', '', line, flags=re.IGNORECASE)

    # 12. Normalize Whitespace and Case
    line = re.sub(r'\s+', ' ', line).strip()
    line = line.lower()

    return line
