"""Text corruption operators for PDF text content streams."""

from __future__ import annotations

import re
import uuid
from typing import Optional, Tuple

from trace.datasets.schemas.corruption import (
    CorruptionOperation,
    CorruptionType,
    Recoverability,
)


def remove_text_operators(
    data: bytes,
    max_count: int = 2,
) -> Tuple[bytes, Optional[CorruptionOperation]]:
    """Remove text rendering operators `(...) Tj` or `[...] TJ`."""
    pattern = re.compile(rb"(\([^\)\r\n]*\)\s*Tj|\[[^\]\r\n]*\]\s*TJ)")
    matches = list(pattern.finditer(data))
    if not matches:
        return data, None

    to_remove = matches[:max_count]
    # Remove from end to preserve earlier offsets
    corrupted = data
    total_removed = 0
    start_pos = to_remove[0].start()
    end_pos = to_remove[-1].end()

    for m in reversed(to_remove):
        corrupted = corrupted[: m.start()] + corrupted[m.end() :]
        total_removed += (m.end() - m.start())

    op = CorruptionOperation(
        operation_id=str(uuid.uuid4())[:8],
        type=CorruptionType.REMOVE_TEXT_OPERATORS,
        offset_start=start_pos,
        offset_end=end_pos,
        original_length=total_removed,
        corrupted_length=0,
        severity=0.50,
        recoverability=Recoverability.UNRECOVERABLE_WITHOUT_EXTERNAL_REDUNDANCY,
        reversible=False,
        details={"removed_operators_count": len(to_remove)},
    )
    return corrupted, op


def remove_text_fragments(
    data: bytes,
    fragment: str,
) -> Tuple[bytes, Optional[CorruptionOperation]]:
    """Remove occurrences of a specific literal text fragment from PDF streams."""
    target = fragment.encode("latin-1", errors="ignore")
    pos = data.find(target)
    if pos == -1:
        return data, None

    orig_len = len(target)
    corrupted = data[:pos] + data[pos + orig_len :]

    op = CorruptionOperation(
        operation_id=str(uuid.uuid4())[:8],
        type=CorruptionType.REMOVE_TEXT_FRAGMENTS,
        offset_start=pos,
        offset_end=pos + orig_len,
        original_length=orig_len,
        corrupted_length=0,
        severity=0.45,
        recoverability=Recoverability.UNRECOVERABLE_WITHOUT_EXTERNAL_REDUNDANCY,
        reversible=False,
        details={"fragment": fragment},
    )
    return corrupted, op


def truncate_text_streams(
    data: bytes,
) -> Tuple[bytes, Optional[CorruptionOperation]]:
    """Truncate content stream between `BT` and `ET` operators."""
    bt_m = re.search(rb"BT\b", data)
    et_m = re.search(rb"\bET", data)

    if not bt_m or not et_m or et_m.start() <= bt_m.end():
        return data, None

    start = bt_m.end()
    end = et_m.start()
    mid = start + (end - start) // 2
    corrupted = data[:mid] + data[end:]

    op = CorruptionOperation(
        operation_id=str(uuid.uuid4())[:8],
        type=CorruptionType.TRUNCATE_TEXT_STREAMS,
        offset_start=mid,
        offset_end=end,
        original_length=end - mid,
        corrupted_length=0,
        severity=0.60,
        recoverability=Recoverability.PARTIAL,
        reversible=False,
        details={"truncated_text_bytes": end - mid},
    )
    return corrupted, op
