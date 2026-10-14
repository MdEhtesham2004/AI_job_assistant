"""Importing this package registers every task handler with the runner."""

from app.workers.handlers import (  # noqa: F401
    analysis,
    automation,
    diagnostics,
    documents,
    hunt,
    interviews,
    jobs,
    outreach,
    prep,
    resumes,
)
