"""PDF structural corruption operators."""

from __future__ import annotations

import random
import re
import uuid
from typing import Optional, Tuple

from trace.datasets.schemas.corruption import (
    CorruptionOperation,
    CorruptionType,
    Recoverability,
)


def damage_xref(
    data: bytes,
    rng: random.Random,
) -> Tuple[bytes, Optional[CorruptionOperation]]:
    """Damage xref table header or tokens."""
    pos = data.rfind(b"xref")
    if pos == -1:
        return data, None

    # Replace 'xref' with 'x_ef' or garbage
    corrupted = data[:pos] + b"x_ef" + data[pos + 4:]
    op = CorruptionOperation(
        operation_id=str(uuid.uuid4())[:8],
        type=CorruptionType.DAMAGE_XREF,
        offset_start=pos,
        offset_end=pos + 4,
        original_length=4,
        corrupted_length=4,
        severity=0.60,
        recoverability=Recoverability.RECOVERABLE_FROM_SURVIVING_EVIDENCE,
        reversible=True,
        details={"original_token": "xref", "corrupted_token": "x_ef"},
    )
    return corrupted, op


def damage_trailer(
    data: bytes,
    rng: random.Random,
) -> Tuple[bytes, Optional[CorruptionOperation]]:
    """Damage trailer keyword or startxref pointer."""
    pos = data.rfind(b"startxref")
    if pos != -1:
        # Damage startxref token
        corrupted = data[:pos] + b"start_ref" + data[pos + 9:]
        op = CorruptionOperation(
            operation_id=str(uuid.uuid4())[:8],
            type=CorruptionType.DAMAGE_TRAILER,
            offset_start=pos,
            offset_end=pos + 9,
            original_length=9,
            corrupted_length=9,
            severity=0.70,
            recoverability=Recoverability.RECOVERABLE_FROM_SURVIVING_EVIDENCE,
            reversible=True,
            details={"original_token": "startxref", "corrupted_token": "start_ref"},
        )
        return corrupted, op

    trailer_pos = data.rfind(b"trailer")
    if trailer_pos != -1:
        corrupted = data[:trailer_pos] + b"tra_ler" + data[trailer_pos + 7:]
        op = CorruptionOperation(
            operation_id=str(uuid.uuid4())[:8],
            type=CorruptionType.DAMAGE_TRAILER,
            offset_start=trailer_pos,
            offset_end=trailer_pos + 7,
            original_length=7,
            corrupted_length=7,
            severity=0.70,
            recoverability=Recoverability.RECOVERABLE_FROM_SURVIVING_EVIDENCE,
            reversible=True,
            details={"original_token": "trailer", "corrupted_token": "tra_ler"},
        )
        return corrupted, op

    return data, None


def damage_object_offsets(
    data: bytes,
    rng: random.Random,
) -> Tuple[bytes, Optional[CorruptionOperation]]:
    """Mutate 10-digit byte offset entries inside xref table."""
    xref_pos = data.rfind(b"xref")
    if xref_pos == -1:
        return data, None

    # Match 10-digit offset lines: "0000000000 65535 f "
    m = re.search(rb"(\d{10})\s+(\d{5})\s+[fn]", data[xref_pos:])
    if not m:
        return data, None

    start = xref_pos + m.start(1)
    end = xref_pos + m.end(1)
    fake_offset = b"9999999999"
    corrupted = data[:start] + fake_offset + data[end:]

    op = CorruptionOperation(
        operation_id=str(uuid.uuid4())[:8],
        type=CorruptionType.DAMAGE_OFFSETS,
        offset_start=start,
        offset_end=end,
        original_length=10,
        corrupted_length=10,
        severity=0.55,
        recoverability=Recoverability.RECOVERABLE_FROM_SURVIVING_EVIDENCE,
        reversible=True,
        details={"original_offset": m.group(1).decode("ascii"), "corrupted_offset": "9999999999"},
    )
    return corrupted, op


def remove_indirect_object(
    data: bytes,
    object_number: int,
) -> Tuple[bytes, Optional[CorruptionOperation]]:
    """Completely remove an indirect object `N 0 obj ... endobj`."""
    pattern = re.compile(rf"(?:^|[\r\n\s])({object_number}\s+0\s+obj[\s\S]*?endobj)", re.MULTILINE)
    m = pattern.search(data.decode("latin-1", errors="ignore"))
    if not m:
        return data, None

    start = m.start(1)
    end = m.end(1)
    orig_len = end - start

    corrupted = data[:start] + data[end:]
    op = CorruptionOperation(
        operation_id=str(uuid.uuid4())[:8],
        type=CorruptionType.REMOVE_OBJECT,
        object_id=f"{object_number} 0 obj",
        offset_start=start,
        offset_end=end,
        original_length=orig_len,
        corrupted_length=0,
        severity=0.65,
        recoverability=Recoverability.UNRECOVERABLE_WITHOUT_EXTERNAL_REDUNDANCY,
        reversible=False,
        details={"object_number": object_number},
    )
    return corrupted, op


def truncate_indirect_object(
    data: bytes,
    object_number: int,
    keep_ratio: float = 0.5,
) -> Tuple[bytes, Optional[CorruptionOperation]]:
    """Partially truncate an indirect object body while preserving header."""
    pattern = re.compile(rf"(?:^|[\r\n\s])({object_number}\s+0\s+obj[\s\S]*?endobj)", re.MULTILINE)
    m = pattern.search(data.decode("latin-1", errors="ignore"))
    if not m:
        return data, None

    start = m.start(1)
    end = m.end(1)
    orig_len = end - start
    keep_len = max(10, int(orig_len * keep_ratio))

    truncated_chunk = data[start : start + keep_len]
    corrupted = data[:start] + truncated_chunk + data[end:]

    op = CorruptionOperation(
        operation_id=str(uuid.uuid4())[:8],
        type=CorruptionType.TRUNCATE_OBJECT,
        object_id=f"{object_number} 0 obj",
        offset_start=start + keep_len,
        offset_end=end,
        original_length=orig_len - keep_len,
        corrupted_length=0,
        severity=0.50,
        recoverability=Recoverability.PARTIAL,
        reversible=False,
        details={"object_number": object_number, "retained_length": keep_len},
    )
    return corrupted, op


def damage_object_boundaries(
    data: bytes,
    object_number: int,
) -> Tuple[bytes, Optional[CorruptionOperation]]:
    """Corrupt 'obj' or 'endobj' boundary keywords."""
    pattern = re.compile(rf"({object_number}\s+0\s+)obj", re.MULTILINE)
    m = pattern.search(data.decode("latin-1", errors="ignore"))
    if not m:
        return data, None

    obj_pos = m.end(1)
    corrupted = data[:obj_pos] + b"obX" + data[obj_pos + 3:]

    op = CorruptionOperation(
        operation_id=str(uuid.uuid4())[:8],
        type=CorruptionType.DAMAGE_OBJECT_BOUNDARIES,
        object_id=f"{object_number} 0 obj",
        offset_start=obj_pos,
        offset_end=obj_pos + 3,
        original_length=3,
        corrupted_length=3,
        severity=0.40,
        recoverability=Recoverability.RECOVERABLE_FROM_SURVIVING_EVIDENCE,
        reversible=True,
        details={"object_number": object_number, "damaged_keyword": "obj -> obX"},
    )
    return corrupted, op


def damage_length(
    data: bytes,
    object_number: Optional[int] = None,
) -> Tuple[bytes, Optional[CorruptionOperation]]:
    """Damage `/Length N` dictionary entry."""
    m = re.search(rb"/Length\s+(\d+)", data)
    if not m:
        return data, None

    start = m.start(1)
    end = m.end(1)
    orig_val = m.group(1)
    fake_val = b"99999"

    corrupted = data[:start] + fake_val + data[end:]
    op = CorruptionOperation(
        operation_id=str(uuid.uuid4())[:8],
        type=CorruptionType.DAMAGE_LENGTH,
        object_id=f"{object_number} 0 obj" if object_number else None,
        offset_start=start,
        offset_end=end,
        original_length=len(orig_val),
        corrupted_length=len(fake_val),
        severity=0.45,
        recoverability=Recoverability.RECOVERABLE_FROM_SURVIVING_EVIDENCE,
        reversible=True,
        details={"original_length": orig_val.decode("ascii"), "corrupted_length": "99999"},
    )
    return corrupted, op
