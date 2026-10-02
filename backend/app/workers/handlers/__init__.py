"""Importing this package registers every task handler with the runner."""

from app.workers.handlers import diagnostics, jobs, resumes  # noqa: F401
