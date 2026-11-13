from __future__ import annotations

import sys
from pathlib import Path
import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "user-demo"))

from runtime_paths import (  # noqa: E402
    UserDemoRuntimePathError,
    resolve_user_demo_database_paths,
    resolve_user_demo_runtime,
)


def test_runtime_resolver_keeps_default_and_safe_custom_names_under_runtime(tmp_path):
    root = tmp_path / "repo"
    expected = root / ".runtime"
    assert resolve_user_demo_runtime("user-demo", root=root) == expected / "user-demo"
    assert resolve_user_demo_runtime("user-demo-r2-e07", root=root) == expected / "user-demo-r2-e07"


@pytest.mark.parametrize(
    "runtime_name",
    ["", ".", "..", "user-demo/../other", "../user-demo", "C:\\temp", "User-Demo", "user-demo_"]
)
def test_runtime_resolver_rejects_arbitrary_paths_and_aliases(tmp_path, runtime_name):
    with pytest.raises(UserDemoRuntimePathError, match="RUNTIME_NAME_INVALID"):
        resolve_user_demo_runtime(runtime_name, root=tmp_path / "repo")


def test_runtime_resolver_rejects_runtime_symlink(tmp_path):
    root = tmp_path / "repo"
    runtime_root = root / ".runtime"
    runtime_root.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (runtime_root / "user-demo-alias").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Directory symlinks are unavailable in this Windows test environment.")
    with pytest.raises(UserDemoRuntimePathError, match="RUNTIME_REPARSE_POINT"):
        resolve_user_demo_runtime("user-demo-alias", root=root)


@pytest.mark.parametrize("override", ["../outside.sqlite3", "C:\\temp\\outside.sqlite3"])
def test_database_path_resolver_rejects_overrides_outside_selected_runtime(tmp_path, override):
    root = tmp_path / "repo"
    runtime_dir = root / ".runtime" / "user-demo-r2"
    runtime_dir.mkdir(parents=True)
    with pytest.raises(UserDemoRuntimePathError, match="DOMAIN_PATH_MISMATCH"):
        resolve_user_demo_database_paths(
            "user-demo-r2", root=root, domain_override=override,
        )


def test_database_path_resolver_accepts_only_exact_selected_runtime_files(tmp_path):
    root = tmp_path / "repo"
    runtime_dir = root / ".runtime" / "user-demo-r2"
    runtime_dir.mkdir(parents=True)
    domain, checkpoint = resolve_user_demo_database_paths(
        "user-demo-r2", root=root,
        domain_override=runtime_dir / "domain.sqlite3",
        checkpoint_override=runtime_dir / "checkpoint.sqlite3",
    )
    assert domain == runtime_dir / "domain.sqlite3"
    assert checkpoint == runtime_dir / "checkpoint.sqlite3"
