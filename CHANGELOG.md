# Changelog

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
