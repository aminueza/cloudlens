"""SVG export route."""

from fastapi import APIRouter, Request
from fastapi.responses import Response

from api.errors import CloudLensError
from exporters.svg import build_svg

router = APIRouter(tags=["export"])


@router.get("/api/svg/{scope}")
async def export_svg(scope: str, request: Request) -> Response:
    fetcher = request.app.state.fetcher
    structured = fetcher.get_structured(scope)
    if not structured:
        raise CloudLensError(503, "Topology data not available yet")
    svg_content = build_svg(scope, structured)
    return Response(
        content=svg_content,
        media_type="image/svg+xml",
        headers={
            "Content-Disposition": f'attachment; filename="cloudlens-{scope}.svg"'
        },
    )
