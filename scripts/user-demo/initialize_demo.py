"""Create the isolated R1 user demo once. Never use this for an existing DB."""
from __future__ import annotations

import asyncio
import argparse
import os
import sys
from pathlib import Path
from unittest.mock import patch

from runtime_paths import DEFAULT_RUNTIME_NAME, resolve_user_demo_runtime


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

S3_FIXTURE_PROFILES = ("standard", "r2-e07-queued", "r2-e08-processed-decoy")


def _add_s2_scope_demo(db_path: Path) -> None:
    from opspilot.domain.database import connect

    # S1 keeps the stock orders-demo fixture (cred-v1 against a cred-v2 policy,
    # yielding the intended local 401). S2 gets a separate trusted resource so
    # both conditions coexist without changing either runtime contract.
    with connect(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT INTO principals VALUES ('tenant-a','principal-s2-a','ENABLED',1)"
        )
        connection.execute(
            "INSERT INTO integrations VALUES ('tenant-a','integration-s2-a','principal-s2-a','cred-v2',1)"
        )
        connection.execute(
            "INSERT INTO services VALUES ('tenant-a','orders-demo-s2','integration-s2-a','/api/orders/demo-order')"
        )
        connection.execute(
            "INSERT INTO semantic_memory_project_approvers "
            "(tenant_id,project_id,actor_id,active,granted_by,granted_at) "
            "VALUES ('tenant-a','service:orders-demo-s2','approver-a',1,'fixture:user-demo-bootstrap',CURRENT_TIMESTAMP)"
        )
        connection.execute(
            "INSERT INTO auth_policies VALUES ('tenant-a','orders-demo-s2','cred-v2',3)"
        )
        connection.execute(
            "INSERT INTO principal_scope_grants "
            "(tenant_id,principal_id,granted_scopes_json,grant_version) "
            "VALUES ('tenant-a','principal-s2-a','[]',1)"
        )
        connection.execute(
            "INSERT INTO route_scope_policies "
            "(tenant_id,service_id,route,required_scopes_json,scope_policy_version) "
            "VALUES ('tenant-a','orders-demo-s2','/api/orders/demo-order','[\"orders.read\"]',1)"
        )


def initialize_checkpoint(checkpoint_path: Path) -> Path:
    """Create the real LangGraph SQLite schema without starting a model or worker."""
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    checkpoint_path = checkpoint_path.resolve()
    if checkpoint_path.exists():
        raise FileExistsError("Checkpoint database already exists; refusing to replace it.")

    async def setup() -> None:
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        async with AsyncSqliteSaver.from_conn_string(str(checkpoint_path)) as saver:
            await saver.setup()

    asyncio.run(setup())
    return checkpoint_path


def _prepare_s3_fixture_with_ids(
    db_path: Path, *, order_id: str, event_uuid: str, transport_uuid: str,
) -> dict[str, object]:
    from uuid import UUID

    from opspilot.domain.s3 import prepare_s3_fixture

    ids = iter((UUID(event_uuid), UUID(transport_uuid)))
    with patch("opspilot.domain.s3.uuid.uuid4", side_effect=lambda: next(ids)):
        return prepare_s3_fixture(
            db_path, "DELIVERED_PENDING", tenant_id="tenant-a", order_id=order_id,
            contract_version=2,
        )


def _seed_s3_fixture_profile(db_path: Path, profile: str) -> None:
    from opspilot.domain.database import connect
    from opspilot.domain.s3 import prepare_s3_fixture

    if profile == "standard":
        prepare_s3_fixture(
            db_path, "DELIVERED_PENDING", tenant_id="tenant-a", order_id="async-order",
            contract_version=2,
        )
        return
    if profile == "r2-e07-queued":
        _prepare_s3_fixture_with_ids(
            db_path, order_id="async-order",
            event_uuid="00000000-0000-4000-8000-000000000001",
            transport_uuid="00000000-0000-4000-8000-000000000002",
        )
        return
    if profile == "r2-e08-processed-decoy":
        _prepare_s3_fixture_with_ids(
            db_path, order_id="async-order",
            event_uuid="00000000-0000-4000-8000-000000000101",
            transport_uuid="00000000-0000-4000-8000-000000000201",
        )
        with connect(db_path) as connection:
            connection.execute(
                "UPDATE s3_receivers SET status='PROCESSED',version=version+1 "
                "WHERE tenant_id='tenant-a' AND order_id='async-order'"
            )
        _prepare_s3_fixture_with_ids(
            db_path, order_id="async-order-decoy",
            event_uuid="00000000-0000-4000-8000-000000000102",
            transport_uuid="00000000-0000-4000-8000-000000000202",
        )
        return
    raise ValueError("USER_DEMO_S3_FIXTURE_PROFILE_INVALID")


def _remove_r2_unrelated_stock_order(db_path: Path) -> None:
    """Keep R2's SUPPORT-visible order catalog limited to its frozen target/decoy."""
    from opspilot.domain.database import connect

    with connect(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        for table in ("s3_deliveries", "s3_receivers", "s3_orders"):
            connection.execute(
                f'DELETE FROM "{table}" WHERE tenant_id=? AND order_id=?',
                ("tenant-a", "async-order-2"),
            )


def _seed_new_user_demo(runtime_dir: Path, s3_fixture_profile: str = "standard") -> Path:
    from opspilot.domain.database import connect, reset_fixture

    db_path = runtime_dir / "domain.sqlite3"
    checkpoint_path = runtime_dir / "checkpoint.sqlite3"
    reset_fixture(db_path, "S1_POS")
    _add_s2_scope_demo(db_path)
    # Standard remains byte-for-byte the existing fixture shape. R2 profiles
    # add deterministic local event identities without changing the S3 Domain.
    if s3_fixture_profile != "standard":
        _remove_r2_unrelated_stock_order(db_path)
    _seed_s3_fixture_profile(db_path, s3_fixture_profile)
    initialize_checkpoint(checkpoint_path)

    with connect(db_path) as connection:
        s1 = connection.execute(
            "SELECT i.credential_ref,p.accepted_credential_ref "
            "FROM integrations i JOIN auth_policies p ON p.tenant_id=i.tenant_id "
            "AND p.service_id='orders-demo' WHERE i.tenant_id='tenant-a' AND i.integration_id='integration-a'"
        ).fetchone()
        s2 = connection.execute(
            "SELECT i.credential_ref,p.accepted_credential_ref,g.granted_scopes_json "
            "FROM integrations i JOIN auth_policies p ON p.tenant_id=i.tenant_id "
            "AND p.service_id='orders-demo-s2' JOIN principal_scope_grants g "
            "ON g.tenant_id=i.tenant_id AND g.principal_id=i.principal_id "
            "WHERE i.tenant_id='tenant-a' AND i.integration_id='integration-s2-a'"
        ).fetchone()
        s3 = connection.execute(
            "SELECT d.status AS delivery_status,r.status AS receiver_status,"
            "d.event_id AS delivery_event_id,r.event_id AS receiver_event_id "
            "FROM s3_deliveries d JOIN s3_receivers r ON r.tenant_id=d.tenant_id "
            "AND r.service_id=d.service_id AND r.order_id=d.order_id "
            "WHERE d.tenant_id='tenant-a' AND d.order_id='async-order'"
        ).fetchone()
        grant_counts = {
            name: int(connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
            for name in (
                "assistant_runtime_authority", "assistant_runtime_pools",
                "assistant_runtime_default_grant", "assistant_runtime_spends",
                "assistant_runtime_campaigns",
            )
        }
        if not s1 or s1["credential_ref"] == s1["accepted_credential_ref"]:
            raise RuntimeError("S1 demo fixture did not retain the expected credential mismatch.")
        if not s2 or s2["credential_ref"] != s2["accepted_credential_ref"] or s2["granted_scopes_json"] != "[]":
            raise RuntimeError("S2 demo fixture did not retain the intended missing-scope condition.")
        if not s3 or s3["delivery_status"] != "ACKNOWLEDGED" or s3["receiver_status"] != "QUEUED":
            if not (s3_fixture_profile == "r2-e08-processed-decoy" and s3
                    and s3["delivery_status"] == "ACKNOWLEDGED"
                    and s3["receiver_status"] == "PROCESSED"):
                raise RuntimeError("S3 demo fixture did not retain the intended delivery/receiver condition.")
        if s3_fixture_profile == "r2-e07-queued" and (
            s3["delivery_event_id"] != s3["receiver_event_id"]
            or s3["delivery_event_id"] != "event-00000000-0000-4000-8000-000000000001"
        ):
            raise RuntimeError("E07 fixture did not preserve the frozen same-Event identity.")
        if s3_fixture_profile == "r2-e08-processed-decoy" and (
            s3["delivery_event_id"] != s3["receiver_event_id"]
            or s3["delivery_event_id"] != "event-00000000-0000-4000-8000-000000000101"
        ):
            raise RuntimeError("E08 target fixture did not preserve the frozen same-Event identity.")
        if s3_fixture_profile == "r2-e08-processed-decoy":
            decoy = connection.execute(
                "SELECT d.event_id AS delivery_event_id,r.event_id AS receiver_event_id,"
                "d.status AS delivery_status,r.status AS receiver_status "
                "FROM s3_deliveries d JOIN s3_receivers r ON r.tenant_id=d.tenant_id "
                "AND r.service_id=d.service_id AND r.order_id=d.order_id "
                "WHERE d.tenant_id='tenant-a' AND d.order_id='async-order-decoy'"
            ).fetchone()
            if (not decoy or decoy["delivery_status"] != "ACKNOWLEDGED"
                    or decoy["receiver_status"] != "QUEUED"
                    or decoy["delivery_event_id"] != decoy["receiver_event_id"]
                    or decoy["delivery_event_id"] == s3["delivery_event_id"]):
                raise RuntimeError("E08 fixture did not preserve a distinct queued decoy Event.")
        clean_tables = (
            "sessions", "messages", "task_bindings", "task_runs",
            "personal_memories", "assistant_runtime_authority", "assistant_runtime_pools",
            "assistant_runtime_default_grant", "assistant_runtime_spends",
            "assistant_runtime_campaigns",
        )
        tables = {str(row["name"]) for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        for table in clean_tables:
            if table in tables and int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]):
                raise RuntimeError(f"Demo initialization unexpectedly created prior state in {table}.")
        if any(grant_counts.values()):
            raise RuntimeError("Demo initialization unexpectedly created Provider authority or spend.")
    return db_path


def initialize_user_demo(
    runtime_dir: Path, *, require_absent_directory: bool = False,
    s3_fixture_profile: str = "standard",
) -> Path:
    """Seed only a new user-demo directory; refuse existing DBs and concurrent initializers."""
    if s3_fixture_profile not in S3_FIXTURE_PROFILES:
        raise ValueError("USER_DEMO_S3_FIXTURE_PROFILE_INVALID")
    runtime_dir = runtime_dir.resolve()
    db_path = runtime_dir / "domain.sqlite3"
    checkpoint_path = runtime_dir / "checkpoint.sqlite3"
    if require_absent_directory and runtime_dir.exists():
        raise FileExistsError("Isolated User Demo directory already exists; refusing to reuse or overwrite it.")
    if db_path.exists() or checkpoint_path.exists():
        raise FileExistsError("User demo data already exists; initialization will not reset it.")

    runtime_dir.mkdir(parents=True, exist_ok=not require_absent_directory)
    lock_path = runtime_dir / ".initialize.lock"
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise FileExistsError("Demo initialization is already active or needs explicit recovery.") from error
    try:
        if db_path.exists() or checkpoint_path.exists():
            raise FileExistsError("User demo data appeared during initialization; refusing to reset it.")
        return _seed_new_user_demo(runtime_dir, s3_fixture_profile)
    finally:
        os.close(lock_fd)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Initialize a fresh local User Demo runtime.")
    parser.add_argument("--runtime-name", default=DEFAULT_RUNTIME_NAME)
    parser.add_argument("--s3-fixture-profile", choices=S3_FIXTURE_PROFILES, default="standard")
    args = parser.parse_args(argv)
    if args.runtime_name == DEFAULT_RUNTIME_NAME and args.s3_fixture_profile != "standard":
        parser.error("R2 S3 fixture profiles require a non-default user-demo-* runtime name.")
    target = resolve_user_demo_runtime(args.runtime_name, root=REPO_ROOT)
    created = initialize_user_demo(
        target,
        require_absent_directory=args.runtime_name != DEFAULT_RUNTIME_NAME,
        s3_fixture_profile=args.s3_fixture_profile,
    )
    print(f"User demo initialized: .runtime/{args.runtime_name}/domain.sqlite3")
    print(f"Checkpoint initialized: .runtime/{args.runtime_name}/checkpoint.sqlite3")
    print("No Sessions, Messages, Tasks, Personal Memory, Runtime Grant or Spend were carried over.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
