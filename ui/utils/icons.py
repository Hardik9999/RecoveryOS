"""
Production-grade SVG icons and components for RecoveryOS.
Clean, modern Lucide/Feather-style vectors without emojis.
"""
from typing import Optional

# SVG Vector definitions (24x24 viewBox, stroke-width=2, stroke-linecap=round, stroke-linejoin=round)
SVG_PATHS = {
    "zap": '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
    "shield_check": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/>',
    "shield_alert": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>',
    "check_circle": '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>',
    "x_circle": '<circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>',
    "alert_triangle": '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
    "trending_up": '<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/>',
    "dollar_sign": '<line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>',
    "cpu": '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/>',
    "search": '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
    "layers": '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>',
    "refresh_cw": '<polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>',
    "activity": '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    "info": '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>',
    "flag": '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" y1="22" x2="4" y2="15"/>',
    "user": '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    "building": '<rect x="4" y="2" width="16" height="20" rx="2"/><line x1="9" y1="22" x2="9" y2="12"/><line x1="15" y1="22" x2="15" y2="12"/><line x1="8" y1="6" x2="10" y2="6"/><line x1="14" y1="6" x2="16" y2="6"/><line x1="8" y1="10" x2="10" y2="10"/><line x1="14" y1="10" x2="16" y2="10"/>',
    "git_branch": '<line x1="6" y1="3" x2="6" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/>',
}

STATUS_COLORS = {
    "success": "#10b981",    # Emerald green
    "error": "#ef4444",      # Crimson red
    "warning": "#f59e0b",    # Amber
    "info": "#3b82f6",       # Cobalt blue
    "purple": "#8b5cf6",     # Indigo/Purple
    "muted": "#94a3b8",      # Slate grey
    "dark": "#0f172a",       # Slate 900
}


def get_svg_icon(name: str, size: int = 18, color: Optional[str] = None, stroke_width: float = 2.0) -> str:
    """Return an inline SVG string for the specified icon name."""
    path = SVG_PATHS.get(name, SVG_PATHS["info"])
    c = color if color else "currentColor"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" '
        f'fill="none" stroke="{c}" stroke-width="{stroke_width}" stroke-linecap="round" stroke-linejoin="round" '
        f'style="display:inline-block;vertical-align:middle;flex-shrink:0;">'
        f'{path}</svg>'
    )


def render_badge(label: str, status: str = "info", icon: Optional[str] = None) -> str:
    """Render a clean, production-grade fintech badge with SVG icon."""
    color = STATUS_COLORS.get(status, STATUS_COLORS["info"])
    icon_name = icon or {
        "success": "check_circle",
        "error": "x_circle",
        "warning": "alert_triangle",
        "info": "info",
    }.get(status, "info")
    
    icon_svg = get_svg_icon(icon_name, size=14, color=color)
    
    return (
        f'<span style="display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:6px;'
        f'background-color:{color}15;border:1px solid {color}40;color:{color};font-size:12px;font-weight:600;'
        f'letter-spacing:0.3px;font-family:system-ui,-apple-system,BlinkMacSystemFont,sans-serif;">'
        f'{icon_svg}{label}</span>'
    )


def render_header(title: str, subtitle: Optional[str] = None, icon: Optional[str] = None, badge_label: Optional[str] = None, badge_status: str = "info") -> str:
    """Render a modern product header with SVG icon and optional badge."""
    icon_markup = ""
    if icon:
        icon_svg = get_svg_icon(icon, size=28, color="#38bdf8")
        icon_markup = (
            f'<div style="display:flex;align-items:center;justify-content:center;width:42px;height:42px;'
            f'border-radius:10px;background:linear-gradient(135deg,rgba(56,189,248,0.15),rgba(59,130,246,0.15));'
            f'border:1px solid rgba(56,189,248,0.3);margin-right:12px;">'
            f'{icon_svg}</div>'
        )
        
    badge_markup = ""
    if badge_label:
        badge_markup = f'<div style="margin-left:auto;">{render_badge(badge_label, badge_status)}</div>'

    sub_markup = ""
    if subtitle:
        sub_markup = f'<p style="margin:4px 0 0 0;font-size:14px;color:#94a3b8;font-weight:400;">{subtitle}</p>'

    return (
        f'<div style="display:flex;align-items:center;margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid rgba(148,163,184,0.15);">'
        f'{icon_markup}'
        f'<div>'
        f'<h1 style="margin:0;font-size:24px;font-weight:700;color:#f8fafc;letter-spacing:-0.4px;">{title}</h1>'
        f'{sub_markup}'
        f'</div>'
        f'{badge_markup}'
        f'</div>'
    )


def render_card_header(title: str, icon: str, color: str = "#38bdf8") -> str:
    """Render a section/card header with an SVG icon."""
    icon_svg = get_svg_icon(icon, size=18, color=color)
    return (
        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;font-weight:600;font-size:15px;color:#f1f5f9;">'
        f'{icon_svg}<span>{title}</span></div>'
    )


def render_banner(message: str, status: str = "info", details: Optional[str] = None) -> str:
    """Render a sleek enterprise notification/banner with SVG icon."""
    color = STATUS_COLORS.get(status, STATUS_COLORS["info"])
    icon_name = {
        "success": "check_circle",
        "error": "x_circle",
        "warning": "alert_triangle",
        "info": "info",
    }.get(status, "info")
    
    icon_svg = get_svg_icon(icon_name, size=20, color=color)
    details_html = f'<div style="margin-top:4px;font-size:12px;color:#94a3b8;">{details}</div>' if details else ""
    
    return (
        f'<div style="display:flex;align-items:flex-start;gap:12px;padding:12px 16px;border-radius:8px;'
        f'background-color:{color}10;border:1px solid {color}30;margin:10px 0;">'
        f'<div style="margin-top:2px;">{icon_svg}</div>'
        f'<div style="flex:1;">'
        f'<div style="font-size:14px;font-weight:500;color:#f8fafc;">{message}</div>'
        f'{details_html}'
        f'</div>'
        f'</div>'
    )
