"""Importing this package registers every task handler with the runner."""

from app.workers.handlers import analysis, diagnostics, jobs, resumes  # noqa: F401
