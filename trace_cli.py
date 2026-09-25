"""TRACE Digital Forensics & Intelligent Data Recovery CLI.

Supported commands:
  trace inspect <evidence_path>
  trace recover <evidence_path> --output <dir> [--format <fmt>]
  trace analyze <evidence_path> [--ai]
  trace report <evidence_path> --format json|html --output <path>
  trace verify <recovered_file> --original <ground_truth>
  trace demo
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Sequence

# Ensure repo root and subpackages are on path
REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "evidence" / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "evidence" / "src"))

from trace.ai.client import ResilientGeminiClient
from trace.ai.config import load_gemini_settings
from trace.ai.mock_client import MockGeminiClient
from trace.ai.service import GeminiForensicService
from trace.cases.case import ForensicCase
from trace.cases.report import ForensicReportGenerator
from trace.recovery.core.carver import MultiFormatCarver
from trace.recovery.disk.disk_carver import ForensicDiskAnalyzer
from trace.recovery.disk.safety import ReadOnlyEvidenceReader
from trace.recovery.models import FragmentCandidate, RecoveredArtifact, RecoveryCategory
from trace.recovery.prioritization import RecoveryPrioritizer


def cmd_inspect(args: argparse.Namespace) -> int:
    """Inspect evidence headers, partition tables, filesystems, and format signatures."""
    target = Path(args.evidence_path).resolve()
    if not target.is_file():
        print(f"Error: File not found: {target}", file=sys.stderr)
        return 1

    print("=" * 70)
    print("TRACE FORENSIC EVIDENCE INSPECTION")
    print("=" * 70)
    print(f"Target:       {target.name}")
    print(f"Path:         {target}")

    with ReadOnlyEvidenceReader(target, write_blocked=args.write_blocked) as reader:
        data = reader.read_bytes()
        sha256_hash = reader.sha256

    print(f"Size:         {len(data):,} bytes")
    print(f"SHA-256:      {sha256_hash}")
    print(f"Write-Block:  {'HARDWARE ATTESTED' if args.write_blocked else 'SOFTWARE READ-ONLY'}")
    print("-" * 70)

    # 1. Check if Disk Image (MBR / GPT)
    analyzer = ForensicDiskAnalyzer(write_blocked=args.write_blocked)
    disk_report = analyzer.analyze_bytes(data, source_name=target.name, image_sha256=sha256_hash)

    if disk_report.partition_scheme in ("MBR", "GPT"):
        print(f"Storage Scheme: {disk_report.partition_scheme} Disk Image")
        print(f"Partitions Identified: {len(disk_report.partitions)}")
        for p in disk_report.partitions:
            print(
                f"  [{p.partition_index}] {p.partition_type} | Start LBA: {p.start_lba:,} | Size: {p.size_bytes:,} B"
            )
        if disk_report.filesystem_files:
            print(f"Filesystem Files Detected: {len(disk_report.filesystem_files)}")
            for f in disk_report.filesystem_files[:10]:
                status = "DELETED" if f.get("is_deleted") else "ACTIVE"
                print(f"  - [{f.get('filesystem')}] {f.get('name')} ({f.get('size_bytes', 0):,} B) [{status}]")
    else:
        # 2. Check File Format
        carver = MultiFormatCarver()
        confidence = carver.identify_format(data, filename=target.name)
        print(f"Detected Format: {confidence.format_name.upper()} ({confidence.mime_type})")
        print(f"Confidence:      {confidence.confidence * 100:.1f}% via {confidence.detected_by}")
        print(f"Indicators:      {', '.join(confidence.structural_indicators)}")

    print("=" * 70)
    return 0


def cmd_recover(args: argparse.Namespace) -> int:
    """Carve and reconstruct recoverable digital artifacts."""
    target = Path(args.evidence_path).resolve()
    if not target.is_file():
        print(f"Error: File not found: {target}", file=sys.stderr)
        return 1

    out_dir = Path(args.output).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    with ReadOnlyEvidenceReader(target, write_blocked=args.write_blocked) as reader:
        data = reader.read_bytes()
        sha256_hash = reader.sha256

    print("=" * 70)
    print("TRACE MULTI-FORMAT RECOVERY ENGINE")
    print("=" * 70)
    print(f"Target:       {target.name} ({len(data):,} bytes)")
    print(f"Output Dir:   {out_dir}")
    print("-" * 70)

    carver = MultiFormatCarver()
    artifacts = carver.carve_raw_stream(data, max_artifacts=args.max_artifacts)

    # Prioritize
    ranked_artifacts = RecoveryPrioritizer.prioritize_artifacts(artifacts)

    if not ranked_artifacts:
        print("No recoverable artifacts identified within supported format signatures.")
        return 0

    print(f"Artifacts Identified: {len(ranked_artifacts)}")
    print(f"{'ID':<16} {'Filename':<20} {'Format':<8} {'Size':<10} {'Status':<14} {'Score':<6}")
    print("-" * 76)

    for a in ranked_artifacts:
        print(
            f"{a.artifact_id:<16} {a.filename:<20} {a.format_name.upper():<8} "
            f"{a.size_bytes:<10,} {a.category.value:<14} {a.confidence_score:>5.1f}%"
        )
        if a.raw_bytes:
            out_file = out_dir / a.filename
            out_file.write_bytes(a.raw_bytes)

    print("=" * 70)
    print(f"Recovered {len(ranked_artifacts)} artifact(s) to: {out_dir}")
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    """Perform structural and optional AI-assisted forensic analysis."""
    target = Path(args.evidence_path).resolve()
    if not target.is_file():
        print(f"Error: File not found: {target}", file=sys.stderr)
        return 1

    with ReadOnlyEvidenceReader(target, write_blocked=args.write_blocked) as reader:
        data = reader.read_bytes()
        sha256_hash = reader.sha256

    print("=" * 70)
    print("TRACE STRUCTURAL & INTELLIGENCE ANALYSIS")
    print("=" * 70)
    print(f"Evidence:     {target.name} (SHA-256: {sha256_hash[:16]}...)")

    carver = MultiFormatCarver()
    format_conf = carver.identify_format(data, filename=target.name)
    print(f"Format:       {format_conf.format_name.upper()} (Confidence: {format_conf.confidence * 100:.1f}%)")

    # Slice into sample fragment candidates for analysis
    frag_candidate = FragmentCandidate(
        fragment_id="FRAG-0001",
        source_offset=0,
        size_bytes=min(len(data), 1024),
        data=data[:1024],
        format_hint=format_conf.format_name,
        structural_role="header",
    )

    if args.ai:
        print("-" * 70)
        print("GEMINI AI INTELLIGENCE ASSISTANCE")
        gemini_settings = load_gemini_settings()
        if not gemini_settings.enabled or not gemini_settings.api_key:
            print("Notice: Gemini API key not configured. Using deterministic offline test mock.")
            mock_client = MockGeminiClient()
            ai_service = GeminiForensicService(client=mock_client)
        else:
            ai_service = GeminiForensicService()

        print(f"Model Preference Queue: {', '.join(ai_service.client.settings.model_preference)}")
        res = ai_service.classify_fragment(frag_candidate)
        if res.success and res.data:
            print(f"AI Classification:      {res.data.likely_file_type.upper()}")
            print(f"Structural Role:        {res.data.structural_role}")
            print(f"Confidence:             {res.data.confidence * 100:.1f}%")
            print(f"Reasoning:              {res.data.reasoning}")
            print(f"Model Executed:         {res.provenance.model_used}")
            print(f"Fallback Occurred:      {res.provenance.fallback_occurred}")
        else:
            print(f"AI Analysis Status:     {res.provenance.error or 'Failed'}")

    print("=" * 70)
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Byte-for-byte verification between recovered file and known ground truth."""
    rec_path = Path(args.recovered_file).resolve()
    gt_path = Path(args.original).resolve()

    if not rec_path.is_file():
        print(f"Error: Recovered file not found: {rec_path}", file=sys.stderr)
        return 1
    if not gt_path.is_file():
        print(f"Error: Original ground-truth file not found: {gt_path}", file=sys.stderr)
        return 1

    rec_bytes = rec_path.read_bytes()
    gt_bytes = gt_path.read_bytes()

    rec_hash = hashlib.sha256(rec_bytes).hexdigest()
    gt_hash = hashlib.sha256(gt_bytes).hexdigest()

    print("=" * 70)
    print("TRACE FORENSIC BYTE-FOR-BYTE VERIFICATION")
    print("=" * 70)
    print(f"Recovered:    {rec_path.name} ({len(rec_bytes):,} bytes)")
    print(f"  SHA-256:    {rec_hash}")
    print(f"Ground Truth: {gt_path.name} ({len(gt_bytes):,} bytes)")
    print(f"  SHA-256:    {gt_hash}")
    print("-" * 70)

    if rec_bytes == gt_bytes and rec_hash == gt_hash:
        print("RESULT: 100% EXACT BYTE-FOR-BYTE MATCH [VERIFIED]")
        print("Evidentiary authenticity mathematically proven against reference ground truth.")
        print("=" * 70)
        return 0
    else:
        print("RESULT: MISMATCH [UNVERIFIED / PARTIAL]")
        diff_len = abs(len(rec_bytes) - len(gt_bytes))
        first_diff = -1
        for i in range(min(len(rec_bytes), len(gt_bytes))):
            if rec_bytes[i] != gt_bytes[i]:
                first_diff = i
                break
        print(f"Length Delta: {diff_len} bytes")
        print(f"First differing byte at offset: {first_diff}")
        print("=" * 70)
        return 2


def cmd_report(args: argparse.Namespace) -> int:
    """Generate formal JSON or HTML forensic report."""
    target = Path(args.evidence_path).resolve()
    if not target.is_file():
        print(f"Error: File not found: {target}", file=sys.stderr)
        return 1

    out_file = Path(args.output).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    with ReadOnlyEvidenceReader(target, write_blocked=args.write_blocked) as reader:
        data = reader.read_bytes()
        sha256_hash = reader.sha256

    case = ForensicCase(
        case_id=args.case_id or "CASE-REPORT-01",
        title="TRACE Forensic Examination Report",
        investigator=args.investigator or "Senior Forensic Analyst",
        write_blocked=args.write_blocked,
    )
    case.log_event("EVIDENCE_INGESTED", "Investigator", f"Ingested {target.name}", sha256_hash)

    carver = MultiFormatCarver()
    artifacts = carver.carve_raw_stream(data, max_artifacts=20)
    case.log_event("FORENSIC_CARVE", "System", f"Carved {len(artifacts)} candidate artifacts")

    fmt = args.format.lower()
    if fmt == "json":
        report_data = ForensicReportGenerator.generate_json_report(case, artifacts)
        out_file.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
    else:
        html_content = ForensicReportGenerator.generate_html_report(case, artifacts)
        out_file.write_text(html_content, encoding="utf-8")

    print(f"Forensic {fmt.upper()} report generated successfully: {out_file}")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    """Execute end-to-end multi-format demonstration with ground-truth verification."""
    from trace.recovery.dataset import run_demonstration_suite

    return run_demonstration_suite()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trace",
        description="TRACE: AI-Assisted Digital Evidence Reconstruction & Intelligent Data Recovery",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # inspect
    p_inspect = subparsers.add_parser("inspect", help="Inspect evidence headers, partitions, and signatures")
    p_inspect.add_argument("evidence_path", help="Path to evidence file or disk image")
    p_inspect.add_argument("--write-blocked", action="store_true", help="Attest hardware write-blocker usage")

    # recover
    p_recover = subparsers.add_parser("recover", help="Carve and reconstruct recoverable artifacts")
    p_recover.add_argument("evidence_path", help="Path to evidence file")
    p_recover.add_argument("--output", "-o", required=True, help="Directory to save recovered files")
    p_recover.add_argument("--format", help="Target format filter (pdf, png, jpeg, zip, text)")
    p_recover.add_argument("--max-artifacts", type=int, default=50, help="Maximum artifacts to carve")
    p_recover.add_argument("--write-blocked", action="store_true", help="Attest hardware write-blocker usage")

    # analyze
    p_analyze = subparsers.add_parser("analyze", help="Perform structural and AI-assisted analysis")
    p_analyze.add_argument("evidence_path", help="Path to evidence file")
    p_analyze.add_argument("--ai", action="store_true", help="Enable Gemini AI assistance")
    p_analyze.add_argument("--write-blocked", action="store_true", help="Attest hardware write-blocker usage")

    # verify
    p_verify = subparsers.add_parser("verify", help="Byte-for-byte verification against ground truth")
    p_verify.add_argument("recovered_file", help="Path to recovered file")
    p_verify.add_argument("--original", required=True, help="Path to reference ground-truth file")

    # report
    p_report = subparsers.add_parser("report", help="Generate forensic report")
    p_report.add_argument("evidence_path", help="Path to evidence file")
    p_report.add_argument("--output", "-o", required=True, help="Report destination file path")
    p_report.add_argument("--format", choices=["json", "html"], default="html", help="Report format")
    p_report.add_argument("--case-id", default="CASE-001", help="Case identifier")
    p_report.add_argument("--investigator", default="Forensic Analyst", help="Investigator name")
    p_report.add_argument("--write-blocked", action="store_true", help="Attest hardware write-blocker usage")

    # demo
    subparsers.add_parser("demo", help="Run full automated synthetic recovery demonstration")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "inspect":
        return cmd_inspect(args)
    elif args.command == "recover":
        return cmd_recover(args)
    elif args.command == "analyze":
        return cmd_analyze(args)
    elif args.command == "verify":
        return cmd_verify(args)
    elif args.command == "report":
        return cmd_report(args)
    elif args.command == "demo":
        return cmd_demo(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
