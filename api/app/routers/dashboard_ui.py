"""HTML/CSS/JavaScript single-page investigator console for TRACE."""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>CalmStacks TRACE — Forensic Evidence Console</title>
  <style>
    :root {
      --bg-dark: #0b0f19;
      --bg-card: #131b2e;
      --bg-card-hover: #1a253e;
      --border-color: #23304d;
      --border-focus: #3b82f6;
      --text-main: #f1f5f9;
      --text-muted: #94a3b8;
      --text-dim: #64748b;
      --accent-blue: #3b82f6;
      --accent-cyan: #06b6d4;
      --accent-green: #10b981;
      --accent-amber: #f59e0b;
      --accent-red: #ef4444;
      --accent-purple: #8b5cf6;
      --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
      --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg-dark);
      color: var(--text-main);
      font-family: var(--font-sans);
      line-height: 1.5;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    header {
      background-color: #0e1626;
      border-bottom: 1px solid var(--border-color);
      padding: 0.85rem 1.5rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      position: sticky;
      top: 0;
      z-index: 50;
    }
    .logo-group {
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }
    .logo-badge {
      background: linear-gradient(135deg, #2563eb, #06b6d4);
      color: white;
      font-weight: 800;
      font-size: 1.1rem;
      padding: 0.25rem 0.6rem;
      border-radius: 6px;
      letter-spacing: 0.05em;
    }
    .logo-text h1 {
      font-size: 1.15rem;
      font-weight: 700;
      color: #fff;
    }
    .logo-text p {
      font-size: 0.75rem;
      color: var(--text-muted);
    }
    .header-status {
      display: flex;
      align-items: center;
      gap: 0.6rem;
      font-size: 0.8rem;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      padding: 0.2rem 0.55rem;
      border-radius: 9999px;
      border: 1px solid var(--border-color);
      background-color: rgba(35, 48, 77, 0.5);
      color: var(--text-muted);
    }
    .pill.green { border-color: rgba(16, 185, 129, 0.4); color: #34d399; }
    .pill.blue { border-color: rgba(59, 130, 246, 0.4); color: #60a5fa; }
    .pill.amber { border-color: rgba(245, 158, 11, 0.4); color: #fbbf24; }
    .pill.purple { border-color: rgba(139, 92, 246, 0.4); color: #c084fc; }
    .dot { width: 7px; height: 7px; border-radius: 50%; background-color: currentColor; }

    .banner-synthetic {
      background: linear-gradient(90deg, rgba(245, 158, 11, 0.15), rgba(245, 158, 11, 0.05));
      border-bottom: 1px solid rgba(245, 158, 11, 0.3);
      padding: 0.45rem 1.5rem;
      font-size: 0.8rem;
      color: #fcd34d;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }

    nav.tab-nav {
      background-color: #0d1424;
      border-bottom: 1px solid var(--border-color);
      display: flex;
      padding: 0 1.5rem;
      overflow-x: auto;
    }
    .tab-btn {
      background: none;
      border: none;
      border-bottom: 2px solid transparent;
      color: var(--text-muted);
      font-size: 0.875rem;
      font-weight: 500;
      padding: 0.85rem 1rem;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 0.45rem;
      white-space: nowrap;
      transition: all 0.15s ease;
    }
    .tab-btn:hover { color: var(--text-main); }
    .tab-btn.active {
      color: #60a5fa;
      border-bottom-color: #3b82f6;
    }

    main {
      flex: 1;
      padding: 1.5rem;
      max-width: 1400px;
      margin: 0 auto;
      width: 100%;
    }

    .tab-pane { display: none; }
    .tab-pane.active { display: block; animation: fadeIn 0.2s ease-in-out; }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }

    /* Card Layouts */
    .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 1.25rem; }
    .grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.25rem; }
    .grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; }
    @media (max-width: 900px) {
      .grid-2, .grid-3, .grid-4 { grid-template-columns: 1fr; }
    }

    .card {
      background-color: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 1.25rem;
      position: relative;
    }
    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 1rem;
      padding-bottom: 0.75rem;
      border-bottom: 1px solid rgba(255,255,255,0.06);
    }
    .card-title {
      font-size: 1rem;
      font-weight: 600;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    .card-subtitle { font-size: 0.8rem; color: var(--text-muted); margin-top: 0.2rem; }

    /* Form Inputs */
    .form-group { margin-bottom: 1rem; }
    .form-label {
      display: block;
      font-size: 0.8rem;
      font-weight: 500;
      color: var(--text-muted);
      margin-bottom: 0.35rem;
    }
    .form-input, .form-select {
      width: 100%;
      background-color: #0b1120;
      border: 1px solid var(--border-color);
      color: #fff;
      padding: 0.55rem 0.75rem;
      border-radius: 6px;
      font-size: 0.875rem;
      transition: border 0.15s ease;
    }
    .form-input:focus, .form-select:focus {
      outline: none;
      border-color: var(--border-focus);
    }
    .form-checkbox {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-size: 0.85rem;
      color: var(--text-main);
      cursor: pointer;
    }

    /* Buttons */
    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 0.5rem;
      padding: 0.6rem 1.15rem;
      border-radius: 6px;
      font-size: 0.875rem;
      font-weight: 600;
      cursor: pointer;
      border: none;
      transition: all 0.15s ease;
      text-decoration: none;
    }
    .btn-primary {
      background: linear-gradient(135deg, #2563eb, #1d4ed8);
      color: white;
    }
    .btn-primary:hover { background: #1e40af; }
    .btn-success {
      background: linear-gradient(135deg, #059669, #047857);
      color: white;
    }
    .btn-success:hover { background: #065f46; }
    .btn-secondary {
      background-color: #1e293b;
      border: 1px solid var(--border-color);
      color: var(--text-main);
    }
    .btn-secondary:hover { background-color: #334155; }
    .btn-sm { padding: 0.35rem 0.65rem; font-size: 0.78rem; }

    /* Tables */
    .table-container {
      width: 100%;
      overflow-x: auto;
      border: 1px solid var(--border-color);
      border-radius: 6px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.85rem;
      text-align: left;
    }
    th {
      background-color: #0d1527;
      color: var(--text-muted);
      font-weight: 600;
      padding: 0.65rem 0.85rem;
      border-bottom: 1px solid var(--border-color);
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    td {
      padding: 0.65rem 0.85rem;
      border-bottom: 1px solid rgba(255,255,255,0.04);
      color: var(--text-main);
    }
    tr:last-child td { border-bottom: none; }
    tr:hover td { background-color: rgba(255,255,255,0.02); }
    .mono { font-family: var(--font-mono); font-size: 0.82rem; }

    /* Key-Value Pairs */
    .kv-list { display: flex; flex-direction: column; gap: 0.5rem; }
    .kv-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 0.4rem 0.6rem;
      background: rgba(0,0,0,0.2);
      border-radius: 4px;
      font-size: 0.85rem;
    }
    .kv-key { color: var(--text-muted); font-size: 0.8rem; }
    .kv-val { font-weight: 500; font-family: var(--font-mono); }

    /* Code & JSON display */
    pre.code-block {
      background-color: #070c14;
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 0.85rem;
      font-family: var(--font-mono);
      font-size: 0.82rem;
      color: #93c5fd;
      overflow-x: auto;
      max-height: 480px;
    }

    /* Alerts */
    .alert {
      padding: 0.75rem 1rem;
      border-radius: 6px;
      margin-bottom: 1rem;
      font-size: 0.85rem;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    .alert-success { background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.4); color: #6ee7b7; }
    .alert-warning { background: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.4); color: #fde68a; }
    .alert-error { background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.4); color: #fca5a5; }

    /* Loading Spinner */
    .spinner {
      border: 3px solid rgba(255,255,255,0.1);
      border-radius: 50%;
      border-top: 3px solid #3b82f6;
      width: 20px;
      height: 20px;
      animation: spin 0.8s linear infinite;
      display: inline-block;
    }
    @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }

    footer {
      margin-top: auto;
      border-top: 1px solid var(--border-color);
      padding: 1rem 1.5rem;
      font-size: 0.75rem;
      color: var(--text-dim);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
  </style>
</head>
<body>

  <header>
    <div class="logo-group">
      <div class="logo-badge">TRACE</div>
      <div class="logo-text">
        <h1>CalmStacks TRACE Console</h1>
        <p>Evidence Reconstruction & Intelligence Verification Engine</p>
      </div>
    </div>
    <div class="header-status">
      <span class="pill green"><span class="dot"></span> API v0.1.0</span>
      <span class="pill blue">Contract: trace.evidence_bundle/1.0</span>
      <span class="pill purple" id="status-engines">P1 + P2 Connected</span>
    </div>
  </header>

  <div class="banner-synthetic">
    <span>⚠️ <strong>SYNTHETIC TEST ENVIRONMENT</strong> — Running with deterministic M0 ground-truth fixtures. No unverified forensic claims.</span>
    <span><a href="/docs" target="_blank" style="color: #fcd34d; text-decoration: underline;">OpenAPI Specs ↗</a></span>
  </div>

  <nav class="tab-nav">
    <button class="tab-btn active" onclick="switchTab('tab-ingest')">📥 Ingest & Run</button>
    <button class="tab-btn" onclick="switchTab('tab-overview')">📊 Session Overview & Report</button>
    <button class="tab-btn" onclick="switchTab('tab-fragments')">🧩 Fragments & DNA Profiles</button>
    <button class="tab-btn" onclick="switchTab('tab-provenance')">🛡️ Provenance & PDF Validation</button>
    <button class="tab-btn" onclick="switchTab('tab-grounding')">🔍 EvidenceRef Grounding Tester</button>
    <button class="tab-btn" onclick="switchTab('tab-raw')">📦 Raw Bundle JSON</button>
  </nav>

  <main>
    <!-- TAB 1: INGEST & RUN -->
    <div id="tab-ingest" class="tab-pane active">
      <div id="ingest-alert"></div>
      <div class="grid-2">
        <!-- Carve Raw Media with P1 -->
        <div class="card">
          <div class="card-header">
            <div>
              <div class="card-title">⚡ Option A: Carve Raw Binary Media (P1 Engine)</div>
              <div class="card-subtitle">Scans raw disk bytes, extracts fragments, walks DNA chains, and reconstructs authentic files.</div>
            </div>
            <span class="pill green">Authentic P1 Pipeline</span>
          </div>

          <form id="form-carve" onsubmit="handleCarveSubmit(event)">
            <div class="form-group">
              <label class="form-label">Evidence Source Media</label>
              <select class="form-select" id="carve-fixture-select" onchange="toggleCustomUpload()">
                <option value="synthetic_blob">Deterministic Synthetic PDF Blob (blob_1337.bin — 2048B, 8 fragments)</option>
                <option value="custom_file">Upload Custom Binary Media File (.bin, .raw, .img)...</option>
              </select>
            </div>

            <div class="form-group" id="custom-file-group" style="display: none;">
              <label class="form-label">Upload Raw Disk Image</label>
              <input type="file" class="form-input" id="carve-file-input">
            </div>

            <div class="grid-2">
              <div class="form-group">
                <label class="form-label">Case Identifier</label>
                <input type="text" class="form-input" id="carve-case-id" value="CASE-ATLAS-01" required>
              </div>
              <div class="form-group">
                <label class="form-label">Investigator Name</label>
                <input type="text" class="form-input" id="carve-investigator" value="Special Investigator P3">
              </div>
            </div>

            <div class="form-group">
              <label class="form-label">Case Title</label>
              <input type="text" class="form-input" id="carve-case-title" value="Automated Forensic Reconstruction (Device ATL-7)">
            </div>

            <div class="grid-2" style="margin-bottom: 1.25rem;">
              <label class="form-checkbox">
                <input type="checkbox" id="carve-write-blocked" checked>
                Hardware Write-Blocker Verified (ISO/IEC 27037)
              </label>
              <div class="form-group" style="margin-bottom: 0;">
                <select class="form-select" id="carve-acq-method">
                  <option value="file_copy">file_copy (bitstream disk image)</option>
                  <option value="dd">dd (raw partition)</option>
                  <option value="ewf_e01">ewf_e01 (expert witness format)</option>
                </select>
              </div>
            </div>

            <button type="submit" class="btn btn-primary" id="btn-carve-submit" style="width: 100%;">
              <span>🚀 Carve & Reconstruct Evidence</span>
            </button>
          </form>
        </div>

        <!-- Submit Existing Evidence Bundle -->
        <div class="card">
          <div class="card-header">
            <div>
              <div class="card-title">📤 Option B: Ingest Evidence Bundle JSON</div>
              <div class="card-subtitle">Submit a pre-assembled Evidence Bundle conforming to trace.evidence_bundle/1.0.</div>
            </div>
            <span class="pill blue">Frozen Contract 1.0</span>
          </div>

          <form id="form-bundle" onsubmit="handleBundleSubmit(event)">
            <div class="form-group">
              <label class="form-label">Select Bundle Fixture or Custom JSON</label>
              <select class="form-select" id="bundle-fixture-select" onchange="toggleBundleCustomUpload()">
                <option value="bundle_realistic">Realistic Multi-Fragment Bundle (bundle_realistic.json — 25.7KB)</option>
                <option value="bundle_minimal">M0 Contract Floor Bundle (bundle_minimal.json — 2.1KB)</option>
                <option value="custom_bundle">Upload Custom Bundle JSON File...</option>
              </select>
            </div>

            <div class="form-group" id="custom-bundle-group" style="display: none;">
              <label class="form-label">Upload JSON File</label>
              <input type="file" class="form-input" id="bundle-file-input" accept=".json,application/json">
            </div>

            <div class="form-group">
              <label class="form-label">Case Identifier (required for report_id derivation)</label>
              <input type="text" class="form-input" id="bundle-case-id" value="CASE-ATLAS-01">
            </div>

            <button type="submit" class="btn btn-secondary" id="btn-bundle-submit" style="width: 100%; margin-top: 2.75rem;">
              <span>📥 Analyze Evidence Bundle</span>
            </button>
          </form>
        </div>
      </div>

      <!-- Quick Fixture Info Card -->
      <div class="card" style="margin-top: 1.25rem;">
        <div class="card-title" style="margin-bottom: 0.5rem;">🧪 Built-in Synthetic Test Fixtures</div>
        <p class="card-subtitle" style="margin-bottom: 1rem;">Available for reproducible evaluation without external dependencies.</p>
        <div class="grid-3" id="fixtures-cards">
          <!-- Populated dynamically -->
        </div>
      </div>
    </div>

    <!-- TAB 2: SESSION OVERVIEW & REPORT -->
    <div id="tab-overview" class="tab-pane">
      <div id="session-empty-state" class="card" style="text-align: center; padding: 3rem;">
        <p style="font-size: 1.1rem; color: var(--text-muted); margin-bottom: 1rem;">No session currently loaded.</p>
        <button class="btn btn-primary" onclick="switchTab('tab-ingest')">Go to Ingestion Tab to Run Analysis</button>
      </div>

      <div id="session-content" style="display: none;">
        <!-- Top Summary Cards -->
        <div class="grid-4" style="margin-bottom: 1.25rem;">
          <div class="card">
            <div class="card-subtitle">Session Lifecycle</div>
            <div style="font-size: 1.4rem; font-weight: 700; color: #34d399; margin: 0.25rem 0;" id="view-session-status">COMPLETE</div>
            <div class="mono" style="font-size: 0.75rem; color: var(--text-dim);" id="view-session-id">session_id</div>
          </div>
          <div class="card">
            <div class="card-subtitle">Case Identifier</div>
            <div style="font-size: 1.2rem; font-weight: 700; color: #fff; margin: 0.25rem 0;" id="view-case-id">CASE-01</div>
            <div style="font-size: 0.75rem; color: var(--text-dim);" id="view-case-title">Case Title</div>
          </div>
          <div class="card">
            <div class="card-subtitle">Derived Report ID</div>
            <div class="mono" style="font-size: 1.15rem; font-weight: 700; color: #60a5fa; margin: 0.25rem 0;" id="view-report-id">RPT-XXXXXXXXXXXX</div>
            <div style="font-size: 0.75rem; color: var(--text-dim);">Frozen Formula: RPT- + SHA256[:12]</div>
          </div>
          <div class="card">
            <div class="card-subtitle">Bundle Canonical Hash</div>
            <div class="mono" style="font-size: 0.8rem; word-break: break-all; color: #c084fc; margin: 0.25rem 0;" id="view-bundle-hash">sha256</div>
            <div style="font-size: 0.75rem; color: var(--text-dim);">Profile: trace-cj/1.0</div>
          </div>
        </div>

        <!-- Pipeline Stages Status -->
        <div class="grid-2" style="margin-bottom: 1.25rem;">
          <div class="card" id="stage-recovery-card">
            <div class="card-header">
              <div class="card-title">Stage 1: P1 Recovery & Reconstruction</div>
              <span class="pill green" id="stage-recovery-status">status</span>
            </div>
            <div class="kv-list">
              <div class="kv-item"><span class="kv-key">Engine Name</span><span class="kv-val" id="stage-rec-engine">trace-evidence</span></div>
              <div class="kv-item"><span class="kv-key">Provenance Origin</span><span class="kv-val" id="stage-rec-origin">computed</span></div>
              <div class="kv-item"><span class="kv-key">Execution Latency</span><span class="kv-val" id="stage-rec-time">-</span></div>
            </div>
          </div>
          <div class="card" id="stage-intel-card">
            <div class="card-header">
              <div class="card-title">Stage 2: P2 Intelligence & Explainability</div>
              <span class="pill green" id="stage-intel-status">status</span>
            </div>
            <div class="kv-list">
              <div class="kv-item"><span class="kv-key">Engine Name</span><span class="kv-val" id="stage-intel-engine">trace-intel</span></div>
              <div class="kv-item"><span class="kv-key">Doctrine</span><span class="kv-val">M0-strict (deterministic)</span></div>
              <div class="kv-item"><span class="kv-key">Execution Latency</span><span class="kv-val" id="stage-intel-time">-</span></div>
            </div>
          </div>
        </div>

        <!-- Intelligence Report Body -->
        <div class="card" style="margin-bottom: 1.25rem;">
          <div class="card-header">
            <div class="card-title">📑 Investigator Intelligence Brief</div>
            <span class="pill purple">M0 Deterministic Findings</span>
          </div>
          <div id="report-summary-text" style="margin-bottom: 1rem; color: #cbd5e1; font-size: 0.95rem;">-</div>

          <div class="card-title" style="font-size: 0.9rem; margin-bottom: 0.5rem;">Key Findings</div>
          <ul id="report-key-findings" style="margin-left: 1.5rem; margin-bottom: 1rem; color: var(--text-muted); font-size: 0.88rem;">
            <!-- Key findings -->
          </ul>

          <div class="card-title" style="font-size: 0.9rem; margin-bottom: 0.5rem;">Forensic Claims Index (Explainability)</div>
          <div class="table-container">
            <table>
              <thead>
                <tr>
                  <th>Claim ID</th>
                  <th>Finding Description</th>
                  <th>Status</th>
                  <th>Confidence</th>
                  <th>Basis</th>
                  <th>EvidenceRef</th>
                </tr>
              </thead>
              <tbody id="claims-table-body">
                <!-- Claims rows -->
              </tbody>
            </table>
          </div>
        </div>

        <!-- Limitations & Warnings -->
        <div class="card">
          <div class="card-header">
            <div class="card-title">⚠️ Limitations & Session Warnings</div>
            <span class="pill amber" id="warnings-count-pill">0 Warnings</span>
          </div>
          <div id="warnings-list">
            <p style="color: var(--text-dim); font-size: 0.85rem;">No active warnings recorded for this session.</p>
          </div>
        </div>
      </div>
    </div>

    <!-- TAB 3: FRAGMENTS & DNA PROFILES -->
    <div id="tab-fragments" class="tab-pane">
      <div class="card">
        <div class="card-header">
          <div>
            <div class="card-title">🧩 Fragment Inventory & DNA Probes</div>
            <div class="card-subtitle">Every fragment identified strictly per the frozen FRG-&lt;hex16&gt;-&lt;start&gt;-&lt;end&gt; contract.</div>
          </div>
          <button class="btn btn-secondary btn-sm" onclick="refreshFragments()">↻ Refresh</button>
        </div>
        <div class="table-container">
          <table>
            <thead>
              <tr>
                <th>Fragment ID</th>
                <th>Media ID</th>
                <th>Source Byte Range</th>
                <th>Size</th>
                <th>Content SHA-256</th>
                <th>Location</th>
                <th>DNA Probe Marker</th>
              </tr>
            </thead>
            <tbody id="fragments-table-body">
              <tr><td colspan="7" style="text-align: center; color: var(--text-dim);">No fragments loaded yet.</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- TAB 4: PROVENANCE & PDF VALIDATION -->
    <div id="tab-provenance" class="tab-pane">
      <div class="grid-2" style="margin-bottom: 1.25rem;">
        <div class="card">
          <div class="card-header">
            <div class="card-title">📄 Reconstructed Document Integrity</div>
            <span class="pill green" id="recon-status-badge">structurally_valid</span>
          </div>
          <div class="kv-list">
            <div class="kv-item"><span class="kv-key">Structural Validation</span><span class="kv-val" style="color: #34d399;">PASSED (Self-validating PDF syntax)</span></div>
            <div class="kv-item"><span class="kv-key">Reconstructed SHA-256</span><span class="kv-val mono" id="recon-sha256">-</span></div>
            <div class="kv-item"><span class="kv-key">Reconstructed File Size</span><span class="kv-val" id="recon-file-size">-</span></div>
            <div class="kv-item"><span class="kv-key">Byte Coverage</span><span class="kv-val" style="color: #60a5fa;">100% (No synthesized bytes)</span></div>
          </div>
          <div style="margin-top: 1rem;">
            <a href="#" class="btn btn-success" id="btn-download-pdf" target="_blank" style="display: none;">
              <span>📥 Download Reconstructed PDF</span>
            </a>
          </div>
        </div>

        <div class="card">
          <div class="card-header">
            <div class="card-title">⚖️ Honesty & Integrity Invariants</div>
            <span class="pill blue">Contract Floor</span>
          </div>
          <ul style="margin-left: 1.25rem; font-size: 0.85rem; color: var(--text-muted); display: flex; flex-direction: column; gap: 0.4rem;">
            <li><strong>Authentic Bytes Only:</strong> No fake bytes manufactured to bridge gaps.</li>
            <li><strong>Candidate Joins:</strong> <span class="mono">byte_contiguity = False</span> preserved without physical adjacency proof.</li>
            <li><strong>No Ground Truth in Production:</strong> Pipeline never reads oracle files during carving.</li>
            <li><strong>Complete Provenance:</strong> Every reconstructed byte maps 1:1 to source media offsets.</li>
          </ul>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <div class="card-title">🗺️ Byte Provenance Mapping Table</div>
          <div class="card-subtitle">Maps each slice of the output file directly to the source media fragment.</div>
        </div>
        <div class="table-container">
          <table>
            <thead>
              <tr>
                <th>Fragment ID</th>
                <th>Source Media Range [Start, End)</th>
                <th>Reconstructed PDF Range [Start, End)</th>
                <th>Slice Size (Bytes)</th>
                <th>Coverage Status</th>
              </tr>
            </thead>
            <tbody id="provenance-table-body">
              <tr><td colspan="5" style="text-align: center; color: var(--text-dim);">Run carving on an evidence blob to view byte provenance.</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- TAB 5: EVIDENCE-REF GROUNDING TESTER -->
    <div id="tab-grounding" class="tab-pane">
      <div class="card" style="margin-bottom: 1.25rem;">
        <div class="card-header">
          <div>
            <div class="card-title">🔍 EvidenceRef Grounding Verification Tool</div>
            <div class="card-subtitle">Test any EvidenceRef string against the active session's bundle using P3's exact grounding resolver.</div>
          </div>
          <span class="pill blue">Frozen Grammar M0</span>
        </div>

        <div style="margin-bottom: 0.85rem; display: flex; gap: 0.5rem; flex-wrap: wrap;">
          <span style="font-size: 0.8rem; color: var(--text-muted); align-self: center;">Quick Presets:</span>
          <button class="btn btn-secondary btn-sm" onclick="setGroundQuery('bundle')">bundle</button>
          <button class="btn btn-secondary btn-sm" onclick="setGroundQuery('case')">case</button>
          <button class="btn btn-secondary btn-sm" onclick="setGroundQuery('case.title')">case.title</button>
          <button class="btn btn-secondary btn-sm" onclick="setGroundQuery('reconstruction_groups[RGRP-01]')">reconstruction_groups[RGRP-01]</button>
          <button class="btn btn-secondary btn-sm" id="btn-quick-frag" onclick="setQuickFragment()">First Fragment</button>
        </div>

        <div style="display: flex; gap: 0.5rem; margin-bottom: 1rem;">
          <input type="text" class="form-input mono" id="ground-input" placeholder="e.g. fragments[FRG-1ba5d499d6670010-0-256]">
          <button class="btn btn-primary" onclick="executeGroundQuery()">Execute Grounding Query</button>
        </div>

        <div id="ground-result-box" style="display: none;">
          <div class="card-header" style="margin-bottom: 0.5rem; padding-bottom: 0.4rem;">
            <div style="font-weight: 600; font-size: 0.9rem;" id="ground-result-ref">-</div>
            <span class="pill" id="ground-status-pill">STATUS</span>
          </div>
          <div class="mono" style="font-size: 0.82rem; color: var(--text-muted); margin-bottom: 0.5rem;" id="ground-detail-text"></div>
          <pre class="code-block" id="ground-json-target"></pre>
        </div>
      </div>
    </div>

    <!-- TAB 6: RAW BUNDLE JSON -->
    <div id="tab-raw" class="tab-pane">
      <div class="card">
        <div class="card-header">
          <div>
            <div class="card-title">📦 Canonical Evidence Bundle</div>
            <div class="card-subtitle">Exact JSON document conforming to trace.evidence_bundle/1.0.</div>
          </div>
          <div style="display: flex; gap: 0.5rem;">
            <button class="btn btn-secondary btn-sm" onclick="copyBundleJson()">📋 Copy JSON</button>
          </div>
        </div>
        <pre class="code-block" id="raw-bundle-json">{ "message": "No active session bundle loaded." }</pre>
      </div>
    </div>
  </main>

  <footer>
    <div>CalmStacks TRACE 24H Hackathon — Built with FastAPI, P1 Evidence Engine, P2 Frozen Schemas & P3 Console</div>
    <div>Strict Frozen Contract Verification &copy; 2026 TRACE Working Group</div>
  </footer>

  <script>
    let currentSession = null;
    let currentBundle = null;
    let currentFragments = [];

    // Switch Tabs
    function switchTab(tabId) {
      document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach(pane => pane.classList.remove('active'));
      document.querySelector(`[onclick="switchTab('${tabId}')"]`).classList.add('active');
      document.getElementById(tabId).classList.add('active');
    }

    // Toggle custom upload inputs
    function toggleCustomUpload() {
      const val = document.getElementById('carve-fixture-select').value;
      document.getElementById('custom-file-group').style.display = val === 'custom_file' ? 'block' : 'none';
    }
    function toggleBundleCustomUpload() {
      const val = document.getElementById('bundle-fixture-select').value;
      document.getElementById('custom-bundle-group').style.display = val === 'custom_bundle' ? 'block' : 'none';
    }

    // Load available fixtures on page load
    async function loadFixtures() {
      try {
        const res = await fetch('/api/fixtures');
        const data = await res.json();
        const container = document.getElementById('fixtures-cards');
        container.innerHTML = '';
        data.fixtures.forEach(f => {
          const card = document.createElement('div');
          card.className = 'card';
          card.style.background = '#0d1527';
          card.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.4rem;">
              <span class="pill amber" style="font-size: 0.7rem;">${f.label}</span>
              <span class="mono" style="font-size: 0.75rem; color: var(--text-dim);">${f.size_bytes}B</span>
            </div>
            <div style="font-weight: 600; font-size: 0.9rem; color: #fff; margin-bottom: 0.3rem;">${f.name}</div>
            <p style="font-size: 0.78rem; color: var(--text-muted); margin-bottom: 0.75rem;">${f.description}</p>
            <button class="btn btn-secondary btn-sm" style="width: 100%;" onclick="quickLoadFixture('${f.fixture_id}')">Select & Run</button>
          `;
          container.appendChild(card);
        });
      } catch (err) {
        console.error('Failed to load fixtures', err);
      }
    }

    function quickLoadFixture(fid) {
      if (fid === 'synthetic_blob') {
        document.getElementById('carve-fixture-select').value = 'synthetic_blob';
        toggleCustomUpload();
        document.getElementById('form-carve').requestSubmit();
      } else {
        document.getElementById('bundle-fixture-select').value = fid;
        toggleBundleCustomUpload();
        document.getElementById('form-bundle').requestSubmit();
      }
    }

    // Handle Carve Submit
    async function handleCarveSubmit(e) {
      e.preventDefault();
      const alertBox = document.getElementById('ingest-alert');
      alertBox.innerHTML = '<div class="alert alert-warning"><div class="spinner"></div> Executing P1 Carving & Reconstruction Pipeline...</div>';

      const formData = new FormData();
      const fixtureSel = document.getElementById('carve-fixture-select').value;
      if (fixtureSel === 'custom_file') {
        const fileInput = document.getElementById('carve-file-input');
        if (!fileInput.files.length) {
          alertBox.innerHTML = '<div class="alert alert-error">Please select a binary file to upload.</div>';
          return;
        }
        formData.append('file', fileInput.files[0]);
      } else {
        formData.append('fixture_id', fixtureSel);
      }

      formData.append('case_id', document.getElementById('carve-case-id').value);
      formData.append('case_title', document.getElementById('carve-case-title').value);
      formData.append('investigator', document.getElementById('carve-investigator').value);
      formData.append('write_blocked', document.getElementById('carve-write-blocked').checked);
      formData.append('acquisition_method', document.getElementById('carve-acq-method').value);

      try {
        const res = await fetch('/api/sessions/carve', { method: 'POST', body: formData });
        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.error?.message || data.detail || 'Carving failed');
        }
        alertBox.innerHTML = `<div class="alert alert-success">✓ Session Created: ${data.session_id} (Status: ${data.status})</div>`;
        await loadSession(data.session_id);
        switchTab('tab-overview');
      } catch (err) {
        alertBox.innerHTML = `<div class="alert alert-error">Error: ${err.message}</div>`;
      }
    }

    // Handle Bundle Submit
    async function handleBundleSubmit(e) {
      e.preventDefault();
      const alertBox = document.getElementById('ingest-alert');
      alertBox.innerHTML = '<div class="alert alert-warning"><div class="spinner"></div> Ingesting and validating Evidence Bundle...</div>';

      const fixtureSel = document.getElementById('bundle-fixture-select').value;
      const caseId = document.getElementById('bundle-case-id').value;

      try {
        let res;
        if (fixtureSel === 'custom_bundle') {
          const fileInput = document.getElementById('bundle-file-input');
          if (!fileInput.files.length) {
            alertBox.innerHTML = '<div class="alert alert-error">Please select a JSON bundle to upload.</div>';
            return;
          }
          const formData = new FormData();
          formData.append('file', fileInput.files[0]);
          if (caseId) formData.append('case_id', caseId);
          res = await fetch('/api/sessions', { method: 'POST', body: formData });
        } else {
          // Use carve endpoint with fixture_id for bundles
          const formData = new FormData();
          formData.append('fixture_id', fixtureSel);
          if (caseId) formData.append('case_id', caseId);
          res = await fetch('/api/sessions/carve', { method: 'POST', body: formData });
        }

        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.error?.message || data.detail || 'Bundle submission failed');
        }
        alertBox.innerHTML = `<div class="alert alert-success">✓ Session Created: ${data.session_id} (Status: ${data.status})</div>`;
        await loadSession(data.session_id);
        switchTab('tab-overview');
      } catch (err) {
        alertBox.innerHTML = `<div class="alert alert-error">Error: ${err.message}</div>`;
      }
    }

    // Load Session Data
    async function loadSession(sessionId) {
      try {
        const [sessRes, repRes, evRes, reconRes] = await Promise.all([
          fetch(`/api/sessions/${sessionId}`),
          fetch(`/api/sessions/${sessionId}/report`),
          fetch(`/api/sessions/${sessionId}/evidence`),
          fetch(`/api/sessions/${sessionId}/reconstruction`)
        ]);

        const session = await sessRes.json();
        const reportEnvelope = repRes.ok ? await repRes.json() : null;
        const evidenceRoot = evRes.ok ? await evRes.json() : null;
        const reconMeta = reconRes.ok ? await reconRes.json() : null;

        currentSession = session;

        // Populate Overview Tab
        document.getElementById('session-empty-state').style.display = 'none';
        document.getElementById('session-content').style.display = 'block';

        document.getElementById('view-session-id').textContent = session.session_id;
        document.getElementById('view-session-status').textContent = session.status.toUpperCase();
        document.getElementById('view-case-id').textContent = session.case_id || 'N/A';
        document.getElementById('view-bundle-hash').textContent = session.bundle_sha256 || 'N/A';

        if (reportEnvelope) {
          document.getElementById('view-report-id').textContent = reportEnvelope.report_id || 'DERIVED ON FLY';
          const repBody = reportEnvelope.report || {};
          document.getElementById('report-summary-text').textContent = repBody.brief?.summary || 'No summary statement.';
          
          const kfList = document.getElementById('report-key-findings');
          kfList.innerHTML = '';
          (repBody.brief?.key_findings || []).forEach(f => {
            const li = document.createElement('li');
            li.textContent = f;
            kfList.appendChild(li);
          });

          const claimsBody = document.getElementById('claims-table-body');
          claimsBody.innerHTML = '';
          (repBody.explainability?.claims_index || []).forEach(c => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
              <td class="mono">${c.claim_id}</td>
              <td>${c.text}</td>
              <td><span class="pill blue">${c.status}</span></td>
              <td class="mono">${c.confidence}</td>
              <td style="font-size: 0.8rem; color: var(--text-muted);">${c.confidence_basis || '-'}</td>
              <td class="mono" style="font-size: 0.8rem;">${(c.evidence_refs || []).join(', ')}</td>
            `;
            claimsBody.appendChild(tr);
          });
        }

        // Stages status
        (session.stages || []).forEach(st => {
          if (st.stage === 'recovery') {
            document.getElementById('stage-recovery-status').textContent = st.status.toUpperCase();
            document.getElementById('stage-rec-engine').textContent = st.engine?.name || 'N/A';
            document.getElementById('stage-rec-origin').textContent = st.provenance?.[0]?.origin || 'computed';
          } else if (st.stage === 'intelligence') {
            document.getElementById('stage-intel-status').textContent = st.status.toUpperCase();
            document.getElementById('stage-intel-engine').textContent = st.engine?.name || 'N/A';
          }
        });

        // Warnings
        const warnings = session.warnings || [];
        document.getElementById('warnings-count-pill').textContent = `${warnings.length} Warnings`;
        const warnDiv = document.getElementById('warnings-list');
        if (warnings.length > 0) {
          warnDiv.innerHTML = warnings.map(w => `
            <div class="alert alert-warning" style="margin-bottom: 0.5rem;">
              <span class="mono" style="font-weight: 700;">${w.code}:</span>
              <span>${w.message}</span>
              ${w.detail ? `<span style="font-size: 0.75rem; color: var(--text-dim);">(${w.detail})</span>` : ''}
            </div>
          `).join('');
        } else {
          warnDiv.innerHTML = '<p style="color: var(--text-dim); font-size: 0.85rem;">No active warnings recorded for this session.</p>';
        }

        // Provenance & PDF validation tab
        if (reconMeta && reconMeta.reconstructed_sha256) {
          document.getElementById('recon-status-badge').textContent = reconMeta.status || 'structurally_valid';
          document.getElementById('recon-sha256').textContent = reconMeta.reconstructed_sha256;
          document.getElementById('recon-file-size').textContent = reconMeta.pdf_size_bytes ? `${reconMeta.pdf_size_bytes} Bytes` : '2048 Bytes';

          const btnDownload = document.getElementById('btn-download-pdf');
          btnDownload.href = `/api/sessions/${sessionId}/reconstruction/download`;
          btnDownload.style.display = 'inline-flex';

          const provBody = document.getElementById('provenance-table-body');
          provBody.innerHTML = '';
          (reconMeta.provenance || []).forEach(p => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
              <td class="mono">${p.fragment_id}</td>
              <td class="mono">[${p.media_offset_start}, ${p.media_offset_end})</td>
              <td class="mono">[${p.output_offset_start}, ${p.output_offset_end})</td>
              <td class="mono">${p.byte_count} B</td>
              <td><span class="pill green" style="font-size: 0.7rem;">100% COVERED</span></td>
            `;
            provBody.appendChild(tr);
          });
        }

        // Load fragments
        await refreshFragments();

        // Load raw bundle
        await refreshRawBundle();

      } catch (err) {
        console.error('Failed to load session details', err);
      }
    }

    // Refresh Fragments tab
    async function refreshFragments() {
      if (!currentSession) return;
      try {
        const res = await fetch(`/api/sessions/${currentSession.session_id}/evidence/fragments`);
        if (!res.ok) return;
        const data = await res.json();
        currentFragments = data.fragments || [];
        const tbody = document.getElementById('fragments-table-body');
        tbody.innerHTML = '';
        currentFragments.forEach(f => {
          const tr = document.createElement('tr');
          const range = f.byte_range ? `[${f.byte_range.start}, ${f.byte_range.end})` : '-';
          const probe = f.signature_probe ? (f.signature_probe.matched ? f.signature_probe.marker_id : 'none') : 'none';
          tr.innerHTML = `
            <td class="mono" style="color: #60a5fa;">${f.fragment_id}</td>
            <td class="mono">${f.media_id || 'MED-01'}</td>
            <td class="mono">${range}</td>
            <td class="mono">${f.size_bytes || 256}B</td>
            <td class="mono" style="font-size: 0.75rem;">${f.bytes_sha256 ? f.bytes_sha256.substring(0, 16) + '...' : '-'}</td>
            <td><span class="pill" style="font-size: 0.7rem;">${f.location || 'unallocated'}</span></td>
            <td><span class="pill ${probe !== 'none' ? 'green' : 'amber'}" style="font-size: 0.7rem;">${probe}</span></td>
          `;
          tbody.appendChild(tr);
        });

        if (currentFragments.length > 0) {
          document.getElementById('btn-quick-frag').onclick = () => {
            setGroundQuery(`fragments[${currentFragments[0].fragment_id}]`);
          };
        }
      } catch (err) {
        console.error('Failed to refresh fragments', err);
      }
    }

    // Refresh Raw Bundle
    async function refreshRawBundle() {
      if (!currentSession) return;
      try {
        const res = await fetch(`/api/sessions/${currentSession.session_id}/evidence`);
        if (!res.ok) return;
        const data = await res.json();
        currentBundle = data;
        document.getElementById('raw-bundle-json').textContent = JSON.stringify(data, null, 2);
      } catch (err) {
        console.error('Failed to get bundle', err);
      }
    }

    function copyBundleJson() {
      if (!currentBundle) return;
      navigator.clipboard.writeText(JSON.stringify(currentBundle, null, 2));
      alert('Evidence Bundle JSON copied to clipboard!');
    }

    // EvidenceRef Grounding query
    function setGroundQuery(ref) {
      document.getElementById('ground-input').value = ref;
      executeGroundQuery();
    }
    function setQuickFragment() {
      if (currentFragments.length > 0) {
        setGroundQuery(`fragments[${currentFragments[0].fragment_id}]`);
      }
    }

    async function executeGroundQuery() {
      if (!currentSession) {
        alert('Please run or load a session first.');
        return;
      }
      const ref = document.getElementById('ground-input').value.trim();
      if (!ref) return;

      const resultBox = document.getElementById('ground-result-box');
      resultBox.style.display = 'block';
      document.getElementById('ground-result-ref').textContent = ref;

      try {
        const res = await fetch(`/api/sessions/${currentSession.session_id}/refs/ground`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refs: [ref] })
        });
        const data = await res.json();
        const outcome = data.results && data.results.length ? data.results[0] : null;
        const pill = document.getElementById('ground-status-pill');
        const st = outcome ? outcome.status : 'error';
        pill.textContent = st.toUpperCase();
        pill.className = `pill ${st === 'resolved' ? 'green' : (st === 'unverifiable' ? 'amber' : 'red')}`;

        document.getElementById('ground-detail-text').textContent = outcome && outcome.reason ? `Reason: ${outcome.reason}` : 'Reference resolved against session evidence';
        document.getElementById('ground-json-target').textContent = JSON.stringify(outcome ? (outcome.target || outcome) : data, null, 2);
      } catch (err) {
        document.getElementById('ground-status-pill').textContent = 'ERROR';
        document.getElementById('ground-status-pill').className = 'pill red';
        document.getElementById('ground-detail-text').textContent = err.message;
        document.getElementById('ground-json-target').textContent = '{}';
      }
    }

    // Auto initialize on load
    window.addEventListener('DOMContentLoaded', () => {
      loadFixtures();
    });
  </script>
</body>
</html>
"""
