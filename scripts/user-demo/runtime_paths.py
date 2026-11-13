"""Safe runtime-name resolution for local User Demo lifecycle entry points."""
from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNTIME_NAME = "user-demo"
_RUNTIME_NAME = re.compile(r"^user-demo(?:-[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?)?$")


class UserDemoRuntimePathError(ValueError):
    """The selected runtime name cannot be safely resolved under `.runtime`."""


def _is_reparse_path(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction and is_junction())


def resolve_user_demo_runtime(runtime_name: str, *, root: str | Path | None = None) -> Path:
    """Resolve a single allowlisted directory name directly beneath repo `.runtime`."""
    if not isinstance(runtime_name, str) or not _RUNTIME_NAME.fullmatch(runtime_name):
        raise UserDemoRuntimePathError("USER_DEMO_RUNTIME_NAME_INVALID")

    repo_root = Path(root) if root is not None else REPO_ROOT
    repo_root = repo_root.resolve()
    runtime_root = repo_root / ".runtime"
    if _is_reparse_path(runtime_root):
        raise UserDemoRuntimePathError("USER_DEMO_RUNTIME_ROOT_REPARSE_POINT")
    resolved_root = runtime_root.resolve(strict=False)
    if resolved_root.parent != repo_root or resolved_root.name.casefold() != ".runtime":
        raise UserDemoRuntimePathError("USER_DEMO_RUNTIME_ROOT_OUTSIDE_REPOSITORY")
    if resolved_root.exists() and not resolved_root.is_dir():
        raise UserDemoRuntimePathError("USER_DEMO_RUNTIME_ROOT_INVALID")

    selected = resolved_root / runtime_name
    if _is_reparse_path(selected):
        raise UserDemoRuntimePathError("USER_DEMO_RUNTIME_REPARSE_POINT")
    resolved = selected.resolve(strict=False)
    if resolved.parent != resolved_root or resolved.name != runtime_name:
        raise UserDemoRuntimePathError("USER_DEMO_RUNTIME_OUTSIDE_ROOT")
    return resolved


def resolve_user_demo_database_paths(
    runtime_name: str,
    *,
    root: str | Path | None = None,
    domain_override: str | Path | None = None,
    checkpoint_override: str | Path | None = None,
) -> tuple[Path, Path]:
    """Resolve the selected Demo's only permitted Domain and Checkpoint files."""
    repo_root = Path(root) if root is not None else REPO_ROOT
    repo_root = repo_root.resolve()
    runtime_dir = resolve_user_demo_runtime(runtime_name, root=repo_root)
    expected = (runtime_dir / "domain.sqlite3", runtime_dir / "checkpoint.sqlite3")
    configured = (domain_override, checkpoint_override)
    resolved: list[Path] = []
    for value, expected_path, label in zip(
        configured, expected, ("DOMAIN", "CHECKPOINT"), strict=True,
    ):
        candidate = Path(value) if value is not None and str(value).strip() else expected_path
        if not candidate.is_absolute():
            candidate = repo_root / candidate
        target = candidate.resolve(strict=False)
        if target != expected_path.resolve(strict=False):
            raise UserDemoRuntimePathError(f"USER_DEMO_{label}_PATH_MISMATCH")
        resolved.append(target)
    return resolved[0], resolved[1]
