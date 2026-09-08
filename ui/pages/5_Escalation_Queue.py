import streamlit as st
import pandas as pd
from ui.api_client import APIClient, APIClientError
from ui.utils.formatting import format_currency, format_percentage
from ui.utils.icons import get_svg_icon, render_header, render_badge, render_banner, render_card_header
from ui.utils.layout import render_layout

st.set_page_config(page_title="Escalation Queue | RecoveryOS", page_icon="ui/assets/favicon.png", layout="wide")
render_layout()

header_html = render_header(
    title="Escalation Queue",
    subtitle="Payments flagged for human agent intervention — economically justified escalations requiring manual review",
    icon="alert_triangle",
    badge_label="Human Review Required",
    badge_status="warning"
)
st.markdown(header_html, unsafe_allow_html=True)

# ─── Styles ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.escalation-card {
    background: linear-gradient(135deg, rgba(245,158,11,0.06) 0%, rgba(239,68,68,0.04) 100%);
    border: 1px solid rgba(245,158,11,0.25);
    border-left: 3px solid #f59e0b;
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 10px;
    transition: border-color 0.2s ease;
}
.escalation-card:hover {
    border-color: rgba(245,158,11,0.55);
}
.escalation-card.high-value {
    border-left: 3px solid #ef4444;
    background: linear-gradient(135deg, rgba(239,68,68,0.07) 0%, rgba(245,158,11,0.04) 100%);
}
.eq-amount {
    font-size: 22px;
    font-weight: 700;
    color: #f8fafc;
    letter-spacing: -0.4px;
}
.eq-id {
    font-size: 11px;
    color: #64748b;
    font-family: monospace;
    margin-top: 2px;
}
.eq-meta {
    font-size: 12px;
    color: #94a3b8;
    margin-top: 6px;
}
.eq-recovery-bar {
    background: rgba(16,185,129,0.12);
    border: 1px solid rgba(16,185,129,0.25);
    border-radius: 6px;
    padding: 8px 12px;
    margin-top: 10px;
    font-size: 12px;
    color: #10b981;
    display: flex;
    align-items: center;
    gap: 6px;
}
.eq-stat-label { font-size: 11px; color: #64748b; font-weight: 500; text-transform: uppercase; letter-spacing: 0.5px; }
.eq-stat-value { font-size: 18px; font-weight: 700; color: #f1f5f9; margin-top: 2px; }
.eq-stat-sub   { font-size: 11px; color: #94a3b8; }
.divider { border: none; border-top: 1px solid rgba(148,163,184,0.1); margin: 16px 0; }
</style>
""", unsafe_allow_html=True)

HIGH_VALUE_THRESHOLD = 2000.0  # Payments above this are highlighted as high priority

# ─── Load Data ────────────────────────────────────────────────────────────────
try:
    with st.spinner("Loading escalation queue..."):
        data = APIClient.get_escalation_queue(limit=200)

    items = data.get("items", [])
    total = data.get("total", 0)

    if not items:
        st.markdown(
            render_banner(
                "No payments are currently in the escalation queue. "
                "Run a batch recovery to process failed payments — escalatable failures will appear here.",
                status="info"
            ),
            unsafe_allow_html=True
        )
        st.stop()

    # ─── Summary Stats ────────────────────────────────────────────────────────
    total_at_risk = sum(i["amount"] for i in items)
    total_recoverable = sum(i["gross_recovery_value"] or 0 for i in items)
    high_value_count = sum(1 for i in items if i["amount"] >= HIGH_VALUE_THRESHOLD)
    avg_prob = sum(i["predicted_recovery_prob"] or 0 for i in items) / len(items) if items else 0

    st.markdown(f"""
<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:24px;">
    <div class="glass-card" style="text-align:center;">
        <div class="eq-stat-label">Payments Queued</div>
        <div class="eq-stat-value">{total}</div>
        <div class="eq-stat-sub">Awaiting human review</div>
    </div>
    <div class="glass-card" style="text-align:center;">
        <div class="eq-stat-label">Total At Risk</div>
        <div class="eq-stat-value">{format_currency(total_at_risk)}</div>
        <div class="eq-stat-sub">Sum of escalated amounts</div>
    </div>
    <div class="glass-card" style="text-align:center;">
        <div class="eq-stat-label">Est. Recoverable</div>
        <div class="eq-stat-value" style="color:#10b981;">{format_currency(total_recoverable)}</div>
        <div class="eq-stat-sub">Gross recovery value</div>
    </div>
    <div class="glass-card" style="text-align:center;">
        <div class="eq-stat-label">High-Priority Cases</div>
        <div class="eq-stat-value" style="color:#ef4444;">{high_value_count}</div>
        <div class="eq-stat-sub">Above ₹{HIGH_VALUE_THRESHOLD:,.0f}</div>
    </div>
</div>
""", unsafe_allow_html=True)

    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    # ─── Filters ──────────────────────────────────────────────────────────────
    col_filter1, col_filter2, col_filter3 = st.columns([2, 2, 3])
    with col_filter1:
        categories = sorted(set(i.get("failure_category", "UNKNOWN") for i in items))
        selected_category = st.selectbox("Filter by Category", ["All"] + categories, key="eq_category")
    with col_filter2:
        methods = sorted(set(i.get("payment_method", "unknown") or "unknown" for i in items))
        selected_method = st.selectbox("Filter by Payment Method", ["All"] + methods, key="eq_method")
    with col_filter3:
        show_high_value_only = st.checkbox(f"Show high-priority only (≥ ₹{HIGH_VALUE_THRESHOLD:,.0f})", key="eq_hv")

    filtered = items
    if selected_category != "All":
        filtered = [i for i in filtered if i.get("failure_category") == selected_category]
    if selected_method != "All":
        filtered = [i for i in filtered if (i.get("payment_method") or "unknown") == selected_method]
    if show_high_value_only:
        filtered = [i for i in filtered if i["amount"] >= HIGH_VALUE_THRESHOLD]

    if not filtered:
        st.markdown(render_banner("No payments match the current filters.", status="info"), unsafe_allow_html=True)
        st.stop()

    st.markdown(f"<div style='font-size:13px;color:#64748b;margin-bottom:12px;'>Showing <b style='color:#f1f5f9;'>{len(filtered)}</b> of {total} escalated payment{'s' if total != 1 else ''}</div>", unsafe_allow_html=True)
    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    # ─── Payment Cards ────────────────────────────────────────────────────────
    for item in filtered:
        is_high_value = item["amount"] >= HIGH_VALUE_THRESHOLD
        card_class = "escalation-card high-value" if is_high_value else "escalation-card"

        prob = item.get("predicted_recovery_prob") or 0
        gross = item.get("gross_recovery_value") or 0
        method = (item.get("payment_method") or "unknown").upper()
        category = item.get("failure_category", "UNKNOWN")
        error_code = item.get("error_code", "N/A")

        priority_badge = render_badge("HIGH PRIORITY", status="error") if is_high_value else render_badge("STANDARD", status="warning")
        method_badge = render_badge(method, status="info")
        category_badge = render_badge(category, status="warning")

        recovery_bar = ""
        if gross > 0:
            recovery_bar = f"""
<div class="eq-recovery-bar">
    <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>
    Est. recoverable: <b>{format_currency(gross)}</b> &nbsp;·&nbsp; Recovery probability: <b>{format_percentage(prob)}</b> &nbsp;·&nbsp; Net value after ₹15 agent cost: <b>{format_currency(max(0, gross - 15))}</b>
</div>"""

        escalated_at = item.get("escalated_at", "")
        if escalated_at:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(escalated_at.replace("Z", "+00:00"))
                escalated_at = dt.strftime("%b %d, %Y %H:%M")
            except Exception:
                pass

        st.markdown(f"""
<div class="{card_class}">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px;">
        <div>
            <div class="eq-amount">{format_currency(item["amount"])}</div>
            <div class="eq-id">ID: {item["payment_id"]}</div>
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;">
            {priority_badge}
            {method_badge}
            {category_badge}
        </div>
    </div>
    <div class="eq-meta">
        <b style="color:#f87171;">Error:</b> {error_code} &nbsp;·&nbsp;
        {item.get("error_message", "N/A")} &nbsp;·&nbsp;
        <b>Status:</b> {item.get("status", "N/A")} &nbsp;·&nbsp;
        <b>Escalated at:</b> {escalated_at or "N/A"}
    </div>
    {recovery_bar}
</div>
""", unsafe_allow_html=True)

    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    # ─── Download Table ────────────────────────────────────────────────────────
    with st.expander("📋 Export Escalation Queue as Table"):
        df = pd.DataFrame([{
            "Payment ID": i["payment_id"],
            "Amount": i["amount"],
            "Method": i.get("payment_method", ""),
            "Category": i.get("failure_category", ""),
            "Error Code": i.get("error_code", ""),
            "Status": i.get("status", ""),
            "Recovery Prob": f"{(i.get('predicted_recovery_prob') or 0)*100:.1f}%",
            "Est. Recoverable": i.get("gross_recovery_value") or 0,
            "Escalated At": i.get("escalated_at", ""),
        } for i in filtered])
        st.dataframe(df, use_container_width=True)
        csv = df.to_csv(index=False)
        st.download_button(
            label="⬇ Download CSV",
            data=csv,
            file_name="escalation_queue.csv",
            mime="text/csv"
        )

except APIClientError as e:
    st.markdown(render_banner(f"Failed to load escalation queue: {e}", status="error"), unsafe_allow_html=True)
