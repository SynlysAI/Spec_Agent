#!/usr/bin/env bash

set -euo pipefail

RUNTIME_DIR="${HOME}/.docker/run"
DATA_ROOT="${HOME}/.local/share/spec-agent-docker-vfs"
DAEMON_LOG="${RUNTIME_DIR}/dockerd-default-vfs.log"

mkdir -p "${RUNTIME_DIR}" "${DATA_ROOT}" "${HOME}/.config/docker"

cat > "${HOME}/.config/docker/daemon.json" <<EOF
{
  "storage-driver": "vfs",
  "data-root": "${DATA_ROOT}",
  "features": {
    "buildkit": true
  }
}
EOF

export XDG_RUNTIME_DIR="${RUNTIME_DIR}"
export DOCKER_HOST="unix://${RUNTIME_DIR}/docker.sock"

if docker info >/dev/null 2>&1; then
  echo "rootless docker already ready: ${DOCKER_HOST}"
  exit 0
fi

nohup "${HOME}/bin/dockerd-rootless.sh" > "${DAEMON_LOG}" 2>&1 &

for _ in $(seq 1 30); do
  if docker info >/dev/null 2>&1; then
    echo "rootless docker ready: ${DOCKER_HOST}"
    exit 0
  fi
  sleep 1
done

echo "rootless docker start timeout, check ${DAEMON_LOG}" >&2
exit 1
