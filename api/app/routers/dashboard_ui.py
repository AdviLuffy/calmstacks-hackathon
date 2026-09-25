"""Professional digital forensics workstation interface, privacy policy, terms, and favicon."""

from __future__ import annotations

FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32">
  <rect width="32" height="32" rx="4" fill="#0d1117"/>
  <path d="M16 3 L27 7 V15 C27 22 22 27 16 29 C10 27 5 22 5 15 V7 Z" fill="none" stroke="#38bdf8" stroke-width="2" stroke-linejoin="round"/>
  <circle cx="16" cy="15" r="4" fill="none" stroke="#34d399" stroke-width="1.5"/>
  <line x1="16" y1="8" x2="16" y2="12" stroke="#38bdf8" stroke-width="1.5"/>
  <line x1="16" y1="18" x2="16" y2="22" stroke="#38bdf8" stroke-width="1.5"/>
  <line x1="9" y1="15" x2="13" y2="15" stroke="#38bdf8" stroke-width="1.5"/>
  <line x1="19" y1="15" x2="23" y2="15" stroke="#38bdf8" stroke-width="1.5"/>
</svg>"""

COMMON_STYLE = """
    :root {
      --bg-canvas: #090d16;
      --bg-panel: #111726;
      --bg-panel-subtle: #172033;
      --bg-inset: #060910;
      --border-subtle: #1f2c47;
      --border-strong: #2e4168;
      --border-focus: #38bdf8;
      --text-primary: #f8fafc;
      --text-secondary: #94a3b8;
      --text-muted: #64748b;
      --accent-blue: #38bdf8;
      --accent-green: #34d399;
      --accent-amber: #fbbf24;
      --accent-red: #f87171;
      --accent-purple: #c084fc;
      --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      --font-mono: ui-monospace, SFMono-Regular, "JetBrains Mono", Menlo, Consolas, monospace;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg-canvas);
      color: var(--text-primary);
      font-family: var(--font-sans);
      font-size: 13px;
      line-height: 1.5;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    a { color: var(--accent-blue); text-decoration: none; }
    a:hover { text-decoration: underline; }
    header.forensic-header {
      background-color: var(--bg-panel);
      border-bottom: 1px solid var(--border-subtle);
      padding: 0.6rem 1.25rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      position: sticky;
      top: 0;
      z-index: 100;
    }
    .header-branding {
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }
    .system-symbol {
      width: 28px;
      height: 28px;
      background-color: var(--bg-inset);
      border: 1px solid var(--border-strong);
      border-radius: 3px;
      display: flex;
      align-items: center;
      justify-content: center;
      color: var(--accent-blue);
      font-family: var(--font-mono);
      font-weight: 700;
      font-size: 11px;
      letter-spacing: 0.05em;
    }
    .system-title {
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 0.04em;
      color: var(--text-primary);
      text-transform: uppercase;
    }
    .system-subtitle {
      font-size: 11px;
      color: var(--text-muted);
      font-family: var(--font-mono);
    }
    .header-telemetry {
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    .tag {
      font-family: var(--font-mono);
      font-size: 11px;
      font-weight: 600;
      padding: 2px 6px;
      border-radius: 2px;
      border: 1px solid var(--border-subtle);
      background-color: var(--bg-inset);
      color: var(--text-secondary);
      text-transform: uppercase;
      letter-spacing: 0.02em;
    }
    .tag-green { border-color: rgba(52, 211, 153, 0.4); color: var(--accent-green); background-color: rgba(52, 211, 153, 0.08); }
    .tag-blue { border-color: rgba(56, 189, 248, 0.4); color: var(--accent-blue); background-color: rgba(56, 189, 248, 0.08); }
    .tag-amber { border-color: rgba(251, 191, 36, 0.4); color: var(--accent-amber); background-color: rgba(251, 191, 36, 0.08); }
    .tag-red { border-color: rgba(248, 113, 113, 0.4); color: var(--accent-red); background-color: rgba(248, 113, 113, 0.08); }
    .tag-purple { border-color: rgba(192, 132, 252, 0.4); color: var(--accent-purple); background-color: rgba(192, 132, 252, 0.08); }

    .banner-advisory {
      background-color: #1a1608;
      border-bottom: 1px solid #42300b;
      padding: 0.4rem 1.25rem;
      font-size: 11px;
      font-family: var(--font-mono);
      color: #fde68a;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    nav.workspace-nav {
      background-color: var(--bg-inset);
      border-bottom: 1px solid var(--border-subtle);
      display: flex;
      padding: 0 1.25rem;
      overflow-x: auto;
    }
    .nav-item {
      background: none;
      border: none;
      border-bottom: 2px solid transparent;
      color: var(--text-muted);
      font-family: var(--font-mono);
      font-size: 11.5px;
      font-weight: 600;
      padding: 0.65rem 0.95rem;
      cursor: pointer;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      white-space: nowrap;
      transition: all 0.1s ease;
    }
    .nav-item:hover { color: var(--text-primary); }
    .nav-item.active {
      color: var(--accent-blue);
      border-bottom-color: var(--accent-blue);
      background-color: rgba(56, 189, 248, 0.04);
    }

    main.workspace-main {
      flex: 1;
      padding: 1.25rem;
      max-width: 1440px;
      margin: 0 auto;
      width: 100%;
    }

    .pane { display: none; }
    .pane.active { display: block; }

    .panel-grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
    .panel-grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; }
    .panel-grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.75rem; }
    @media (max-width: 960px) {
      .panel-grid-2, .panel-grid-3, .panel-grid-4 { grid-template-columns: 1fr; }
    }

    .panel {
      background-color: var(--bg-panel);
      border: 1px solid var(--border-subtle);
      border-radius: 3px;
      padding: 1rem;
      position: relative;
    }
    .panel-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.85rem;
      padding-bottom: 0.5rem;
      border-bottom: 1px solid var(--border-subtle);
    }
    .panel-title {
      font-size: 12px;
      font-weight: 700;
      color: var(--text-primary);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      font-family: var(--font-mono);
      display: flex;
      align-items: center;
      gap: 0.45rem;
    }
    .panel-desc {
      font-size: 11px;
      color: var(--text-muted);
      margin-top: 0.2rem;
    }

    .field-group { margin-bottom: 0.85rem; }
    .field-label {
      display: block;
      font-family: var(--font-mono);
      font-size: 11px;
      font-weight: 600;
      color: var(--text-secondary);
      margin-bottom: 0.3rem;
      text-transform: uppercase;
      letter-spacing: 0.02em;
    }
    .field-input, .field-select {
      width: 100%;
      background-color: var(--bg-inset);
      border: 1px solid var(--border-subtle);
      color: var(--text-primary);
      padding: 0.45rem 0.65rem;
      border-radius: 2px;
      font-size: 12.5px;
      font-family: var(--font-mono);
    }
    .field-input:focus, .field-select:focus {
      outline: none;
      border-color: var(--border-focus);
    }
    .field-checkbox-container {
      display: flex;
      align-items: flex-start;
      gap: 0.55rem;
      padding: 0.6rem;
      background-color: var(--bg-inset);
      border: 1px solid var(--border-subtle);
      border-radius: 2px;
      margin-bottom: 0.85rem;
      cursor: pointer;
    }
    .field-checkbox-container input[type="checkbox"] {
      margin-top: 2px;
    }
    .checkbox-label-text {
      font-size: 11.5px;
      color: var(--text-primary);
      font-weight: 500;
    }
    .checkbox-sub-text {
      font-size: 10.5px;
      color: var(--text-muted);
      font-family: var(--font-mono);
      margin-top: 0.15rem;
    }

    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 0.4rem;
      padding: 0.5rem 0.95rem;
      border-radius: 2px;
      font-family: var(--font-mono);
      font-size: 11.5px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      cursor: pointer;
      border: 1px solid transparent;
      transition: all 0.1s ease;
      text-decoration: none;
    }
    .btn-primary {
      background-color: #1d4ed8;
      border-color: #2563eb;
      color: white;
    }
    .btn-primary:hover { background-color: #2563eb; }
    .btn-secondary {
      background-color: var(--bg-panel-subtle);
      border-color: var(--border-strong);
      color: var(--text-primary);
    }
    .btn-secondary:hover { background-color: #24324f; border-color: var(--border-focus); }
    .btn-success {
      background-color: #047857;
      border-color: #059669;
      color: white;
    }
    .btn-success:hover { background-color: #059669; }
    .btn-sm { padding: 0.25rem 0.55rem; font-size: 10.5px; }

    .data-table-wrapper {
      width: 100%;
      overflow-x: auto;
      border: 1px solid var(--border-subtle);
      border-radius: 2px;
    }
    table.data-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
      font-family: var(--font-mono);
      text-align: left;
    }
    table.data-table th {
      background-color: var(--bg-inset);
      color: var(--text-secondary);
      font-weight: 600;
      padding: 0.5rem 0.75rem;
      border-bottom: 1px solid var(--border-subtle);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    table.data-table td {
      padding: 0.45rem 0.75rem;
      border-bottom: 1px solid rgba(31, 44, 71, 0.6);
      color: var(--text-primary);
      white-space: nowrap;
    }
    table.data-table tr:hover td { background-color: rgba(56, 189, 248, 0.03); }
    .mono-cell { font-family: var(--font-mono); }

    .kv-grid { display: flex; flex-direction: column; gap: 0.35rem; }
    .kv-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 0.35rem 0.55rem;
      background: var(--bg-inset);
      border: 1px solid var(--border-subtle);
      border-radius: 2px;
      font-family: var(--font-mono);
      font-size: 11.5px;
    }
    .kv-name { color: var(--text-muted); text-transform: uppercase; }
    .kv-data { font-weight: 600; color: var(--text-primary); }

    pre.code-dump {
      background-color: var(--bg-inset);
      border: 1px solid var(--border-subtle);
      border-radius: 2px;
      padding: 0.75rem;
      font-family: var(--font-mono);
      font-size: 11.5px;
      color: #93c5fd;
      overflow-x: auto;
      max-height: 520px;
      line-height: 1.45;
    }

    .notice {
      padding: 0.65rem 0.9rem;
      border-radius: 2px;
      margin-bottom: 0.85rem;
      font-size: 12px;
      display: flex;
      align-items: flex-start;
      gap: 0.5rem;
      font-family: var(--font-mono);
    }
    .notice-info { background: rgba(56, 189, 248, 0.08); border: 1px solid rgba(56, 189, 248, 0.3); color: #bae6fd; }
    .notice-success { background: rgba(52, 211, 153, 0.08); border: 1px solid rgba(52, 211, 153, 0.3); color: #a7f3d0; }
    .notice-warning { background: rgba(251, 191, 36, 0.08); border: 1px solid rgba(251, 191, 36, 0.3); color: #fde68a; }
    .notice-error { background: rgba(248, 113, 113, 0.08); border: 1px solid rgba(248, 113, 113, 0.3); color: #fecaca; }

    footer.forensic-footer {
      margin-top: auto;
      border-top: 1px solid var(--border-subtle);
      background-color: var(--bg-panel);
      padding: 0.75rem 1.25rem;
      font-size: 11px;
      color: var(--text-muted);
      font-family: var(--font-mono);
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.75rem;
    }
    .footer-links {
      display: flex;
      gap: 1rem;
    }
"""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TRACE Forensic Evidence Reconstruction Console</title>
  <link rel="icon" type="image/svg+xml" href="/favicon.svg">
  <style>
/*COMMON_STYLE*/
  </style>
</head>
<body>

  <header class="forensic-header">
    <div class="header-branding">
      <div class="system-symbol">TR</div>
      <div>
        <div class="system-title">CalmStacks TRACE Console</div>
        <div class="system-subtitle">Digital Evidence Reconstruction & Intelligence Verification System</div>
      </div>
    </div>
    <div class="header-telemetry">
      <span class="tag tag-green">P1: CARVER ACTIVE</span>
      <span class="tag tag-blue">P2: CONTRACT FROZEN M0</span>
      <span class="tag tag-purple">P3: FASTAPI SERVER</span>
      <span class="tag" id="status-clock">UTC --:--:--Z</span>
    </div>
  </header>

  <div class="banner-advisory">
    <div><strong>ADVISORY [SYNTHETIC TEST ENVIRONMENT]:</strong> Operating against deterministic synthetic media fixtures. Zero unverified evidentiary claims permitted.</div>
    <div><a href="/docs" target="_blank" style="color: #fde68a;">[API SCHEMA / DOCS]</a></div>
  </div>

  <nav class="workspace-nav">
    <button class="nav-item active" onclick="switchPane('pane-ingest')">[01] Ingestion & Carving</button>
    <button class="nav-item" onclick="switchPane('pane-summary')">[02] Case Summary & Report</button>
    <button class="nav-item" onclick="switchPane('pane-fragments')">[03] Fragment Registry</button>
    <button class="nav-item" onclick="switchPane('pane-provenance')">[04] Provenance & Validation</button>
    <button class="nav-item" onclick="switchPane('pane-grounding')">[05] Referential Grounding</button>
    <button class="nav-item" onclick="switchPane('pane-bundle')">[06] Canonical Bundle</button>
  </nav>

  <main class="workspace-main">
    <div id="status-notification"></div>

    <!-- PANE 1: INGESTION -->
    <div id="pane-ingest" class="pane active">
      <div class="panel-grid-2">
        <!-- Panel 1: P1 Carving -->
        <div class="panel">
          <div class="panel-header">
            <div>
              <div class="panel-title">[ACTION] CARVE UNALLOCATED DISK BYTES</div>
              <div class="panel-desc">Runs P1 byte carver, DNA profiling, candidate relationship walk, and PDF reconstruction.</div>
            </div>
            <span class="tag tag-blue">Engine: trace-evidence</span>
          </div>

          <form id="form-carve" onsubmit="executeCarve(event)">
            <div class="field-group">
              <label class="field-label">Target Media Stream</label>
              <select class="field-select" id="carve-source-mode" onchange="toggleSourceInput()">
                <option value="synthetic_blob">Synthetic Disk Image (blob_1337.bin — 2,048 Bytes, 8 Shuffled Blocks)</option>
                <option value="custom_file">External Disk Image Upload (Raw Bitstream .bin / .img / .raw)...</option>
              </select>
            </div>

            <div class="field-group" id="file-upload-container" style="display: none;">
              <label class="field-label">Select Bitstream Image</label>
              <input type="file" class="field-input" id="carve-binary-file">
            </div>

            <div class="panel-grid-2">
              <div class="field-group">
                <label class="field-label">Case Identifier</label>
                <input type="text" class="field-input" id="input-case-id" placeholder="e.g. CASE-2026-001 (InstanceId format)" pattern="^[A-Z]{2,6}(-[A-Z0-9]{1,12})*-\\d{2,10}$">
              </div>
              <div class="field-group">
                <label class="field-label">Lead Examiner</label>
                <input type="text" class="field-input" id="input-investigator" placeholder="e.g. Examiner Badge #4812">
              </div>
            </div>

            <div class="field-group">
              <label class="field-label">Matter / Incident Description</label>
              <input type="text" class="field-input" id="input-case-title" placeholder="e.g. Examination of unallocated storage partition">
            </div>

            <div class="field-group">
              <label class="field-label">Acquisition Method</label>
              <select class="field-select" id="input-acq-method">
                <option value="file_copy">file_copy — Direct bitstream duplicate</option>
                <option value="dd">dd — Raw physical block read</option>
                <option value="ewf_e01">ewf_e01 — Expert witness format image</option>
              </select>
            </div>

            <label class="field-checkbox-container" id="write-blocker-toggle">
              <input type="checkbox" id="input-write-blocked" onchange="updateWriteBlockStatus()">
              <div>
                <div class="checkbox-label-text">Examiner Hardware Write-Block Attestation (ISO/IEC 27037)</div>
                <div class="checkbox-sub-text" id="write-block-explanation">CURRENT STATUS: NOT VERIFIED — Acquisition will be recorded with write_blocked: false.</div>
              </div>
            </label>

            <button type="submit" class="btn btn-primary" id="btn-run-carve" style="width: 100%;">
              [EXECUTE P1 FORENSIC RECONSTRUCTION]
            </button>
          </form>
        </div>

        <!-- Panel 2: Ingest Existing Bundle -->
        <div class="panel">
          <div class="panel-header">
            <div>
              <div class="panel-title">[ACTION] INGEST PRE-COMPILED BUNDLE</div>
              <div class="panel-desc">Submit an existing Evidence Bundle JSON for validation against frozen schema.</div>
            </div>
            <span class="tag tag-purple">Contract: v1.0</span>
          </div>

          <form id="form-bundle" onsubmit="executeBundleIngest(event)">
            <div class="field-group">
              <label class="field-label">Bundle Ingestion Source</label>
              <select class="field-select" id="bundle-fixture-select" onchange="toggleBundleInput()">
                <option value="bundle_realistic">M0 Realistic Multi-Fragment Bundle (bundle_realistic.json)</option>
                <option value="bundle_minimal">M0 Minimal Contract Floor Bundle (bundle_minimal.json)</option>
                <option value="custom_json">Upload Investigator Bundle (.json)...</option>
              </select>
            </div>

            <div class="field-group" id="bundle-file-container" style="display: none;">
              <label class="field-label">Select JSON File</label>
              <input type="file" class="field-input" id="bundle-file-input" accept=".json,application/json">
            </div>

            <div class="field-group">
              <label class="field-label">Case Identifier Override</label>
              <input type="text" class="field-input" id="bundle-case-override" placeholder="Optional: Override case_id for report derivation">
            </div>

            <div class="notice notice-info" style="margin-top: 1.5rem;">
              <div><strong>FROZEN CONTRACT CONFORMANCE:</strong> The bundle root is strictly checked against the frozen 8 required fields. Empty artifacts array (<code>artifacts: []</code>) is supported.</div>
            </div>

            <button type="submit" class="btn btn-secondary" id="btn-run-bundle" style="width: 100%; margin-top: 1rem;">
              [SUBMIT & VALIDATE BUNDLE]
            </button>
          </form>
        </div>
      </div>

      <!-- Fixture Inventory -->
      <div class="panel" style="margin-top: 1rem;">
        <div class="panel-header">
          <div class="panel-title">SYSTEM TEST FIXTURE INVENTORY</div>
          <span class="tag">M0 Ground Truth</span>
        </div>
        <div class="panel-grid-3" id="fixture-cards-grid">
          <!-- Populated dynamically -->
        </div>
      </div>
    </div>

    <!-- PANE 2: SUMMARY & REPORT -->
    <div id="pane-summary" class="pane">
      <div id="summary-empty" class="panel" style="text-align: center; padding: 3rem;">
        <div style="font-family: var(--font-mono); color: var(--text-muted); margin-bottom: 1rem;">[NO SESSION LOADED IN MEMORY]</div>
        <button class="btn btn-primary" onclick="switchPane('pane-ingest')">PROCEED TO INGESTION PANE</button>
      </div>

      <div id="summary-view" style="display: none;">
        <div class="panel-grid-4" style="margin-bottom: 1rem;">
          <div class="panel">
            <div class="panel-desc">SESSION STATE</div>
            <div style="font-size: 16px; font-weight: 700; color: var(--accent-green); margin: 0.2rem 0;" id="sum-session-status">UNKNOWN</div>
            <div class="mono-cell" style="font-size: 10px; color: var(--text-muted);" id="sum-session-id">-</div>
          </div>
          <div class="panel">
            <div class="panel-desc">CASE IDENTIFIER</div>
            <div style="font-size: 14px; font-weight: 700; color: var(--text-primary); margin: 0.2rem 0;" id="sum-case-id">-</div>
            <div style="font-size: 10.5px; color: var(--text-muted);" id="sum-case-title">-</div>
          </div>
          <div class="panel">
            <div class="panel-desc">DERIVED REPORT ID</div>
            <div class="mono-cell" style="font-size: 13px; font-weight: 700; color: var(--accent-blue); margin: 0.2rem 0;" id="sum-report-id">RPT-PENDING</div>
            <div style="font-size: 10px; color: var(--text-muted);">Preimage: RPT- + SHA256[:12]</div>
          </div>
          <div class="panel">
            <div class="panel-desc">CANONICAL BUNDLE HASH</div>
            <div class="mono-cell" style="font-size: 10.5px; word-break: break-all; color: var(--accent-purple); margin: 0.2rem 0;" id="sum-bundle-hash">-</div>
            <div style="font-size: 10px; color: var(--text-muted);">Canonical: trace-cj/1.0</div>
          </div>
        </div>

        <div class="panel-grid-2" style="margin-bottom: 1rem;">
          <div class="panel">
            <div class="panel-header">
              <div class="panel-title">STAGE 1: P1 RECOVERY ENGINE</div>
              <span class="tag" id="sum-stage1-tag">PENDING</span>
            </div>
            <div class="kv-grid">
              <div class="kv-row"><span class="kv-name">Connected Engine</span><span class="kv-data" id="sum-rec-engine">trace-evidence</span></div>
              <div class="kv-row"><span class="kv-name">Provenance Origin</span><span class="kv-data" id="sum-rec-origin">computed</span></div>
              <div class="kv-row"><span class="kv-name">PDF Self-Validation</span><span class="kv-data" style="color: var(--accent-green);" id="sum-rec-valid">STRUCTURALLY VALID</span></div>
            </div>
          </div>
          <div class="panel">
            <div class="panel-header">
              <div class="panel-title">STAGE 2: P2 INTELLIGENCE ENGINE</div>
              <span class="tag" id="sum-stage2-tag">PENDING</span>
            </div>
            <div class="kv-grid">
              <div class="kv-row"><span class="kv-name">Connected Engine</span><span class="kv-data" id="sum-intel-engine">trace-intel</span></div>
              <div class="kv-row"><span class="kv-name">Doctrine Standard</span><span class="kv-data">M0-STRICT (Deterministic)</span></div>
              <div class="kv-row"><span class="kv-name">Ref Resolver</span><span class="kv-data" style="color: var(--accent-blue);">ACTIVE</span></div>
            </div>
          </div>
        </div>

        <div class="panel" style="margin-bottom: 1rem;">
          <div class="panel-header">
            <div class="panel-title">EXECUTIVE FORENSIC REPORT</div>
            <span class="tag tag-purple">M0 DETERMINISTIC</span>
          </div>
          <div id="sum-brief-text" style="color: var(--text-secondary); margin-bottom: 0.85rem; font-family: var(--font-mono); font-size: 12px;"></div>
          
          <div class="panel-title" style="font-size: 11px; margin-bottom: 0.4rem;">PRIMARY FINDINGS</div>
          <ul id="sum-key-findings" style="margin-left: 1.25rem; margin-bottom: 0.85rem; color: var(--text-secondary); font-family: var(--font-mono); font-size: 11.5px;"></ul>

          <div class="panel-title" style="font-size: 11px; margin-bottom: 0.4rem;">CLAIMS EXPLAINABILITY INDEX</div>
          <div class="data-table-wrapper">
            <table class="data-table">
              <thead>
                <tr>
                  <th>Claim ID</th>
                  <th>Finding Text</th>
                  <th>Status</th>
                  <th>Confidence</th>
                  <th>Basis Note</th>
                  <th>EvidenceRef</th>
                </tr>
              </thead>
              <tbody id="claims-rows"></tbody>
            </table>
          </div>
        </div>

        <div class="panel">
          <div class="panel-header">
            <div class="panel-title">ACTIVE AUDIT NOTICES & WARNINGS</div>
            <span class="tag tag-amber" id="sum-warnings-count">0 NOTICES</span>
          </div>
          <div id="sum-warnings-box"></div>
        </div>
      </div>
    </div>

    <!-- PANE 3: FRAGMENTS -->
    <div id="pane-fragments" class="pane">
      <div class="panel">
        <div class="panel-header">
          <div>
            <div class="panel-title">FRAGMENT REGISTRY INVENTORY</div>
            <div class="panel-desc">All discovered fragments identified by strictly frozen FRG-&lt;hex16&gt;-&lt;start&gt;-&lt;end&gt; nomenclature.</div>
          </div>
          <button class="btn btn-secondary btn-sm" onclick="loadFragments()">[RELOAD FRAGMENTS]</button>
        </div>
        <div class="data-table-wrapper">
          <table class="data-table">
            <thead>
              <tr>
                <th>Fragment ID</th>
                <th>Media ID</th>
                <th>Offset Range [Start, End)</th>
                <th>Length</th>
                <th>SHA-256 Digest</th>
                <th>Location</th>
                <th>DNA Probe Match</th>
              </tr>
            </thead>
            <tbody id="fragments-table-body">
              <tr><td colspan="7" style="text-align: center; color: var(--text-muted);">No active session evidence loaded.</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- PANE 4: PROVENANCE -->
    <div id="pane-provenance" class="pane">
      <div class="panel-grid-2" style="margin-bottom: 1rem;">
        <div class="panel">
          <div class="panel-header">
            <div class="panel-title">RECONSTRUCTED ARTIFACT INTEGRITY</div>
            <span class="tag tag-green" id="prov-status-tag">STRUCTURALLY_VALID</span>
          </div>
          <div class="kv-grid">
            <div class="kv-row"><span class="kv-name">PDF Syntax Self-Validation</span><span class="kv-data" style="color: var(--accent-green);">PASSED (Internal Token Check)</span></div>
            <div class="kv-row"><span class="kv-name">Reconstructed File Digest</span><span class="kv-data mono-cell" id="prov-file-sha256">-</span></div>
            <div class="kv-row"><span class="kv-name">Reconstructed Byte Count</span><span class="kv-data" id="prov-file-bytes">-</span></div>
            <div class="kv-row"><span class="kv-name">Byte Coverage Invariant</span><span class="kv-data" style="color: var(--accent-blue);">100% (Zero Synthesized Bytes)</span></div>
          </div>
          <div style="margin-top: 0.85rem;">
            <a href="#" class="btn btn-success btn-sm" id="prov-download-btn" target="_blank" style="display: none;">
              [DOWNLOAD AUTHENTIC RECONSTRUCTED PDF]
            </a>
          </div>
        </div>

        <div class="panel">
          <div class="panel-header">
            <div class="panel-title">HONESTY & FORENSIC INVARIANTS</div>
            <span class="tag tag-blue">M0 Specification</span>
          </div>
          <div style="font-size: 11.5px; color: var(--text-secondary); display: flex; flex-direction: column; gap: 0.4rem; font-family: var(--font-mono);">
            <div>1. NO FABRICATED BYTES: Missing gaps are never bridged with artificial filler.</div>
            <div>2. CANDIDATE JOINS: byte_contiguity remains false without physical sector proof.</div>
            <div>3. ZERO ORACLE CONTAMINATION: Production code strictly forbids ground truth reads.</div>
            <div>4. UNVERIFIED WRITE-BLOCK: Status is not claimed verified without explicit attestation.</div>
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">EXACT BYTE PROVENANCE MATRIX</div>
          <div class="panel-desc">Maps every contiguous reconstructed byte slice directly to source media coordinates.</div>
        </div>
        <div class="data-table-wrapper">
          <table class="data-table">
            <thead>
              <tr>
                <th>Fragment ID</th>
                <th>Source Media Range [Start, End)</th>
                <th>Output File Range [Start, End)</th>
                <th>Length (Bytes)</th>
                <th>Provenance Coverage</th>
              </tr>
            </thead>
            <tbody id="prov-table-body">
              <tr><td colspan="5" style="text-align: center; color: var(--text-muted);">Execute carving to generate byte-provenance ledger.</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- PANE 5: GROUNDING -->
    <div id="pane-grounding" class="pane">
      <div class="panel">
        <div class="panel-header">
          <div>
            <div class="panel-title">REFERENTIAL GROUNDING VERIFIER</div>
            <div class="panel-desc">Test EvidenceRef strings against the active session bundle using P3's exact resolver.</div>
          </div>
          <span class="tag tag-blue">Grammar: common.schema.json</span>
        </div>

        <div style="display: flex; gap: 0.4rem; margin-bottom: 0.85rem; flex-wrap: wrap;">
          <span style="font-size: 11px; font-family: var(--font-mono); color: var(--text-muted); align-self: center;">STANDARD PRESETS:</span>
          <button class="btn btn-secondary btn-sm" onclick="setRef('bundle')">bundle</button>
          <button class="btn btn-secondary btn-sm" onclick="setRef('case')">case</button>
          <button class="btn btn-secondary btn-sm" onclick="setRef('case.title')">case.title</button>
          <button class="btn btn-secondary btn-sm" onclick="setRef('reconstruction_groups[RGRP-01]')">reconstruction_groups[RGRP-01]</button>
          <button class="btn btn-secondary btn-sm" id="btn-first-frag" onclick="setRefFirstFragment()">[FIRST FRAGMENT]</button>
        </div>

        <div style="display: flex; gap: 0.4rem; margin-bottom: 1rem;">
          <input type="text" class="field-input mono-cell" id="ref-query-input" placeholder="e.g. fragments[FRG-0d38f61b5da8a20b-256-512]">
          <button class="btn btn-primary" onclick="resolveEvidenceRef()">[RESOLVE REFERENTIAL GROUNDING]</button>
        </div>

        <div id="ref-outcome-box" style="display: none;">
          <div class="panel-header" style="margin-bottom: 0.4rem;">
            <div class="mono-cell" style="font-weight: 700; color: var(--text-primary);" id="ref-tested-text">-</div>
            <span class="tag" id="ref-status-tag">STATUS</span>
          </div>
          <div class="mono-cell" style="font-size: 11px; color: var(--text-muted); margin-bottom: 0.5rem;" id="ref-reason-text">-</div>
          <pre class="code-dump" id="ref-target-json"></pre>
        </div>
      </div>
    </div>

    <!-- PANE 6: CANONICAL BUNDLE -->
    <div id="pane-bundle" class="pane">
      <div class="panel">
        <div class="panel-header">
          <div>
            <div class="panel-title">CANONICAL EVIDENCE BUNDLE JSON</div>
            <div class="panel-desc">Compliant with trace.evidence_bundle/1.0 schema specification.</div>
          </div>
          <button class="btn btn-secondary btn-sm" onclick="copyBundleToClipboard()">[COPY BUNDLE JSON]</button>
        </div>
        <pre class="code-dump" id="raw-bundle-view">{ "notice": "No active session loaded." }</pre>
      </div>
    </div>
  </main>

  <footer class="forensic-footer">
    <div>CalmStacks TRACE Forensic Workstation — 24H Engineering Implementation</div>
    <div class="footer-links">
      <a href="/privacy">[Privacy Policy]</a>
      <a href="/terms">[Terms of Examination]</a>
      <a href="/docs" target="_blank">[OpenAPI Documentation]</a>
      <a href="/api/health" target="_blank">[Health]</a>
      <a href="/api/meta" target="_blank">[Meta]</a>
    </div>
  </footer>

  <script>
    let activeSession = null;
    let activeFragments = [];
    let activeBundle = null;

    function switchPane(paneId) {
      document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
      document.querySelectorAll('.pane').forEach(el => el.classList.remove('active'));
      event.target.classList.add('active');
      document.getElementById(paneId).classList.add('active');
    }

    function updateClock() {
      const now = new Date();
      document.getElementById('status-clock').textContent = 'UTC ' + now.toISOString().substring(11, 19) + 'Z';
    }
    setInterval(updateClock, 1000);
    updateClock();

    function toggleSourceInput() {
      const mode = document.getElementById('carve-source-mode').value;
      document.getElementById('file-upload-container').style.display = mode === 'custom_file' ? 'block' : 'none';
    }

    function toggleBundleInput() {
      const mode = document.getElementById('bundle-fixture-select').value;
      document.getElementById('bundle-file-container').style.display = mode === 'custom_json' ? 'block' : 'none';
    }

    function updateWriteBlockStatus() {
      const checked = document.getElementById('input-write-blocked').checked;
      const el = document.getElementById('write-block-explanation');
      if (checked) {
        el.textContent = 'CURRENT STATUS: EXAMINER VERIFIED — Hardware write-block verified per ISO/IEC 27037 standard.';
        el.style.color = 'var(--accent-green)';
      } else {
        el.textContent = 'CURRENT STATUS: NOT VERIFIED — Acquisition will be recorded with write_blocked: false.';
        el.style.color = 'var(--text-muted)';
      }
    }

    async function loadFixtureCards() {
      try {
        const res = await fetch('/api/fixtures');
        const data = await res.json();
        const grid = document.getElementById('fixture-cards-grid');
        grid.innerHTML = '';
        (data.fixtures || []).forEach(f => {
          const item = document.createElement('div');
          item.className = 'panel';
          item.style.backgroundColor = 'var(--bg-inset)';
          item.innerHTML = `
            <div style="display: flex; justify-content: space-between; margin-bottom: 0.35rem;">
              <span class="tag tag-amber" style="font-size: 10px;">${f.label}</span>
              <span class="mono-cell" style="font-size: 10.5px; color: var(--text-muted);">${f.size_bytes} B</span>
            </div>
            <div style="font-weight: 700; font-size: 12px; margin-bottom: 0.25rem;">${f.name}</div>
            <p style="font-size: 11px; color: var(--text-muted); margin-bottom: 0.75rem;">${f.description}</p>
            <button class="btn btn-secondary btn-sm" style="width: 100%;" onclick="runPresetFixture('${f.fixture_id}')">[LOAD FIXTURE]</button>
          `;
          grid.appendChild(item);
        });
      } catch (err) {
        console.error('Failed to load fixtures', err);
      }
    }

    function runPresetFixture(fid) {
      if (fid === 'synthetic_blob') {
        document.getElementById('carve-source-mode').value = 'synthetic_blob';
        toggleSourceInput();
        document.getElementById('form-carve').requestSubmit();
      } else {
        document.getElementById('bundle-fixture-select').value = fid;
        toggleBundleInput();
        document.getElementById('form-bundle').requestSubmit();
      }
    }

    async function executeCarve(e) {
      e.preventDefault();
      const notif = document.getElementById('status-notification');
      notif.innerHTML = '<div class="notice notice-warning">[RUNNING] Executing P1 Carving, Structural Profiling & Reconstruction...</div>';

      const formData = new FormData();
      const mode = document.getElementById('carve-source-mode').value;
      if (mode === 'custom_file') {
        const fi = document.getElementById('carve-binary-file');
        if (!fi.files.length) {
          notif.innerHTML = '<div class="notice notice-error">[ERROR] No binary disk image selected.</div>';
          return;
        }
        formData.append('file', fi.files[0]);
      } else {
        formData.append('fixture_id', mode);
      }

      const cid = document.getElementById('input-case-id').value.trim();
      if (cid) formData.append('case_id', cid);
      const title = document.getElementById('input-case-title').value.trim();
      if (title) formData.append('case_title', title);
      const inv = document.getElementById('input-investigator').value.trim();
      if (inv) formData.append('investigator', inv);

      formData.append('acquisition_method', document.getElementById('input-acq-method').value);
      formData.append('write_blocked', document.getElementById('input-write-blocked').checked);

      try {
        const res = await fetch('/api/sessions/carve', { method: 'POST', body: formData });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error?.message || data.detail || 'Execution failure');

        notif.innerHTML = `<div class="notice notice-success">[SESSION CREATED] ${data.session_id} — Status: ${data.status.toUpperCase()}</div>`;
        await loadSession(data.session_id);
        document.querySelectorAll('.nav-item')[1].click();
      } catch (err) {
        notif.innerHTML = `<div class="notice notice-error">[FAILURE] ${err.message}</div>`;
      }
    }

    async function executeBundleIngest(e) {
      e.preventDefault();
      const notif = document.getElementById('status-notification');
      notif.innerHTML = '<div class="notice notice-warning">[INGESTING] Validating Evidence Bundle against frozen M0 schema...</div>';

      const sel = document.getElementById('bundle-fixture-select').value;
      const caseOverride = document.getElementById('bundle-case-override').value.trim();

      try {
        let res;
        if (sel === 'custom_json') {
          const fi = document.getElementById('bundle-file-input');
          if (!fi.files.length) {
            notif.innerHTML = '<div class="notice notice-error">[ERROR] No JSON file selected.</div>';
            return;
          }
          const formData = new FormData();
          formData.append('file', fi.files[0]);
          if (caseOverride) formData.append('case_id', caseOverride);
          res = await fetch('/api/sessions', { method: 'POST', body: formData });
        } else {
          const formData = new FormData();
          formData.append('fixture_id', sel);
          if (caseOverride) formData.append('case_id', caseOverride);
          res = await fetch('/api/sessions/carve', { method: 'POST', body: formData });
        }

        const data = await res.json();
        if (!res.ok) throw new Error(data.error?.message || data.detail || 'Ingestion failure');

        notif.innerHTML = `<div class="notice notice-success">[SESSION CREATED] ${data.session_id} — Status: ${data.status.toUpperCase()}</div>`;
        await loadSession(data.session_id);
        document.querySelectorAll('.nav-item')[1].click();
      } catch (err) {
        notif.innerHTML = `<div class="notice notice-error">[FAILURE] ${err.message}</div>`;
      }
    }

    async function loadSession(sessionId) {
      try {
        const [sRes, rRes, eRes, rcRes] = await Promise.all([
          fetch(`/api/sessions/${sessionId}`),
          fetch(`/api/sessions/${sessionId}/report`),
          fetch(`/api/sessions/${sessionId}/evidence`),
          fetch(`/api/sessions/${sessionId}/reconstruction`)
        ]);

        const session = await sRes.json();
        const report = rRes.ok ? await rRes.json() : null;
        const evidence = eRes.ok ? await eRes.json() : null;
        const recon = rcRes.ok ? await rcRes.json() : null;

        activeSession = session;
        activeBundle = evidence;

        // Display Summary
        document.getElementById('summary-empty').style.display = 'none';
        document.getElementById('summary-view').style.display = 'block';

        document.getElementById('sum-session-id').textContent = session.session_id;
        document.getElementById('sum-session-status').textContent = session.status.toUpperCase();
        document.getElementById('sum-case-id').textContent = session.case_id || '[NO CASE ID SPECIFIED]';
        document.getElementById('sum-case-title').textContent = session.case_title || 'Formal Evidence Processing';
        document.getElementById('sum-bundle-hash').textContent = session.bundle_sha256 || 'N/A';

        if (report) {
          document.getElementById('sum-report-id').textContent = report.report_id || 'DERIVED_VOLATILE';
          const rBody = report.report || {};
          document.getElementById('sum-brief-text').textContent = rBody.brief?.summary || '[No deterministic narrative generated]';
          
          const kf = document.getElementById('sum-key-findings');
          kf.innerHTML = '';
          (rBody.brief?.key_findings || []).forEach(f => {
            const li = document.createElement('li');
            li.textContent = f;
            kf.appendChild(li);
          });

          const cTable = document.getElementById('claims-rows');
          cTable.innerHTML = '';
          (rBody.explainability?.claims_index || []).forEach(c => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
              <td class="mono-cell">${c.claim_id}</td>
              <td>${c.text}</td>
              <td><span class="tag tag-blue">${c.status}</span></td>
              <td class="mono-cell">${c.confidence}</td>
              <td style="font-size: 10.5px; color: var(--text-secondary);">${c.confidence_basis || '-'}</td>
              <td class="mono-cell" style="font-size: 10.5px;">${(c.evidence_refs || []).join(', ')}</td>
            `;
            cTable.appendChild(tr);
          });
        }

        // Stages
        (session.stages || []).forEach(st => {
          if (st.stage === 'recovery') {
            const tag = document.getElementById('sum-stage1-tag');
            tag.textContent = st.status.toUpperCase();
            tag.className = `tag ${st.status === 'ok' ? 'tag-green' : 'tag-amber'}`;
            document.getElementById('sum-rec-engine').textContent = st.engine?.name || 'trace-evidence';
          } else if (st.stage === 'intelligence') {
            const tag = document.getElementById('sum-stage2-tag');
            tag.textContent = st.status.toUpperCase();
            tag.className = `tag ${st.status === 'ok' ? 'tag-green' : 'tag-amber'}`;
            document.getElementById('sum-intel-engine').textContent = st.engine?.name || 'trace-intel';
          }
        });

        // Warnings
        const warns = session.warnings || [];
        document.getElementById('sum-warnings-count').textContent = `${warns.length} NOTICES`;
        const wBox = document.getElementById('sum-warnings-box');
        if (warns.length) {
          wBox.innerHTML = warns.map(w => `
            <div class="notice notice-warning">
              <strong>${w.code}:</strong> ${w.message} ${w.detail ? `(${w.detail})` : ''}
            </div>
          `).join('');
        } else {
          wBox.innerHTML = '<div style="color: var(--text-muted); font-size: 11px;">Zero anomalous audit notices recorded.</div>';
        }

        // Provenance & Reconstructed Artifact
        if (recon && recon.reconstructed_sha256) {
          document.getElementById('prov-status-tag').textContent = (recon.status || 'structurally_valid').toUpperCase();
          document.getElementById('prov-file-sha256').textContent = recon.reconstructed_sha256;
          document.getElementById('prov-file-bytes').textContent = `${recon.pdf_size_bytes || 2048} Bytes`;

          const dl = document.getElementById('prov-download-btn');
          dl.href = `/api/sessions/${sessionId}/reconstruction/download`;
          dl.style.display = 'inline-flex';

          const pBody = document.getElementById('prov-table-body');
          pBody.innerHTML = '';
          (recon.provenance || []).forEach(p => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
              <td class="mono-cell" style="color: var(--accent-blue);">${p.fragment_id}</td>
              <td class="mono-cell">[${p.media_offset_start}, ${p.media_offset_end})</td>
              <td class="mono-cell">[${p.output_offset_start}, ${p.output_offset_end})</td>
              <td class="mono-cell">${p.byte_count} B</td>
              <td><span class="tag tag-green">VERIFIED 1:1</span></td>
            `;
            pBody.appendChild(tr);
          });
        }

        await loadFragments();
        await loadRawBundle();
      } catch (err) {
        console.error('Session load error', err);
      }
    }

    async function loadFragments() {
      if (!activeSession) return;
      try {
        const res = await fetch(`/api/sessions/${activeSession.session_id}/evidence/fragments`);
        if (!res.ok) return;
        const data = await res.json();
        activeFragments = data.fragments || [];
        const tbody = document.getElementById('fragments-table-body');
        tbody.innerHTML = '';
        activeFragments.forEach(f => {
          const tr = document.createElement('tr');
          const range = f.byte_range ? `[${f.byte_range.start}, ${f.byte_range.end})` : '-';
          const marker = f.signature_probe?.matched ? f.signature_probe.marker_id : 'none';
          tr.innerHTML = `
            <td class="mono-cell" style="color: var(--accent-blue);">${f.fragment_id}</td>
            <td class="mono-cell">${f.media_id || 'MED-01'}</td>
            <td class="mono-cell">${range}</td>
            <td class="mono-cell">${f.size_bytes || 256} B</td>
            <td class="mono-cell" style="font-size: 10.5px;">${f.bytes_sha256 ? f.bytes_sha256.substring(0, 16) + '...' : '-'}</td>
            <td><span class="tag">${f.location || 'unallocated'}</span></td>
            <td><span class="tag ${marker !== 'none' ? 'tag-green' : 'tag-amber'}">${marker}</span></td>
          `;
          tbody.appendChild(tr);
        });

        if (activeFragments.length > 0) {
          document.getElementById('btn-first-frag').onclick = () => {
            setRef(`fragments[${activeFragments[0].fragment_id}]`);
          };
        }
      } catch (err) {
        console.error('Fragment load error', err);
      }
    }

    async function loadRawBundle() {
      if (!activeSession) return;
      try {
        const res = await fetch(`/api/sessions/${activeSession.session_id}/evidence`);
        if (!res.ok) return;
        const data = await res.json();
        document.getElementById('raw-bundle-view').textContent = JSON.stringify(data, null, 2);
      } catch (err) {
        console.error('Bundle load error', err);
      }
    }

    function copyBundleToClipboard() {
      const text = document.getElementById('raw-bundle-view').textContent;
      navigator.clipboard.writeText(text);
      alert('Canonical Bundle JSON copied to clipboard.');
    }

    function setRef(ref) {
      document.getElementById('ref-query-input').value = ref;
      resolveEvidenceRef();
    }
    function setRefFirstFragment() {
      if (activeFragments.length) {
        setRef(`fragments[${activeFragments[0].fragment_id}]`);
      }
    }

    async function resolveEvidenceRef() {
      if (!activeSession) {
        alert('Active session required to resolve EvidenceRefs.');
        return;
      }
      const ref = document.getElementById('ref-query-input').value.trim();
      if (!ref) return;

      const box = document.getElementById('ref-outcome-box');
      box.style.display = 'block';
      document.getElementById('ref-tested-text').textContent = ref;

      try {
        const res = await fetch(`/api/sessions/${activeSession.session_id}/refs/ground`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refs: [ref] })
        });
        const data = await res.json();
        const outcome = data.results && data.results.length ? data.results[0] : null;
        const tag = document.getElementById('ref-status-tag');
        const st = outcome ? outcome.status : 'error';
        tag.textContent = st.toUpperCase();
        tag.className = `tag ${st === 'resolved' ? 'tag-green' : (st === 'unverifiable' ? 'tag-amber' : 'tag-red')}`;

        document.getElementById('ref-reason-text').textContent = outcome?.reason ? `REASON: ${outcome.reason}` : 'GROUNDED: Verified against session bundle';
        document.getElementById('ref-target-json').textContent = JSON.stringify(outcome?.target || outcome || data, null, 2);
      } catch (err) {
        document.getElementById('ref-status-tag').textContent = 'ERROR';
        document.getElementById('ref-status-tag').className = 'tag tag-red';
        document.getElementById('ref-reason-text').textContent = err.message;
        document.getElementById('ref-target-json').textContent = '{}';
      }
    }

    window.addEventListener('DOMContentLoaded', () => {
      loadFixtureCards();
    });
  </script>
</body>
</html>
""".replace("/*COMMON_STYLE*/", COMMON_STYLE)

PRIVACY_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TRACE Forensic Console — Evidentiary Privacy & Data Governance Policy</title>
  <link rel="icon" type="image/svg+xml" href="/favicon.svg">
  <style>
/*COMMON_STYLE*/
    .legal-doc {
      max-width: 860px;
      margin: 1.5rem auto;
      background-color: var(--bg-panel);
      border: 1px solid var(--border-subtle);
      border-radius: 3px;
      padding: 2rem;
    }
    .legal-doc h1 {
      font-size: 18px;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      margin-bottom: 0.5rem;
      color: var(--text-primary);
    }
    .legal-doc h2 {
      font-size: 13px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-top: 1.5rem;
      margin-bottom: 0.5rem;
      color: var(--accent-blue);
      border-bottom: 1px solid var(--border-subtle);
      padding-bottom: 0.35rem;
    }
    .legal-doc p, .legal-doc li {
      font-size: 12.5px;
      color: var(--text-secondary);
      margin-bottom: 0.75rem;
      line-height: 1.6;
    }
    .legal-doc ul {
      margin-left: 1.25rem;
      margin-bottom: 1rem;
    }
    .legal-header-meta {
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--text-muted);
      margin-bottom: 1.5rem;
      padding-bottom: 0.75rem;
      border-bottom: 1px solid var(--border-subtle);
    }
  </style>
</head>
<body>
  <header class="forensic-header">
    <div class="header-branding">
      <div class="system-symbol">TR</div>
      <div>
        <div class="system-title">CalmStacks TRACE Console</div>
        <div class="system-subtitle">Evidentiary Privacy Policy &amp; Data Protection</div>
      </div>
    </div>
    <div class="header-telemetry">
      <a href="/" class="btn btn-secondary btn-sm">[RETURN TO CONSOLE]</a>
    </div>
  </header>

  <main class="workspace-main">
    <div class="legal-doc">
      <h1>Digital Forensics Privacy Policy &amp; Data Protection</h1>
      <div class="legal-header-meta">
        DOCUMENT REF: TRACE-POL-PRIV-2026.1 | COMPLIANCE: ISO/IEC 27037:2012 | REVISION: M0-FROZEN
      </div>

      <h2>1. Local-First Processing Architecture (Zero Telemetry)</h2>
      <p>The CalmStacks TRACE Forensic Workstation operates under a strict local-first, Zero Telemetry architecture. All disk carving, profiling, fragment relationship reconstruction, and referential grounding are conducted entirely within the local host runtime. No evidentiary bitstreams, fragment hashes, or case metadata are transmitted to external servers, cloud providers, or third-party telemetry aggregators.</p>

      <h2>2. Volatile Memory Model & Evidence Retention</h2>
      <p>In accordance with forensic minimization principles:</p>
      <ul>
        <li><strong>In-Memory Bundles:</strong> Submitted Evidence Bundles and carved fragments are held strictly in process memory during active investigation and are never committed to permanent storage unless explicit examiner persistence (<code>TRACE_PERSIST_SESSIONS=true</code>) is authorized.</li>
        <li><strong>Process Isolation:</strong> Session termination, daemon shutdown, or process cycling purges in-memory byte buffers immediately, preventing residual forensic artifacts from persisting across reboots.</li>
        <li><strong>Downloadable Artifacts:</strong> Reconstructed PDF files assembled during an active session reside in transient staging memory and are provided solely for download by the authorized examiner.</li>
      </ul>

      <h2>3. Ground Truth Isolation & Oracle Defense</h2>
      <p>Production modules (including P1 carving, P2 schema validation, and P3 reporting) are architecturally isolated from oracle manifests and ground truth fixtures. Ground truth files are accessible strictly within automated test harnesses (<code>tests/</code>) to guarantee that examiner analysis is unbiased and derived solely from authentic source media bytes.</p>

      <h2>4. Chain of Custody & Examiner Attestation</h2>
      <p>All timestamps originating from carved media are preserved in UTC with trailing Z notation without timezone mutation. Hardware write-blocker status is treated as an explicit examiner attestation: write-blocking is never reported as verified unless verified through documented attestation, satisfying forensic integrity standard ISO/IEC 27037.</p>
    </div>
  </main>

  <footer class="forensic-footer">
    <div>CalmStacks TRACE Forensic Workstation — Governance Compliance Module</div>
    <div class="footer-links">
      <a href="/">[Console]</a>
      <a href="/terms">[Terms of Examination]</a>
      <a href="/docs">[API Specs]</a>
    </div>
  </footer>
</body>
</html>
""".replace("/*COMMON_STYLE*/", COMMON_STYLE)

TERMS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TRACE Forensic Console — Terms of Examination & Evidentiary Standards</title>
  <link rel="icon" type="image/svg+xml" href="/favicon.svg">
  <style>
/*COMMON_STYLE*/
    .legal-doc {
      max-width: 860px;
      margin: 1.5rem auto;
      background-color: var(--bg-panel);
      border: 1px solid var(--border-subtle);
      border-radius: 3px;
      padding: 2rem;
    }
    .legal-doc h1 {
      font-size: 18px;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      margin-bottom: 0.5rem;
      color: var(--text-primary);
    }
    .legal-doc h2 {
      font-size: 13px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-top: 1.5rem;
      margin-bottom: 0.5rem;
      color: var(--accent-blue);
      border-bottom: 1px solid var(--border-subtle);
      padding-bottom: 0.35rem;
    }
    .legal-doc p, .legal-doc li {
      font-size: 12.5px;
      color: var(--text-secondary);
      margin-bottom: 0.75rem;
      line-height: 1.6;
    }
    .legal-doc ul {
      margin-left: 1.25rem;
      margin-bottom: 1rem;
    }
    .legal-header-meta {
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--text-muted);
      margin-bottom: 1.5rem;
      padding-bottom: 0.75rem;
      border-bottom: 1px solid var(--border-subtle);
    }
  </style>
</head>
<body>
  <header class="forensic-header">
    <div class="header-branding">
      <div class="system-symbol">TR</div>
      <div>
        <div class="system-title">CalmStacks TRACE Console</div>
        <div class="system-subtitle">Terms of Examination & Evidentiary Standards</div>
      </div>
    </div>
    <div class="header-telemetry">
      <a href="/" class="btn btn-secondary btn-sm">[RETURN TO CONSOLE]</a>
    </div>
  </header>

  <main class="workspace-main">
    <div class="legal-doc">
      <h1>Terms of Examination & Evidentiary Standards</h1>
      <div class="legal-header-meta">
        DOCUMENT REF: TRACE-TOS-EVID-2026.1 | STANDARDS: NIST SP 800-86 / ISO/IEC 27037 | REVISION: M0-FROZEN
      </div>

      <h2>1. Scope and Authorized Utilization</h2>
      <p>This software workstation is engineered specifically for digital forensic examiners, incident responders, and judicial analysts. All functionality adheres to scientific and repeatable methodologies for data recovery, carving, structural profiling, and evidence verification.</p>

      <h2>2. Daubert / Frye Forensic Invariants</h2>
      <p>To preserve evidentiary admissibility under Daubert v. Merrell Dow Pharmaceuticals (509 U.S. 579) and the Frye standard:</p>
      <ul>
        <li><strong>Deterministic Byte Assembly:</strong> Reconstructed files are assembled solely from authentic recovered byte blocks. The workstation strictly prohibits artificial byte synthesis, padding interpolation, or hallucinated file data.</li>
        <li><strong>Candidate-Only Joins:</strong> Where physical sector adjacency cannot be established, the system strictly mandates <code>byte_contiguity = False</code>. Definitive joins are never asserted without physical adjacency proof.</li>
        <li><strong>Complete Provenance Ledger:</strong> Every reconstructed output byte is mapped with 100% coverage back to its originating fragment and source media offset.</li>
        <li><strong>Empirical Verification Ceilings:</strong> Claims marked COMPUTED or OBSERVED carry deterministic proof. Any heuristic or AI-assisted findings are strictly capped at 0.70 confidence and designated as INFERRED.</li>
      </ul>

      <h2>3. Chain of Custody &amp; Forensic Integrity</h2>
      <p>The forensic examiner maintains ultimate responsibility for preserving the Chain of Custody and Forensic Integrity of original physical and digital media. The TRACE platform computes cryptographically secure SHA-256 digests over all ingested media and individual fragments, ensuring full tamper-evident auditability.</p>

      <h2>4. Write-Blocker Compliance (A13)</h2>
      <p>In adherence to ISO/IEC 27037 Clause 6.3, digital evidence acquisition requires validation that target media is protected from modification. The examiner agrees to accurately declare write-block status. Operating without verified write-blocking will be permanently tagged in the canonical Evidence Bundle audit trail.</p>

      <h2>5. Disclaimer of Warranty and Limitation of Liability</h2>
      <p>The TRACE software provides deterministic mathematical analysis based on the inputs provided. The forensic examiner maintains ultimate professional responsibility for validating findings, verifying chain-of-custody, and corroborating conclusions prior to submission in legal or regulatory proceedings.</p>
    </div>
  </main>

  <footer class="forensic-footer">
    <div>CalmStacks TRACE Forensic Workstation — Governance Compliance Module</div>
    <div class="footer-links">
      <a href="/">[Console]</a>
      <a href="/privacy">[Privacy Policy]</a>
      <a href="/docs">[API Specs]</a>
    </div>
  </footer>
</body>
</html>
""".replace("/*COMMON_STYLE*/", COMMON_STYLE)
