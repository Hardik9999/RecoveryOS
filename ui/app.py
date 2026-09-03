import streamlit as st
from ui.api_client import APIClient
from ui.utils.icons import get_svg_icon, render_badge, render_header

st.set_page_config(
    page_title="RecoveryOS",
    page_icon="ui/assets/favicon.png",
    layout="wide",
    initial_sidebar_state="expanded",
)

def render_sidebar():
    """Render the global sidebar and API status."""
    # Production-grade header with SVG Zap
    brand_svg = get_svg_icon("zap", size=24, color="#38bdf8")
    st.sidebar.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;">
            <div style="display:flex;align-items:center;justify-content:center;width:34px;height:34px;border-radius:8px;background:rgba(56,189,248,0.15);border:1px solid rgba(56,189,248,0.3);">
                {brand_svg}
            </div>
            <span style="font-size:20px;font-weight:700;color:#f8fafc;letter-spacing:-0.4px;">RecoveryOS</span>
        </div>
        <div style="font-size:12px;font-weight:600;color:#94a3b8;letter-spacing:0.5px;text-transform:uppercase;margin-bottom:4px;">Revenue Recovery Intelligence</div>
        <div style="font-size:12px;color:#64748b;line-height:1.4;">AI-powered recovery decisions with deterministic financial guardrails</div>
        """,
        unsafe_allow_html=True
    )
    
    st.sidebar.divider()
    
    # Check API health
    with st.sidebar:
        health = APIClient.get_health()
            
        if health.get("status") == "healthy":
            badge_html = render_badge("API Connected", status="success")
            st.markdown(
                f"""
                <div style="padding:10px;border-radius:8px;background:rgba(16,185,129,0.06);border:1px solid rgba(16,185,129,0.2);margin-bottom:12px;">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <span style="font-size:13px;font-weight:500;color:#cbd5e1;">Backend Service</span>
                        {badge_html}
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
        else:
            badge_html = render_badge("API Offline", status="error")
            st.markdown(
                f"""
                <div style="padding:10px;border-radius:8px;background:rgba(239,68,68,0.06);border:1px solid rgba(239,68,68,0.2);margin-bottom:12px;">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <span style="font-size:13px;font-weight:500;color:#cbd5e1;">Backend Service</span>
                        {badge_html}
                    </div>
                    <div style="font-size:11px;color:#94a3b8;margin-top:6px;">Please verify FastAPI is running on port 8000.</div>
                </div>
                """,
                unsafe_allow_html=True
            )

def main():
    """Main entry point for the Streamlit app."""
    render_sidebar()
    
    header_html = render_header(
        title="RecoveryOS Console",
        subtitle="Intelligent revenue recovery orchestration powered by ML, Economics, and Agentic Guardrails",
        icon="zap",
        badge_label="Enterprise Prototype",
        badge_status="info"
    )
    st.markdown(header_html, unsafe_allow_html=True)
    
    st.markdown(
        """
        RecoveryOS evaluates every failed payment across recoverability, 
        economic value, agent recommendation, and deterministic policy 
        before allowing an intervention.
        """
    )
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            f"""
            <div style="padding:18px;border-radius:10px;background:rgba(30,41,59,0.4);border:1px solid rgba(148,163,184,0.12);margin-bottom:16px;">
                <div style="display:flex;align-items:center;gap:8px;font-weight:600;font-size:16px;color:#38bdf8;margin-bottom:8px;">
                    {get_svg_icon("trending_up", size=18, color="#38bdf8")}
                    <span>Executive Dashboard</span>
                </div>
                <p style="font-size:13px;color:#94a3b8;margin:0 0 10px 0;">Monitor key business impact metrics: Revenue at Risk, Revenue Recovered, and Net Recovered Value.</p>
                <div style="font-size:12px;color:#64748b;">Navigate using the sidebar to view live analytics.</div>
            </div>
            """,
            unsafe_allow_html=True
        )
        st.markdown(
            f"""
            <div style="padding:18px;border-radius:10px;background:rgba(30,41,59,0.4);border:1px solid rgba(148,163,184,0.12);margin-bottom:16px;">
                <div style="display:flex;align-items:center;gap:8px;font-weight:600;font-size:16px;color:#38bdf8;margin-bottom:8px;">
                    {get_svg_icon("search", size=18, color="#38bdf8")}
                    <span>Payment Explorer</span>
                </div>
                <p style="font-size:13px;color:#94a3b8;margin:0 0 10px 0;">Inspect individual failed transactions, drill into Failure Intelligence, and trigger live single recoveries.</p>
                <div style="font-size:12px;color:#64748b;">Select any payment to inspect root cause & customer context.</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with col2:
        st.markdown(
            f"""
            <div style="padding:18px;border-radius:10px;background:rgba(30,41,59,0.4);border:1px solid rgba(148,163,184,0.12);margin-bottom:16px;">
                <div style="display:flex;align-items:center;gap:8px;font-weight:600;font-size:16px;color:#38bdf8;margin-bottom:8px;">
                    {get_svg_icon("git_branch", size=18, color="#38bdf8")}
                    <span>Decision Trace</span>
                </div>
                <p style="font-size:13px;color:#94a3b8;margin:0 0 10px 0;">Auditable 4-stage pipeline visualizing ML probability, Expected Net Value, AI proposal, and Deterministic Guardrails.</p>
                <div style="font-size:12px;color:#64748b;">Full transparency into why an action was proposed and authorized.</div>
            </div>
            """,
            unsafe_allow_html=True
        )
        st.markdown(
            f"""
            <div style="padding:18px;border-radius:10px;background:rgba(30,41,59,0.4);border:1px solid rgba(148,163,184,0.12);margin-bottom:16px;">
                <div style="display:flex;align-items:center;gap:8px;font-weight:600;font-size:16px;color:#38bdf8;margin-bottom:8px;">
                    {get_svg_icon("layers", size=18, color="#38bdf8")}
                    <span>Recovery Operations</span>
                </div>
                <p style="font-size:13px;color:#94a3b8;margin:0 0 10px 0;">Batch execution engine to recover hundreds of transactions at scale with aggregate performance tracking.</p>
                <div style="font-size:12px;color:#64748b;">Automated batch processing without manual overhead.</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    
if __name__ == "__main__":
    main()
