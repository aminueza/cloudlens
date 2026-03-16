"""Minimal SVG exporter — generates static network diagrams."""

from graph.constants import ENV_COLORS, PROVIDER_COLORS
from graph.helpers import esc


def build_svg(scope: str, structured: dict) -> str:
    networks = structured.get("networks", [])
    structured.get("peerings", [])
    if not networks:
        return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 100"><text x="200" y="50" text-anchor="middle" fill="#888" font-size="14">No topology data</text></svg>'

    box_w, box_h = 260, 120
    pad, cols = 30, 3
    rows = (len(networks) + cols - 1) // cols
    total_w = cols * (box_w + pad) + pad
    total_h = rows * (box_h + pad) + pad + 60

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total_w} {total_h}" font-family="Segoe UI,sans-serif">',
        f'<rect width="{total_w}" height="{total_h}" fill="#0D0D1A" rx="8"/>',
    ]

    for i, net in enumerate(networks):
        col, row = i % cols, i // cols
        x = pad + col * (box_w + pad)
        y = pad + row * (box_h + pad)
        env = net.get("env", "other")
        provider = net.get("provider", "")
        border = PROVIDER_COLORS.get(provider, ENV_COLORS.get(env, "#64748b"))
        name = esc(net.get("name", "?"))
        addr = esc(", ".join(net.get("addressSpace", [])))
        res_count = len(net.get("resources", [])) + len(net.get("securityGroups", []))
        subnet_count = len(net.get("subnets", []))

        parts.append(
            f'<rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" rx="8" fill="#1a1d27" stroke="{border}" stroke-width="2"/>'
        )
        parts.append(
            f'<text x="{x + 10}" y="{y + 20}" fill="#e2e8f0" font-size="12" font-weight="700">{name}</text>'
        )
        parts.append(
            f'<text x="{x + 10}" y="{y + 36}" fill="#64748b" font-size="9">{addr}</text>'
        )
        parts.append(
            f'<text x="{x + 10}" y="{y + 52}" fill="#94a3b8" font-size="9">{provider.upper()} | {env.upper()} | {res_count} resources | {subnet_count} subnets</text>'
        )

    parts.append(
        f'<text x="{total_w // 2}" y="{total_h - 16}" fill="#444" font-size="9" text-anchor="middle">'
        f"CloudLens \u00b7 {scope}</text>"
    )
    parts.append("</svg>")
    return "\n".join(parts)
