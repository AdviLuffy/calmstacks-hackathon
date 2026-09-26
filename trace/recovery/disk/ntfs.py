"""NTFS file system parser: VBR, MFT record parsing, and deleted file recovery."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Any, Sequence


@dataclass
class NtfsFileEntry:
    """A file record parsed from an NTFS MFT entry."""

    record_number: int
    name: str
    is_deleted: bool
    is_directory: bool
    size_bytes: int
    resident: bool
    data: bytes = field(default=b"", repr=False)
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class NtfsBootSector:
    """Decoded NTFS Volume Boot Record."""

    oem_id: str
    bytes_per_sector: int
    sectors_per_cluster: int
    total_sectors: int
    mft_cluster_lcn: int
    mft_record_size_bytes: int


class NtfsParser:
    """Read-only parser for NTFS Volume Boot Record and Master File Table (MFT)."""

    def __init__(self, partition_bytes: bytes) -> None:
        self.raw = partition_bytes
        self.vbr = self._parse_vbr()

    def _parse_vbr(self) -> NtfsBootSector | None:
        if len(self.raw) < 512:
            return None

        oem_id = self.raw[3:11].decode("latin-1", errors="replace")
        if not oem_id.startswith("NTFS"):
            return None

        try:
            bytes_per_sec, sec_per_clus = struct.unpack("<HB", self.raw[11:14])
            total_sectors = struct.unpack("<Q", self.raw[40:48])[0]
            mft_cluster = struct.unpack("<Q", self.raw[48:56])[0]
            clusters_per_mft_record = struct.unpack("<b", self.raw[64:65])[0]

            # If clusters_per_mft_record < 0, size is 2^|val|
            if clusters_per_mft_record < 0:
                record_size = 1 << abs(clusters_per_mft_record)
            else:
                record_size = clusters_per_mft_record * sec_per_clus * bytes_per_sec

            return NtfsBootSector(
                oem_id=oem_id,
                bytes_per_sector=bytes_per_sec,
                sectors_per_cluster=sec_per_clus,
                total_sectors=total_sectors,
                mft_cluster_lcn=mft_cluster,
                mft_record_size_bytes=record_size,
            )
        except Exception:
            return None

    def scan_mft_records(self, max_records: int = 100) -> list[NtfsFileEntry]:
        """Scan MFT records from the MFT table offset."""
        if not self.vbr:
            return []

        cluster_size = self.vbr.bytes_per_sector * self.vbr.sectors_per_cluster
        mft_offset = self.vbr.mft_cluster_lcn * cluster_size
        rec_size = self.vbr.mft_record_size_bytes or 1024

        entries: list[NtfsFileEntry] = []
        offset = mft_offset

        record_idx = 0
        while offset + rec_size <= len(self.raw) and record_idx < max_records:
            record_raw = self.raw[offset : offset + rec_size]
            offset += rec_size
            record_idx += 1

            # Check 'FILE' signature
            if not record_raw.startswith(b"FILE"):
                continue

            try:
                usa_offset, usa_count, lsn, seq_num, link_count, attr_offset, flags = (
                    struct.unpack("<HHQHHHH", record_raw[4:24])
                )
                is_in_use = bool(flags & 0x0001)
                is_dir = bool(flags & 0x0002)
                is_deleted = not is_in_use

                # Parse attributes
                file_name = f"MFT_Record_{record_idx}"
                file_size = 0
                resident_data = b""
                is_resident = True

                curr_attr = attr_offset
                while curr_attr + 8 <= len(record_raw):
                    attr_type, attr_len = struct.unpack("<II", record_raw[curr_attr : curr_attr + 8])
                    if attr_type == 0xFFFFFFFF or attr_len == 0:
                        break

                    non_resident_flag = record_raw[curr_attr + 8]
                    if attr_type == 0x30:  # $FILE_NAME
                        content_offset = (
                            curr_attr + struct.unpack("<H", record_raw[curr_attr + 20 : curr_attr + 22])[0]
                        )
                        name_len = record_raw[content_offset + 64]
                        name_bytes = record_raw[content_offset + 66 : content_offset + 66 + (name_len * 2)]
                        decoded_name = name_bytes.decode("utf-16le", errors="ignore")
                        if decoded_name and not file_name.startswith("$"):
                            file_name = decoded_name

                    elif attr_type == 0x80:  # $DATA
                        if non_resident_flag == 0:  # Resident
                            val_len = struct.unpack("<I", record_raw[curr_attr + 16 : curr_attr + 20])[0]
                            val_off = struct.unpack("<H", record_raw[curr_attr + 20 : curr_attr + 22])[0]
                            file_size = val_len
                            resident_data = record_raw[curr_attr + val_off : curr_attr + val_off + val_len]
                        else:  # Non-resident
                            is_resident = False
                            data_size = struct.unpack("<Q", record_raw[curr_attr + 48 : curr_attr + 56])[0]
                            file_size = data_size

                    curr_attr += attr_len

                # Skip system files unless deleted
                if not file_name.startswith("$") or is_deleted:
                    entries.append(
                        NtfsFileEntry(
                            record_number=record_idx,
                            name=file_name,
                            is_deleted=is_deleted,
                            is_directory=is_dir,
                            size_bytes=file_size,
                            resident=is_resident,
                            data=resident_data,
                            attributes={"flags": hex(flags)},
                        )
                    )
            except Exception:
                continue

        return entries
