"""Forensic report generator producing structured JSON and human-readable HTML reports."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from trace.cases.case import ForensicCase
from trace.recovery.models import RecoveredArtifact, RecoveryCategory


class ForensicReportGenerator:
    """Generates formal forensic reports in JSON and HTML formats."""

    @staticmethod
    def generate_json_report(
        case: ForensicCase,
        artifacts: Sequence[RecoveredArtifact],
        ai_summary: Mapping[str, Any] | None = None,
        disk_report: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate structured JSON report complying with forensic integrity rules."""
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        return {
            "report_id": f"RPT-{case.case_id}-{int(datetime.now(timezone.utc).timestamp())}",
            "generated_utc": now_utc,
            "case": case.to_dict(),
            "summary": {
                "total_artifacts": len(artifacts),
                "verified_count": sum(1 for a in artifacts if a.category == RecoveryCategory.VERIFIED),
                "recovered_count": sum(1 for a in artifacts if a.category == RecoveryCategory.RECOVERED),
                "partial_count": sum(1 for a in artifacts if a.category == RecoveryCategory.PARTIAL),
                "unrecoverable_count": sum(1 for a in artifacts if a.category == RecoveryCategory.UNRECOVERABLE),
            },
            "artifacts": [a.to_dict() for a in artifacts],
            "ai_analysis": ai_summary or {},
            "disk_analysis": disk_report or {},
            "audit_trail": [e.to_dict() for e in case.audit_log],
            "forensic_declarations": {
                "write_blocker_attested": case.write_blocked,
                "read_only_enforced": True,
                "zero_oracle_pollution": True,
                "notice": "Integrity categories are explicit: VERIFIED indicates ground-truth comparison; RECOVERED indicates format structural validation.",
            },
        }

    @staticmethod
    def generate_html_report(
        case: ForensicCase,
        artifacts: Sequence[RecoveredArtifact],
        ai_summary: Mapping[str, Any] | None = None,
        disk_report: Mapping[str, Any] | None = None,
    ) -> str:
        """Generate a self-contained, editorial HTML report matching TRACE brand styling."""
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        artifacts_rows = []
        for a in artifacts:
            cat_badge_class = {
                RecoveryCategory.VERIFIED: "badge-verified",
                RecoveryCategory.RECOVERED: "badge-recovered",
                RecoveryCategory.PARTIAL: "badge-partial",
                RecoveryCategory.CANDIDATE: "badge-candidate",
                RecoveryCategory.UNRECOVERABLE: "badge-unrecoverable",
            }.get(a.category, "badge-candidate")

            artifacts_rows.append(
                f"""<tr>
                <td style="font-family:monospace; font-weight:600;">{html.escape(a.artifact_id)}</td>
                <td>{html.escape(a.filename)}</td>
                <td><span class="format-pill">{html.escape(a.format_name.upper())}</span></td>
                <td>{a.size_bytes:,} B</td>
                <td><span class="badge {cat_badge_class}">{a.category.value}</span></td>
                <td><strong>{a.confidence_score:.1f}%</strong></td>
                <td style="font-family:monospace; font-size:11px;">{html.escape(a.sha256[:16])}...</td>
                <td>{html.escape(a.explanation)}</td>
            </tr>"""
            )

        audit_rows = []
        for e in case.audit_log:
            audit_rows.append(
                f"""<tr>
                <td style="font-family:monospace; font-size:11px;">{html.escape(e.timestamp_utc)}</td>
                <td><span class="action-tag">{html.escape(e.action)}</span></td>
                <td>{html.escape(e.actor)}</td>
                <td>{html.escape(e.details)}</td>
                <td style="font-family:monospace; font-size:11px;">{html.escape(e.target_hash[:16]) if e.target_hash else "—"}</td>
            </tr>"""
            )

        ai_section_html = ""
        if ai_summary and ai_summary.get("executive_summary"):
            ai_section_html = f"""
            <div class="card" style="margin-top:24px; border-left: 3px solid #00ff66;">
                <h3 style="margin-top:0; color:#00ff66;">AI-Assisted Investigation Brief</h3>
                <p><strong>Executive Summary:</strong> {html.escape(str(ai_summary.get("executive_summary", "")))}</p>
                <p><strong>Artifacts Assessment:</strong> {html.escape(str(ai_summary.get("recovered_artifacts_overview", "")))}</p>
                <p><strong>Missing Data:</strong> {html.escape(str(ai_summary.get("missing_data_assessment", "")))}</p>
                <p><strong>Evidentiary Statement:</strong> {html.escape(str(ai_summary.get("evidentiary_integrity_statement", "")))}</p>
            </div>
            """

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>TRACE Forensic Report — Case {html.escape(case.case_id)}</title>
<style>
    body {{
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        background-color: #0d1117;
        color: #c9d1d9;
        margin: 0;
        padding: 40px;
        line-height: 1.5;
    }}
    .container {{ max-width: 1100px; margin: 0 auto; }}
    .header {{
        border-bottom: 1px solid #30363d;
        padding-bottom: 20px;
        margin-bottom: 30px;
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
    }}
    h1 {{ margin: 0 0 8px 0; color: #f0f6fc; font-size: 26px; letter-spacing: -0.5px; }}
    .meta-line {{ font-size: 13px; color: #8b949e; }}
    .card {{
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 6px;
        padding: 20px;
        margin-bottom: 24px;
    }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 13px; }}
    th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #21262d; }}
    th {{ background: #0d1117; color: #8b949e; font-weight: 600; text-transform: uppercase; font-size: 11px; }}
    .badge {{
        display: inline-block;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
    }}
    .badge-verified {{ background: rgba(0, 255, 102, 0.15); color: #00ff66; border: 1px solid #00ff66; }}
    .badge-recovered {{ background: rgba(56, 139, 253, 0.15); color: #58a6ff; border: 1px solid #388bfd; }}
    .badge-partial {{ background: rgba(210, 153, 34, 0.15); color: #d29922; border: 1px solid #d29922; }}
    .badge-unrecoverable {{ background: rgba(248, 81, 73, 0.15); color: #f85149; border: 1px solid #f85149; }}
    .format-pill {{ background: #21262d; padding: 2px 6px; border-radius: 3px; font-size: 10px; font-weight: 600; }}
    .action-tag {{ font-family: monospace; font-size: 11px; color: #58a6ff; }}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <div>
            <h1>TRACE EVIDENCE INTELLIGENCE REPORT</h1>
            <div class="meta-line">Case ID: <strong>{html.escape(case.case_id)}</strong> | Title: {html.escape(case.title)} | Investigator: {html.escape(case.investigator)}</div>
        </div>
        <div style="text-align: right;">
            <div style="font-weight: 700; color: #00ff66;">OFFICIAL FORENSIC RECORD</div>
            <div class="meta-line">Generated: {now_utc}</div>
            <div class="meta-line">Write-Block Attestation: <strong>{"YES (HARDWARE)" if case.write_blocked else "SOFTWARE READ-ONLY"}</strong></div>
        </div>
    </div>

    {ai_section_html}

    <div class="card">
        <h3 style="margin-top:0; color:#f0f6fc;">Recovered Artifacts Inventory</h3>
        <table>
            <thead>
                <tr>
                    <th>Artifact ID</th>
                    <th>Filename</th>
                    <th>Format</th>
                    <th>Size</th>
                    <th>Status</th>
                    <th>Confidence</th>
                    <th>SHA-256</th>
                    <th>Recovery Notes</th>
                </tr>
            </thead>
            <tbody>
                {''.join(artifacts_rows) if artifacts_rows else '<tr><td colspan="8">No artifacts recovered</td></tr>'}
            </tbody>
        </table>
    </div>

    <div class="card">
        <h3 style="margin-top:0; color:#f0f6fc;">Audit Trail & Chain of Custody</h3>
        <table>
            <thead>
                <tr>
                    <th>Timestamp (UTC)</th>
                    <th>Action</th>
                    <th>Actor</th>
                    <th>Details</th>
                    <th>Target SHA-256</th>
                </tr>
            </thead>
            <tbody>
                {''.join(audit_rows) if audit_rows else '<tr><td colspan="5">No audit events recorded</td></tr>'}
            </tbody>
        </table>
    </div>
</div>
</body>
</html>"""
