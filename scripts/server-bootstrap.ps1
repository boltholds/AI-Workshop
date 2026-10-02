$ErrorActionPreference = "Stop"

$storage = if ($env:AI_WORKSHOP_STORAGE_ROOT) { $env:AI_WORKSHOP_STORAGE_ROOT } else { ".workshop-server/storage" }
$state = if ($env:AI_WORKSHOP_STATE_ROOT) { $env:AI_WORKSHOP_STATE_ROOT } else { ".workshop-server/state" }
$ca = if ($env:AI_WORKSHOP_CA_ROOT) { $env:AI_WORKSHOP_CA_ROOT } else { ".workshop-server/ca" }
$admin = if ($env:AI_WORKSHOP_FIRST_ADMIN_ID) { $env:AI_WORKSHOP_FIRST_ADMIN_ID } else { "admin" }

python -c @"
from pathlib import Path
import json
from ai_workshop.server.bootstrap import ServerBootstrap
result = ServerBootstrap(
    storage_root=Path(r'$storage'),
    state_root=Path(r'$state'),
    ca_root=Path(r'$ca'),
    first_admin_id=r'$admin',
).initialize()
print(json.dumps({k:v for k,v in result.items() if k != 'tokens'}, indent=2, sort_keys=True))
"@
