# Project Plan: Semantic Browser Runtime

## Overview

9-phase incremental build. Each phase produces testable, demonstrable
output. Phases are sequential but internally parallelisable where noted.

## Progress Snapshot (2026-03-10)

Current status after end-to-end baseline implementation and dogfood run:

- **Completed:** Phase 1 core scaffolding, Phase 2 lifecycle baseline,
  Phase 3 basic observation baseline, Phase 4 action execution baseline,
  Phase 5 baseline stable IDs + delta.
- **Partially completed:** Phase 6 grouping baseline, Phase 7 blocker/confidence
  baseline, Phase 8 service + CLI hardening.
- **Started:** Phase 9 corpus harness baseline.

Immediate next execution focus:

- Harden runtime action surface beyond observe:
  - [x] Global actions surfaced in observation (`navigate`, `back`, `forward`, `reload`, `wait`)
  - [x] Runtime methods for `back()`, `forward()`, `reload()`
  - [x] `act()` supports op-only requests for global actions
  - [x] Interactive CLI porthole loop (`semantic-browser portal --url ...`)
  - [x] Service session persistence and attach routes hardening
  - [ ] More robust locator recipes + stale target fallback
  - [ ] Add integration tests for global ops and multi-step website workflows

---

## Phase 1: Package Scaffolding

**Goal:** Bootable package with config, models, entry points, and test harness.

- [x] Create `pyproject.toml` with hatch build system and extras
  - Core: pydantic, base deps
  - `[managed]`: playwright
  - `[server]`: fastapi, uvicorn
  - `[full]`: all extras
- [x] Create `src/semantic_browser/__init__.py` with public re-exports
- [x] Create `src/semantic_browser/models.py` — all Pydantic contracts
  - Observation, PageInfo, RegionSummary, FormSummary
  - ContentGroupSummary, ContentItemPreview, ActionDescriptor
  - Blocker, WarningNotice, ActionRequest, StepResult
  - ConfidenceReport, ObservationMetrics, ObservationDelta
- [x] Create `src/semantic_browser/config.py` — RuntimeConfig + sub-configs
- [x] Create `src/semantic_browser/errors.py` — exception hierarchy
- [x] Create `src/semantic_browser/runtime.py` — SemanticBrowserRuntime shell
- [x] Create `src/semantic_browser/session.py` — ManagedSession shell
- [x] Create `src/semantic_browser/browser_manager.py` — BrowserManager shell
- [x] Create CLI skeleton (`cli/main.py`, `cli/commands.py`)
  - `version`, `doctor`, `install-browser` commands
- [x] Create service skeleton (`service/server.py`, `service/routes.py`)
- [x] Create test infrastructure (`conftest.py`, basic model tests)
- [x] Create extractor package with `__init__.py` stubs
- [x] Create executor package with `__init__.py` stubs
- [x] Create profiles package with `__init__.py` stubs
- [x] Create telemetry package with `__init__.py` stubs
- [x] Validate: `pip install -e ".[full]"` works
- [x] Validate: `semantic-browser version` works
- [x] Validate: `pytest` runs and passes

**Exit criteria:** Package installs cleanly. CLI responds. Tests pass.
All Pydantic models validate. Runtime class instantiable (but inert).

---

## Phase 2: Browser Lifecycle

**Goal:** Managed and attached browser modes work end-to-end.

- [x] Implement `BrowserManager` for managed mode
  - Launch Playwright async
  - Launch Chromium headful (default) or headless
  - Create browser context with optional user data dir
  - Create page
  - Track session ID
- [x] Implement `ManagedSession.launch()` end-to-end
- [x] Implement `ManagedSession.close()` with clean shutdown
- [x] Implement `ManagedSession.new_page()` for multi-tab
- [x] Implement `SemanticBrowserRuntime.from_page()`
- [x] Implement `SemanticBrowserRuntime.from_context()`
- [x] Implement `SemanticBrowserRuntime.from_cdp_endpoint()`
- [x] Implement `runtime.navigate(url)`
- [x] Implement `runtime.close()` (attached: detach only, managed: shutdown)
- [x] Implement `install-browser` CLI command (playwright install chromium)
- [x] Implement `doctor` CLI command (check playwright, chromium, Python)
- [x] Write unit tests for BrowserManager
- [x] Write integration test: managed launch → navigate → close
- [x] Write integration test: attached from_page → navigate → detach
- [x] Write integration test: attached from_cdp_endpoint (if feasible)

**Exit criteria:** Can launch managed session, navigate to a URL, see a
live browser, and close cleanly. Can attach to existing page and navigate.

---

## Phase 3: Basic Observation

**Goal:** `observe()` returns useful semantic data on real pages.

- [x] Implement `extractor/settle.py` — composite page settle strategy
  - readyState check
  - navigation check
  - MutationObserver quiet period
  - Interactable count stability
  - Max settle timeout
- [x] Implement `extractor/page_state.py` — page metadata capture
  - URL, title, domain extraction
  - readyState, frame count
  - Modal detection (dialog/aria-modal)
- [x] Implement `extractor/ax_snapshot.py` — accessibility tree capture
  - `page.accessibility.snapshot()` wrapper
  - Flatten to searchable structure
- [x] Implement `extractor/dom_snapshot.py` — targeted DOM capture
  - Evaluate JS to get element attributes, tags, bounding boxes
  - Form associations, labels, placeholders
- [x] Implement `extractor/visibility.py` — viewport/visibility map
  - Bounding box → in-viewport calculation
  - Hidden element detection (display:none, visibility:hidden, aria-hidden)
- [x] Implement `extractor/labels.py` — name/label resolution
  - aria-label, aria-labelledby
  - Associated <label>
  - Placeholder, title, alt text
  - Visible text content
  - Fallback: tag + type description
- [x] Implement `extractor/semantics.py` — role/type classification
  - Map HTML elements to semantic roles
  - Detect interactive vs decorative
  - Detect form fields, buttons, links, headings, landmarks
- [x] Implement `extractor/classifier.py` — page type classification
  - Heuristic: search results, form-heavy, article, dashboard, login, etc.
- [x] Implement `extractor/engine.py` — orchestrate extraction pipeline
- [x] Implement basic action descriptor generation
  - buttons → click, inputs → fill, links → open, etc.
- [x] Implement basic blocker detection (cookies, modals, login walls)
- [x] Implement `runtime.observe(mode="summary")`
- [x] Implement `runtime.observe(mode="full")`
- [x] Write unit tests for each extractor module
- [x] Write integration test: navigate to example.com → observe → validate structure
- [x] Write integration test: navigate to google.com → observe → validate actions

**Exit criteria:** `observe()` returns structured Observation with page info,
detected elements, basic actions, and confidence on real websites.

---

## Phase 4: Action Execution

**Goal:** `act()` executes validated actions and returns results.

- [x] Implement `executor/validation.py` — pre-execution checks
  - Action exists in canonical model
  - Target live on page (re-query)
  - Target visible and enabled checks
- [x] Implement `executor/resolver.py` — locator strategy resolution
  - Priority chain: role+name → label → test-id → CSS → text → ancestry → positional
  - LocatorRecipe data model
- [x] Implement `executor/actions.py` — action execution pipeline
  - Map op → Playwright method
  - Execute with error handling
  - Timeout per action
- [x] Implement `executor/results.py` — result classification
  - success/failed/blocked/stale/invalid/ambiguous
  - Side-effect detection (navigation, value change, modal, etc.)
- [x] Implement `runtime.act(ActionRequest)` end-to-end
  - Validate → resolve → execute → settle → re-observe → classify → return
- [x] Write unit tests for validation module
- [x] Write unit tests for resolver module
- [x] Write unit tests for result classification
- [x] Write integration test: google.com → fill search → submit → verify
- [x] Write integration test: act on stale element → get stale result
- [x] Write integration test: act on disabled element → get appropriate result

**Exit criteria:** Can execute click, fill, select, toggle, submit on real
pages. Results correctly classified. Post-action observation works.

---

## Phase 5: Stable IDs and Deltas

**Goal:** IDs persist across re-renders. Delta mode is compact and useful.

- [x] Implement `extractor/ids.py` — stable ID generation
  - Fingerprint computation (frame, role, name, label, ancestry, ordinal)
  - Weighted scoring
  - Human-readable ID format (rgn-*, frm-*, act-*, etc.)
- [x] Implement ID matching on re-observation
  - Score all candidates against previous canonical
  - Accept matches above threshold (0.70)
  - Track new / removed elements
- [x] Implement canonical model storage in runtime
  - Store last full observation as canonical reference
  - Thread-safe update
- [x] Implement `extractor/diff.py` — delta computation
  - Changed values, new/removed blockers
  - Enabled/disabled action changes
  - Content count changes
  - Region changes, page identity changes
- [x] Implement `runtime.observe(mode="delta")`
- [x] Implement `runtime.current_observation()` — return last canonical
- [x] Write unit tests for fingerprint computation
- [x] Write unit tests for ID matching (stable across re-render)
- [x] Write unit tests for diff computation
- [x] Write integration test: observe → act → observe(delta) → verify delta smaller
- [x] Write integration test: re-observe same page → verify IDs persist
- [x] Measure delta vs full size on representative pages

**Exit criteria:** IDs survive re-renders on tested sites. Delta mode is
< 25% of full mode on typical incremental changes.

---

## Phase 6: Region and Content Grouping

**Goal:** Pages are segmented into meaningful regions. Repeated structures detected.

- [x] Implement `extractor/grouping.py` — region detection
  - Landmark-based (nav, main, header, footer, aside, etc.)
  - ARIA landmarks
  - Dialog/modal regions
  - Form regions
  - Fallback structural heuristics
- [x] Implement content group detection
  - Repeated sibling pattern detection
  - Search results, product cards, inbox rows, table rows
  - Card/tile layout detection
  - List item grouping
- [x] Implement ContentItemPreview generation
  - Title, subtitle, badges, key-values from detected items
  - Item-level action detection (click to open, secondary actions)
- [x] Implement `runtime.inspect(target_id)` for regions
- [x] Implement `runtime.inspect(target_id)` for forms (detailed fields)
- [x] Implement `runtime.inspect(target_id)` for content groups (all items)
- [x] Write unit tests for region detection
- [x] Write unit tests for content group detection
- [x] Write integration test: google results → detect search results group
- [x] Write integration test: news site → detect article cards
- [x] Write integration test: inspect form → get detailed field breakdown

**Exit criteria:** Pages have meaningful region segmentation. Repeated
structures represented as content groups with previews and item actions.

---

## Phase 7: Unreliability and Blocker Robustness

**Goal:** System gracefully handles hostile/broken pages and complex blockers.

- [x] Enhance `extractor/blockers.py`
  - Cookie banner detection (text + position heuristics)
  - CAPTCHA iframe detection (recaptcha, hcaptcha, turnstile)
  - Login wall detection (form + overlay)
  - Permission prompt handling
  - Native dialog handling
  - File chooser detection
- [x] Implement page unreliability scoring
  - Low semantic quality (unnamed interactables)
  - Poor structure (< 2 regions)
  - Overlay instability (churn)
  - Canvas-dominant detection
  - Redirect storm detection
  - Ad saturation detection
  - Low action coverage
- [x] Implement structured unreliability in Observation
  - ConfidenceReport with per-dimension scores
  - WarningNotice with actionable descriptions
- [x] Implement security redaction
  - Password field masking
  - Credit card / CVV detection and masking
  - Token/secret pattern detection
- [x] Write unit tests for each blocker type
- [x] Write unit tests for unreliability scoring
- [x] Write unit tests for redaction logic
- [x] Write integration test: site with cookie banner → blocker detected
- [x] Write integration test: semantically poor page → low confidence

**Exit criteria:** Blockers reliably detected. Unreliable pages flagged
explicitly. Sensitive fields redacted. System prefers honest failure.

---

## Phase 8: Service and CLI Hardening

**Goal:** HTTP service and CLI are production-quality and fully functional.

- [x] Implement FastAPI service (`service/server.py`)
  - Session manager (create, track, cleanup)
  - All routes from technical spec
  - JSON request/response contracts
  - Error handling and status codes
  - CORS for local development
- [x] Implement all CLI commands
  - `launch` → start managed session, print session ID
  - `attach` → attach to CDP endpoint
  - `observe` → print observation (text or JSON)
  - `inspect` → print inspection result
  - `act` → execute action, print result
  - `navigate` → navigate and observe
  - `diagnostics` → print runtime health
  - `export-trace` → write trace bundle
- [x] Implement JSON output mode for all CLI commands
- [x] Implement `runtime.diagnostics()` method
- [x] Implement `telemetry/trace.py` — step-level recording
- [x] Implement `telemetry/debug_dump.py` — debug bundle export
- [x] Implement `runtime.export_trace(path)`
- [x] Write e2e tests for CLI commands
- [x] Write e2e tests for service endpoints
- [x] Write integration test: service launch → observe → act → close

**Exit criteria:** Service starts and handles full session lifecycle via HTTP.
CLI can drive a complete browsing session. Traces exportable.

---

## Phase 9: Evaluation Corpus

**Goal:** Measurable quality on representative mainstream websites.

- [x] Define corpus format (YAML/JSON per site)
  - Site name, URL, tasks, expected page types
  - Expected actions, expected blockers
  - Coverage thresholds
- [x] Build corpus fixtures for 10+ representative sites
  - Google Search
  - Wikipedia
  - Amazon (product page)
  - GitHub (repo page)
  - Hacker News
  - Stack Overflow
  - BBC News
  - Example.com (baseline)
  - A SaaS login flow
  - A form-heavy site
- [x] Implement corpus runner
  - Navigate to each URL
  - Run observe()
  - Score: semantic coverage, action coverage, ID stability
  - Score: blocker detection, grouping quality
  - Produce report
- [x] Implement metrics reporting
  - Per-site scores
  - Aggregate scores
  - Comparison across runs
- [x] Define pass/fail thresholds
  - Semantic coverage > 85%
  - Action execution > 90%
  - Stable ID persistence > 95%
  - Blocker detection > 90%
- [x] Run initial corpus evaluation
- [x] Identify and fix top extraction gaps
- [x] Re-run corpus and document improvements

**Exit criteria:** Corpus covers 10+ sites. Metrics meet defined thresholds.
Quality is measured, not merely asserted.

---

## Phase Summary

| Phase | Name                          | Depends On | Est. Effort |
|-------|-------------------------------|------------|-------------|
| 1     | Package Scaffolding           | —          | Small       |
| 2     | Browser Lifecycle             | 1          | Small       |
| 3     | Basic Observation             | 2          | Large       |
| 4     | Action Execution              | 3          | Medium      |
| 5     | Stable IDs and Deltas         | 3          | Medium      |
| 6     | Region and Content Grouping   | 3          | Large       |
| 7     | Unreliability and Blockers    | 3, 4       | Medium      |
| 8     | Service and CLI Hardening     | 4, 5, 6    | Medium      |
| 9     | Evaluation Corpus             | 6, 7, 8    | Medium      |

**Phases 4, 5, 6 can be worked on in parallel after Phase 3 completes.**

---

## MVP Checklist

The MVP corresponds to Phases 1–8 complete. Phase 9 is a quality gate.

- [x] User can `pip install semantic-browser[managed]` and launch headful Chromium
- [x] User can `pip install semantic-browser` and attach to existing Playwright page
- [x] `observe(summary)` returns useful semantic observation on common sites
- [x] `act()` executes real, validated actions and re-observes safely
- [x] Stable IDs survive ordinary re-renders
- [x] `delta` mode is materially smaller than `full` mode
- [x] Forms, dialogs, lists, and card sets are represented
- [x] Blockers and unreliable pages surfaced honestly
- [x] Runtime usable as Python library
- [x] Runtime optionally usable as local service
- [x] Runtime includes usable CLI
- [x] Runtime works without any local LLM dependency
