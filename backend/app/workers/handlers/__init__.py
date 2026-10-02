"""Importing this package registers every task handler with the runner."""

from app.workers.handlers import diagnostics, resumes  # noqa: F401
