import streamlit as st
import pandas as pd
import plotly.express as px
from ui.api_client import APIClient, APIClientError
from ui.utils.formatting import format_currency, format_percentage
from ui.utils.icons import get_svg_icon, render_header, render_banner, render_card_header

st.set_page_config(page_title="Dashboard | RecoveryOS", page_icon="ui/assets/favicon.png", layout="wide")

header_html = render_header(
    title="Executive Dashboard",
    subtitle="Business impact, revenue recovery velocity, and intervention economics",
    icon="trending_up",
    badge_label="Live KPIs",
    badge_status="success"
)
st.markdown(header_html, unsafe_allow_html=True)

try:
    with st.spinner("Loading analytics summary..."):
        summary = APIClient.get_analytics_summary()
        
    # KPI Cards Row 1
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            label="Revenue at Risk", 
            value=format_currency(summary.get("revenue_at_risk", 0.0))
        )
    with col2:
        st.metric(
            label="Revenue Recovered", 
            value=format_currency(summary.get("revenue_recovered", 0.0))
        )
    with col3:
        st.metric(
            label="Recovery Rate", 
            value=format_percentage(summary.get("recovery_rate"))
        )
    with col4:
        st.metric(
            label="Net Recovered Value", 
            value=format_currency(summary.get("net_recovered_value", 0.0)),
            help="Revenue Recovered - Intervention Cost"
        )
        
    # KPI Cards Row 2
    st.write("")
    col5, col6, col7, col8 = st.columns(4)
    with col5:
        st.metric(label="Total Failed Payments", value=summary.get("total_failed", 0) + summary.get("total_recovered", 0))
    with col6:
        st.metric(label="Interventions Executed", value=summary.get("interventions", 0))
    with col7:
        st.metric(label="Interventions Avoided", value=summary.get("interventions_avoided", 0))
    with col8:
        st.metric(
            label="Intervention Cost", 
            value=format_currency(summary.get("intervention_cost", 0.0)),
            delta_color="inverse"
        )
        
    st.divider()
    
    # Charts Area
    chart_header = render_card_header("Recovery Outcomes & Operational Efficiency", icon="activity")
    st.markdown(chart_header, unsafe_allow_html=True)
    
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        outcomes_data = {
            "Status": ["Recovered", "Stopped/Terminal", "Failed (Pending)"],
            "Count": [
                summary.get("total_recovered", 0),
                summary.get("stopped_payments", 0) + summary.get("total_terminal", 0),
                summary.get("total_failed", 0) - summary.get("stopped_payments", 0) - summary.get("total_terminal", 0)
            ]
        }
        df_outcomes = pd.DataFrame(outcomes_data)
        df_outcomes["Count"] = df_outcomes["Count"].apply(lambda x: max(0, x))
        
        fig1 = px.pie(
            df_outcomes, 
            values='Count', 
            names='Status', 
            hole=0.45,
            color='Status',
            color_discrete_map={
                "Recovered": "#10b981",
                "Stopped/Terminal": "#f59e0b",
                "Failed (Pending)": "#ef4444"
            },
            title="Overall Payment Outcomes"
        )
        fig1.update_layout(
            margin=dict(t=40, b=20, l=20, r=20),
            legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5)
        )
        st.plotly_chart(fig1, use_container_width=True)
        
    with col_chart2:
        st.markdown(
            f"""
            <div style="display:flex;flex-direction:column;gap:12px;margin-top:16px;">
                <div style="padding:14px 16px;border-radius:8px;background:rgba(59,130,246,0.08);border:1px solid rgba(59,130,246,0.25);display:flex;align-items:center;gap:12px;">
                    {get_svg_icon("activity", size=20, color="#3b82f6")}
                    <div>
                        <div style="font-size:14px;font-weight:600;color:#f8fafc;">{summary.get('interventions', 0)} Interventions Executed</div>
                        <div style="font-size:12px;color:#94a3b8;">Recovery actions orchestrated across retry, reminders, and payment links.</div>
                    </div>
                </div>
                <div style="padding:14px 16px;border-radius:8px;background:rgba(16,185,129,0.08);border:1px solid rgba(16,185,129,0.25);display:flex;align-items:center;gap:12px;">
                    {get_svg_icon("shield_check", size=20, color="#10b981")}
                    <div>
                        <div style="font-size:14px;font-weight:600;color:#f8fafc;">{summary.get('interventions_avoided', 0)} Interventions Intelligently Avoided</div>
                        <div style="font-size:12px;color:#94a3b8;">Saved costs and prevented user fatigue on low-probability or fraudulent payments.</div>
                    </div>
                </div>
                <div style="padding:14px 16px;border-radius:8px;background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.25);display:flex;align-items:center;gap:12px;">
                    {get_svg_icon("alert_triangle", size=20, color="#f59e0b")}
                    <div>
                        <div style="font-size:14px;font-weight:600;color:#f8fafc;">{summary.get('escalations', 0)} Severe Escalations</div>
                        <div style="font-size:12px;color:#94a3b8;">High-severity payment issues flagged for operational intervention.</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        if summary.get("average_attempts"):
            st.metric("Avg Attempts per Recovery", f"{summary.get('average_attempts'):.1f}")
        
except APIClientError as e:
    banner = render_banner(
        message="RecoveryOS backend is currently unavailable or returned an error.",
        status="error",
        details=f"Please verify FastAPI server is running. Error details: {str(e)}"
    )
    st.markdown(banner, unsafe_allow_html=True)
