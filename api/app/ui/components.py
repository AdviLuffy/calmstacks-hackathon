"""TRACE Reusable UI Components: Header, Sub-Navigation, Footer, and Shell."""

from __future__ import annotations

from app.ui.styles import COMMON_CSS, FAVICON_SVG


def render_brand_glyph() -> str:
    return """<svg class="brand-glyph" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect x="2" y="2" width="20" height="20" rx="3" fill="#14181f" stroke="#333d4d" stroke-width="1.5"/>
  <path d="M12 4V8M12 16V20M4 12H8M16 12H20" stroke="#d97736" stroke-width="1.75" stroke-linecap="square"/>
  <circle cx="12" cy="12" r="3" stroke="#f4f3ef" stroke-width="1.5"/>
  <circle cx="12" cy="12" r="1" fill="#d97736"/>
</svg>"""


def render_header(active_route: str = "") -> str:
    routes = [
        ("/", "home", "Home"),
        ("/product", "product", "Product"),
        ("/investigations", "investigations", "Investigations"),
        ("/investigations/new", "new_analysis", "New Analysis"),
        ("/about", "about", "About"),
    ]

    links_html = []
    for href, key, label in routes:
        is_active = "active" if active_route == key else ""
        links_html.append(f'<a href="{href}" class="nav-link {is_active}">{label}</a>')

    nav_items = "\n      ".join(links_html)

    return f"""<header class="site-header">
  <div class="header-inner">
    <a href="/" class="brand-anchor" title="TRACE Systems">
      {render_brand_glyph()}
      <div class="brand-text">
        <span class="brand-name">CalmStacks TRACE</span>
        <span class="brand-tagline">Forensic Evidence &amp; Intelligence</span>
      </div>
    </a>

    <nav class="main-nav">
      {nav_items}
      <a href="/docs" target="_blank" class="nav-link" title="Open API Documentation">[API Specs]</a>
    </nav>

    <div class="header-actions">
      <div class="env-indicator" title="Local volatile execution mode">
        <span class="env-dot"></span>
        <span id="utc-clock">UTC --:--:--Z</span>
      </div>
      <a href="/investigations/new" class="btn btn-primary btn-sm">+ New Analysis</a>
    </div>
  </div>
</header>
"""


def render_investigation_subnav(session_id: str, active_tab: str = "overview") -> str:
    tabs = [
        (f"/investigations/{session_id}", "overview", "Overview & Report"),
        (f"/investigations/{session_id}/evidence", "evidence", "Evidence Explorer"),
        (f"/investigations/{session_id}/provenance", "provenance", "Provenance Ledger"),
        (f"/investigations/{session_id}/bundle", "bundle", "Raw Bundle JSON"),
    ]

    tabs_html = []
    for href, key, label in tabs:
        is_active = "active" if active_tab == key else ""
        tabs_html.append(f'<a href="{href}" class="nav-link {is_active}">[{label}]</a>')

    joined_tabs = "\n      ".join(tabs_html)

    return f"""<div style="background: var(--bg-surface); border-bottom: 1px solid var(--border-subtle); padding: 0.75rem 1.5rem; margin-bottom: 2rem;">
  <div class="container-wide" style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 1rem;">
    <div style="display: flex; align-items: center; gap: 0.75rem; font-family: var(--font-mono); font-size: 12px;">
      <a href="/investigations" style="color: var(--text-muted);">&larr; Investigations</a>
      <span style="color: var(--border-strong);">/</span>
      <span style="color: var(--accent-cyan); font-weight: 700;">{session_id}</span>
    </div>
    <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
      {joined_tabs}
    </div>
  </div>
</div>
"""


def render_footer() -> str:
    return """<footer class="site-footer">
  <div class="footer-inner">
    <div class="footer-top">
      <div class="footer-brand">
        <div style="display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.75rem;">
          <span style="font-family: var(--font-mono); font-weight: 700; font-size: 14px; letter-spacing: 0.1em; color: var(--text-primary);">CalmStacks TRACE</span>
          <span class="tag tag-copper">FORENSIC SUITE</span>
        </div>
        <p style="font-size: 12.5px; color: var(--text-muted); line-height: 1.6;">
          Scientific, deterministic digital evidence carving, structural reconstruction, and referential grounding for judicial-grade forensics.
        </p>
      </div>

      <div class="footer-links-grid">
        <div>
          <div class="footer-col-title">Platform</div>
          <ul class="footer-col-links">
            <li><a href="/investigations">Investigations Workspace</a></li>
            <li><a href="/investigations/new">New Evidence Analysis</a></li>
            <li><a href="/product">Forensic Pipeline Architecture</a></li>
            <li><a href="/docs" target="_blank">FastAPI Schema &amp; Endpoints</a></li>
          </ul>
        </div>

        <div>
          <div class="footer-col-title">Standards &amp; Governance</div>
          <ul class="footer-col-links">
            <li><a href="/about">System Principles</a></li>
            <li><a href="/privacy">Evidentiary Privacy &amp; Zero-Telemetry</a></li>
            <li><a href="/terms">Terms of Examination &amp; Admissibility</a></li>
          </ul>
        </div>
      </div>
    </div>

    <div class="footer-bottom">
      <div>ISO/IEC 27037:2012 Evidentiary Governance &bull; NIST SP 800-86 Forensic Invariants &bull; Daubert/Frye Admissibility</div>
      <div>TRACE &bull; Authentic Byte Provenance Engine</div>
    </div>
  </div>
</footer>

<script>
  function updateClock() {
    const el = document.getElementById('utc-clock');
    if (el) {
      const now = new Date();
      el.textContent = 'UTC ' + now.toISOString().substring(11, 19) + 'Z';
    }
  }
  setInterval(updateClock, 1000);
  updateClock();
</script>
"""


def wrap_page(
    *,
    title: str,
    content: str,
    active_route: str = "",
    extra_head: str = "",
    extra_scripts: str = "",
) -> str:
    """Wrap content in standard HTML5 page shell with TRACE design system."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} &mdash; CalmStacks TRACE</title>
  <link rel="icon" type="image/svg+xml" href="/favicon.svg">
  <style>
{COMMON_CSS}
  </style>
  {extra_head}
</head>
<body>
  {render_header(active_route)}
  {content}
  {render_footer()}
  {extra_scripts}
</body>
</html>
"""
