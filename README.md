# NetSage AI 🌐🤖

> **AI-Assisted Network Troubleshooting System with Deterministic Rule Checking & Human-in-the-Loop Review**  
> *Built for Cisco Packet Tracer and Multi-Layer Networking Lab Scenarios*

---

## 📌 Project Overview

Junior network engineers and students frequently memorize Cisco IOS commands but struggle to isolate root causes when multi-layer faults occur (e.g., a PC gets an IP address but cannot reach a server—is it a VLAN, Gateway, Routing, ACL, NAT, DHCP, or DNS fault?).

**NetSage AI** assists network students and engineers through a 3-stage Human-in-the-Loop (HITL) pipeline:
1. **Case Inspection**: Reads **symptoms**, **topology design notes**, and **Cisco IOS `show` command outputs** across 30 structured scenarios (`dataset/cases.csv`).
2. **Deterministic Python Rule Checker (`src/checker.py`)**: Runs 6 static configuration checks using regular expressions and IPv4 prefix arithmetic to catch duplicate IPs, subnet mask mismatches, wrong default gateways, down interfaces (both prose and tabular `show ip interface brief` formats), VLAN mismatches/trunk pruning, and missing routes.
3. **Structured Google Gemini AI Diagnosis (`src/ai_diagnoser.py`)**: Combines `prompts/diagnose_prompt.md`, case evidence, and rule-checker findings to query the **Google Gemini API** (`gemini-2.5-flash` with JSON schema validation), returning `root_cause`, `confidence`, `evidence`, `next_command`, and `fix_steps`.
4. **Mandatory Human Review & Responsible AI Logging (`src/review_logger.py`)**: Requires a human reviewer to explicitly select `Accepted`, `Edited`, or `Rejected` before any remediation is approved, logging all decisions to `logs/human_reviews.csv` and all human corrections to `logs/responsible_ai_log.csv`.

---

## 📂 Project Directory Structure

```text
NetSage-AI/
├── app.py                              # Main Streamlit web application (Streamlit Cloud entrypoint)
├── requirements.txt                    # Python dependencies (streamlit, google-genai, fastapi, uvicorn, groq)
├── .env.example                        # Environment variable template with GEMINI_API_KEY placeholder
├── .gitignore                          # Excludes .env, .streamlit/secrets.toml, and virtual environments
├── .streamlit/
│   ├── config.toml                     # Streamlit dark theme & server configuration
│   └── secrets.toml.example            # Template for Streamlit secrets configuration
├── dataset/
│   └── cases.csv                       # 30 structured Packet Tracer lab cases across 8 fault domains
├── prompts/
│   └── diagnose_prompt.md              # System prompt with strict 5-key JSON schema & 3 worked examples
├── logs/
│   ├── human_reviews.csv               # Audit log of all human review decisions
│   └── responsible_ai_log.csv          # Dedicated Responsible AI log of Edited/Rejected diagnoses
├── assets/
│   └── architecture_diagram.png        # System architecture & data flow diagram
└── src/
    ├── __init__.py
    ├── checker.py                      # Deterministic rule checker (6 static checks, flags 12/30 cases)
    ├── ai_diagnoser.py                 # Google Gemini API & Groq fallback integration + JSON validator
    ├── review_logger.py                # Human review & Responsible AI CSV logger
    ├── api.py                          # Optional FastAPI REST backend (/diagnose, /review, /cases, /summary)
    └── static/
        └── index.html                  # Standalone HTML/JS frontend served when running FastAPI mode
```

---

## 🚀 Local Setup & Execution Guide

### 1. Prerequisites
- **Python 3.10+** installed.
- A **Google Gemini API Key** from [Google AI Studio](https://aistudio.google.com/).

### 2. Create & Activate a Virtual Environment
```bash
# Create virtual environment
python -m venv .venv

# Activate on Windows PowerShell:
.\.venv\Scripts\Activate.ps1

# Activate on macOS / Linux:
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Your Gemini API Key
You can provide your Gemini API key in any of three ways:

- **Option A — Streamlit Secrets (Recommended for Streamlit):**
  Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and insert your key:
  ```toml
  GEMINI_API_KEY = "YOUR_ACTUAL_GEMINI_API_KEY"
  GEMINI_MODEL_NAME = "gemini-2.5-flash"
  ```
- **Option B — Environment Variable:**
  ```bash
  # Linux / macOS
  export GEMINI_API_KEY="YOUR_ACTUAL_GEMINI_API_KEY"

  # Windows PowerShell
  $env:GEMINI_API_KEY="YOUR_ACTUAL_GEMINI_API_KEY"
  ```
- **Option C — Sidebar Input Box at Runtime:**
  Launch the app and paste your Gemini API key directly into the **🔑 Gemini API Configuration** password field in the left sidebar.

*(Note: Even if no API key is configured, the **Deterministic Rule Checker** and **Human Review Logger** work 100% offline!)*

### 5. Run the Streamlit Application (Primary Mode)
```bash
streamlit run app.py
```
Open your browser at **`http://localhost:8501`**.

### 6. Run the FastAPI Backend & Static UI (Optional REST Mode)
```bash
python -m uvicorn src.api:app --reload
```
Open your browser at **`http://127.0.0.1:8000`**.

---

## ☁️ Deploying to Streamlit Community Cloud

1. Push the contents of this folder to a GitHub repository (ensure `.streamlit/secrets.toml` and `.env` are **not** committed; `.gitignore` blocks them automatically).
2. Log in to [Streamlit Community Cloud](https://share.streamlit.io/) and click **Create app**.
3. Select your GitHub repository, branch (`main`), and set **Main file path** to:
   ```text
   app.py
   ```
4. Click **Advanced settings...** $ightarrow$ **Secrets**, and paste your Gemini API key in TOML format:
   ```toml
   GEMINI_API_KEY = "your_actual_gemini_api_key_here"
   GEMINI_MODEL_NAME = "gemini-2.5-flash"
   ```
5. Click **Save** and **Deploy!**.
