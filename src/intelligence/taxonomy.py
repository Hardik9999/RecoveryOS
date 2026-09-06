from typing import Dict, TypedDict, Optional

class TaxonomyInfo(TypedDict, total=False):
    category: str
    is_retryable: bool
    severity: str
    network: Optional[str]
    description: Optional[str]
    recommended_action: Optional[str]

# Standardized taxonomy mapping for error codes
# Severity levels: LOW, MEDIUM, HIGH, TERMINAL

FAILURE_TAXONOMY: Dict[str, TaxonomyInfo] = {
    # ─── Legacy / Fallback Codes (for backward compatibility and tests) ───
    "INSUFFICIENT_FUNDS": {
        "category": "USER",
        "is_retryable": True,
        "severity": "MEDIUM",
        "network": "GENERIC",
        "description": "Insufficient funds in account",
        "recommended_action": "SEND_PAYMENT_REMINDER"
    },
    "NETWORK_TIMEOUT": {
        "category": "NETWORK",
        "is_retryable": True,
        "severity": "LOW",
        "network": "GENERIC",
        "description": "Network or switch timeout",
        "recommended_action": "RETRY"
    },
    "CARD_DECLINED": {
        "category": "BANK",
        "is_retryable": True,
        "severity": "MEDIUM",
        "network": "GENERIC",
        "description": "Generic card decline",
        "recommended_action": "SEND_PAYMENT_LINK"
    },
    "FRAUD_SUSPECTED": {
        "category": "FRAUD",
        "is_retryable": False,
        "severity": "TERMINAL",
        "network": "GENERIC",
        "description": "Suspected fraudulent transaction",
        "recommended_action": "STOP"
    },
    "LIMIT_EXCEEDED": {
        "category": "BANK",
        "is_retryable": True,
        "severity": "HIGH",
        "network": "GENERIC",
        "description": "Payment limit exceeded",
        "recommended_action": "SEND_PAYMENT_LINK"
    },
    
    # ─── NPCI (UPI) Error Codes ───
    "NPCI:U69": {
        "category": "USER",
        "is_retryable": True,
        "severity": "MEDIUM",
        "network": "NPCI",
        "description": "Insufficient Funds in Customer Account",
        "recommended_action": "SEND_PAYMENT_REMINDER"
    },
    "NPCI:U90": {
        "category": "NETWORK",
        "is_retryable": True,
        "severity": "LOW",
        "network": "NPCI",
        "description": "Remitter Bank / NPCI Switch Technical Timeout",
        "recommended_action": "RETRY"
    },
    "NPCI:U30": {
        "category": "BANK",
        "is_retryable": True,
        "severity": "HIGH",
        "network": "NPCI",
        "description": "Exceeded Daily / Per-Txn Volume/Amount Limit",
        "recommended_action": "SEND_PAYMENT_LINK"
    },
    "NPCI:U29": {
        "category": "USER",
        "is_retryable": True,
        "severity": "HIGH",
        "network": "NPCI",
        "description": "Invalid MPIN / PIN Retries Exhausted",
        "recommended_action": "SEND_PAYMENT_LINK"
    },
    "NPCI:U68": {
        "category": "FRAUD",
        "is_retryable": False,
        "severity": "TERMINAL",
        "network": "NPCI",
        "description": "High Risk / Suspected Fraud Flagged by NPCI",
        "recommended_action": "STOP"
    },
    "NPCI:U31": {
        "category": "BANK",
        "is_retryable": False,
        "severity": "TERMINAL",
        "network": "NPCI",
        "description": "Account Blocked / Frozen / Dormant VPA",
        "recommended_action": "ESCALATE"
    },
    "NPCI:ZA": {
        "category": "USER",
        "is_retryable": True,
        "severity": "MEDIUM",
        "network": "NPCI",
        "description": "Customer Cancelled / PSP Approval Timeout",
        "recommended_action": "SEND_PAYMENT_REMINDER"
    },

    # ─── VISA / Mastercard Error Codes (ISO 8583) ───
    "VISA:51": {
        "category": "USER",
        "is_retryable": True,
        "severity": "MEDIUM",
        "network": "VISA",
        "description": "Insufficient Funds / Credit Limit Exceeded",
        "recommended_action": "SEND_PAYMENT_REMINDER"
    },
    "MC:51": {
        "category": "USER",
        "is_retryable": True,
        "severity": "MEDIUM",
        "network": "MASTERCARD",
        "description": "Not Sufficient Funds",
        "recommended_action": "SEND_PAYMENT_REMINDER"
    },
    "VISA:05": {
        "category": "BANK",
        "is_retryable": True,
        "severity": "MEDIUM",
        "network": "VISA",
        "description": "Do Not Honor (Generic Bank Decline)",
        "recommended_action": "SEND_PAYMENT_LINK"
    },
    "MC:05": {
        "category": "BANK",
        "is_retryable": True,
        "severity": "MEDIUM",
        "network": "MASTERCARD",
        "description": "Do Not Honor",
        "recommended_action": "SEND_PAYMENT_LINK"
    },
    "VISA:91": {
        "category": "NETWORK",
        "is_retryable": True,
        "severity": "LOW",
        "network": "VISA",
        "description": "Issuer / Switch System Unavailable",
        "recommended_action": "RETRY"
    },
    "MC:96": {
        "category": "NETWORK",
        "is_retryable": True,
        "severity": "LOW",
        "network": "MASTERCARD",
        "description": "System Malfunction",
        "recommended_action": "RETRY"
    },
    "VISA:65": {
        "category": "BANK",
        "is_retryable": True,
        "severity": "HIGH",
        "network": "VISA",
        "description": "Activity Count / Daily Limit Exceeded",
        "recommended_action": "SEND_PAYMENT_LINK"
    },
    "MC:65": {
        "category": "BANK",
        "is_retryable": True,
        "severity": "HIGH",
        "network": "MASTERCARD",
        "description": "Exceeds Withdrawal Limit",
        "recommended_action": "SEND_PAYMENT_LINK"
    },
    "VISA:54": {
        "category": "USER",
        "is_retryable": False,
        "severity": "TERMINAL",
        "network": "VISA",
        "description": "Expired Card",
        "recommended_action": "SEND_PAYMENT_LINK"
    },
    "MC:54": {
        "category": "USER",
        "is_retryable": False,
        "severity": "TERMINAL",
        "network": "MASTERCARD",
        "description": "Expired Card",
        "recommended_action": "SEND_PAYMENT_LINK"
    },
    "VISA:07": {
        "category": "FRAUD",
        "is_retryable": False,
        "severity": "TERMINAL",
        "network": "VISA",
        "description": "Pick Up Card / Suspected Fraud",
        "recommended_action": "STOP"
    },
    "MC:41": {
        "category": "FRAUD",
        "is_retryable": False,
        "severity": "TERMINAL",
        "network": "MASTERCARD",
        "description": "Lost Card - Pick Up",
        "recommended_action": "STOP"
    },

    # ─── Netbanking / Wallet Error Codes ───
    "NB:NET_TIMEOUT": {
        "category": "NETWORK",
        "is_retryable": True,
        "severity": "LOW",
        "network": "NETBANKING",
        "description": "Core Banking Gateway Timeout",
        "recommended_action": "RETRY"
    },
    "NB:AUTH_FAIL": {
        "category": "USER",
        "is_retryable": True,
        "severity": "MEDIUM",
        "network": "NETBANKING",
        "description": "2FA / OTP Verification Timeout",
        "recommended_action": "SEND_PAYMENT_REMINDER"
    },
    "WALLET:LOW_BALANCE": {
        "category": "USER",
        "is_retryable": True,
        "severity": "MEDIUM",
        "network": "WALLET",
        "description": "Pre-paid Wallet Balance Low",
        "recommended_action": "SEND_PAYMENT_REMINDER"
    },

    # ─── Default fallback ───
    "UNKNOWN": {
        "category": "UNKNOWN",
        "is_retryable": False,
        "severity": "TERMINAL",
        "network": "UNKNOWN",
        "description": "Unknown Error",
        "recommended_action": "ESCALATE"
    }
}

def get_taxonomy_info(error_code: str) -> TaxonomyInfo:
    return FAILURE_TAXONOMY.get(error_code, FAILURE_TAXONOMY["UNKNOWN"])
