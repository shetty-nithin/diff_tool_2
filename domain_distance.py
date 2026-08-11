import re
import numpy as np

# ============================================================
# Sensitivity parameters
# ============================================================

WARNING_SCALE = 0.05
FAILURE_SCALE = 0.02
CONTAMINATION_SCALE = 0.005

# Relative importance of each domain
WARNING_WEIGHT = 0.30
FAILURE_WEIGHT = 0.40
CONTAMINATION_WEIGHT = 0.30

# Balance between baseline NED and domain-aware distance
NED_WEIGHT = 0.50
DOMAIN_WEIGHT = 0.50


# ============================================================
# Classify individual log lines
# ============================================================

def classify_line(line):
    text = line.strip().lower()

    if not text:
        return "normal"

    # Contamination
    contamination_patterns = [
        r"\bmy name is\b",
        r"\bmy project\b",
        r"\bproject delivery\b",
        r"\bi am doing\b",
        r"\bi'm doing\b",
        r"\bthis is my work\b",
        r"\bthis is my project\b",
        r"\bdeadline\b",
        r"\bmeeting\b",
        r"\bassignment\b",
        r"\bhello\b",
        r"\btest contamination\b",
    ]

    for pattern in contamination_patterns:
        if re.search(pattern, text):
            return "contamination"

    # Failure
    failure_patterns = [
        r"\bkernel panic\b",
        r"\bpanic\b",
        r"\bout of memory\b",
        r"\boom\b",
        r"\bmemory allocation failure\b",
        r"\bfilesystem corruption\b",
        r"\bfilesystem.*corrupt",
        r"\bdriver.*failed\b",
        r"\bdriver.*failure\b",
        r"\bfailed to initialize\b",
        r"\binitialization failure\b",
        r"\bpci.*failure\b",
        r"\bpci.*enumeration.*fail",
        r"\bnetwork interface.*fail",
        r"\binterface.*failed\b",
        r"\bscsi.*fail",
        r"\busb.*fail",
        r"\bnfs.*fail",
        r"\bmce.*fail",
        r"\bcritical\b",
        r"\bemergency\b",
        r"\balert\b",
    ]

    for pattern in failure_patterns:
        if re.search(pattern, text):
            return "failure"

    # --------------------------------------------------------
    # Syslog severity
    # <0> emerg
    # <1> alert
    # <2> critical
    # <3> error
    # <4> warning
    # --------------------------------------------------------

    severity_match = re.search(r"<([0-7])>", text)

    if severity_match:
        severity = int(severity_match.group(1))

        if severity <= 3:
            return "failure"

        if severity == 4:
            return "warning"

    # Warning
    warning_patterns = [
        r"\bwarning\b",
        r"\bwarn\b",
        r"\bpebs disabled\b",
        r"\bcpu errata\b",
        r"\bunknown kernel parameter\b",
        r"\bunknown.*kernel.*param",
        r"\bno numa configuration\b",
        r"\bmicrocode mismatch\b",
        r"\bthermal warning\b",
        r"\bthermal.*warn",
        r"\bdegraded\b",
    ]

    for pattern in warning_patterns:
        if re.search(pattern, text):
            return "warning"

    return "normal"


# ============================================================
# Calculate domain composition of one log file
# ============================================================

def get_domain_signature(path):
    warning_count = 0
    failure_count = 0
    contamination_count = 0
    total = 0

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if not line.strip():
                continue

            total += 1
            category = classify_line(line)

            if category == "warning":
                warning_count += 1
            elif category == "failure":
                failure_count += 1
            elif category == "contamination":
                contamination_count += 1

    if total == 0:
        return {
            "warning": 0.0,
            "failure": 0.0,
            "contamination": 0.0,
        }

    return {
        "warning": warning_count / total,
        "failure": failure_count / total,
        "contamination": contamination_count / total,
    }


# ============================================================
# Convert raw rates into sensitive values
# ============================================================

def sensitivity(rate, scale):
    if rate <= 0.0:
        return 0.0

    return float(1.0 - np.exp(-rate / scale))


def get_sensitive_signature(signature):
    return {
        "warning": sensitivity(signature["warning"], WARNING_SCALE),
        "failure": sensitivity(signature["failure"], FAILURE_SCALE),
        "contamination": sensitivity(signature["contamination"], CONTAMINATION_SCALE),
    }


# ============================================================
# Calculate domain distance between two files
# ============================================================

def calculate_domain_distance(signature_a, signature_b):
    a = get_sensitive_signature(signature_a)
    b = get_sensitive_signature(signature_b)

    warning_distance = abs(a["warning"] - b["warning"])
    failure_distance = abs(a["failure"] - b["failure"])
    contamination_distance = abs(a["contamination"] - b["contamination"])

    domain_distance = (
        WARNING_WEIGHT * warning_distance
        + FAILURE_WEIGHT * failure_distance
        + CONTAMINATION_WEIGHT * contamination_distance
    )

    return (
        round(warning_distance, 4),
        round(failure_distance, 4),
        round(contamination_distance, 4),
        round(domain_distance, 4),
    )


# ============================================================
# Combine NED and domain-aware distance
# ============================================================

def calculate_composite_distance(ned, warning_distance, failure_distance, contamination_distance):
    domain_distance = (
        WARNING_WEIGHT * warning_distance
        + FAILURE_WEIGHT * failure_distance
        + CONTAMINATION_WEIGHT * contamination_distance
    )

    composite = (NED_WEIGHT * ned) + (DOMAIN_WEIGHT * domain_distance)

    return (
        round(domain_distance, 4),
        round(composite, 4)
    )
