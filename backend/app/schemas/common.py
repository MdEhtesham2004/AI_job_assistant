from pydantic import BaseModel


class Page[ItemT](BaseModel):
    """Phase 1 §3.3 list format."""

    items: list[ItemT]
    total: int
    page: int
    page_size: int
