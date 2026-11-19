"""Car Crash AI — Streamlit Frontend"""

import httpx
import streamlit as st

API_BASE = "http://localhost:8000/api/v1"

st.set_page_config(page_title="Car Crash AI", page_icon="🚗", layout="wide")
st.title("🚗 Car Crash Damage Assessment")
st.markdown("Upload photos of your damaged vehicle to get an AI-powered damage report and cost estimate.")

# --- Sidebar: Vehicle Info Override ---
with st.sidebar:
    st.header("Vehicle Info (Optional)")
    st.caption("Leave blank to let AI identify the vehicle automatically.")
    override_make = st.text_input("Make", placeholder="e.g. Toyota")
    override_model = st.text_input("Model", placeholder="e.g. Camry")
    override_year = st.number_input("Year", min_value=1990, max_value=2026, value=None, step=1)

# --- Image Upload ---
uploaded_files = st.file_uploader(
    "Upload vehicle images (1–10 photos)",
    type=["jpg", "jpeg", "png"],
    accept_multiple_files=True,
)

if uploaded_files:
    cols = st.columns(min(len(uploaded_files), 4))
    for i, f in enumerate(uploaded_files):
        cols[i % len(cols)].image(f, caption=f.name, use_container_width=True)

# --- Analyze Button ---
if st.button("🔍 Analyze Damage", type="primary", disabled=not uploaded_files):
    with st.spinner("Uploading images..."):
        files = [("images", (f.name, f.getvalue(), f.type)) for f in uploaded_files]
        try:
            upload_resp = httpx.post(f"{API_BASE}/upload", files=files, timeout=30.0)
            if upload_resp.status_code != 200:
                detail = upload_resp.json().get("detail", upload_resp.text)
                st.error(f"Upload failed: {detail}")
                st.stop()
            upload_data = upload_resp.json()
            upload_id = upload_data["upload_id"]
            st.success(f"✅ Uploaded {upload_data['image_count']} image(s)")
        except Exception as e:
            st.error(f"Upload failed: {e}")
            st.stop()

    def _handle_rate_limit(resp: httpx.Response) -> None:
        if resp.status_code == 429:
            detail = resp.json().get("detail", "")
            st.error(f"⏳ AI rate limit reached: {detail}")
            st.info("💡 Tip: Wait a few minutes and try again, or check your API key quotas at https://ai.google.dev/gemini-api/docs/rate-limits")
            st.stop()

    def _handle_error(resp: httpx.Response, step: str) -> None:
        _handle_rate_limit(resp)
        if resp.status_code != 200:
            detail = resp.json().get("detail", resp.text)
            st.error(f"{step} failed: {detail}")
            st.stop()

    # --- Step 1: Vehicle Identification ---
    with st.status("🔍 Step 1/3 — Identifying vehicle...", expanded=True) as status:
        id_payload = {"upload_id": upload_id}
        if override_make and override_model and override_year:
            id_payload["make"] = override_make
            id_payload["model"] = override_model
            id_payload["year"] = override_year

        try:
            vehicle_resp = httpx.post(
                f"{API_BASE}/identify-vehicle", json=id_payload, timeout=120.0
            )
            _handle_error(vehicle_resp, "Vehicle identification")
            vehicle_data = vehicle_resp.json()
        except Exception as e:
            st.error(f"Vehicle identification failed: {e}")
            st.stop()

        if vehicle_data.get("status") == "vehicle_confirmation_needed":
            guess = vehicle_data["vehicle_guess"]
            st.warning(vehicle_data["message"])
            st.info(
                f"AI guess: **{guess.get('year', '?')} {guess.get('make', '?')} "
                f"{guess.get('model', '?')}** (confidence: {guess.get('confidence', 0):.0%})"
            )
            st.markdown("Please enter the correct vehicle info in the sidebar and re-run.")
            st.stop()

        st.write(f"✅ Identified: {vehicle_data.get('year')} {vehicle_data.get('make')} {vehicle_data.get('model')}")
        status.update(label="✅ Step 1/3 — Vehicle identified", state="complete")

    # --- Step 2: Damage Detection ---
    with st.status("🔍 Step 2/3 — Analyzing damage...", expanded=True) as status:
        try:
            damage_resp = httpx.post(
                f"{API_BASE}/detect-damage", json={"upload_id": upload_id}, timeout=120.0
            )
            _handle_error(damage_resp, "Damage detection")
            damage_data = damage_resp.json()
        except Exception as e:
            st.error(f"Damage detection failed: {e}")
            st.stop()

        num_damages = len(damage_data.get("damages", []))
        st.write(f"✅ Found {num_damages} damaged component(s)")
        status.update(label=f"✅ Step 2/3 — Found {num_damages} damaged component(s)", state="complete")

    # --- Step 3: Cost Estimation ---
    with st.status("💰 Step 3/3 — Estimating repair costs...", expanded=True) as status:
        try:
            estimate_resp = httpx.post(
                f"{API_BASE}/estimate-costs",
                json={"vehicle": vehicle_data, "damage_assessment": damage_data},
                timeout=300.0,
            )
            _handle_error(estimate_resp, "Cost estimation")
            report = estimate_resp.json()
        except Exception as e:
            st.error(f"Cost estimation failed: {e}")
            st.stop()

        st.write(f"✅ Estimated costs for {len(report.get('cost_estimates', []))} component(s)")
        status.update(label="✅ Step 3/3 — Cost estimation complete", state="complete")

    # --- Vehicle Info ---
    vehicle = report["vehicle"]
    st.header("🚘 Vehicle Identified")
    v_cols = st.columns(4)
    v_cols[0].metric("Make", vehicle["make"])
    v_cols[1].metric("Model", vehicle["model"])
    v_cols[2].metric("Year", vehicle["year"])
    v_cols[3].metric("Confidence", f"{vehicle.get('confidence', 1.0):.0%}")

    # --- Damage Report ---
    damages = report.get("damage_assessment", {}).get("damages", [])
    st.header(f"💥 Damage Report ({len(damages)} components)")

    if damages:
        for dmg in damages:
            severity = dmg["severity"]
            color = "🟢" if severity <= 0.3 else "🟡" if severity <= 0.6 else "🔴"
            rec = "🔧 Repair" if dmg["recommendation"] == "repair" else "🔄 Replace"

            with st.expander(
                f"{color} {dmg['component'].replace('_', ' ').title()} — "
                f"Severity: {severity:.0%} — {rec}"
            ):
                st.write(f"**Damage type:** {dmg['damage_type']}")
                st.write(f"**Description:** {dmg['description']}")
                st.progress(severity)
    else:
        st.info("No damage detected!")

    # --- Cost Estimates ---
    cost_estimates = report.get("cost_estimates", [])
    if cost_estimates:
        st.header("💰 Cost Estimate")

        for est in cost_estimates:
            component_name = est["component"].replace("_", " ").title()
            st.subheader(component_name)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Parts (avg)", f"${est['part_cost_avg']}")
            c2.metric("Labor", f"${est['labor_cost']}")
            c3.metric("Total (avg)", f"${est['total_avg']}")
            c4.metric("Source", est.get("pricing_method", "").replace("_", " ").title())

        # --- Totals ---
        st.divider()
        totals = report["totals"]
        t1, t2, t3 = st.columns(3)
        t1.metric("🔩 Total Parts", f"${totals['parts_total']}")
        t2.metric("👷 Total Labor", f"${totals['labor_total']}")
        t3.metric("💵 Grand Total", f"${totals['grand_total']}")

    # --- Disclaimer ---
    st.divider()
    st.caption(report.get("disclaimer", ""))

    # --- Raw JSON ---
    with st.expander("📋 Raw JSON Report"):
        st.json(report)
