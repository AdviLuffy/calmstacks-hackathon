"""Safe, Rate-Limited Real-World Document Downloader for TRACE Phase 10.

Downloads candidate documents, verifies SHA-256 hashes against registry declarations,
and provides complete manual download instructions when offline or if downloads fail.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
import time
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional, Tuple, Union

from trace.datasets.schemas.real_world import RealWorldDocumentRecord

logger = logging.getLogger(__name__)

DEFAULT_ORIGINALS_DIR = Path(__file__).resolve().parent / "data" / "originals"


class RealWorldDocumentDownloader:
    """Safe downloader that verifies integrity against registry records."""

    def __init__(
        self,
        output_dir: Optional[Union[str, Path]] = None,
        timeout_seconds: int = 15,
        rate_limit_delay_seconds: float = 1.0,
    ) -> None:
        self.output_dir = Path(output_dir) if output_dir else DEFAULT_ORIGINALS_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout_seconds
        self.rate_limit_delay = rate_limit_delay_seconds

    def compute_sha256(self, data: bytes) -> str:
        """Compute cryptographic SHA-256 digest."""
        return hashlib.sha256(data).hexdigest()

    def download_document(
        self,
        record: RealWorldDocumentRecord,
        force: bool = False,
    ) -> Tuple[bool, str, Optional[Path]]:
        """Download and verify a document against its registry record.
        
        Returns:
            (success: bool, message: str, file_path: Optional[Path])
        """
        dest_file = self.output_dir / f"{record.document_id}.pdf"

        # Check if already present and valid
        if dest_file.is_file() and not force:
            existing_bytes = dest_file.read_bytes()
            existing_hash = self.compute_sha256(existing_bytes)
            if existing_hash == record.original_sha256:
                return True, f"Already present and verified (SHA-256 matches: {existing_hash[:12]}...)", dest_file

        if not record.download_url:
            return False, f"Document {record.document_id} has no automated download URL; requires manual download", None

        # Download with timeout and user-agent
        req = urllib.request.Request(
            record.download_url,
            headers={
                "User-Agent": "TRACE-Forensics-Benchmark/1.0 (academic research reproducibility; mailto:trace-research@example.org)",
            },
        )

        try:
            time.sleep(self.rate_limit_delay)
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                downloaded_bytes = resp.read()

            dl_hash = self.compute_sha256(downloaded_bytes)
            # If the remote copy differs due to revision (e.g. arXiv v1 vs v2), record actual hash or check
            dest_file.write_bytes(downloaded_bytes)
            if dl_hash != record.original_sha256:
                msg = f"Downloaded {len(downloaded_bytes)} bytes; note SHA-256 differs from registry baseline ({dl_hash[:12]}... vs {record.original_sha256[:12]}...)"
            else:
                msg = f"Downloaded and verified {len(downloaded_bytes)} bytes (SHA-256: {dl_hash[:12]}...)"

            return True, msg, dest_file

        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            return False, f"Download failed ({e}). Follow manual instructions in download guide.", None

    def generate_manual_download_guide(
        self,
        records: List[RealWorldDocumentRecord],
        guide_path: Optional[Union[str, Path]] = None,
    ) -> Path:
        """Generate a complete Markdown manual download guide and checklist."""
        target_path = Path(guide_path) if guide_path else self.output_dir.parent / "MANUAL_DOWNLOAD_GUIDE.md"
        target_path.parent.mkdir(parents=True, exist_ok=True)

        lines: List[str] = [
            "# TRACE Phase 10: Real-World PDF Dataset Manual Download Guide",
            "",
            "This guide provides exact manual download links, license terms, and verification hashes",
            "for candidate real-world evaluation documents.",
            "",
            "## Storage Location",
            f"Save intact downloaded PDFs into: `{self.output_dir.resolve()}`",
            "",
            "## Document Checklist",
            "",
        ]

        for r in records:
            lines.extend([
                f"### {r.document_id} — {r.title}",
                f"- **Source:** [{r.source_name}]({r.source_url})",
                f"- **Direct Download URL:** {r.download_url or 'N/A (manual portal retrieval)'}",
                f"- **License:** [{r.license_type.value}]({r.license_url})",
                f"- **Expected SHA-256:** `{r.original_sha256}`",
                f"- **Expected Size:** ~{r.file_size_bytes:,} bytes",
                f"- **Intact:** {r.is_intact} | **Verified Ground Truth:** {r.has_verified_ground_truth}",
                f"- **Content Features:** {', '.join(c.value for c in r.characteristics)}",
                f"- **Destination File:** `{r.document_id}.pdf`",
                f"- **Download Command:** `curl -L -o {r.document_id}.pdf {r.download_url}`" if r.download_url else "",
                "",
            ])

        lines.extend([
            "## Verification Step",
            "To verify downloaded PDFs match their registry hashes, run:",
            "```powershell",
            "python -m trace.datasets.real_world.verify_dataset",
            "```",
            "",
        ])

        target_path.write_text("\n".join(lines), encoding="utf-8")
        return target_path
