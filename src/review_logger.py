"""
review_logger.py — NetSage AI Human Review & Audit Logging
----------------------------------------------------------
Records genuine human review decisions (Accepted, Edited, Rejected)
and logs cases where the AI diagnosis was corrected by a human.
"""

import os
import csv
from datetime import datetime
from typing import Dict, Any, Optional, List

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.path.join(BASE_DIR, "logs")
REVIEWS_CSV_PATH = os.path.join(LOGS_DIR, "human_reviews.csv")
RESPONSIBLE_AI_CSV_PATH = os.path.join(LOGS_DIR, "responsible_ai_log.csv")

VALID_DECISIONS = ["Accepted", "Edited", "Rejected"]


def init_log_files():
    """Ensures CSV files with proper headers exist in logs/ directory."""
    os.makedirs(LOGS_DIR, exist_ok=True)

    if not os.path.exists(REVIEWS_CSV_PATH):
        with open(REVIEWS_CSV_PATH, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["case_id", "decision", "ai_root_cause", "corrected_root_cause", "reviewer_notes", "timestamp"])

    if not os.path.exists(RESPONSIBLE_AI_CSV_PATH):
        with open(RESPONSIBLE_AI_CSV_PATH, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["case_id", "decision", "ai_root_cause", "human_corrected_root_cause", "reason_for_correction", "timestamp"])


def log_review(
    case_id: str,
    decision: str,
    ai_root_cause: str,
    corrected_root_cause: Optional[str] = "",
    reviewer_notes: Optional[str] = ""
) -> Dict[str, Any]:
    """
    Records one human review entry.
    - If decision is 'Edited' or 'Rejected', also logs to responsible_ai_log.csv.
    """
    init_log_files()

    normalized_decision = decision.strip().capitalize()
    if normalized_decision not in VALID_DECISIONS:
        raise ValueError(f"Invalid decision: '{decision}'. Must be one of {VALID_DECISIONS}")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    corrected_cause = (corrected_root_cause or "").strip()
    notes = (reviewer_notes or "").strip()

    # 1. Append to general reviews log
    with open(REVIEWS_CSV_PATH, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([case_id, normalized_decision, ai_root_cause, corrected_cause, notes, timestamp])

    # 2. If the AI diagnosis was edited or rejected, append to Responsible AI audit log
    if normalized_decision in ["Edited", "Rejected"]:
        with open(RESPONSIBLE_AI_CSV_PATH, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([case_id, normalized_decision, ai_root_cause, corrected_cause, notes, timestamp])

    return {
        "status": "ok",
        "case_id": case_id,
        "decision": normalized_decision,
        "timestamp": timestamp,
        "logged_to_responsible_ai": normalized_decision in ["Edited", "Rejected"]
    }


def get_all_reviews() -> List[Dict[str, str]]:
    """Returns all rows from logs/human_reviews.csv."""
    init_log_files()
    if os.path.exists(REVIEWS_CSV_PATH):
        with open(REVIEWS_CSV_PATH, mode="r", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    return []


def get_review_summary() -> Dict[str, Any]:
    """Returns statistics on all human reviews logged so far."""
    init_log_files()
    counts = {"Accepted": 0, "Edited": 0, "Rejected": 0, "Total": 0}

    if os.path.exists(REVIEWS_CSV_PATH):
        with open(REVIEWS_CSV_PATH, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                dec = row.get("decision", "").capitalize()
                if dec in counts:
                    counts[dec] += 1
                counts["Total"] += 1

    agreement_rate = (counts["Accepted"] / counts["Total"] * 100) if counts["Total"] > 0 else 0.0
    return {
        "counts": counts,
        "agreement_rate_percent": round(agreement_rate, 2)
    }


def get_responsible_ai_logs() -> List[Dict[str, str]]:
    """Returns all rows from logs/responsible_ai_log.csv."""
    init_log_files()
    if os.path.exists(RESPONSIBLE_AI_CSV_PATH):
        with open(RESPONSIBLE_AI_CSV_PATH, mode="r", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    return []
