"""MBR (Master Boot Record) and GPT (GUID Partition Table) parser."""

from __future__ import annotations

import struct
import uuid
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class PartitionInfo:
    """Standardized partition table entry."""

    partition_index: int
    scheme: str  # "MBR" or "GPT"
    partition_type: str
    type_guid_or_code: str
    is_bootable: bool
    start_lba: int
    end_lba: int
    sector_count: int
    size_bytes: int
    name: str = ""


_MBR_TYPE_NAMES = {
    0x00: "Empty",
    0x01: "FAT12",
    0x04: "FAT16 (<32M)",
    0x05: "Extended",
    0x06: "FAT16",
    0x07: "NTFS / exFAT",
    0x0B: "FAT32 (CHS)",
    0x0C: "FAT32 (LBA)",
    0x0E: "FAT16 (LBA)",
    0x0F: "Extended (LBA)",
    0x82: "Linux swap",
    0x83: "Linux native",
    0xEE: "GPT Protective",
    0xEF: "EFI System Partition",
}


def parse_mbr(sector_0: bytes, sector_size: int = 512) -> list[PartitionInfo]:
    """Parse Master Boot Record from Sector 0 (first 512 bytes)."""
    if len(sector_0) < 512:
        return []

    # Check MBR boot signature 0x55AA at offset 510
    if sector_0[510:512] != b"\x55\xaa":
        return []

    partitions: list[PartitionInfo] = []
    # 4 partition entries of 16 bytes each starting at offset 0x1BE
    table_offset = 0x1BE
    for i in range(4):
        entry = sector_0[table_offset + i * 16 : table_offset + (i + 1) * 16]
        status, chs_first, part_type, chs_last, start_lba, sector_count = struct.unpack(
            "<B3sB3sII", entry
        )

        if part_type == 0x00 or sector_count == 0:
            continue

        type_desc = _MBR_TYPE_NAMES.get(part_type, f"Unknown (0x{part_type:02X})")
        is_boot = (status & 0x80) != 0

        partitions.append(
            PartitionInfo(
                partition_index=i + 1,
                scheme="MBR",
                partition_type=type_desc,
                type_guid_or_code=f"0x{part_type:02X}",
                is_bootable=is_boot,
                start_lba=start_lba,
                end_lba=start_lba + sector_count - 1,
                sector_count=sector_count,
                size_bytes=sector_count * sector_size,
                name=f"Partition_{i + 1}",
            )
        )

    return partitions


def parse_gpt(disk_stream: bytes, sector_size: int = 512) -> list[PartitionInfo]:
    """Parse GPT (GUID Partition Table) starting from LBA 1."""
    if len(disk_stream) < 2 * sector_size:
        return []

    # LBA 1 contains the GPT Header (92 bytes min)
    gpt_header_offset = 1 * sector_size
    gpt_header = disk_stream[gpt_header_offset : gpt_header_offset + sector_size]

    if not gpt_header.startswith(b"EFI PART"):
        return []

    try:
        (
            signature,
            revision,
            header_size,
            header_crc32,
            reserved,
            current_lba,
            backup_lba,
            first_usable_lba,
            last_usable_lba,
            disk_guid_bytes,
            part_entry_lba,
            num_part_entries,
            part_entry_size,
            part_array_crc32,
        ) = struct.unpack("<8sIIIIQQQQ16sQIII", gpt_header[:92])
    except struct.error:
        return []

    entries_offset = part_entry_lba * sector_size
    partitions: list[PartitionInfo] = []

    for i in range(min(num_part_entries, 128)):
        entry_start = entries_offset + (i * part_entry_size)
        if entry_start + part_entry_size > len(disk_stream):
            break

        entry_bytes = disk_stream[entry_start : entry_start + part_entry_size]
        type_guid_bytes = entry_bytes[:16]
        if type_guid_bytes == b"\x00" * 16:
            continue  # Unused entry

        type_guid = str(uuid.UUID(bytes_le=type_guid_bytes))
        unique_guid = str(uuid.UUID(bytes_le=entry_bytes[16:32]))
        start_lba, end_lba, attributes = struct.unpack("<QQQ", entry_bytes[32:56])
        name = entry_bytes[56:128].decode("utf-16le", errors="ignore").rstrip("\x00")

        sector_cnt = (end_lba - start_lba) + 1

        partitions.append(
            PartitionInfo(
                partition_index=i + 1,
                scheme="GPT",
                partition_type="GPT Partition",
                type_guid_or_code=type_guid,
                is_bootable=bool(attributes & 0x04),
                start_lba=start_lba,
                end_lba=end_lba,
                sector_count=sector_cnt,
                size_bytes=sector_cnt * sector_size,
                name=name or f"GPT_Part_{i + 1}",
            )
        )

    return partitions
