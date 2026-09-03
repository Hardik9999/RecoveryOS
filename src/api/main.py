"""
RecoveryOS — FastAPI Application

This is the application entry point. It mounts all route modules and
provides the OpenAPI schema.

The API layer delegates ALL business logic to the existing RecoveryOS
domain components (Phases 1–7). No decision logic lives here.
"""
import logging
from fastapi import FastAPI

from src.api.routes import health, payments, recovery, analytics

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s"
)

app = FastAPI(
    title="RecoveryOS",
    description=(
        "AI-powered payment recovery decision and orchestration platform. "
        "RecoveryOS uses predictive models, economic analysis, and deterministic "
        "policy guardrails to intelligently recover failed payments."
    ),
    version="0.8.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Mount routes
app.include_router(health.router)
app.include_router(payments.router)
app.include_router(recovery.router)
app.include_router(analytics.router)
