import streamlit as st
import pandas as pd
from ui.api_client import APIClient, APIClientError
from ui.utils.formatting import format_currency
from ui.utils.icons import get_svg_icon, render_header, render_banner, render_card_header, render_badge

st.set_page_config(page_title="Recovery Operations | RecoveryOS", page_icon="ui/assets/favicon.png", layout="wide")

header_html = render_header(
    title="Recovery Operations",
    subtitle="Automated batch recovery execution and aggregate performance tracking",
    icon="layers",
    badge_label="Batch Automation",
    badge_status="info"
)
st.markdown(header_html, unsafe_allow_html=True)

col1, col2 = st.columns([1, 2])

with col1:
    st.markdown(render_card_header("Batch Configuration", icon="layers"), unsafe_allow_html=True)
    batch_size = st.number_input(
        "Batch Size (Max 500)", 
        min_value=1, 
        max_value=500, 
        value=50,
        step=10,
        help="Number of eligible FAILED payments to process in this batch."
    )
    
    st.markdown(
        f"""
        <div style="padding:12px;border-radius:8px;background:rgba(59,130,246,0.08);border:1px solid rgba(59,130,246,0.2);margin-bottom:14px;">
            <div style="display:flex;align-items:center;gap:8px;font-size:13px;font-weight:600;color:#38bdf8;margin-bottom:4px;">
                {get_svg_icon('zap', size=16, color='#38bdf8')}
                <span>Autonomous Pipeline</span>
            </div>
            <div style="font-size:12px;color:#94a3b8;line-height:1.4;">
                Sequentially evaluates Intelligence → Prediction → Economics → Agent Proposal → Policy Guardrail → Execution for each transaction.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )
    
    run_button = st.button("Run Batch Recovery", type="primary", use_container_width=True)

with col2:
    if run_button:
        with st.spinner(f"Processing batch of {batch_size} payments..."):
            try:
                result = APIClient.run_batch_recovery(limit=batch_size)
                st.session_state.last_batch_result = result
                st.success("Batch processing complete.")
            except APIClientError as e:
                st.markdown(render_banner("Batch processing failed.", status="error", details=str(e)), unsafe_allow_html=True)
                st.stop()
                
    if "last_batch_result" in st.session_state:
        st.markdown(render_card_header("Batch Results Summary", icon="trending_up"), unsafe_allow_html=True)
        summary = st.session_state.last_batch_result
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Processed", summary.get("payments_processed", 0))
        c2.metric("Recovered", summary.get("payments_recovered", 0))
        c3.metric("Policy Denied", summary.get("payments_policy_denied", 0))
        c4.metric("Stopped/Terminal", summary.get("payments_stopped", 0))
        
        st.write("")
        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Revenue at Risk", format_currency(summary.get("revenue_at_risk", 0.0)))
        c6.metric("Revenue Recovered", format_currency(summary.get("revenue_recovered", 0.0)))
        c7.metric("Intervention Cost", format_currency(summary.get("intervention_cost", 0.0)), delta_color="inverse")
        c8.metric("Net Recovered", format_currency(summary.get("net_recovered_value", 0.0)))
        
        st.divider()
        st.markdown(render_card_header("Processed Transactions", icon="activity"), unsafe_allow_html=True)
        details = summary.get("details", [])
        if details:
            df = pd.DataFrame(details)
            display_df = pd.DataFrame({
                "Payment ID": df["payment_id"],
                "Final Status": df["status"],
                "Action Taken": df["action"].fillna("None"),
                "Amount Recovered": df["amount_recovered"].apply(format_currency)
            })
            
            def color_status(val):
                if val == 'RECOVERED': return 'color: #10b981; font-weight: 600;'
                elif val in ('FAILED', 'ERROR'): return 'color: #ef4444; font-weight: 600;'
                elif val in ('STOPPED', 'FAILED_TERMINAL'): return 'color: #f59e0b; font-weight: 600;'
                return ''
                
            st.dataframe(
                display_df.style.map(color_status, subset=['Final Status']), 
                use_container_width=True,
                hide_index=True
            )
        else:
            st.markdown(render_banner("No payments were processed. The batch may be empty.", status="warning"), unsafe_allow_html=True)
    else:
        st.markdown(render_card_header("Batch Results Summary", icon="trending_up"), unsafe_allow_html=True)
        st.info("Run a batch using the configuration on the left to see aggregate results.")
