"""Independent acceptance entrypoint; never imported by production entrypoints."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
from observe_provider import install

install(Path(os.environ["OPSPILOT_DB_PATH"]), Path(os.environ["OPSPILOT_HF02_PROVIDER_OBSERVATIONS"]))
from opspilot.web.server import main

raise SystemExit(main())
