"""
ai_diagnoser.py — NetSage AI
-----------------------------
Sends one troubleshooting case (plus deterministic rule-checker findings)
to Google Gemini API (supporting both standard AIza... AI Studio keys and
AQ... Vertex AI Express Mode / Authorization keys, plus Groq fallback)
and returns a strict JSON diagnosis.
A human reviewer always verifies the diagnosis before remediation is accepted.
"""

import os
import csv
import json
import re
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

try:
    from src.checker import run_rule_checker
except ModuleNotFoundError:
    from checker import run_rule_checker

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Fields the AI's JSON reply must contain.
REQUIRED_FIELDS = [
    "root_cause",
    "confidence",
    "evidence",
    "next_command",
    "fix_steps",
]

# Valid confidence values.
VALID_CONFIDENCE_VALUES = ["high", "medium", "low"]

PROMPT_PATH = os.path.join(BASE_DIR, "prompts", "diagnose_prompt.md")
CASES_CSV_PATH = os.path.join(BASE_DIR, "dataset", "cases.csv")

# Default models
GEMINI_MODEL_NAME = os.environ.get("GEMINI_MODEL_NAME", "gemini-3.6-flash")
GROQ_MODEL_NAME = os.environ.get("GROQ_MODEL_NAME", "openai/gpt-oss-120b")

# Secure configuration placeholder (User replaces with actual key in .streamlit/secrets.toml, .env, or UI)
API_KEY_PLACEHOLDER = "YOUR_GEMINI_API_KEY_HERE"


def _clean_key_string(val: Optional[str]) -> str:
    """Strips whitespace and accidental surrounding quotes from a key string."""
    if not val:
        return ""
    cleaned = str(val).strip()
    if (cleaned.startswith('"') and cleaned.endswith('"')) or (cleaned.startswith("'") and cleaned.endswith("'")):
        cleaned = cleaned[1:-1].strip()
    return cleaned


def get_configured_api_key(explicit_key: Optional[str] = None, key_name: str = "GEMINI_API_KEY") -> Optional[str]:
    """
    Securely resolves the API key in order of priority:
    1. Explicit key passed at runtime (e.g., from Streamlit sidebar input)
    2. Streamlit secrets (st.secrets[key_name] or GOOGLE_API_KEY / VERTEX_AI_KEY)
    3. Environment variables (os.environ[key_name])
    Returns None if unset or still equal to a placeholder string.
    """
    placeholders = {
        "",
        API_KEY_PLACEHOLDER.lower(),
        "your_gemini_api_key_here",
        "your_actual_gemini_api_key_here",
        "your_groq_api_key_here",
        "your_actual_groq_api_key_here",
        "paste_your_api_key_here",
    }

    cand = _clean_key_string(explicit_key)
    if cand and cand.lower() not in placeholders:
        return cand

    alias_names = [key_name]
    if key_name == "GEMINI_API_KEY":
        alias_names.extend(["GOOGLE_API_KEY", "VERTEX_AI_KEY", "GOOGLE_CLOUD_API_KEY"])

    # Check Streamlit secrets safely if running inside Streamlit
    try:
        import streamlit as st
        if hasattr(st, "secrets"):
            for k in alias_names:
                if k in st.secrets:
                    secret_val = _clean_key_string(st.secrets[k])
                    if secret_val and secret_val.lower() not in placeholders:
                        return secret_val
    except Exception:
        pass

    # Check OS environment variables
    for k in alias_names:
        env_val = _clean_key_string(os.environ.get(k, ""))
        if env_val and env_val.lower() not in placeholders:
            return env_val

    return None


def load_prompt_template(path: str = PROMPT_PATH) -> str:
    """Read the base instructions for the AI."""
    if not os.path.exists(path):
        alt_path = os.path.join(BASE_DIR, path)
        if os.path.exists(alt_path):
            path = alt_path
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def build_user_message(case: dict, checker_result: dict) -> str:
    """Turn the case and checker findings into text for the model."""
    findings_text = "\n".join(
        f"- Rule: {item['rule']} | "
        f"Status: {item['status']} | "
        f"Details: {item['details']}"
        for item in checker_result.get("flagged_rules", [])
    ) or "None"

    return (
        f"Case ID: {case.get('case_id')}\n"
        f"Symptom: {case.get('symptom')}\n"
        f"Topology note: {case.get('topology_note')}\n"
        f"Show outputs: {case.get('show_outputs')}\n"
        f"Concept tag: {case.get('concept_tag')}\n"
        f"Severity: {case.get('severity')}\n\n"
        f"Rule checker matches found: "
        f"{checker_result.get('rule_matches_found')}\n"
        f"Rule checker findings:\n{findings_text}\n\n"
        "Respond with ONLY a JSON object with exactly these keys: "
        "root_cause, confidence, evidence, next_command, fix_steps. "
        "The 'confidence' value must be exactly one of: "
        "high, medium, low."
    )


def parse_ai_response(raw_text: str) -> dict:
    """
    Parse the model's reply as JSON (stripping optional markdown code fences if present)
    and validate all required fields.
    """
    cleaned = (raw_text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if match:
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError as e:
                raise ValueError(f"AI response was not valid JSON: {e}")
        else:
            raise ValueError("AI response was not valid JSON.")

    missing = [field for field in REQUIRED_FIELDS if field not in data]
    if missing:
        raise ValueError(f"AI response is missing required fields: {missing}")

    confidence = str(data.get("confidence", "")).strip().lower()
    if confidence not in VALID_CONFIDENCE_VALUES:
        raise ValueError(
            f"Invalid confidence value: {data.get('confidence')!r}. "
            f"Must be one of {VALID_CONFIDENCE_VALUES}."
        )

    data["confidence"] = confidence
    return data


def _rest_call_vertex_express(full_prompt: str, api_key: str, model_name: str) -> str:
    """
    Calls the Google Cloud Vertex AI Express Mode REST endpoint (`aiplatform.googleapis.com`),
    which is required for API keys prefixed with `AQ.` (Express Mode / Bound Authorization Keys).
    """
    url = f"https://aiplatform.googleapis.com/v1/publishers/google/models/{model_name}:generateContent"
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": full_prompt}],
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        return body["candidates"][0]["content"]["parts"][0]["text"]


def _rest_call_ai_studio(full_prompt: str, api_key: str, model_name: str) -> str:
    """
    Calls the standard Google AI Studio Gemini Developer API REST endpoint (`generativelanguage.googleapis.com`),
    used for traditional `AIzaSy...` API keys.
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": full_prompt}],
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        return body["candidates"][0]["content"]["parts"][0]["text"]


def _call_gemini_api(full_prompt: str, api_key: str, model_name: str = GEMINI_MODEL_NAME) -> str:
    """
    Smart multi-path caller for Google Gemini:
    - Automatically detects whether `api_key` is a Vertex AI Express Mode key (`AQ....`)
      or a standard AI Studio key (`AIza...`).
    - Tries the matching `google-genai` SDK mode (`vertexai=True` vs `vertexai=False`) first,
      then falls back to direct REST requests across both `aiplatform.googleapis.com` and
      `generativelanguage.googleapis.com` so neither `ACCESS_TOKEN_TYPE_UNSUPPORTED` nor
      SDK version mismatches can block diagnosis.
    """
    is_aq_key = api_key.startswith("AQ.")
    errors = []

    # 1. Try google-genai SDK with the appropriate vertexai flag first
    try:
        from google import genai
        from google.genai import types

        sdk_modes = [True, False] if is_aq_key else [False, True]
        for use_vertex in sdk_modes:
            try:
                client = genai.Client(vertexai=use_vertex, api_key=api_key)
                response = client.models.generate_content(
                    model=model_name,
                    contents=full_prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.2,
                        response_mime_type="application/json",
                    ),
                )
                if response and getattr(response, "text", None):
                    return response.text
            except Exception as sdk_err:
                errors.append(f"SDK(vertexai={use_vertex}): {sdk_err}")
    except ImportError:
        pass

    # 2. Try direct HTTPS REST endpoints (Vertex AI Express Mode + AI Studio)
    rest_callers = (
        [("Vertex Express REST", _rest_call_vertex_express), ("AI Studio REST", _rest_call_ai_studio)]
        if is_aq_key
        else [("AI Studio REST", _rest_call_ai_studio), ("Vertex Express REST", _rest_call_vertex_express)]
    )

    for label, fn in rest_callers:
        try:
            text = fn(full_prompt, api_key, model_name)
            if text:
                return text
        except urllib.error.HTTPError as he:
            err_body = he.read().decode("utf-8", errors="replace")
            errors.append(f"{label} HTTP {he.code}: {err_body}")
        except Exception as rest_err:
            errors.append(f"{label}: {rest_err}")

    raise RuntimeError(" | ".join(errors))


def _call_groq_api(full_prompt: str, api_key: str, model_name: str = GROQ_MODEL_NAME) -> str:
    """Calls Groq API as secondary fallback if configured."""
    from groq import Groq
    client = Groq(api_key=api_key)
    response = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": full_prompt}],
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content


def diagnose_case(
    case: dict,
    api_key: Optional[str] = None,
    provider: str = "gemini",
    model_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Runs the deterministic rule checker first, then invokes Gemini API (or Groq fallback)
    and returns a validated JSON diagnosis dictionary.
    """
    # 1. Run deterministic rule checker first (always succeeds offline).
    checker_result = run_rule_checker(case)

    # 2. Resolve API credentials.
    gemini_key = get_configured_api_key(api_key if provider == "gemini" else None, "GEMINI_API_KEY")
    groq_key = get_configured_api_key(api_key if provider == "groq" else None, "GROQ_API_KEY")

    active_provider = provider.lower()
    if active_provider == "gemini" and not gemini_key and groq_key:
        active_provider = "groq"
    elif active_provider == "groq" and not groq_key and gemini_key:
        active_provider = "gemini"

    if active_provider == "gemini" and not gemini_key:
        return {
            "status": "error",
            "error": (
                "No valid Gemini API key is configured. If you put 'YOUR_GEMINI_API_KEY_HERE' in "
                ".streamlit/secrets.toml or .env, replace it with your real key (or paste your key "
                "into the Sidebar box on the left)."
            ),
            "provider": "gemini",
            "checker_result": checker_result,
        }

    if active_provider == "groq" and not groq_key:
        return {
            "status": "error",
            "error": "GROQ_API_KEY environment variable is not set.",
            "provider": "groq",
            "checker_result": checker_result,
        }

    # 3. Load the AI prompt template.
    try:
        prompt_template = load_prompt_template()
    except OSError as e:
        return {
            "status": "error",
            "error": f"Could not read prompt template: {e}",
            "provider": active_provider,
            "checker_result": checker_result,
        }

    # 4. Build the complete prompt.
    user_message = build_user_message(case, checker_result)
    full_prompt = f"{prompt_template}\n\n{user_message}"

    # 5. Call the selected AI provider.
    try:
        if active_provider == "gemini":
            chosen_model = model_name or GEMINI_MODEL_NAME
            raw_text = _call_gemini_api(full_prompt, gemini_key, chosen_model)
        else:
            chosen_model = model_name or GROQ_MODEL_NAME
            raw_text = _call_groq_api(full_prompt, groq_key, chosen_model)
    except Exception as e:
        return {
            "status": "error",
            "error": f"{active_provider.capitalize()} API call failed: {e}",
            "provider": active_provider,
            "checker_result": checker_result,
        }

    # 6. Parse and validate AI response.
    try:
        diagnosis = parse_ai_response(raw_text)
    except ValueError as e:
        return {
            "status": "error",
            "error": str(e),
            "provider": active_provider,
            "checker_result": checker_result,
        }

    # 7. Return successful result.
    return {
        "status": "ok",
        "provider": active_provider,
        "model": chosen_model,
        "diagnosis": diagnosis,
        "checker_result": checker_result,
    }


def load_first_case(path: str = CASES_CSV_PATH) -> dict:
    """Read the first real case from cases.csv."""
    if not os.path.exists(path):
        path = os.path.join(BASE_DIR, "dataset", "cases.csv")
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            return row
    raise ValueError(f"No rows found in {path}")


if __name__ == "__main__":
    case = load_first_case()
    result = diagnose_case(case)
    print(json.dumps(result, indent=2))
