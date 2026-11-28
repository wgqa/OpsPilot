"""Create the isolated R1 user demo once. Never use this for an existing DB."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


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


def _seed_new_user_demo(runtime_dir: Path) -> Path:
    from opspilot.domain.database import connect, reset_fixture
    from opspilot.domain.s3 import prepare_s3_fixture

    db_path = runtime_dir / "domain.sqlite3"
    checkpoint_path = runtime_dir / "checkpoint.sqlite3"
    reset_fixture(db_path, "S1_POS")
    _add_s2_scope_demo(db_path)
    # The first callback order is deliberately accepted by the local loopback
    # receiver and remains QUEUED; the second stays an unattempted example.
    prepare_s3_fixture(
        db_path, "DELIVERED_PENDING", tenant_id="tenant-a", order_id="async-order",
        contract_version=2,
    )
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
            "SELECT d.status AS delivery_status,r.status AS receiver_status "
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
            raise RuntimeError("S3 demo fixture did not retain the intended accepted/queued condition.")
        if any(grant_counts.values()):
            raise RuntimeError("Demo initialization unexpectedly created Provider authority or spend.")
    return db_path


def initialize_user_demo(runtime_dir: Path) -> Path:
    """Seed only a new user-demo directory; refuse existing DBs and concurrent initializers."""
    runtime_dir = runtime_dir.resolve()
    db_path = runtime_dir / "domain.sqlite3"
    checkpoint_path = runtime_dir / "checkpoint.sqlite3"
    if db_path.exists() or checkpoint_path.exists():
        raise FileExistsError("User demo data already exists; initialization will not reset it.")

    runtime_dir.mkdir(parents=True, exist_ok=True)
    lock_path = runtime_dir / ".initialize.lock"
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise FileExistsError("Demo initialization is already active or needs explicit recovery.") from error
    try:
        if db_path.exists() or checkpoint_path.exists():
            raise FileExistsError("User demo data appeared during initialization; refusing to reset it.")
        return _seed_new_user_demo(runtime_dir)
    finally:
        os.close(lock_fd)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    target = REPO_ROOT / ".runtime" / "user-demo"
    created = initialize_user_demo(target)
    print(f"User demo initialized: {created}")
