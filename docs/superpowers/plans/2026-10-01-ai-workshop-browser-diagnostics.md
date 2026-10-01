# AI Workshop Browser Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent Chromium/Playwright browser service with screenshots, explicit video capture, and adaptive temporal-composite diagnostics that produce PNG and JSON artifacts.

**Architecture:** A private browser service owns Chromium and its persistent user data directory. Normal browsing uses a persistent Playwright context; explicit diagnostic recording runs as a bounded capture session using the persisted authentication state and produces video plus optional temporal composites. Image/video processing is isolated behind deterministic frame-selection and rendering interfaces so it can be unit tested without a browser.

**Tech Stack:** Python 3.12, Playwright Python, Chromium, FastAPI, NumPy, OpenCV headless, Pillow, pytest.

**Spec:** `docs/superpowers/specs/2026-10-01-ai-workshop-design.md`

## Global Constraints

- Browser login/session state must survive container restarts.
- The Workshop browser profile must be isolated from the host user's normal browser profile.
- Video recording and temporal-composite generation start only on explicit agent request.
- Temporal composites support whole-page, CSS-selector, and coordinate-region capture.
- Composite output supports neutral, time-gradient, or both variants; time legend is optional.
- Frame selection is adaptive with auto sensitivity by default and optional manual override.
- Intermediate frames are deleted by default and preserved only when `keep_frames=true`.
- If composite generation fails after recording succeeds, the original video must remain available.

## Review Focus

- A selector that resolves to zero or multiple elements must fail clearly rather than silently capture the wrong region; Task 2 adds `test_selector_region_requires_single_match`.
- Browser restart must retain cookies/local storage from the persistent profile; Task 1 adds `test_profile_survives_restart`.
- A static video must not generate dozens of duplicate trail layers; Task 3 adds `test_adaptive_selector_collapses_static_frames`.
- Real UI colors must remain usable in neutral output; Task 4 adds `test_neutral_composite_preserves_latest_pixel_color`.
- Composite failure must not remove a valid recording; Task 5 adds `test_recording_survives_composite_failure`.

---

### Task 1: Persistent browser runtime and interaction API

**Files:**
- Create: `src/ai_workshop/browser/runtime.py`
- Create: `src/ai_workshop/browser/app.py`
- Create: `src/ai_workshop/browser/models.py`
- Create: `browser/Dockerfile`
- Create: `browser/entrypoint.sh`
- Test: `tests/integration/browser/test_runtime.py`

**Interfaces:**
- Consumes: private Workshop Docker network from the core plan.
- Produces: `BrowserRuntime.start() -> None`, `BrowserRuntime.stop() -> None`, `BrowserRuntime.page() -> Page`, plus private HTTP operations for navigate/click/type/scroll/evaluate/console/network.

- [ ] **Step 1: Write failing runtime tests**

Cover navigation, interaction, console event capture, network event capture, and `test_profile_survives_restart` using a local test site that writes a cookie and localStorage token.

- [ ] **Step 2: Implement persistent Chromium runtime**

Use Playwright `launch_persistent_context(user_data_dir=...)` with a named Docker volume mounted at `/data/browser-profile`. Keep one active page ID registry and expose stable page identifiers.

- [ ] **Step 3: Run runtime tests**

Run: `uv run pytest tests/integration/browser/test_runtime.py -v`  
Expected: PASS.

- [ ] **Step 4: Containerize the browser service**

Install only Chromium plus Playwright runtime dependencies. Add healthcheck and persistent profile/artifact volumes.

- [ ] **Step 5: Commit**

```bash
git add src/ai_workshop/browser browser tests/integration/browser
git commit -m "feat: add persistent playwright browser"
```

### Task 2: Static screenshots and capture-region resolution

**Files:**
- Create: `src/ai_workshop/browser/regions.py`
- Create: `src/ai_workshop/browser/screenshots.py`
- Test: `tests/unit/browser/test_regions.py`
- Test: `tests/integration/browser/test_screenshots.py`

**Interfaces:**
- Consumes: Playwright page IDs from Task 1.
- Produces: `CaptureRegion.resolve(page, request) -> ResolvedRegion` and `ScreenshotService.capture(request) -> ArtifactRef`.

- [ ] **Step 1: Write failing region tests**

Cover whole viewport, full page, coordinate region bounds, a unique selector, out-of-bounds coordinates, and `test_selector_region_requires_single_match`.

- [ ] **Step 2: Implement region resolution**

Define a discriminated union: `PageRegion`, `SelectorRegion(selector: str)`, and `CoordinateRegion(x: int, y: int, width: int, height: int)`.

- [ ] **Step 3: Run region tests**

Run: `uv run pytest tests/unit/browser/test_regions.py -v`  
Expected: PASS.

- [ ] **Step 4: Write failing screenshot integration tests**

Assert viewport screenshot, full-page screenshot, selector crop, and coordinate crop dimensions against a deterministic fixture page.

- [ ] **Step 5: Implement screenshot capture**

Return an `ArtifactRef(id, media_type, path, width, height)`; keep artifacts under `/data/artifacts/<session-id>/`.

- [ ] **Step 6: Run Task 2 tests**

Run: `uv run pytest tests/unit/browser/test_regions.py tests/integration/browser/test_screenshots.py -v`  
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/ai_workshop/browser/regions.py src/ai_workshop/browser/screenshots.py tests
git commit -m "feat: add targeted browser screenshots"
```

### Task 3: Explicit video recording and adaptive frame selection

**Files:**
- Create: `src/ai_workshop/browser/recording.py`
- Create: `src/ai_workshop/browser/frames.py`
- Create: `src/ai_workshop/browser/artifacts.py`
- Test: `tests/integration/browser/test_recording.py`
- Test: `tests/unit/browser/test_frames.py`
- Test fixtures: `tests/fixtures/browser_frames/`

**Interfaces:**
- Consumes: persisted auth state and region model from Tasks 1–2.
- Produces: `RecordingService.start(request) -> CaptureSession`, `RecordingService.stop(session_id) -> RecordingArtifact`, `AdaptiveFrameSelector.select(frames, config) -> SelectionResult`.

- [ ] **Step 1: Write failing recording lifecycle tests**

Assert that recording is absent during ordinary browsing, starts only through `start`, produces WebM after `stop`, and stores source URL/viewport/region in session metadata.

- [ ] **Step 2: Implement explicit diagnostic capture session**

Create a recording context only for the requested capture session, seed it from current persisted browser storage state, run requested browser actions against that session, and close it on stop so Playwright flushes the WebM.

- [ ] **Step 3: Run recording tests**

Run: `uv run pytest tests/integration/browser/test_recording.py -v`  
Expected: PASS.

- [ ] **Step 4: Write failing adaptive-selection tests**

Use deterministic synthetic frame sequences. Cover a static sequence, one moving rectangle, subtle low-amplitude change, noisy canvas-like pixels, `test_adaptive_selector_collapses_static_frames`, auto sensitivity, manual `low|medium|high`, and max-FPS limiting.

- [ ] **Step 5: Implement `AdaptiveFrameSelector`**

Decode the WebM to timestamped frames, compute normalized change score and changed-region bounding boxes, then retain significant frames according to adaptive threshold and max-FPS constraints.

- [ ] **Step 6: Run Task 3 tests**

Run: `uv run pytest tests/unit/browser/test_frames.py tests/integration/browser/test_recording.py -v`  
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/ai_workshop/browser tests/unit/browser tests/integration/browser tests/fixtures
git commit -m "feat: add explicit browser recording"
```

### Task 4: Neutral and time-gradient temporal composite renderer

**Files:**
- Create: `src/ai_workshop/browser/composite.py`
- Create: `src/ai_workshop/browser/metadata.py`
- Test: `tests/unit/browser/test_composite.py`
- Test: `tests/unit/browser/test_metadata.py`

**Interfaces:**
- Consumes: `SelectionResult` from Task 3.
- Produces: `CompositeRenderer.render(selection, variant, legend) -> Image.Image` and `build_metadata(...) -> DiagnosticMetadata`.

- [ ] **Step 1: Write failing neutral-composite tests**

Assert multiple moving positions remain visible, static background is not multiplied, and `test_neutral_composite_preserves_latest_pixel_color`.

- [ ] **Step 2: Implement neutral trail rendering**

Use changed-region masks to blend only motion regions onto a stable base frame with recency-weighted opacity; keep unchanged pixels from the latest base frame.

- [ ] **Step 3: Run neutral tests**

Run: `uv run pytest tests/unit/browser/test_composite.py -k neutral -v`  
Expected: PASS.

- [ ] **Step 4: Write failing time-gradient and legend tests**

Assert early and late motion receive different temporal encoding, legend can be enabled/disabled, and dimensions remain unchanged when the legend is omitted.

- [ ] **Step 5: Implement time-gradient rendering**

Map normalized timestamp to a configurable gradient applied only to changed-region trail masks. Keep original image available separately so real UI color analysis is not lost.

- [ ] **Step 6: Write and implement metadata tests**

Metadata must include source URL, viewport, region/selector, duration, every candidate frame timestamp/change score/boxes/selected flag, variant, threshold configuration, max FPS, and legend configuration.

- [ ] **Step 7: Run Task 4 tests**

Run: `uv run pytest tests/unit/browser/test_composite.py tests/unit/browser/test_metadata.py -v`  
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/ai_workshop/browser/composite.py src/ai_workshop/browser/metadata.py tests/unit/browser
git commit -m "feat: add temporal composite diagnostics"
```

### Task 5: Browser MCP tools, artifact lifecycle, and end-to-end diagnostics

**Files:**
- Create: `src/ai_workshop/gateway/browser_client.py`
- Create: `src/ai_workshop/gateway/browser_tools.py`
- Modify: `src/ai_workshop/gateway/server.py`
- Modify: `compose.yaml`
- Test: `tests/integration/test_browser_mcp.py`
- Test: `tests/e2e/test_browser_diagnostics.py`

**Interfaces:**
- Consumes: browser private API from Tasks 1–4 and MCP gateway from the core plan.
- Produces: MCP tools `browser_navigate`, `browser_click`, `browser_type`, `browser_screenshot`, `browser_record_start`, `browser_record_stop`, and `browser_capture_diagnostics`.

- [ ] **Step 1: Write failing MCP browser tests**

Assert navigation and screenshot tool results include artifact metadata, capture options accept page/selector/coordinates, and composite variant accepts `neutral|time-gradient|both`.

- [ ] **Step 2: Implement browser MCP client/tools**

Keep browser internals private; MCP returns artifact references plus structured metadata instead of raw container paths where possible.

- [ ] **Step 3: Write failing artifact-failure test**

Implement `test_recording_survives_composite_failure` by injecting a renderer failure after a valid WebM is flushed.

- [ ] **Step 4: Implement artifact lifecycle**

Delete intermediate decoded frames unless `keep_frames=true`; never delete `recording.webm` because a later renderer failed.

- [ ] **Step 5: Write and run E2E diagnostic scenario**

The fixture page animates/drags a rectangle across a canvas. Through MCP: start capture, perform motion, stop, request both composites, verify `recording.webm`, `composite-neutral.png`, `composite-time-gradient.png`, and `metadata.json`.

Run: `uv run pytest tests/integration/test_browser_mcp.py tests/e2e/test_browser_diagnostics.py -v`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ai_workshop/gateway compose.yaml tests
git commit -m "feat: expose browser diagnostics through mcp"
```
