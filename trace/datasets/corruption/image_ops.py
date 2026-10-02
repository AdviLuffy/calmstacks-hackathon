"""Image corruption operators for embedded PDF visuals."""

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


def remove_image_object(
    data: bytes,
) -> Tuple[bytes, Optional[CorruptionOperation]]:
    """Remove an embedded `/Subtype /Image` XObject."""
    m = re.search(rb"(?:^|[\r\n\s])(\d+\s+0\s+obj[\s\S]*?/Subtype\s*/Image[\s\S]*?endobj)", data)
    if not m:
        return data, None

    start = m.start(1)
    end = m.end(1)
    orig_len = end - start
    corrupted = data[:start] + data[end:]

    op = CorruptionOperation(
        operation_id=str(uuid.uuid4())[:8],
        type=CorruptionType.REMOVE_IMAGE_OBJECT,
        offset_start=start,
        offset_end=end,
        original_length=orig_len,
        corrupted_length=0,
        severity=0.70,
        recoverability=Recoverability.UNRECOVERABLE_WITHOUT_EXTERNAL_REDUNDANCY,
        reversible=False,
        details={"removed_image_bytes": orig_len},
    )
    return corrupted, op


def truncate_image_stream(
    data: bytes,
    keep_ratio: float = 0.3,
) -> Tuple[bytes, Optional[CorruptionOperation]]:
    """Truncate the image stream while keeping the Image XObject dictionary."""
    img_m = re.search(rb"/Subtype\s*/Image[\s\S]*?stream[\r\n]+([\s\S]*?)[\r\n]*endstream", data)
    if not img_m:
        return data, None

    stream_payload = img_m.group(1)
    s_start = img_m.start(1)
    s_end = img_m.end(1)
    orig_len = len(stream_payload)

    keep_len = max(4, int(orig_len * keep_ratio))
    corrupted = data[: s_start + keep_len] + data[s_end:]

    op = CorruptionOperation(
        operation_id=str(uuid.uuid4())[:8],
        type=CorruptionType.TRUNCATE_IMAGE_STREAM,
        offset_start=s_start + keep_len,
        offset_end=s_end,
        original_length=orig_len - keep_len,
        corrupted_length=0,
        severity=round(1.0 - keep_ratio, 3),
        recoverability=Recoverability.PARTIAL,
        reversible=False,
        details={"original_image_bytes": orig_len, "retained_image_bytes": keep_len},
    )
    return corrupted, op


def remove_image_references(
    data: bytes,
) -> Tuple[bytes, Optional[CorruptionOperation]]:
    """Remove `/Do` operator invoking image display."""
    m = re.search(rb"/[A-Za-z0-9_-]+\s+Do\b", data)
    if not m:
        return data, None

    start = m.start(0)
    end = m.end(0)
    corrupted = data[:start] + data[end:]

    op = CorruptionOperation(
        operation_id=str(uuid.uuid4())[:8],
        type=CorruptionType.REMOVE_IMAGE_REFERENCES,
        offset_start=start,
        offset_end=end,
        original_length=end - start,
        corrupted_length=0,
        severity=0.40,
        recoverability=Recoverability.RECOVERABLE_FROM_SURVIVING_EVIDENCE,
        reversible=True,
        details={"removed_operator": m.group(0).decode("ascii", errors="ignore")},
    )
    return corrupted, op
