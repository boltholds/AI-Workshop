#!/usr/bin/env sh
set -eu

AI_WORKSHOP_UID="${AI_WORKSHOP_UID:-10001}"
AI_WORKSHOP_GID="${AI_WORKSHOP_GID:-10001}"

case "$AI_WORKSHOP_UID:$AI_WORKSHOP_GID" in
  *[!0-9:]*|:*|*:) echo "AI_WORKSHOP_UID/GID must be numeric" >&2; exit 64 ;;
esac
if [ "$AI_WORKSHOP_UID" = "0" ] || [ "$AI_WORKSHOP_GID" = "0" ]; then
  echo "AI Workshop refuses to run the agent process as root" >&2
  exit 64
fi

mkdir -p /home/workshop/.cache
chown -R "$AI_WORKSHOP_UID:$AI_WORKSHOP_GID" /home/workshop
if [ -d /state ]; then
  chown -R "$AI_WORKSHOP_UID:$AI_WORKSHOP_GID" /state
fi
export HOME=/home/workshop

exec gosu "$AI_WORKSHOP_UID:$AI_WORKSHOP_GID" ai-workshop "$@"
