"""Legal & compliance pages (Declarative Agent Architecture Pivot).

`/privacy` and `/terms` are the only two routes from the deleted Jinja2
dashboard (formerly `api/web.py`) that had to survive the pivot: Microsoft
Partner Center's SaaS offer listing and `appPackage/manifest.json`'s
`developer.privacyUrl`/`termsOfUseUrl` both require a reachable, real page at
these URLs. `templates/privacy.html`/`terms.html` themselves were kept as-is
(see the pivot plan's section 3); this module is just the thin route layer
that used to live alongside the now-removed marketing homepage/dashboard
routes in `api/web.py`.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from api.templates import templates

router = APIRouter()


@router.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "privacy.html", {})


@router.get("/terms", response_class=HTMLResponse)
async def terms(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "terms.html", {})
