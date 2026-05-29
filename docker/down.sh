#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

export XDG_RUNTIME_DIR="${HOME}/.docker/run"
export DOCKER_HOST="unix://${XDG_RUNTIME_DIR}/docker.sock"

cd "${PROJECT_ROOT}"
docker-compose --env-file docker/.env -f docker/docker-compose.yml down
