"""TRACE User Interface exports and backwards-compatible constants."""

from __future__ import annotations

from app.ui.styles import FAVICON_SVG
from app.ui.pages_public import (
    about_page,
    home_page,
    privacy_page,
    product_page,
    terms_page,
)
from app.ui.pages_app import (
    bundle_page,
    evidence_explorer_page,
    investigation_overview_page,
    investigations_list_page,
    new_analysis_page,
    provenance_page,
)

# Backwards-compatible constants for main.py and tests
DASHBOARD_HTML = home_page()
PRIVACY_HTML = privacy_page()
TERMS_HTML = terms_page()

__all__ = [
    "DASHBOARD_HTML",
    "FAVICON_SVG",
    "PRIVACY_HTML",
    "TERMS_HTML",
    "about_page",
    "bundle_page",
    "evidence_explorer_page",
    "home_page",
    "investigation_overview_page",
    "investigations_list_page",
    "new_analysis_page",
    "privacy_page",
    "product_page",
    "provenance_page",
    "terms_page",
]
