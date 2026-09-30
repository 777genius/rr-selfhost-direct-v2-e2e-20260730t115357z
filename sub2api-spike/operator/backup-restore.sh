#!/bin/sh
# TRUSTED coordinator ONLY. Raw database backup remains PRIVATE; no worker access.
# Separate rr-sub2-spike-20260930-restore instance; does not touch baseline DB.
set -eu
: "${PRIVATE_DIR:?owned private directory}"
: "${POSTGRES_IMAGE:?reviewed immutable digest}"
case "$PRIVATE_DIR" in */rr-sub2-spike-20260930-*) ;; *) exit 2;; esac
case "$POSTGRES_IMAGE" in *@sha256:*) ;; *) exit 2;; esac
umask 077
compose=sub2api-spike/operator/compose.yaml
docker compose -p rr-sub2-spike-20260930 -f "$compose" exec -T postgres pg_dump -U rrsub2 -d rrsub2 --format=custom > "$PRIVATE_DIR/rr-sub2-spike-20260930.dump"
# No public ports or host socket. Original key files are never mounted.
docker run -d --name rr-sub2-spike-20260930-restore --network none --security-opt no-new-privileges --env-file "$PRIVATE_DIR/postgres.env" --mount type=volume,source=rr-sub2-spike-20260930-restore-data,target=/var/lib/postgresql/data "$POSTGRES_IMAGE" > "$PRIVATE_DIR/restore-container.id"
i=0
until docker exec rr-sub2-spike-20260930-restore pg_isready -U rrsub2 -d rrsub2 > /dev/null; do
  i=$((i+1))
  [ "$i" -lt 30 ] || exit 1
  sleep 1
done
docker exec -i rr-sub2-spike-20260930-restore pg_restore -U rrsub2 -d rrsub2 --exit-on-error < "$PRIVATE_DIR/rr-sub2-spike-20260930.dump"
# Export only aggregate owned counts; never JSONB credentials/keys.
docker exec rr-sub2-spike-20260930-restore psql -U rrsub2 -d rrsub2 -Atc "SELECT json_build_object('owned_accounts', (SELECT count(*) FROM accounts WHERE name LIKE 'rr-sub2-spike-20260930-%'), 'owned_groups', (SELECT count(*) FROM groups WHERE name LIKE 'rr-sub2-spike-20260930-%'));" > "$PRIVATE_DIR/restore-counts.json"
# G04 stays incomplete until counts compared with source and BROKER restart replay
# tested using the original run ledger. Database restore alone is NOT stale-run proof.
docker rm -f rr-sub2-spike-20260930-restore > /dev/null
docker volume rm rr-sub2-spike-20260930-restore-data > /dev/null
