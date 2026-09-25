"""Legal, compliance, and public handbook pages.

`/privacy` and `/terms` are required by Microsoft Partner Center's SaaS offer
listing and `appPackage/manifest.json`'s `developer.privacyUrl`/`termsOfUseUrl`.
`/guide` is the Digital User Guide / Agent Handbook for Copilot and Teams users.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from api.templates import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def homepage(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {})


@router.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "privacy.html", {})


@router.get("/terms", response_class=HTMLResponse)
async def terms(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "terms.html", {})


@router.get("/guide", response_class=HTMLResponse)
async def guide(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "guide.html", {})
