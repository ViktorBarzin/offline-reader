"""/api/captures — create, list, read, delete, refresh; serve manifest + Pages.

Every route depends on ``current_username`` (identity is enforced by the
middleware; the dependency also documents each route as authenticated).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import FileResponse, Response

from offline_reader_api.auth import current_username
from offline_reader_api.deps import get_service, get_session
from offline_reader_api.errors import ApiError
from offline_reader_api.models import Capture
from offline_reader_api.schemas import CaptureCreate, CaptureOut
from offline_reader_api.service import CaptureService

router = APIRouter(prefix="/captures", tags=["captures"])


@router.post("", response_model=CaptureOut, status_code=201)
async def create_capture(
    body: CaptureCreate,
    username: str = Depends(current_username),
    session: AsyncSession = Depends(get_session),
    service: CaptureService = Depends(get_service),
) -> CaptureOut:
    """Create a Capture and kick off its crawl (status ``crawling`` on success)."""
    capture = await service.create(session, body)
    return CaptureOut.model_validate(capture)


@router.get("", response_model=list[CaptureOut])
async def list_captures(
    username: str = Depends(current_username),
    session: AsyncSession = Depends(get_session),
    service: CaptureService = Depends(get_service),
) -> list[CaptureOut]:
    captures = await service.list_all(session)
    return [CaptureOut.model_validate(c) for c in captures]


async def _require_capture(session: AsyncSession, service: CaptureService, cid: str) -> Capture:
    capture = await service.get(session, cid)
    if capture is None:
        raise ApiError(404, "not_found", "capture not found")
    return capture


@router.get("/{cid}", response_model=CaptureOut)
async def get_capture(
    cid: str,
    username: str = Depends(current_username),
    session: AsyncSession = Depends(get_session),
    service: CaptureService = Depends(get_service),
) -> CaptureOut:
    """Read one Capture; refresh its status from the runner if still in flight."""
    capture = await _require_capture(session, service, cid)
    capture = await service.advance(session, capture)
    return CaptureOut.model_validate(capture)


@router.delete("/{cid}", status_code=204)
async def delete_capture(
    cid: str,
    username: str = Depends(current_username),
    session: AsyncSession = Depends(get_session),
    service: CaptureService = Depends(get_service),
) -> Response:
    """Delete a Capture's files and its row."""
    capture = await _require_capture(session, service, cid)
    await service.delete(session, capture)
    return Response(status_code=204)


@router.post("/{cid}/refresh", response_model=CaptureOut)
async def refresh_capture(
    cid: str,
    username: str = Depends(current_username),
    session: AsyncSession = Depends(get_session),
    service: CaptureService = Depends(get_service),
) -> CaptureOut:
    """Re-crawl the Capture, replacing its Pages in place."""
    capture = await _require_capture(session, service, cid)
    capture = await service.refresh(session, capture)
    return CaptureOut.model_validate(capture)


@router.get("/{cid}/manifest")
async def get_manifest(
    cid: str,
    username: str = Depends(current_username),
    session: AsyncSession = Depends(get_session),
    service: CaptureService = Depends(get_service),
) -> FileResponse:
    """The Capture's ``manifest.json`` (404 until the crawl is done)."""
    capture = await _require_capture(session, service, cid)
    path = service.manifest_file(cid)
    if capture.status != "done" or not path.is_file():
        raise ApiError(404, "not_ready", "manifest not available")
    return FileResponse(path, media_type="application/json")


@router.get("/{cid}/pages/{page_id}")
async def get_page(
    cid: str,
    page_id: str,
    username: str = Depends(current_username),
    session: AsyncSession = Depends(get_session),
    service: CaptureService = Depends(get_service),
) -> FileResponse:
    """One captured Page as ``text/html`` (404 if unknown or missing)."""
    await _require_capture(session, service, cid)
    path = service.page_file(cid, page_id)
    if path is None:
        raise ApiError(404, "not_found", "page not found")
    return FileResponse(path, media_type="text/html")
