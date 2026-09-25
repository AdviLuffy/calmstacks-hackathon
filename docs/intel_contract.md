# TRACE M0 Intelligence Contract

Frozen: 2026-09-25T00:00:00Z | Revision: 1.0.0

---

## 1. Authority Boundary

| Layer | Authority | Produces |
|-------|-----------|----------|
| Deterministic | **Authoritative** | OBSERVED, COMPUTED |
| AI / Narrative | **Non-authoritative** | INFERRED only |

**Rule**: `produced_by == "ai" → status == "INFERRED"` (schema-enforced).
**Rule**: `status ∈ {OBSERVED, COMPUTED} → produced_by == "deterministic"` (schema-enforced).

---

## 2. Identifiers

| Type | Pattern | Purpose |
|------|---------|---------|
| InstanceId | `^[A-Z]{2,6}(-[A-Z0-9]{1,12})*-\d{2,10}$` | Artifacts, groups, events, cases, media |
| FragmentInstanceId | `^FRG-[0-9a-f]{16}-\d{1,10}-\d{1,10}$` | Fragment records; **embedded range MUST equal byte_range** |
| DerivedId | `^RPT-[0-9a-f]{12}$` | report_id only |
| ActionId | `^ACT(-[A-Z0-9]{2,16}){1,4}$` | Recommended actions |

---

## 3. EvidenceRef (M0 Minimum Grammar)

```
bundle
case
case.<field>*
artifacts[<InstanceId>](.<field>*){0,2}
fragments[<FragmentInstanceId>](.<field>*){0,2}
reconstruction_groups[<InstanceId>](.<field>*){0,2}
timeline_events[<InstanceId>](.<field>*){0,2}
known_file_matches[<artifact InstanceId>](.<field>*){0,2}
```

- Every EvidenceRef **must resolve to exactly one record** in the bundle.
- Unresolvable refs fail grounding.
- `known_file_matches` is keyed by artifact_id (foreign key).

---

## 4. Confidence Rules

- Confidence ∈ [0, 1] is **ordinal reliability of a derivation**, NOT a probability.
- Ceilings per epistemic status:
  - INFERRED ≤ 0.70 (schema-enforced via `ConfidenceCeilings`)
  - OBSERVED, COMPUTED ≤ 1.00
- Monotonicity: derived confidence ≤ min confidence of cited evidence.
- ScoreComponent: `contribution == weight * value` (semantic rule SM-9).

---

## 5. Canonicalization (trace-cj/1.0)

- JSON sorted by key; reserved root keys (`_*`) excluded.
- Numbers: integers bare; floats quantized to 6dp, trailing zeros stripped, `-0 → 0`.
- Strings: UTF-8, JSON-escaped.
- Used for: `bundle_sha256`, `bytes_sha256`, `report_id`, `outputs_hash`.

---

## 6. Identity Hashing

### report_id
```
RPT- + hex(SHA256(
  "trace.intelligence_report/1.0" || 0x1F || case_id || 0x1F ||
  bundle_sha256 || 0x1F || module_version
))[:12]
```
- Identifies **what was analyzed** (stable across narrative changes).

### outputs_hash
```
SHA256(trace-cj/1.0(
  report
  - audit.outputs_hash
  - all x-volatile properties (generated_utc, audit.runtime_ms, audit.provider_calls[].latency_ms)
  - all reserved root keys (_*)
))
```
- Identifies **content produced** (changes when narrative/claims change).

### Volatile Properties (excluded from outputs_hash)
- `generated_utc`
- `audit.runtime_ms`
- `audit.provider_calls[].latency_ms`

---

## 7. P1 → P2 → P3 Data Flow

```
P1 (Evidence)          P2 (Intelligence)          P3 (Experience)
─────────────────      ───────────────────       ─────────────────
evidence_bundle/1.0 →  intelligence_report/1.0 →  UI / Reviewer
```

### Grounding Requirements (P2 → P3)

Every printable sentence in the intelligence report **must exist as a Claim** in `explainability.claims_index`.

Each Claim must have:
- `status` ∈ {OBSERVED, COMPUTED, INFERRED, MISSING}
- `confidence` respecting status ceiling
- `evidence_refs` (≥1, all resolvable)
- `validator_status` ∈ {passed, downgraded, rejected}
- `produced_by` ∈ {deterministic, ai} with schema-enforced link to status

**Failed grounding = claim dropped, recorded in `explainability.validator.rejected_claims`.**

---

## 8. Doctrines (Frozen)

- `epistemic_states`: ["OBSERVED", "COMPUTED", "INFERRED", "MISSING"]
- `ai_role`: "narrative_only"
- `policy`: "ai_never_invents_evidence"
- `confidence_ceilings`: {"INFERRED": 0.7}

---

## 9. Sanitisation

- `UntrustedText`: raw recovered content; C0 controls, bidi, instruction-like text **legal**.
- `SanitizedText`: output side; C0 controls/DEL **forbidden** (pattern enforced).
- Consumers **must sanitise before render/prompt**; never treat UntrustedText as executable.

---

## 10. Closed Vocabularies (1.x)

| Vocabulary | Enum | Frozen |
|------------|------|--------|
| ArtifactFamily | 13 values | ✅ |
| ArtifactKind | 52 values | ✅ |
| ArtifactLabel | 22 values | ✅ |
| TimestampKind | 9 values | ✅ |
| TimestampPrecision | 6 values | ✅ |

---

## 11. Extensions

- `extensions` object at bundle/report root: forward-compatible, consumers ignore unknown members.
- `additionalProperties: true` on Artifact, Fragment, ReconstructionGroup, Relationship.

---

## 12. Validation Layers

1. **Schema** (Draft 2020-12): structure, types, enums, patterns, required fields.
2. **Semantic (SM-1..SM-16)**: cross-ref integrity, byte-range bounds, identifier uniqueness, confidence/completeness consistency, EvidenceRef resolution, Fragment ID/range agreement, group gap arithmetic.
3. **Doctrine**: AI/authority boundary, confidence ceilings, grounding.

A report with `validation.bundle_conformed: false` or semantic violations **must surface them** in `validation.violations[]` — never silently omit.