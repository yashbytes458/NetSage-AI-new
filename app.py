"""
app.py — NetSage AI Streamlit Application
-----------------------------------------
Entrypoint for local Streamlit execution (`streamlit run app.py`) and
Streamlit Community Cloud deployment. Integrates:
1. 30-Case Cisco Packet Tracer Troubleshooting Dataset (`dataset/cases.csv`)
2. Deterministic 6-Rule Python Configuration Checker (`src/checker.py`)
3. Google Gemini API Structured JSON Diagnosis (`src/ai_diagnoser.py`) with secure key placeholder
4. Mandatory Human-in-the-Loop (HITL) Review & Responsible AI Audit Logger (`src/review_logger.py`)
5. Live Analytics & Dataset Distribution Dashboard
"""

import os
import csv
from collections import Counter
import streamlit as st

from src.checker import run_rule_checker
from src.ai_diagnoser import (
    diagnose_case,
    get_configured_api_key,
    GEMINI_MODEL_NAME,
    API_KEY_PLACEHOLDER,
)
from src.review_logger import (
    log_review,
    get_review_summary,
    get_responsible_ai_logs,
    get_all_reviews,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CASES_CSV_PATH = os.path.join(BASE_DIR, "dataset", "cases.csv")
ARCH_IMG_PATH = os.path.join(BASE_DIR, "assets", "architecture_diagram.png")

st.set_page_config(
    page_title="NetSage AI — Network Troubleshooting Assistant",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom styling for dark terminal boxes and metric cards
st.markdown(
    """
    <style>
    .terminal-card {
        background-color: #0B0F17;
        color: #E2E8F0;
        border: 1px solid #1E293B;
        border-radius: 8px;
        padding: 12px 14px;
        font-family: 'JetBrains Mono', 'Courier New', monospace;
        font-size: 0.86rem;
        white-space: pre-wrap;
        line-height: 1.5;
        margin-bottom: 10px;
    }
    .symptom-card {
        background-color: #1E293B;
        color: #FCD34D;
        border-left: 4px solid #F59E0B;
        border-radius: 6px;
        padding: 10px 14px;
        font-size: 0.92rem;
        margin-bottom: 10px;
    }
    .topology-card {
        background-color: #0F172A;
        color: #93C5FD;
        border-left: 4px solid #0EA5E9;
        border-radius: 6px;
        padding: 10px 14px;
        font-size: 0.92rem;
        margin-bottom: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def load_all_cases():
    """Loads all 30 network troubleshooting cases from dataset/cases.csv."""
    if not os.path.exists(CASES_CSV_PATH):
        return []
    with open(CASES_CSV_PATH, mode="r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    cases = load_all_cases()
    summary = get_review_summary()
    counts = summary.get("counts", {"Total": 0, "Accepted": 0, "Edited": 0, "Rejected": 0})
    agreement_pct = summary.get("agreement_rate_percent", 0.0)

    # ── SIDEBAR: Secure Gemini API Configuration & Case Filter ──
    with st.sidebar:
        st.title("🌐 NetSage AI")
        st.caption("AI-Assisted Packet Tracer Troubleshooter with Human-in-the-Loop Review")
        st.divider()

        st.subheader("🔑 Gemini API Configuration")
        preconfigured_gemini = get_configured_api_key(None, "GEMINI_API_KEY")
        sidebar_key = st.text_input(
            "Enter / Override Gemini API Key:",
            value="",
            type="password",
            placeholder="Paste AIza... or AQ... key here",
            help="Supports both standard Google AI Studio keys (AIza...) and Google Cloud Vertex AI Express Mode keys (AQ...).",
        )
        active_api_key = get_configured_api_key(sidebar_key, "GEMINI_API_KEY") or preconfigured_gemini

        if active_api_key:
            key_mode = "Vertex AI Express Mode (`AQ...`)" if active_api_key.startswith("AQ.") else "Google AI Studio (`AIza...`)"
            masked = f"{active_api_key[:6]}...{active_api_key[-4:]}" if len(active_api_key) > 12 else "Configured"
            st.success(f"✓ Active Key: `{masked}`\nMode: {key_mode}")
        else:
            st.warning(
                "No valid API key detected yet. Paste your `AQ...` or `AIza...` key in the box above or in `.streamlit/secrets.toml`."
            )

        model_choice = st.selectbox(
            "Gemini Model:",
            options=["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro","gemini-3.6-flash"],
            index=0,
        )

        st.divider()
        st.subheader("🔍 Filter Lab Cases")
        osi_options = ["All Layers"] + sorted(list({c["osi_layer"] for c in cases}))
        selected_osi = st.selectbox("OSI Layer:", osi_options)

        sev_options = ["All Severities", "High", "Medium", "Low"]
        selected_sev = st.selectbox("Severity:", sev_options)

        filtered_cases = [
            c for c in cases
            if (selected_osi == "All Layers" or c["osi_layer"] == selected_osi)
            and (selected_sev == "All Severities" or c["severity"] == selected_sev)
        ]
        st.caption(f"Showing **{len(filtered_cases)}** of **{len(cases)}** lab cases")

    # ── TOP HEADER & LIVE KPI METRICS ──
    st.markdown("## 🌐 NetSage AI — Network Troubleshooting Assistant")
    st.markdown(
        "**Hybrid Deterministic Rule Checker + Google Gemini AI Diagnosis with Mandatory Human-in-the-Loop Verification**"
    )

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Dataset Cases", len(cases))
    m2.metric("Total Reviewed", counts.get("Total", 0))
    m3.metric("Accepted Fixes", counts.get("Accepted", 0))
    m4.metric("Edited / Corrected", counts.get("Edited", 0) + counts.get("Rejected", 0))
    m5.metric("AI-Human Agreement", f"{agreement_pct}%")

    tab_diag, tab_analytics, tab_logs, tab_arch = st.tabs([
        "🩺 Interactive Lab Diagnosis & Review",
        "📊 Dataset & Rule Checker Analytics",
        "🛡️ Responsible AI Audit Logs",
        "🏗️ System Architecture & Prompt Schema",
    ])

    # =========================================================================
    # TAB 1: INTERACTIVE LAB DIAGNOSIS & HUMAN REVIEW
    # =========================================================================
    with tab_diag:
        if not filtered_cases:
            st.warning("No cases match the selected sidebar filters. Reset the filters to view cases.")
        else:
            col_left, col_right = st.columns([1.1, 1.0], gap="large")

            with col_left:
                st.subheader("1. Select Lab Troubleshooting Case")
                case_labels = {
                    c["case_id"]: f"[{c['case_id']}] {c['concept_tag']} ({c['severity']}) — {c['symptom'][:55]}..."
                    for c in filtered_cases
                }
                selected_case_id = st.selectbox(
                    "Choose Case:",
                    options=list(case_labels.keys()),
                    format_func=lambda cid: case_labels[cid],
                )
                current_case = next(c for c in filtered_cases if c["case_id"] == selected_case_id)

                # Clear previous diagnosis if user switches case
                if st.session_state.get("last_case_id") != selected_case_id:
                    st.session_state["last_case_id"] = selected_case_id
                    st.session_state["latest_result"] = None

                c_info1, c_info2, c_info3 = st.columns(3)
                c_info1.info(f"**Case ID:** `{current_case['case_id']}`")
                c_info2.info(f"**OSI Layer:** {current_case['osi_layer']}")
                c_info3.warning(f"**Severity:** {current_case['severity']}")

                st.markdown(f"**Concept Tag:** `{current_case['concept_tag']}`")

                st.markdown("**Reported Symptom:**")
                st.markdown(f"<div class='symptom-card'>{current_case['symptom']}</div>", unsafe_allow_html=True)

                st.markdown("**Topology Design Note:**")
                st.markdown(f"<div class='topology-card'>{current_case['topology_note']}</div>", unsafe_allow_html=True)

                st.markdown("**Device `show` Command Outputs:**")
                st.markdown(f"<div class='terminal-card'>{current_case['show_outputs']}</div>", unsafe_allow_html=True)

                with st.expander("📖 View Ground-Truth Expected Fault (Reference Benchmark)"):
                    st.write(current_case["expected_fault"])

                col_btn1, col_btn2 = st.columns(2)
                if col_btn1.button("⚡ Run Full Diagnosis (Rule Checker + Gemini AI)", type="primary", use_container_width=True):
                    with st.spinner(f"Running deterministic checks and querying {model_choice}..."):
                        st.session_state["latest_result"] = diagnose_case(
                            current_case,
                            api_key=active_api_key,
                            provider="gemini",
                            model_name=model_choice,
                        )

                if col_btn2.button("🔍 Run Deterministic Rule Checker Only (Offline)", use_container_width=True):
                    checker_only = run_rule_checker(current_case)
                    st.session_state["latest_result"] = {
                        "status": "checker_only",
                        "checker_result": checker_only,
                        "diagnosis": None,
                    }

            with col_right:
                st.subheader("2. NetSage AI Diagnosis & Rule Results")
                result = st.session_state.get("latest_result")

                if not result:
                    st.info("Select a case on the left and click **⚡ Run Full Diagnosis** or **🔍 Run Deterministic Rule Checker Only**.")
                else:
                    checker = result.get("checker_result", {})
                    flagged = checker.get("flagged_rules", [])

                    st.markdown("#### A. Python Deterministic Rule Checker (`src/checker.py`)")
                    if flagged:
                        for f_rule in flagged:
                            st.warning(f"⚠️ **{f_rule['rule']}**: {f_rule['details']}")
                    else:
                        st.success("✓ **No static syntax rule flagged**: Fault requires semantic/multi-layer inspection.")

                    with st.expander("View All 6 Deterministic Rule Check Statuses"):
                        st.table([
                            {
                                "Rule Name": r["rule"],
                                "Status": r["status"],
                                "Diagnostic Details": r["details"],
                            }
                            for r in checker.get("all_checks", [])
                        ])

                    st.markdown("#### B. Gemini AI Structured Diagnosis (`src/ai_diagnoser.py`)")
                    diag = result.get("diagnosis")
                    if result.get("status") == "ok" and diag:
                        conf = diag.get("confidence", "medium").upper()
                        if conf == "HIGH":
                            st.success(f"**Confidence Level:** {conf}  |  **Model:** `{result.get('model', model_choice)}`")
                        elif conf == "MEDIUM":
                            st.warning(f"**Confidence Level:** {conf}  |  **Model:** `{result.get('model', model_choice)}`")
                        else:
                            st.error(f"**Confidence Level:** {conf}  |  **Model:** `{result.get('model', model_choice)}`")

                        st.markdown("**AI Identified Root Cause:**")
                        st.info(diag.get("root_cause", "—"))

                        st.markdown("**Cited CLI / Topology Evidence:**")
                        st.markdown(f"<div class='terminal-card'>{diag.get('evidence', '—')}</div>", unsafe_allow_html=True)

                        st.markdown(f"**Next Recommended Verification Command:** `{diag.get('next_command', 'show running-config')}`")

                        st.markdown("**Evidence-Backed Remediation Steps:**")
                        st.code(diag.get("fix_steps", "—"), language="bash")

                    elif result.get("status") == "checker_only":
                        st.info("Ran in **Deterministic Checker Only** mode. Click **⚡ Run Full Diagnosis** with a configured Gemini API key to invoke LLM root-cause synthesis.")
                    else:
                        st.error(f"**AI Diagnosis Notice:** {result.get('error', 'Unknown error')}")
                        st.caption("Deterministic rule-checker findings above remain fully available for human review.")

                    # ── MANDATORY HUMAN-IN-THE-LOOP REVIEW PANEL ──
                    st.divider()
                    st.subheader("3. Mandatory Human Review & Verification (HITL)")
                    st.caption(
                        "Every decision is logged to `logs/human_reviews.csv`. Choosing **Edited** or **Rejected** also records an entry in `logs/responsible_ai_log.csv`."
                    )

                    default_ai_cause = (
                        diag.get("root_cause")
                        if diag and diag.get("root_cause")
                        else (
                            f"{flagged[0]['rule']}: {flagged[0]['details']}"
                            if flagged
                            else f"Manual inspection of {current_case['case_id']} ({current_case['concept_tag']})"
                        )
                    )

                    with st.form(key=f"review_form_{current_case['case_id']}"):
                        decision = st.radio(
                            "Review Decision:",
                            options=["Accepted", "Edited", "Rejected"],
                            horizontal=True,
                        )
                        corrected_cause = st.text_area(
                            "Corrected Root Cause & Fix (Required if Editing or Rejecting):",
                            value=default_ai_cause if decision == "Edited" else "",
                            placeholder="Specify the refined root cause, VLAN names, or exact Cisco IOS fix commands...",
                        )
                        reviewer_notes = st.text_input(
                            "Reviewer Notes / Verification Rationale:",
                            placeholder="e.g., Verified against topology and switchport output; remediation commands are accurate.",
                        )
                        submitted = st.form_submit_button("💾 Submit Human Review Decision to Audit Log", use_container_width=True)

                        if submitted:
                            try:
                                res_log = log_review(
                                    case_id=current_case["case_id"],
                                    decision=decision,
                                    ai_root_cause=default_ai_cause,
                                    corrected_root_cause=corrected_cause,
                                    reviewer_notes=reviewer_notes,
                                )
                                st.success(
                                    f"✓ Logged **{res_log['decision']}** decision for `{res_log['case_id']}` at `{res_log['timestamp']}`."
                                )
                                if res_log["logged_to_responsible_ai"]:
                                    st.warning("🛡️ Correction recorded in `logs/responsible_ai_log.csv`.")
                                st.rerun()
                            except Exception as exc:
                                st.error(f"Failed to record review: {exc}")

    # =========================================================================
    # TAB 2: DATASET & DETERMINISTIC RULE CHECKER ANALYTICS
    # =========================================================================
    with tab_analytics:
        st.subheader("📊 30-Case Dataset & Deterministic Rule Checker Benchmark")
        st.write(
            "Below is the live evaluation of `src/checker.py` across all 30 Cisco Packet Tracer troubleshooting scenarios in `dataset/cases.csv`."
        )

        checker_rows = []
        rule_counter = Counter()
        layer_counter = Counter()
        flagged_total = 0

        for c in cases:
            layer_counter[c["osi_layer"]] += 1
            res = run_rule_checker(c)
            if res["rule_matches_found"]:
                flagged_total += 1
                rules_str = ", ".join(r["rule"] for r in res["flagged_rules"])
                details_str = "; ".join(r["details"] for r in res["flagged_rules"])
                for r in res["flagged_rules"]:
                    rule_counter[r["rule"]] += 1
            else:
                rules_str = "NOT_FLAGGED (Requires LLM / Manual)"
                details_str = "—"

            checker_rows.append({
                "Case ID": c["case_id"],
                "OSI Layer": c["osi_layer"],
                "Severity": c["severity"],
                "Concept Tag": c["concept_tag"],
                "Checker Flag(s)": rules_str,
                "Deterministic Evidence Details": details_str,
            })

        a1, a2, a3 = st.columns(3)
        a1.metric("Total Lab Cases", len(cases))
        a2.metric("Cases Flagged Deterministically", f"{flagged_total} / {len(cases)} ({flagged_total/len(cases)*100:.1f}%)")
        a3.metric("Distinct OSI Layers Covered", len(layer_counter))

        col_c1, col_c2 = st.columns(2)
        with col_c1:
            st.markdown("#### Cases by OSI Reference Layer")
            st.bar_chart(dict(layer_counter))
        with col_c2:
            st.markdown("#### Triggered Deterministic Rule Counts")
            st.bar_chart(dict(rule_counter))

        st.markdown("#### Complete 30-Case Deterministic Verification Table")
        st.dataframe(checker_rows, use_container_width=True, hide_index=True)

    # =========================================================================
    # TAB 3: RESPONSIBLE AI & HUMAN REVIEW AUDIT LOGS
    # =========================================================================
    with tab_logs:
        st.subheader("🛡️ Responsible AI Discrepancy Log (`logs/responsible_ai_log.csv`)")
        st.caption("Captures all instances where a human engineer edited or rejected an AI diagnosis.")
        rai_logs = get_responsible_ai_logs()
        if rai_logs:
            st.dataframe(rai_logs, use_container_width=True, hide_index=True)
        else:
            st.info("No human corrections logged yet.")

        st.divider()
        st.subheader("📋 Complete Human Review History (`logs/human_reviews.csv`)")
        all_revs = get_all_reviews()
        if all_revs:
            st.dataframe(all_revs, use_container_width=True, hide_index=True)
        else:
            st.info("No human reviews logged yet.")

    # =========================================================================
    # TAB 4: SYSTEM ARCHITECTURE & PROMPT SCHEMA
    # =========================================================================
    with tab_arch:
        st.subheader("🏗️ NetSage AI Architecture & Component Flow")
        if os.path.exists(ARCH_IMG_PATH):
            st.image(ARCH_IMG_PATH, caption="NetSage AI Hybrid Rule-Checking, Gemini LLM, and Human-in-the-Loop Architecture", use_container_width=True)

        st.markdown("#### Engineered System Prompt (`prompts/diagnose_prompt.md`)")
        prompt_file = os.path.join(BASE_DIR, "prompts", "diagnose_prompt.md")
        if os.path.exists(prompt_file):
            with open(prompt_file, "r", encoding="utf-8") as f:
                st.code(f.read(), language="markdown")


if __name__ == "__main__":
    main()
