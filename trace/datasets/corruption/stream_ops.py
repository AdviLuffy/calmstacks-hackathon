"""Stream corruption operators for PDF bitstreams."""

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


def _find_stream_bounds(data: bytes, obj_num: Optional[int] = None) -> Optional[Tuple[int, int]]:
    """Locate stream payload bounds (start after stream\\r?\\n, end before endstream)."""
    search_space = data
    offset_base = 0

    if obj_num is not None:
        obj_m = re.search(rb"(?:^|[\r\n\s])" + str(obj_num).encode() + rb"\s+0\s+obj[\s\S]*?endobj", data)
        if obj_m:
            search_space = obj_m.group(0)
            offset_base = obj_m.start(0)

    sm = re.search(rb"stream[\r\n]+", search_space)
    em = re.search(rb"[\r\n]*endstream", search_space)

    if sm and em and em.start() > sm.end():
        return offset_base + sm.end(), offset_base + em.start()
    return None


def truncate_stream(
    data: bytes,
    obj_num: Optional[int] = None,
    keep_ratio: float = 0.5,
) -> Tuple[bytes, Optional[CorruptionOperation]]:
    """Truncate the byte payload within a stream."""
    bounds = _find_stream_bounds(data, obj_num)
    if not bounds:
        return data, None

    s_start, s_end = bounds
    orig_len = s_end - s_start
    if orig_len <= 4:
        return data, None

    keep_len = max(2, int(orig_len * keep_ratio))
    corrupted = data[: s_start + keep_len] + data[s_end:]

    op = CorruptionOperation(
        operation_id=str(uuid.uuid4())[:8],
        type=CorruptionType.TRUNCATE_STREAM,
        object_id=f"{obj_num} 0 obj" if obj_num else None,
        offset_start=s_start + keep_len,
        offset_end=s_end,
        original_length=orig_len - keep_len,
        corrupted_length=0,
        severity=round(1.0 - keep_ratio, 3),
        recoverability=Recoverability.PARTIAL,
        reversible=False,
        details={"original_stream_length": orig_len, "retained_stream_length": keep_len},
    )
    return corrupted, op


def remove_stream_prefix(
    data: bytes,
    obj_num: Optional[int] = None,
    bytes_to_remove: int = 16,
) -> Tuple[bytes, Optional[CorruptionOperation]]:
    """Remove leading bytes of a stream (e.g. zlib / FlateDecode header)."""
    bounds = _find_stream_bounds(data, obj_num)
    if not bounds:
        return data, None

    s_start, s_end = bounds
    cut = min(bytes_to_remove, s_end - s_start)
    corrupted = data[:s_start] + data[s_start + cut :]

    op = CorruptionOperation(
        operation_id=str(uuid.uuid4())[:8],
        type=CorruptionType.REMOVE_STREAM_PREFIX,
        object_id=f"{obj_num} 0 obj" if obj_num else None,
        offset_start=s_start,
        offset_end=s_start + cut,
        original_length=cut,
        corrupted_length=0,
        severity=0.55,
        recoverability=Recoverability.PARTIAL,
        reversible=False,
        details={"removed_prefix_bytes": cut},
    )
    return corrupted, op


def remove_stream_suffix(
    data: bytes,
    obj_num: Optional[int] = None,
) -> Tuple[bytes, Optional[CorruptionOperation]]:
    """Remove 'endstream' keyword."""
    search_space = data
    base = 0
    if obj_num is not None:
        obj_m = re.search(rb"(?:^|[\r\n\s])" + str(obj_num).encode() + rb"\s+0\s+obj[\s\S]*?endobj", data)
        if obj_m:
            search_space = obj_m.group(0)
            base = obj_m.start(0)

    em = re.search(rb"endstream", search_space)
    if not em:
        return data, None

    pos = base + em.start()
    corrupted = data[:pos] + data[pos + 9 :]

    op = CorruptionOperation(
        operation_id=str(uuid.uuid4())[:8],
        type=CorruptionType.REMOVE_STREAM_SUFFIX,
        object_id=f"{obj_num} 0 obj" if obj_num else None,
        offset_start=pos,
        offset_end=pos + 9,
        original_length=9,
        corrupted_length=0,
        severity=0.50,
        recoverability=Recoverability.RECOVERABLE_FROM_SURVIVING_EVIDENCE,
        reversible=True,
        details={"removed_keyword": "endstream"},
    )
    return corrupted, op


def corrupt_stream_bytes(
    data: bytes,
    obj_num: Optional[int] = None,
    rng: Optional[random.Random] = None,
) -> Tuple[bytes, Optional[CorruptionOperation]]:
    """Mutate bytes inside a stream payload with noise."""
    bounds = _find_stream_bounds(data, obj_num)
    if not bounds:
        return data, None

    r = rng or random.Random(42)
    s_start, s_end = bounds
    orig_len = s_end - s_start
    if orig_len <= 4:
        return data, None

    # Corrupt 30% of stream middle
    corrupt_len = max(2, int(orig_len * 0.30))
    pos = s_start + r.randint(0, max(0, orig_len - corrupt_len))
    noise = bytes(r.getrandbits(8) for _ in range(corrupt_len))

    corrupted = data[:pos] + noise + data[pos + corrupt_len :]
    op = CorruptionOperation(
        operation_id=str(uuid.uuid4())[:8],
        type=CorruptionType.CORRUPT_STREAM_BYTES,
        object_id=f"{obj_num} 0 obj" if obj_num else None,
        offset_start=pos,
        offset_end=pos + corrupt_len,
        original_length=corrupt_len,
        corrupted_length=corrupt_len,
        severity=0.60,
        recoverability=Recoverability.UNRECOVERABLE_WITHOUT_EXTERNAL_REDUNDANCY,
        reversible=False,
        details={"mutated_bytes": corrupt_len},
    )
    return corrupted, op


def damage_stream_payload_only(
    data: bytes,
    obj_num: Optional[int] = None,
    rng: Optional[random.Random] = None,
) -> Tuple[bytes, Optional[CorruptionOperation]]:
    """Damage stream payload while preserving `/Length`, `/Filter`, and dictionary tokens intact."""
    bounds = _find_stream_bounds(data, obj_num)
    if not bounds:
        return data, None

    r = rng or random.Random(42)
    s_start, s_end = bounds
    orig_len = s_end - s_start

    zero_len = max(4, int(orig_len * 0.40))
    pos = s_start + max(0, (orig_len - zero_len) // 2)
    corrupted = data[:pos] + (b"\x00" * zero_len) + data[pos + zero_len :]

    op = CorruptionOperation(
        operation_id=str(uuid.uuid4())[:8],
        type=CorruptionType.DAMAGE_STREAM_PAYLOAD_ONLY,
        object_id=f"{obj_num} 0 obj" if obj_num else None,
        offset_start=pos,
        offset_end=pos + zero_len,
        original_length=zero_len,
        corrupted_length=zero_len,
        severity=0.55,
        recoverability=Recoverability.PARTIAL,
        reversible=False,
        details={"zeroed_payload_bytes": zero_len, "dictionary_preserved": True},
    )
    return corrupted, op
