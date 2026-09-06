"""
Shared global layout and memory components for RecoveryOS.
"""
import streamlit as st
from datetime import datetime
from ui.api_client import APIClient
from ui.utils.icons import get_svg_icon, render_badge
from ui.utils.styles import inject_global_styles

def render_layout():
    """Render the global layout including CSS styles, sidebar, and memory log."""
    # 1. Inject Global Styles
    inject_global_styles()
    
    # 2. Render Global Sidebar
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
        try:
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
                raise Exception("API Offline")
        except Exception:
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
            
    # 3. Action Memory Panel
    st.sidebar.divider()
    st.sidebar.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:6px;margin-bottom:12px;">
            {get_svg_icon("activity", size=16, color="#94a3b8")}
            <span style="font-size:13px;font-weight:600;color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px;">Session Memory</span>
        </div>
        """,
        unsafe_allow_html=True
    )
    
    if "action_history" not in st.session_state:
        st.session_state.action_history = []
        
    if not st.session_state.action_history:
        st.sidebar.markdown(
            """<div style="font-size:12px;color:#64748b;font-style:italic;">No recovery actions taken in this session.</div>""",
            unsafe_allow_html=True
        )
    else:
        # Show last 5 actions
        for action in reversed(st.session_state.action_history[-5:]):
            time_str = action["time"].strftime("%H:%M:%S")
            pid = action["payment_id"][:8] + "..."
            status = action["status"]
            status_color = "#10b981" if status == "SUCCESS" else ("#f59e0b" if status == "STOPPED" else "#ef4444")
            
            st.sidebar.markdown(
                f"""
                <div class="memory-item" style="border-left-color: {status_color}">
                    <div class="memory-time">{time_str}</div>
                    <div class="memory-title">Payment {pid}</div>
                    <div style="font-size:12px;color:#cbd5e1;margin-top:2px;">Outcome: <span style="color:{status_color};font-weight:600;">{status}</span></div>
                </div>
                """,
                unsafe_allow_html=True
            )
            
def record_action(payment_id: str, status: str):
    """Helper to record an action into memory."""
    if "action_history" not in st.session_state:
        st.session_state.action_history = []
    st.session_state.action_history.append({
        "time": datetime.now(),
        "payment_id": payment_id,
        "status": status
    })
