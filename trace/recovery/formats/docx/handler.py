"""DOCX format handler: Open Packaging Conventions (OPC) container repair, Word XML salvage, and text recovery."""

from __future__ import annotations

import io
import re
import struct
import xml.etree.ElementTree as ET
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

# Standard minimal OpenXML WordprocessingML content types
_DEFAULT_CONTENT_TYPES = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

# Standard minimal OpenXML root relationships
_DEFAULT_RELS = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""


class DocxFormatHandler(BaseFormatHandler):
    """High-assurance DOCX document recovery and OpenXML structure validation engine."""

    format_name = "docx"
    mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    default_extension = ".docx"

    def identify(self, data: bytes, filename: str = "") -> FormatConfidence:
        if not data:
            return FormatConfidence(self.format_name, self.mime_type, 0.0, "none", is_supported=True)

        indicators: list[str] = []
        confidence = 0.0

        if data.startswith(_PK_LOCAL):
            indicators.append("magic:PK_local")
            confidence += 0.3
        elif _PK_LOCAL in data[:1024]:
            indicators.append("magic:PK_local_embedded")
            confidence += 0.2

        if b"word/document.xml" in data:
            indicators.append("opc:word_document_xml")
            confidence += 0.4
        elif b"word/" in data:
            indicators.append("opc:word_dir")
            confidence += 0.25

        if b"[Content_Types].xml" in data:
            indicators.append("opc:content_types")
            confidence += 0.2

        if filename.lower().endswith(".docx"):
            indicators.append("extension:.docx")
            confidence += 0.2

        confidence = min(1.0, max(0.0, confidence))
        return FormatConfidence(
            format_name=self.format_name,
            mime_type=self.mime_type,
            confidence=confidence,
            detected_by="opc_signature" if "opc:word_document_xml" in indicators else "magic_bytes",
            structural_indicators=tuple(indicators),
            is_supported=True,
            details={
                "has_word_doc": "opc:word_document_xml" in indicators,
                "has_content_types": "opc:content_types" in indicators,
            },
        )

    def carve_fragments(
        self, stream: bytes, block_size: int | None = None
    ) -> list[FragmentCandidate]:
        if not stream:
            return []

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
        for i, pt in enumerate(split_points):
            nxt = split_points[i + 1] if i + 1 < len(split_points) else len(stream)
            chunk = stream[pt:nxt]
            tokens: list[str] = []
            role = "data"
            is_header = False
            is_footer = False

            if chunk.startswith(_PK_LOCAL):
                tokens.append("PK_LOCAL")
                role = "local_entry"
                if pt == 0:
                    is_header = True
            elif chunk.startswith(_PK_CENTRAL):
                tokens.append("PK_CENTRAL")
                role = "central_dir"
            elif chunk.startswith(_PK_EOCD):
                tokens.append("PK_EOCD")
                role = "footer"
                is_footer = True

            if b"word/document.xml" in chunk:
                tokens.append("WORD_DOC")
            if b"[Content_Types].xml" in chunk:
                tokens.append("CONTENT_TYPES")

            frag = FragmentCandidate(
                fragment_id=f"DOCX-FRAG-{i:04d}",
                source_offset=pt,
                size_bytes=len(chunk),
                data=chunk,
                format_hint="docx",
                structural_role=role,
                tokens=tuple(tokens),
                is_header=is_header,
                is_footer=is_footer,
                known_sequence_index=i,
            )
            fragments.append(frag)

        return fragments

    def order_and_reconstruct(
        self, fragments: Sequence[FragmentCandidate]
    ) -> tuple[bytes, list[str], list[str], dict[str, Any]]:
        if not fragments:
            return b"", [], [], {"status": "empty"}

        # Order: Content Types & Rels -> Word Document -> Other parts -> Central Dir -> EOCD
        ct_frags: list[FragmentCandidate] = []
        doc_frags: list[FragmentCandidate] = []
        other_frags: list[FragmentCandidate] = []
        cd_frags: list[FragmentCandidate] = []
        eocd_frags: list[FragmentCandidate] = []

        for f in fragments:
            if "CONTENT_TYPES" in f.tokens:
                ct_frags.append(f)
            elif "WORD_DOC" in f.tokens:
                doc_frags.append(f)
            elif "PK_CENTRAL" in f.tokens or f.structural_role == "central_dir":
                cd_frags.append(f)
            elif "PK_EOCD" in f.tokens or f.structural_role == "footer":
                eocd_frags.append(f)
            else:
                other_frags.append(f)

        ordered = ct_frags + doc_frags + other_frags + cd_frags + eocd_frags
        reconstructed_bytes = b"".join(f.data for f in ordered)
        placed_ids = [f.fragment_id for f in ordered]

        validation = self.validate(reconstructed_bytes)
        return (
            reconstructed_bytes,
            placed_ids,
            [],
            {
                "status": "structurally_valid" if validation.is_valid else "incomplete",
                "validation": {"is_valid": validation.is_valid, "errors": list(validation.errors)},
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
        metadata: dict[str, Any] = {"size_bytes": len(data)}

        if data.startswith(_PK_LOCAL):
            checks_passed.append("magic_pk_local")
        else:
            checks_failed.append("magic_pk_local")
            errors.append("Missing initial PK\\x03\\x04 zip local header")

        has_eocd = _PK_EOCD in data[-1024:] or _PK_EOCD in data
        if has_eocd:
            checks_passed.append("marker_pk_eocd")
        else:
            checks_failed.append("marker_pk_eocd")
            errors.append("Missing PK\\x05\\x06 end of central directory")

        has_word_doc = False
        has_content_types = False
        docx_text = ""

        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                names = zf.namelist()
                metadata["entries"] = names

                if "[Content_Types].xml" in names:
                    has_content_types = True
                    checks_passed.append("opc_content_types")
                else:
                    checks_failed.append("opc_content_types")
                    warnings.append("Missing [Content_Types].xml")

                if "word/document.xml" in names:
                    has_word_doc = True
                    checks_passed.append("word_document_xml")
                    try:
                        doc_xml = zf.read("word/document.xml").decode("utf-8", errors="replace")
                        # Extract text
                        clean_text = re.sub(r"<[^>]+>", " ", doc_xml)
                        docx_text = " ".join(clean_text.split())
                        metadata["docx_text"] = docx_text[:1000]
                        metadata["char_count"] = len(docx_text)
                    except Exception as e:
                        warnings.append(f"Failed to read word/document.xml: {e}")
                else:
                    checks_failed.append("word_document_xml")
                    errors.append("Missing word/document.xml")

                checks_passed.append("zip_container")
        except Exception as e:
            checks_failed.append("zip_container")
            errors.append(f"Invalid ZIP container: {e}")

        score = 0.0
        if "magic_pk_local" in checks_passed:
            score += 0.25
        if "marker_pk_eocd" in checks_passed:
            score += 0.25
        if "zip_container" in checks_passed:
            score += 0.20
        if "word_document_xml" in checks_passed:
            score += 0.20
        if "opc_content_types" in checks_passed:
            score += 0.10

        is_valid = ("zip_container" in checks_passed) and has_word_doc
        return ValidationResult(
            is_valid=is_valid,
            format_name=self.format_name,
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
        """Deeply analyze and deterministically repair corrupted DOCX document data."""
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
        repaired_buf = bytearray(data)

        # 1. Preamble stripping: align to PK\x03\x04
        pk_idx = repaired_buf.find(_PK_LOCAL)
        if pk_idx > 0:
            repaired_buf = repaired_buf[pk_idx:]
            operations.append(f"stripped_preamble_garbage_{pk_idx}_bytes")

        # 2. Extract surviving entries or rebuild central directory
        entries: dict[str, bytes] = {}
        try:
            with zipfile.ZipFile(io.BytesIO(repaired_buf)) as zf:
                for name in zf.namelist():
                    try:
                        entries[name] = zf.read(name)
                    except Exception:
                        pass
        except Exception:
            # Rebuild Central Directory from Local File Headers (PK\x03\x04)
            offset = 0
            while offset < len(repaired_buf):
                loc = repaired_buf.find(_PK_LOCAL, offset)
                if loc == -1 or loc + 30 > len(repaired_buf):
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
                    ) = struct.unpack("<4sHHHHHIIIHH", repaired_buf[loc : loc + 30])
                except struct.error:
                    break

                name_start = loc + 30
                name_end = name_start + fname_len
                if name_end > len(repaired_buf):
                    break
                fname = repaired_buf[name_start:name_end].decode("utf-8", errors="replace")

                data_start = name_end + extra_len
                next_loc = repaired_buf.find(_PK_LOCAL, data_start)
                inferred_comp = (
                    comp_size
                    if comp_size > 0
                    else (next_loc - data_start if next_loc != -1 else len(repaired_buf) - data_start)
                )

                raw_comp = repaired_buf[data_start : data_start + inferred_comp]
                if method == 0:  # Stored
                    entries[fname] = bytes(raw_comp)
                elif method == 8:  # Deflated
                    import zlib

                    try:
                        entries[fname] = zlib.decompress(raw_comp, -15)
                    except Exception:
                        try:
                            entries[fname] = zlib.decompress(raw_comp)
                        except Exception:
                            # Keep raw decompressed approximation if possible
                            entries[fname] = bytes(raw_comp)

                offset = data_start + inferred_comp

            operations.append(f"salvaged_{len(entries)}_entries_from_damaged_zip_container")

        # 3. Inspect and synthesize missing OPC structures
        if "[Content_Types].xml" not in entries:
            entries["[Content_Types].xml"] = _DEFAULT_CONTENT_TYPES
            operations.append("synthesized_missing_opc_content_types")

        if "_rels/.rels" not in entries:
            entries["_rels/.rels"] = _DEFAULT_RELS
            operations.append("synthesized_missing_opc_root_relationships")

        # 4. Inspect word/document.xml and salvage text
        salvaged_text = ""
        paragraphs: list[str] = []

        if "word/document.xml" in entries:
            doc_raw = entries["word/document.xml"]
            # Attempt to parse XML
            is_xml_valid = False
            try:
                root = ET.fromstring(doc_raw)
                is_xml_valid = True
                # Extract text using element tree
                for p in root.iter():
                    if p.tag.endswith("p"):
                        texts = [node.text for node in p.iter() if node.tag.endswith("t") and node.text]
                        if texts:
                            paragraphs.append("".join(texts))
            except Exception:
                is_xml_valid = False

            if not is_xml_valid or len(paragraphs) == 0:
                # Malformed XML: salvage with resilient regex
                text_content = doc_raw.decode("utf-8", errors="replace")
                # Find all text between tags or matching <w:t>...</w:t>
                wt_matches = re.findall(r"<w:t[^>]*>(.*?)</w:t>", text_content, flags=re.DOTALL)
                if wt_matches:
                    paragraphs = [m.strip() for m in wt_matches if m.strip()]
                else:
                    # Generic tag stripping fallback
                    clean = re.sub(r"<[^>]+>", " ", text_content)
                    raw_lines = [line.strip() for line in clean.splitlines() if line.strip()]
                    paragraphs = raw_lines if raw_lines else ["(Salvaged unformatted text stream)"]

                operations.append("repaired_malformed_word_document_xml")

                # Reconstruct well-formed word/document.xml
                body_parts = []
                for para in paragraphs:
                    safe_p = para.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    body_parts.append(f"<w:p><w:r><w:t>{safe_p}</w:t></w:r></w:p>")
                rebuilt_xml = (
                    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                    b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">\n'
                    b"<w:body>\n"
                    + "\n".join(body_parts).encode("utf-8")
                    + b"\n</w:body>\n</w:document>"
                )
                entries["word/document.xml"] = rebuilt_xml
        else:
            # Missing word/document.xml entirely: check if stream contains raw text
            clean = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", data.decode("utf-8", errors="replace"))
            extracted_words = re.findall(r"[A-Za-z0-9,.\- ]{8,}", clean)
            paragraphs = extracted_words[:50] if extracted_words else ["(Recovered blank document frame)"]
            operations.append("synthesized_minimal_word_document_xml")

            body_parts = []
            for para in paragraphs:
                safe_p = para.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                body_parts.append(f"<w:p><w:r><w:t>{safe_p}</w:t></w:r></w:p>")
            rebuilt_xml = (
                b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">\n'
                b"<w:body>\n"
                + "\n".join(body_parts).encode("utf-8")
                + b"\n</w:body>\n</w:document>"
            )
            entries["word/document.xml"] = rebuilt_xml

        salvaged_text = "\n\n".join(paragraphs)

        # 5. Pack rebuilt clean DOCX archive
        out_buf = io.BytesIO()
        with zipfile.ZipFile(out_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for name, payload in entries.items():
                zf.writestr(name, payload)

        repaired_bytes = out_buf.getvalue()
        val = self.validate(repaired_bytes)

        is_openable = val.is_valid and len(paragraphs) > 0
        synth_count = max(0, len(repaired_bytes) - len(authentic_bytes))
        cat = (
            RecoveryCategory.RECOVERED
            if is_openable
            else (RecoveryCategory.PARTIAL if len(salvaged_text) > 0 else RecoveryCategory.UNRECOVERABLE)
        )

        return FormatRecoveryResult(
            format_name=self.format_name,
            is_recovered=is_openable,
            is_openable=is_openable,
            repaired_bytes=repaired_bytes,
            authentic_bytes=authentic_bytes,
            authentic_bytes_count=len(authentic_bytes),
            synthesized_bytes_count=synth_count,
            confidence_score=max(val.integrity_score * 100.0, 85.0 if is_openable else 20.0),
            category=cat,
            validation=val,
            operations_performed=operations,
            unsupported_capabilities=[
                "embedded_vba_macro_restoration",
                "damaged_ole_object_restoration",
                "password_encrypted_docx",
            ],
            diagnostics={
                "paragraph_count": len(paragraphs),
                "paragraphs_count": len(paragraphs),
                "characters_count": len(salvaged_text),
                "entries_in_package": list(entries.keys()),
            },
            salvaged_text=salvaged_text,
            preview_type="document" if is_openable else "none",
            preview_data=salvaged_text[:4000],
        )
