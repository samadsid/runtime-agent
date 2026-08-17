React Native Design System and Responsive UI Specification

1. Purpose

Transform the existing functional staff-mobile application into a polished,consistent, responsive, and accessible operational product for MeatUncle staff andadministrators.

This milestone changes presentation and interaction quality, not commerce behavior:

Existing authenticated mobile flows
    -> centralized visual language
    -> reusable design-system components
    -> responsive screen compositions
    -> accessible interaction states
    -> production-quality Android experience

React Native does not use browser CSS as its primary styling model. The implementationuses typed React Native StyleSheet styles, theme tokens, and responsive layoututilities. No screen may become a collection of unrelated inline colors, dimensions,and typography rules.

2. Prerequisites

Functional React Native staff/admin application from specification 021.

Catalog and inventory administration flows from specification 024 implemented orrepresented by stable mobile routes/components.

Existing Expo, TypeScript, Expo Router, TanStack Query, React Hook Form, Zod, andSecureStore setup.

Existing staff authentication, order, catalog, and inventory API contracts.

At least one small Android phone/emulator and one larger Android device/tablet profilefor verification.

3. Goals

Establish a recognizable MeatUncle staff-app visual identity.

Make every screen feel like one coherent application.

Improve information hierarchy for time-sensitive fulfilment work.

Make status, risk, stock, and available actions understandable at a glance.

Support compact phones, large phones, tablets, portrait, and landscape layouts.

Support system light/dark appearance without losing semantic meaning.

Support large system font sizes and accessible touch/reading behavior.

Replace repeated screen-specific styling with reusable tokens and components.

Give loading, empty, error, offline, success, disabled, and stale-data states equaldesign attention.

Preserve performance on ordinary Android devices.

Preserve existing authentication, permissions, idempotency, concurrency, and privacybehavior.

Keep shared styles portable enough for a later iOS release.

4. Non-goals

Changing backend APIs, database schemas, business rules, roles, or permissions.

Rewriting the app in another framework.

Introducing browser CSS, DOM elements, or web-only layout assumptions.

Replacing Expo Router, TanStack Query, React Hook Form, or the existing API client.

A customer-facing shopping application redesign.

Marketing animation, video backgrounds, 3D effects, or decorative motion that slowsoperational work.

A generic white-label theme editor.

User-uploaded themes or arbitrary per-tenant colors.

Full localization of staff UI in this milestone.

Building separate phone and tablet codebases.

Pixel-identical Android and iOS rendering.

Adding product photos or media management.

Changing authorization because an action is visually hidden.

5. Design Principles

5.1 Operational clarity first

The staff app is a work tool. It should feel warm and branded without hiding importantdata behind decorative surfaces. Status, order reference, product identity, quantity,stock, and the next permitted action receive visual priority.

5.2 Calm by default, emphasis by meaning

Neutral surfaces carry most content.

Brand burgundy identifies navigation, focus, and primary actions.

Green is reserved for successful/healthy meaning.

Amber is reserved for warning/low-stock meaning.

Crimson is reserved for destructive/error meaning.

Blue is reserved for informational/in-progress meaning.

Color never acts as the only status indicator.

5.3 Progressive disclosure

Lists show enough information to choose an item. Details screens reveal operationaldata and actions. Rare or destructive actions require explicit confirmation ratherthan competing with the primary workflow.

5.4 Reusable before clever

A screen uses established primitives and patterns. A new component is introduced onlywhen existing components cannot represent the interaction clearly.

5.5 Responsive composition, not scaled screenshots

Responsive layouts rearrange information according to available width. They do notsimply enlarge every phone component on a tablet.

6. Frozen Technical Decisions

Use:

React Native StyleSheet.create for component styles.

A typed theme provider for light/dark semantic tokens.

useWindowDimensions() for live responsive decisions.

react-native-safe-area-context for screen insets.

Expo Router for responsive navigation composition.

Existing Expo-supported vector icons through one internal AppIcon wrapper.

React Native FlatList/SectionList for operational lists unless measured data provesanother virtualized list is required.

Existing form and query tools from specification 021.

Allowed Expo enhancements when compatible with the pinned SDK:

expo-font only if a bundled brand typeface is intentionally selected;

expo-haptics for restrained confirmation/error feedback;

expo-linear-gradient only for limited branded hero/header surfaces;

expo-navigation-bar and expo-status-bar for system-bar theme integration.

Do not add NativeWind, a large component framework, or another styling runtime in thismilestone. The existing application is already built; adding a second styling paradigmwould increase migration and maintenance cost without being necessary for a coherentdesign system.

Do not scatter raw hex values, font sizes, spacing numbers, radii, shadows, or z-indexesthrough feature screens. Components consume tokens.

7. Design-System Architecture

Recommended structure:

staff-mobile/src/design-system/
  theme/
    colors.ts
    semantic-colors.ts
    typography.ts
    spacing.ts
    radii.ts
    shadows.ts
    motion.ts
    breakpoints.ts
    light-theme.ts
    dark-theme.ts
    theme-provider.tsx
    use-theme.ts
  primitives/
    AppText.tsx
    Box.tsx
    Stack.tsx
    Inline.tsx
    Divider.tsx
    AppIcon.tsx
    Screen.tsx
    ResponsiveContainer.tsx
  components/
    Button.tsx
    IconButton.tsx
    TextField.tsx
    SelectField.tsx
    SearchField.tsx
    Card.tsx
    StatusBadge.tsx
    FilterChip.tsx
    MetricCard.tsx
    ListRow.tsx
    EmptyState.tsx
    ErrorState.tsx
    LoadingSkeleton.tsx
    Banner.tsx
    Snackbar.tsx
    ConfirmationSheet.tsx
    SectionHeader.tsx
    KeyValueRow.tsx
    Timeline.tsx
    AppHeader.tsx
  responsive/
    use-responsive-layout.ts
    ResponsiveGrid.tsx
    AdaptiveNavigation.tsx
    MasterDetailLayout.tsx
  index.ts

Feature screens import from the design-system public index rather than reaching intotheme internals.

8. Brand Direction

The visual direction is warm, trustworthy, premium, and operational. Avoid cartoonmeat graphics, aggressive red saturation, excessive gradients, or restaurant-menustyling. This is a staff operations app, not a consumer advertisement.

8.1 Core palette

Initial light palette:

export const palette = {
  burgundy900: "#5F1518",
  burgundy800: "#741A1E",
  burgundy700: "#8F2025",
  burgundy600: "#A6292E",
  burgundy100: "#F8E5E4",
  burgundy50: "#FDF3F2",

  cream50: "#FFF9F5",
  warmWhite: "#FFFCFA",
  white: "#FFFFFF",

  charcoal950: "#1E1917",
  charcoal800: "#342D2A",
  charcoal600: "#6E625D",
  charcoal400: "#9A8E88",

  stone300: "#D8CEC9",
  stone200: "#E7DFDA",
  stone100: "#F1EBE7",

  green700: "#237A4B",
  green100: "#DCF3E6",
  amber700: "#A65E00",
  amber100: "#FFF0CF",
  blue700: "#245EA8",
  blue100: "#E1EEFF",
  crimson700: "#C3313B",
  crimson100: "#FBE2E4",
};

Raw palette values are never selected directly in feature screens. Semantic tokens mapintent to palette.

8.2 Semantic light tokens

export const lightColors = {
  background: palette.cream50,
  surface: palette.white,
  surfaceRaised: palette.warmWhite,
  surfaceMuted: palette.stone100,
  overlay: "rgba(30, 25, 23, 0.48)",

  textPrimary: palette.charcoal950,
  textSecondary: palette.charcoal600,
  textDisabled: palette.charcoal400,
  textOnBrand: palette.white,

  border: palette.stone200,
  borderStrong: palette.stone300,
  focus: palette.burgundy700,

  brand: palette.burgundy700,
  brandPressed: palette.burgundy900,
  brandSubtle: palette.burgundy50,

  success: palette.green700,
  successSubtle: palette.green100,
  warning: palette.amber700,
  warningSubtle: palette.amber100,
  info: palette.blue700,
  infoSubtle: palette.blue100,
  danger: palette.crimson700,
  dangerSubtle: palette.crimson100,
};

8.3 Dark theme

The dark theme uses warm near-black surfaces, softened borders, off-white text, andadjusted semantic colors with verified contrast. It is not created by mechanicallyinverting the light palette.

Requirements:

Default theme follows the Android system preference.

Account settings may offer System, Light, and Dark if preference persistence isimplemented safely.

Status meaning remains consistent across themes.

Shadows reduce in dark mode; borders and tonal surface separation carry hierarchy.

System status/navigation bars match the active theme.

Exact dark tokens must be contrast-tested before freezing; raw unverified values mustnot be copied from a design mockup directly into production.

9. Typography

Use the platform system font for the first redesign unless a properly licensed,bundled, performance-tested brand font is approved. System fonts improve startup,language coverage, and accessibility.

Typed scale:

Token

Compact size/line

Expanded size/line

Typical use

display

30/38

36/44

Login welcome or rare hero number

titleLarge

24/32

28/36

Screen title

titleMedium

20/28

22/30

Card/section title

titleSmall

17/24

18/26

List-row primary text

bodyLarge

16/24

17/26

Primary body/form input

bodyMedium

14/21

15/22

Secondary content

labelLarge

14/20

15/21

Buttons/chips

labelSmall

12/17

12/17

Metadata/captions

Rules:

Use semantic AppText variants, not arbitrary font sizes.

Respect user font scaling.

Do not cap font scaling globally to make layouts easier.

Numbers in metrics may use tabular numerals when available.

Avoid all-caps paragraph or button labels.

Truncate only low-priority list metadata; critical status, quantity, totals, andactions must wrap or reflow.

10. Spacing, Shape, and Elevation

Spacing scale:

export const spacing = {
  0: 0,
  1: 4,
  2: 8,
  3: 12,
  4: 16,
  5: 20,
  6: 24,
  8: 32,
  10: 40,
  12: 48,
  16: 64,
};

Radius scale:

export const radii = {
  small: 8,
  medium: 12,
  large: 18,
  xlarge: 24,
  pill: 999,
};

Rules:

Compact screen horizontal padding: 16.

Large-phone padding: 20–24 according to layout tier.

Expanded/tablet content uses a centered max width rather than endless stretching.

Minimum interactive target is 44x44 density-independent pixels; prefer 48x48.

Use no more than three meaningful elevation levels.

Android elevation and iOS shadow values live behind semantic shadow tokens.

Borders remain visible when shadows are unavailable or reduced.

11. Responsive Layout Model

Use live window width, not one-time Dimensions.get("window") values.

type LayoutTier = "compact" | "medium" | "expanded";

compact:  width < 600
medium:   600 <= width < 900
expanded: width >= 900

These are layout breakpoints in density-independent pixels, not device-name detection.Do not use Platform, phone model, or orientation alone to choose composition.

11.1 Compact

Bottom tab navigation.

One-column cards and lists.

Full-screen detail and form routes.

Full-width primary actions with safe-area spacing.

Filters open in a sheet when they do not fit inline.

Metric cards use one or two columns depending on actual minimum card width.

11.2 Medium

Navigation rail or appropriately spaced tabs.

Two-column dashboard and catalog grids where content remains readable.

Wider forms constrained to a readable width.

Optional list/detail split when enough width remains after navigation.

Filters may remain inline with a collapsible overflow.

11.3 Expanded

Persistent navigation rail.

Centered application canvas with a documented maximum width, initially 1440.

Two-pane master/detail for orders, catalog, and inventory where it improves speed.

Two or three content columns based on component minimum width, not a fixed tabletcount.

Form content remains approximately 560–720 wide while supporting side context.

11.4 Orientation and resizing

Recompute layout when window dimensions change.

Preserve selected route, filters, draft form data, and safe scroll context duringrotation.

Do not use orientation lock unless a narrowly documented operational screen requiresit; none is expected in this milestone.

Avoid layouts that are usable in portrait but clip actions in landscape.

12. Responsive Layout Primitives

12.1 ResponsiveContainer

Responsibilities:

safe-area-aware outer frame;

tier-specific horizontal padding;

centered maximum content width;

background and keyboard behavior hooks;

optional scrolling owned explicitly by caller.

12.2 ResponsiveGrid

Accepts minimum item width and spacing, then calculates valid columns from availablecontent width. Never calculate from global screen width while ignoring padding ornavigation rails.

12.3 AdaptiveNavigation

Bottom tabs on compact layouts.

Navigation rail on medium/expanded layouts.

Role-filtered destinations.

Accessible selected state with icon and label.

No more than five primary destinations; move secondary actions into account/overflow.

12.4 MasterDetailLayout

Full-screen route transition on compact.

Optional adjacent list/detail panes on expanded layouts.

Stable selected item and back behavior.

Detail pane empty state when no item is selected.

No duplicate API business state; both compositions use the same query hooks.

13. Core Component Contracts

13.1 AppText

semantic typography variant;

semantic color;

accessible font scaling;

optional weight/alignment only from allowed values;

no arbitrary raw font size prop.

13.2 Button

Variants:

primary
secondary
tertiary
danger

States:

default
pressed
focused
disabled
loading

Rules:

Loading preserves button dimensions.

Disabled state uses opacity plus semantic styling, not opacity alone.

Icon placement and spacing are standardized.

Destructive actions never use the same treatment as ordinary primary progress.

Buttons expose accessible role, label, hint, and busy/disabled state.

13.3 Form fields

TextField, SearchField, and SelectField provide:

label outside the value;

optional help text;

required indication;

error message associated with the field;

leading/trailing icon slots;

focus, filled, disabled, and error states;

at least 48-high touch/input area;

correct keyboard/input mode;

secure password visibility control with accessible labels.

Placeholder text never replaces a persistent label.

13.4 Card

Variants:

default
outlined
interactive
tonal

Cards group related information. Avoid nested cards and excessive rounded rectangles.Interactive cards have visible pressed/focus states and one clear primary target.

13.5 StatusBadge

Each badge includes a text label and optional icon, never color alone. Map domain statuscentrally:

Meaning

Treatment

Confirmed / pending action

brand or info

Preparing / in progress

info

Out for delivery

info with distinct label/icon

Delivered / active / healthy

success

Low stock

warning

Out of stock / failed / cancelled

danger or neutral terminal treatment

Inactive

neutral

The exact mapping lives in one domain-presentation adapter, not repeated screen logic.

13.6 Feedback components

Banner: persistent contextual warning/offline/stale state.

Snackbar: short non-critical success/information feedback.

ConfirmationSheet: explicit action confirmation on compact screens.

ConfirmationDialog: accessible centered dialog where expanded layouts justify it.

ErrorState: safe failure explanation, request correlation ID when appropriate, andvalid retry action.

Never show success solely as a disappearing toast when the screen's authoritativestate can visibly update.

14. Iconography and Imagery

Use one supported icon family through AppIcon.

Do not mix outlined, filled, emoji, and unrelated icon styles in the same navigationsystem.

Icons supplement text for operational actions; ambiguous icon-only actions requireaccessible labels and usually visible text.

Reserve illustrations for login, empty states, and rare onboarding moments.

Do not use decorative product photography as a substitute for product data in thisstaff milestone.

App logo/icon assets must be crisp at required Android sizes and include safe padding.

15. Motion and Haptics

Motion reinforces state change without delaying work:

120–180 ms for press/focus micro-interactions;

180–260 ms for sheets, banners, and route-adjacent transitions;

subtle skeleton shimmer or static pulse, never multiple competing loaders;

restrained haptic feedback after confirmed success, warning, or destructive action.

Rules:

Honor reduced-motion accessibility preference where exposed by the platform.

Do not animate large lists continuously.

Do not animate an authoritative status change before backend success.

Avoid layout animation that causes actionable rows to move under a user's finger.

Haptics are enhancement only; all outcomes remain visible and announced.

16. Screen Redesign Requirements

16.1 Launch and session restoration

Brand mark or wordmark with calm background.

One centered loading treatment.

No flash of login or protected content before session validation completes.

Error/retry state uses the same full-screen state pattern as the rest of the app.

16.2 Login

Compact:

warm branded background or subtle tonal header;

centered form card only when it fits naturally, otherwise an integrated screen;

clear Staff sign in title and short operational subtitle;

email and password fields with persistent labels;

prominent primary sign-in action;

safe keyboard avoidance and scroll behavior;

generic credential error near the form without revealing account existence.

Expanded:

constrained form pane and restrained branded companion pane;

no oversized decorative panel that crowds the form;

form remains keyboard and screen-reader navigable.

16.3 Application shell

Consistent app header with screen title and only relevant actions.

Compact bottom navigation respects gesture/navigation safe area.

Medium/expanded navigation rail displays brand, destinations, selected state, andaccount access.

Role-filtered destinations never leave empty visual gaps.

Offline/session banners appear below navigation/header without covering content.

16.4 Dashboard

Information order:

contextual greeting and role/tenant label;

operational summary metrics;

oldest/actionable order queue;

low/out-of-stock inventory for admins;

recent safe activity only if backed by an existing endpoint.

Metric cards include label, value, icon, semantic accent, and optional trend/context.Do not invent trend percentages without backend data.

Responsive layout:

compact: two-column metrics only when large fonts still fit; otherwise one column;

medium: two-column content sections;

expanded: metric row/grid plus side-by-side actionable queues.

16.5 Order list

Search field and status filters remain discoverable.

Active filters display as removable chips.

Each row/card emphasizes order reference, current status, customer name, total, andwaiting time/update time.

Full phone/address remains absent from list cards.

Compact layouts use one vertical list.

Expanded layouts may use master/detail rather than tiny multi-column cards.

Pull-to-refresh, pagination footer, empty results, and load failure use standardizedcomponents.

16.6 Order details

Sections:

status and permitted next action
order summary/items
delivery details
payment summary
status timeline
audit/context allowed to staff

Primary valid action remains reachable without covering content.

Compact may use a safe-area sticky bottom action bar.

Expanded uses a side action panel or header action region.

Delivery PII does not appear in navigation titles, screenshots generated by tests,analytics, or debug logs.

Cancellation remains visually destructive and separated from forward fulfilment.

16.7 Catalog list

Search, lifecycle, category, and stock filters use the shared filter pattern.

Product cards/rows show name, SKU, status, price/unit, sellable/on-hand/reserved stock,and low-stock state with clear hierarchy.

Compact uses list rows/cards; medium may use two-column cards; expanded may use adense but accessible data list or master/detail layout.

Floating or header Add product action appears only for authorized admins and neverobscures pagination/content.

16.8 Product create/edit

Group fields:

Identity: name, SKU, category
Selling: price, currency, unit
Availability: lifecycle status, threshold, display order

Options come from the typed catalog options endpoint.

Use searchable selection sheets/dialogs when option lists need them.

Explain locked unit behavior before the user attempts an invalid edit.

Dirty-form navigation requires discard confirmation.

Compact form is one column; expanded may use two columns for related short fields butkeeps long fields and validation readable.

Submit action remains visible without creating two competing primary actions.

16.9 Inventory overview and product inventory detail

Summary cards distinguish active, low, out-of-stock, and inactive products.

Balance display gives Sellable primary emphasis, with On hand and Reserved assupporting values.

Never imply reserved stock is available.

Movement actions use clear increase/decrease language and semantic icons.

System-only movements never appear as buttons.

Expanded layouts show balance/action panel alongside recent movement history.

16.10 Inventory adjustment

Movement type is selected before quantity/reason.

Increase actions use neutral/success treatment; reductions use warning treatment;damage/wastage confirmation receives stronger warning without being styled like appfailure.

Show unit beside quantity and current balance context.

Confirmation summarizes product, movement, quantity, unit, and direction.

Submission preserves existing version/idempotency behavior.

Stale balance opens standardized conflict UI and requires review before a new action.

16.11 Movement timeline

Vertical timeline on compact screens.

Dense chronological list or two-pane detail on expanded screens.

Each entry shows type label, signed quantity/deltas, before/after summary, reason,actor/source, and timestamp.

Color/icon reinforces but never replaces text.

Long reasons wrap; they are not truncated into ambiguity.

16.12 Account

Staff identity and role are presented clearly without exposing token data.

Theme selection appears here if user override is implemented.

App version, build environment for non-production, privacy/support links whereconfigured, and logout are grouped separately.

Logout is visually clear but not styled as an irreversible destructive businessaction.

17. Loading, Empty, Error, and Offline States

Every data surface defines:

initial loading
background refreshing
empty data
filtered empty data
offline with cached in-memory data
offline without data
recoverable server error
authorization/session error
contract/update-required error
stale concurrency conflict

Rules:

Skeletons resemble the eventual layout and avoid content jump.

Do not show a full-screen spinner for background refresh.

Empty state explains what is empty and offers a valid next action only when permitted.

Filtered empty state offers Clear filters; it does not imply the catalog/order queueis globally empty.

Offline banner does not erase already rendered safe in-memory data.

Error copy is concise, safe, and includes a retry only when retry semantics allow it.

Mutation ambiguity follows existing idempotency rules, never a generic new-key retry.

18. Forms and Keyboard Responsiveness

Use KeyboardAvoidingView/scroll composition appropriate to the platform and screen.

Focused inputs must remain visible above the keyboard.

Submit actions must remain reachable with large fonts and smaller screens.

Use keyboardShouldPersistTaps intentionally on scrollable forms/options.

Decimal fields use an appropriate decimal keyboard but still validate pasted input.

Return/next actions move through fields logically.

Validation summary/focus moves to the first invalid field when submission fails.

Do not hide errors only below the fold.

Preserve draft state through rotation and recoverable API failures.

Password values follow the existing security lifecycle and are never persisted.

19. Accessibility Requirements

Target WCAG 2.2 AA principles where applicable to native mobile UI.

Normal text contrast at least 4.5:1; large text/UI treatment follows applicablecontrast requirements.

Touch targets at least approximately 44x44, preferably 48x48.

Every interactive control has an accessible name, role, state, and useful hint wherebehavior is not obvious.

Icon-only controls have explicit labels.

Screen reader traversal follows visual/logical order.

New screen and modal titles receive appropriate accessibility focus.

Dynamic success/error/status changes are announced without repeated noise.

Status and stock meaning use text/icon plus color.

Forms associate labels, help, required state, and errors.

Support large font settings without clipped values or unreachable actions.

Reduced-motion preference disables nonessential movement.

Test with Android TalkBack, not only automated accessibility assertions.

20. Privacy and Security Preservation

The redesign must not add customer PII to list summaries, analytics, crash reports,screenshots, or persistent storage.

Decorative logging/debug tools must not capture authorization headers or complete APIpayloads.

Query caches remain memory-only and clear on logout/session expiry.

Sensitive order details use the existing authenticated route and authorizationbehavior.

Theme preferences may persist; tokens, customer data, order data, and form secrets maynot be stored with them.

Third-party UI/analytics libraries require privacy review before addition.

UI permission checks remain convenience only; backend authorization stays mandatory.

21. Performance Requirements

Avoid rerendering the entire application when one semantic token or query itemchanges.

Memoize theme objects and stable style factories where measurement justifies it.

Keep screen styles outside render where they do not depend on theme/dimensions.

Virtualize long order/product/movement lists.

Provide stable keys and cursor merging without duplicates.

Avoid nested same-direction scroll views.

Avoid measuring every list item synchronously.

Bundle only required font weights and image sizes.

Prefer vector icons to many bitmap variants.

Test release/preview builds on a mid-range physical Android device; development modeperformance is not the acceptance benchmark.

Record baseline and post-redesign cold launch, navigation, list-scroll, and memoryobservations. The redesign must not introduce obvious input or scroll lag.

22. Theme and Presentation State

Allowed persisted UI preference:

type ThemePreference = "system" | "light" | "dark";

Store this non-sensitive preference separately from authentication. Resolve:

system preference + app override -> active theme

Do not place business state in the theme provider. Domain-to-presentation mapping, suchas order status to badge treatment, belongs in feature presentation adapters that usesemantic design tokens.

23. Development Component Gallery

Add a development-only component-gallery route or screen that demonstrates:

theme colors and typography;

buttons and all states;

fields and validation states;

status badges and filter chips;

cards and metric cards;

banners, snackbars, empty/error states;

skeletons;

confirmation sheet/dialog;

timeline entries;

compact, medium, and expanded containers.

Requirements:

It is unavailable in production builds.

It contains synthetic data only, never copied production PII.

It accelerates visual review but is not a second implementation of feature screens.

24. Testing Strategy

24.1 Token and component tests

Every light/dark semantic token resolves.

No status maps to an undefined treatment.

Typography and spacing variants reject arbitrary unsupported values at compile time.

Button loading/disabled/pressed behavior and accessibility state.

Field labels, help, error, secure toggle, and focus behavior.

Badge text and icon remain present without relying on color.

Banner, empty, error, skeleton, and confirmation behavior.

24.2 Responsive tests

For representative widths, test:

360 compact phone
412 large phone
600 boundary
768 medium tablet
900 expanded boundary
1280 expanded tablet/landscape

Verify:

correct layout tier;

correct navigation type;

column count respects minimum component width;

no clipped critical text/action;

form width remains readable;

rotation preserves draft/selection;

master/detail activates only at intended width;

safe areas and keyboard do not cover actions.

24.3 Screen behavior tests

Login in light/dark, keyboard open, error, loading, and large-font states.

Dashboard cards and queues across roles and widths.

Order list/detail/status actions and destructive cancellation distinction.

Catalog list/form/options/status and dirty-form confirmation.

Inventory balances, movement actions, adjustment confirmation, and timeline.

Every screen's initial loading, empty, filtered empty, error, offline, and refreshstate.

Role-filtered navigation does not expose unauthorized admin destinations.

Existing stale-version and idempotent-retry UX remains intact.

24.4 Accessibility tests

Automated accessible name/role/state assertions for shared components.

Android TalkBack traversal on login, dashboard, one list, one detail, one form, andone confirmation flow.

Large-font verification at commonly supported enlarged settings.

Light/dark contrast verification for text, borders, focus, badges, and buttons.

Reduced-motion verification.

Hardware keyboard/focus verification on tablet/emulator where available.

24.5 Visual regression

Capture reviewed screenshot baselines using fixed synthetic data, fixed emulatordimensions, pinned font scale, and both themes for selected stable screens:

login
dashboard
order list
order detail
catalog list
product form
inventory detail
adjustment confirmation
movement history

Visual snapshots supplement behavioral tests; they do not replace accessibility,interaction, or responsive assertions. Update baselines only after explicit review.

24.6 Physical-device acceptance

Verify on at least:

one small/common Android phone;

one large Android phone or tablet profile;

portrait and landscape;

light and dark system themes;

large font setting;

slow/interrupted network;

preview/release build rather than only Expo Go development mode.

25. Migration Strategy

Refactor incrementally so visual work does not break working business flows:

Inventory existing colors, styles, repeated components, layouts, and navigation.

Freeze screenshots and behavioral tests for current critical flows.

Implement tokens, theme provider, primitives, and component gallery.

Replace global app shell/navigation and shared feedback states.

Migrate authentication/account.

Migrate dashboard.

Migrate orders list/detail/actions.

Migrate catalog/product forms.

Migrate inventory/movement flows.

Remove superseded style constants/components only after all consumers migrate.

Rules:

Do not combine visual migration with API contract redesign.

Keep each feature functional at every merge point.

Avoid a long-lived branch that rewrites the entire app before testing.

Preserve route names/deep links unless an explicit migration is documented.

Search for remaining raw colors, unapproved spacing, and duplicate primitives beforeacceptance.

26. Quality Gates

The following commands or their repository equivalents must pass:

typecheck
lint
unit/component tests
Expo dependency check
Expo doctor
Android end-to-end smoke tests
preview/release build

Add static review rules where practical:

feature screens do not contain raw hex colors;

no new inline style objects in virtualized list render paths without justification;

no unsupported icon family imports outside AppIcon;

no direct theme preference branching scattered across screens;

no fixed screen width assumptions;

no role-based UI treated as backend authorization.

27. Acceptance Criteria

This milestone is complete when:

The application has one typed light/dark design system used by all productionscreens.

Feature screens contain no duplicated raw brand/status palettes and use sharedtypography, spacing, radius, and elevation tokens.

Login, shell, dashboard, orders, catalog, inventory, movement, forms, account, andconfirmation experiences are visually consistent and production quality.

Compact, medium, and expanded layouts work at defined breakpoints without clippedcritical content or inaccessible actions.

Compact navigation uses bottom tabs and expanded navigation uses an appropriaterail/master-detail composition.

Rotation and window resizing preserve route, safe draft state, and selection.

Light/dark modes preserve contrast and semantic status meaning.

Large fonts and Android TalkBack can complete core login, order transition, productedit, and inventory adjustment flows.

Loading, empty, filtered-empty, error, offline, refresh, stale, disabled, and successstates use reusable patterns.

Customer PII, staff tokens, business stock data, and adjustment reasons are notnewly exposed or persisted by the redesign.

Existing permissions, API validation, order transitions, catalog rules, inventoryinvariants, versions, and idempotency behavior remain unchanged.

The preview/release build performs acceptably on a mid-range Android device.

Visual regression baselines and behavioral tests cover the selected criticalscreens.

Expo checks, typecheck, lint, automated tests, accessibility review, and physicaldevice acceptance pass.

28. Recommended Implementation Order

Audit the current mobile UI and capture baseline screenshots for all implementedroutes and states.

Add palette, semantic light/dark themes, typography, spacing, radii, elevation,motion, and breakpoint tokens.

Add ThemeProvider, useTheme, responsive-tier hook, and system-bar integration.

Build primitives and a development-only component gallery.

Build buttons, fields, cards, badges, chips, feedback, skeleton, confirmation,timeline, and navigation components with accessibility tests.

Implement ResponsiveContainer, grid, adaptive navigation, and master/detailprimitives.

Redesign login, session restoration, app shell, and account.

Redesign dashboard and order list/detail/action flows.

Redesign catalog list, product form, and lifecycle controls.

Redesign inventory summary/detail, adjustment, and movement history.

Add responsive, dark-mode, large-font, TalkBack, and visual-regression coverage.

Remove obsolete styles/components and run static audits for raw values and duplicatepatterns.

Verify on physical Android devices and produce a signed preview build for review.

29. Follow-up Milestones

After this specification:

Run a small staff usability pilot and measure task completion, errors, and confusingstates before adding more decoration.

Add production deployment/security hardening, monitoring, backups, and recovery.

Add production customer messaging when the provider setup is ready.

Add iOS-specific visual verification and release preparation when required.

Add localization only after identifying actual staff languages and terminology.