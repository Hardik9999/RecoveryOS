import streamlit as st
from ui.utils.icons import get_svg_icon, render_header
from ui.utils.layout import render_layout

st.set_page_config(
    page_title="RecoveryOS",
    page_icon="ui/assets/favicon.png",
    layout="wide",
    initial_sidebar_state="expanded",
)

def main():
    """Main entry point for the Streamlit app."""
    render_layout()
    
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
            <div class="glass-card hover-lift">
                <div class="section-title">
                    {get_svg_icon("trending_up", size=18, color="#38bdf8")}
                    <span>Executive Dashboard</span>
                </div>
                <p class="text-muted">Monitor key business impact metrics: Revenue at Risk, Revenue Recovered, and Net Recovered Value.</p>
                <div style="font-size:12px;color:#64748b;">Navigate using the sidebar to view live analytics.</div>
            </div>
            """,
            unsafe_allow_html=True
        )
        st.markdown(
            f"""
            <div class="glass-card hover-lift">
                <div class="section-title">
                    {get_svg_icon("search", size=18, color="#38bdf8")}
                    <span>Payment Explorer</span>
                </div>
                <p class="text-muted">Inspect individual failed transactions, drill into Failure Intelligence, and trigger live single recoveries.</p>
                <div style="font-size:12px;color:#64748b;">Select any payment to inspect root cause & customer context.</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with col2:
        st.markdown(
            f"""
            <div class="glass-card hover-lift">
                <div class="section-title">
                    {get_svg_icon("git_branch", size=18, color="#38bdf8")}
                    <span>Decision Trace</span>
                </div>
                <p class="text-muted">Auditable 4-stage pipeline visualizing ML probability, Expected Net Value, AI proposal, and Deterministic Guardrails.</p>
                <div style="font-size:12px;color:#64748b;">Full transparency into why an action was proposed and authorized.</div>
            </div>
            """,
            unsafe_allow_html=True
        )
        st.markdown(
            f"""
            <div class="glass-card hover-lift">
                <div class="section-title">
                    {get_svg_icon("layers", size=18, color="#38bdf8")}
                    <span>Recovery Operations</span>
                </div>
                <p class="text-muted">Batch execution engine to recover hundreds of transactions at scale with aggregate performance tracking.</p>
                <div style="font-size:12px;color:#64748b;">Automated batch processing without manual overhead.</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    
if __name__ == "__main__":
    main()
