import streamlit as st
import pandas as pd
from ui.api_client import APIClient, APIClientError
from ui.utils.formatting import format_currency, format_action_name
from ui.utils.icons import get_svg_icon, render_header, render_badge, render_banner, render_card_header
from ui.utils.layout import render_layout, record_action

st.set_page_config(page_title="Payment Explorer | RecoveryOS", page_icon="ui/assets/favicon.png", layout="wide")
render_layout()

header_html = render_header(
    title="Payment Explorer",
    subtitle="Inspect individual payment failures, failure taxonomy, and customer risk context",
    icon="search",
    badge_label="Transaction Inspector",
    badge_status="info"
)
st.markdown(header_html, unsafe_allow_html=True)

# Initialize session state for selected payment
if "selected_payment_id" not in st.session_state:
    st.session_state.selected_payment_id = None

try:
    with st.spinner("Loading payments..."):
        payments_data = APIClient.get_payments(limit=100)
        
    payments = payments_data.get("payments", [])
    
    if not payments:
        st.info("No payments are currently available in the system.")
        st.stop()
        
    # Build a clean dataframe for the list
    df_data = []
    for p in payments:
        failure_type = p.get("failure", {}).get("failure_category", "N/A") if p.get("failure") else "None"
        df_data.append({
            "Payment ID": p["id"],
            "Status": p["status"],
            "Amount": format_currency(p["amount"]),
            "Method": str(p.get("payment_method")).upper(),
            "Failure Type": failure_type,
            "Attempts": p.get("attempt_count", 0),
            "Created": p.get("created_at", "")[:19].replace("T", " ") if p.get("created_at") else "Unknown"
        })
        
    df = pd.DataFrame(df_data)
    
    col_list, col_detail = st.columns([1, 1])
    
    with col_list:
        st.markdown(render_card_header("Recent Transactions", icon="activity"), unsafe_allow_html=True)
        
        # Simple selection mechanism
        selected_id = st.selectbox(
            "Select a payment to inspect:",
            options=df["Payment ID"].tolist(),
            format_func=lambda x: f"{x[:8]}... - {df[df['Payment ID'] == x]['Status'].values[0]} ({df[df['Payment ID'] == x]['Amount'].values[0]})"
        )
        
        st.session_state.selected_payment_id = selected_id
        
        # Display the dataframe for visual reference
        st.dataframe(df, use_container_width=True, hide_index=True)
        
    with col_detail:
        if st.session_state.selected_payment_id:
            with st.spinner("Loading payment details..."):
                details = APIClient.get_payment_details(st.session_state.selected_payment_id)
            
            st.markdown(render_card_header("Payment Overview", icon="dollar_sign"), unsafe_allow_html=True)
            
            # Header card with badges
            status_val = details["status"]
            status_theme = "success" if status_val in ("SUCCESS", "RECOVERED") else ("error" if status_val in ("FAILED", "FAILED_TERMINAL") else "warning")
            status_badge = render_badge(status_val, status=status_theme)
            
            st.markdown(
                f"""
                <div class="glass-card">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                        <span style="font-size:18px;font-weight:700;color:#f8fafc;">{format_currency(details['amount'], details.get('currency', '₹'))}</span>
                        {status_badge}
                    </div>
                    <div style="font-size:12px;color:#94a3b8;font-family:monospace;">ID: {details['id']}</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            
            # Split info into tabs
            tab1, tab2, tab3 = st.tabs(["Failure Intelligence", "Recovery History", "Context"])
            
            with tab1:
                if details.get("failure"):
                    f = details["failure"]
                    is_ret = "Yes" if f.get("is_retryable") else "No"
                    ret_badge = render_badge(f"Retryable: {is_ret}", status="success" if f.get("is_retryable") else "error")
                    cat_badge = render_badge(f.get("failure_category", "UNKNOWN"), status="warning")
                    
                    st.markdown(
                        f"""
                        <div class="info-panel">
                            <div style="display:flex;gap:8px;margin-bottom:10px;">
                                {cat_badge}
                                {ret_badge}
                            </div>
                            <div style="font-size:14px;font-weight:600;color:#f1f5f9;margin-bottom:4px;">Error Code: <span class="text-mono" style="color:#f87171;">{f.get('error_code')}</span></div>
                            <div class="text-muted">{f.get('error_message')}</div>
                            <div style="font-size:11px;color:#64748b;">Occurred At: {f.get('occurred_at')}</div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                else:
                    st.markdown(render_banner("No failure recorded. This payment processed normally.", status="success"), unsafe_allow_html=True)
                    
            with tab2:
                actions = details.get("recovery_actions", [])
                if not actions:
                    st.markdown(render_banner("No recovery actions have been attempted yet.", status="info"), unsafe_allow_html=True)
                else:
                    for i, action in enumerate(actions):
                        action_title = f"Attempt #{action.get('attempt_number', i+1)}: {format_action_name(action.get('action_type'))}"
                        with st.expander(action_title, expanded=(i == len(actions)-1)):
                            st.write(f"**Action Status:** `{action.get('action_status')}`")
                            if action.get('predicted_recovery_prob'):
                                st.write(f"**ML Predicted Probability:** {action.get('predicted_recovery_prob') * 100:.1f}%")
                            st.write(f"**Policy Guardrail Decision:** `{action.get('policy_decision')}`")
                            if action.get('policy_reason'):
                                st.caption(f"Policy Reason: {action.get('policy_reason')}")
                            if action.get('outcome_success') is not None:
                                outcome_str = "SUCCESS" if action.get('outcome_success') else "FAILED"
                                outcome_status = "success" if action.get('outcome_success') else "error"
                                st.markdown(f"**Execution Outcome:** {render_badge(outcome_str, status=outcome_status)}", unsafe_allow_html=True)
                            
            with tab3:
                st.markdown(
                    f"""
                    <div class="info-panel">
                        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
                            {get_svg_icon('user', size=16, color='#94a3b8')}
                            <span style="font-size:13px;color:#cbd5e1;">Customer ID: <code class="text-mono" style="color:#38bdf8;background:transparent;">{details.get('customer_id')}</code></span>
                        </div>
                        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
                            {get_svg_icon('building', size=16, color='#94a3b8')}
                            <span style="font-size:13px;color:#cbd5e1;">Merchant ID: <code class="text-mono" style="color:#38bdf8;background:transparent;">{details.get('merchant_id')}</code></span>
                        </div>
                        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
                            {get_svg_icon('activity', size=16, color='#94a3b8')}
                            <span style="font-size:13px;color:#cbd5e1;">Method: <b>{str(details.get('payment_method')).upper()}</b></span>
                        </div>
                        <div style="display:flex;align-items:center;gap:8px;">
                            {get_svg_icon('clock', size=16, color='#94a3b8')}
                            <span style="font-size:13px;color:#64748b;">Created: {details.get('created_at')}</span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                
            st.divider()
            
            # Action Area
            if details["status"] in ("FAILED", "FAILED_TERMINAL"):
                st.markdown(render_card_header("Recovery Operations", icon="zap"), unsafe_allow_html=True)
                
                if st.button("Run Recovery Workflow", type="primary", use_container_width=True):
                    with st.spinner("Executing RecoveryOS workflow..."):
                        try:
                            result = APIClient.recover_payment(details['id'])
                            st.session_state.last_recovery_result = result
                            st.session_state.last_recovery_id = details['id']
                            
                            # Log action into memory sidebar
                            record_action(details['id'], result['final_status'])
                            
                            st.success(f"Workflow completed. Final status: {result['final_status']}")
                            st.info("Navigate to the Decision Trace page to see the full auditable pipeline.")
                            st.rerun()
                        except APIClientError as e:
                            st.error(str(e))
                            
except APIClientError as e:
    banner = render_banner("Backend connection error", status="error", details=str(e))
    st.markdown(banner, unsafe_allow_html=True)
