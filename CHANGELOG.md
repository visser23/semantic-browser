# Changelog

## 1.3.2

- Added unauthenticated `GET /health` service endpoint for liveness/readiness probes with
  `{status, version, active_sessions}` response payload.
- Improved service internals by exposing `SessionRegistry.active_session_count()` and removing
  route-level access to private registry fields.
- Added service health endpoint tests and fixed HTTP endpoint docs (`diagnostics` is `GET`).

## 1.3.1

- Fixed version mismatch: `__init__.py` now exports `1.3.0` matching `pyproject.toml` and
  README (was incorrectly left at `1.2.0`).
- Documentation overhaul:
  - Added `docs/planner_contract.md` — canonical interface contract for LLM planners
    (observation format, allowed replies, blocker handling, failure recovery, system prompt).
  - Added `docs/integration_examples.md` — end-to-end worked examples for OpenAI chat,
    OpenAI function-calling, Anthropic tool use, HTTP service, CDP attach, and error
    handling patterns.
  - Added `docs/api_reference.md` — complete reference for every public class, method,
    model field, configuration option, and error type.
  - Added `docs/runtime_modes.md` — decision table for ephemeral/persistent/clone/attach/
    service modes with ownership semantics and migration guide.
  - Rewrote `docs/getting_started.md` — comprehensive onboarding covering portal, Python
    API, CLI, service mode, output format explanation, and troubleshooting.
  - Expanded `docs/real_profiles.md` — when to use each profile mode, safety guarantees,
    common pitfalls, profile path locations.
  - Restructured `README.md` — cleaner layout, consistent version references, documentation
    index linking all guides, removed verbose inline details in favor of dedicated docs.

## 1.3.0

- Framework-agnostic element discovery: custom elements with AngularJS (`ng-click`,
  `on-click`), Vue (`v-on:click`, `@click`), Alpine.js (`x-on:click`), and other
  framework bindings are now captured via a universal hyphenated-tag discovery pass.
- Fuzzy structural settle: page settle now uses a configurable tolerance (`settle_tolerance_pct`,
  default 5%) instead of exact count matching; auto-escalates to 10% after 3 resets to prevent
  timeout on live-updating pages (sports odds, stock tickers, chat, etc.).
- Stable fingerprints: action IDs no longer include `rect.y` pixel position, using DOM id
  and CSS selector instead. Eliminates stale action IDs caused by layout shifts.
- Increased budgets: curated actions raised from 15 to 25, room budget from 1000 to 2000
  chars, expanded room from 4000 to 8000, action labels from 40 to 60 chars, narration
  from 200 to 350 chars, max elements from 2000 to 4000.
- Custom element curation priority: framework-rendered interactive components with `open`
  or `toggle` ops are promoted to the primary curation tier.
- Enhanced modal/overlay detection: three-tier detection covering standard ARIA (now
  visibility-checked — invisible/zero-size dialog remnants no longer trigger false positives),
  class-based heuristics (`[class*="modal"]`, `[class*="overlay"]`), custom-element modals
  (e.g. `<abc-modal>`, `<safety-message-modal>`), and viewport-coverage heuristic for
  fixed-position overlays covering >50% of viewport with high z-index.
- Improved resolver for custom elements: tag+text fallback (`tag:has-text(...)`) and
  count-checked CSS selector resolution to avoid returning empty locators.
- SPA navigation settle: URL changes during structural settle reset counters and flag
  `spa_navigation_during_settle` instability. SPA navigation now always classifies as
  "success" instead of falling through to "ambiguous".
- Cookie blocker detection widened: now matches "allow" in addition to "accept"/"consent"
  for OneTrust-style consent banners.
- Smarter result classification: actions that produce positive side-effects (changed regions,
  values, or materiality) alongside newly-appearing blockers (e.g. betslip opening with
  role="dialog") are now classified as "success" instead of false "blocked".
- Dialog blocker visibility check: `role="dialog"` elements are only flagged as modal blockers
  when visible in viewport and covering >30% of the screen, preventing false positives from
  hidden dialog remnants or small betslip panels.
- Resolver CSS sanitization: volatile framework state classes (Angular `ng-pristine`,
  `ng-untouched`, `ng-valid`, `ng-empty`, etc.; Vue transition classes; Element UI modifier
  classes) are stripped from CSS selectors before resolution, preventing stale locator failures.
- Input locator priority: `<input>`/`<textarea>`/`<select>` elements now resolve via
  sanitized CSS selector first, then `get_by_label`, then `get_by_placeholder` (with a tag
  check to avoid targeting custom element wrappers like `<sbk-input>`).

## 1.2.0

- Added CSS selector fallback for custom web components (Paddy Power `<abc-button>` support)
- Resolved F841 unused variable lint errors in `test_resolver.py`
- Installed Playwright browsers before test step in CI pipeline
- Suppressed CVE-2026-4539 in pip-audit (security)
- Bumped version to 1.2.0

## 1.1.0

- Added explicit runtime ownership modes:
  - `owned_ephemeral`
  - `owned_persistent_profile`
  - `attached_context`
  - `attached_cdp`
- Refactored close lifecycle semantics:
  - non-destructive `close()` defaults for attached modes
  - explicit `force_close_browser()` override
- Promoted profile handling to first-class launch API:
  - `profile_mode` (`persistent|clone|ephemeral`)
  - `profile_dir`
  - `storage_state_path`
  - profile health diagnostics (lock/writable/version warnings)
- Expanded delta semantics with materiality scoring:
  - interaction/content/workflow/reliability/classification transitions
  - `delta.materiality = minor|moderate|major`
- Hardened settle loop and tracing:
  - layered settle phases with instability classification
  - enriched trace payloads (effect, evidence, URL history, tab creation)
- Added docs for real profile workflows:
  - `docs/real_profiles.md`
  - updated `README.md` and `docs/getting_started.md`
- Expanded test coverage and CI gate to include integration tests.

## 1.0.0 (Alpha) - 2026-03-12

- First open-source alpha release.
- Repository cleaned for third-party consumption:
  - removed internal planning/working docs
  - removed tracked bytecode artifacts
  - removed internal benchmark journals and snapshots
- Hardened service defaults:
  - optional token auth
  - localhost-focused CORS defaults
  - session TTL cleanup
- Improved runtime reliability and observability:
  - frame-aware extraction path
  - stable action/element ID behavior improvements
  - structured action/observe trace timing and warning events
  - trace export redaction of sensitive values
- Added release and community docs:
  - `docs/versioning.md`
  - `docs/publishing.md`
  - `CONTRIBUTING.md`
  - `SECURITY.md`

## 0.1.0 - 2026-03-10

- Initial end-to-end implementation:
  - Managed + attached runtime modes
  - Deterministic extraction engine
  - Action execution pipeline with validation
  - Stable ID matching and delta generation
  - Optional FastAPI local service
  - CLI for launch/attach/observe/act/inspect + portal interaction loop
  - Global runtime operations (`navigate`, `back`, `forward`, `reload`, `wait`)
  - Corpus harness baseline (`eval-corpus`) with YAML fixtures and scoring
  - Telemetry + debug trace export
  - Initial test coverage for core functionality
