#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

export XDG_RUNTIME_DIR="${HOME}/.docker/run"
export DOCKER_HOST="unix://${XDG_RUNTIME_DIR}/docker.sock"
export http_proxy="${http_proxy:-http://127.0.0.1:7890}"
export https_proxy="${https_proxy:-http://127.0.0.1:7890}"

"${SCRIPT_DIR}/rootless-vfs-start.sh"

if [ ! -f "${SCRIPT_DIR}/.env" ]; then
  cp "${SCRIPT_DIR}/.env.example" "${SCRIPT_DIR}/.env"
fi

cd "${PROJECT_ROOT}"
docker-compose --env-file docker/.env -f docker/docker-compose.yml -f docker/docker-compose.infra.yml up -d
