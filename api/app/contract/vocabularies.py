"""Frozen M0 vocabularies.

Every value in this module is transcribed verbatim from the M0 contract-freeze
material. Nothing here is renamed, merged, aliased or expanded.

D-5 decision (authorized): ``ArtifactKind`` is supplied by the M0 material only as
*examples*, so it is exposed as a frozen constant and is NOT a validating enum. It is
also never inferred from ArtifactLabel, because no label-to-kind mapping is frozen.
"""
from __future__ import annotations

from enum import Enum
from typing import Final

# ---------------------------------------------------------------------------------
# ArtifactLabel - exactly 21 values, in the order supplied by the M0 material.
# ---------------------------------------------------------------------------------
ARTIFACT_LABEL_VALUES: Final[tuple[str, ...]] = (
    "image/jpeg",
    "image/png",
    "image/gif",
    "video/mp4",
    "audio/mpeg",
    "application/pdf",
    "application/zip",
    "application/x-7z",
    "application/x-sqlite3",
    "application/json",
    "text/plain",
    "text/csv",
    "text/xml",
    "message/rfc822",
    "application/x-executable",
    "application/x-elf",
    "application/x-pe",
    "application/octet-stream",
    "cryptographic_container",
    "filesystem_metadata",
    "unknown",
)


class ArtifactLabel(str, Enum):
    """Frozen ArtifactLabel vocabulary: exactly 21 values.

    These values are MIME-flavoured strings but are NOT validated as registered MIME
    types: five of them (see ``UNOFFICIAL_X_LABELS``) are unofficial, and three are not
    MIME-shaped at all. The M0 material freezes the value set, not a MIME conformance
    rule, so no such rule is applied here.
    """

    IMAGE_JPEG = "image/jpeg"
    IMAGE_PNG = "image/png"
    IMAGE_GIF = "image/gif"
    VIDEO_MP4 = "video/mp4"
    AUDIO_MPEG = "audio/mpeg"
    APPLICATION_PDF = "application/pdf"
    APPLICATION_ZIP = "application/zip"
    APPLICATION_X_7Z = "application/x-7z"
    APPLICATION_X_SQLITE3 = "application/x-sqlite3"
    APPLICATION_JSON = "application/json"
    TEXT_PLAIN = "text/plain"
    TEXT_CSV = "text/csv"
    TEXT_XML = "text/xml"
    MESSAGE_RFC822 = "message/rfc822"
    APPLICATION_X_EXECUTABLE = "application/x-executable"
    APPLICATION_X_ELF = "application/x-elf"
    APPLICATION_X_PE = "application/x-pe"
    APPLICATION_OCTET_STREAM = "application/octet-stream"
    CRYPTOGRAPHIC_CONTAINER = "cryptographic_container"
    FILESYSTEM_METADATA = "filesystem_metadata"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------------
# ArtifactFamily - the 13 frozen family values supplied by the team.
# ---------------------------------------------------------------------------------
ARTIFACT_FAMILY_VALUES: Final[tuple[str, ...]] = (
    "image",
    "video",
    "audio",
    "document",
    "archive",
    "database",
    "executable",
    "log",
    "text",
    "email",
    "cryptographic_container",
    "filesystem_metadata",
    "unknown",
)


class ArtifactFamily(str, Enum):
    """Frozen ArtifactFamily vocabulary: exactly 13 values."""

    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    ARCHIVE = "archive"
    DATABASE = "database"
    EXECUTABLE = "executable"
    LOG = "log"
    TEXT = "text"
    EMAIL = "email"
    CRYPTOGRAPHIC_CONTAINER = "cryptographic_container"
    FILESYSTEM_METADATA = "filesystem_metadata"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------------
# ArtifactKind - supplied as EXAMPLES (D-5). Frozen constant, not a validating enum.
# ---------------------------------------------------------------------------------
ARTIFACT_KIND_EXAMPLES: Final[tuple[str, ...]] = (
    "jpeg",
    "png",
    "gif",
    "mp4",
    "mpeg",
    "pdf",
    "zip",
    "sevenzip",
    "sqlite3",
    "json",
    "csv",
    "xml",
    "txt",
    "eml",
    "elf",
    "pe",
    "crypto_container",
    "unknown",
)

#: D-5: the supplied kind vocabulary is a documented example list, not a closed set.
ARTIFACT_KIND_IS_VALIDATING_ENUM: Final[bool] = False

#: No label -> kind mapping is frozen, so none is derived.
LABEL_TO_KIND_MAPPING_IS_FROZEN: Final[bool] = False

#: No label -> family mapping is frozen, so none is derived.
LABEL_TO_FAMILY_MAPPING_IS_FROZEN: Final[bool] = False

#: No synonyms or aliases are permitted for the frozen label values.
ARTIFACT_LABEL_ALIASES_ALLOWED: Final[bool] = False

#: Labels that are NOT MIME-shaped at all.
NON_MIME_LABELS: Final[tuple[str, ...]] = (
    "cryptographic_container",
    "filesystem_metadata",
    "unknown",
)

#: Labels that use the unofficial ``x-`` (unregistered) MIME form.
UNOFFICIAL_X_LABELS: Final[tuple[str, ...]] = (
    "application/x-7z",
    "application/x-sqlite3",
    "application/x-executable",
    "application/x-elf",
    "application/x-pe",
)


def is_valid_artifact_label(value: str) -> bool:
    """True only for an exact, case-sensitive member of the 21 frozen values."""
    return value in ARTIFACT_LABEL_VALUES


def is_valid_artifact_family(value: str) -> bool:
    """True only for an exact, case-sensitive member of the 13 frozen values."""
    return value in ARTIFACT_FAMILY_VALUES


def is_documented_artifact_kind(value: str) -> bool:
    """True when ``value`` appears in the supplied ArtifactKind *examples*.

    Deliberately non-validating (D-5): a False result does not mean the value is
    invalid, only that it is not one of the documented examples. The API never rejects
    a kind on this basis.
    """
    return value in ARTIFACT_KIND_EXAMPLES