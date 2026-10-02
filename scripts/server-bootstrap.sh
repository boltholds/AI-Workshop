#!/bin/sh
set -eu

STORAGE_ROOT="${AI_WORKSHOP_STORAGE_ROOT:-./.workshop-server/storage}"
STATE_ROOT="${AI_WORKSHOP_STATE_ROOT:-./.workshop-server/state}"
CA_ROOT="${AI_WORKSHOP_CA_ROOT:-./.workshop-server/ca}"
ADMIN_ID="${AI_WORKSHOP_FIRST_ADMIN_ID:-admin}"

exec python -c '
from pathlib import Path
import json, os
from ai_workshop.server.bootstrap import ServerBootstrap
result = ServerBootstrap(
    storage_root=Path(os.environ.get("AI_WORKSHOP_STORAGE_ROOT", "./.workshop-server/storage")),
    state_root=Path(os.environ.get("AI_WORKSHOP_STATE_ROOT", "./.workshop-server/state")),
    ca_root=Path(os.environ.get("AI_WORKSHOP_CA_ROOT", "./.workshop-server/ca")),
    first_admin_id=os.environ.get("AI_WORKSHOP_FIRST_ADMIN_ID", "admin"),
).initialize()
print(json.dumps({k:v for k,v in result.items() if k != "tokens"}, indent=2, sort_keys=True))
'
