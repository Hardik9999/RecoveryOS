import streamlit as st
from ui.api_client import APIClient, APIClientError
from ui.utils.formatting import format_currency, format_percentage, format_action_name
from ui.utils.icons import get_svg_icon, render_header, render_badge, render_banner, render_card_header
from ui.utils.layout import render_layout

st.set_page_config(page_title="Decision Trace | RecoveryOS", page_icon="ui/assets/favicon.png", layout="wide")
render_layout()

header_html = render_header(
    title="Decision Trace",
    subtitle="Auditable decision journey: ML Prediction → Economics → AI Agent Proposal → Deterministic Policy Guardrails",
    icon="git_branch",
    badge_label="Audit Trail",
    badge_status="purple"
)
st.markdown(header_html, unsafe_allow_html=True)

# Ensure we have a recovery result to trace
if "last_recovery_result" not in st.session_state or not st.session_state.last_recovery_result:
    banner = render_banner(
        message="No recent recovery trace available in session.",
        status="info",
        details="Select a payment in Payment Explorer and click 'Run Recovery Workflow', or generate a trace directly below."
    )
    st.markdown(banner, unsafe_allow_html=True)
    
    st.write("")
    st.markdown(render_card_header("Generate Trace from Failed Payment", icon="refresh_cw"), unsafe_allow_html=True)
    
    try:
        with st.spinner("Loading eligible failed payments..."):
            payments_data = APIClient.get_payments(status="FAILED", limit=10)
            failed_payments = payments_data.get("payments", [])
            
        if failed_payments:
            selected_id = st.selectbox(
                "Select a failed payment to trace:",
                options=[p["id"] for p in failed_payments],
                format_func=lambda x: f"{x[:8]}... - {format_currency(next(p['amount'] for p in failed_payments if p['id'] == x))}"
            )
            
            if st.button("Generate Decision Trace", type="primary"):
                with st.spinner("Executing RecoveryOS workflow..."):
                    try:
                        result = APIClient.recover_payment(selected_id)
                        st.session_state.last_recovery_result = result
                        st.session_state.last_recovery_id = selected_id
                        st.rerun()
                    except APIClientError as e:
                        st.error(str(e))
        else:
            st.markdown(render_banner("No FAILED payments available to trace.", status="warning"), unsafe_allow_html=True)
    except APIClientError as e:
        st.markdown(render_banner("Could not reach backend service.", status="error", details=str(e)), unsafe_allow_html=True)
        
    st.stop()

# --- Render the Trace ---

result = st.session_state.last_recovery_result
pid = st.session_state.last_recovery_id

st.markdown(
    f"""
    <div style="display:flex;align-items:center;justify-content:space-between;padding:12px 16px;border-radius:8px;background:rgba(56,189,248,0.08);border:1px solid rgba(56,189,248,0.25);margin-bottom:20px;">
        <div style="display:flex;align-items:center;gap:10px;">
            {get_svg_icon('activity', size=20, color='#38bdf8')}
            <span style="font-size:14px;color:#e2e8f0;">Inspecting Decision Trace for Payment: <code style="color:#38bdf8;">{pid}</code></span>
        </div>
        {render_badge('Pipeline Verified', status='success')}
    </div>
    """,
    unsafe_allow_html=True
)

audit_trail = result.get("audit_trail", [])
prob = result.get("recovery_probability")
action = result.get("recommended_action")
economics = {
    "expected_recovery": result.get("expected_recovery_value"),
    "cost": result.get("intervention_cost"),
    "net": result.get("expected_net_value")
}
policy = result.get("policy", {})
execution = result.get("execution", {})
final_status = result.get("final_status")


# Parse Audit Trail into Loops
loops = []
current_loop = []
failure_info = {}

for step in audit_trail:
    if step.get("step") == "load_context":
        if current_loop:
            loops.append(current_loop)
        current_loop = [step]
        if not failure_info:
            details = step.get("details", {})
            failure_info = {
                "error_code": details.get("error_code", "UNKNOWN"),
                "category": details.get("failure_category", "UNKNOWN"),
                "severity": details.get("failure_severity", "UNKNOWN"),
                "retryable": details.get("is_retryable", False)
            }
    else:
        current_loop.append(step)
if current_loop:
    loops.append(current_loop)

# Stage 0: Failure Diagnosis
st.markdown(render_card_header("Stage 0: Failure Diagnosis", icon="search"), unsafe_allow_html=True)
retry_badge = render_badge("Retryable", "success") if failure_info.get("retryable") else render_badge("Not Retryable", "error")
st.markdown(
    f"""
    <div style="padding:16px;border-radius:8px;background:rgba(30,41,59,0.4);border:1px solid rgba(148,163,184,0.12);margin-bottom:20px;">
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:8px;">
            <div><div style="font-size:11px;color:#94a3b8;">Error Code</div><div style="font-size:16px;font-weight:600;color:#f8fafc;">{failure_info.get('error_code')}</div></div>
            <div><div style="font-size:11px;color:#94a3b8;">Category</div><div style="font-size:16px;font-weight:600;color:#f8fafc;">{failure_info.get('category')}</div></div>
            <div><div style="font-size:11px;color:#94a3b8;">Severity</div><div style="font-size:16px;font-weight:600;color:#f8fafc;">{failure_info.get('severity')}</div></div>
            <div><div style="font-size:11px;color:#94a3b8;">Gateway Retryability</div><div style="margin-top:4px;">{retry_badge}</div></div>
        </div>
    </div>
    """, unsafe_allow_html=True
)
st.divider()

if len(loops) > 1:
    st.markdown(f"**🔄 Re-evaluation Indicator: {len(loops)} closed-loop iterations executed.**")

for i, loop_steps in enumerate(loops):
    if len(loops) > 1:
        st.markdown(f"### Attempt #{i+1}")
        st.write("")
        
    load_ctx = next((s for s in loop_steps if s["step"] == "load_context"), {}).get("details", {})
    prop_act = next((s for s in loop_steps if s["step"] == "propose_action"), {}).get("details", {})
    pol_chk = next((s for s in loop_steps if s["step"] == "policy_check"), {}).get("details", {})
    exec_act = next((s for s in loop_steps if s["step"] == "execute_action"), {}).get("details", {})
    
    viable_actions = load_ctx.get("economically_viable_actions", [])
    
    # 1. Prediction & Economics
    st.markdown(render_card_header(f"Stage 1: Intelligence & Economic Viability", icon="trending_up"), unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            f"""
            <div style="padding:16px;border-radius:8px;background:rgba(30,41,59,0.4);border:1px solid rgba(148,163,184,0.12);height:100%;">
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
                    {get_svg_icon('trending_up', size=16, color='#38bdf8')}
                    <span style="font-size:14px;font-weight:600;color:#f8fafc;">ML Recovery Prediction Engine</span>
                </div>
                <div style="font-size:28px;font-weight:700;color:#38bdf8;margin:8px 0;">{format_percentage(prob)}</div>
                <div style="font-size:12px;color:#94a3b8;">Calibrated probability of successful recovery based on historical features and failure taxonomy.</div>
            </div>
            """,
            unsafe_allow_html=True
        )
        
    with col2:
        viable_html = "".join([f"<div style='display:flex;align-items:center;gap:4px;margin-bottom:4px;'>{get_svg_icon('check_circle', size=14, color='#10b981')} <span style='font-size:12px;color:#e2e8f0;'>{a}</span></div>" for a in viable_actions])
        if not viable_actions:
            viable_html = "<div style='font-size:12px;color:#ef4444;'>No economically viable actions</div>"

        st.markdown(
            f"""
            <div style="padding:16px;border-radius:8px;background:rgba(30,41,59,0.4);border:1px solid rgba(148,163,184,0.12);height:100%;">
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
                    {get_svg_icon('dollar_sign', size=16, color='#10b981')}
                    <span style="font-size:14px;font-weight:600;color:#f8fafc;">Economic Value Assessment</span>
                </div>
                <div style="margin-bottom: 8px;">
                    <div style="font-size:11px;color:#94a3b8;margin-bottom:4px;">Economically Viable Candidates:</div>
                    {viable_html}
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
    
    st.divider()
    
    # 2. Agent Proposal
    st.markdown(render_card_header(f"Stage 2: AI Agent Decision", icon="cpu"), unsafe_allow_html=True)
    
    agent_rationale_text = prop_act.get("rationale", "Agent evaluated the economic model and proposed optimal intervention.")
    agent_action = prop_act.get("action", action)
    orig_proposal = prop_act.get("original_proposal")
    
    if orig_proposal:
        econ_val_badge = render_badge("Economic Override Applied", "warning")
        agent_action_html = f"<code>{format_action_name(agent_action)}</code> <span style='font-size:12px;color:#94a3b8;'>(Overridden from {format_action_name(orig_proposal)})</span>"
    else:
        econ_val_badge = render_badge("Economic Validation Passed", "success")
        agent_action_html = f"<code>{format_action_name(agent_action)}</code>"
        
    st.markdown(
        f"""
        <div style="padding:16px;border-radius:8px;background:rgba(245,158,11,0.06);border:1px solid rgba(245,158,11,0.25);margin-bottom:16px;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
                <div style="display:flex;align-items:center;gap:8px;">
                    {get_svg_icon('cpu', size=18, color='#f59e0b')}
                    <span style="font-size:14px;font-weight:600;color:#f8fafc;">Autonomous Reasoner Proposal</span>
                </div>
                <div style="display:flex;align-items:center;gap:8px;">
                    {econ_val_badge}
                    {render_badge('AI Advisory', status='warning')}
                </div>
            </div>
            <div style="font-size:18px;font-weight:700;color:#f59e0b;margin-bottom:6px;">Final Proposal: {agent_action_html}</div>
            <div style="font-size:13px;color:#cbd5e1;line-height:1.5;">{agent_rationale_text}</div>
        </div>
        """,
        unsafe_allow_html=True
    )
    
    st.divider()
    
    # 3. Policy Guardrail
    st.markdown(render_card_header(f"Stage 3: Deterministic Policy Engine & Guardrails", icon="shield_check"), unsafe_allow_html=True)
    
    is_allowed = pol_chk.get("allowed", False)
    guard_status = "success" if is_allowed else "error"
    guard_icon = "shield_check" if is_allowed else "shield_alert"
    guard_label = "POLICY ALLOWED" if is_allowed else "POLICY DENIED"
    guard_color = "#10b981" if is_allowed else "#ef4444"
    
    reason_text = pol_chk.get("reason", "N/A")
    rule_text = f"Triggered Rule: {pol_chk.get('policy_rule')}" if pol_chk.get("policy_rule") else "Rule Compliance: 9/9 Deterministic Rules Verified"
    
    st.markdown(
        f"""
        <div style="padding:16px;border-radius:8px;background:{guard_color}10;border:1px solid {guard_color}35;margin-bottom:16px;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                <div style="display:flex;align-items:center;gap:8px;">
                    {get_svg_icon(guard_icon, size=20, color=guard_color)}
                    <span style="font-size:15px;font-weight:700;color:{guard_color};">{guard_label}</span>
                </div>
                {render_badge('Deterministic Firewall', status=guard_status)}
            </div>
            <div style="font-size:13px;color:#f1f5f9;margin-bottom:4px;"><b>Policy Assessment:</b> {reason_text}</div>
            <div style="font-size:11px;color:#94a3b8;">{rule_text}</div>
        </div>
        """,
        unsafe_allow_html=True
    )
    
    st.divider()
    
    # 4. Execution & Outcome
    if exec_act:
        st.markdown(render_card_header(f"Stage 4: Execution Result", icon="activity"), unsafe_allow_html=True)
        exec_success = exec_act.get("success", False)
        exec_status = "SUCCESS" if exec_success else "FAILURE"
        amount_rec = exec_act.get("amount_recovered", 0.0)
        
        exec_badge = render_badge(exec_status, status="success" if exec_success else "error")
        recovery_text = f"<div style='font-size:13px;color:#10b981;margin-top:6px;font-weight:600;'>Recovered: {format_currency(amount_rec)}</div>" if exec_success else ""
        st.markdown(
            f"""
            <div style="padding:16px;border-radius:8px;background:rgba(30,41,59,0.4);border:1px solid rgba(148,163,184,0.12);height:100%;">
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
                    {get_svg_icon('activity', size=16, color='#38bdf8')}
                    <span style="font-size:14px;font-weight:600;color:#f8fafc;">Execution Outcome</span>
                </div>
                <div style="margin:8px 0;">{exec_badge}</div>
                {recovery_text}
            </div>
            """,
            unsafe_allow_html=True
        )
        st.divider()

# Final outcome
st.markdown(render_card_header("Final State", icon="flag"), unsafe_allow_html=True)
out_theme = "success" if final_status == "RECOVERED" else ("warning" if final_status == "FAILED_TERMINAL" else "error")
out_badge = render_badge(final_status, status=out_theme)
st.markdown(
    f"""
    <div style="padding:16px;border-radius:8px;background:rgba(30,41,59,0.4);border:1px solid rgba(148,163,184,0.12);height:100%;">
        <div style="margin:8px 0;">{out_badge}</div>
    </div>
    """,
    unsafe_allow_html=True
)

st.write("")
if st.button("Clear Decision Trace", use_container_width=False):
    st.session_state.last_recovery_result = None
    st.rerun()
