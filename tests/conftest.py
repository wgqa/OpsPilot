from __future__ import annotations

import threading
from pathlib import Path

import pytest

from opspilot.domain.api import make_server
from opspilot.domain.database import reset_fixture


@pytest.fixture
def demo_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "domain.sqlite3"
    reset_fixture(db_path, "S1_POS")
    return db_path


@pytest.fixture
def live_api(demo_db: Path):
    server = make_server(demo_db, "tenant-a", "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
