def format_currency(value: float, currency: str = "₹") -> str:
    """Format a monetary value into a clean, human-readable string."""
    if value is None:
        return f"{currency}0.00"
    
    if value >= 10000000: # Crores
        return f"{currency}{value/10000000:.2f}Cr"
    elif value >= 100000: # Lakhs
        return f"{currency}{value/100000:.2f}L"
    elif value >= 1000: # Thousands
        return f"{currency}{value:,.0f}"
    else:
        return f"{currency}{value:,.2f}"

def format_percentage(value: float) -> str:
    """Format a decimal probability/rate into a percentage string."""
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%"

def format_status_color(status: str) -> str:
    """Return a Streamlit/HTML color for semantic statuses."""
    status = str(status).upper()
    if status in ("SUCCESS", "RECOVERED", "ALLOWED"):
        return "green"
    elif status in ("FAILED", "FAILED_TERMINAL", "DENIED", "ERROR"):
        return "red"
    elif status in ("STOPPED", "WARNING"):
        return "orange"
    else:
        return "blue"
        
def format_action_name(action: str) -> str:
    """Make raw enum actions more readable."""
    if not action:
        return "None"
    return action.replace("_", " ").title()
