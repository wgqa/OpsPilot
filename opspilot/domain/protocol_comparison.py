"""Protocol Knowledge Version Comparison Domain Module.

Independent vertical slice for AR-03-01 (with HF01 enhancements).
Reads versioned protocol documents by verified references from trusted catalogs,
performs deterministic structural difference comparison, produces traceable evidence,
and enforces epistemic boundaries (documents cannot prove live deployment state).

Document content is treated as untrusted data, never as system instructions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Sequence

from opspilot.config import ROOT
from opspilot.domain.d2 import canonical_json, digest_json, utc_now

# Default trusted catalog directories
DEFAULT_CATALOG_DIRS: tuple[Path, ...] = (
    ROOT / "knowledge" / "async-callback",
    ROOT / "knowledge" / "api-scope",
)

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")

_NEGATIVE_OR_HISTORICAL_PATTERN = re.compile(
    r"\b(historically|historical|legacy|older drafts?|example(?:\s+of)?|not(?:\s+yet)?|never adopted|deprecated|obsolete|do not infer)\b",
    re.IGNORECASE,
)


class ProtocolComparisonError(RuntimeError):
    """Base error for protocol comparison."""

    def __init__(self, message: str, reason_code: str | None = None):
        super().__init__(message)
        self.reason_code = reason_code or "PROTOCOL_COMPARISON_ERROR"


class InvalidReferenceError(ProtocolComparisonError):
    """Document reference is missing, None, or structurally invalid."""

    def __init__(self, message: str):
        super().__init__(message, reason_code="MISSING_OR_INVALID_REFERENCE")


class DocumentNotFoundError(ProtocolComparisonError):
    """Document reference could not be found in trusted catalogs."""

    def __init__(self, message: str):
        super().__init__(message, reason_code="DOCUMENT_NOT_FOUND")


class DocumentSourceMismatchError(ProtocolComparisonError):
    """Document reference source does not match trusted catalog source."""

    def __init__(self, message: str):
        super().__init__(message, reason_code="DOCUMENT_SOURCE_MISMATCH")


class DocumentIntegrityError(ProtocolComparisonError):
    """Document digest mismatch or content tampering detected."""

    def __init__(self, message: str):
        super().__init__(message, reason_code="DOCUMENT_DIGEST_MISMATCH")


class DocumentExpiredError(ProtocolComparisonError):
    """Document is expired, premature, or marked inactive."""

    def __init__(self, message: str):
        super().__init__(message, reason_code="DOCUMENT_EXPIRED")


@dataclass(frozen=True)
class DocumentRef:
    """Immutable reference to a versioned protocol specification document."""

    document_id: str
    version: str
    digest: str
    source: str
    valid_from: str | None = None
    expires_at: str | None = None
    title: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "version": self.version,
            "digest": self.digest,
            "source": self.source,
            "valid_from": self.valid_from,
            "expires_at": self.expires_at,
            "title": self.title,
        }

    @classmethod
    def from_dict(cls, data: Any) -> DocumentRef:
        if not isinstance(data, dict):
            raise InvalidReferenceError(f"Expected reference dict, got {type(data).__name__}")
        document_id = data.get("document_id")
        version = data.get("version")
        digest = data.get("digest")
        source = data.get("source")
        if not (isinstance(document_id, str) and document_id.strip()):
            raise InvalidReferenceError("Document reference missing valid 'document_id'")
        if not (isinstance(version, str) and version.strip()):
            raise InvalidReferenceError("Document reference missing valid 'version'")
        if not (isinstance(digest, str) and _SHA256_HEX.fullmatch(digest)):
            raise InvalidReferenceError("Document reference missing valid 64-char hex 'digest'")
        if not (isinstance(source, str) and source.strip()):
            raise InvalidReferenceError("Document reference missing valid 'source'")
        return cls(
            document_id=document_id.strip(),
            version=version.strip(),
            digest=digest.strip(),
            source=source.strip(),
            valid_from=str(data["valid_from"]) if data.get("valid_from") else None,
            expires_at=str(data["expires_at"]) if data.get("expires_at") else None,
            title=str(data["title"]) if data.get("title") else None,
        )


@dataclass(frozen=True)
class ResolvedDocument:
    """A verified document retrieved from trusted catalog with content and metadata."""

    document_id: str
    version: str
    digest: str
    source: str
    valid_from: str
    expires_at: str | None
    title: str
    file_path: Path
    content: str
    contract_versions: list[int]
    active: bool
    applicable: bool

    def to_ref(self) -> DocumentRef:
        return DocumentRef(
            document_id=self.document_id,
            version=self.version,
            digest=self.digest,
            source=self.source,
            valid_from=self.valid_from,
            expires_at=self.expires_at,
            title=self.title,
        )


@dataclass(frozen=True)
class MarkdownSection:
    """Represents a discrete heading-delimited section, preserving duplicate titles."""

    section_index: int
    title: str
    occurrence: int
    start_line: int
    end_line: int
    text: str

    @property
    def key(self) -> tuple[str, int]:
        return (self.title, self.occurrence)

    @property
    def display_title(self) -> str:
        if self.occurrence == 1:
            return self.title
        return f"{self.title} (#{self.occurrence})"


@dataclass(frozen=True)
class DiffEvidence:
    """Verifiable, cryptographically anchored excerpt evidence for a difference."""

    evidence_id: str
    diff_type: str
    base_doc_id: str
    base_version: str
    base_location: str
    base_excerpt: str
    base_excerpt_digest: str
    target_doc_id: str
    target_version: str
    target_location: str
    target_excerpt: str
    target_excerpt_digest: str
    traceability: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProtocolDifference:
    """Structured description of a protocol difference."""

    difference_id: str
    category: str
    title: str
    description: str
    base_location: str
    target_location: str
    evidence_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProtocolComparisonResult:
    """Complete structured comparison result between two protocol versions."""

    base_ref: dict[str, Any]
    target_ref: dict[str, Any]
    identical: bool
    summary: str
    diff_count: int
    differences: list[dict[str, Any]]
    diff_evidence: list[dict[str, Any]]
    unconfirmed_aspects: list[str]
    deployment_version_verified: bool = False
    authority: str = "DOCUMENTED_SPECIFICATION_ONLY_NOT_LIVE_DEPLOYMENT_EVIDENCE"
    compared_at: str = field(default_factory=utc_now)
    comparison_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_ref": self.base_ref,
            "target_ref": self.target_ref,
            "identical": self.identical,
            "summary": self.summary,
            "diff_count": self.diff_count,
            "differences": self.differences,
            "diff_evidence": self.diff_evidence,
            "unconfirmed_aspects": self.unconfirmed_aspects,
            "deployment_version_verified": self.deployment_version_verified,
            "authority": self.authority,
            "compared_at": self.compared_at,
            "comparison_digest": self.comparison_digest,
        }


def _parse_iso_utc(date_str: str) -> datetime:
    """Parse ISO date or datetime string into a UTC-aware datetime."""
    clean = date_str.strip()
    if clean.endswith("Z"):
        clean = clean[:-1] + "+00:00"
    dt = datetime.fromisoformat(clean)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _ensure_catalog_dirs(catalog_dirs: Sequence[Path | str] | None) -> list[Path]:
    if catalog_dirs is None:
        return [p.resolve() for p in DEFAULT_CATALOG_DIRS]
    return [Path(p).resolve() for p in catalog_dirs]


def _find_catalog_entry(
    document_id: str,
    version: str,
    catalog_dirs: list[Path],
) -> tuple[dict[str, Any], Path, Path]:
    """Find document entry in catalog manifests. Returns (entry_dict, catalog_dir, manifest_path)."""
    for catalog_dir in catalog_dirs:
        manifest_path = catalog_dir / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest_content = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(manifest_content, dict) or not isinstance(manifest_content.get("documents"), list):
            continue
        for entry in manifest_content["documents"]:
            if not isinstance(entry, dict):
                continue
            if entry.get("document_id") == document_id and entry.get("version") == version:
                return entry, catalog_dir, manifest_path
    raise DocumentNotFoundError(f"DOCUMENT_NOT_FOUND: No catalog entry found for document '{document_id}' v'{version}'")


def resolve_document(
    ref: dict[str, Any] | DocumentRef,
    *,
    catalog_dirs: Sequence[Path | str] | None = None,
    as_of: datetime | str | None = None,
    check_validity: bool = True,
    allow_inapplicable: bool = True,
) -> ResolvedDocument:
    """Resolve and verify a document reference against trusted catalog files.

    Performs:
    1. Reference structure validation
    2. Manifest lookup
    3. Source matching
    4. Path traversal safety
    5. Disk content SHA-256 vs manifest digest verification
    6. Disk content SHA-256 vs reference digest verification
    7. Validity period and active flag check
    8. UTF-8 decoding
    """
    if isinstance(ref, DocumentRef):
        doc_ref = ref
    else:
        doc_ref = DocumentRef.from_dict(ref)

    resolved_catalogs = _ensure_catalog_dirs(catalog_dirs)
    entry, catalog_dir, _ = _find_catalog_entry(doc_ref.document_id, doc_ref.version, resolved_catalogs)

    # 3. Source verification
    expected_source = entry.get("source")
    if doc_ref.source != expected_source:
        raise DocumentSourceMismatchError(
            f"DOCUMENT_SOURCE_MISMATCH: Reference specifies source '{doc_ref.source}', "
            f"but trusted catalog manifest specifies '{expected_source}' for '{doc_ref.document_id}'"
        )

    # 4. Path traversal safety
    filename = entry.get("file")
    if not isinstance(filename, str) or Path(filename).name != filename:
        raise DocumentIntegrityError(f"MALFORMED_CATALOG_FILE_ENTRY: Invalid filename '{filename}'")
    file_path = (catalog_dir / filename).resolve()
    if not file_path.is_file() or file_path.parent != catalog_dir:
        raise DocumentIntegrityError(f"PATH_TRAVERSAL_OR_MISSING_FILE: Document file '{filename}' invalid or missing")

    # 5. Read raw bytes and compute actual SHA-256
    try:
        raw_bytes = file_path.read_bytes()
    except OSError as err:
        raise DocumentIntegrityError(f"DOCUMENT_FILE_UNREADABLE: Could not read '{file_path}': {err}") from err

    actual_digest = hashlib.sha256(raw_bytes).hexdigest()
    manifest_digest = entry.get("digest")

    if actual_digest != manifest_digest:
        raise DocumentIntegrityError(
            f"DOCUMENT_DIGEST_MISMATCH: Actual file digest ({actual_digest}) does not match "
            f"manifest digest ({manifest_digest}) for '{doc_ref.document_id}'"
        )

    # 6. Verify against reference digest
    if actual_digest != doc_ref.digest:
        raise DocumentIntegrityError(
            f"DOCUMENT_DIGEST_MISMATCH: Actual file digest ({actual_digest}) does not match "
            f"reference digest ({doc_ref.digest}) for '{doc_ref.document_id}'"
        )

    # 7. Check active and validity
    is_active = entry.get("active", True)
    if is_active is False:
        raise DocumentExpiredError(f"DOCUMENT_EXPIRED: Document '{doc_ref.document_id}' is marked inactive in catalog")

    is_applicable = entry.get("applicable", True)
    if not allow_inapplicable and is_applicable is False:
        raise DocumentExpiredError(f"DOCUMENT_INAPPLICABLE: Document '{doc_ref.document_id}' is flagged as non-applicable/legacy")

    valid_from_str = entry.get("valid_from", "1970-01-01T00:00:00+00:00")
    expires_at_str = entry.get("expires_at")

    if check_validity:
        check_time: datetime
        if as_of is None:
            check_time = datetime.now(timezone.utc)
        elif isinstance(as_of, str):
            check_time = _parse_iso_utc(as_of)
        else:
            check_time = as_of if as_of.tzinfo is not None else as_of.replace(tzinfo=timezone.utc)

        valid_from_dt = _parse_iso_utc(valid_from_str)
        if check_time < valid_from_dt:
            raise DocumentExpiredError(
                f"DOCUMENT_EXPIRED: Document '{doc_ref.document_id}' is not yet valid (valid_from={valid_from_str}, check_time={check_time.isoformat()})"
            )

        if expires_at_str:
            expires_at_dt = _parse_iso_utc(expires_at_str)
            if check_time >= expires_at_dt:
                raise DocumentExpiredError(
                    f"DOCUMENT_EXPIRED: Document '{doc_ref.document_id}' expired at {expires_at_str} (check_time={check_time.isoformat()})"
                )

    # 8. Decode UTF-8
    try:
        content_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as err:
        raise DocumentIntegrityError(f"DOCUMENT_ENCODING_ERROR: Document '{file_path}' is not valid UTF-8: {err}") from err

    return ResolvedDocument(
        document_id=doc_ref.document_id,
        version=doc_ref.version,
        digest=actual_digest,
        source=doc_ref.source,
        valid_from=valid_from_str,
        expires_at=expires_at_str,
        title=entry.get("title", doc_ref.document_id),
        file_path=file_path,
        content=content_text,
        contract_versions=list(entry.get("contract_versions", [1])),
        active=bool(is_active),
        applicable=bool(is_applicable),
    )


def _split_markdown_sections(text: str) -> list[MarkdownSection]:
    """Parse markdown text into sections by heading, tracking occurrences to avoid collisions."""
    lines = text.splitlines()
    if not lines:
        return [MarkdownSection(section_index=0, title="Root", occurrence=1, start_line=1, end_line=1, text="")]

    sections: list[MarkdownSection] = []
    current_title = "Root"
    current_start = 1
    current_lines: list[str] = []
    title_counts: dict[str, int] = {}
    sec_idx = 0

    def _flush_section(end_line: int) -> None:
        nonlocal sec_idx
        trimmed_lines = list(current_lines)
        while trimmed_lines and not trimmed_lines[-1].strip():
            trimmed_lines.pop()
        title_counts[current_title] = title_counts.get(current_title, 0) + 1
        occ = title_counts[current_title]
        sec_text = "\n".join(trimmed_lines)
        sections.append(
            MarkdownSection(
                section_index=sec_idx,
                title=current_title,
                occurrence=occ,
                start_line=current_start,
                end_line=end_line,
                text=sec_text,
            )
        )
        sec_idx += 1

    for idx, line in enumerate(lines, start=1):
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            if current_lines or current_title != "Root":
                _flush_section(idx - 1)
            current_title = heading_match.group(2).strip()
            current_start = idx
            current_lines = [line]
        else:
            current_lines.append(line)

    _flush_section(len(lines))
    return sections


def _truncate_around_span(
    text: str,
    span_start: int,
    span_end: int,
    *,
    max_len: int = 600,
    had_prior_left: bool = False,
    had_prior_right: bool = False,
) -> tuple[str, bool]:
    """Window text to at most max_len characters centered around [span_start, span_end].

    Maintains [truncated] markers and ensures changed spans are preserved in excerpts.
    """
    if len(text) <= max_len and not had_prior_left and not had_prior_right:
        return text, False

    budget = max_len - 14
    span_len = max(1, span_end - span_start)

    if len(text) <= budget:
        slice_start = 0
        slice_end = len(text)
    elif span_len >= budget:
        slice_start = span_start
        slice_end = min(len(text), span_start + budget)
    else:
        avail = budget - span_len
        left_avail = avail // 2
        right_avail = avail - left_avail
        slice_start = span_start - left_avail
        slice_end = span_end + right_avail
        if slice_start < 0:
            slice_end += (0 - slice_start)
            slice_start = 0
        if slice_end > len(text):
            excess = slice_end - len(text)
            slice_start = max(0, slice_start - excess)
            slice_end = len(text)

    is_left = had_prior_left or (slice_start > 0)
    is_right = had_prior_right or (slice_end < len(text))

    parts: list[str] = []
    if is_left:
        parts.append("[...] ")
    parts.append(text[slice_start:slice_end])
    if is_right:
        parts.append(" [...]")

    final_str = "".join(parts)
    return final_str, (is_left or is_right)


def _extract_diff_excerpt(
    b_start_line: int,
    b_end_line: int,
    t_start_line: int,
    t_end_line: int,
    b_text: str,
    t_text: str,
    *,
    max_chars: int = 600,
    context_lines: int = 2,
) -> tuple[str, str, str, str, bool]:
    """Extract excerpt window focused on actual changed content between b_text and t_text.

    Supports both multi-line documents and long single-line sections, providing
    independent line location tracking for base and target.

    Returns:
        (base_excerpt, target_excerpt, base_loc_str, target_loc_str, is_truncated)
    """
    b_lines = b_text.splitlines()
    t_lines = t_text.splitlines()

    # Case A: section added in target
    if not b_text:
        base_excerpt = ""
        base_loc_str = "ABSENT"
        if len(t_text) <= max_chars:
            target_excerpt = t_text
            target_loc_str = f"Lines {t_start_line}-{t_end_line}"
            is_trunc = False
        else:
            target_excerpt = t_text[:max_chars - 7] + " [...]"
            target_loc_str = f"Lines {t_start_line}-{t_start_line + len(target_excerpt.splitlines()) - 1} [truncated] (section L{t_start_line}-L{t_end_line})"
            is_trunc = True
        return base_excerpt, target_excerpt, base_loc_str, target_loc_str, is_trunc

    # Case B: section removed in target
    if not t_text:
        target_excerpt = ""
        target_loc_str = "OMITTED"
        if len(b_text) <= max_chars:
            base_excerpt = b_text
            base_loc_str = f"Lines {b_start_line}-{b_end_line}"
            is_trunc = False
        else:
            base_excerpt = b_text[:max_chars - 7] + " [...]"
            base_loc_str = f"Lines {b_start_line}-{b_start_line + len(base_excerpt.splitlines()) - 1} [truncated] (section L{b_start_line}-L{b_end_line})"
            is_trunc = True
        return base_excerpt, target_excerpt, base_loc_str, target_loc_str, is_trunc

    # Case C: section present in both with differences
    # C.1 Both fit completely within max_chars
    if len(b_text) <= max_chars and len(t_text) <= max_chars:
        b_loc = f"Lines {b_start_line}-{b_end_line}" if b_lines else "Lines 1-1"
        t_loc = f"Lines {t_start_line}-{t_end_line}" if t_lines else "Lines 1-1"
        return b_text, t_text, b_loc, t_loc, False

    # Line-level diff
    matcher = difflib.SequenceMatcher(None, b_lines, t_lines)
    opcodes = matcher.get_opcodes()
    changed_ops = [op for op in opcodes if op[0] != "equal"]

    if not changed_ops:
        b_loc = f"Lines {b_start_line}-{b_end_line}"
        t_loc = f"Lines {t_start_line}-{t_end_line}"
        b_trunc, b_tr = _truncate_around_span(b_text, 0, len(b_text), max_len=max_chars)
        t_trunc, t_tr = _truncate_around_span(t_text, 0, len(t_text), max_len=max_chars)
        return b_trunc, t_trunc, b_loc, t_loc, (b_tr or t_tr)

    b_ch_start = min(op[1] for op in changed_ops)
    b_ch_end = max(op[2] for op in changed_ops)
    t_ch_start = min(op[3] for op in changed_ops)
    t_ch_end = max(op[4] for op in changed_ops)

    # Base line window
    b_win_start = max(0, b_ch_start - context_lines)
    b_win_end = min(len(b_lines), b_ch_end + context_lines)
    b_sub_text = "\n".join(b_lines[b_win_start:b_win_end])
    b_had_line_trunc_left = (b_win_start > 0)
    b_had_line_trunc_right = (b_win_end < len(b_lines))

    # Target line window
    t_win_start = max(0, t_ch_start - context_lines)
    t_win_end = min(len(t_lines), t_ch_end + context_lines)
    t_sub_text = "\n".join(t_lines[t_win_start:t_win_end])
    t_had_line_trunc_left = (t_win_start > 0)
    t_had_line_trunc_right = (t_win_end < len(t_lines))

    # Character-level diff within the extracted sub-texts
    char_matcher = difflib.SequenceMatcher(None, b_sub_text, t_sub_text)
    char_ops = [op for op in char_matcher.get_opcodes() if op[0] != "equal"]

    if char_ops:
        b_diff_start = min(op[1] for op in char_ops)
        b_diff_end = max(op[2] for op in char_ops)
        t_diff_start = min(op[3] for op in char_ops)
        t_diff_end = max(op[4] for op in char_ops)
    else:
        b_diff_start = 0
        b_diff_end = len(b_sub_text)
        t_diff_start = 0
        t_diff_end = len(t_sub_text)

    b_final_text, b_is_trunc = _truncate_around_span(
        b_sub_text,
        b_diff_start,
        b_diff_end,
        max_len=max_chars,
        had_prior_left=b_had_line_trunc_left,
        had_prior_right=b_had_line_trunc_right,
    )
    t_final_text, t_is_trunc = _truncate_around_span(
        t_sub_text,
        t_diff_start,
        t_diff_end,
        max_len=max_chars,
        had_prior_left=t_had_line_trunc_left,
        had_prior_right=t_had_line_trunc_right,
    )

    b_abs_start = b_start_line + b_win_start
    b_abs_end = b_start_line + max(b_win_start, b_win_end - 1)
    b_loc_desc = f"Lines {b_abs_start}-{b_abs_end}"
    if b_is_trunc:
        b_loc_desc += f" (section L{b_start_line}-L{b_end_line})"

    t_abs_start = t_start_line + t_win_start
    t_abs_end = t_start_line + max(t_win_start, t_win_end - 1)
    t_loc_desc = f"Lines {t_abs_start}-{t_abs_end}"
    if t_is_trunc:
        t_loc_desc += f" (section L{t_start_line}-L{t_end_line})"

    return b_final_text, t_final_text, b_loc_desc, t_loc_desc, (b_is_trunc or t_is_trunc)


def _extract_protocol_features(text: str) -> dict[str, set[str]]:
    """Extract candidate lexical cues while respecting negative and historical contexts.

    Lexical hits serve purely as candidate search hints for investigation; they
    never constitute proof of runtime protocol rule adoption or online deployment behavior.
    """
    status_codes = set(re.findall(r"\b([1-5]\d\d)\b", text))
    known_parameters = {
        "processing_sla_seconds", "event_id", "delivery_version", "attempt_count",
        "max_attempts", "order_version", "order_id", "missing_scopes", "required_scopes", "granted_scopes"
    }

    sentences = re.split(r"[.!?\n;]+", text)
    found_params: set[str] = set()
    candidate_directives: set[str] = set()

    for sentence in sentences:
        s_clean = sentence.strip()
        if not s_clean:
            continue

        is_negated_or_historical = bool(_NEGATIVE_OR_HISTORICAL_PATTERN.search(s_clean))

        # Parameter references
        for param in known_parameters:
            if param in s_clean:
                if not is_negated_or_historical:
                    found_params.add(param)

        # Behavioral cues
        if "never resend" in s_clean.lower() and not is_negated_or_historical:
            candidate_directives.add("PROHIBIT_AUTO_RESEND")
        if ("asynchronous" in s_clean.lower() or "async" in s_clean.lower()) and not is_negated_or_historical:
            candidate_directives.add("ASYNC_PUBLICATION")
        if re.search(r"not(?:.*?)(?:prove|mean)(?:.*?)completed", s_clean, re.IGNORECASE) and not is_negated_or_historical:
            candidate_directives.add("ACCEPTANCE_NOT_COMPLETION")

    return {
        "status_codes": status_codes,
        "parameters": found_params,
        "candidate_directives": candidate_directives,
    }


def _digest_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compare_protocol_versions(
    base_ref: dict[str, Any] | DocumentRef,
    target_ref: dict[str, Any] | DocumentRef,
    *,
    catalog_dirs: Sequence[Path | str] | None = None,
    as_of: datetime | str | None = None,
    check_validity: bool = True,
    allow_inapplicable: bool = True,
) -> ProtocolComparisonResult:
    """Compare two protocol versions using verified references from trusted catalogs.

    Produces structural differences, verifiable excerpt evidence, and maintains
    firm epistemic boundaries (cannot prove live deployment state).
    """
    resolved_base = resolve_document(
        base_ref,
        catalog_dirs=catalog_dirs,
        as_of=as_of,
        check_validity=check_validity,
        allow_inapplicable=allow_inapplicable,
    )
    resolved_target = resolve_document(
        target_ref,
        catalog_dirs=catalog_dirs,
        as_of=as_of,
        check_validity=check_validity,
        allow_inapplicable=allow_inapplicable,
    )

    base_ref_dict = resolved_base.to_ref().to_dict()
    target_ref_dict = resolved_target.to_ref().to_dict()

    # Epistemic boundary constraints
    unconfirmed_aspects = [
        "LIVE_DEPLOYMENT_VERSION_UNVERIFIED: Static protocol documents describe specifications only. "
        "They cannot prove which version is actually running in production/cluster environments without live probing.",
        "RUNTIME_CONSUMER_READINESS_UNVERIFIED: Cannot determine whether live callers, queues, or consumers "
        "have adopted this target contract version without runtime observation.",
        "HISTORICAL_SPECIFICATION_BOUNDARY: Comparison reflects documented specifications as authored; "
        "runtime bug fixes or unannounced gateway routing behaviors are not verified by document text.",
    ]
    if not resolved_base.applicable or not resolved_target.applicable:
        unconfirmed_aspects.append(
            "LEGACY_OR_INAPPLICABLE_SPECIFICATION: One or more compared versions are flagged as non-applicable "
            "or legacy for current production operations."
        )

    # 1. Identical check
    if resolved_base.digest == resolved_target.digest and resolved_base.content == resolved_target.content:
        summary = (
            f"Document versions are identical in content and digest ({resolved_base.digest[:12]}...). "
            f"Both refer to '{resolved_base.title}' v{resolved_base.version}."
        )
        res_data = {
            "base_digest": resolved_base.digest,
            "target_digest": resolved_target.digest,
            "identical": True,
            "diff_count": 0,
        }
        return ProtocolComparisonResult(
            base_ref=base_ref_dict,
            target_ref=target_ref_dict,
            identical=True,
            summary=summary,
            diff_count=0,
            differences=[],
            diff_evidence=[],
            unconfirmed_aspects=unconfirmed_aspects,
            deployment_version_verified=False,
            comparison_digest=digest_json(res_data),
        )

    # 2. Structural and feature comparison (duplicate-heading safe)
    base_sections = _split_markdown_sections(resolved_base.content)
    target_sections = _split_markdown_sections(resolved_target.content)

    base_map = {sec.key: sec for sec in base_sections}
    target_map = {sec.key: sec for sec in target_sections}

    all_keys = list(dict.fromkeys(list(base_map.keys()) + list(target_map.keys())))

    differences: list[dict[str, Any]] = []
    diff_evidence: list[dict[str, Any]] = []
    counter = 1

    for key in all_keys:
        sec_title, sec_occ = key
        b_sec = base_map.get(key)
        t_sec = target_map.get(key)
        disp_title = b_sec.display_title if b_sec else (t_sec.display_title if t_sec else sec_title)

        if b_sec is not None and t_sec is None:
            # Section removed in target
            b_excerpt, t_excerpt, b_loc, t_loc, is_trunc = _extract_diff_excerpt(
                b_sec.start_line, b_sec.end_line, 0, 0, b_sec.text, ""
            )
            evidence_id = f"EVID-{counter:03d}"
            diff_id = f"DIFF-{counter:03d}"
            counter += 1

            evidence = DiffEvidence(
                evidence_id=evidence_id,
                diff_type="SECTION_REMOVED",
                base_doc_id=resolved_base.document_id,
                base_version=resolved_base.version,
                base_location=b_loc,
                base_excerpt=b_excerpt,
                base_excerpt_digest=_digest_text(b_excerpt),
                target_doc_id=resolved_target.document_id,
                target_version=resolved_target.version,
                target_location=t_loc,
                target_excerpt=t_excerpt,
                target_excerpt_digest=_digest_text(t_excerpt),
                traceability=f"Base section '{disp_title}' removed in target v{resolved_target.version}",
            )
            diff = ProtocolDifference(
                difference_id=diff_id,
                category="SECTION_STRUCTURE",
                title=f"Section removed: {disp_title}",
                description=f"Section '{disp_title}' present in v{resolved_base.version} is omitted in v{resolved_target.version}.",
                base_location=b_loc,
                target_location=t_loc,
                evidence_id=evidence_id,
            )
            differences.append(diff.to_dict())
            diff_evidence.append(evidence.to_dict())

        elif b_sec is None and t_sec is not None:
            # Section added in target
            b_excerpt, t_excerpt, b_loc, t_loc, is_trunc = _extract_diff_excerpt(
                0, 0, t_sec.start_line, t_sec.end_line, "", t_sec.text
            )
            evidence_id = f"EVID-{counter:03d}"
            diff_id = f"DIFF-{counter:03d}"
            counter += 1

            evidence = DiffEvidence(
                evidence_id=evidence_id,
                diff_type="SECTION_ADDED",
                base_doc_id=resolved_base.document_id,
                base_version=resolved_base.version,
                base_location=b_loc,
                base_excerpt=b_excerpt,
                base_excerpt_digest=_digest_text(b_excerpt),
                target_doc_id=resolved_target.document_id,
                target_version=resolved_target.version,
                target_location=t_loc,
                target_excerpt=t_excerpt,
                target_excerpt_digest=_digest_text(t_excerpt),
                traceability=f"Target section '{disp_title}' added in v{resolved_target.version}",
            )
            diff = ProtocolDifference(
                difference_id=diff_id,
                category="SECTION_STRUCTURE",
                title=f"Section added: {disp_title}",
                description=f"New section '{disp_title}' introduced in v{resolved_target.version}.",
                base_location=b_loc,
                target_location=t_loc,
                evidence_id=evidence_id,
            )
            differences.append(diff.to_dict())
            diff_evidence.append(evidence.to_dict())

        elif b_sec is not None and t_sec is not None:
            # Present in both: check text difference
            if b_sec.text != t_sec.text:
                b_excerpt, t_excerpt, b_loc, t_loc, is_trunc = _extract_diff_excerpt(
                    b_sec.start_line, b_sec.end_line, t_sec.start_line, t_sec.end_line, b_sec.text, t_sec.text
                )
                evidence_id = f"EVID-{counter:03d}"
                diff_id = f"DIFF-{counter:03d}"
                counter += 1

                b_features = _extract_protocol_features(b_sec.text)
                t_features = _extract_protocol_features(t_sec.text)

                candidate_param_additions = t_features["parameters"] - b_features["parameters"]
                candidate_directive_additions = t_features["candidate_directives"] - b_features["candidate_directives"]

                lexical_cues: list[str] = []
                if candidate_param_additions:
                    lexical_cues.append(f"parameters: {', '.join(sorted(candidate_param_additions))}")
                if candidate_directive_additions:
                    lexical_cues.append(f"candidate behavioral cues: {', '.join(sorted(candidate_directive_additions))}")

                if lexical_cues:
                    detail_desc = (
                        f"Section '{disp_title}' content modified. Changes include candidate "
                        f"{'; '.join(lexical_cues)} (advisory lexical hint; does not prove runtime rule adoption)."
                    )
                else:
                    detail_desc = f"Section '{disp_title}' text formulation updated between versions without keyword trigger."

                evidence = DiffEvidence(
                    evidence_id=evidence_id,
                    diff_type="SECTION_MODIFIED",
                    base_doc_id=resolved_base.document_id,
                    base_version=resolved_base.version,
                    base_location=b_loc,
                    base_excerpt=b_excerpt,
                    base_excerpt_digest=_digest_text(b_excerpt),
                    target_doc_id=resolved_target.document_id,
                    target_version=resolved_target.version,
                    target_location=t_loc,
                    target_excerpt=t_excerpt,
                    target_excerpt_digest=_digest_text(t_excerpt),
                    traceability=f"Content difference verified in section '{disp_title}' between v{resolved_base.version} and v{resolved_target.version}",
                )
                diff = ProtocolDifference(
                    difference_id=diff_id,
                    category="TEXT_DIFFERENCE",
                    title=f"Section modified: {disp_title}",
                    description=detail_desc,
                    base_location=b_loc,
                    target_location=t_loc,
                    evidence_id=evidence_id,
                )
                differences.append(diff.to_dict())
                diff_evidence.append(evidence.to_dict())

    # Document-level candidate lexical summary
    base_full_feats = _extract_protocol_features(resolved_base.content)
    target_full_feats = _extract_protocol_features(resolved_target.content)

    summary_parts: list[str] = [
        f"Compared {resolved_base.document_id} (v{resolved_base.version}) with "
        f"{resolved_target.document_id} (v{resolved_target.version}): "
        f"{len(differences)} structural differences detected."
    ]

    all_added_params = target_full_feats["parameters"] - base_full_feats["parameters"]
    all_added_directives = target_full_feats["candidate_directives"] - base_full_feats["candidate_directives"]

    cues_detected: list[str] = []
    if all_added_params:
        cues_detected.append(f"parameters: {', '.join(sorted(all_added_params))}")
    if all_added_directives:
        cues_detected.append(f"behavioral cues: {', '.join(sorted(all_added_directives))}")

    if cues_detected:
        summary_parts.append(
            f"Candidate lexical cues detected in target text ({'; '.join(cues_detected)}). "
            f"Notice: Lexical keywords serve as investigation cues only; protocol semantics and runtime adoption must be verified via context and live telemetry."
        )

    summary_text = " ".join(summary_parts)

    res_data = {
        "base_digest": resolved_base.digest,
        "target_digest": resolved_target.digest,
        "identical": False,
        "diff_count": len(differences),
        "differences": differences,
    }

    return ProtocolComparisonResult(
        base_ref=base_ref_dict,
        target_ref=target_ref_dict,
        identical=False,
        summary=summary_text,
        diff_count=len(differences),
        differences=differences,
        diff_evidence=diff_evidence,
        unconfirmed_aspects=unconfirmed_aspects,
        deployment_version_verified=False,
        comparison_digest=digest_json(res_data),
    )


def compare_protocols_safe(
    base_ref: Any,
    target_ref: Any,
    *,
    catalog_dirs: Sequence[Path | str] | None = None,
    as_of: datetime | str | None = None,
    check_validity: bool = True,
    allow_inapplicable: bool = True,
) -> dict[str, Any]:
    """Safe wrapper returning structured result dict or rejection dict without unhandled exceptions."""
    try:
        result = compare_protocol_versions(
            base_ref=base_ref,
            target_ref=target_ref,
            catalog_dirs=catalog_dirs,
            as_of=as_of,
            check_validity=check_validity,
            allow_inapplicable=allow_inapplicable,
        )
        return {"status": "SUCCESS", **result.to_dict()}
    except ProtocolComparisonError as err:
        return {
            "status": "REJECTED",
            "reason_code": err.reason_code,
            "error_message": str(err),
            "deployment_version_verified": False,
            "authority": "DOCUMENTED_SPECIFICATION_ONLY_NOT_LIVE_DEPLOYMENT_EVIDENCE",
            "unconfirmed_aspects": [
                "LIVE_DEPLOYMENT_VERSION_UNVERIFIED: Comparison was rejected or could not complete; "
                "no live deployment state is verified."
            ],
            "diff_count": 0,
            "differences": [],
            "diff_evidence": [],
        }
    except Exception as err:
        return {
            "status": "ERROR",
            "reason_code": "INTERNAL_COMPARISON_ERROR",
            "error_message": f"Unexpected error during protocol comparison: {err}",
            "deployment_version_verified": False,
            "authority": "DOCUMENTED_SPECIFICATION_ONLY_NOT_LIVE_DEPLOYMENT_EVIDENCE",
            "unconfirmed_aspects": [
                "LIVE_DEPLOYMENT_VERSION_UNVERIFIED: Comparison encountered an internal error; "
                "no deployment inference is possible."
            ],
            "diff_count": 0,
            "differences": [],
            "diff_evidence": [],
        }
