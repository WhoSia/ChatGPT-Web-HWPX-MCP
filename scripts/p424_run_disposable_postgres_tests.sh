#!/usr/bin/env bash
# Isolated, opt-in P4.24 Postgres integration verification using Docker.
# Never reads production credentials or mounts application/private files.
set -Eeuo pipefail

if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  echo "Docker daemon unavailable. No DB or tests started." >&2
  exit 2
fi
if [[ ! -d tests || ! -f hwpx_mcp/testing/p424_disposable_database.py ]]; then
  echo "Run from the P4.24 repository root." >&2
  exit 2
fi
if ! command -v python >/dev/null 2>&1; then
  echo "Activate the repository virtualenv before running." >&2
  exit 2
fi

# Never inherit any environment-provided application or test database URL.
unset P424_TEST_DATABASE_URL P424_TEST_DATABASE_DISPOSABLE
unset P12_AUTH_DATABASE_URL P30_DOCUMENT_DATABASE_URL
unset P414_DATABASE_URL P424_PDF_DATABASE_URL

container_name="p424-disposable-pg-${RANDOM}-${RANDOM}"
db_name="p424_disposable_${RANDOM}_${RANDOM}"
password="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
cleanup() {
  docker rm -f "$container_name" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

docker run --detach --rm \
  --name "$container_name" \
  --publish 127.0.0.1::5432 \
  --env POSTGRES_USER=p424_test_user \
  --env POSTGRES_PASSWORD="$password" \
  --env POSTGRES_DB="$db_name" \
  --tmpfs /var/lib/postgresql/data:rw,noexec,nosuid,size=256m \
  postgres:16-alpine >/dev/null

published="$(docker port "$container_name" 5432/tcp)"
if [[ ! "$published" =~ ^127\.0\.0\.1:[0-9]+$ ]]; then
  echo "Refusing non-loopback Docker database publication." >&2
  exit 3
fi
port="${published##*:}"

for ((attempt=1; attempt<=60; attempt++)); do
  if docker exec "$container_name" pg_isready -U p424_test_user -d "$db_name" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done
if ! docker exec "$container_name" pg_isready -U p424_test_user -d "$db_name" >/dev/null 2>&1; then
  echo "Disposable PostgreSQL did not become ready." >&2
  exit 4
fi

# Password remains only in the process environment and is never printed.
export P424_TEST_DATABASE_DISPOSABLE=YES
export P424_TEST_DATABASE_URL="postgresql://p424_test_user:${password}@127.0.0.1:${port}/${db_name}"
echo "Running P4.24 tests against a newly created localhost-only disposable PostgreSQL container."
python -m unittest discover -s tests -p 'test_p424_*.py' -v
echo "Disposable DB tests completed; Docker container will be removed."
