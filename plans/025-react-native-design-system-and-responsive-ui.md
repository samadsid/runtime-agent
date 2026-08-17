# React Native Design System and Responsive UI Implementation Plan

## Outcome

Implement specification 025 as a presentation-only redesign of `staff-mobile`.
The existing authenticated staff workflows, Expo Router routes, TanStack Query
ownership, React Hook Form/Zod validation, API contracts, role checks, optimistic
versions, and mutation idempotency remain unchanged. All production screens will use
one typed, light/dark React Native design system and responsive composition at the
specified compact, medium, and expanded breakpoints.

The finished application will use bottom navigation on compact widths and a
persistent role-filtered rail on wider widths; present operational data through
shared accessible components; preserve usable layouts through resize, rotation,
large fonts, keyboard display, offline operation, refresh, and stale-data conflicts;
and remain suitable for an Android preview/release build.

No backend API, database schema, commerce service, customer graph, or domain rule is
changed by this milestone.

## Repository findings and implementation decisions

- Specification 021 and 024 functionality is present under `staff-mobile/app`, with
  stable routes for login, dashboard, orders, catalog, inventory, and account.
- `src/components/design-system` is a useful prototype, but it currently combines
  theme hooks, primitives, domain presentation, and raw typography in two files.
  Replace it incrementally with `src/design-system`, keeping a temporary re-export
  bridge so each route remains functional while it migrates.
- Current themes use blue/gray raw palettes and `useColorScheme` directly. Introduce
  a typed `ThemeProvider` with memoized semantic MeatUncle tokens. Follow system
  appearance for this milestone; do not persist a user override until a product
  decision requires the optional account setting.
- Use the platform system font. Do not add `expo-font`, gradients, haptics, or another
  styling/component runtime without a demonstrated need. Existing Expo StatusBar,
  safe-area context, and Ionicons are sufficient.
- Keep Ionicons behind one typed `AppIcon` wrapper. Feature screens and navigation
  may not import icon libraries directly.
- Use `useWindowDimensions()` and content-space calculations for all responsive
  decisions. Breakpoints are `<600`, `600-899`, and `>=900` dp; no device, platform,
  or orientation detection controls layout.
- Preserve the current route tree and deep links. Implement adaptive navigation as a
  custom Expo Router tab bar/layout: bottom bar for compact and a left rail framing
  the same slot/routes for medium and expanded widths. Do not create parallel phone
  and tablet screens.
- Introduce master/detail only where the current routing/query ownership can be
  shared without duplicate business state. Orders are the first candidate; catalog
  and inventory can use responsive list/detail composition after the primitive is
  proven. A full-screen route remains the compact behavior.
- Centralize domain-to-presentation mappings in feature adapters: order status,
  product lifecycle, stock state, inventory movement direction, and payment state.
  These adapters return semantic treatment and labels, never colors.
- Existing `Alert.alert` confirmations are replaced by a shared adaptive
  confirmation surface: bottom sheet on compact and centered dialog on expanded.
  The callback continues to invoke the existing mutation attempt/idempotency logic.
- Existing list and detail screens expose a number of inline style objects and raw
  colors, including the offline banner and modal overlay. Migrate them to tokens and
  stable `StyleSheet.create` definitions, especially inside virtualized render paths.
- Long operational collections remain virtualized. Convert inventory movement
  history from a mapped `ScrollView` to a `FlatList`/`SectionList`; avoid nested
  same-direction scrolling.
- The repository has Jest/component tests and Maestro smoke tests but no visual
  regression harness or lint script. Add a small screenshot workflow with fixed
  synthetic fixtures and define a lint/static-audit command rather than treating
  manual review as a substitute for the specification's quality gates.

## Design-system foundation

Create `staff-mobile/src/design-system` with a single public `index.ts` and prevent
feature imports from reaching theme internals.

### Theme

Add the following typed modules under `theme/`:

- `colors.ts` for the frozen raw palette and separately reviewed dark palette.
- `semantic-colors.ts` for the complete semantic color contract.
- `typography.ts`, `spacing.ts`, `radii.ts`, `shadows.ts`, and `motion.ts` for the
  approved scales and reduced-motion-safe duration policy.
- `breakpoints.ts` for `LayoutTier`, width boundaries, maximum canvas width, tier
  padding, readable form widths, and minimum grid item widths.
- `light-theme.ts` and `dark-theme.ts` implementing one exact `AppTheme` type.
- `theme-provider.tsx` and `use-theme.ts` to resolve system appearance, expose stable
  memoized values, and coordinate status/navigation bar colors.

Dark tokens must be selected by contrast measurement, not inversion. Add automated
contrast assertions for normal text, controls, focus borders, buttons, and every
semantic badge treatment in both themes.

### Primitives

Build small typed primitives under `primitives/`:

- `AppText` with only the approved semantic variants, colors, weights, alignments,
  font scaling, wrapping, and optional tabular numerals.
- `Box`, `Stack`, `Inline`, and `Divider` using constrained token props rather than
  arbitrary visual values.
- `AppIcon` with an allowlisted Ionicons name map, consistent size/color semantics,
  and required accessible labels for interactive use.
- `Screen` and `ResponsiveContainer` for background, safe areas, maximum width,
  tier padding, explicit scroll/keyboard ownership, and full-screen feedback states.

Avoid making primitives into an unrestricted style-prop language. Feature-specific
layout remains in local `StyleSheet.create` declarations that consume tokens.

### Responsive composition

Add `responsive/use-responsive-layout.ts`, `ResponsiveGrid`,
`AdaptiveNavigation`, and `MasterDetailLayout`.

- The hook returns live tier, usable content width, padding, rail width, form width,
  and reduced-motion information from `useWindowDimensions` and safe-area insets.
- `ResponsiveGrid` derives its column count from its measured content width after
  container padding and navigation rail, using a minimum item width and gap.
- `AdaptiveNavigation` renders at most five role-filtered destinations with icons,
  labels, selected state, safe-area padding, and account access without empty gaps.
- `MasterDetailLayout` uses route/query identifiers as selection, renders a compact
  full-screen route or expanded adjacent panes, and supplies an empty detail state.
  It does not copy query results into a second store.

## Shared component layer

Build the specification's shared components in coherent batches rather than as empty
wrappers:

1. Interaction: `Button`, `IconButton`, `FilterChip`, `Card`, and `ListRow`, including
   pressed, focused, disabled, selected, busy, and accessible states with 44/48 dp
   targets. Button loading must preserve dimensions and destructive actions must use
   the danger treatment.
2. Forms: `TextField`, `SearchField`, and `SelectField` with persistent labels, help,
   required/error association, leading/trailing icons, secure visibility controls,
   input modes, return-key traversal hooks, and focus handles for first-invalid-field
   behavior.
3. Operational display: `StatusBadge`, `MetricCard`, `SectionHeader`, `KeyValueRow`,
   and `Timeline`. Status/stock/movement mappings live in typed feature presentation
   adapters and always expose text plus icon where useful.
4. Feedback: `Banner`, `Snackbar`, `EmptyState`, `ErrorState`, `LoadingSkeleton`, and
   adaptive `ConfirmationSheet`/`ConfirmationDialog`. ErrorState accepts only safe
   error copy, optional request correlation ID, and a semantically valid action.
5. Shell: `AppHeader` and an action-bar primitive for compact sticky actions versus
   expanded side/header actions.

Replace the current `StateMessage`, `Loading`, `Field`, raw chips, `Alert` dialogs,
and screen-specific cards only after their consumers have migrated. Delete the old
implementation and bridge once imports reach zero.

## Application shell and global states

1. Wrap the app with `ThemeProvider` and safe-area integration in `app/_layout.tsx`.
   Apply active theme colors to Expo StatusBar and Android navigation/system surfaces.
2. Keep `NavigationGate` authoritative for restoration. Redesign restoration,
   connection failure, and configuration failure with branded full-screen shared
   states so protected/login content never flashes before validation.
3. Replace the protected `Tabs` presentation with `AdaptiveNavigation`, retaining the
   existing route names and ADMIN destination filtering. Confirm that STAFF users
   cannot focus or navigate to hidden catalog/inventory destinations through the UI,
   while backend authorization remains authoritative.
4. Move `OfflineBanner` into the shell below navigation/header. Use semantic warning
   tokens, announce connectivity changes once, keep cached safe data visible, and
   distinguish offline-with-data from offline-without-data at each query surface.
5. Add a development-only component-gallery route guarded by the build environment.
   It uses synthetic data to cover both themes, typography, component states,
   feedback, confirmation, timeline, and all layout tiers, and is unreachable in
   production builds.

## Screen migration

### Authentication and account

- Redesign login with keyboard-aware scrolling, persistent labeled email/password
  fields, accessible password visibility, first-invalid focus, generic credential
  failure, stable loading action, and an expanded constrained form/brand composition.
  Password state stays ephemeral and is cleared according to existing behavior.
- Present account identity, role, application metadata, environment (only outside
  production), support/privacy links only when configured, and logout as separate
  groups. Use adaptive confirmation for logout without implying an irreversible
  business operation. Do not expose tokens.

### Dashboard

- Add contextual identity/role information, responsive metric cards for fulfilment
  counts, the oldest confirmed queue, and ADMIN inventory risk using only existing
  endpoint data. Do not invent trends or activity.
- Use one column when font/width constraints require it, otherwise a responsive metric
  grid; medium/expanded layouts place queues side by side where minimum widths hold.
- Keep pull-to-refresh as background refresh, show initial skeletons only for initial
  loading, and give dashboard and inventory queries independent partial-error states.

### Orders

- Rebuild the order filter region with `SearchField`, date fields, removable filter
  chips, compact sheet overflow where necessary, and clear distinction between
  globally empty and filtered-empty results.
- Redesign `OrderRow` to prioritize reference, status, customer name, total, and
  waiting/update time. Remove masked phone from list summaries to meet specification
  025's tighter PII rule.
- Preserve cursor merge, stable keys, pull refresh, pagination footer, safe retries,
  and exact-reference/date validation. Use list skeletons shaped like order rows.
- Organize order details into status/action, summary/items, delivery, payment,
  timeline, and audit/context sections. Compact gets a safe-area action region;
  expanded gets a side action panel and optional master/detail list context.
- Replace confirmation alerts/modal code with adaptive confirmation. Keep cancellation
  visually separate and destructive; preserve permitted-action filtering, ambiguous
  same-key retry, stale-version refresh/review, access refresh, announcements, and
  query invalidation exactly.

### Catalog and product forms

- Build responsive catalog filters for search, lifecycle, category, and stock using
  the typed endpoint/filter support that actually exists; do not fabricate client-only
  business filtering. Show product name, SKU, lifecycle badge, price/unit, balances,
  and stock state through shared rows/cards.
- Keep compact as a virtualized list, use a measured two-column grid only when cards
  remain readable, and permit expanded dense list/master-detail composition. The add
  action remains ADMIN-only and never overlays pagination content.
- Refactor create/edit into grouped Identity, Selling, and Availability sections.
  Bind typed catalog options rather than silently selecting only the first option;
  use accessible selection sheets/dialogs and explain immutable unit behavior.
- Move edit validation to React Hook Form/Zod where practical without changing the
  request schema. Preserve drafts on API errors/rotation, focus the first invalid
  field, and add dirty-route/back discard confirmation. Stale product versions must
  refresh and require explicit review before another save/status action.
- Product details use shared status/balance components and adaptive confirmation for
  activation/deactivation, preserving reason and optimistic-version semantics.

### Inventory and movements

- Present active, low, out-of-stock, and inactive summaries when backed by current
  response data; otherwise show only available metrics. Make Sellable primary and On
  hand/Reserved supporting, with text that never implies reserved stock is available.
- Use responsive list/detail composition and an expanded balance/action panel beside
  virtualized movement history.
- Replace movement-type button stacks with an accessible selection control. Label
  receipts/corrections/reductions in operational language; exclude system-only
  movements from actions and retain their presence in history.
- Build adjustment review with product, direction, type, quantity, unit, current
  balance, and reason. Use warning emphasis for reductions/damage/wastage without
  presenting valid business actions as app errors.
- Preserve the current mutation key across ambiguous network retries, reset it only
  when inputs change or the result is authoritative, and retain version checks.
  Standardize stale balance conflict UI and require review before resubmission.
- Render movements through `Timeline`/virtualized list with type, signed delta,
  before/after values, reason, actor/source when provided by the contract, and
  timestamp. Missing endpoint fields are not inferred.

## State, accessibility, privacy, and performance rules

- Define an explicit state matrix for every query surface: initial loading, background
  refresh, empty, filtered empty, offline with cache, offline without data,
  recoverable error, authorization/session error, contract/update-required error,
  and stale conflict. Mutations additionally define disabled, pending, unambiguous
  success, ambiguous retry, and authoritative failure.
- Announce meaningful dynamic outcomes through bounded live regions or
  `AccessibilityInfo`; avoid duplicate announcements from nested feedback components.
- Validate names, roles, hints, busy/disabled/selected states, focus order, modal title
  focus, minimum targets, large-font wrapping, contrast, and reduced-motion behavior.
- Keep critical reference, status, quantity, total, stock, and action text wrappable.
  Only low-priority metadata may truncate.
- Do not add PII to list rows, navigation titles, analytics, fixtures, screenshots,
  logs, or persistence. Query cache remains memory-only and clears through the
  existing authentication lifecycle.
- Keep theme state presentation-only. Do not place query results, drafts, selection,
  roles, or business state in the theme/navigation providers.
- Memoize provider values and presentation maps; keep invariant styles outside render;
  avoid inline allocations in list renderers; preserve FlatList cursor deduplication;
  and measure release-mode launch, navigation, scrolling, and memory before/after.

## Testing and tooling

### Automated component and unit tests

- Token completeness and light/dark contrast; exact breakpoint boundaries and tier
  values; responsive grid columns based on usable width.
- AppText variants; button pressed/loading/disabled accessibility; field labels,
  help, errors, secure toggle, and focus; chips; badge mapping completeness; banners;
  skeletons; state components; confirmations; timeline entries; navigation selection.
- Compile-time type fixtures or `tsc` assertions proving arbitrary typography,
  spacing, colors, and icon names are rejected.

### Screen tests

- Render representative widths of 360, 412, 600, 768, 900, and 1280 dp and assert
  navigation mode, column count, readable form width, master/detail activation, and
  presence of critical actions.
- Cover login, dashboard roles, orders, catalog, product forms, inventory adjustment,
  movement history, account, and all state-matrix branches in both themes where
  semantics differ.
- Assert role-filtered navigation, no list PII, stale-version review, and exact reuse
  of ambiguous mutation idempotency keys.
- Test resizing with mounted form/filter/selection state to prove drafts and route
  selection survive recomposition.

### Visual, end-to-end, and device verification

- Add deterministic synthetic screenshot fixtures for login, dashboard, order list,
  order detail, catalog list, product form, inventory detail, adjustment confirmation,
  and movement history in both themes at selected fixed widths/font scales. Baseline
  changes require explicit visual review.
- Extend Maestro smoke flows for login, an order transition, product edit, inventory
  adjustment confirmation, role navigation, logout, and rotation-safe route behavior.
- Manually verify TalkBack and large-font completion for login, order transition,
  product edit, and inventory adjustment.
- Run portrait/landscape, light/dark, large font, slow/interrupted network, and
  preview/release checks on one small Android phone and one large phone/tablet profile.
- Record cold launch, navigation, list-scroll, input responsiveness, and memory notes
  for a mid-range release build.

### Static and build quality gates

Add or document repository-equivalent commands for:

- `npm run typecheck`
- `npm test`
- `npm run lint` plus static checks for raw feature hex colors, direct icon-library
  imports, fixed screen-width APIs, scattered color-scheme branching, and unsafe
  inline styles in list paths
- Expo dependency validation and `npm run doctor`
- Maestro Android smoke tests
- preview/release Android build

Run existing backend tests as a regression guard only; this milestone should not
require backend test changes.

## Implementation sequence

1. Inventory current routes, styles, state branches, PII surfaces, accessibility
   behavior, and performance; capture approved pre-migration behavioral and visual
   baselines.
2. Add typed palette, semantic themes, scales, provider, system bars, breakpoint hook,
   contrast tests, and the temporary legacy design-system re-export bridge.
3. Build/test primitives and the development-only component gallery.
4. Build/test shared interaction, form, operational display, feedback, confirmation,
   and shell components plus presentation adapters.
5. Implement/test ResponsiveContainer, ResponsiveGrid, adaptive navigation, and the
   initial MasterDetailLayout without changing route identities.
6. Migrate launch/session restoration, login, protected shell, offline handling, and
   account; verify authentication and role-navigation behavior.
7. Migrate dashboard and order list/detail/action flows; verify PII boundaries,
   cursor behavior, stale conflicts, and same-key ambiguous retries.
8. Migrate catalog list, product details, create/edit forms, option selection,
   lifecycle confirmation, dirty-form protection, and optimistic conflict review.
9. Migrate inventory overview/detail, adjustment review, and virtualized movement
   timeline while preserving balance/version/idempotency semantics.
10. Complete responsive, dark-theme, large-font, reduced-motion, accessibility,
    visual-regression, Maestro, and physical-device coverage.
11. Remove the legacy design-system bridge and superseded styles; audit production
    screens for raw visual values, direct icons, duplicate primitives, fixed widths,
    nested scrolling, and unauthorized/PII presentation.
12. Run all quality gates, build a signed preview, record performance/device results,
    and update `docs/architecture.md`, `docs/decisions.md`, and
    `docs/current-status.md` with the finalized presentation architecture and status.

## Acceptance verification matrix

### Architecture and regression

- No backend/API/database/domain changes are required; all existing staff routes and
  deep links still resolve.
- Authentication, permissions, query ownership, optimistic versions, inventory/order
  invariants, and idempotency behavior match the pre-redesign tests.
- Every production screen imports design-system APIs only from its public index.

### Visual system and responsive behavior

- Every light/dark token resolves and semantic meaning remains consistent with tested
  contrast.
- Widths 599/600 and 899/900 switch at the exact frozen boundaries.
- Compact uses bottom tabs; medium/expanded use a rail; expanded content is centered
  at a 1440 maximum and forms remain approximately 560-720 wide.
- Grid columns honor usable content width and minimum card width; critical content and
  actions neither clip nor become unreachable in portrait, landscape, or large fonts.
- Resize/rotation preserves current route, filters, drafts, and selected detail.

### Interaction and state quality

- All controls expose accessible name, role, state, hint where needed, and minimum
  target size; color is never the only status/stock indicator.
- Loading, refresh, empty, filtered-empty, offline, error, stale, success, disabled,
  and ambiguous mutation states use shared patterns with valid actions.
- Keyboard display keeps focused fields and submission reachable; invalid submission
  exposes/focuses the first error; dirty forms require discard confirmation.
- Destructive cancellation/deactivation and stock reduction are visually distinct
  from ordinary forward progress and always receive explicit review.

### Privacy and release readiness

- Customer PII is absent from list summaries, navigation titles, analytics, logs,
  screenshots, synthetic fixtures, and new persistence; staff tokens remain hidden.
- Long lists are virtualized with stable keys, no duplicate cursor items, no nested
  same-direction scroll, and no obvious release-mode input/scroll regression.
- Typecheck, lint/static audits, Jest, Expo checks, Maestro, visual review, TalkBack,
  physical-device checks, and Android preview/release build all pass.
