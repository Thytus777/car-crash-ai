"""Car Crash AI: Streamlit demo (internal). The primary client is frontend-next."""

import os
from datetime import date
from typing import Any

import api_client
import httpx
import streamlit as st
from api_client import ApiError, money

API_URL = os.environ.get("CAR_CRASH_API_URL", "http://localhost:8000")
# Server-side only (Streamlit runs in Python), so the key never reaches a browser.
API_KEY = os.environ.get("CAR_CRASH_API_KEY", "")

st.set_page_config(page_title="Car Crash AI", page_icon="🚗", layout="wide")
st.title("🚗 Car Crash Damage Assessment")
st.markdown("Upload photos of a damaged vehicle to get a damage report and estimate.")


@st.cache_resource
def _client() -> httpx.Client:
    headers = {"X-API-Key": API_KEY} if API_KEY else {}
    return httpx.Client(
        base_url=API_URL, headers=headers, timeout=httpx.Timeout(300.0, connect=10.0)
    )


# --- Sidebar: optional vehicle override (also used to confirm a low-confidence ID)
with st.sidebar:
    st.header("Vehicle (optional)")
    st.caption("Leave blank to let the AI identify the vehicle.")
    make = st.text_input("Make", placeholder="e.g. Toyota")
    model = st.text_input("Model", placeholder="e.g. Camry")
    year = st.number_input(
        "Year", min_value=1980, max_value=date.today().year + 1, value=None, step=1
    )

uploaded = st.file_uploader(
    "Vehicle photos (1–10)",
    type=["jpg", "jpeg", "png", "webp"],
    accept_multiple_files=True,
)
if uploaded:
    cols = st.columns(min(len(uploaded), 4))
    for i, f in enumerate(uploaded):
        cols[i % len(cols)].image(f, caption=f.name, use_container_width=True)


def _show_error(step: str, err: ApiError) -> None:
    st.error(f"{step} failed ({err.status} {err.title}): {err.detail}")
    if err.status == 429:
        st.info("The AI provider is rate-limited. Wait a few minutes and retry.")


def _render(report: dict[str, Any]) -> None:
    if report["status"] == "partial":
        st.warning(
            "Partial assessment. Some steps could not complete:\n\n"
            + "\n".join(f"- {issue['detail']}" for issue in report["issues"])
        )

    vehicle = report["vehicle"]
    st.header("🚘 Vehicle")
    v = st.columns(4)
    v[0].metric("Make", vehicle["make"])
    v[1].metric("Model", vehicle["model"])
    v[2].metric("Year", vehicle["year"])
    v[3].metric("Confidence", f"{vehicle.get('confidence', 1.0):.0%}")

    damages = report["damage_assessment"]["damages"]
    st.header(f"💥 Damage ({len(damages)} components)")
    if not damages:
        st.info("No damage detected in the assessed zones.")
    for d in damages:
        icon = "🟢" if d["severity"] <= 0.3 else "🟡" if d["severity"] <= 0.6 else "🔴"
        with st.expander(
            f"{icon} {d['component'].replace('_', ' ').title()}: "
            f"severity {d['severity']:.0%}, {d['recommendation']}"
        ):
            st.write(f"**Type:** {d['damage_type']}")
            st.write(d["description"])
            st.progress(d["severity"])

    if report["cost_estimates"]:
        st.header("💰 Estimate")
        for est in report["cost_estimates"]:
            c = st.columns(4)
            c[0].metric(
                est["component"].replace("_", " ").title(), money(est["part_cost_avg"])
            )
            c[1].metric("Labour", money(est["labor_cost"]))
            c[2].metric("Total (avg)", money(est["total_avg"]))
            c[3].metric("Source", est["pricing_method"].replace("_", " "))
        totals = report["totals"]
        t = st.columns(3)
        t[0].metric("Parts", money(totals["parts_total"]))
        t[1].metric("Labour", money(totals["labor_total"]))
        t[2].metric("Grand total", money(totals["grand_total"]))
        if totals["unpriced_components"]:
            st.caption("Excludes unpriced: " + ", ".join(totals["unpriced_components"]))

    for warning in report["assessment_warnings"]:
        st.warning(warning)
    st.caption(report["disclaimer"])
    meta = report.get("meta") or {}
    st.caption(
        f"Prompt {meta.get('prompt_version', '?')} · models: "
        f"{', '.join(meta.get('models', [])) or 'none'} · "
        f"{meta.get('input_tokens', 0)} in / {meta.get('output_tokens', 0)} out tokens"
    )
    with st.expander("Raw JSON"):
        st.json(report)


if st.button("🔍 Analyze damage", type="primary", disabled=not uploaded):
    client = _client()
    with st.spinner("Uploading…"):
        try:
            files = [
                (f.name, f.getvalue(), f.type or "application/octet-stream")
                for f in uploaded
            ]
            st.session_state["upload_id"] = api_client.upload(client, files)[
                "upload_id"
            ]
        except ApiError as err:
            _show_error("Upload", err)
            st.stop()

    with st.spinner("Analysing (this can take a minute)…"):
        try:
            result = api_client.analyze(
                client,
                st.session_state["upload_id"],
                make=make or None,
                model=model or None,
                year=int(year) if year else None,
            )
        except ApiError as err:
            _show_error("Analysis", err)
            st.stop()

    if result.get("status") == "vehicle_confirmation_needed":
        guess = result["vehicle_guess"]
        st.warning(result["message"])
        st.info(
            f"Best guess: **{guess['year']} {guess['make']} {guess['model']}**. "
            "Enter the correct make, model and year in the sidebar and run again."
        )
    else:
        _render(result)
