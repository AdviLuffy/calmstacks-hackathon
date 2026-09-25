# TRACE Contracts Changelog

## [1.0.0] — FROZEN — 2026-09-25T00:00:00Z

M0 contract foundation. Frozen by P1, P2, P3 consensus.

### Schema SHA256 Hashes (trace-cj/1.0 canonical form)

- `common.schema.json`: dafed0a92893a39dcd2c2c6a8fa2d6922b82f715d334a603ca569356085dc2d2
- `evidence_bundle.schema.json`: ca9472bc27f9fa922818ff8f745e0fabba4a46876711e7b9406c11230774f519
- `intelligence_report.schema.json`: 23d61db8a7c91bbafc04f4b03f71acf14625974ae0ed3c03a889d4084363075e

### Scope

- `trace.evidence_bundle/1.0` — Producer contract (P1 → P2)
- `trace.intelligence_report/1.0` — Producer contract (P2 → P3)
- `common.schema.json` — Shared $defs (identifiers, vocabularies, rules)

### Frozen Amendments

- FragmentInstanceId format: `FRG-<lowercase_hex16>-<start>-<end>` with embedded range agreement
- EvidenceRef grammar (minimum M0): `bundle`, `case`, `artifacts[<InstanceId>]`, `fragments[<FragmentInstanceId>]`, `reconstruction_groups[<InstanceId>]`, `timeline_events[<InstanceId>]`, `known_file_matches[<artifact InstanceId>]` plus optional field path (≤2 segments)
- Confidence ceilings: INFERRED ≤ 0.70; OBSERVED/COMPUTED ≤ 1.00
- AI role: narrative_only; produced_by=ai → status=INFERRED
- Canonicalization: trace-cj/1.0 (sorted keys, normalized numbers, reserved root keys excluded)
- report_id: `RPT-` + hex(SHA256(domain || 0x1F || case_id || 0x1F || bundle_sha256 || 0x1F || module_version))[:12]
- outputs_hash: SHA256 of canonicalized report with x-volatile properties, audit.outputs_hash, and reserved root keys removed

### No Further Changes

This version is frozen. Any modification requires M1+ consensus.