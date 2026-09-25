"""FAT32 file system parser: BPB analysis, directory walking, and deleted file carving."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Any, Sequence


@dataclass
class Fat32FileEntry:
    """A file or directory entry extracted from FAT32 structures."""

    name: str
    is_deleted: bool
    is_directory: bool
    size_bytes: int
    first_cluster: int
    data: bytes = field(default=b"", repr=False)
    attributes: dict[str, bool] = field(default_factory=dict)


@dataclass
class Fat32BootSector:
    """Decoded FAT32 BIOS Parameter Block (BPB)."""

    bytes_per_sector: int
    sectors_per_cluster: int
    reserved_sector_count: int
    num_fats: int
    total_sectors: int
    sectors_per_fat: int
    root_cluster: int
    volume_label: str
    fs_type: str


class Fat32Parser:
    """Read-only parser and deleted-file recovery engine for FAT32 partitions."""

    def __init__(self, partition_bytes: bytes) -> None:
        self.raw = partition_bytes
        self.bpb = self._parse_bpb()

    def _parse_bpb(self) -> Fat32BootSector | None:
        if len(self.raw) < 512:
            return None
        # Check boot signature 0x55AA
        if self.raw[510:512] != b"\x55\xaa":
            return None

        try:
            bytes_per_sec, sec_per_clus, res_sec, num_fats = struct.unpack(
                "<HBHB", self.raw[11:17]
            )
            # Total sectors (FAT32 uses offset 32)
            total_sec_16 = struct.unpack("<H", self.raw[19:21])[0]
            total_sec_32 = struct.unpack("<I", self.raw[32:36])[0]
            total_sectors = total_sec_32 if total_sec_16 == 0 else total_sec_16

            # Sectors per FAT (FAT32 offset 36)
            sec_per_fat = struct.unpack("<I", self.raw[36:40])[0]
            root_cluster = struct.unpack("<I", self.raw[44:48])[0]

            vol_label = self.raw[71:82].decode("latin-1", errors="replace").strip()
            fs_type = self.raw[82:90].decode("latin-1", errors="replace").strip()

            if bytes_per_sec == 0 or sec_per_clus == 0 or sec_per_fat == 0:
                return None

            return Fat32BootSector(
                bytes_per_sector=bytes_per_sec,
                sectors_per_cluster=sec_per_clus,
                reserved_sector_count=res_sec,
                num_fats=num_fats,
                total_sectors=total_sectors,
                sectors_per_fat=sec_per_fat,
                root_cluster=root_cluster,
                volume_label=vol_label,
                fs_type=fs_type,
            )
        except Exception:
            return None

    def cluster_to_offset(self, cluster: int) -> int:
        """Map cluster number (starting at 2) to byte offset in partition."""
        if not self.bpb:
            return -1
        # Data region starts after reserved sectors and all FATs
        fat_size_bytes = self.bpb.sectors_per_fat * self.bpb.bytes_per_sector
        data_start_offset = (
            self.bpb.reserved_sector_count * self.bpb.bytes_per_sector
            + self.bpb.num_fats * fat_size_bytes
        )
        cluster_size = self.bpb.sectors_per_cluster * self.bpb.bytes_per_sector
        return data_start_offset + (cluster - 2) * cluster_size

    def read_cluster_chain(self, start_cluster: int, max_bytes: int = 10 * 1024 * 1024) -> bytes:
        """Read data across cluster chain using the FAT table."""
        if not self.bpb or start_cluster < 2:
            return b""

        cluster_size = self.bpb.sectors_per_cluster * self.bpb.bytes_per_sector
        fat_offset = self.bpb.reserved_sector_count * self.bpb.bytes_per_sector

        data_chunks: list[bytes] = []
        current = start_cluster
        visited: set[int] = set()

        while current < 0x0FFFFFF8 and current >= 2 and len(data_chunks) * cluster_size < max_bytes:
            if current in visited:
                break  # Cycle detection
            visited.add(current)

            offset = self.cluster_to_offset(current)
            if offset + cluster_size > len(self.raw):
                # Truncated or out of bounds
                chunk = self.raw[offset:]
                data_chunks.append(chunk)
                break

            data_chunks.append(self.raw[offset : offset + cluster_size])

            # Read next cluster from FAT1
            fat_entry_offset = fat_offset + (current * 4)
            if fat_entry_offset + 4 > len(self.raw):
                break
            (next_cluster,) = struct.unpack("<I", self.raw[fat_entry_offset : fat_entry_offset + 4])
            current = next_cluster & 0x0FFFFFFF  # 28-bit cluster address in FAT32

        return b"".join(data_chunks)

    def scan_directory(self, dir_cluster: int = 2) -> list[Fat32FileEntry]:
        """Scan directory entries in a cluster and extract active and deleted files."""
        if not self.bpb:
            return []

        entries: list[Fat32FileEntry] = []
        dir_bytes = self.read_cluster_chain(dir_cluster, max_bytes=2 * 1024 * 1024)

        offset = 0
        while offset + 32 <= len(dir_bytes):
            entry_raw = dir_bytes[offset : offset + 32]
            offset += 32

            # 0x00 marks end of directory entries
            if entry_raw[0] == 0x00:
                break

            # Check if entry is deleted (0xE5)
            is_deleted = entry_raw[0] == 0xE5

            attr = entry_raw[11]
            # Skip LFN entries (attr == 0x0F)
            if attr == 0x0F:
                continue

            # Skip volume ID entries
            if attr & 0x08:
                continue

            # Parse name
            name_raw = bytearray(entry_raw[:11])
            if is_deleted:
                name_raw[0] = ord("_")  # Replace 0xE5 with underscore placeholder

            base = name_raw[:8].decode("latin-1", errors="replace").strip()
            ext = name_raw[8:11].decode("latin-1", errors="replace").strip()
            filename = f"{base}.{ext}" if ext else base

            is_dir = bool(attr & 0x10)
            high_cluster = struct.unpack("<H", entry_raw[20:22])[0]
            low_cluster = struct.unpack("<H", entry_raw[26:28])[0]
            file_size = struct.unpack("<I", entry_raw[28:32])[0]
            first_cluster = (high_cluster << 16) | low_cluster

            # Extract data if it is a regular file
            file_data = b""
            if not is_dir and first_cluster >= 2 and file_size > 0:
                full_chain = self.read_cluster_chain(first_cluster, max_bytes=file_size + 4096)
                file_data = full_chain[:file_size]

            entries.append(
                Fat32FileEntry(
                    name=filename,
                    is_deleted=is_deleted,
                    is_directory=is_dir,
                    size_bytes=file_size,
                    first_cluster=first_cluster,
                    data=file_data,
                    attributes={
                        "read_only": bool(attr & 0x01),
                        "hidden": bool(attr & 0x02),
                        "system": bool(attr & 0x04),
                        "directory": is_dir,
                        "archive": bool(attr & 0x20),
                    },
                )
            )

        return entries
