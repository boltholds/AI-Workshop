#!/bin/sh
set -eu
exec ai-workshop browser serve \
  --profile "${AI_WORKSHOP_BROWSER_PROFILE:-/data/browser-profile}" \
  --host "${AI_WORKSHOP_BROWSER_HOST:-0.0.0.0}" \
  --port "${AI_WORKSHOP_BROWSER_PORT:-8767}"
