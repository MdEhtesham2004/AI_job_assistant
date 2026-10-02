from urllib.parse import quote

from fastapi import APIRouter, Request, Response

from app.api.deps import SettingsDep
from app.core.errors import NotFoundError
from app.core.security import InvalidTokenError, decode_file_token

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/{token}", summary="Download a file through a short-lived signed link")
async def download(token: str, request: Request, settings: SettingsDep) -> Response:
    """No Authorization header needed: the signed token is the permission (Phase 1 §6)."""
    try:
        claims = decode_file_token(token, settings.secret_key)
    except InvalidTokenError as exc:
        raise NotFoundError("This download link is invalid or has expired.") from exc

    data = await request.app.state.storage.read(claims.key)
    return Response(
        content=data,
        media_type=claims.content_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(claims.filename)}",
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
