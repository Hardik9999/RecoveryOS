import os
import requests
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("recoveryos.ui.api_client")

# Get API URL from env, defaulting to localhost for local dev
API_BASE_URL = os.getenv("RECOVERYOS_API_URL", "http://localhost:8000")
TIMEOUT_SEC = 30  # Reasonable timeout for the recovery operations

class APIClientError(Exception):
    """Base exception for API client errors."""
    pass

class APIClient:
    """Client for the RecoveryOS FastAPI backend."""

    @staticmethod
    def _handle_response(response: requests.Response) -> Dict[str, Any]:
        """Parse response and handle common HTTP errors."""
        try:
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            try:
                error_data = response.json()
                detail = error_data.get("detail", str(e))
                raise APIClientError(f"API Error: {detail}") from e
            except ValueError:
                raise APIClientError(f"API Error: {response.status_code} - {response.text}") from e
        except requests.exceptions.RequestException as e:
            raise APIClientError(f"Connection failed: {str(e)}") from e

    @staticmethod
    def get_health() -> Dict[str, Any]:
        """Check API health."""
        try:
            resp = requests.get(f"{API_BASE_URL}/health", timeout=5)
            return APIClient._handle_response(resp)
        except requests.exceptions.RequestException:
            return {"status": "unreachable"}

    @staticmethod
    def get_analytics_summary() -> Dict[str, Any]:
        """Get system-wide analytics summary."""
        resp = requests.get(f"{API_BASE_URL}/analytics/summary", timeout=10)
        return APIClient._handle_response(resp)

    @staticmethod
    def get_payments(status: Optional[str] = None, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        """List payments, optionally filtered by status."""
        params = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        resp = requests.get(f"{API_BASE_URL}/payments", params=params, timeout=10)
        return APIClient._handle_response(resp)

    @staticmethod
    def get_payment_details(payment_id: str) -> Dict[str, Any]:
        """Get detailed view of a single payment."""
        resp = requests.get(f"{API_BASE_URL}/payments/{payment_id}", timeout=10)
        return APIClient._handle_response(resp)

    @staticmethod
    def recover_payment(payment_id: str) -> Dict[str, Any]:
        """Trigger the recovery agent pipeline for a specific payment."""
        resp = requests.post(f"{API_BASE_URL}/payments/{payment_id}/recover", timeout=TIMEOUT_SEC)
        return APIClient._handle_response(resp)

    @staticmethod
    def run_batch_recovery(limit: int = 100) -> Dict[str, Any]:
        """Process a batch of eligible failed payments."""
        resp = requests.post(f"{API_BASE_URL}/recovery/batch", json={"limit": limit}, timeout=TIMEOUT_SEC * 5)
        return APIClient._handle_response(resp)

    @staticmethod
    def get_escalation_queue(limit: int = 200, offset: int = 0) -> Dict[str, Any]:
        """Fetch payments flagged for human escalation."""
        params = {"limit": limit, "offset": offset}
        resp = requests.get(f"{API_BASE_URL}/payments/escalation-queue", params=params, timeout=10)
        return APIClient._handle_response(resp)
