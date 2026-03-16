"""SVG export route."""

from fastapi import APIRouter, Request
from fastapi.responses import Response

from api.errors import CloudLensError
from exporters.svg import render_svg
from graph.builder import build_graph

router = APIRouter(tags=["export"])


@router.get("/api/svg/{scope}")
async def export_svg(scope: str, request: Request) -> Response:
    """Export topology as an SVG image."""
    fetcher = request.app.state.fetcher

    data = fetcher.get_topology(scope)
    if data is None:
        try:
            registry = request.app.state.registry
            data = await registry.fetch_topology(scope)
        except Exception as exc:
            raise CloudLensError(503, f"Failed to fetch topology: {exc}") from exc

    if data is None:
        raise CloudLensError(404, f"No topology data for scope '{scope}'")

    graph = build_graph(data.get("nodes", []), data.get("edges", []))
    svg_content = render_svg(graph)

    return Response(
        content=svg_content,
        media_type="image/svg+xml",
        headers={
            "Content-Disposition": f'attachment; filename="cloudlens-{scope}.svg"'
        },
    )
