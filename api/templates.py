"""Shared Jinja2 templating engine (Frontend Jinja2 Template Suite).

One `Jinja2Templates` instance, imported by both `api/web.py` (marketing/
dashboard/legal pages) and `api/marketplace.py` (the landing page) -- kept
in its own module specifically so neither of those two has to import the
other just to share a templates engine.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Callable (not a precomputed value) so a long-lived `uvicorn` process still
# renders the correct year across a Dec 31 -> Jan 1 rollover without a
# restart -- used in templates/base.html's footer as `{{ now_year() }}`.
templates.env.globals["now_year"] = lambda: datetime.now(timezone.utc).year
