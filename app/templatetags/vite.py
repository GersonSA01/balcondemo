# app/templatetags/vite.py
from django import template
from django.conf import settings
from django.utils.safestring import mark_safe
from pathlib import Path
import json

register = template.Library()

@register.simple_tag
def vite_hmr_tags():
    """
    En desarrollo: inyecta HMR y el entry. Usamos mark_safe para evitar que Django
    lo imprima como texto literal (esto te estaba pasando).
    """
    if getattr(settings, "DEBUG", False):
        html = (
            '<script type="module" src="http://localhost:5173/@vite/client"></script>'
            '<script type="module" src="http://localhost:5173/src/main.js"></script>'
        )
        return mark_safe(html)
    return ""

@register.simple_tag
def vite_asset_tags():
    """
    En producción: lee manifest.json y genera tags <link>/<script>.
    """
    if getattr(settings, "DEBUG", False):
        return ""

    manifest_path = Path(settings.BASE_DIR) / "static" / "frontend" / "manifest.json"
    if not manifest_path.exists():
        return mark_safe("<!-- manifest.json no encontrado en /static/frontend -->")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    entry = manifest.get("src/main.js", {})
    tags = []

    for css in entry.get("css", []):
        tags.append(f'<link rel="stylesheet" href="/static/frontend/{css}">')

    if "file" in entry:
        tags.append(f'<script type="module" src="/static/frontend/{entry["file"]}"></script>')

    # CSS adicionales de chunks
    for _, chunk in manifest.items():
        for css in chunk.get("css", []):
            link = f'<link rel="stylesheet" href="/static/frontend/{css}">'
            if link not in tags:
                tags.append(link)

    return mark_safe("\n".join(tags))

