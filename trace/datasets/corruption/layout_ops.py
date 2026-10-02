"""Page and layout structure corruption operators."""

from __future__ import annotations

import re
import uuid
from typing import Optional, Tuple

from trace.datasets.schemas.corruption import (
    CorruptionOperation,
    CorruptionType,
    Recoverability,
)


def remove_page_object(
    data: bytes,
) -> Tuple[bytes, Optional[CorruptionOperation]]:
    """Remove a `/Type /Page` object."""
    m = re.search(rb"(?:^|[\r\n\s])(\d+\s+0\s+obj[\s\S]*?/Type\s*/Page\b[\s\S]*?endobj)", data)
    if not m:
        return data, None

    start = m.start(1)
    end = m.end(1)
    orig_len = end - start
    corrupted = data[:start] + data[end:]

    op = CorruptionOperation(
        operation_id=str(uuid.uuid4())[:8],
        type=CorruptionType.REMOVE_PAGE_OBJECT,
        offset_start=start,
        offset_end=end,
        original_length=orig_len,
        corrupted_length=0,
        severity=0.75,
        recoverability=Recoverability.UNRECOVERABLE_WITHOUT_EXTERNAL_REDUNDANCY,
        reversible=False,
        details={"removed_page_bytes": orig_len},
    )
    return corrupted, op


def damage_page_tree(
    data: bytes,
) -> Tuple[bytes, Optional[CorruptionOperation]]:
    """Damage `/Kids [ ... ]` array in the Page tree."""
    m = re.search(rb"/Kids\s*\[([^\]]+)\]", data)
    if not m:
        return data, None

    start = m.start(1)
    end = m.end(1)
    orig_kids = m.group(1)
    # Empty out the Kids array
    corrupted = data[:start] + b" " + data[end:]

    op = CorruptionOperation(
        operation_id=str(uuid.uuid4())[:8],
        type=CorruptionType.DAMAGE_PAGE_TREE,
        offset_start=start,
        offset_end=end,
        original_length=len(orig_kids),
        corrupted_length=1,
        severity=0.80,
        recoverability=Recoverability.RECOVERABLE_FROM_SURVIVING_EVIDENCE,
        reversible=True,
        details={"original_kids": orig_kids.decode("ascii", errors="ignore"), "corrupted": "cleared"},
    )
    return corrupted, op


def remove_content_ref(
    data: bytes,
) -> Tuple[bytes, Optional[CorruptionOperation]]:
    """Remove `/Contents N 0 R` reference from Page dictionary."""
    m = re.search(rb"/Contents\s+(\d+\s+0\s+R|\[[^\]]+\])", data)
    if not m:
        return data, None

    start = m.start(0)
    end = m.end(0)
    orig_ref = m.group(0)
    corrupted = data[:start] + data[end:]

    op = CorruptionOperation(
        operation_id=str(uuid.uuid4())[:8],
        type=CorruptionType.REMOVE_CONTENT_REF,
        offset_start=start,
        offset_end=end,
        original_length=end - start,
        corrupted_length=0,
        severity=0.65,
        recoverability=Recoverability.RECOVERABLE_FROM_SURVIVING_EVIDENCE,
        reversible=True,
        details={"removed_contents_ref": orig_ref.decode("ascii", errors="ignore")},
    )
    return corrupted, op
