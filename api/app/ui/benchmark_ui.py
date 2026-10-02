"""UI Page for TRACE Real-World Dataset Integration and Benchmarking (Phase 10).

Native TRACE interface integrated with the core design system:
- Built with wrap_page() for identical header, navigation, live UTC clock, and footer.
- Open-access document registry table (arXiv CC-BY-4.0, NIST, W3C) with license verification.
- SafeDocs genuinely damaged test corpus table with static safety scan badges.
- Interactive benchmark execution control panel with loading, error, and empty states.
- Granular multimodal metrics (authentic recovery %, text Jaccard, table grid, equation, parser openability).
- Scientific honesty invariants clearly explained (zero fabricated ground truth, document split isolation).
- 100% relative URLs for seamless local development and Vercel production deployment.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.ui.components import wrap_page
from trace.datasets.real_world.genuine_damaged import GenuinelyDamagedCorpusManager
from trace.datasets.real_world.registry import RealWorldRegistryManager


def benchmark_page(benchmark_data: Optional[Dict[str, Any]] = None) -> str:
    """Generate the native TRACE HTML page for the Real-World Dataset Benchmark dashboard."""
    reg_mgr = RealWorldRegistryManager()
    genuine_mgr = GenuinelyDamagedCorpusManager()

    docs = reg_mgr.registry.documents
    genuine_samples = genuine_mgr.list_samples()

    # Pre-render table rows for registered documents
    doc_rows = []
    for d in docs:
        is_intact = d.is_intact
        status_tag = '<span class="tag tag-green">INTACT (GROUND TRUTH)</span>' if is_intact else '<span class="tag tag-amber">MALFORMED (UNVERIFIED)</span>'
        
        char_tags = "".join(
            f'<span class="tag tag-cyan" style="margin-right: 4px; margin-bottom: 3px;">{c.value}</span>'
            for c in d.characteristics[:4]
        )

        authors_str = ", ".join(d.authors[:2])
        if len(d.authors) > 2:
            authors_str += " et al."

        download_hint = f'<code>{d.document_id}.pdf</code>'

        doc_rows.append(f"""
        <tr>
            <td style="font-weight: 600;">
                <div style="color: var(--text-primary); font-size: 13px;">{d.title}</div>
                <div style="font-family: var(--font-mono); font-size: 11px; color: var(--accent-cyan); margin-top: 3px;">
                    {d.document_id} &bull; <span style="color: var(--text-muted);">{d.source_name}</span>
                </div>
                <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">{authors_str}</div>
            </td>
            <td>
                <a href="{d.license_url}" target="_blank" rel="noopener noreferrer" class="tag tag-copper" title="View license terms">
                    {d.license_type.value} &nearr;
                </a>
            </td>
            <td style="font-family: var(--font-mono); font-size: 11.5px; color: var(--text-secondary); white-space: nowrap;">
                {d.page_count} p.<br>
                <span style="color: var(--text-muted); font-size: 10.5px;">{d.file_size_bytes / 1024:.1f} KB</span>
            </td>
            <td>
                <div style="display: flex; flex-wrap: wrap;">{char_tags}</div>
            </td>
            <td style="white-space: nowrap;">
                {status_tag}
            </td>
        </tr>
        """)

    rendered_doc_rows = "".join(doc_rows)

    # Pre-render genuine malformed samples
    genuine_rows = []
    for g in genuine_samples:
        damage_tags = "".join(
            f'<span class="tag tag-amber" style="margin-right: 4px; margin-bottom: 3px;">{c}</span>'
            for c in g.observed_damage_classes
        )
        safe, issues = genuine_mgr.verify_safety_static(g.sample_id)
        safety_badge = (
            '<span class="tag tag-green">&#x2713; STATIC SAFE</span>'
            if safe
            else '<span class="tag tag-red">&#x26A0; UNTRUSTED</span>'
        )

        genuine_rows.append(f"""
        <tr>
            <td style="font-family: var(--font-mono); font-size: 12px; font-weight: 600; color: var(--text-primary);">
                {g.sample_id}
                <div style="font-size: 11px; color: var(--text-muted); font-weight: normal; margin-top: 2px;">
                    {g.source_name}
                </div>
            </td>
            <td>
                <a href="{g.license_url}" target="_blank" rel="noopener noreferrer" class="tag tag-copper">
                    {g.license_type.value} &nearr;
                </a>
            </td>
            <td>
                <div style="display: flex; flex-wrap: wrap;">{damage_tags}</div>
            </td>
            <td style="white-space: nowrap;">
                {safety_badge}
            </td>
            <td style="white-space: nowrap;">
                <span class="tag tag-red" title="Ground truth is absent by definition">NO FABRICATED GROUND TRUTH</span>
            </td>
        </tr>
        """)

    rendered_genuine_rows = "".join(genuine_rows)

    content = f"""
<main class="page-main">
  <div class="container-wide">
    <!-- PAGE HEADER -->
    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 2rem; flex-wrap: wrap; gap: 1.5rem; border-bottom: 1px solid var(--border-subtle); padding-bottom: 1.5rem;">
      <div style="max-width: 820px;">
        <div class="section-eyebrow">Digital Forensics &bull; Phase 10</div>
        <h1 class="section-title">TRACE Forensic Benchmarking &amp; Real-World Dataset Laboratory</h1>
        <p class="section-lead" style="margin-bottom: 0;">
          Controlled corruption evaluation on verified open-access research papers (arXiv CC-BY-4.0, NIST, W3C) alongside honest qualitative assessment of genuinely damaged corpora (DARPA SafeDocs) with zero fabricated ground truth.
        </p>
      </div>
      <div style="display: flex; gap: 0.75rem; flex-wrap: wrap; align-items: center;">
        <a href="/investigations" class="btn btn-secondary">&larr; Investigations Workspace</a>
        <a href="/investigations/new" class="btn btn-secondary">+ Ingest Evidence</a>
        <button onclick="triggerLiveBenchmark()" id="btn-run-benchmark" class="btn btn-primary">
          &#x26A1; Run Live Benchmark
        </button>
      </div>
    </div>

    <!-- FORENSIC SCIENTIFIC HONESTY INVARIANT -->
    <div class="notice notice-info">
      <div style="font-weight: 700; color: var(--accent-cyan); white-space: nowrap;">[FORENSIC SCIENTIFIC HONESTY GUARANTEE]</div>
      <div>
        Controlled corruptions use verified intact originals as cryptographic ground truth. Genuinely damaged files from SafeDocs do NOT claim unverified ground truth. Missing content is never hallucinated or falsely labeled authentic.
      </div>
    </div>

    <!-- BENCHMARK CONTROL & PROGRESS PANEL -->
    <div class="panel" style="background: var(--bg-surface); border: 1px solid var(--border-subtle); margin-bottom: 2rem;">
      <div class="panel-header">
        <span class="panel-title">[CONTROL PANEL] Reproducible Multimodal Benchmark Execution</span>
        <div style="display: flex; gap: 0.5rem; align-items: center;">
          <span class="tag tag-copper">LOCAL-FIRST &bull; ZERO CLOUD API</span>
          <span class="tag tag-cyan">DOCUMENT-LEVEL SPLIT ISOLATION</span>
        </div>
      </div>

      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1.25rem; margin-bottom: 1.5rem;">
        <div>
          <label class="form-label" for="cfg-samples-per-doc">Corruptions Per Document</label>
          <select id="cfg-samples-per-doc" class="form-select">
            <option value="1">1 Variant (Fast Scan)</option>
            <option value="2" selected>2 Variants (Standard Severity L1-L2)</option>
            <option value="3">3 Variants (Deep Stress L1-L3)</option>
          </select>
          <div class="form-hint">Severity levels generated with deterministic seeds.</div>
        </div>

        <div>
          <label class="form-label" for="cfg-max-docs">Target Documents to Evaluate</label>
          <select id="cfg-max-docs" class="form-select">
            <option value="1">1 Document (Quick Verification)</option>
            <option value="2" selected>2 Documents (Balanced Multimodal)</option>
            <option value="4">4 Documents (Comprehensive Suite)</option>
            <option value="6">6 Documents (Full Collection)</option>
          </select>
          <div class="form-hint">Strict split isolation: no cross-set leakage.</div>
        </div>

        <div style="display: flex; flex-direction: column; justify-content: flex-end;">
          <div style="display: flex; gap: 0.5rem;">
            <button onclick="triggerLiveBenchmark()" id="btn-run-panel" class="btn btn-primary" style="flex: 1;">
              Run Benchmark Now
            </button>
            <button onclick="refreshBenchmarkStatus()" class="btn btn-ghost" title="Reload cached results">
              &#x21bb; Refresh
            </button>
          </div>
          <div class="form-hint">Runs 100% offline. Zero Gemini quota consumed.</div>
        </div>
      </div>

      <!-- LIVE PROGRESS & STATUS CONTAINER -->
      <div id="benchmark-status-box" style="display: none; padding: 1rem; border-radius: 2px; border: 1px solid var(--border-subtle); background: var(--bg-inset); margin-top: 1rem;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
          <span id="benchmark-status-title" style="font-family: var(--font-mono); font-size: 12px; font-weight: 700; color: var(--text-primary);">
            Ready
          </span>
          <span id="benchmark-status-timer" style="font-family: var(--font-mono); font-size: 11px; color: var(--accent-copper);">
            00:00
          </span>
        </div>
        <p id="benchmark-status-desc" style="font-size: 12px; color: var(--text-secondary); margin: 0; line-height: 1.5;">
          Idle.
        </p>
      </div>
    </div>

    <!-- METRICS SUMMARY GRID -->
    <div style="margin-bottom: 2rem;">
      <div class="panel-header" style="border: none; margin-bottom: 0.75rem; padding-bottom: 0;">
        <span class="panel-title">[SUMMARY] Multimodal Recovery Metrics</span>
        <span id="metrics-provenance-tag" class="tag tag-copper">AWAITING RUN / CACHED</span>
      </div>

      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem;">
        <div class="panel" style="margin-bottom: 0; background: var(--bg-surface);">
          <div style="font-family: var(--font-mono); font-size: 10.5px; text-transform: uppercase; color: var(--text-muted); font-weight: 700;">
            Authentic Recovery
          </div>
          <div id="stat-auth-recovery" style="font-family: var(--font-mono); font-size: 26px; font-weight: 700; color: var(--accent-green); margin-top: 0.4rem;">
            --%
          </div>
          <div style="font-size: 11px; color: var(--text-muted); margin-top: 0.25rem;">
            Verifiable carved bytes
          </div>
        </div>

        <div class="panel" style="margin-bottom: 0; background: var(--bg-surface);">
          <div style="font-family: var(--font-mono); font-size: 10.5px; text-transform: uppercase; color: var(--text-muted); font-weight: 700;">
            Text Token Jaccard
          </div>
          <div id="stat-text-jaccard" style="font-family: var(--font-mono); font-size: 26px; font-weight: 700; color: var(--accent-cyan); margin-top: 0.4rem;">
            --
          </div>
          <div style="font-size: 11px; color: var(--text-muted); margin-top: 0.25rem;">
            Ground-truth lexical overlap
          </div>
        </div>

        <div class="panel" style="margin-bottom: 0; background: var(--bg-surface);">
          <div style="font-family: var(--font-mono); font-size: 10.5px; text-transform: uppercase; color: var(--text-muted); font-weight: 700;">
            Table Grid Recovery
          </div>
          <div id="stat-table-recovery" style="font-family: var(--font-mono); font-size: 26px; font-weight: 700; color: #a78bfa; margin-top: 0.4rem;">
            --%
          </div>
          <div style="font-size: 11px; color: var(--text-muted); margin-top: 0.25rem;">
            Row/column alignment rate
          </div>
        </div>

        <div class="panel" style="margin-bottom: 0; background: var(--bg-surface);">
          <div style="font-family: var(--font-mono); font-size: 10.5px; text-transform: uppercase; color: var(--text-muted); font-weight: 700;">
            Equation Salvage
          </div>
          <div id="stat-equation-recovery" style="font-family: var(--font-mono); font-size: 26px; font-weight: 700; color: var(--accent-amber); margin-top: 0.4rem;">
            --%
          </div>
          <div style="font-size: 11px; color: var(--text-muted); margin-top: 0.25rem;">
            Formulas &amp; LaTeX transcription
          </div>
        </div>

        <div class="panel" style="margin-bottom: 0; background: var(--bg-surface);">
          <div style="font-family: var(--font-mono); font-size: 10.5px; text-transform: uppercase; color: var(--text-muted); font-weight: 700;">
            Parser Openability
          </div>
          <div id="stat-parser-validity" style="font-family: var(--font-mono); font-size: 26px; font-weight: 700; color: #f472b6; margin-top: 0.4rem;">
            --%
          </div>
          <div style="font-size: 11px; color: var(--text-muted); margin-top: 0.25rem;">
            ISO 32000-1 conformance
          </div>
        </div>

        <div class="panel" style="margin-bottom: 0; background: var(--bg-surface);">
          <div style="font-family: var(--font-mono); font-size: 10.5px; text-transform: uppercase; color: var(--text-muted); font-weight: 700;">
            AI Inferred Content
          </div>
          <div id="stat-ai-inferred" style="font-family: var(--font-mono); font-size: 26px; font-weight: 700; color: var(--text-secondary); margin-top: 0.4rem;">
            --%
          </div>
          <div style="font-size: 11px; color: var(--text-muted); margin-top: 0.25rem;">
            Clearly distinguished provenance
          </div>
        </div>
      </div>
    </div>

    <!-- SECTION 1: VERIFIED OPEN-ACCESS DOCUMENT REGISTRY -->
    <div class="panel" style="padding: 0; overflow: hidden; margin-bottom: 2rem;">
      <div style="padding: 1.25rem 1.5rem; border-bottom: 1px solid var(--border-subtle); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.75rem;">
        <div>
          <span class="panel-title">[1] Verified Open-Access Document Registry</span>
          <p style="font-size: 12.5px; color: var(--text-muted); margin-top: 4px; margin-bottom: 0;">
            Candidate open-access research papers (arXiv CC-BY-4.0), W3C standards, and NIST publications with verified licenses and cryptographic SHA-256 hashes.
          </p>
        </div>
        <span class="tag tag-copper">{len(docs)} REGISTERED ITEMS</span>
      </div>

      <div class="table-container" style="border: none; margin-bottom: 0;">
        <table class="data-table">
          <thead>
            <tr>
              <th>Document Title &amp; ID</th>
              <th>License Terms</th>
              <th>Pages / Size</th>
              <th>Multimodal Characteristics</th>
              <th>Ground Truth Status</th>
            </tr>
          </thead>
          <tbody>
            {rendered_doc_rows}
          </tbody>
        </table>
      </div>
    </div>

    <!-- SECTION 2: GENUINELY DAMAGED TEST CORPUS -->
    <div class="panel" style="padding: 0; overflow: hidden; margin-bottom: 2rem;">
      <div style="padding: 1.25rem 1.5rem; border-bottom: 1px solid var(--border-subtle); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.75rem;">
        <div>
          <span class="panel-title">[2] Genuinely Damaged PDF Test Corpus</span>
          <p style="font-size: 12.5px; color: var(--text-muted); margin-top: 4px; margin-bottom: 0;">
            Authentic malformed PDFs from DARPA SafeDocs and public corpora. Evaluated without fabricated ground truth to maintain evidentiary integrity.
          </p>
        </div>
        <span class="tag tag-amber">{len(genuine_samples)} MALFORMED SAMPLES</span>
      </div>

      <div class="table-container" style="border: none; margin-bottom: 0;">
        <table class="data-table">
          <thead>
            <tr>
              <th>Sample Identifier</th>
              <th>Corpus License</th>
              <th>Observed Damage Classes</th>
              <th>Static Safety Scan</th>
              <th>Evidentiary Policy</th>
            </tr>
          </thead>
          <tbody>
            {rendered_genuine_rows}
          </tbody>
        </table>
      </div>
    </div>

    <!-- SECTION 3: SCIENTIFIC HONESTY & EVALUATION INVARIANTS -->
    <div class="panel">
      <div class="panel-header">
        <span class="panel-title">[3] Evidentiary Integrity &amp; Benchmarking Governance</span>
        <span class="tag tag-green">DAUBERT / FRYE ADMISSIBILITY</span>
      </div>
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1.5rem;">
        <div>
          <h4 style="font-family: var(--font-mono); font-size: 12px; color: var(--accent-copper); margin-bottom: 0.5rem; text-transform: uppercase;">
            Document-Level Split Isolation
          </h4>
          <p style="font-size: 12.5px; color: var(--text-secondary); line-height: 1.6;">
            Splitting occurs strictly at the parent document level. All corruptions derived from a given document remain in its designated split (train, validation, or test) with zero cross-set leakage.
          </p>
        </div>

        <div>
          <h4 style="font-family: var(--font-mono); font-size: 12px; color: var(--accent-cyan); margin-bottom: 0.5rem; text-transform: uppercase;">
            Zero Fabricated Ground Truth
          </h4>
          <p style="font-size: 12.5px; color: var(--text-secondary); line-height: 1.6;">
            Where original source documents do not exist (e.g. DARPA SafeDocs malformed issues), TRACE refuses to invent pseudo ground truth. Evaluations remain strictly qualitative diagnostics.
          </p>
        </div>

        <div>
          <h4 style="font-family: var(--font-mono); font-size: 12px; color: var(--accent-green); margin-bottom: 0.5rem; text-transform: uppercase;">
            Authentic vs Inferred Separation
          </h4>
          <p style="font-size: 12.5px; color: var(--text-secondary); line-height: 1.6;">
            Every salvaged byte is tracked to its physical offset. Authentic carved content, structural synthetic repair, and generative inferences are maintained in separate, distinct artifacts.
          </p>
        </div>
      </div>
    </div>
  </div>
</main>
"""

    extra_scripts = """
<script>
let timerInterval = null;
let secondsElapsed = 0;

function updateTimer() {
    secondsElapsed++;
    const mins = String(Math.floor(secondsElapsed / 60)).padStart(2, '0');
    const secs = String(secondsElapsed % 60).padStart(2, '0');
    const el = document.getElementById('benchmark-status-timer');
    if (el) el.innerText = `${mins}:${secs}`;
}

async function triggerLiveBenchmark() {
    const btn1 = document.getElementById('btn-run-benchmark');
    const btn2 = document.getElementById('btn-run-panel');
    const statusBox = document.getElementById('benchmark-status-box');
    const statusTitle = document.getElementById('benchmark-status-title');
    const statusDesc = document.getElementById('benchmark-status-desc');
    const samplesSelect = document.getElementById('cfg-samples-per-doc');
    const maxDocsSelect = document.getElementById('cfg-max-docs');

    const samplesPerDoc = samplesSelect ? samplesSelect.value : 2;
    const maxDocs = maxDocsSelect ? maxDocsSelect.value : 2;

    if (btn1) { btn1.disabled = true; btn1.innerText = 'Running Benchmark...'; }
    if (btn2) { btn2.disabled = true; btn2.innerText = 'Evaluating...'; }

    statusBox.style.display = 'block';
    statusTitle.style.color = 'var(--accent-copper)';
    statusTitle.innerText = 'BENCHMARK RUN IN PROGRESS';
    statusDesc.innerText = `Ingesting ${maxDocs} candidate document(s), generating ${samplesPerDoc} isolated controlled corruptions per document, running multimodal reconstruction engine, and verifying parser conformance...`;

    secondsElapsed = 0;
    if (timerInterval) clearInterval(timerInterval);
    timerInterval = setInterval(updateTimer, 1000);

    try {
        const url = `/api/datasets/benchmark/run?samples_per_doc=${samplesPerDoc}&max_docs=${maxDocs}`;
        const resp = await fetch(url, { method: 'POST' });
        
        if (!resp.ok) {
            throw new Error(`Server returned HTTP ${resp.status}: ${resp.statusText}`);
        }

        const data = await resp.json();
        clearInterval(timerInterval);

        statusTitle.style.color = 'var(--accent-green)';
        statusTitle.innerText = 'BENCHMARK COMPLETED SUCCESSFULLY';
        const ctrl = data.controlled_benchmark_summary || {};
        const gen = data.genuinely_damaged_summary || {};

        statusDesc.innerText = `Evaluated ${ctrl.total_controlled_samples || 0} controlled corruption(s) and ${gen.total_genuinely_damaged_samples || 0} genuine damaged sample(s). Authentic Recovery: ${ctrl.avg_authentic_byte_recovery_pct || 0}%, Text Jaccard: ${ctrl.avg_text_jaccard_similarity || 0}, Parser Openability: ${ctrl.parser_validity_rate || 0}%.`;

        populateMetrics(ctrl, 'COMPLETED LIVE RUN');
    } catch (err) {
        clearInterval(timerInterval);
        statusTitle.style.color = 'var(--accent-red)';
        statusTitle.innerText = 'BENCHMARK FAILED';
        statusDesc.innerText = `Error executing benchmark: ${err.message}`;
    } finally {
        if (btn1) { btn1.disabled = false; btn1.innerText = '⚡ Run Live Benchmark'; }
        if (btn2) { btn2.disabled = false; btn2.innerText = 'Run Benchmark Now'; }
    }
}

function populateMetrics(ctrlSummary, tagLabel) {
    if (!ctrlSummary) return;

    const elAuth = document.getElementById('stat-auth-recovery');
    const elJaccard = document.getElementById('stat-text-jaccard');
    const elTable = document.getElementById('stat-table-recovery');
    const elEq = document.getElementById('stat-equation-recovery');
    const elParser = document.getElementById('stat-parser-validity');
    const elAi = document.getElementById('stat-ai-inferred');
    const elTag = document.getElementById('metrics-provenance-tag');

    if (elAuth && ctrlSummary.avg_authentic_byte_recovery_pct !== undefined) {
        elAuth.innerText = `${ctrlSummary.avg_authentic_byte_recovery_pct}%`;
    }
    if (elJaccard && ctrlSummary.avg_text_jaccard_similarity !== undefined) {
        elJaccard.innerText = `${ctrlSummary.avg_text_jaccard_similarity}`;
    }
    if (elTable && ctrlSummary.avg_table_recovery_rate !== undefined) {
        elTable.innerText = `${Math.round(ctrlSummary.avg_table_recovery_rate * 100)}%`;
    }
    if (elEq && ctrlSummary.avg_equation_recovery_rate !== undefined) {
        elEq.innerText = `${Math.round(ctrlSummary.avg_equation_recovery_rate * 100)}%`;
    }
    if (elParser && ctrlSummary.parser_validity_rate !== undefined) {
        elParser.innerText = `${ctrlSummary.parser_validity_rate}%`;
    }
    if (elAi && ctrlSummary.avg_ai_inferred_pct !== undefined) {
        elAi.innerText = `${ctrlSummary.avg_ai_inferred_pct}%`;
    }
    if (elTag && tagLabel) {
        elTag.innerText = tagLabel;
        elTag.className = 'tag tag-green';
    }
}

async function refreshBenchmarkStatus() {
    try {
        const resp = await fetch('/api/datasets/benchmark/status');
        if (!resp.ok) return;
        const data = await resp.json();
        if (data.has_cached_run && data.latest_run) {
            const ctrl = data.latest_run.controlled_benchmark_summary;
            if (ctrl) {
                populateMetrics(ctrl, 'CACHED BENCHMARK RUN');
            }
        }
    } catch (e) {
        console.warn('Could not load cached benchmark status:', e);
    }
}

// Auto-load cached metrics on page load
document.addEventListener('DOMContentLoaded', refreshBenchmarkStatus);
</script>
"""

    return wrap_page(
        title="Dataset Benchmarks & Real-World Evaluation",
        content=content,
        active_route="benchmark",
        extra_scripts=extra_scripts,
    )
