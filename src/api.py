"""
api.py — NetSage AI FastAPI Backend
-----------------------------------
Exposes REST endpoints (/diagnose, /review, /cases, /responsible-ai-log,
/summary, /health) and serves the static HTML dashboard.
"""

import os
import csv
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

try:
    from src.ai_diagnoser import diagnose_case
except ModuleNotFoundError:
    from ai_diagnoser import diagnose_case

try:
    from src.review_logger import log_review, get_review_summary, get_responsible_ai_logs
except ModuleNotFoundError:
    from review_logger import log_review, get_review_summary, get_responsible_ai_logs

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES_CSV_PATH = os.path.join(BASE_DIR, "dataset", "cases.csv")

app = FastAPI(title="NetSage AI API")


class CaseInput(BaseModel):
    case_id: str
    symptom: str
    topology_note: str
    show_outputs: str
    expected_fault: str
    osi_layer: str
    concept_tag: str
    severity: str


class ReviewInput(BaseModel):
    case_id: str
    decision: str  # Accepted, Edited, or Rejected
    ai_root_cause: str
    corrected_root_cause: Optional[str] = ""
    reviewer_notes: Optional[str] = ""


@app.post("/diagnose")
def diagnose(case: CaseInput):
    try:
        case_dict = case.model_dump() if hasattr(case, "model_dump") else case.dict()
        result = diagnose_case(case_dict)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected server error: {e}")
    return result


@app.post("/review")
def submit_review(review: ReviewInput):
    try:
        res = log_review(
            case_id=review.case_id,
            decision=review.decision,
            ai_root_cause=review.ai_root_cause,
            corrected_root_cause=review.corrected_root_cause,
            reviewer_notes=review.reviewer_notes
        )
        return res
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to log review: {e}")


@app.get("/cases")
def get_all_cases():
    if not os.path.exists(CASES_CSV_PATH):
        raise HTTPException(status_code=404, detail="dataset/cases.csv not found")
    with open(CASES_CSV_PATH, mode="r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@app.get("/responsible-ai-log")
def get_responsible_ai_log_entries():
    return get_responsible_ai_logs()


@app.get("/summary")
def get_dashboard_summary():
    return get_review_summary()


static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
def serve_dashboard():
    index_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "NetSage AI API is running. Visit /docs for API documentation."}


@app.get("/health")
def health():
    return {"status": "ok"}
