WhatsApp Delivery Location and Serviceability Specification

1. Purpose

Allow customers to share a delivery-location pin through WhatsApp, check the exactcoordinates against business-managed delivery coverage, collect the remainingbuilding-level instructions, and save the confirmed serviceable destination.

The central rule is:

Meta supplies a customer-shared location.
The commerce platform decides whether it delivers there.

Meta, a geocoder, PIN code, locality name, and the LLM are never serviceabilityauthorities. Active tenant-owned zones in PostgreSQL/PostGIS are authoritative.

This milestone extends specifications 012, 016, 020, 026, 027, and 028. Existingidentity, consent, checkout, order snapshot, channel security, replay, localization,staff authorization, and idempotency rules remain authoritative.

2. Goals

Accept WhatsApp location messages as typed provider-neutral inbound attachments.

Trust coordinates only after Meta raw-body signature verification.

Keep precise coordinates out of planner prompts and LLM-generated arguments.

Check coordinates against active tenant-scoped PostGIS delivery zones.

Allow admins to create, preview, update, activate, and deactivate coverage boundaries.

Prefer location sharing for WhatsApp onboarding and address replacement.

Still collect flat/house number, floor, entrance, and landmark details.

Optionally reverse-geocode for customer-readable locality text.

Require review and consent before durable profile persistence or overwrite.

Revalidate serviceability during checkout and immediately before confirmation.

Retain a text-address fallback when location sharing is unavailable.

Treat precise location as sensitive personal data.

Preserve the frozen Planner -> Execute -> Response graph.

3. Non-goals

Continuous/live/background customer tracking.

Driver tracking, routing, navigation, or ETA prediction.

Proving the customer is physically present at or owns the location.

Deriving flat, floor, entrance, or recipient instructions from coordinates.

Using PIN/locality matching as the final coverage decision.

Allowing the LLM to generate, repair, round, or move coordinates.

Letting Meta or a maps provider define delivery coverage.

Delivery fees, minimum orders, slots, or zone-specific pricing/catalog policy.

A new LangGraph node or capability-to-capability calls.

4. Frozen Architecture and Trust Boundary

Customer shares WhatsApp location
    -> signed Meta webhook
    -> verify signature over exact raw body
    -> normalize LOCATION message
    -> atomically persist message and coordinates
    -> inbound worker claims message
    -> trusted runtime context carries attachment
    -> Planner sees only "customer shared location"
    -> submit_delivery_location (no coordinate arguments)
    -> DeliveryService
    -> PostGIS DeliveryZoneRepository
    -> pending serviceable-location state
    -> collect building details
    -> explicit review/confirmation
    -> saved delivery address
    -> Response Node

Rules:

Webhook routes authenticate and normalize; they do not decide coverage.

The planner never receives precise coordinates in this milestone.

Capability arguments never contain LLM-generated coordinates.

The capability reads the current attachment from trusted execution context.

Services own serviceability policy; repositories own spatial SQL and tenant scoping.

PostgreSQL is authoritative for zones and saved locations.

Reverse-geocoding is advisory enrichment only.

The Response Node localizes approved meaning and never decides coverage.

5. Customer Experience

5.1 First-time WhatsApp onboarding

Prefer:

Welcome to MeatUncle!

Order aur delivery ke liye apna naam aur phone number share kar dijiye.

Jahan order deliver karwana hai, WhatsApp attachment se us jagah ki location bhi send
kar dijiye.

The wording must request the delivery destination, not necessarily the customer'scurrent location. Text and location normally arrive as separate messages, so pendingstate retains valid values across turns without asking for them again.

5.2 Serviceable location

✅ Is location par delivery available hai.

Delivery complete karne ke liye flat/house number, floor aur nearby landmark share kar
dijiye.

5.3 Outside delivery area

Sorry, abhi hum is location par delivery nahi karte.

Kya aap kisi doosri delivery location ko check karna chahenge?

Do not expose polygon boundaries, internal zone IDs, or operational notes.

5.4 Final review

*Delivery Details*

Name: Samad
Phone: ****7170
Area: New Zafrabad, Delhi
Address details: B-68, 2nd Floor, near ABC School

Kya main yeh delivery details future orders ke liye save kar doon?

Do not display raw coordinates by default. Persist only after explicit consent andconfirmation under specifications 012 and 016.

5.5 Returning customer

A saved location may be offered through a masked projection. The customer may use it,share another location, select another saved address, or use the text fallback.

6. Meta Inbound Location Contract

Extend the provider-neutral model:

class MessageKind(str, Enum):
    TEXT = "TEXT"
    LOCATION = "LOCATION"
    UNSUPPORTED = "UNSUPPORTED"


class InboundLocation(BaseModel):
    latitude: Decimal = Field(ge=Decimal("-90"), le=Decimal("90"))
    longitude: Decimal = Field(ge=Decimal("-180"), le=Decimal("180"))
    name: str | None = None
    provider_address: str | None = None

Rules:

Reject NaN, infinity, booleans, missing/malformed values, and values outside bounds.

Parse without binary floating-point round trips where practical.

Bound and trim optional provider text.

Never use provider name/address as profile or serviceability truth.

Standard location messages are supported; live/background tracking is not.

Preserve specification 026's atomic-valid-set batch rule and wamid deduplication.

Provider-neutral persistence may use a typed attachment table or these nullable columns:

ALTER TABLE channel_inbound_messages
    ADD COLUMN location_latitude numeric(9,6),
    ADD COLUMN location_longitude numeric(9,6),
    ADD COLUMN location_name varchar(200),
    ADD COLUMN location_provider_address varchar(500);

Enforce that LOCATION rows have both valid coordinates and non-location rows do not.Do not persist full raw webhook bodies.

7. Trusted Execution Context

class TrustedInboundMessageContext(BaseModel):
    inbound_message_id: UUID
    request_id: str
    message_kind: MessageKind
    location: InboundLocation | None = None

The application boundary creates this context. The planner prompt receives only a safefact such as customer_shared_location=true. The current location must remain bound tothe claimed inbound message so replay or later turns cannot substitute another pin.

8. Delivery-Zone Domain Model

class DeliveryZoneStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class DeliveryZone(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    status: DeliveryZoneStatus
    priority: int
    version: int
    created_at: datetime
    updated_at: datetime

Invariants:

Only ACTIVE zones are serviceable.

Name is normalized, unique per tenant, non-empty, and bounded.

Priority is a bounded non-negative integer; lower value wins.

Version starts at 1 and supports optimistic concurrency.

Boundary is a valid, non-empty Polygon/MultiPolygon in WGS84 (SRID 4326).

Rings are closed and non-self-intersecting.

Bound vertices, rings, payload size, and processing time.

Overlaps resolve deterministically by priority then stable ID.

PostGIS polygon/multipolygon is canonical. A centre/radius admin editor may convert thecircle to a bounded polygon, but must not create a second coverage engine.

9. PostgreSQL/PostGIS Schema

Use Alembic:

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE delivery_zones (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    name varchar(120) NOT NULL,
    name_normalized varchar(120) NOT NULL,
    status varchar(16) NOT NULL,
    priority integer NOT NULL DEFAULT 100,
    boundary geometry(MultiPolygon, 4326) NOT NULL,
    version integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    CHECK (status IN ('DRAFT', 'ACTIVE', 'INACTIVE')),
    CHECK (priority >= 0),
    CHECK (version >= 1),
    CHECK (NOT ST_IsEmpty(boundary)),
    CHECK (ST_IsValid(boundary)),
    UNIQUE (tenant_id, name_normalized)
);

CREATE INDEX ix_delivery_zones_boundary
    ON delivery_zones USING gist (boundary);

CREATE INDEX ix_delivery_zones_tenant_status_priority
    ON delivery_zones (tenant_id, status, priority, id);

If the target PostgreSQL environment cannot enforce a spatial function in a checkconstraint, validate geometry transactionally and add the strongest supported databaseenforcement. Application-only validation is insufficient for admin geometry.

When serviceability is enabled but PostGIS is unavailable, readiness fails and orderconfirmation fails closed without discarding the cart.

10. Authoritative Serviceability Query

Use ST_Covers so boundary points count as covered:

SELECT id, tenant_id, name, status, priority, version, created_at, updated_at
FROM delivery_zones
WHERE tenant_id = $1
  AND status = 'ACTIVE'
  AND ST_Covers(
      boundary,
      ST_SetSRID(ST_MakePoint($2, $3), 4326)
  )
ORDER BY priority ASC, id ASC
LIMIT 1;

$1 = trusted tenant_id
$2 = longitude
$3 = latitude

PostGIS and GeoJSON use longitude first. Repository bindings must be explicit and testedagainst accidental coordinate reversal.

11. Repository and Service Contracts

class DeliveryZoneRepository(Protocol):
    async def find_serviceable_zone(
        self,
        tenant_id: UUID,
        latitude: Decimal,
        longitude: Decimal,
    ) -> DeliveryZone | None: ...

    async def list_zones(...) -> Page[DeliveryZone]: ...
    async def get_zone(...) -> DeliveryZone | None: ...
    async def create_zone(...) -> DeliveryZone: ...
    async def update_zone(...) -> DeliveryZone: ...
    async def change_zone_status(...) -> DeliveryZone: ...

class ServiceabilityKind(str, Enum):
    SERVICEABLE = "SERVICEABLE"
    OUTSIDE_SERVICE_AREA = "OUTSIDE_SERVICE_AREA"
    TEMPORARILY_UNAVAILABLE = "TEMPORARILY_UNAVAILABLE"


class ServiceabilityResult(BaseModel):
    kind: ServiceabilityKind
    zone_id: UUID | None = None
    zone_name: str | None = None
    zone_version: int | None = None
    checked_at: datetime

Database/PostGIS failure maps to TEMPORARILY_UNAVAILABLE, never outside-area. Allqueries use trusted tenant identity. Cache only briefly, tenant-scope it, and invalidateon zone mutation.

12. Optional Reverse Geocoder

Polygon serviceability works directly from coordinates; a maps provider is optional.

class ReverseGeocodeResult(BaseModel):
    formatted_area: str | None
    locality: str | None
    city: str | None
    state: str | None
    postal_code: str | None
    provider_reference: str | None


class ReverseGeocoder(Protocol):
    async def reverse_geocode(
        self,
        latitude: Decimal,
        longitude: Decimal,
    ) -> ReverseGeocodeResult: ...

REVERSE_GEOCODER_PROVIDER=disabled|mappls|google

Provider output improves display only. Provider failure after a successful zone matchdoes not make the location unsupported. Send only coordinates, apply provider terms,timeouts, quota controls, and safe errors, and never send unrelated PII.

13. Pending and Durable Address State

class PendingDeliveryLocation(BaseModel):
    inbound_message_id: UUID
    latitude: Decimal
    longitude: Decimal
    zone_id: UUID
    zone_name: str
    zone_version: int
    formatted_area: str | None
    address_details: str | None
    checked_at: datetime

Attach it to the existing onboarding proposal; do not create a competing workflow.

Rules:

Store only a serviceable pending location.

Use the existing onboarding TTL.

Freshly checked explicit location may replace an older pending location.

Outside-area input does not silently erase a valid serviceable pending location.

Nothing becomes long-term profile memory before review and confirmation.

Do not place coordinates in assistant message history.

Extend canonical saved addresses with nullable coordinates, formatted area, zone ID,zone version, status, and checked time. Suggested statuses:

class SavedAddressServiceabilityStatus(str, Enum):
    SERVICEABLE = "SERVICEABLE"
    REVALIDATION_REQUIRED = "REVALIDATION_REQUIRED"
    LEGACY_UNVALIDATED = "LEGACY_UNVALIDATED"

Legacy text-only rows become LEGACY_UNVALIDATED; never invent coordinates. Preferdeactivation over deletion for zones referenced by saved addresses/orders.

14. Capability Contracts

14.1 request_delivery_location

No arguments. It asks for the delivery-destination pin, preserves collected values,sets the pending expectation, and offers text fallback guidance.

14.2 submit_delivery_location

class SubmitDeliveryLocationArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

No coordinates, address, zone, tenant, customer, or message ID are planner arguments.The capability:

requires current trusted MessageKind.LOCATION;

reads coordinates from trusted context;

checks tenant serviceability;

optionally reverse-geocodes;

stores pending state only when serviceable;

asks for all missing name/phone/building details together;

returns outside-area meaning without persistence; and

distinguishes temporary infrastructure failure from unsupported coverage.

14.3 collect_delivery_address_details

class CollectDeliveryAddressDetailsArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    address_details: NonEmptyText

Validate bounded, non-empty, control-character-free flat/house/floor/entrance/landmarktext. It cannot replace coordinates. When all onboarding fields exist, show the proposaland use existing explicit confirmation to persist it.

Location replacement requires a new trusted pin and overwrite confirmation. Separate abuilding-detail-only edit from a location replacement so text edits never retain stalecoordinates ambiguously.

15. Planner Routing Rules

When delivery location is expected and trusted message kind is LOCATION, executesubmit_delivery_location without arguments.

Never convert a location message into text search or copy coordinates into arguments.

After a serviceable location, building details route tocollect_delivery_address_details.

Unrelated text while location is required produces a location/fallback request; neverguessed coordinates.

Explicit inability to share location routes to text fallback.

Sharing a location is not consent to save it or confirmation to order.

Generic yes resolves only against the active follow-up.

Apply rules across languages/scripts; one planner decision per turn remains mandatory.

16. Checkout and Order Revalidation

Recheck coordinates:

when received;

when a saved location is selected for checkout; and

inside authoritative order confirmation before mutation/reservation.

Checkout snapshots name, phone, coordinates, formatted area, building details, and thecurrent zone result/version. Customer review masks the phone and omits coordinates.

If no longer serviceable:

do not create the order or reserve/consume inventory;

keep the active cart;

invalidate stale checkout location readiness;

ask for another location; and

require a fresh final review.

On temporary PostGIS failure, fail closed while preserving recoverable state and nevertell the customer the area is unsupported.

Confirmed orders retain immutable delivery snapshots required for fulfilment. Laterprofile/zone changes do not rewrite them, and safe projections avoid unnecessarycoordinate exposure.

17. Text-Address Fallback

Fallback remains available when the customer declines/cannot share location, orders fora remote address, uses an unsupported channel, or uses web/REST.

complete text address
    -> completeness validation
    -> provider-neutral forward geocoding
    -> reject ambiguous/coarse match
    -> PostGIS point check
    -> review/confirmation

PIN/locality may narrow candidates but never provides exact coverage. A locality/PINcentroid cannot be accepted as the customer's exact point; request a location pin/mapselection instead.

18. Staff/Admin Delivery-Zone API

Use specification 020's authenticated tenant-scoped staff boundary. Only authorizedadmins mutate zones.

GET    /staff/delivery-zones
GET    /staff/delivery-zones/{zone_id}
POST   /staff/delivery-zones
PATCH  /staff/delivery-zones/{zone_id}
POST   /staff/delivery-zones/{zone_id}/activate
POST   /staff/delivery-zones/{zone_id}/deactivate
POST   /staff/delivery-zones/check-point

Create/update accepts bounded GeoJSON Polygon/MultiPolygon. The backend must:

parameterize PostGIS SQL;

normalize to MultiPolygon/SRID 4326;

validate geometry type, rings, bounds, size, and vertices;

require trusted tenant/admin identity;

require idempotency and expected version for mutations;

audit safe metadata plus geometry hash/version, not customer PII; and

return concurrency conflicts rather than overwrite newer changes.

The check-point endpoint previews coverage without mutating customer/profile data.

19. Staff Mobile Zone Management

Extend the staff/admin app to list/filter zones, preview maps, draw/edit polygons orcentre/radius converted to polygon, test a point, confirm status changes, preserveunsaved edits, send longitude-first GeoJSON, and handle version conflicts.

If map editing is deferred, provide the guarded API plus migration/seed/manual GeoJSONconfiguration. Never hardcode production zones in prompts or business code.

20. Approved Outcomes and WhatsApp UX

Recommended IDs:

delivery-location-requested
delivery-location-serviceable
delivery-location-outside-area
delivery-serviceability-temporarily-unavailable
delivery-address-details-required
delivery-location-review
delivery-location-saved
saved-location-no-longer-serviceable
location-message-invalid
location-sharing-unavailable

The Response Node localizes approved meaning, asks one question, preserves approved areaand building details, and never exposes raw coordinates, geometry, zone UUID, or providerreferences. It must not claim serviceability during temporary failure.

Text instructions:

📍 WhatsApp mein attachment icon dabaiye, Location select kijiye, aur jahan delivery
chahiye us jagah ki location send kijiye.

If the selected Meta API version supports an approved interactive location request, thechannel adapter may render a provider-neutral REQUEST_LOCATION action. Other providersuse text fallback. Provider feature negotiation never belongs in the planner.

21. Configuration

DELIVERY_SERVICEABILITY_ENABLED=true
DELIVERY_LOCATION_REQUIRED_FOR_WHATSAPP=true
DELIVERY_ZONE_MAX_VERTICES=500
DELIVERY_ZONE_MAX_RINGS=20
DELIVERY_LOCATION_DECIMAL_PLACES=6
DELIVERY_SERVICEABILITY_TIMEOUT_SECONDS=3
REVERSE_GEOCODER_PROVIDER=disabled
REVERSE_GEOCODER_TIMEOUT_SECONDS=3

Validate bounds at startup. Readiness verifies PostGIS when enabled. Provider secretsremain in secret management. Disabling serviceability requires an explicit manual/textfallback and must never mean that every location is accepted.

22. Privacy, Security, and Retention

Explain use of the pin for coverage/delivery and obtain consent before long-term save.

Never request continuous/live location.

Do not infer home/work labels without customer confirmation.

Exclude coordinates, raw address, and full payload from prompts, logs, metrics, andtracing baggage.

Tenant-scope every zone/profile/order query.

Include saved location in customer export/deletion.

Delete checkpoint-only pins under checkpoint retention/abandonment rules.

Retain confirmed-order snapshots only under order/legal retention policy.

Send only coordinates to reverse geocoder and document provider processing.

Bound webhook bodies and GeoJSON nesting/vertices/processing time.

Require signed Meta input and authenticated authorized admin mutations.

Rate-limit repeated customer checks and staff preview/mutation endpoints.

23. Observability and Health

whatsapp_inbound_messages_total{message_kind,outcome}
delivery_serviceability_checks_total{source,outcome}
delivery_serviceability_duration_seconds{source,outcome}
delivery_zone_mutations_total{operation,outcome}
delivery_zone_geometry_rejections_total{reason}
reverse_geocoder_requests_total{provider,outcome}
saved_location_revalidations_total{outcome}

Never label metrics with coordinates, addresses, phone/customer/conversation IDs, zonenames/IDs, or free text. Readiness fails when required PostgreSQL/PostGIS is unavailable.Optional reverse-geocoder failure does not fail readiness when it is non-critical.

24. Migration and Backfill

Use Alembic to:

enable/verify PostGIS;

create delivery zones and spatial indexes;

add typed inbound location persistence;

extend saved addresses with coordinates, area, zone, version, status, and check time;

extend order delivery snapshots where required;

backfill text-only addresses as LEGACY_UNVALIDATED without coordinates; and

preserve existing UUID relationships and data.

Never call external geocoders from Alembic. Historical geocoding, if required later,must be a separate resumable reconciliation job. Downgrade must not silently discardspatial/profile data.

25. Testing Requirements

25.1 Meta/channel

Valid signed location normalizes exact coordinates.

Invalid signature writes nothing.

Missing/out-of-range/non-finite values are rejected.

Duplicate wamid creates one logical action.

Mixed webhook batches preserve atomic-valid-set behavior.

25.2 PostGIS/repository

Inside point matches; boundary point matches with ST_Covers; outside point does not.

Draft/inactive zones do not match.

Tenant A never matches Tenant B.

Overlap uses priority then stable ID.

Latitude/longitude reversal regression fails.

Invalid/self-intersecting/empty/oversized geometry is rejected.

Representative query plans use bounded spatial access.

25.3 Onboarding/profile

Text then location and location then text both retain valid pending fields.

Serviceable location requests building details.

Outside location is not saved.

Infrastructure failure is not called outside-area.

Review masks phone and omits coordinates.

Confirmation persists exactly once under replay/retry.

25.4 Checkout/order

Saved location revalidates at selection and confirmation.

Zone deactivation prevents a new order but preserves cart.

Temporary failure preserves recoverable checkout state.

Confirmed order snapshots destination; later edits do not rewrite it.

25.5 Staff, privacy, fallback

Auth/role/tenant checks protect every zone endpoint.

Mutations are idempotent and version-safe.

Longitude-first map coordinates are correct.

Logs/metrics contain no location PII.

Localized responses never expose raw coordinates.

Declining location uses text fallback.

Coarse geocoder centroid is never accepted as exact location.

26. Acceptance Criteria

Signed Meta location messages become typed provider-neutral inbound records.

Coordinates never come from the LLM and are hidden from planner prompts.

PostGIS active tenant zones make the serviceability decision.

Admins can configure coverage without changing prompts/code.

Serviceable pins continue to building-detail collection and review.

Unsupported pins cannot be saved as serviceable or used for an order.

Long-term location storage requires explicit consent.

Saved pins revalidate during checkout and immediately before confirmation.

Zone changes prevent stale new orders while preserving the cart.

Text fallback remains available.

Precise location is excluded from normal responses/logs/metrics.

Spatial, webhook, replay, privacy, localization, and live WhatsApp tests pass.

27. Recommended Implementation Order

Audit Meta normalization, inbound storage, capability context, saved addresses,checkout snapshots, staff auth, and migrations.

Add PostGIS development/test support and migration tests.

Implement delivery-zone schema, repository, geometry validation, and point lookup.

Add authenticated admin APIs and seed/manual GeoJSON configuration.

Normalize/persist Meta location messages and extend trusted execution context.

Implement location request/submission and building-detail onboarding state.

Extend saved-address persistence with explicit confirmation.

Add checkout/order revalidation and snapshots.

Add optional reverse geocoder and text fallback.

Add staff mobile zone editor or guarded operational configuration.

Add observability, privacy/deletion documentation, and full automated tests.

Run live WhatsApp acceptance tests for inside, boundary, outside, stale-zone, andinfrastructure-failure scenarios.

