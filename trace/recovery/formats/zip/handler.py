"""ZIP and DOCX format handler: central directory parsing, archive security, and reconstruction."""

from __future__ import annotations

import io
import re
import struct
import zipfile
from typing import Any, Mapping, Sequence

from trace.recovery.formats.base import BaseFormatHandler
from trace.recovery.models import (
    FormatConfidence,
    FormatRecoveryResult,
    FragmentCandidate,
    RecoveryCategory,
    ValidationResult,
)

_PK_LOCAL = b"PK\x03\x04"
_PK_CENTRAL = b"PK\x01\x02"
_PK_EOCD = b"PK\x05\x06"

# Security limits
_MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024  # 50 MB
_MAX_COMPRESSION_RATIO = 100.0  # Max 100:1 ratio defense against zip bombs


class ZipFormatHandler(BaseFormatHandler):
    """High-assurance ZIP archive and DOCX document recovery and security validation engine."""

    format_name = "zip"
    mime_type = "application/zip"
    default_extension = ".zip"

    def identify(self, data: bytes, filename: str = "") -> FormatConfidence:
        if not data:
            return FormatConfidence(self.format_name, self.mime_type, 0.0, "none", is_supported=True)

        indicators: list[str] = []
        confidence = 0.0
        is_docx = False

        if data.startswith(_PK_LOCAL):
            indicators.append("magic:PK_local")
            confidence += 0.5
        elif _PK_LOCAL in data[:1024]:
            indicators.append("magic:PK_local_embedded")
            confidence += 0.3

        if _PK_EOCD in data[-1024:] or _PK_EOCD in data:
            indicators.append("marker:PK_eocd")
            confidence += 0.3

        if _PK_CENTRAL in data:
            indicators.append("marker:PK_central_dir")
            confidence += 0.2

        if b"word/document.xml" in data or b"[Content_Types].xml" in data:
            indicators.append("docx_structure:word_document")
            is_docx = True
            confidence += 0.2

        if filename.lower().endswith(".docx"):
            indicators.append("extension:.docx")
            is_docx = True
            confidence += 0.1
        elif filename.lower().endswith(".zip"):
            indicators.append("extension:.zip")
            confidence += 0.1

        confidence = min(1.0, max(0.0, confidence))
        fmt_name = "docx" if is_docx else "zip"
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document" if is_docx else "application/zip"

        return FormatConfidence(
            format_name=fmt_name,
            mime_type=mime,
            confidence=confidence,
            detected_by="magic_bytes" if "magic:PK_local" in str(indicators) else "tokens",
            structural_indicators=tuple(indicators),
            is_supported=True,
            details={"is_docx": is_docx, "has_eocd": "marker:PK_eocd" in indicators},
        )

    def carve_fragments(
        self, stream: bytes, block_size: int | None = None
    ) -> list[FragmentCandidate]:
        if not stream:
            return []

        if block_size is None:
            # Signature-aligned record carving
            split_points: list[int] = []
            for sig in (_PK_LOCAL, _PK_CENTRAL, _PK_EOCD):
                pos = 0
                while True:
                    idx = stream.find(sig, pos)
                    if idx == -1:
                        break
                    split_points.append(idx)
                    pos = idx + 1
            split_points = sorted(set(split_points))
            if not split_points or split_points[0] != 0:
                split_points.insert(0, 0)

            fragments: list[FragmentCandidate] = []
            for i in range(len(split_points)):
                start = split_points[i]
                end = split_points[i + 1] if i + 1 < len(split_points) else len(stream)
                chunk = stream[start:end]
                if not chunk:
                    continue

                tokens: list[str] = []
                role = "data"
                is_header = False
                is_footer = False

                if chunk.startswith(_PK_LOCAL):
                    tokens.append("PK_LOCAL")
                    role = "local_entry"
                    is_header = True
                elif chunk.startswith(_PK_CENTRAL):
                    tokens.append("PK_CENTRAL")
                    role = "central_dir"
                elif chunk.startswith(_PK_EOCD):
                    tokens.append("PK_EOCD")
                    role = "footer"
                    is_footer = True
                else:
                    if _PK_LOCAL in chunk:
                        tokens.append("PK_LOCAL")
                    if _PK_CENTRAL in chunk:
                        tokens.append("PK_CENTRAL")
                    if _PK_EOCD in chunk:
                        tokens.append("PK_EOCD")

                if b"[Content_Types].xml" in chunk:
                    tokens.append("CONTENT_TYPES")
                if b"word/document.xml" in chunk:
                    tokens.append("WORD_DOC")

                frag = FragmentCandidate(
                    fragment_id=f"ZIP-FRAG-{len(fragments):04d}",
                    source_offset=start,
                    size_bytes=len(chunk),
                    data=chunk,
                    format_hint="zip",
                    structural_role=role,
                    tokens=tuple(tokens),
                    is_header=is_header,
                    is_footer=is_footer,
                    known_sequence_index=len(fragments),
                )
                fragments.append(frag)
            return fragments

        bs = block_size
        fragments: list[FragmentCandidate] = []
        offset = 0
        idx = 0

        while offset < len(stream):
            chunk = stream[offset : offset + bs]
            tokens: list[str] = []
            role = "data"
            is_header = False
            is_footer = False

            if _PK_LOCAL in chunk:
                tokens.append("PK_LOCAL")
                role = "local_entry"
                if offset == 0 or chunk.startswith(_PK_LOCAL):
                    is_header = True
            if _PK_CENTRAL in chunk:
                tokens.append("PK_CENTRAL")
                role = "central_dir"
            if _PK_EOCD in chunk:
                tokens.append("PK_EOCD")
                role = "footer"
                is_footer = True
            if b"[Content_Types].xml" in chunk:
                tokens.append("CONTENT_TYPES")
            if b"word/document.xml" in chunk:
                tokens.append("WORD_DOC")

            frag = FragmentCandidate(
                fragment_id=f"ZIP-FRAG-{idx:04d}",
                source_offset=offset,
                size_bytes=len(chunk),
                data=chunk,
                format_hint="zip",
                structural_role=role,
                tokens=tuple(tokens),
                is_header=is_header,
                is_footer=is_footer,
                known_sequence_index=idx,
            )
            fragments.append(frag)
            offset += bs
            idx += 1

        return fragments

    def order_and_reconstruct(
        self, fragments: Sequence[FragmentCandidate]
    ) -> tuple[bytes, list[str], list[str], dict[str, Any]]:
        """Order ZIP fragments: Local entries -> Central Directory -> EOCD footer."""
        if not fragments:
            return b"", [], [], {"status": "empty"}

        local_frags: list[FragmentCandidate] = []
        central_frags: list[FragmentCandidate] = []
        footer_frags: list[FragmentCandidate] = []
        data_frags: list[FragmentCandidate] = []

        for f in fragments:
            if f.is_header or "PK_LOCAL" in f.tokens or f.structural_role == "local_entry":
                local_frags.append(f)
            elif f.is_footer or "PK_EOCD" in f.tokens or f.structural_role == "footer":
                footer_frags.append(f)
            elif "PK_CENTRAL" in f.tokens or f.structural_role == "central_dir":
                central_frags.append(f)
            else:
                data_frags.append(f)

        ordered = local_frags + data_frags + central_frags + footer_frags
        reconstructed_bytes = b"".join(f.data for f in ordered)
        placed_ids = [f.fragment_id for f in ordered]

        validation = self.validate(reconstructed_bytes)
        return (
            reconstructed_bytes,
            placed_ids,
            [],
            {
                "status": "structurally_valid" if validation.is_valid else "incomplete",
                "validation": {
                    "is_valid": validation.is_valid,
                    "errors": list(validation.errors),
                },
            },
        )

    def validate(self, data: bytes) -> ValidationResult:
        if not data:
            return ValidationResult(
                is_valid=False,
                format_name=self.format_name,
                integrity_score=0.0,
                checks_failed=("non_empty",),
                errors=("Byte stream is empty",),
            )

        checks_passed: list[str] = []
        checks_failed: list[str] = []
        errors: list[str] = []
        warnings: list[str] = []
        metadata: dict[str, Any] = {"size_bytes": len(data), "entries": []}

        # 1. Check local file header magic
        if data.startswith(_PK_LOCAL):
            checks_passed.append("magic_pk_local")
        else:
            checks_failed.append("magic_pk_local")
            errors.append("Missing PK\\x03\\x04 local file header magic")

        # 2. Check EOCD
        eocd_idx = data.rfind(_PK_EOCD)
        if eocd_idx != -1:
            checks_passed.append("marker_pk_eocd")
        else:
            checks_failed.append("marker_pk_eocd")
            errors.append("Missing PK\\x05\\x06 End of Central Directory record")

        # 3. Test integrity with zipfile module and enforce security controls
        is_zip_valid = False
        is_docx = False
        docx_text = ""

        if "magic_pk_local" in checks_passed and "marker_pk_eocd" in checks_passed:
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    # Test CRC checksums
                    bad_file = zf.testzip()
                    if bad_file is None:
                        checks_passed.append("crc32_checksums")
                    else:
                        checks_failed.append("crc32_checksums")
                        errors.append(f"CRC-32 checksum mismatch in archived file: {bad_file}")

                    entry_names = zf.namelist()
                    metadata["entries"] = entry_names[:20]

                    # Security Checks: Zip Slip (path traversal) & Zip Bomb
                    total_uncompressed = 0
                    for info in zf.infolist():
                        # Path traversal defense
                        name = info.filename
                        if ".." in name or name.startswith("/") or name.startswith("\\"):
                            warnings.append(f"Suspicious path traversal attempt detected in entry: {name}")

                        total_uncompressed += info.file_size
                        if info.compress_size > 0:
                            ratio = info.file_size / max(1, info.compress_size)
                            if ratio > _MAX_COMPRESSION_RATIO:
                                warnings.append(
                                    f"High compression ratio ({ratio:.1f}:1) for entry {name} (possible zip bomb)"
                                )

                    if total_uncompressed > _MAX_UNCOMPRESSED_BYTES:
                        warnings.append(
                            f"Total uncompressed size ({total_uncompressed} bytes) exceeds safety limit"
                        )

                    # Check for DOCX internal structure
                    if "[Content_Types].xml" in entry_names and (
                        "word/document.xml" in entry_names or "word/document2.xml" in entry_names
                    ):
                        is_docx = True
                        checks_passed.append("docx_structure")
                        try:
                            # Safe text preview extraction
                            doc_xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
                            # Strip tags to get raw text
                            clean_text = re.sub(r"<[^>]+>", " ", doc_xml)
                            docx_text = " ".join(clean_text.split())[:500]
                            metadata["docx_text_preview"] = docx_text
                        except Exception:
                            pass

                    is_zip_valid = True
                    checks_passed.append("zip_container")
            except Exception as e:
                checks_failed.append("zip_container")
                errors.append(f"Zip parsing failed: {e}")

        score = 0.0
        if "magic_pk_local" in checks_passed:
            score += 0.3
        if "marker_pk_eocd" in checks_passed:
            score += 0.3
        if "zip_container" in checks_passed:
            score += 0.25
        if "crc32_checksums" in checks_passed:
            score += 0.15

        actual_format = "docx" if is_docx else "zip"
        return ValidationResult(
            is_valid=is_zip_valid,
            format_name=actual_format,
            integrity_score=round(score, 2),
            checks_passed=tuple(checks_passed),
            checks_failed=tuple(checks_failed),
            errors=tuple(errors),
            warnings=tuple(warnings),
            metadata=metadata,
        )

    def repair_or_recover(
        self, data: bytes, filename: str = "", **kwargs: Any
    ) -> FormatRecoveryResult:
        """Deeply analyze and deterministically repair corrupted ZIP archive data."""
        if not data:
            val = self.validate(b"")
            return FormatRecoveryResult(
                format_name=self.format_name,
                is_recovered=False,
                is_openable=False,
                repaired_bytes=b"",
                authentic_bytes=b"",
                confidence_score=0.0,
                category=RecoveryCategory.UNRECOVERABLE,
                validation=val,
                operations_performed=[],
                unsupported_capabilities=["empty_input"],
            )

        operations: list[str] = []
        authentic_bytes = data
        repaired = bytearray(data)

        # 1. Preamble stripping: find first PK\x03\x04
        pk_idx = repaired.find(_PK_LOCAL)
        if pk_idx > 0:
            repaired = repaired[pk_idx:]
            operations.append(f"stripped_preamble_garbage_{pk_idx}_bytes")

        # 2. Check if Central Directory & EOCD exist
        eocd_idx = repaired.rfind(_PK_EOCD)
        needs_cd_rebuild = (eocd_idx == -1)

        # Test if standard zipfile can open it
        try:
            with zipfile.ZipFile(io.BytesIO(repaired)) as zf:
                if len(zf.namelist()) == 0:
                    needs_cd_rebuild = True
        except Exception:
            needs_cd_rebuild = True

        extracted_items: list[dict[str, Any]] = []
        salvaged_text_parts: list[str] = []

        if needs_cd_rebuild:
            # Reconstruct Central Directory from Local File Headers (PK\x03\x04)
            cd_entries = bytearray()
            entry_count = 0
            offset = 0

            while offset < len(repaired):
                loc = repaired.find(_PK_LOCAL, offset)
                if loc == -1 or loc + 30 > len(repaired):
                    break

                try:
                    (
                        sig,
                        ver,
                        flags,
                        method,
                        mod_time,
                        mod_date,
                        crc32_val,
                        comp_size,
                        uncomp_size,
                        fname_len,
                        extra_len,
                    ) = struct.unpack("<4sHHHHHIIIHH", repaired[loc : loc + 30])
                except struct.error:
                    break

                name_start = loc + 30
                name_end = name_start + fname_len
                if name_end > len(repaired):
                    break
                fname = repaired[name_start:name_end].decode("utf-8", errors="replace")

                data_start = name_end + extra_len
                next_loc = repaired.find(_PK_LOCAL, data_start)
                if comp_size == 0 and next_loc != -1:
                    inferred_comp = next_loc - data_start
                elif comp_size == 0:
                    inferred_comp = max(0, len(repaired) - data_start)
                else:
                    inferred_comp = comp_size

                # Build Central Directory Record (PK\x01\x02)
                cd_header = struct.pack(
                    "<4sHHHHHHIIIHHHHHII",
                    _PK_CENTRAL,
                    ver,
                    ver,
                    flags,
                    method,
                    mod_time,
                    mod_date,
                    crc32_val,
                    inferred_comp,
                    uncomp_size or inferred_comp,
                    fname_len,
                    0,  # extra field length
                    0,  # file comment length
                    0,  # disk number start
                    0,  # internal file attributes
                    0,  # external file attributes
                    loc,  # relative offset of local header
                )
                cd_entries.extend(cd_header)
                cd_entries.extend(repaired[name_start:name_end])
                entry_count += 1

                offset = data_start + inferred_comp

            if entry_count > 0:
                cd_offset = len(repaired)
                cd_size = len(cd_entries)
                eocd = struct.pack(
                    "<4sHHHHIIH",
                    _PK_EOCD,
                    0,
                    0,
                    entry_count,
                    entry_count,
                    cd_size,
                    cd_offset,
                    0,
                )
                repaired.extend(cd_entries)
                repaired.extend(eocd)
                operations.append(f"reconstructed_central_directory_with_{entry_count}_entries")

        repaired_bytes = bytes(repaired)
        val = self.validate(repaired_bytes)

        # Test extraction of entries
        is_openable = False
        try:
            with zipfile.ZipFile(io.BytesIO(repaired_bytes)) as zf:
                is_openable = True
                for info in zf.infolist():
                    if ".." in info.filename or info.filename.startswith(("/", "\\")):
                        operations.append(f"quarantined_zip_slip_entry_{info.filename}")
                        extracted_items.append({
                            "name": info.filename,
                            "size_bytes": info.file_size,
                            "compressed_size": info.compress_size,
                            "status": "QUARANTINED",
                        })
                        continue

                    status = "DAMAGED"
                    try:
                        content = zf.read(info.filename)
                        status = "INTACT"
                        if info.filename.lower().endswith((".txt", ".json", ".csv", ".xml", ".log", ".md")):
                            snippet = content.decode("utf-8", errors="replace")[:1000]
                            salvaged_text_parts.append(f"--- {info.filename} ---\n{snippet}")
                    except Exception:
                        pass
                    extracted_items.append({
                        "name": info.filename,
                        "size_bytes": info.file_size,
                        "compressed_size": info.compress_size,
                        "status": status,
                    })
        except Exception:
            is_openable = False

        synth_count = max(0, len(repaired_bytes) - len(authentic_bytes))
        cat = (
            RecoveryCategory.RECOVERED
            if (is_openable and all(e["status"] == "INTACT" for e in extracted_items))
            else (RecoveryCategory.PARTIAL if is_openable else RecoveryCategory.UNRECOVERABLE)
        )

        return FormatRecoveryResult(
            format_name=self.format_name,
            is_recovered=is_openable,
            is_openable=is_openable,
            repaired_bytes=repaired_bytes,
            authentic_bytes=authentic_bytes,
            authentic_bytes_count=len(authentic_bytes),
            synthesized_bytes_count=synth_count,
            confidence_score=max(val.integrity_score * 100.0, 90.0 if is_openable else 15.0),
            category=cat,
            validation=val,
            operations_performed=operations,
            unsupported_capabilities=[
                "multidisk_spanned_zip_volume_recovery",
                "aes256_strong_encryption_key_recovery",
            ],
            diagnostics={
                "entries_count": len(extracted_items),
                "intact_entries": sum(1 for e in extracted_items if e["status"] == "INTACT"),
                "damaged_entries": sum(1 for e in extracted_items if e["status"] == "DAMAGED"),
            },
            salvaged_text="\n\n".join(salvaged_text_parts),
            extracted_items=extracted_items,
            preview_type="archive" if is_openable else "none",
        )

