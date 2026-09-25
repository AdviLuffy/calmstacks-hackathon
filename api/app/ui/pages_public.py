"""TRACE Public Brand Pages: Home, Product, About, Privacy, and Terms."""

from __future__ import annotations

from app.ui.components import wrap_page


def home_page() -> str:
    content = """
<main class="page-main">
  <!-- HERO SECTION -->
  <section class="container-wide" style="padding: 2.5rem 0 4rem; border-bottom: 1px solid var(--border-subtle);">
    <div style="max-width: 960px;">
      <div class="section-eyebrow">Digital Forensics &amp; Evidence Intelligence</div>
      <h1 style="font-size: 38px; font-weight: 700; letter-spacing: -0.03em; line-height: 1.18; margin-bottom: 1.25rem; color: var(--text-primary);">
        Deterministic byte reconstruction for digital evidence.
      </h1>
      <p style="font-size: 16.5px; line-height: 1.6; color: var(--text-secondary); margin-bottom: 2rem; max-width: 820px;">
        Eliminate speculative analysis. CalmStacks TRACE reassembles raw, fragmented disk images with 100% authentic byte-level provenance, strictly validates frozen contract schemas, and grounds intelligence claims against verifiable physical media offsets.
      </p>

      <div style="display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 2.5rem;">
        <a href="/investigations" class="btn btn-primary" style="padding: 0.75rem 1.5rem; font-size: 12px;">Open Investigations Workspace</a>
        <a href="/investigations/new" class="btn btn-secondary" style="padding: 0.75rem 1.5rem; font-size: 12px;">+ Ingest New Evidence</a>
        <a href="/product" class="btn btn-ghost" style="padding: 0.75rem 1.5rem; font-size: 12px;">Explore Forensic Architecture &rarr;</a>
      </div>

      <div style="display: flex; gap: 2rem; flex-wrap: wrap; font-family: var(--font-mono); font-size: 11.5px; color: var(--text-muted); border-top: 1px solid var(--border-subtle); padding-top: 1.25rem;">
        <div><span style="color: var(--accent-copper); font-weight: 700;">[P1]</span> Authentic Byte Carver</div>
        <div><span style="color: var(--accent-cyan); font-weight: 700;">[P2]</span> M0 Frozen Contract</div>
        <div><span style="color: var(--accent-green); font-weight: 700;">[P3]</span> Grounded Intelligence API</div>
        <div><span style="color: var(--text-primary); font-weight: 700;">ISO/IEC 27037</span> Compliant</div>
      </div>
    </div>
  </section>

  <!-- ARCHITECTURE BREAKDOWN -->
  <section class="container-wide" style="padding: 4rem 0; border-bottom: 1px solid var(--border-subtle);">
    <div class="section-eyebrow">Core Pipeline Architecture</div>
    <h2 class="section-title">Three decoupled subsystems. Zero speculative claims.</h2>
    <p class="section-lead">TRACE strictly separates byte recovery, intelligence reporting, and presentation into verifiable pipeline stages.</p>

    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 1.5rem;">
      <div class="panel" style="margin-bottom: 0;">
        <div class="panel-header">
          <span class="panel-title">[STAGE 1] EVIDENCE CARVER</span>
          <span class="tag tag-copper">P1 SUBSYSTEM</span>
        </div>
        <p style="font-size: 13px; color: var(--text-secondary); margin-bottom: 1rem; line-height: 1.6;">
          Scans raw bitstreams for magic headers, trailer tags, and Shannon entropy distributions. Deterministically reassembles shuffled PDF structures without synthetic byte interpolation.
        </p>
        <ul style="font-family: var(--font-mono); font-size: 11.5px; color: var(--text-muted); list-style: none; display: flex; flex-direction: column; gap: 0.4rem;">
          <li>&bull; Authentic bytes only (never synthesized)</li>
          <li>&bull; Candidate-only joins (byte_contiguity=False)</li>
          <li>&bull; 100% output-to-source provenance ledger</li>
        </ul>
      </div>

      <div class="panel" style="margin-bottom: 0;">
        <div class="panel-header">
          <span class="panel-title">[STAGE 2] CONTRACT VALIDATOR</span>
          <span class="tag tag-cyan">P2 SUBSYSTEM</span>
        </div>
        <p style="font-size: 13px; color: var(--text-secondary); margin-bottom: 1rem; line-height: 1.6;">
          Ingests standard <code>trace.evidence_bundle/1.0</code> bundles against the frozen M0 JSON Schema. Enforces strict vocabularies and prohibits unverified assertions.
        </p>
        <ul style="font-family: var(--font-mono); font-size: 11.5px; color: var(--text-muted); list-style: none; display: flex; flex-direction: column; gap: 0.4rem;">
          <li>&bull; M0 Frozen Contract Schema compliance</li>
          <li>&bull; Controlled vocabularies (VocabCode)</li>
          <li>&bull; Authentic empty artifacts array enforcement</li>
        </ul>
      </div>

      <div class="panel" style="margin-bottom: 0;">
        <div class="panel-header">
          <span class="panel-title">[STAGE 3] REFERENTIAL GROUNDING</span>
          <span class="tag tag-green">P3 SUBSYSTEM</span>
        </div>
        <p style="font-size: 13px; color: var(--text-secondary); margin-bottom: 1rem; line-height: 1.6;">
          FastAPI investigator service and volatile session store. Resolves evidentiary references to physical fragment offsets, ensuring every finding is grounded in immutable proof.
        </p>
        <ul style="font-family: var(--font-mono); font-size: 11.5px; color: var(--text-muted); list-style: none; display: flex; flex-direction: column; gap: 0.4rem;">
          <li>&bull; Local-first volatile in-memory storage</li>
          <li>&bull; Cryptographic token reference resolution</li>
          <li>&bull; Complete session audit and report exports</li>
        </ul>
      </div>
    </div>
  </section>

  <!-- SCIENTIFIC INVARIANTS & ADMISSIBILITY -->
  <section class="container-wide" style="padding: 4rem 0;">
    <div class="section-eyebrow">Evidentiary Rigor</div>
    <h2 class="section-title">Built for judicial scrutiny and legal admissibility.</h2>
    <p class="section-lead">Designed in alignment with Daubert v. Merrell Dow Pharmaceuticals and ISO/IEC 27037 standards.</p>

    <div class="table-container">
      <table class="data-table">
        <thead>
          <tr>
            <th>Forensic Invariant</th>
            <th>Conventional Tooling</th>
            <th>TRACE Platform Standard</th>
            <th>Admissibility Verification</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td class="code-cell">Byte Reconstruction</td>
            <td>Approximates missing sectors with zero padding</td>
            <td>Authentic-bytes-only; zero synthetic byte interpolation</td>
            <td><span class="tag tag-green">STRICT RECOVERY</span></td>
          </tr>
          <tr>
            <td class="code-cell">Fragment Relationships</td>
            <td>Heuristically links fragments without contiguity proof</td>
            <td>Candidate-only relationships; byte_contiguity explicitly False</td>
            <td><span class="tag tag-copper">DAUBERT COMPLIANT</span></td>
          </tr>
          <tr>
            <td class="code-cell">Provenance Ledger</td>
            <td>Partial or absent byte-to-media tracking</td>
            <td>1:1 mapping from every output byte to physical media offset</td>
            <td><span class="tag tag-cyan">100% COVERAGE</span></td>
          </tr>
          <tr>
            <td class="code-cell">Hardware Write-Block</td>
            <td>Assumes protection or auto-fills verified status</td>
            <td>Explicit examiner attestation required; warns on unverified state</td>
            <td><span class="tag tag-amber">ISO/IEC 27037 A13</span></td>
          </tr>
        </tbody>
      </table>
    </div>

    <div style="text-align: center; padding-top: 1.5rem;">
      <a href="/investigations" class="btn btn-primary" style="font-size: 12px; padding: 0.75rem 2rem;">Launch TRACE Forensic Workstation</a>
    </div>
  </section>
</main>
"""
    return wrap_page(title="Forensic Evidence Reconstruction", content=content, active_route="home")


def product_page() -> str:
    content = """
<main class="page-main">
  <div class="container-prose">
    <div class="section-eyebrow">Product Architecture</div>
    <h1 class="section-title">The TRACE Forensic Pipeline Workflow</h1>
    <p class="section-lead">
      An end-to-end overview of how raw media bitstreams are ingested, carved, reconstructed, validated against frozen contract schemas, and grounded in cryptographic proof.
    </p>

    <div class="panel">
      <div class="panel-header">
        <span class="panel-title">Stage 01 &mdash; Ingestion &amp; Write-Block Attestation</span>
        <span class="tag tag-copper">ISO/IEC 27037</span>
      </div>
      <p style="font-size: 13px; color: var(--text-secondary); line-height: 1.6; margin-bottom: 0.75rem;">
        Before physical carving begins, TRACE computes authoritative SHA-256 and MD5 cryptographic digests across the raw source bitstream. In accordance with ISO/IEC 27037 Clause 6.3, hardware write-blocker status must be explicitly attested by the examiner.
      </p>
      <p style="font-size: 13px; color: var(--text-muted); line-height: 1.6;">
        If write-block validation is not confirmed, TRACE marks media hashes as unverified and injects the canonical warning <code>WRITE_BLOCK_NOT_VERIFIED</code> into the evidence bundle audit trail.
      </p>
    </div>

    <div class="panel">
      <div class="panel-header">
        <span class="panel-title">Stage 02 &mdash; Deterministic Carving &amp; Structural Profiling</span>
        <span class="tag tag-copper">P1 ENGINE</span>
      </div>
      <p style="font-size: 13px; color: var(--text-secondary); line-height: 1.6; margin-bottom: 0.75rem;">
        The P1 Evidence Carver scans the bitstream using deterministic block-level windowing. For each identified segment, the engine computes:
      </p>
      <ul style="font-size: 13px; color: var(--text-secondary); line-height: 1.6; margin-left: 1.5rem; margin-bottom: 0.75rem;">
        <li>Magic byte identification and trailer marker recognition (e.g. <code>%PDF-1.</code> and <code>%%EOF</code>)</li>
        <li>Shannon entropy calculation across 256-byte blocks to distinguish compressed streams from text</li>
        <li>Structural boundary detection and object dictionary parsing</li>
      </ul>
      <p style="font-size: 13px; color: var(--text-muted); line-height: 1.6;">
        Every fragment is assigned a deterministic fragment identifier with physical start and end offsets recorded.
      </p>
    </div>

    <div class="panel">
      <div class="panel-header">
        <span class="panel-title">Stage 03 &mdash; Authentic Assembly &amp; Provenance Ledger</span>
        <span class="tag tag-copper">P1 RECONSTRUCTION</span>
      </div>
      <p style="font-size: 13px; color: var(--text-secondary); line-height: 1.6; margin-bottom: 0.75rem;">
        Reconstruction organizes shuffled fragments into valid syntactic file structures. In adherence to strict forensic invariants:
      </p>
      <ul style="font-size: 13px; color: var(--text-secondary); line-height: 1.6; margin-left: 1.5rem; margin-bottom: 0.75rem;">
        <li><strong>Authentic Bytes Only:</strong> No synthetic padding or hallucinated byte blocks are permitted.</li>
        <li><strong>Candidate-Only Relationships:</strong> Without physical sector adjacency proof, all joins are designated as candidates with <code>byte_contiguity = False</code>.</li>
        <li><strong>100% Provenance Coverage:</strong> A comprehensive ledger accounts for every byte in the reconstructed file, specifying exact originating fragment IDs and source media byte ranges.</li>
      </ul>
    </div>

    <div class="panel">
      <div class="panel-header">
        <span class="panel-title">Stage 04 &mdash; M0 Schema Validation &amp; Intelligence Grounding</span>
        <span class="tag tag-cyan">P2 &amp; P3 SUBSYSTEMS</span>
      </div>
      <p style="font-size: 13px; color: var(--text-secondary); line-height: 1.6; margin-bottom: 0.75rem;">
        The reconstructed output and fragment metadata are packaged into a canonical <code>trace.evidence_bundle/1.0</code> payload and validated against P2's frozen M0 JSON Schema.
      </p>
      <p style="font-size: 13px; color: var(--text-secondary); line-height: 1.6;">
        The P3 Investigator API resolves referential tokens (e.g., <code>fragments[FRAG-0001]</code>) back to physical offsets. Any claim generated by analytical models must be grounded in authentic byte references, preventing AI hallucinations.
      </p>
    </div>

    <div style="margin-top: 2rem; display: flex; gap: 1rem;">
      <a href="/investigations/new" class="btn btn-primary">Start New Analysis Workflow</a>
      <a href="/investigations" class="btn btn-secondary">View Investigations</a>
    </div>
  </div>
</main>
"""
    return wrap_page(title="Pipeline Architecture", content=content, active_route="product")


def about_page() -> str:
    content = """
<main class="page-main">
  <div class="container-prose">
    <div class="section-eyebrow">Engineering Principles</div>
    <h1 class="section-title">About CalmStacks TRACE</h1>
    <p class="section-lead">
      TRACE was engineered to establish scientific, repeatable, and mathematically verifiable standards for digital evidence reconstruction and intelligence analysis.
    </p>

    <div class="panel">
      <h2 style="font-size: 14px; font-family: var(--font-mono); color: var(--accent-copper); margin-bottom: 0.75rem;">THE PROBLEM: SPECULATIVE CARVING</h2>
      <p style="font-size: 13px; color: var(--text-secondary); line-height: 1.6; margin-bottom: 0.75rem;">
        Traditional digital carving tools often attempt best-guess assembly of fragmented files, inserting zero-byte padding or synthesizing headers to produce viewable documents. While convenient for quick previews, these practices contaminate the evidentiary bitstream, degrade integrity, and risk failing legal admissibility tests under Daubert and Frye standards.
      </p>
      <p style="font-size: 13px; color: var(--text-secondary); line-height: 1.6;">
        Simultaneously, the introduction of generative AI into investigative workflows introduces severe risks of hallucinated claims, fabricated timestamps, and ungrounded conclusions.
      </p>
    </div>

    <div class="panel">
      <h2 style="font-size: 14px; font-family: var(--font-mono); color: var(--accent-copper); margin-bottom: 0.75rem;">THE TRACE ARCHITECTURAL INVARIANTS</h2>
      <ul style="font-size: 13px; color: var(--text-secondary); line-height: 1.6; margin-left: 1.5rem; display: flex; flex-direction: column; gap: 0.75rem;">
        <li>
          <strong>Deterministic Provenance:</strong> Every byte of reconstructed output is mathematically tracked to an authentic physical offset on source media.
        </li>
        <li>
          <strong>Candidate-Only Joins:</strong> The system explicitly refuses to declare definitive sector contiguity without physical verification.
        </li>
        <li>
          <strong>Empirical Verification Ceilings:</strong> Claims marked COMPUTED or OBSERVED carry absolute mathematical proof. Any heuristic analysis is strictly capped at 0.70 confidence and designated as INFERRED.
        </li>
        <li>
          <strong>Strict Contract Schemas:</strong> Data exchanges between carving, intelligence, and presentation are governed by frozen, versioned JSON Schemas that reject unverified fields.
        </li>
        <li>
          <strong>Zero Telemetry:</strong> All processing occurs locally in volatile process memory. No evidence bitstreams or case identifiers are transmitted across networks.
        </li>
      </ul>
    </div>

    <div style="margin-top: 2rem;">
      <a href="/investigations" class="btn btn-primary">Open Workstation</a>
    </div>
  </div>
</main>
"""
    return wrap_page(title="About", content=content, active_route="about")


def privacy_page() -> str:
    content = """
<main class="page-main">
  <div class="container-prose">
    <div class="section-eyebrow">Governance &amp; Compliance</div>
    <h1 class="section-title">Evidentiary Privacy Policy &amp; Data Protection</h1>
    <div style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted); margin-bottom: 2rem; padding-bottom: 0.75rem; border-bottom: 1px solid var(--border-subtle);">
      DOCUMENT REF: TRACE-POL-PRIV-2026.1 &bull; STANDARD: ISO/IEC 27037:2012 &bull; REVISION: M0-FROZEN
    </div>

    <div class="panel">
      <h2 style="font-size: 13px; font-family: var(--font-mono); color: var(--accent-copper); margin-bottom: 0.5rem;">1. Local-First Processing Architecture (Zero Telemetry)</h2>
      <p style="font-size: 13px; color: var(--text-secondary); line-height: 1.6; margin-bottom: 0.5rem;">
        The CalmStacks TRACE Forensic Workstation operates under a strict local-first, Zero Telemetry architecture. All disk carving, profiling, fragment relationship reconstruction, and referential grounding are conducted entirely within the local host runtime.
      </p>
      <p style="font-size: 13px; color: var(--text-secondary); line-height: 1.6;">
        No evidentiary bitstreams, fragment hashes, or case metadata are transmitted to external servers, cloud providers, or third-party telemetry aggregators.
      </p>
    </div>

    <div class="panel">
      <h2 style="font-size: 13px; font-family: var(--font-mono); color: var(--accent-copper); margin-bottom: 0.5rem;">2. Volatile Memory Model &amp; Evidence Retention</h2>
      <p style="font-size: 13px; color: var(--text-secondary); line-height: 1.6; margin-bottom: 0.5rem;">
        In accordance with forensic data minimization principles:
      </p>
      <ul style="font-size: 13px; color: var(--text-secondary); line-height: 1.6; margin-left: 1.5rem;">
        <li><strong>In-Memory Bundles:</strong> Submitted Evidence Bundles and carved fragments are held strictly in process memory during active investigation and are never committed to permanent storage unless explicit examiner persistence (<code>TRACE_PERSIST_SESSIONS=true</code>) is authorized.</li>
        <li><strong>Process Isolation:</strong> Session termination or daemon shutdown purges in-memory byte buffers immediately, preventing residual forensic artifacts from persisting across reboots.</li>
        <li><strong>Downloadable Artifacts:</strong> Reconstructed PDF files assembled during an active session reside in transient staging memory and are provided solely for download by the authorized examiner.</li>
      </ul>
    </div>

    <div class="panel">
      <h2 style="font-size: 13px; font-family: var(--font-mono); color: var(--accent-copper); margin-bottom: 0.5rem;">3. Ground Truth Isolation &amp; Oracle Defense</h2>
      <p style="font-size: 13px; color: var(--text-secondary); line-height: 1.6;">
        Production modules (including P1 carving, P2 schema validation, and P3 reporting) are architecturally isolated from oracle manifests and ground truth fixtures. Ground truth files are accessible strictly within automated test harnesses (<code>tests/</code>) to guarantee that examiner analysis is unbiased and derived solely from authentic source media bytes.
      </p>
    </div>

    <div class="panel">
      <h2 style="font-size: 13px; font-family: var(--font-mono); color: var(--accent-copper); margin-bottom: 0.5rem;">4. Chain of Custody &amp; Examiner Attestation</h2>
      <p style="font-size: 13px; color: var(--text-secondary); line-height: 1.6;">
        All timestamps originating from carved media are preserved in UTC with trailing Z notation without timezone mutation. Hardware write-blocker status is treated as an explicit examiner attestation: write-blocking is never reported as verified unless verified through documented attestation, satisfying forensic integrity standard ISO/IEC 27037.
      </p>
    </div>
  </div>
</main>
"""
    return wrap_page(title="Privacy Policy & Data Protection", content=content, active_route="about")


def terms_page() -> str:
    content = """
<main class="page-main">
  <div class="container-prose">
    <div class="section-eyebrow">Evidentiary Standards</div>
    <h1 class="section-title">Terms of Examination &amp; Evidentiary Standards</h1>
    <div style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted); margin-bottom: 2rem; padding-bottom: 0.75rem; border-bottom: 1px solid var(--border-subtle);">
      DOCUMENT REF: TRACE-TOS-EVID-2026.1 &bull; STANDARDS: NIST SP 800-86 / ISO/IEC 27037 &bull; REVISION: M0-FROZEN
    </div>

    <div class="panel">
      <h2 style="font-size: 13px; font-family: var(--font-mono); color: var(--accent-copper); margin-bottom: 0.5rem;">1. Scope and Authorized Utilization</h2>
      <p style="font-size: 13px; color: var(--text-secondary); line-height: 1.6;">
        This software workstation is engineered specifically for digital forensic examiners, incident responders, and judicial analysts. All functionality adheres to scientific and repeatable methodologies for data recovery, carving, structural profiling, and evidence verification.
      </p>
    </div>

    <div class="panel">
      <h2 style="font-size: 13px; font-family: var(--font-mono); color: var(--accent-copper); margin-bottom: 0.5rem;">2. Daubert / Frye Forensic Invariants</h2>
      <p style="font-size: 13px; color: var(--text-secondary); line-height: 1.6; margin-bottom: 0.5rem;">
        To preserve evidentiary admissibility under Daubert v. Merrell Dow Pharmaceuticals (509 U.S. 579) and the Frye standard:
      </p>
      <ul style="font-size: 13px; color: var(--text-secondary); line-height: 1.6; margin-left: 1.5rem;">
        <li><strong>Deterministic Byte Assembly:</strong> Reconstructed files are assembled solely from authentic recovered byte blocks. The workstation strictly prohibits artificial byte synthesis, padding interpolation, or hallucinated file data.</li>
        <li><strong>Candidate-Only Joins:</strong> Where physical sector adjacency cannot be established, the system strictly mandates <code>byte_contiguity = False</code>. Definitive joins are never asserted without physical adjacency proof.</li>
        <li><strong>Complete Provenance Ledger:</strong> Every reconstructed output byte is mapped with 100% coverage back to its originating fragment and source media offset.</li>
        <li><strong>Empirical Verification Ceilings:</strong> Claims marked COMPUTED or OBSERVED carry deterministic proof. Any heuristic or AI-assisted findings are strictly capped at 0.70 confidence and designated as INFERRED.</li>
      </ul>
    </div>

    <div class="panel">
      <h2 style="font-size: 13px; font-family: var(--font-mono); color: var(--accent-copper); margin-bottom: 0.5rem;">3. Chain of Custody &amp; Forensic Integrity</h2>
      <p style="font-size: 13px; color: var(--text-secondary); line-height: 1.6;">
        The forensic examiner maintains ultimate responsibility for preserving the Chain of Custody and Forensic Integrity of original physical and digital media. The TRACE platform computes cryptographically secure SHA-256 digests over all ingested media and individual fragments, ensuring full tamper-evident auditability.
      </p>
    </div>

    <div class="panel">
      <h2 style="font-size: 13px; font-family: var(--font-mono); color: var(--accent-copper); margin-bottom: 0.5rem;">4. Write-Blocker Compliance (A13)</h2>
      <p style="font-size: 13px; color: var(--text-secondary); line-height: 1.6;">
        In adherence to ISO/IEC 27037 Clause 6.3, digital evidence acquisition requires validation that target media is protected from modification. The examiner agrees to accurately declare write-block status. Operating without verified write-blocking will be permanently tagged in the canonical Evidence Bundle audit trail.
      </p>
    </div>

    <div class="panel">
      <h2 style="font-size: 13px; font-family: var(--font-mono); color: var(--accent-copper); margin-bottom: 0.5rem;">5. Disclaimer of Warranty and Limitation of Liability</h2>
      <p style="font-size: 13px; color: var(--text-secondary); line-height: 1.6;">
        The TRACE software provides deterministic mathematical analysis based on the inputs provided. The forensic examiner maintains ultimate professional responsibility for validating findings, verifying chain-of-custody, and corroborating conclusions prior to submission in legal or regulatory proceedings.
      </p>
    </div>
  </div>
</main>
"""
    return wrap_page(title="Terms of Examination & Evidentiary Standards", content=content, active_route="about")
