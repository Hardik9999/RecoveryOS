"""
Global CSS definitions for RecoveryOS.
Implements modern, production-grade UI with glassmorphism, dynamic hover effects, and crisp typography.
"""
import streamlit as st

def inject_global_styles():
    """Inject global CSS into the Streamlit app."""
    st.markdown("""
        <style>
        /* Base typography & backgrounds */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif !important;
        }
        
        /* Interactive Cards */
        .glass-card {
            padding: 18px;
            border-radius: 12px;
            background: rgba(30, 41, 59, 0.45);
            border: 1px solid rgba(148, 163, 184, 0.12);
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            margin-bottom: 16px;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        
        .hover-lift:hover {
            transform: translateY(-3px);
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.25), 0 4px 6px -2px rgba(0, 0, 0, 0.15);
            border-color: rgba(56, 189, 248, 0.4);
            background: rgba(30, 41, 59, 0.6);
        }
        
        /* Headings & Text */
        .text-glow {
            color: #f8fafc;
            text-shadow: 0 0 12px rgba(56,189,248,0.3);
        }
        .section-title {
            display: flex;
            align-items: center;
            gap: 8px;
            font-weight: 600;
            font-size: 16px;
            color: #38bdf8;
            margin-bottom: 8px;
        }
        .text-muted {
            font-size: 13px;
            color: #94a3b8;
            line-height: 1.5;
            margin: 0 0 10px 0;
        }
        .text-mono {
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
        }
        
        /* Details / Info Cards */
        .info-panel {
            padding: 14px;
            border-radius: 8px;
            background: rgba(15, 23, 42, 0.4);
            border: 1px solid rgba(148, 163, 184, 0.12);
            margin-top: 10px;
            transition: background 0.2s ease;
        }
        .info-panel:hover {
            background: rgba(15, 23, 42, 0.6);
        }
        
        /* Action Memory / Sidebar Timeline */
        .memory-item {
            padding: 10px;
            border-radius: 8px;
            background: rgba(15, 23, 42, 0.5);
            border-left: 3px solid #38bdf8;
            margin-bottom: 10px;
            font-size: 13px;
            transition: transform 0.2s ease;
        }
        .memory-item:hover {
            transform: translateX(4px);
            background: rgba(15, 23, 42, 0.8);
        }
        .memory-time {
            font-size: 11px;
            color: #64748b;
            margin-bottom: 4px;
        }
        .memory-title {
            font-weight: 600;
            color: #f1f5f9;
        }
        
        /* Metric Cards */
        .metric-value {
            font-size: 28px;
            font-weight: 700;
            color: #f8fafc;
            letter-spacing: -0.5px;
        }
        .metric-label {
            font-size: 13px;
            font-weight: 500;
            color: #cbd5e1;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        /* General Streamlit tweaks for cleaner UI */
        .stButton>button {
            border-radius: 8px;
            font-weight: 600;
            transition: all 0.2s ease;
        }
        .stButton>button:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(56, 189, 248, 0.3);
        }
        </style>
    """, unsafe_allow_html=True)
