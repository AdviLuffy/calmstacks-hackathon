"""TRACE Forensic Design System & Global Styles."""

FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32">
  <rect width="32" height="32" rx="3" fill="#0c0f12"/>
  <rect x="2" y="2" width="28" height="28" rx="2" fill="none" stroke="#232a35" stroke-width="1.5"/>
  <path d="M16 4 V10 M16 22 V28 M4 16 H10 M22 16 H28" stroke="#d97736" stroke-width="1.75" stroke-linecap="square"/>
  <circle cx="16" cy="16" r="5.5" fill="none" stroke="#f4f3ef" stroke-width="1.5"/>
  <circle cx="16" cy="16" r="2" fill="#d97736"/>
  <path d="M9 9 L11 11 M23 9 L21 11 M9 23 L11 21 M23 23 L21 21" stroke="#38bdf8" stroke-width="1.25"/>
</svg>"""

COMMON_CSS = """
:root {
  --bg-canvas: #0c0f12;
  --bg-surface: #14181f;
  --bg-elevated: #1a2029;
  --bg-inset: #080a0d;
  --border-subtle: #232a35;
  --border-strong: #333d4d;
  --border-active: #d97736;
  --text-primary: #f4f3ef;
  --text-secondary: #c8c7be;
  --text-muted: #7d848f;
  --accent-copper: #d97736;
  --accent-copper-soft: rgba(217, 119, 54, 0.12);
  --accent-cyan: #38bdf8;
  --accent-cyan-soft: rgba(56, 189, 248, 0.10);
  --accent-green: #10b981;
  --accent-green-soft: rgba(16, 185, 129, 0.12);
  --accent-amber: #f59e0b;
  --accent-amber-soft: rgba(245, 158, 11, 0.12);
  --accent-red: #ef4444;
  --accent-red-soft: rgba(239, 68, 68, 0.12);
  --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --font-mono: ui-monospace, SFMono-Regular, "JetBrains Mono", Menlo, Consolas, monospace;
}

* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

html, body {
  background-color: var(--bg-canvas);
  color: var(--text-primary);
  font-family: var(--font-sans);
  font-size: 13.5px;
  line-height: 1.55;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  -webkit-font-smoothing: antialiased;
}

a {
  color: inherit;
  text-decoration: none;
  transition: color 0.15s ease;
}

a:hover {
  color: var(--accent-copper);
}

/* HEADER & GLOBAL NAVIGATION */
header.site-header {
  background-color: var(--bg-surface);
  border-bottom: 1px solid var(--border-subtle);
  position: sticky;
  top: 0;
  z-index: 100;
  padding: 0 1.5rem;
}

.header-inner {
  max-width: 1400px;
  margin: 0 auto;
  height: 58px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1.5rem;
}

.brand-anchor {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  color: var(--text-primary);
  text-decoration: none;
}

.brand-anchor:hover {
  color: var(--text-primary);
}

.brand-glyph {
  width: 26px;
  height: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.brand-text {
  display: flex;
  flex-direction: column;
}

.brand-name {
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 15px;
  letter-spacing: 0.12em;
  color: var(--text-primary);
  line-height: 1.1;
}

.brand-tagline {
  font-family: var(--font-mono);
  font-size: 9.5px;
  letter-spacing: 0.08em;
  color: var(--text-muted);
  text-transform: uppercase;
}

nav.main-nav {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.nav-link {
  font-family: var(--font-mono);
  font-size: 11.5px;
  letter-spacing: 0.04em;
  padding: 0.45rem 0.85rem;
  color: var(--text-secondary);
  border-radius: 2px;
  border: 1px solid transparent;
  transition: all 0.15s ease;
}

.nav-link:hover {
  color: var(--text-primary);
  background: var(--bg-elevated);
  border-color: var(--border-subtle);
  text-decoration: none;
}

.nav-link.active {
  color: var(--text-primary);
  background: var(--bg-canvas);
  border-color: var(--border-strong);
  font-weight: 600;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.env-indicator {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--text-muted);
  background: var(--bg-canvas);
  border: 1px solid var(--border-subtle);
  padding: 0.3rem 0.6rem;
  border-radius: 2px;
}

.env-dot {
  width: 6px;
  height: 6px;
  border-radius: 1px;
  background: var(--accent-green);
}

/* BUTTONS */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  font-family: var(--font-mono);
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  padding: 0.55rem 1.15rem;
  border-radius: 2px;
  cursor: pointer;
  transition: all 0.15s ease;
  border: 1px solid transparent;
  text-decoration: none;
  white-space: nowrap;
}

.btn:hover {
  text-decoration: none;
}

.btn-primary {
  background-color: var(--accent-copper);
  color: #ffffff;
  border-color: var(--accent-copper);
}

.btn-primary:hover {
  background-color: #b8622b;
  border-color: #b8622b;
  color: #ffffff;
}

.btn-secondary {
  background-color: var(--bg-elevated);
  color: var(--text-primary);
  border-color: var(--border-strong);
}

.btn-secondary:hover {
  background-color: var(--border-subtle);
  border-color: var(--text-muted);
  color: var(--text-primary);
}

.btn-ghost {
  background-color: transparent;
  color: var(--text-secondary);
  border-color: var(--border-subtle);
}

.btn-ghost:hover {
  background-color: var(--bg-surface);
  color: var(--text-primary);
  border-color: var(--border-strong);
}

.btn-sm {
  font-size: 10.5px;
  padding: 0.35rem 0.75rem;
}

/* MONOSPACE TAGS & BADGES */
.tag {
  display: inline-flex;
  align-items: center;
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  padding: 0.2rem 0.55rem;
  border-radius: 2px;
  border: 1px solid var(--border-subtle);
  background: var(--bg-canvas);
  color: var(--text-secondary);
  line-height: 1.2;
}

.tag-copper {
  border-color: rgba(217, 119, 54, 0.4);
  background: var(--accent-copper-soft);
  color: #fca566;
}

.tag-green {
  border-color: rgba(16, 185, 129, 0.4);
  background: var(--accent-green-soft);
  color: #6ee7b7;
}

.tag-cyan {
  border-color: rgba(56, 189, 248, 0.4);
  background: var(--accent-cyan-soft);
  color: #7dd3fc;
}

.tag-amber {
  border-color: rgba(245, 158, 11, 0.4);
  background: var(--accent-amber-soft);
  color: #fcd34d;
}

.tag-red {
  border-color: rgba(239, 68, 68, 0.4);
  background: var(--accent-red-soft);
  color: #fca5a5;
}

/* CONTAINERS & LAYOUT */
main.page-main {
  flex: 1;
  padding: 2.5rem 1.5rem;
}

.container-wide {
  max-width: 1400px;
  margin: 0 auto;
}

.container-prose {
  max-width: 880px;
  margin: 0 auto;
}

.container-narrow {
  max-width: 720px;
  margin: 0 auto;
}

/* SECTION HEADINGS */
.section-eyebrow {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--accent-copper);
  margin-bottom: 0.5rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.section-eyebrow::before {
  content: "";
  display: inline-block;
  width: 8px;
  height: 2px;
  background-color: var(--accent-copper);
}

.section-title {
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--text-primary);
  margin-bottom: 0.75rem;
  line-height: 1.25;
}

.section-lead {
  font-size: 14.5px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin-bottom: 2rem;
}

/* DATA TABLES */
.table-container {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: 2px;
  overflow-x: auto;
  margin-bottom: 1.5rem;
}

table.data-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
  font-size: 12.5px;
}

table.data-table th {
  background: var(--bg-canvas);
  font-family: var(--font-mono);
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--text-muted);
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border-subtle);
  white-space: nowrap;
}

table.data-table td {
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-secondary);
}

table.data-table tr:last-child td {
  border-bottom: none;
}

table.data-table tr:hover td {
  background: rgba(255, 255, 255, 0.02);
  color: var(--text-primary);
}

.code-cell {
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--text-primary);
}

.hash-cell {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--accent-cyan);
  word-break: break-all;
}

/* CARD & PANEL SURFACES */
.panel {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: 2px;
  padding: 1.5rem;
  margin-bottom: 1.5rem;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1.25rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid var(--border-subtle);
}

.panel-title {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--text-primary);
}

/* FORM ELEMENTS */
.form-group {
  margin-bottom: 1.25rem;
}

.form-label {
  display: block;
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--text-secondary);
  margin-bottom: 0.4rem;
}

.form-hint {
  font-size: 11.5px;
  color: var(--text-muted);
  margin-top: 0.35rem;
  line-height: 1.4;
}

.form-input, .form-select, .form-textarea {
  width: 100%;
  background: var(--bg-inset);
  border: 1px solid var(--border-subtle);
  border-radius: 2px;
  padding: 0.65rem 0.85rem;
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 12px;
  outline: none;
  transition: border-color 0.15s ease;
}

.form-input:focus, .form-select:focus, .form-textarea:focus {
  border-color: var(--border-active);
}

.form-checkbox-label {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  cursor: pointer;
  padding: 0.75rem;
  background: var(--bg-inset);
  border: 1px solid var(--border-subtle);
  border-radius: 2px;
}

.form-checkbox-label input[type="checkbox"] {
  margin-top: 0.2rem;
  accent-color: var(--accent-copper);
}

/* NOTICES */
.notice {
  font-family: var(--font-mono);
  font-size: 11.5px;
  padding: 0.75rem 1rem;
  border-radius: 2px;
  border: 1px solid var(--border-subtle);
  margin-bottom: 1.5rem;
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
}

.notice-info {
  background: var(--accent-cyan-soft);
  border-color: rgba(56, 189, 248, 0.3);
  color: #bae6fd;
}

.notice-warning {
  background: var(--accent-amber-soft);
  border-color: rgba(245, 158, 11, 0.3);
  color: #fde68a;
}

.notice-success {
  background: var(--accent-green-soft);
  border-color: rgba(16, 185, 129, 0.3);
  color: #a7f3d0;
}

.notice-danger {
  background: var(--accent-red-soft);
  border-color: rgba(239, 68, 68, 0.3);
  color: #fca5a5;
}

/* FOOTER */
footer.site-footer {
  background: var(--bg-surface);
  border-top: 1px solid var(--border-subtle);
  padding: 2.5rem 1.5rem;
  margin-top: auto;
}

.footer-inner {
  max-width: 1400px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.footer-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 2rem;
}

.footer-brand {
  max-width: 380px;
}

.footer-links-grid {
  display: flex;
  gap: 3.5rem;
  flex-wrap: wrap;
}

.footer-col-title {
  font-family: var(--font-mono);
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-muted);
  margin-bottom: 0.75rem;
}

.footer-col-links {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.footer-col-links a {
  font-size: 12.5px;
  color: var(--text-secondary);
}

.footer-col-links a:hover {
  color: var(--text-primary);
}

.footer-bottom {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 1rem;
  padding-top: 1.5rem;
  border-top: 1px solid var(--border-subtle);
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
}

/* RESPONSIVE */
@media (max-width: 768px) {
  nav.main-nav {
    display: none;
  }
  .header-actions {
    margin-left: auto;
  }
  .footer-links-grid {
    gap: 2rem;
  }
}
"""
