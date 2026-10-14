from typing import Any

from fastapi import APIRouter, Request, UploadFile

from app.api.deps import ApprovedUser, DbSession
from app.core.errors import ValidationAppError
from app.services.legacy_import import MAX_BYTES, import_csv

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post(
    "/legacy",
    summary="Import a CSV export of the old Google Sheets (job list or LinkedIn Leads)",
)
async def import_legacy(
    file: UploadFile, request: Request, db: DbSession, user: ApprovedUser
) -> dict[str, Any]:
    name = (file.filename or "").lower()
    if not name.endswith(".csv"):
        raise ValidationAppError("Choose a .csv file (File › Download › CSV in Google Sheets).")
    data = await file.read(MAX_BYTES + 1)
    result = await import_csv(db, user.id, data, request.app.state.domain_checker)
    return result.as_dict()
