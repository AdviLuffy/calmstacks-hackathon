"""The M0 contract registry: authorized decisions and open ambiguities.

Two different things are recorded here and they must not be conflated.

``DECISIONS``
    Contract decisions the team explicitly authorized (D-1 to D-5). These ARE binding
    for this implementation and are encoded in code.

``AMBIGUITIES``
    Gaps in the supplied M0 material for which no contract decision exists. These are NOT
    invented away. Where the material is silent, the implementation proceeds using only
    what the material does specify, and any behaviour that would require a guess is
    withheld and reported as unavailable with an explicit reason.

Everything here is exposed by ``GET /api/meta`` so no gap is invisible at runtime.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from app.contract.assumptions import (
    A7_ANALYSIS_CLOCK_EXEMPT_FIELDS,
    CONFIDENCE_BASIS_MIN_LENGTH,
    INFERRED_CONFIDENCE_MAX,
    OBSERVED_CONFIDENCE_MAX,
)
from app.contract.canonical import (
    CANONICALIZATION_PROFILE,
    REPORT_SCHEMA_ID,
    VOLATILE_OUTPUT_PATHS,
)
from app.contract.evidence_ref import (
    EVIDENCE_REF_PATTERN,
    GROUNDING_REASON_FIELD_NAMESPACE_NOT_FROZEN,
    PROSE_GRAMMAR_IS_NORMATIVE,
    REGEX_IS_NORMATIVE,
)
from app.contract.vocabularies import (
    ARTIFACT_KIND_IS_VALIDATING_ENUM,
    LABEL_TO_FAMILY_MAPPING_IS_FROZEN,
    LABEL_TO_KIND_MAPPING_IS_FROZEN,
)


@dataclass(frozen=True)
class ContractDecision:
    """A contract decision the team authorized, and where it is encoded."""

    decision_id: str
    title: str
    status: str
    authorized_by: str
    statement: str
    encoded_in: tuple[str, ...]
    consequence: str


@dataclass(frozen=True)
class ContractAmbiguity:
    """A gap in the supplied M0 material."""

    ambiguity_id: str
    title: str
    detail: str
    impact: str
    current_handling: str
    resolution: str | None = None
    blocking: bool = False
    recorded_in: tuple[str, ...] = field(default_factory=tuple)


DECISIONS: tuple[ContractDecision, ...] = (
    ContractDecision(
        decision_id="M0-DEC-01",
        title="EvidenceRef: the regex is the single normative syntactic validator",
        status="authorized",
        authorized_by="P1 (team contract owner)",
        statement=(
            "The regex supplied in the M0 material is normative for EvidenceRef syntax. "
            "The prose grammar is recorded as non-normative. Only one validation path is "
            "implemented; both conflicting definitions are never supported simultaneously."
        ),
        encoded_in=(
            "app.contract.evidence_ref.EVIDENCE_REF_PATTERN",
            "app.contract.evidence_ref.parse_evidence_ref",
            "app.contract.evidence_ref.REGEX_IS_NORMATIVE",
        ),
        consequence=(
            "The regex accepts 100% of the contract enumerated valid examples, whereas the "
            "prose grammar rejects `case`, which the contract lists as valid. The regex is "
            "therefore the only reading consistent with the material's own examples."
        ),
    ),
    ContractDecision(
        decision_id="M0-DEC-02",
        title="EvidenceRef resolution is tri-state and field-name agnostic",
        status="authorized",
        authorized_by="P1 (team contract owner)",
        statement=(
            "Resolution returns resolved, unresolved or unverifiable. No legal field name "
            "is invented, because the field namespace is not frozen. A syntactically valid "
            "reference whose target field cannot be verified is unverifiable with reason "
            "evidence_ref_field_namespace_not_frozen, and grounding fails conservatively."
        ),
        encoded_in=(
            "app.contract.evidence_ref.GroundingStatus",
            "app.contract.evidence_ref.SessionEvidenceRefResolver",
            "app.contract.evidence_ref.all_grounded",
        ),
        consequence=(
            "Grounding requires every reference to resolve. Because trailing field names "
            "cannot be verified yet, grounded AI explanations are effectively withheld until "
            "P1 publishes the field namespace. They are withheld with a recorded reason "
            "rather than accepted on an unverified basis."
        ),
    ),
    ContractDecision(
        decision_id="M0-DEC-03",
        title="AI output is INFERRED for the M0 confidence rules",
        status="authorized",
        authorized_by="P1 (team contract owner)",
        statement=(
            "ai_assisted output is treated as INFERRED. Confidence is capped at 0.70 and "
            "confidence_basis is mandatory with at least 8 characters. Confidence may remain "
            "null when the model does not provide one. Confidence is never synthesised and "
            "never inflated."
        ),
        encoded_in=(
            "app.contract.assumptions.validate_confidence",
            "app.contract.assumptions.combine_confidence",
            "app.schemas.ai.AIAnalysis",
        ),
        consequence=(
            "Any AI claim above the 0.70 ceiling is rejected at schema construction time, so "
            "an inflated model confidence cannot reach a client."
        ),
    ),
    ContractDecision(
        decision_id="M0-DEC-04",
        title="A7 governs evidence-derived timestamps only",
        status="authorized",
        authorized_by="P1 (team contract owner)",
        statement=(
            "A7 applies to evidence/media timestamps, which must use UTC Z, carry a "
            "timestamp source and a timestamp precision, and originate from the evidence. "
            "API bookkeeping timestamps may use the analysis system clock because the API "
            "contract requires them."
        ),
        encoded_in=(
            "app.contract.assumptions.A7_ANALYSIS_CLOCK_EXEMPT_FIELDS",
            "app.contract.assumptions.validate_evidence_timestamp",
            "app.schemas.common.EvidenceTimestamp",
            "app.schemas.common.UTCDateTime",
        ),
        consequence=(
            "Read literally, A7 would forbid generated_utc and audit.runtime_ms from "
            "existing at all, yet the canonicalization profile names them. Splitting evidence "
            "timestamps from API bookkeeping timestamps removes that contradiction."
        ),
    ),
    ContractDecision(
        decision_id="M0-DEC-05",
        title="ArtifactKind is a frozen constant, not a validating enum",
        status="authorized",
        authorized_by="P1 (team contract owner)",
        statement=(
            "The supplied ArtifactKind values are treated as a frozen documented constant "
            "and example set. Values are neither silently added nor removed. ArtifactKind is "
            "never inferred from ArtifactLabel because no label-to-kind mapping is frozen."
        ),
        encoded_in=(
            "app.contract.vocabularies.ARTIFACT_KIND_EXAMPLES",
            "app.contract.vocabularies.ARTIFACT_KIND_IS_VALIDATING_ENUM",
            "app.contract.vocabularies.LABEL_TO_KIND_MAPPING_IS_FROZEN",
        ),
        consequence=(
            "The API accepts any kind string and reports the label, family and kind as "
            "independent provenance-bearing values. It never fabricates one from another."
        ),
    ),
    ContractDecision(
        decision_id="M0-DEC-06",
        title="trace.evidence_bundle/1.0 root contract and the Option A fragment EvidenceRef form are frozen",
        status="authorized",
        authorized_by=(
            "P1/P2 (formal freeze of trace.evidence_bundle/1.0, including the Option A "
            "fragment EvidenceRef amendment)"
        ),
        statement=(
            "The frozen root contract for the Evidence Bundle has eight required root fields "
            "and six optional root fields; schema_version must carry the exact value "
            "trace.evidence_bundle/1.0 and bundle_id is permanently required within 1.x; no "
            "additional root fields are authorized. Fragment EvidenceRefs use "
            "fragments[FRG-<16 lowercase hex>-<start>-<end>] with an optional field path of up "
            "to two segments, and every fragments[...] reference must resolve to exactly one "
            "fragment record in the supplied Evidence Bundle: zero matches or multiple matches "
            "are grounding failures. No additional root fields, ID formats, or EvidenceRef "
            "syntax are authorized by this freeze."
        ),
        encoded_in=(
            "app.contract.evidence_bundle.EVIDENCE_BUNDLE_SCHEMA_VERSION",
            "app.contract.evidence_bundle.validate_evidence_bundle_root",
            "app.contract.evidence_ref.EVIDENCE_REF_PATTERN",
            "app.services.evidence.BundleEvidenceResolver",
        ),
        consequence=(
            "M0-AMB-07 is closed: the fragments slot of the single M0-DEC-01 pattern now "
            "expresses a frozen FragmentInstanceId as an alternative, the root contract is "
            "enforced at ingestion as bundle_contract_violation (422), and fragment grounding "
            "fails closed on zero or multiple matches instead of assuming a record. The P2 "
            "intelligence-report schema remains unfrozen and is untouched by this decision."
        ),
    ),
)


DECISION_IDS: tuple[str, ...] = tuple(decision.decision_id for decision in DECISIONS)
# ---------------------------------------------------------------------------------
# Open gaps in the supplied M0 material. None of these is resolved by invention.
# ---------------------------------------------------------------------------------
AMBIGUITIES: tuple[ContractAmbiguity, ...] = (
    ContractAmbiguity(
        ambiguity_id="M0-AMB-01",
        title="ArtifactLabel has no normative prose definitions",
        detail=(
            "The material freezes the 21 ArtifactLabel VALUES but supplies no normative prose "
            "definition for any individual label. The boundaries between "
            "application/octet-stream, unknown, cryptographic_container and "
            "application/x-executable are therefore undefined, and "
            "application/x-executable overlaps application/x-elf and application/x-pe."
        ),
        impact=(
            "Affects classification semantics, which belong to P2. This API never classifies, so "
            "it needs only the frozen value set, which IS supplied."
        ),
        current_handling=(
            "The 21 values are enforced exactly, with no synonyms and no additions. No "
            "definition-dependent behaviour exists anywhere in the API."
        ),
        blocking=False,
        recorded_in=("app.contract.vocabularies.ArtifactLabel",),
    ),
    ContractAmbiguity(
        ambiguity_id="M0-AMB-02",
        title="No label-to-family or label-to-kind mapping is frozen",
        detail=(
            "Ten of the thirteen family values (image, video, audio, document, archive, database, "
            "executable, log, text, email) have no identically named label, so the mapping is not "
            "derivable by name. No label-to-kind table is supplied at all, and three labels "
            "(application/x-executable, application/octet-stream, filesystem_metadata) have no "
            "plausible kind in the supplied kind examples."
        ),
        impact="Deriving one vocabulary from another would require inventing a contract table.",
        current_handling=(
            "Label, family and kind are carried as independent provenance-bearing values from "
            "P1/P2. The API never derives, defaults or completes one from another."
        ),
        blocking=False,
        recorded_in=(
            "app.contract.vocabularies.LABEL_TO_FAMILY_MAPPING_IS_FROZEN",
            "app.contract.vocabularies.LABEL_TO_KIND_MAPPING_IS_FROZEN",
        ),
    ),
    ContractAmbiguity(
        ambiguity_id="M0-AMB-03",
        title="EvidenceRef prose grammar and regex are not equivalent",
        detail=(
            "The material declares the regex equivalent to the prose grammar, but they differ. "
            "The regex accepts bundle.signature.matched and bundle.a.b, which the grammar forbids "
            "because the bundle alternative is standalone. Conversely the grammar requires case to "
            "carry 1..2 segments, which makes bare case invalid, yet bare case is listed in the "
            "material's own valid examples."
        ),
        impact=(
            "A validator cannot honour both definitions. The choice determines whether bare case "
            "is legal and whether trailing segments may follow bundle."
        ),
        current_handling=(
            "The regex is the single normative validator. Every enumerated valid example passes it, "
            "including bare case. Only one validation path exists; both definitions are never "
            "supported simultaneously."
        ),
        resolution=(
            "Resolved by M0-DEC-01. The regex is the only reading consistent with the material's "
            "own enumerated valid examples."
        ),
        blocking=False,
        recorded_in=(
            "app.contract.evidence_ref.EVIDENCE_REF_PATTERN",
            "app.contract.evidence_ref.PARSE_PATTERN",
        ),
    ),
    ContractAmbiguity(
        ambiguity_id="M0-AMB-04",
        title="The [n] index position rule exists only in prose",
        detail=(
            "The prose states the [n] index is allowed for timestamp provenance and is the only "
            "array index allowed, but the normative grammar attaches the optional index to every "
            "segment. The regex therefore accepts artifacts[ART-0001].signature[3].matched, which "
            "the prose forbids, and no positions are restricted."
        ),
        impact=(
            "A reference can carry an index on a segment the prose did not intend, and there is no "
            "frozen rule to reject it."
        ),
        current_handling=(
            "Syntax follows the regex. Indexed segments are decomposed and reported, but no "
            "positional restriction is invented. The required example "
            "artifacts[ART-0005].timestamps[0].value_utc is valid."
        ),
        resolution=None,
        blocking=False,
        recorded_in=("app.contract.evidence_ref.parse_evidence_ref",),
    ),
    ContractAmbiguity(
        ambiguity_id="M0-AMB-05",
        title="The EvidenceRef field namespace is not frozen",
        detail=(
            "The material requires every EvidenceRef to resolve, but never supplies the set of legal "
            "trailing field names per collection. Only eight names appear anywhere in the material "
            "(investigation_profile, focus_categories, signature, matched, timestamps, value_utc, "
            "byte_range, byte_contiguity, ts_utc, result), and the legal set per collection is "
            "never stated."
        ),
        impact=(
            "Full resolution and therefore grounding of AI explanations cannot be completed without "
            "inventing field names."
        ),
        current_handling=(
            "Resolution is tri-state. Collection membership and identifier existence are verified; "
            "any reference carrying trailing segments resolves to unverifiable with reason "
            "evidence_ref_field_namespace_not_frozen. Grounding fails conservatively, so no AI "
            "explanation is accepted on an unverified basis."
        ),
        resolution="Resolved by M0-DEC-02 (conservative handling).",
        blocking=False,
        recorded_in=(
            "app.contract.evidence_ref.SessionEvidenceRefResolver",
            "app.contract.evidence_ref.GROUNDING_REASON_FIELD_NAMESPACE_NOT_FROZEN",
        ),
    ),
    ContractAmbiguity(
        ambiguity_id="M0-AMB-06",
        title="Derivation class INFERRED is not mapped to a provenance origin",
        detail=(
            "A4/D2 names three derivation classes (OBSERVED, COMPUTED, INFERRED) and caps INFERRED at "
            "0.70, but never states that AI output is INFERRED. There is no stated ceiling for "
            "model-derived output."
        ),
        impact="Determines the confidence validator applied to every AI finding.",
        current_handling=(
            "ai_assisted is treated as INFERRED and capped at 0.70, which is the conservative "
            "reading and consistent with A4's never-inflate rule."
        ),
        resolution="Resolved by M0-DEC-03.",
        blocking=False,
        recorded_in=("app.contract.assumptions.CONFIDENCE_CEILINGS",),
    ),
    ContractAmbiguity(
        ambiguity_id="M0-AMB-07",
        title="The frozen FragmentInstanceId is not expressible by the EvidenceRef pattern",
        detail=(
            "The fragment-ID amendment freezes FragmentInstanceId as "
            "FRG-<16 lowercase hex>-<start>-<end> with digits{1,10} in both numeric positions, "
            "and freezes that every EvidenceRef must resolve to exactly one record. The "
            "normative EvidenceRef pattern (M0-DEC-01) requires an instance identifier of the "
            "form [A-Z]{2,6}(-[A-Z0-9]{1,12})*-\\d{2,10}: it admits no lowercase-hex segment and "
            "no second numeric suffix, so fragments[FRG-0123456789abcdef-0-4096] is rejected by "
            "the only normative validator (verified by execution). As written, the two frozen "
            "statements cannot both hold."
        ),
        impact=(
            "A fragment EvidenceRef cannot be written in a form the normative validator "
            "accepts, so it always resolves to evidence_ref_syntax_invalid and the amendment's "
            "every-EvidenceRef-resolves requirement cannot be met for the fragments collection."
        ),
        current_handling=(
            "Closed by the frozen Option A amendment (M0-DEC-06): the fragments slot of the "
            "single normative EvidenceRef pattern was widened to admit "
            "fragments[FRG-<16 lowercase hex>-<start>-<end>] as an alternative, so the "
            "identifier IS now expressible and no second EvidenceRef syntax exists. "
            "Exactly-one-record grounding against the supplied bundle lives in "
            "app.services.evidence, and both the widening and the grounding rule are "
            "asserted by api/tests/test_fragment_id.py, api/tests/test_contract_evidence_ref.py "
            "and api/tests/test_evidence.py."
        ),
        resolution=(
            "Resolved by M0-DEC-06. The frozen Option A amendment widened the fragments "
            "instance-ID slot inside the single normative pattern."
        ),
        blocking=False,
        recorded_in=(
            "app.contract.fragment_id.FRAGMENT_ID_PATTERN",
            "app.contract.evidence_ref.EVIDENCE_REF_PATTERN",
        ),
    ),
    ContractAmbiguity(
        ambiguity_id="M0-AMB-08",
        title="The fragment digest encoding, the 16-hex derivation and the digits spelling are not frozen",
        detail=(
            "The amendment states that bytes_sha256 is the full SHA-256 digest of fragment "
            "content and that the identifier carries 16 lowercase hex characters, but it never "
            "states the digest's textual encoding (hex case, or a prefix encoding), never states "
            "that the identifier's 16 characters are the digest's first 16 characters, and never "
            "states a canonical spelling for digits{1,10}, which admits leading zeros such as "
            "FRG-0123456789abcdef-007-4096."
        ),
        impact=(
            "Two producers can build different but syntactically valid identifiers for the same "
            "fragment, which would break the frozen uniqueness and identity semantics without any "
            "validator being able to detect it."
        ),
        current_handling=(
            "bytes_sha256 is accepted as exactly 64 hexadecimal characters in either case; the "
            "identifier's own 16 characters must be lowercase, which IS frozen. The single "
            "constructor fragment_instance_id_from_content derives those 16 characters as the "
            "first 16 characters of the lowercased digest, and validation never requires that "
            "derivation. An identifier is never rewritten or normalised: the supplied string is "
            "preserved, and FragmentIdIndex refuses to register two identifiers that denote the "
            "same source occurrence."
        ),
        resolution=None,
        blocking=False,
        recorded_in=(
            "app.contract.fragment_id.fragment_instance_id_from_content",
            "app.contract.fragment_id.FragmentIdIndex",
        ),
    ),
)

AMBIGUITY_IDS: tuple[str, ...] = tuple(
    ambiguity.ambiguity_id for ambiguity in AMBIGUITIES
)

#: Gaps that currently prevent a frozen requirement from being met. Each one needs a team
#: decision before it can be closed; none of them is closed by invention.
BLOCKING_AMBIGUITIES: tuple[ContractAmbiguity, ...] = tuple(
    ambiguity for ambiguity in AMBIGUITIES if ambiguity.blocking
)