from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import UUID, uuid4

import asyncpg

from commerce.models import DeliveryZone, DeliveryZoneStatus
from commerce.repositories import (
    DeliveryZoneConflictError,
    DeliveryZoneNotFoundError,
    DeliveryZoneRepository,
    InvalidDeliveryZoneGeometryError,
)
from infrastructure.database import DatabasePool


class PostgresDeliveryZoneRepository(DeliveryZoneRepository):
    def __init__(
        self,
        pool: DatabasePool,
        *,
        max_vertices: int,
        max_rings: int,
        timeout_seconds: float,
        idempotency_hours: int,
    ) -> None:
        self._pool = pool
        self._max_vertices = max_vertices
        self._max_rings = max_rings
        self._timeout_ms = max(1, int(timeout_seconds * 1000))
        self._idempotency_hours = idempotency_hours

    async def find_serviceable_zone(self, tenant_id, latitude, longitude):
        async with self._pool.pool.acquire() as connection, connection.transaction():
            await connection.execute(
                f"SET LOCAL statement_timeout = {self._timeout_ms}"
            )
            row = await connection.fetchrow(
                """SELECT id,tenant_id,name,status,priority,version,created_at,updated_at
                   FROM delivery_zones
                   WHERE tenant_id=$1 AND status='ACTIVE'
                     AND ST_Covers(boundary,ST_SetSRID(ST_MakePoint($2,$3),4326))
                   ORDER BY priority ASC,id ASC LIMIT 1""",
                tenant_id,
                longitude,
                latitude,
            )
        return self._zone(row) if row else None

    async def list_zones(
        self, tenant_id, *, status=None, limit=50, cursor=None
    ) -> tuple[DeliveryZone, ...]:
        rows = await self._pool.pool.fetch(
            """SELECT id,tenant_id,name,status,priority,version,created_at,updated_at
               FROM delivery_zones WHERE tenant_id=$1
                 AND ($2::text IS NULL OR status=$2)
                 AND ($3::uuid IS NULL OR id > $3)
               ORDER BY id LIMIT $4""",
            tenant_id,
            status.value if status else None,
            cursor,
            limit,
        )
        return tuple(self._zone(row) for row in rows)

    async def get_zone(self, tenant_id, zone_id) -> DeliveryZone | None:
        row = await self._pool.pool.fetchrow(
            """SELECT id,tenant_id,name,status,priority,version,created_at,updated_at,
                      ST_AsGeoJSON(boundary)::jsonb AS boundary
               FROM delivery_zones WHERE tenant_id=$1 AND id=$2""",
            tenant_id,
            zone_id,
        )
        return self._zone(row) if row else None

    async def check_point(self, tenant_id, latitude, longitude) -> DeliveryZone | None:
        return await self.find_serviceable_zone(tenant_id, latitude, longitude)

    async def create_zone(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        request_id: str,
        idempotency_key: str,
        name: str,
        priority: int,
        boundary: dict[str, object],
    ) -> DeliveryZone:
        zone_id = uuid4()
        payload = {"name": name, "priority": priority, "boundary": boundary}
        request_hash = self._hash(payload)
        now = datetime.now(timezone.utc)
        async with self._pool.pool.acquire() as connection, connection.transaction():
            replay = await self._claim_idempotency(
                connection,
                tenant_id,
                actor_id,
                idempotency_key,
                "delivery_zone_create",
                request_hash,
                zone_id,
                now,
            )
            if replay is not None:
                existing = await self._get_zone(connection, tenant_id, replay)
                if existing is None:
                    raise DeliveryZoneConflictError("idempotency_resource_missing")
                return existing
            geometry = await self._validated_geometry(connection, boundary)
            try:
                row = await connection.fetchrow(
                    """INSERT INTO delivery_zones
                       (id,tenant_id,name,name_normalized,status,priority,boundary,
                        version,created_at,updated_at)
                       VALUES ($1,$2,$3,$4,'DRAFT',$5,
                         ST_Multi(ST_Force2D(ST_SetSRID(ST_GeomFromGeoJSON($6),4326))),
                         1,$7,$7)
                       RETURNING id,tenant_id,name,status,priority,version,created_at,updated_at,
                                 ST_AsGeoJSON(boundary)::jsonb AS boundary""",
                    zone_id,
                    tenant_id,
                    self._name(name),
                    self._name(name).casefold(),
                    priority,
                    geometry,
                    now,
                )
            except asyncpg.UniqueViolationError as error:
                raise DeliveryZoneConflictError("zone_name_conflict") from error
            await self._audit(connection, row, actor_id, request_id, "CREATED", None)
            return self._zone(row)

    async def update_zone(
        self,
        *,
        tenant_id: UUID,
        zone_id: UUID,
        actor_id: UUID,
        request_id: str,
        idempotency_key: str,
        expected_version: int,
        name: str | None,
        priority: int | None,
        boundary: dict[str, object] | None,
    ) -> DeliveryZone:
        payload = {
            "zone_id": str(zone_id),
            "expected_version": expected_version,
            "name": name,
            "priority": priority,
            "boundary": boundary,
        }
        now = datetime.now(timezone.utc)
        async with self._pool.pool.acquire() as connection, connection.transaction():
            replay = await self._claim_idempotency(
                connection,
                tenant_id,
                actor_id,
                idempotency_key,
                "delivery_zone_update",
                self._hash(payload),
                zone_id,
                now,
            )
            if replay is not None:
                existing = await self._get_zone(connection, tenant_id, replay)
                if existing is None:
                    raise DeliveryZoneConflictError("idempotency_resource_missing")
                return existing
            current = await self._get_zone(connection, tenant_id, zone_id, lock=True)
            if current is None:
                raise DeliveryZoneNotFoundError("delivery_zone_not_found")
            if current.version != expected_version:
                raise DeliveryZoneConflictError("stale_delivery_zone_version", current)
            geometry = (
                await self._validated_geometry(connection, boundary)
                if boundary is not None
                else None
            )
            try:
                row = await connection.fetchrow(
                    """UPDATE delivery_zones SET
                         name=COALESCE($4,name),
                         name_normalized=COALESCE($5,name_normalized),
                         priority=COALESCE($6,priority),
                         boundary=CASE WHEN $7::text IS NULL THEN boundary ELSE
                           ST_Multi(ST_Force2D(ST_SetSRID(ST_GeomFromGeoJSON($7),4326))) END,
                         version=version+1,updated_at=$8
                       WHERE tenant_id=$1 AND id=$2 AND version=$3
                       RETURNING id,tenant_id,name,status,priority,version,created_at,updated_at,
                                 ST_AsGeoJSON(boundary)::jsonb AS boundary""",
                    tenant_id,
                    zone_id,
                    expected_version,
                    self._name(name) if name is not None else None,
                    self._name(name).casefold() if name is not None else None,
                    priority,
                    geometry,
                    now,
                )
            except asyncpg.UniqueViolationError as error:
                raise DeliveryZoneConflictError("zone_name_conflict") from error
            await self._audit(
                connection, row, actor_id, request_id, "UPDATED", expected_version
            )
            return self._zone(row)

    async def change_status(
        self,
        *,
        tenant_id: UUID,
        zone_id: UUID,
        actor_id: UUID,
        request_id: str,
        idempotency_key: str,
        expected_version: int,
        status: DeliveryZoneStatus,
    ) -> DeliveryZone:
        if status is DeliveryZoneStatus.DRAFT:
            raise ValueError("Draft is not a status action.")
        now = datetime.now(timezone.utc)
        operation = (
            "ACTIVATED" if status is DeliveryZoneStatus.ACTIVE else "DEACTIVATED"
        )
        payload = {
            "zone_id": str(zone_id),
            "version": expected_version,
            "status": status.value,
        }
        async with self._pool.pool.acquire() as connection, connection.transaction():
            replay = await self._claim_idempotency(
                connection,
                tenant_id,
                actor_id,
                idempotency_key,
                f"delivery_zone_{status.value.lower()}",
                self._hash(payload),
                zone_id,
                now,
            )
            if replay is not None:
                existing = await self._get_zone(connection, tenant_id, replay)
                if existing is None:
                    raise DeliveryZoneConflictError("idempotency_resource_missing")
                return existing
            current = await self._get_zone(connection, tenant_id, zone_id, lock=True)
            if current is None:
                raise DeliveryZoneNotFoundError("delivery_zone_not_found")
            if current.version != expected_version:
                raise DeliveryZoneConflictError("stale_delivery_zone_version", current)
            row = await connection.fetchrow(
                """UPDATE delivery_zones SET status=$4,version=version+1,updated_at=$5
                   WHERE tenant_id=$1 AND id=$2 AND version=$3
                   RETURNING id,tenant_id,name,status,priority,version,created_at,updated_at,
                             ST_AsGeoJSON(boundary)::jsonb AS boundary""",
                tenant_id,
                zone_id,
                expected_version,
                status.value,
                now,
            )
            await self._audit(
                connection, row, actor_id, request_id, operation, expected_version
            )
            return self._zone(row)

    async def postgis_available(self) -> bool:
        return bool(
            await self._pool.pool.fetchval(
                "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname='postgis')"
            )
        )

    async def _validated_geometry(self, connection, boundary):
        raw = json.dumps(boundary, separators=(",", ":"))
        try:
            row = await connection.fetchrow(
                """WITH candidate AS (
                     SELECT ST_Multi(ST_Force2D(ST_SetSRID(ST_GeomFromGeoJSON($1),4326))) AS geom
                   ), ring_count AS (
                     SELECT COALESCE(sum(ST_NRings(part.geom)),0) AS rings
                     FROM candidate CROSS JOIN LATERAL ST_Dump(geom) AS part
                   )
                   SELECT geom,GeometryType(geom) AS kind,ST_IsEmpty(geom) AS empty,
                          ST_IsValid(geom) AS valid,ST_NPoints(geom) AS vertices,rings
                   FROM candidate,ring_count""",
                raw,
            )
        except (asyncpg.PostgresError, ValueError) as error:
            raise InvalidDeliveryZoneGeometryError("malformed_geometry") from error
        if row["kind"] != "MULTIPOLYGON":
            raise InvalidDeliveryZoneGeometryError("unsupported_geometry_type")
        if row["empty"]:
            raise InvalidDeliveryZoneGeometryError("empty_geometry")
        if not row["valid"]:
            raise InvalidDeliveryZoneGeometryError("invalid_geometry")
        if row["vertices"] > self._max_vertices:
            raise InvalidDeliveryZoneGeometryError("too_many_vertices")
        if row["rings"] > self._max_rings:
            raise InvalidDeliveryZoneGeometryError("too_many_rings")
        return raw

    async def _claim_idempotency(
        self,
        connection,
        tenant_id,
        actor_id,
        key,
        operation,
        request_hash,
        resource_id,
        now,
    ) -> UUID | None:
        await connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended($1,0))",
            f"{tenant_id}:{actor_id}:{key}",
        )
        existing = await connection.fetchrow(
            """SELECT operation,request_hash,resource_id FROM staff_api_idempotency
               WHERE tenant_id=$1 AND staff_id=$2 AND idempotency_key=$3""",
            tenant_id,
            actor_id,
            key,
        )
        if existing:
            if (
                existing["operation"] != operation
                or existing["request_hash"] != request_hash
            ):
                raise DeliveryZoneConflictError("idempotency_key_conflict")
            return existing["resource_id"]
        await connection.execute(
            """INSERT INTO staff_api_idempotency
               (id,tenant_id,staff_id,idempotency_key,operation,request_hash,
                resource_id,response_status,response_body,created_at,expires_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7,200,NULL,$8,$9)""",
            uuid4(),
            tenant_id,
            actor_id,
            key,
            operation,
            request_hash,
            resource_id,
            now,
            now + timedelta(hours=self._idempotency_hours),
        )
        return None

    async def _get_zone(self, connection, tenant_id, zone_id, lock=False):
        row = await connection.fetchrow(
            """SELECT id,tenant_id,name,status,priority,version,created_at,updated_at,
                      ST_AsGeoJSON(boundary)::jsonb AS boundary
               FROM delivery_zones WHERE tenant_id=$1 AND id=$2"""
            + (" FOR UPDATE" if lock else ""),
            tenant_id,
            zone_id,
        )
        return self._zone(row) if row else None

    @staticmethod
    async def _audit(connection, row, actor_id, request_id, operation, from_version):
        await connection.execute(
            """INSERT INTO delivery_zone_audit
               (id,tenant_id,zone_id,actor_id,operation,from_version,to_version,
                geometry_hash,request_id,created_at)
               SELECT $1,$2,$3,$4,$5,$6,$7,md5(ST_AsBinary(boundary)::text),$8,$9
               FROM delivery_zones WHERE id=$3 AND tenant_id=$2""",
            uuid4(),
            row["tenant_id"],
            row["id"],
            actor_id,
            operation,
            from_version,
            row["version"],
            request_id,
            row["updated_at"],
        )

    @staticmethod
    def _zone(row) -> DeliveryZone:
        data = dict(row)
        boundary = data.get("boundary")
        if isinstance(boundary, str):
            data["boundary"] = json.loads(boundary)
        return DeliveryZone.model_validate(data)

    @staticmethod
    def _name(value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized or len(normalized) > 120:
            raise ValueError("invalid_zone_name")
        return normalized

    @staticmethod
    def _hash(payload: object) -> str:
        return sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
