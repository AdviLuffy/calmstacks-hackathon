"""Real-World PDF Corruption Laboratory (TRACE Phase 11).

Provides high-fidelity corruption recipes simulating real online PDF corrupters
(e.g., corrupter.net, file-repair online tools), file-transfer truncations,
bad-sector null overwrites, and bitstream mangling.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import random
import re
from typing import Any, Callable, Dict, List, Tuple


@dataclass(frozen=True)
class CorruptionRecipeResult:
    """Outcome of applying a real-world corruption recipe to a source PDF."""

    recipe_id: str
    recipe_name: str
    original_sha256: str
    original_size: int
    corrupted_bytes: bytes
    corrupted_sha256: str
    corrupted_size: int
    corruption_description: str
    expected_openable_after_repair: bool
    expected_min_authentic_pct: float
    details: Dict[str, Any]


def corrupt_mangled_header(source: bytes, rng: random.Random | None = None) -> bytes:
    """Simulate online corrupter or HTTP error: replace %PDF- with random noise or HTML."""
    if not source:
        return source
    r = rng or random.Random(42)
    # Prepend HTML/noise error wrapper and scramble magic bytes
    preamble = b"<html><head><title>500 Internal Error</title></head><body>"
    mangled = re.sub(rb"%PDF-\d+\.\d+", b"XPDF-CORRUPT", source, count=1)
    return preamble + mangled


def corrupt_destroyed_xref_trailer(source: bytes, rng: random.Random | None = None) -> bytes:
    """Simulate disk truncation or corrupter: completely destroy xref table and trailer."""
    # Look for isolated 'xref' keyword (not startxref)
    m = re.search(rb"(?:\r?\n|^)xref\b", source)
    if m:
        return source[:m.start()].rstrip()
    t_pos = source.rfind(b"trailer")
    if t_pos != -1:
        return source[:t_pos].rstrip()
    return source[: int(len(source) * 0.90)]



def corrupt_unterminated_objects(source: bytes, rng: random.Random | None = None) -> bytes:
    """Simulate delimiter stripping: erase 'endobj' tokens from intermediate objects."""
    r = rng or random.Random(42)
    matches = list(re.finditer(rb"\bendobj\b", source))
    if not matches:
        return source
    res = bytearray(source)
    # Wipe half of the endobj occurrences with spaces or nulls
    for idx, m in enumerate(matches):
        if idx % 2 == 1:
            res[m.start() : m.end()] = b" " * (m.end() - m.start())
    return bytes(res)


def corrupt_mutated_stream_lengths(source: bytes, rng: random.Random | None = None) -> bytes:
    """Simulate length corruption: replace /Length attributes with bogus values or remove them."""
    # Replace valid /Length 123 with /Length 999999 or /Length 0
    def _repl(m: re.Match) -> bytes:
        return b"/Length 999999"

    return re.sub(rb"/Length\s+\d+", _repl, source)


def corrupt_mutilated_flate_header(source: bytes, rng: random.Random | None = None) -> bytes:
    """Simulate Flate compression corruption: alter the 2-byte zlib header (0x78 0x9c)."""
    res = bytearray(source)
    # Locate streams and flip header bytes
    for sm in re.finditer(rb"stream[\r\n]+", source):
        start = sm.end()
        if start + 2 < len(res):
            # Check if looks like zlib header (0x78)
            if res[start] == 0x78:
                res[start] = 0x00  # Wipe zlib compression mode
                res[start + 1] = 0x00
    return bytes(res)


def corrupt_null_byte_sectors(source: bytes, sector_size: int = 512, rng: random.Random | None = None) -> bytes:
    """Simulate bad sectors / physical media damage: overwrite 512-byte blocks with null bytes."""
    if len(source) < sector_size * 2:
        return source
    r = rng or random.Random(42)
    res = bytearray(source)
    # Target middle sector (around 40% into the file)
    target_offset = (len(source) * 2) // 5
    target_offset = (target_offset // sector_size) * sector_size
    end_offset = min(len(res), target_offset + sector_size)
    res[target_offset:end_offset] = b"\x00" * (end_offset - target_offset)
    return bytes(res)


def corrupt_arbitrary_truncation(source: bytes, ratio: float = 0.65) -> bytes:
    """Simulate incomplete download / interrupted transfer: truncate file midstream."""
    cut = max(64, int(len(source) * ratio))
    return source[:cut]


def corrupt_online_scramble(source: bytes, rate: float = 0.03, rng: random.Random | None = None) -> bytes:
    """Simulate online corrupter (corrupter.net style): random byte modifications outside keywords."""
    r = rng or random.Random(42)
    res = bytearray(source)
    num_corruptions = max(1, int(len(res) * rate))
    for _ in range(num_corruptions):
        idx = r.randint(0, len(res) - 1)
        # Avoid corrupting initial %PDF- or final %%EOF if possible
        if idx > 32 and idx < len(res) - 32:
            res[idx] = r.randint(0, 255)
    return bytes(res)


def corrupt_orphan_pages(source: bytes) -> bytes:
    """Simulate deleted page hierarchy: wipe /Catalog and /Pages definitions."""
    corrupted = re.sub(rb"/Type\s*/Catalog\b", b"/Type /Cata_og", source)
    corrupted = re.sub(rb"/Type\s*/Pages\b", b"/Type /Pag_s", corrupted)
    return corrupted


RECIPES: Dict[str, Tuple[str, Callable[[bytes, random.Random | None], bytes], str, float]] = {
    "mangled_header": (
        "Mangled Magic Header & HTML Preamble",
        lambda src, rng: corrupt_mangled_header(src, rng),
        "Prepends web server error noise and corrupts %PDF- magic bytes.",
        0.80,
    ),
    "destroyed_xref_trailer": (
        "Obliterated XRef Table & Trailer",
        lambda src, rng: corrupt_destroyed_xref_trailer(src, rng),
        "Removes cross-reference table, startxref pointer, and trailer dictionary.",
        0.85,
    ),
    "unterminated_objects": (
        "Unterminated Objects (Missing endobj)",
        lambda src, rng: corrupt_unterminated_objects(src, rng),
        "Erases 'endobj' tokens from intermediate indirect objects.",
        0.90,
    ),
    "mutated_stream_lengths": (
        "Corrupted /Length Attributes",
        lambda src, rng: corrupt_mutated_stream_lengths(src, rng),
        "Replaces stream dictionary /Length integers with invalid values (999999).",
        0.95,
    ),
    "mutilated_flate_header": (
        "Damaged Flate / zlib Stream Headers",
        lambda src, rng: corrupt_mutilated_flate_header(src, rng),
        "Overwrites initial zlib header bytes inside compressed streams with nulls.",
        0.75,
    ),
    "null_byte_sectors": (
        "Zero-Filled Bad Sectors (512-byte blocks)",
        lambda src, rng: corrupt_null_byte_sectors(src, rng=rng),
        "Overwrites 512-byte sectors with zeros, simulating storage medium bad blocks.",
        0.70,
    ),
    "arbitrary_truncation": (
        "Interrupted Download / Mid-Bitstream Truncation",
        lambda src, rng: corrupt_arbitrary_truncation(src, ratio=0.65),
        "Truncates file at 65% of its length, cutting off downstream objects and EOF.",
        0.60,
    ),
    "online_scramble": (
        "Online File Corrupter (Byte Scramble)",
        lambda src, rng: corrupt_online_scramble(src, rate=0.02, rng=rng),
        "Simulates online tools that randomly alter 2% of byte content.",
        0.75,
    ),
    "orphan_pages": (
        "Orphan Pages (Obliterated Catalog & Pages Hierarchy)",
        lambda src, rng: corrupt_orphan_pages(src),
        "Destroys document catalog and page parent tree, stranding individual page objects.",
        0.85,
    ),
}


class RealWorldCorrupter:
    """Laboratory engine applying controlled real-world corruption recipes."""

    def __init__(self, seed: int = 42) -> None:
        self.seed = seed
        self.rng = random.Random(seed)

    def apply_recipe(
        self,
        recipe_id: str,
        source_pdf: bytes,
        seed: int | None = None,
    ) -> CorruptionRecipeResult:
        """Apply a named corruption recipe to a source PDF and return structured results."""
        if not source_pdf:
            raise ValueError("source_pdf cannot be empty")
        if recipe_id not in RECIPES:
            raise KeyError(f"Unknown corruption recipe: '{recipe_id}'. Available: {list(RECIPES.keys())}")

        active_rng = random.Random(seed if seed is not None else self.seed)
        name, fn, desc, exp_auth_pct = RECIPES[recipe_id]

        orig_sha = hashlib.sha256(source_pdf).hexdigest()
        corrupted_data = fn(source_pdf, active_rng)
        corr_sha = hashlib.sha256(corrupted_data).hexdigest()

        return CorruptionRecipeResult(
            recipe_id=recipe_id,
            recipe_name=name,
            original_sha256=orig_sha,
            original_size=len(source_pdf),
            corrupted_bytes=corrupted_data,
            corrupted_sha256=corr_sha,
            corrupted_size=len(corrupted_data),
            corruption_description=desc,
            expected_openable_after_repair=True,
            expected_min_authentic_pct=exp_auth_pct,
            details={"recipe_id": recipe_id, "seed": seed if seed is not None else self.seed},
        )
