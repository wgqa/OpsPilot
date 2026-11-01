"""Protocol Knowledge Version Comparison Domain Module.

Independent vertical slice for AR-03-01.
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
            # Match document_id and version (exact version match)
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


def _split_markdown_sections(text: str) -> dict[str, tuple[int, int, str]]:
    """Parse markdown text into sections by heading. Returns {heading_title: (start_line, end_line, body_text)}."""
    lines = text.splitlines()
    if not lines:
        return {"Root": (1, 1, "")}

    sections: dict[str, tuple[int, int, str]] = {}
    current_title = "Root"
    current_start = 1
    current_lines: list[str] = []

    for idx, line in enumerate(lines, start=1):
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            if current_lines or current_title != "Root":
                sections[current_title] = (current_start, idx - 1, "\n".join(current_lines))
            current_title = heading_match.group(2).strip()
            current_start = idx
            current_lines = [line]
        else:
            current_lines.append(line)

    sections[current_title] = (current_start, len(lines), "\n".join(current_lines))
    return sections


def _extract_protocol_features(text: str) -> dict[str, set[str]]:
    """Deterministically extract protocol-relevant indicators from untrusted document text.

    Text is treated purely as data strings; no execution or directive evaluation.
    """
    status_codes = set(re.findall(r"\b([1-5]\d\d)\b", text))
    known_states = {"COMPLETED", "PROCESSING", "QUEUED", "PROCESSED", "UNKNOWN", "RETRYABLE", "EXHAUSTED", "SCHEDULED"}
    found_states = {state for state in known_states if re.search(rf"\b{state}\b", text, re.IGNORECASE)}

    known_parameters = {
        "processing_sla_seconds", "event_id", "delivery_version", "attempt_count",
        "max_attempts", "order_version", "order_id", "missing_scopes", "required_scopes", "granted_scopes"
    }
    found_params = {param for param in known_parameters if param in text}

    behavior_restrictions = set()
    if re.search(r"never resend", text, re.IGNORECASE):
        behavior_restrictions.add("PROHIBIT_AUTO_RESEND")
    if re.search(r"not(?:.*?)(?:prove|mean)(?:.*?)completed", text, re.IGNORECASE):
        behavior_restrictions.add("ACCEPTANCE_NOT_COMPLETION")
    if re.search(r"asynchronous", text, re.IGNORECASE):
        behavior_restrictions.add("ASYNC_PUBLICATION")

    return {
        "status_codes": status_codes,
        "states": found_states,
        "parameters": found_params,
        "restrictions": behavior_restrictions,
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

    # 2. Structural and feature comparison
    base_sections = _split_markdown_sections(resolved_base.content)
    target_sections = _split_markdown_sections(resolved_target.content)

    differences: list[dict[str, Any]] = []
    diff_evidence: list[dict[str, Any]] = []
    counter = 1

    # Section-level diffs
    all_section_titles = list(dict.fromkeys(list(base_sections.keys()) + list(target_sections.keys())))

    for title in all_section_titles:
        in_base = title in base_sections
        in_target = title in target_sections

        if in_base and not in_target:
            start_l, end_l, text = base_sections[title]
            evidence_id = f"EVID-{counter:03d}"
            diff_id = f"DIFF-{counter:03d}"
            counter += 1

            evidence = DiffEvidence(
                evidence_id=evidence_id,
                diff_type="SECTION_REMOVED",
                base_doc_id=resolved_base.document_id,
                base_version=resolved_base.version,
                base_location=f"Lines {start_l}-{end_l}",
                base_excerpt=text[:500],
                base_excerpt_digest=_digest_text(text[:500]),
                target_doc_id=resolved_target.document_id,
                target_version=resolved_target.version,
                target_location="OMITTED",
                target_excerpt="",
                target_excerpt_digest=_digest_text(""),
                traceability=f"Base section '{title}' removed in target v{resolved_target.version}",
            )
            diff = ProtocolDifference(
                difference_id=diff_id,
                category="SECTION_STRUCTURE",
                title=f"Section removed: {title}",
                description=f"Section '{title}' present in v{resolved_base.version} is omitted in v{resolved_target.version}.",
                base_location=f"Lines {start_l}-{end_l}",
                target_location="OMITTED",
                evidence_id=evidence_id,
            )
            differences.append(diff.to_dict())
            diff_evidence.append(evidence.to_dict())

        elif not in_base and in_target:
            start_l, end_l, text = target_sections[title]
            evidence_id = f"EVID-{counter:03d}"
            diff_id = f"DIFF-{counter:03d}"
            counter += 1

            evidence = DiffEvidence(
                evidence_id=evidence_id,
                diff_type="SECTION_ADDED",
                base_doc_id=resolved_base.document_id,
                base_version=resolved_base.version,
                base_location="ABSENT",
                base_excerpt="",
                base_excerpt_digest=_digest_text(""),
                target_doc_id=resolved_target.document_id,
                target_version=resolved_target.version,
                target_location=f"Lines {start_l}-{end_l}",
                target_excerpt=text[:500],
                target_excerpt_digest=_digest_text(text[:500]),
                traceability=f"Target section '{title}' added in v{resolved_target.version}",
            )
            diff = ProtocolDifference(
                difference_id=diff_id,
                category="SECTION_STRUCTURE",
                title=f"Section added: {title}",
                description=f"New section '{title}' introduced in v{resolved_target.version}.",
                base_location="ABSENT",
                target_location=f"Lines {start_l}-{end_l}",
                evidence_id=evidence_id,
            )
            differences.append(diff.to_dict())
            diff_evidence.append(evidence.to_dict())

        else:
            # Present in both: check content difference
            b_start, b_end, b_text = base_sections[title]
            t_start, t_end, t_text = target_sections[title]

            if b_text != t_text:
                evidence_id = f"EVID-{counter:03d}"
                diff_id = f"DIFF-{counter:03d}"
                counter += 1

                b_features = _extract_protocol_features(b_text)
                t_features = _extract_protocol_features(t_text)

                feature_changes: list[str] = []
                added_params = t_features["parameters"] - b_features["parameters"]
                removed_params = b_features["parameters"] - t_features["parameters"]
                if added_params:
                    feature_changes.append(f"added fields/parameters: {', '.join(sorted(added_params))}")
                if removed_params:
                    feature_changes.append(f"removed fields/parameters: {', '.join(sorted(removed_params))}")

                added_restr = t_features["restrictions"] - b_features["restrictions"]
                if added_restr:
                    feature_changes.append(f"added restrictions: {', '.join(sorted(added_restr))}")

                detail_desc = (
                    f"Section '{title}' content modified. Changes include: {'; '.join(feature_changes)}"
                    if feature_changes
                    else f"Section '{title}' text formulation updated between versions."
                )

                category = "PROTOCOL_SPECIFICATION" if feature_changes else "TEXT_MODIFICATION"

                evidence = DiffEvidence(
                    evidence_id=evidence_id,
                    diff_type="SECTION_MODIFIED",
                    base_doc_id=resolved_base.document_id,
                    base_version=resolved_base.version,
                    base_location=f"Lines {b_start}-{b_end}",
                    base_excerpt=b_text[:500],
                    base_excerpt_digest=_digest_text(b_text[:500]),
                    target_doc_id=resolved_target.document_id,
                    target_version=resolved_target.version,
                    target_location=f"Lines {t_start}-{t_end}",
                    target_excerpt=t_text[:500],
                    target_excerpt_digest=_digest_text(t_text[:500]),
                    traceability=f"Content difference verified in section '{title}' between v{resolved_base.version} and v{resolved_target.version}",
                )
                diff = ProtocolDifference(
                    difference_id=diff_id,
                    category=category,
                    title=f"Section modified: {title}",
                    description=detail_desc,
                    base_location=f"Lines {b_start}-{b_end}",
                    target_location=f"Lines {t_start}-{t_end}",
                    evidence_id=evidence_id,
                )
                differences.append(diff.to_dict())
                diff_evidence.append(evidence.to_dict())

    # Document-level feature change summary
    base_full_feats = _extract_protocol_features(resolved_base.content)
    target_full_feats = _extract_protocol_features(resolved_target.content)

    summary_parts: list[str] = [
        f"Compared {resolved_base.document_id} (v{resolved_base.version}) with "
        f"{resolved_target.document_id} (v{resolved_target.version}): "
        f"{len(differences)} structural differences detected."
    ]

    all_added_params = target_full_feats["parameters"] - base_full_feats["parameters"]
    if all_added_params:
        summary_parts.append(f"Target introduces parameters: {', '.join(sorted(all_added_params))}.")

    all_added_restr = target_full_feats["restrictions"] - base_full_feats["restrictions"]
    if all_added_restr:
        summary_parts.append(f"Target introduces behavioral directives: {', '.join(sorted(all_added_restr))}.")

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
