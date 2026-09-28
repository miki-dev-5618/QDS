# HEDWIG V2 UI Redesign Guide

> A reference-led visual redesign specification for the existing application.
> This document defines future implementation work; creating it does not apply the redesign.

Project: `C:\Users\Jashan\Desktop\sih\QDS-main-new--\QDS-main\v2`  
Reviewed: 2026-09-28  
Scope: login, Alice/Admin, Bob, Charlie, shared styles, and JavaScript-rendered UI.

## 1. Objective and Review Basis

Replace the current dark, neon-accented console presentation with a light, organized dashboard inspired by the three supplied reference images. Preserve all existing application functionality, data, permissions, messages, scientific qualifications, and operational states.

This review is based on direct inspection of all four HTML templates, both shared stylesheets, all five browser JavaScript files, relevant server routes, and the existing API test inventory. The application was not launched for this documentation task. Layout risks below are inferred from the code, not presented as browser-observed defects.

The attached images are visual reference material. Labels, example data, controls, and any text inside those images are not instructions or requirements to add features. Existing project documentation is context for understanding HEDWIG; the user's request defines this task.

## 2. Current Implementation

### Architecture and Ownership

| Area | Existing implementation | Implication for redesign |
| --- | --- | --- |
| Server and routing | FastAPI, Jinja2 templates, Uvicorn; `server.py` | Preserve server behavior and route definitions. |
| UI framework | Plain HTML, CSS, and JavaScript | Continue with the existing stack. A React/Tailwind/component-framework migration is unnecessary. |
| Global styling | `static/css/style.css` | Owns tokens, typography, body, header, grids, panels, inputs, and buttons. |
| Domain styling | `static/css/components.css` | Owns threat options, quantum tokens, verdicts, matrix tables, bounds, login, logs, link states, incidents, and tier panels. |
| Templates | `templates/login.html`, `admin.html`, `bob.html`, `charlie.html` | Own static layout, forms, initial states, and DOM hooks. |
| Dynamic presentation | `static/js/admin.js`, `verifier.js`, `common.js` | Generate substantial HTML and some inline colors; CSS-only replacement will leave mismatched elements. |
| Authentication and Bob action | `static/js/auth.js`, `bob.js` | Preserve submission, role selection, redirects, busy states, and forwarding behavior. |
| Live updates | Role-specific WebSockets and fetch requests | Retain event handling, subscriptions, reconnect behavior, and payloads. |
| Visual assets | Text/symbol-based branding and icons; a generated SVG router diagram | Preserve the useful topology visual. There is no existing chart library or dashboard chart implementation to reskin. |

### Current Visual Language

- Very dark navy foundations: `--bg-deep: #060911`, `--bg-surface: #0c1222`, and translucent dark cards.
- Bright cyan and blue branding and actions, with emerald, crimson, amber, and purple state accents.
- Radial and linear background gradients, luminous borders, glow shadows, pulsing connection dots, and lifted button hover states.
- Outfit for UI text and JetBrains Mono for technical data; many labels and section headings use uppercase and small type.
- A sticky 70px top header contains the product, long role title, badge, subtitle, connectivity, node identity, cross-role links, and logout.
- Main content is capped at 1600px. The main two-column grid is `1.15fr 0.85fr`; common gaps are 24-28px.
- `.glass-panel` uses 14px corners, a 16px backdrop blur, and dark shadows. Login uses 16px corners.
- Several sections contain additional framed cards: telemetry metrics, dispatch entries, certificate grids, and tier results.
- No media queries or reduced-motion rules are present in the two stylesheets. A few component grids use `auto-fit`, but the overall header and main layout do not adapt explicitly.

Evidence anchors: `style.css:3` (tokens), `:74` (header), `:198` (main container), `:206` (two columns), `:219` (panels), `:286` (primary actions); `components.css:180` (matrix), `:228` (bounds), `:258` (log), `:290` (login). Line numbers describe the reviewed snapshot.

### Existing Screens and Workflows

| Screen | Existing content and behavior to retain |
| --- | --- |
| Login, `/login` | HEDWIG branding; conditional demo node presets; username/password; authentication errors; role-aware login redirect. |
| Alice/Admin, `/admin` and alias `/alice` | Message composition; 16/32/64-qubit selection; token preview; sign/transmit; eight threat scenarios; conditional tampered payload; recent dispatches; metrics and injected-versus-detected results; link reset; router topology; audit-chain verification; incidents; live log. |
| Bob, `/bob` | Waiting state; latest verification; verdict and mismatch/QBER values; received payload; checks; signed audit and tier results; elimination matrix; bounds and assumptions; dishonest-forward action to Charlie. |
| Charlie, `/charlie` | Waiting state; latest independent verification and forwarded results; received payload; checks; signed audit and tier results; independent matrix; bounds and assumptions; integrity explanations. |

### Design Problems to Address

| Observation from source | Resulting design risk | Redesign response |
| --- | --- | --- |
| Dense, fixed-height header with no wrapping strategy | Long role names and navigation can crowd or overflow smaller screens. | Move navigation to a sidebar; allow the top bar and status group to wrap. |
| Persistent two-column layouts and inline fixed track counts | Composer, metrics, threat options, and verifier panels can become too narrow. | Add explicit breakpoints and `minmax(0, 1fr)` tracks. |
| `body { overflow-x: hidden; }` | Overflow may be concealed rather than resolved. | Fix child sizing; retain horizontal scrolling only where needed for tables. |
| Many tiny uppercase monospace labels | Technical details and everyday controls compete for attention. | Use sentence-case section labels and readable sans-serif controls; keep technical values monospace. |
| Almost every region has a border, shadow, and panel hover effect | Passive information can appear interactive; hierarchy becomes flat. | Use unframed sections, simple separators, and clearly bounded tools. |
| Dark colors exist in CSS, template styles, and JavaScript strings | A token swap alone will produce partially themed states. | Audit all three sources and centralize presentation colors. |
| A shared danger treatment appears in different situations | Signature rejection, nonparticipation, aborted distribution, and future-link policy may be confused. | Keep the exact verdict text and distinct state labels visible; never infer state from color. |
| Clickable threat/preset `div` elements and limited focus treatment | Keyboard operation is weaker than mouse operation. | Use native buttons with preserved hooks and explicit focus styling. |

## 3. How the References Translate to HEDWIG

| Reference | Visual cues to borrow | HEDWIG application | Elements outside scope |
| --- | --- | --- | --- |
| Image 1: Lector admin dashboard | Slim sidebar, white content, compact metric strip, disciplined table/list spacing, small pink/purple accents | Scan-friendly summaries, dispatch feed, readable matrix and audit rows | Revenue, traffic charts, date filters, calendar controls, fabricated statistics |
| Image 2: Intelly medical dashboard | Strong dark text, clearly grouped pastel surfaces, primary work area with a secondary information column | Message/threat workspace, pastel metric tiles, visually distinct current state and activity | Patient records, appointments, search, notifications, cream-dominant canvas, decorative shapes |
| Image 3: CoachPro dashboard | Light translucent shell, mint/teal accents, selected sidebar item, restrained depth, large readable values | Primary shell direction, active navigation, topology tool, summary tiles | Sports content, finance cards, promotional banner, decorative 3D scene, all-over blur |

**Chosen direction:** use Image 3 for the light shell and teal navigation, Image 2 for pastel grouping and clear typography, and Image 1 for compact operational density.

Use a pale neutral canvas, a mist-colored sidebar, mostly opaque white work surfaces, and a small amount of translucency in the top bar. Apply mint, rose, butter-yellow, blue, and lavender in limited areas. The composition should read as a working QDS dashboard, with HEDWIG and the active role prominent in the first viewport.

Use practical 6-8px component corners and restrained shadows. Do not reproduce the references' large outer presentation frames, oversized rounded sections, nested cards, or decorative backgrounds. Preserve the existing router graphic and state tokens as domain-relevant visual assets.

## 4. Proposed Design Tokens

Introduce semantic tokens in `static/css/style.css`. The values below are a starting implementation specification.

```css
:root {
  --canvas: #f3f6f5;
  --sidebar: #e8efed;
  --surface: #ffffff;
  --surface-soft: #edf3f1;
  --surface-frosted: rgba(255, 255, 255, 0.94);
  --field: #ffffff;
  --line: #d4dfdb;
  --field-line: #82958f;

  --ink: #172b2a;
  --ink-muted: #536663;
  --primary: #0c777c;
  --primary-hover: #095f63;
  --on-primary: #ffffff;

  --success-bg: #e3f3e9;
  --success-ink: #176342;
  --danger-bg: #fbe5ed;
  --danger-ink: #a72649;
  --warning-bg: #fff0c2;
  --warning-ink: #795300;
  --info-bg: #e7effb;
  --info-ink: #20568e;
  --role-bg: #eee9f7;
  --role-ink: #66449a;

  --radius-control: 6px;
  --radius-panel: 8px;
  --shadow-panel: 0 4px 16px rgba(23, 43, 42, 0.07);
  --focus-ring: 0 0 0 3px rgba(12, 119, 124, 0.24);

  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 24px;
  --space-6: 32px;
  --sidebar-width: 224px;
}
```

Keep Outfit and JetBrains Mono with their existing fallbacks. Use 14-16px body and controls, 12-13px supporting data labels, 16-18px section headings, 28px page headings, and 28-32px primary metric values. Use 13px monospace for tables and logs where practical. Set letter spacing to zero; use tabular numerals for metrics. Do not size typography with viewport units.

The specified solid-background text pairs were checked mathematically: white on primary is approximately 5.32:1; muted text on canvas is 5.60:1; the success, danger, warning, info, and role pairs exceed 5.8:1. Check actual rendered combinations separately, particularly translucent backgrounds, input boundaries, and focus indicators.

### Compatibility During Migration

Existing templates and renderers still reference the old tokens. Add compatibility aliases first so all live states remain legible, then migrate presentation references consistently.

| Existing token | New token or treatment |
| --- | --- |
| `--bg-deep`, `--bg-surface` | `--canvas`, `--surface-soft` |
| `--bg-card`, `--bg-card-hover` | `--surface`, `--surface-soft` |
| `--bg-input` | `--field` |
| `--text-main` | `--ink` |
| `--text-muted`, `--text-dim` | `--ink-muted` |
| `--border-subtle`, `--border-active` | `--line`, `--primary`; use stronger `--field-line` for inputs |
| `--cyan-glow`, `--blue-accent` | `--primary`, `--info-ink` |
| `--emerald`, `--crimson`, `--amber`, `--purple` | Corresponding semantic ink tokens |
| `--border-danger`, `--border-success` | Corresponding semantic ink, or a tested accessible border variant |
| `--shadow-main` | `--shadow-panel` |
| Glow shadow variables | Remove glow effects; use flat semantic backgrounds and borders |
| `--glass-blur` | Limit to top-bar translucency; use opaque surfaces for data |
| `--bg-panel` | Define as `--surface`; topology currently falls back to hard-coded `#0b1220` |

Token aliases do not replace the required audit of literal colors in inline styles and generated markup.

## 5. Shell and Responsive Layout

### Desktop

Use a two-column application shell: a 224px sidebar and a flexible main area. Use the available viewport; do not center the entire application inside a decorative rounded frame.

Sidebar content:

1. HEDWIG brand and the existing symbol mark.
2. Current role, visibly selected.
3. The two existing cross-role links with their existing paths and `target="_blank"`.
4. Existing role-specific logout control.

A sidebar role link opens another role's page; it does not switch authenticated identity. Preserve the server's login checks and distinct role sessions. Retain clear labels for Alice/Admin, Bob, and Charlie. Do not add nonfunctional Search, Settings, Notifications, Profile, or Calendar controls from the references.

The top bar contains the page title, existing role/node identity, and live connection indicator. Give it a minimum height of 64px with natural wrapping. Keep `connDot` and `connText` available to the existing update function. Separate socket connectivity from channel enforcement status.

Main content uses 24px padding and 16-24px gaps. Place `channelBanner` immediately below the page header so watch, quarantine, and probation information precedes normal work.

### Responsive Rules

| Width | Layout |
| --- | --- |
| 1280px and wider | 224px sidebar; two-column work area; four metric tiles in one row. |
| 768-1279px | 200px sidebar; main sections stack; metrics use two columns; header wraps. |
| Below 768px | Sidebar becomes an in-flow compact navigation band with wrapping text links; one-column work area; no new drawer JavaScript is required. |
| Below 480px | Threat options, certificate cells, and metric tiles use one column when needed; forms use the full width. |

Preserve DOM reading order and keyboard order when rearranging sections. Use `min-width: 0` on grid/flex children, `overflow-wrap: anywhere` for identifiers and long payloads, and natural wrapping for labels and statuses. Keep technical tables in a labeled horizontal scroll region; do not hide columns.

Use 44px minimum control height, stable icon-button dimensions, and sufficient button height for multi-line busy labels. Avoid a fixed-height page header or verdict banner. Remove global overflow masking once child layouts are corrected.

## 6. Screen Specifications

### Alice / Admin

Recommended arrangement:

```text
HEDWIG sidebar | Alice / Admin                     Connection + node
               | Channel state banner, when applicable
               | Transmissions | Accepted | Threats detected | Last QBER
               | Injected / missed / false alarms / policy counters
               | Message signer                 | Threat injection
               | Recent dispatches & audit feed | Links + topology + latency
               | Audit chain & incidents        | Event log
```

- Move the existing four metric values out of the nested telemetry cards into one unframed summary row. Keep their current IDs and source fields.
- Suggested tile treatments: transmissions pale blue, accepted mint, threats rose, QBER pale yellow. A tile's decorative background does not itself signal an alarm.
- Keep the message composer as a bounded white tool. Preserve the initial message, required textarea, default 32-qubit option, 16/32/64 choices, disabled channel field, and token preview.
- Keep the sign/transmit action directly beneath the composer with a solid teal fill. Retain its complete action label and busy/disabled behavior.
- Present all eight threat scenarios as selectable rows/options within an unframed section. Preserve their order, descriptions, names, and `data-threat` values. Mark selection with a check and border, not color alone.
- The selected authentic baseline uses teal; selected attack scenarios use a danger treatment. Preserve the conditional tampered-payload field.
- Render dispatches as compact stacked records separated by rules. Avoid placing `.glass-panel` records inside another shadowed panel.
- Keep every dispatch field: ID, payload, classification, Bob and Charlie results, mismatch/limit values, channel evidence, early-abort details, injected scenario, detected/missed/false-alarm result, enforcement, response, Tier 2 attribution, audit link, and incident link.
- Preserve current history behavior: initial load shows the last five transmissions; incoming records are deduplicated and prepended. A redesign must not introduce new pagination, filtering, retention limits, or record selection.
- Give links, topology, and latency a coherent work section. Keep reset accessible and preserve the reason prompt.
- Use a thin divider and section header for audit chain/incidents. Preserve the Verify chain action and the current last-six incident list.
- Keep a bounded, scrollable event log with all prefixes and timestamps. A light neutral log surface and semantic text replace the dark terminal; preserve automatic scrolling.

Metric sources remain `stats.total_sent`, `stats.verified_authentic`, `stats.threats_detected`, and `stats.last_qber`. Retain the current percentage formatting. The additional counters in `statTruth` and all latency labels/units in `latencyRow` remain available.

### Bob

- Use the same shell with Bob selected and a small mint role accent.
- Preserve the waiting state until a relevant transmission is rendered.
- Make the existing verdict a full-width status band with visible mismatch/limit and QBER values.
- Keep received payload, verification checks, signed audit metadata, latency, and tier results below the verdict in their current information sequence.
- Place the elimination matrix in the wider desktop column and the bounds plus dishonest-forward tool in the narrower column.
- Keep the dishonest-forward action visually distinct as an attack simulation. Preserve its current availability inside `activeContent`, API call, disabled interval, long busy label, and error/quarantine alerts.
- Maintain `window.HEDWIG_ROLE = "bob"` and the existing shared-verifier initialization.

### Charlie

- Match Bob's layout with Charlie selected and a restrained lavender role accent.
- Preserve independent verification content, Charlie's matrix, forwarded-by information, and bounds.
- Keep the existing integrity explanations in the secondary column; retain the probabilistic qualifications.
- Do not add Bob's attack action or Alice's threat controls.
- Maintain `window.HEDWIG_ROLE = "charlie"` and the shared renderer.

### Login

- Use the same neutral canvas, HEDWIG typography, and teal primary action.
- Keep a single white form surface at approximately 440px maximum width with 8px corners and a soft shadow.
- Present existing demo role presets as a compact segmented selection; preserve their conditional Jinja rendering and `data-role` values.
- Preserve the demo warning, initial credential behavior, required fields, autocomplete, error region, and authentication redirect behavior.
- Do not add a marketing hero, a new identity provider, signup, or password recovery as part of this redesign.

## 7. Component and State Rules

| Component | Required visual treatment and preserved behavior |
| --- | --- |
| Section headings | Sentence case is acceptable for static labels; preserve domain meaning and warnings. Keep dynamic verdict wording and field values intact. |
| Buttons | Solid teal primary, bordered neutral secondary, semantic danger for attack actions. Use disabled styling without losing readable text. |
| Icons | Replace decorative emoji with a consistent locally available Lucide icon set if introduced. Keep accessible names and existing action text. Do not require a new frontend framework or runtime CDN for core controls. |
| Threat/preset selection | Native `button type="button"` can preserve current click listeners, classes, and data attributes. Add `aria-pressed` synchronized from the existing selected state. Do not create a second selection model. |
| Inputs | White fields, strong enough boundaries, persistent labels, clear focus. Keep select options and constraints unchanged. |
| Quantum tokens | Small pale blue/lavender/mint/yellow tokens with dark text. Preserve symbols, Q index, count, and unresolved `?` previews. |
| Verdict | Pale semantic band, exact status text, icon, and readable stats; allow long text to wrap. |
| Checks | Readable pass/fail icon plus label, freshness detail, and all reasons. Preserve the current eight checks. |
| Matrix | Light header, row separators, monospace technical values, scrollable wrapper, pale red collision rows. Preserve every column and row. |
| Bounds | Unframed definition-style grid with separators. Keep all six values, decision rule, target/met result, inputs, and expandable assumptions. |
| Tier results | Compact labeled blocks separated by rules inside the audit area; keep Tier 1, conditional Tier 2, and response policy distinct. |
| Audit/incident links | Keep existing URLs and new-tab behavior; use a recognizable document/download icon with descriptive link text. |
| Connection | Online and reconnecting remain text-labeled. Subtle static indicator is sufficient; motion must respect reduced-motion preferences. |
| Topology | Retain existing SVG nodes, links, classical dashed path, labels, token/drop counts, and state mapping. Update fills/strokes and readable label sizing only. |

### State Semantics That Must Survive the Redesign

| State | Presentation |
| --- | --- |
| Accepted signature | Success text and mint band, based on the current verifier result. |
| Rejected signature | Danger text and rose band, with the actual classification/details. |
| Aborted distribution / verifier did not participate | Preserve the exact existing explanatory verdict and absent-result values; do not display these as accepted or invent verification data. |
| Open link / up hop | Success indicator with explicit state label. |
| Watch / degraded hop | Amber warning with evidence, strike/window information, and existing explanation. |
| Reset pending / probation hop | Blue information treatment with the existing reset reason and probation explanation. Preserve the `reset_pending` backend/UI state key. |
| Quarantined / down hop | Danger treatment with incident/reason/purged-record details and existing refusal semantics. |
| Empty result or missing bounds | Preserve the existing absence/empty-state behavior; do not fabricate metrics. |

Signature acceptance, detector classification, and the policy governing future traffic are different concepts. Styling must follow the existing fields and branches rather than collapse them into a single green/red score.

Do not replace matrices, probability bounds, or channel evidence with decorative charts. No trend, donut, or historical QBER chart is specified because the current UI does not implement one.

## 8. Functionality Preservation Contract

### DOM Hooks

Retain one copy of every existing ID on its relevant page. Move the actual element when changing layout; do not create hidden duplicate copies for desktop and mobile.

| Area | IDs to preserve |
| --- | --- |
| Shared role pages | `connDot`, `connText`, `channelBanner` |
| Login | `loginForm`, `username`, `password`, `errorMsg`, `btnLogin` |
| Admin composer/threats | `signForm`, `messageText`, `bitDepth`, `tokenPreview`, `btnSign`, `recentTxList`, `activeThreatBadge`, `tamperedGroup`, `tamperedText` |
| Admin telemetry | `statTotal`, `statAuth`, `statThreat`, `statQber`, `statTruth`, `linkStates`, `btnResetLinks`, `latencyRow`, `topologySvg`, `topologyLegend`, `btnCheckChain`, `chainRow`, `incidentList`, `terminalLog` |
| Bob and Charlie | `emptyState`, `activeContent`, `verdictBanner`, `verdictIcon`, `verdictTitle`, `verdictSubtitle`, `mismatchesVal`, `qberVal`, `verifiedMsgText`, `checksList`, `auditRow`, `matrixBody`, `certCard` |
| Bob only | `btnDishonestForward` |

Preserve `.threat-card`, `.preset-pill`, their `.active` state, `data-role`, and role-specific `data-logout` values. Preserve all threat identifiers:

```text
authentic
eve_forgery
dishonest_bob
eve_intercept
message_tampering
repudiation
replay
impersonation
```

### Requests, Events, and Data

- Keep all existing route paths, HTTP methods, request body keys, authorization, cookies, redirects, and response interpretation unchanged.
- Key existing UI calls include login/logout, arm-threat, sign-and-send, dishonest-bob-forward, channel reset, history, metrics, topology, incidents, audit chain, and per-artifact audit links.
- Preserve `/ws/{role}`, `init_sync`, `new_transmission`, `threat_armed`, `channel_state`, and `security_event` handling as applicable to each page.
- Preserve 401 role-aware redirects, WebSocket 4401 login redirection, the existing 2000ms reconnect delay, and HTTP 423 refusal handling.
- Preserve role filtering: Bob and Charlie see their own verification data and no injected ground-truth label. Do not add admin fetches to populate a shared sidebar or metric strip on verifier pages.
- Preserve rendering calculations, rounding, order, conditional visibility, `seenTx` deduplication, and current limits on initially displayed history/incidents.
- Preserve `escapeHtml`, `textContent`, and `encodeURIComponent` protections when modifying presentation strings.
- Keep native reset prompts and existing alerts during this visual pass. Replacing their interaction model is separate work.
- Preserve visible scientific assumptions, target-not-met notices, probabilistic wording, and classical-versus-hybrid audit labeling.
- Leave `server.py`, `auth.py`, `src/quantum_engine/`, storage, audit keys, dependencies, and protocol tests unchanged by the UI implementation.

### Dynamic Rendering Traps

1. `verifier.js` assigns complete `banner.className` strings. Additional classes placed only in the HTML will be lost; use the stable ID/base classes or update both presentation assignments consistently.
2. `emptyState`, `activeContent`, `channelBanner`, `tamperedGroup`, and `errorMsg` use inline display changes. Put new grid wrappers inside these containers or preserve their display behavior; avoid overriding hidden states with `!important`.
3. `admin.js` uses `innerHTML` for sign-button busy/default labels; `bob.js` replaces `textContent`. Static icons inserted only into those buttons will disappear unless both existing label states are handled.
4. `setArmedThreatUI()` writes inline border/text colors. Change those presentation assignments or use compatible tokens.
5. `handleNewTransmission()` sets `row.className = 'glass-panel'` and inline spacing. Replace its row presentation with the new feed style while preserving content and ordering.
6. `renderTopology()` has a dark fallback node fill. Define `--bg-panel` or replace the fallback with a semantic surface token.
7. Freshness notes, bounds, tier panels, audit links, and incidents are generated after load. Verify the theme again after receiving real data.
8. Both role templates must keep `window.HEDWIG_ROLE` before `verifier.js`. Preserve script order and avoid duplicate initialization when reorganizing markup.

## 9. File-by-File Implementation Map

| File | Permitted presentation edits |
| --- | --- |
| `static/css/style.css` | Semantic tokens/aliases, neutral canvas, shell/sidebar/top bar, typography, responsive layout, controls, focus, reduced-motion treatment. |
| `static/css/components.css` | Component surfaces, state colors, selectable options, tokens, verdicts, matrices, bounds, log, login, links, incidents, tier spacing. |
| `templates/admin.html` | Sidebar and top bar markup; move existing KPI nodes; reorganize current tools/sections; replace static inline styling with classes. |
| `templates/bob.html` | Shared visual shell, responsive verdict/workspace layout, cleaner bounds and attack-tool presentation. |
| `templates/charlie.html` | Match Bob's visual structure while retaining Charlie-specific content and role. |
| `templates/login.html` | Light form presentation, accessible presets, spacing, labels, and focus states. Preserve Jinja conditions. |
| `static/js/admin.js` | Generated markup/classes and color tokens in threat badge, dispatch feed, links, topology, incidents, logs, and button labels. No calculation or request changes. |
| `static/js/verifier.js` | Generated markup/classes for verdicts, checks, matrix, bounds, and audit; preserve branches and output data. |
| `static/js/common.js` | Presentation of channel banners and tier panels; preserve shared API/socket/escape helpers and logout semantics. |
| `static/js/auth.js` | Normally unchanged; only synchronize accessible selected-state attributes if preset buttons are introduced. |
| `static/js/bob.js` | Normally unchanged; only presentation of busy/default labels if required for icons. |

Keep the two existing CSS entry points. Extracting a shared Jinja partial is optional only if it removes meaningful shell duplication without changing server context or script ordering. Do not turn this pass into a routing or template architecture rewrite.

## 10. Implementation Sequence

1. Capture the existing four screens and representative dynamic states in an isolated local demo setup. Record baseline behavior before editing.
2. Add semantic tokens and temporary compatibility aliases; update base typography, surfaces, inputs, focus, and buttons.
3. Build the sidebar/top-bar layout in each role template with existing navigation and unique DOM hooks.
4. Rearrange Admin sections and verifier columns; flatten decorative panel nesting; preserve forms and visibility containers.
5. Update every dynamic renderer listed above so newly received data matches the static shell.
6. Finish login, responsive rules, keyboard selection, long-content wrapping, and reduced motion.
7. Compare requests, events, values, and state transitions with the baseline; run the focused checks below.
8. Review desktop and mobile screenshots against the three reference qualities: light shell, restrained pastel hierarchy, compact information density.

## 11. Acceptance and Verification

These checks are for the future UI implementation. They were not run as application tests during creation of this document.

### Visual Acceptance

- [ ] HEDWIG and the active role are clearly visible in the first viewport.
- [ ] The main palette is neutral/light, with teal action/navigation and multiple restrained pastel accents.
- [ ] No neon glows, radial decoration, card-in-card layouts, or passive panel hover effects remain.
- [ ] All existing sections and technical details remain accessible without introducing new tabs or collapsed-by-default areas.
- [ ] Static HTML and newly rendered dynamic content use the same theme.
- [ ] Inputs, links, selected options, status text, and focus indicators remain legible.
- [ ] There are no mock charts, fake metrics, decorative search/calendar/profile controls, or added operational workflows.

### Workflow Acceptance

| Check | Expected result |
| --- | --- |
| Login for each role and invalid credentials | Existing success/error behavior and role redirect remain intact. |
| Demo presets and non-demo login | Presets/warning appear only when the existing server flag allows them. |
| Cross-role links and logout | Existing new-tab navigation, role login requirements, and role-specific logout remain intact. |
| Composer at 16, 32, and 64 qubits | Same preview count, default selection, payload, submit behavior, and resulting values. |
| All eight threat selections | Same identifiers, arming behavior, selected state, and tampering-field condition. |
| Live updates and reload | Same connection text, initial history, newest-first live feed, deduplication, and latest verifier result. |
| Bob dishonest forwarding | Same request, busy state, Charlie result handling, and error/refusal behavior. |
| Open/watch/quarantine/probation | Same state labels, reasons, incident links, topology state, and reset outcomes. |
| Reset cancellation or short reason | Existing minimum-three-character reason requirement and cancellation remain intact. |
| Accepted/rejected/aborted/not-participating | Correct existing branches render; stale matrix, checks, and bounds are cleared as before. |
| Bounds and tiers | All values, assumptions, applicability conditions, units, and assurance labels are preserved. |
| Audit/incident retrieval and chain check | Same destination URLs, new-tab behavior, displayed verification, and log messages. |
| Session expiry and socket reconnect | Same redirects, authorization boundaries, and reconnect handling. |

Use seeded fixtures or existing tests to inspect probabilistic attack outcomes; do not require every simulated attack to be rejected on every small-signature run. Visual changes must preserve the result supplied by the current implementation.

Run the existing focused API regression suite after template/renderer changes:

```powershell
python -m pytest tests/test_api.py -q
```

Relevant existing tests cover role authorization, WebSocket sessions, ground-truth isolation, signing, replay, audit records, dishonest forwarding, reason-gated resets, quarantine, and audit-chain verification. These tests do not prove browser layout or interaction correctness.

Use browser smoke checks at 1440x900, 1024x768, 768x1024, and 390x844; also inspect 320px width and 200% zoom. Check keyboard focus, role navigation, native form validation, preset/threat selection, local table scrolling, visible disabled states, long identifiers/payloads, long busy labels, and actual live update rendering. No page-wide horizontal clipping or overlapping text is acceptable.

Use isolated test data for future transmission/reset checks so visual verification does not alter the user's current demo history or audit chain.

## 12. Reference Provenance

The three images supplied with the request were used as visual references:

| Image | Original attachment filename |
| --- | --- |
| 1, Lector | `codex-clipboard-5fcc2089-9198-46eb-88b8-44e025d049b5.png` |
| 2, Intelly | `codex-clipboard-e749d65b-41b3-4bd4-9f5d-bfbb9f6a6a07.png` |
| 3, CoachPro | `codex-clipboard-af21a108-bf74-4fb3-a71c-34d7a20d2076.png` |

Their original directory is `C:\Users\Jashan\AppData\Local\Temp`. This guide includes descriptions and mappings so it remains useful if the temporary attachments are removed.

Deliverable status: design analysis and implementation specification only. Application source, runtime behavior, and data remain unchanged by this documentation task.

