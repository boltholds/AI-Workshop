#!/bin/sh
set -eu
exec ai-workshop workspace serve \
  --config "${AI_WORKSHOP_PROJECTS_CONFIG:-/config/projects.yaml}" \
  --host "${AI_WORKSHOP_WORKSPACE_HOST:-0.0.0.0}" \
  --port "${AI_WORKSHOP_WORKSPACE_PORT:-8766}"
