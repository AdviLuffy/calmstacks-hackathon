"""Real-World PDF Corruption Test Corpus Builder (TRACE Phase 11).

Constructs a reproducible, audited corpus of damaged PDFs covering:
1. Truncated files and missing endings
2. Missing or damaged cross-reference tables and trailers
3. Corrupted object streams
4. Damaged page trees and resource references
5. Missing or altered byte ranges (preamble noise)
6. Random byte overwrites and deletions (online corrupters)
7. Zero-filled physical bad sectors
8. Genuine DARPA SafeDocs damaged samples

Ground truth documents are stored separately and are NEVER exposed to the
recovery engine during evaluation.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from trace.datasets.corruption.real_world_corrupter import RealWorldCorrupter

logger = logging.getLogger(__name__)

CORPUS_ROOT = Path(__file__).resolve().parent / "corpus"
ORIGINALS_DIR = CORPUS_ROOT / "originals"
DAMAGED_DIR = CORPUS_ROOT / "damaged"
MANIFEST_PATH = CORPUS_ROOT / "corpus_manifest.json"


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class CorpusBuilder:
    """Builds and verifies the Phase 11 Real-World PDF Corruption Corpus."""

    def __init__(self, root_dir: Path | None = None) -> None:
        self.root_dir = root_dir or CORPUS_ROOT
        self.originals_dir = self.root_dir / "originals"
        self.damaged_dir = self.root_dir / "damaged"
        self.manifest_path = self.root_dir / "corpus_manifest.json"
        self.corrupter = RealWorldCorrupter(seed=42)

    def ensure_directories(self) -> None:
        self.originals_dir.mkdir(parents=True, exist_ok=True)
        self.damaged_dir.mkdir(parents=True, exist_ok=True)

    def build_corpus(self) -> dict[str, Any]:
        """Generate the full test corpus with originals, damaged copies, and manifest."""
        self.ensure_directories()
        repo_root = Path(__file__).resolve().parents[3]

        # Locate clean original seed files
        seed_candidates = [
            repo_root / "trace" / "datasets" / "real_world" / "data" / "sample_collection" / "originals" / "canonical_paper_001.pdf",
            repo_root / "trace" / "datasets" / "real_world" / "data" / "sample_collection" / "originals" / "canonical_paper_002.pdf",
            repo_root / "evidence" / "datasets" / "groundtruth" / "reference_complete.pdf",
            repo_root / "evidence" / "datasets" / "groundtruth" / "visible_text.pdf",
        ]

        seeds: dict[str, bytes] = {}
        for p in seed_candidates:
            if p.is_file():
                data = p.read_bytes()
                seeds[p.name] = data
                # Copy into originals directory
                (self.originals_dir / p.name).write_bytes(data)

        if "canonical_paper_001.pdf" not in seeds:
            # Fallback self-contained seed
            sample_minimal = (
                b"%PDF-1.4\n"
                b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
                b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
                b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
                b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
                b"5 0 obj\n<< /Length 44 >>\nstream\n"
                b"BT /F1 20 Tf 50 720 Td (Phase 11 Corpus Baseline) Tj ET\n"
                b"endstream\nendobj\n"
                b"xref\n0 6\n0000000000 65535 f \r\n0000000009 00000 n \r\n0000000058 00000 n \r\n"
                b"0000000115 00000 n \r\n0000000240 00000 n \r\n0000000310 00000 n \r\n"
                b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n404\n%%EOF\n"
            )
            seeds["canonical_paper_001.pdf"] = sample_minimal
            (self.originals_dir / "canonical_paper_001.pdf").write_bytes(sample_minimal)

        doc1 = seeds["canonical_paper_001.pdf"]
        doc2 = seeds.get("canonical_paper_002.pdf", doc1)
        doc3 = seeds.get("reference_complete.pdf", doc1)

        manifest_entries: list[dict[str, Any]] = []

        # 1. Mangled Header
        res_mangled = self.corrupter.apply_recipe("mangled_header", doc1)
        mangled_name = "CORPUS_01_mangled_header.pdf"
        (self.damaged_dir / mangled_name).write_bytes(res_mangled.corrupted_bytes)
        manifest_entries.append({
            "corpus_id": "CORPUS-01-MANGLED-HEADER",
            "damage_category": "altered_byte_ranges",
            "source_type": "controlled_recipe",
            "recipe_id": "mangled_header",
            "original_filename": "canonical_paper_001.pdf",
            "original_sha256": sha256_of(doc1),
            "original_size_bytes": len(doc1),
            "corrupted_filename": mangled_name,
            "corrupted_sha256": res_mangled.corrupted_sha256,
            "corrupted_size_bytes": res_mangled.corrupted_size,
            "description": "HTTP error header preamble prepended and %PDF- magic bytes replaced.",
            "expected_openable_after_recovery": True,
            "expected_min_authentic_pct": 80.0,
        })

        # 2. Destroyed XRef Table and Trailer
        res_xref = self.corrupter.apply_recipe("destroyed_xref_trailer", doc1)
        xref_name = "CORPUS_02_destroyed_xref_trailer.pdf"
        (self.damaged_dir / xref_name).write_bytes(res_xref.corrupted_bytes)
        manifest_entries.append({
            "corpus_id": "CORPUS-02-DESTROYED-XREF",
            "damage_category": "damaged_xref_trailer",
            "source_type": "controlled_recipe",
            "recipe_id": "destroyed_xref_trailer",
            "original_filename": "canonical_paper_001.pdf",
            "original_sha256": sha256_of(doc1),
            "original_size_bytes": len(doc1),
            "corrupted_filename": xref_name,
            "corrupted_sha256": res_xref.corrupted_sha256,
            "corrupted_size_bytes": res_xref.corrupted_size,
            "description": "Cross-reference table, trailer dictionary, startxref, and EOF completely severed.",
            "expected_openable_after_recovery": True,
            "expected_min_authentic_pct": 85.0,
        })

        # 3. Unterminated Objects
        res_unterminated = self.corrupter.apply_recipe("unterminated_objects", doc1)
        unterminated_name = "CORPUS_03_unterminated_objects.pdf"
        (self.damaged_dir / unterminated_name).write_bytes(res_unterminated.corrupted_bytes)
        manifest_entries.append({
            "corpus_id": "CORPUS-03-UNTERMINATED-OBJECTS",
            "damage_category": "broken_metadata",
            "source_type": "controlled_recipe",
            "recipe_id": "unterminated_objects",
            "original_filename": "canonical_paper_001.pdf",
            "original_sha256": sha256_of(doc1),
            "original_size_bytes": len(doc1),
            "corrupted_filename": unterminated_name,
            "corrupted_sha256": res_unterminated.corrupted_sha256,
            "corrupted_size_bytes": res_unterminated.corrupted_size,
            "description": "endobj delimiter tokens erased between consecutive indirect objects.",
            "expected_openable_after_recovery": True,
            "expected_min_authentic_pct": 90.0,
        })

        # 4. Mutated Stream Lengths
        res_lengths = self.corrupter.apply_recipe("mutated_stream_lengths", doc1)
        lengths_name = "CORPUS_04_mutated_stream_lengths.pdf"
        (self.damaged_dir / lengths_name).write_bytes(res_lengths.corrupted_bytes)
        manifest_entries.append({
            "corpus_id": "CORPUS-04-MUTATED-STREAM-LENGTHS",
            "damage_category": "corrupted_object_stream",
            "source_type": "controlled_recipe",
            "recipe_id": "mutated_stream_lengths",
            "original_filename": "canonical_paper_001.pdf",
            "original_sha256": sha256_of(doc1),
            "original_size_bytes": len(doc1),
            "corrupted_filename": lengths_name,
            "corrupted_sha256": res_lengths.corrupted_sha256,
            "corrupted_size_bytes": res_lengths.corrupted_size,
            "description": "Stream dictionary /Length attributes set to invalid bogus integer (999999).",
            "expected_openable_after_recovery": True,
            "expected_min_authentic_pct": 95.0,
        })

        # 5. Mutilated Flate Stream Headers
        res_flate = self.corrupter.apply_recipe("mutilated_flate_header", doc2)
        flate_name = "CORPUS_05_mutilated_flate_header.pdf"
        (self.damaged_dir / flate_name).write_bytes(res_flate.corrupted_bytes)
        manifest_entries.append({
            "corpus_id": "CORPUS-05-MUTILATED-FLATE",
            "damage_category": "corrupted_object_stream",
            "source_type": "controlled_recipe",
            "recipe_id": "mutilated_flate_header",
            "original_filename": "canonical_paper_002.pdf",
            "original_sha256": sha256_of(doc2),
            "original_size_bytes": len(doc2),
            "corrupted_filename": flate_name,
            "corrupted_sha256": res_flate.corrupted_sha256,
            "corrupted_size_bytes": res_flate.corrupted_size,
            "description": "Zlib 0x78 compression headers overwritten with null bytes inside streams.",
            "expected_openable_after_recovery": True,
            "expected_min_authentic_pct": 75.0,
        })

        # 6. Null-Byte Sector Damage
        res_null = self.corrupter.apply_recipe("null_byte_sectors", doc3)
        null_name = "CORPUS_06_null_byte_sectors.pdf"
        (self.damaged_dir / null_name).write_bytes(res_null.corrupted_bytes)
        manifest_entries.append({
            "corpus_id": "CORPUS-06-NULL-BYTE-SECTOR",
            "damage_category": "missing_byte_ranges",
            "source_type": "controlled_recipe",
            "recipe_id": "null_byte_sectors",
            "original_filename": "reference_complete.pdf",
            "original_sha256": sha256_of(doc3),
            "original_size_bytes": len(doc3),
            "corrupted_filename": null_name,
            "corrupted_sha256": res_null.corrupted_sha256,
            "corrupted_size_bytes": res_null.corrupted_size,
            "description": "512-byte contiguous null-filled sector overwrite simulating bad media block.",
            "expected_openable_after_recovery": True,
            "expected_min_authentic_pct": 70.0,
        })

        # 7. Arbitrary Mid-Stream Truncation
        res_trunc = self.corrupter.apply_recipe("arbitrary_truncation", doc2)
        trunc_name = "CORPUS_07_arbitrary_truncation.pdf"
        (self.damaged_dir / trunc_name).write_bytes(res_trunc.corrupted_bytes)
        manifest_entries.append({
            "corpus_id": "CORPUS-07-MIDSTREAM-TRUNCATION",
            "damage_category": "truncated_file",
            "source_type": "controlled_recipe",
            "recipe_id": "arbitrary_truncation",
            "original_filename": "canonical_paper_002.pdf",
            "original_sha256": sha256_of(doc2),
            "original_size_bytes": len(doc2),
            "corrupted_filename": trunc_name,
            "corrupted_sha256": res_trunc.corrupted_sha256,
            "corrupted_size_bytes": res_trunc.corrupted_size,
            "description": "File cut off abruptly at 65% length, simulating network transfer failure.",
            "expected_openable_after_recovery": True,
            "expected_min_authentic_pct": 60.0,
        })

        # 8. Online Byte Scramble (corrupter.net)
        res_scramble = self.corrupter.apply_recipe("online_scramble", doc1, seed=777)
        scramble_name = "CORPUS_08_online_scramble.pdf"
        (self.damaged_dir / scramble_name).write_bytes(res_scramble.corrupted_bytes)
        manifest_entries.append({
            "corpus_id": "CORPUS-08-ONLINE-SCRAMBLE",
            "damage_category": "random_byte_overwrites",
            "source_type": "controlled_recipe",
            "recipe_id": "online_scramble",
            "original_filename": "canonical_paper_001.pdf",
            "original_sha256": sha256_of(doc1),
            "original_size_bytes": len(doc1),
            "corrupted_filename": scramble_name,
            "corrupted_sha256": res_scramble.corrupted_sha256,
            "corrupted_size_bytes": res_scramble.corrupted_size,
            "description": "2% pseudo-random byte mutation across stream bodies and dictionary tokens.",
            "expected_openable_after_recovery": True,
            "expected_min_authentic_pct": 75.0,
        })

        # 9. Orphan Pages (wiped Catalog and Pages hierarchy)
        res_orphan = self.corrupter.apply_recipe("orphan_pages", doc1)
        orphan_name = "CORPUS_09_orphan_pages.pdf"
        (self.damaged_dir / orphan_name).write_bytes(res_orphan.corrupted_bytes)
        manifest_entries.append({
            "corpus_id": "CORPUS-09-ORPHAN-PAGES",
            "damage_category": "damaged_page_tree",
            "source_type": "controlled_recipe",
            "recipe_id": "orphan_pages",
            "original_filename": "canonical_paper_001.pdf",
            "original_sha256": sha256_of(doc1),
            "original_size_bytes": len(doc1),
            "corrupted_filename": orphan_name,
            "corrupted_sha256": res_orphan.corrupted_sha256,
            "corrupted_size_bytes": res_orphan.corrupted_size,
            "description": "Root /Catalog and /Pages dictionary markers obliterated.",
            "expected_openable_after_recovery": True,
            "expected_min_authentic_pct": 85.0,
        })

        # 10. Genuine DARPA SafeDocs sample 1 (xref corruption)
        safedocs_1_path = repo_root / "trace" / "datasets" / "real_world" / "data" / "genuine_damaged" / "safedocs_xref_corruption_01.pdf"
        if safedocs_1_path.is_file():
            data_sd1 = safedocs_1_path.read_bytes()
            sd1_name = "CORPUS_10_safedocs_xref_corruption.pdf"
            (self.damaged_dir / sd1_name).write_bytes(data_sd1)
            manifest_entries.append({
                "corpus_id": "CORPUS-10-SAFEDOCS-XREF",
                "damage_category": "damaged_xref_trailer",
                "source_type": "genuine_external_safedocs",
                "recipe_id": "darpa_safedocs_in_the_wild",
                "original_filename": None,
                "original_sha256": None,
                "original_size_bytes": None,
                "corrupted_filename": sd1_name,
                "corrupted_sha256": sha256_of(data_sd1),
                "corrupted_size_bytes": len(data_sd1),
                "description": "Genuine in-the-wild xref table corruption from DARPA SafeDocs public corpus.",
                "expected_openable_after_recovery": True,
                "expected_min_authentic_pct": 80.0,
            })

        # 11. Genuine DARPA SafeDocs sample 2 (truncated stream)
        safedocs_2_path = repo_root / "trace" / "datasets" / "real_world" / "data" / "genuine_damaged" / "safedocs_truncated_stream_02.pdf"
        if safedocs_2_path.is_file():
            data_sd2 = safedocs_2_path.read_bytes()
            sd2_name = "CORPUS_11_safedocs_truncated_stream.pdf"
            (self.damaged_dir / sd2_name).write_bytes(data_sd2)
            manifest_entries.append({
                "corpus_id": "CORPUS-11-SAFEDOCS-TRUNC",
                "damage_category": "truncated_file",
                "source_type": "genuine_external_safedocs",
                "recipe_id": "darpa_safedocs_in_the_wild",
                "original_filename": None,
                "original_sha256": None,
                "original_size_bytes": None,
                "corrupted_filename": sd2_name,
                "corrupted_sha256": sha256_of(data_sd2),
                "corrupted_size_bytes": len(data_sd2),
                "description": "Genuine in-the-wild truncated stream from DARPA SafeDocs public corpus.",
                "expected_openable_after_recovery": True,
                "expected_min_authentic_pct": 70.0,
            })

        manifest = {
            "version": "1.0",
            "corpus_name": "TRACE Phase 11 Real-World PDF Corruption Corpus",
            "total_items": len(manifest_entries),
            "controlled_recipe_items": sum(1 for e in manifest_entries if e["source_type"] == "controlled_recipe"),
            "genuine_safedocs_items": sum(1 for e in manifest_entries if e["source_type"] == "genuine_external_safedocs"),
            "categories_covered": sorted(list({e["damage_category"] for e in manifest_entries})),
            "items": manifest_entries,
        }

        self.manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest


def get_corpus_manifest() -> dict[str, Any]:
    """Retrieve or build the real-world corruption corpus manifest."""
    builder = CorpusBuilder()
    if not builder.manifest_path.is_file():
        return builder.build_corpus()
    try:
        return json.loads(builder.manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return builder.build_corpus()
