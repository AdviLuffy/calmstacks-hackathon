"""Unified forensic disk image analyzer and unallocated space carver."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from trace.recovery.core.carver import MultiFormatCarver
from trace.recovery.disk.fat32 import Fat32FileEntry, Fat32Parser
from trace.recovery.disk.mbr_gpt import PartitionInfo, parse_gpt, parse_mbr
from trace.recovery.disk.ntfs import NtfsFileEntry, NtfsParser
from trace.recovery.disk.safety import ReadOnlyEvidenceReader
from trace.recovery.models import RecoveredArtifact, RecoveryCategory


@dataclass
class DiskAnalysisReport:
    """Comprehensive findings from forensic disk image analysis."""

    image_path: str
    image_size_bytes: int
    image_sha256: str
    write_blocked_attested: bool
    partition_scheme: str  # "MBR", "GPT", or "RAW"
    partitions: list[PartitionInfo] = field(default_factory=list)
    filesystem_files: list[dict[str, Any]] = field(default_factory=list)
    carved_artifacts: list[RecoveredArtifact] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unallocated_regions: list[dict[str, int]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "image_path": self.image_path,
            "image_size_bytes": self.image_size_bytes,
            "image_sha256": self.image_sha256,
            "write_blocked_attested": self.write_blocked_attested,
            "partition_scheme": self.partition_scheme,
            "partitions": [
                {
                    "index": p.partition_index,
                    "scheme": p.scheme,
                    "type": p.partition_type,
                    "start_lba": p.start_lba,
                    "end_lba": p.end_lba,
                    "size_bytes": p.size_bytes,
                    "name": p.name,
                }
                for p in self.partitions
            ],
            "filesystem_files_count": len(self.filesystem_files),
            "filesystem_files": self.filesystem_files,
            "carved_artifacts_count": len(self.carved_artifacts),
            "carved_artifacts": [a.to_dict() for a in self.carved_artifacts],
            "warnings": self.warnings,
            "unallocated_regions": self.unallocated_regions,
        }


class ForensicDiskAnalyzer:
    """Read-only disk image processor for partitions, filesystems, and unallocated carving."""

    def __init__(self, write_blocked: bool = False) -> None:
        self.write_blocked = write_blocked
        self.carver = MultiFormatCarver()

    def analyze_image(self, path: Path | str) -> DiskAnalysisReport:
        """Execute complete non-destructive read-only forensic analysis of a disk image."""
        target_path = Path(path).resolve()
        with ReadOnlyEvidenceReader(target_path, write_blocked=self.write_blocked) as reader:
            image_bytes = reader.read_bytes()
            image_sha256 = reader.sha256

        return self.analyze_bytes(
            image_bytes=image_bytes,
            source_name=target_path.name,
            image_sha256=image_sha256,
        )

    def analyze_bytes(
        self, image_bytes: bytes, source_name: str = "disk.img", image_sha256: str = ""
    ) -> DiskAnalysisReport:
        """Analyze disk image from bytes in memory."""
        if not image_sha256:
            image_sha256 = hashlib.sha256(image_bytes).hexdigest()

        warnings: list[str] = []
        if not self.write_blocked:
            warnings.append(
                "NOTICE: No physical write-blocker attestation verified. Software read-only mode enforced."
            )

        # 1. Partition Analysis
        partitions: list[PartitionInfo] = []
        partition_scheme = "RAW"

        gpt_parts = parse_gpt(image_bytes)
        if gpt_parts:
            partitions = gpt_parts
            partition_scheme = "GPT"
        else:
            mbr_parts = parse_mbr(image_bytes[:512])
            if mbr_parts:
                partitions = mbr_parts
                partition_scheme = "MBR"

        # 2. Filesystem Analysis
        fs_files: list[dict[str, Any]] = []

        # Analyze whole image or each partition for FAT32 / NTFS
        targets_to_inspect: list[tuple[int, bytes]] = []
        if partitions:
            for p in partitions:
                start_byte = p.start_lba * 512
                part_data = image_bytes[start_byte : start_byte + p.size_bytes]
                if part_data:
                    targets_to_inspect.append((start_byte, part_data))
        else:
            targets_to_inspect.append((0, image_bytes))

        for base_offset, p_bytes in targets_to_inspect:
            # Check FAT32
            fat_parser = Fat32Parser(p_bytes)
            if fat_parser.bpb:
                entries = fat_parser.scan_directory()
                for e in entries:
                    fs_files.append(
                        {
                            "filesystem": "FAT32",
                            "name": e.name,
                            "is_deleted": e.is_deleted,
                            "is_directory": e.is_directory,
                            "size_bytes": e.size_bytes,
                            "first_cluster": e.first_cluster,
                            "recovered_data_size": len(e.data),
                            "sha256": hashlib.sha256(e.data).hexdigest() if e.data else "",
                        }
                    )

            # Check NTFS
            ntfs_parser = NtfsParser(p_bytes)
            if ntfs_parser.vbr:
                ntfs_entries = ntfs_parser.scan_mft_records()
                for ne in ntfs_entries:
                    fs_files.append(
                        {
                            "filesystem": "NTFS",
                            "name": ne.name,
                            "is_deleted": ne.is_deleted,
                            "is_directory": ne.is_directory,
                            "size_bytes": ne.size_bytes,
                            "record_number": ne.record_number,
                            "recovered_data_size": len(ne.data),
                            "sha256": hashlib.sha256(ne.data).hexdigest() if ne.data else "",
                        }
                    )

        # 3. Multi-Format Carving across the entire byte stream
        carved = self.carver.carve_raw_stream(image_bytes, max_artifacts=30)

        return DiskAnalysisReport(
            image_path=source_name,
            image_size_bytes=len(image_bytes),
            image_sha256=image_sha256,
            write_blocked_attested=self.write_blocked,
            partition_scheme=partition_scheme,
            partitions=partitions,
            filesystem_files=fs_files,
            carved_artifacts=carved,
            warnings=warnings,
        )
