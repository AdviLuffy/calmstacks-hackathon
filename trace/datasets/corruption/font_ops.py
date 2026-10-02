"""Font corruption operators for PDF font descriptors and CMaps."""

from __future__ import annotations

import re
import uuid
from typing import Optional, Tuple

from trace.datasets.schemas.corruption import (
    CorruptionOperation,
    CorruptionType,
    Recoverability,
)


def remove_font_object(
    data: bytes,
) -> Tuple[bytes, Optional[CorruptionOperation]]:
    """Remove a `/Type /Font` object."""
    m = re.search(rb"(?:^|[\r\n\s])(\d+\s+0\s+obj[\s\S]*?/Type\s*/Font[\s\S]*?endobj)", data)
    if not m:
        return data, None

    start = m.start(1)
    end = m.end(1)
    orig_len = end - start
    corrupted = data[:start] + data[end:]

    op = CorruptionOperation(
        operation_id=str(uuid.uuid4())[:8],
        type=CorruptionType.REMOVE_FONT_OBJECT,
        offset_start=start,
        offset_end=end,
        original_length=orig_len,
        corrupted_length=0,
        severity=0.60,
        recoverability=Recoverability.PARTIAL,
        reversible=False,
        details={"removed_font_bytes": orig_len},
    )
    return corrupted, op


def damage_font_references(
    data: bytes,
) -> Tuple[bytes, Optional[CorruptionOperation]]:
    """Mutate `/BaseFont /Name` into garbage font name."""
    m = re.search(rb"/BaseFont\s*/([A-Za-z0-9_-]+)", data)
    if not m:
        return data, None

    start = m.start(1)
    end = m.end(1)
    orig_name = m.group(1)
    fake_name = b"DamagedFontMissing"
    corrupted = data[:start] + fake_name + data[end:]

    op = CorruptionOperation(
        operation_id=str(uuid.uuid4())[:8],
        type=CorruptionType.DAMAGE_FONT_REFERENCES,
        offset_start=start,
        offset_end=end,
        original_length=len(orig_name),
        corrupted_length=len(fake_name),
        severity=0.45,
        recoverability=Recoverability.RECOVERABLE_FROM_SURVIVING_EVIDENCE,
        reversible=True,
        details={"original_font": orig_name.decode("ascii", errors="ignore"), "corrupted_font": "DamagedFontMissing"},
    )
    return corrupted, op


def remove_tounicode(
    data: bytes,
) -> Tuple[bytes, Optional[CorruptionOperation]]:
    """Remove `/ToUnicode` dictionary reference."""
    m = re.search(rb"/ToUnicode\s+\d+\s+0\s+R", data)
    if not m:
        return data, None

    start = m.start(0)
    end = m.end(0)
    corrupted = data[:start] + data[end:]

    op = CorruptionOperation(
        operation_id=str(uuid.uuid4())[:8],
        type=CorruptionType.REMOVE_TOUNICODE,
        offset_start=start,
        offset_end=end,
        original_length=end - start,
        corrupted_length=0,
        severity=0.50,
        recoverability=Recoverability.PARTIAL,
        reversible=False,
        details={"removed_tounicode_reference": True},
    )
    return corrupted, op
