from typing import Dict, TypedDict

class TaxonomyInfo(TypedDict):
    category: str
    is_retryable: bool
    severity: str

# Standardized taxonomy mapping for error codes
# Severity levels: LOW, MEDIUM, HIGH, TERMINAL

FAILURE_TAXONOMY: Dict[str, TaxonomyInfo] = {
    "INSUFFICIENT_FUNDS": {
        "category": "USER",
        "is_retryable": True,
        "severity": "MEDIUM"
    },
    "NETWORK_TIMEOUT": {
        "category": "NETWORK",
        "is_retryable": True,
        "severity": "LOW"
    },
    "CARD_DECLINED": {
        "category": "BANK",
        "is_retryable": True,
        "severity": "MEDIUM"
    },
    "FRAUD_SUSPECTED": {
        "category": "FRAUD",
        "is_retryable": False,
        "severity": "TERMINAL"
    },
    "LIMIT_EXCEEDED": {
        "category": "BANK",
        "is_retryable": True,
        "severity": "HIGH"
    },
    # Default fallback
    "UNKNOWN": {
        "category": "UNKNOWN",
        "is_retryable": False,
        "severity": "TERMINAL"
    }
}

def get_taxonomy_info(error_code: str) -> TaxonomyInfo:
    return FAILURE_TAXONOMY.get(error_code, FAILURE_TAXONOMY["UNKNOWN"])
