"""Importing this package registers every task handler with the runner."""

from app.workers.handlers import analysis, diagnostics, documents, jobs, resumes  # noqa: F401
