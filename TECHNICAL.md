# OpenAct — Document Analysis Engine: Technical Deep Dive

> A complete walkthrough of how the three tiers (Vue → Laravel → FastAPI → DeepSeek) collaborate
> to deliver asynchronous, cache-aware, legal document analysis with inline highlight overlays.

---

## 0. What the Product Does

OpenAct's document-analysis engine takes a legal document (PDF, DOCX, or plain text) that a user has
previously uploaded into a chat, and produces a structured, professional review of it. The review
includes:

- A **risk score** (0–100) and label (Low / Medium / High / Critical).
- **Highlights** — verbatim excerpts from the document, each tagged with a category
  (`risk_high`, `risk_medium`, `risk_low`, `clause_key`, `obligation`, `party`, `date`), an
  explanation, a section hint, and an optional page number.
- Aggregate **metrics** — clause count, obligation count, parties list, key dates, executive summary.
- Optional **two-document comparison**, showing added obligations, removed protections, and material
  changes across versions.

The frontend does not just *display* these results — it paints them directly on top of the rendered
document inside a `pdf.js` canvas or a `mammoth`-rendered DOCX, so the lawyer can click a finding
in the sidebar and land exactly on the relevant clause.

The entire analysis pipeline is asynchronous: the HTTP call that kicks off an analysis returns
within milliseconds with a `pending` record; the heavy AI work happens in a background worker; the
SPA polls for completion.

---

## 1. Tier Responsibilities at a Glance

| Tier               | Technology                                     | Single responsibility                                                              |
| ------------------ | ---------------------------------------------- | ---------------------------------------------------------------------------------- |
| **Frontend**       | Vue 3, Pinia, Vite, pdf.js, mammoth.js         | Render documents + overlay highlights + orchestrate UX (tabs, compare, tooltip)    |
| **API Gate**       | Laravel 11, Sanctum, PostgreSQL, Redis         | Auth, authorization, persistence, job dispatch, idempotency                        |
| **AI Kernel**      | FastAPI, Pydantic v2, loguru, OpenAI SDK       | Prompt construction, LLM call, JSON parsing, response validation                   |
| **LLM**            | DeepSeek v3 (`chat.completions`)               | Raw intelligence — produces JSON per the system prompt's schema                    |

Every tier has a **narrow contract** with the next: the browser talks JSON over Sanctum cookies
to Laravel; Laravel talks JSON + a shared-secret header to FastAPI; FastAPI talks the OpenAI
chat protocol to DeepSeek. Each boundary is also a trust boundary.

---

## 2. The Life of a Request (End-to-End)

This is the *golden path* — what happens when the user clicks "Analyze" on a document for the
first time.

### Step 1 — SPA trigger

`DocumentAnalysisPanel.vue` is mounted with a `document` prop. On mount it calls
`useDocumentAnalysis()`, which wraps a Pinia store and exposes `triggerAnalysis()`. If nothing is
cached for the current `(documentId, analysisType, compareDocumentId)` key, the composable POSTs:

```
POST /api/chats/{chat}/documents/{document}/analyze
Cookie: laravel_session, XSRF-TOKEN
Body: { "analysis_type": "full" }
```

The axios instance (`services/axios.js`) automatically attaches `withCredentials: true` and
mirrors the XSRF cookie into the `X-XSRF-TOKEN` header. A 401 anywhere forces a redirect to
`/login`.

### Step 2 — Laravel controller

`DocumentAnalysisController::analyze` runs inside the `auth:sanctum` + `throttle:60,1`
middleware group. It performs four things in order:

1. **Authorize** — `authorizeAccess()` aborts 403 if the chat is not owned by the user or the
   document does not belong to the chat.
2. **Validate** — `analysis_type` must be in the closed set
   `{full, risk, clauses, compare}`, `compare_document_id` must be a valid UUID that exists
   on `chat_documents`, and `force` is coerced into a boolean.
3. **Readiness gate** — `$document->isReady()` guards against analyzing a file whose text
   extraction has not finished yet (returns `422 DOCUMENT_NOT_READY`).
4. **Idempotency check** — unless `force=true`, the controller looks up the latest `done`
   analysis for that exact `(document, analysis_type, compare_document_id)` triplet and
   returns it verbatim via `DocumentAnalysisResource`. This turns repeated clicks on the
   same tab into free cache hits.

Only when the cache misses does it:

5. Delete stale `pending` / `failed` rows (so the index on `(chat_document_id, status)` stays
   tight and the UI never sees an old error).
6. `INSERT` a fresh `DocumentAnalysis` row in state `pending`.
7. Dispatch `ProcessDocumentAnalysis::onQueue('streaming')` to Redis.
8. Return `202 Accepted` with the pending resource — shape is identical to the eventual `done`
   shape so the frontend can render skeletons consistently.

### Step 3 — Queue worker

`php artisan queue:work --queue=streaming --tries=2 --timeout=120` (the
`laravel-worker` container from `docker-compose.yml`) picks up the job. `ProcessDocumentAnalysis::handle()`:

1. Re-loads the `DocumentAnalysis` row by id, or bails quietly if it was deleted.
2. Re-checks `ChatDocument::isReady()` — between dispatch and run the file could have been
   invalidated; if so, the job marks the row `failed` and exits.
3. Updates status → `processing`.
4. Builds the kernel payload from `ChatDocument::extracted_text` (plus `compare_text` /
   `compare_filename` when present).
5. Reads `config('services.kernel.url')` and `config('services.kernel.secret')`, then:

```php
Http::timeout(110)
    ->withHeaders(['X-Kernel-Secret' => $secret])
    ->post("{$kernelUrl}/analyze-document", $payload);
```

The 110s client timeout is deliberately shorter than Laravel's 120s job timeout — the HTTP call
will always fail before the job itself dies, so the exception path runs predictably.

On failure, behaviour depends on the attempt counter. The first failure `throw`s back to the
queue so Laravel schedules a retry (up to `$tries = 2`). The final failure calls `markFailed()`
which persists `status=failed` + `error_message`. Successes call `writeResult()` which stamps
`highlights`, `metrics`, `risk_score`, `risk_label`, `compare_highlights`, `compare_summary`
onto the row and clears `error_message`.

### Step 4 — FastAPI kernel

FastAPI boots from `kernel/main.py`. Two middlewares wrap every request:

- **`attach_request_id`** — reads `X-Request-ID` or mints a UUID, then binds it to the loguru
  context so every log line inside the request carries the correlation id. The header is echoed
  back on the response, so Laravel logs and Kernel logs can be joined on that id.
- **`verify_secret`** — rejects any non-`/health` request whose `X-Kernel-Secret` does not match
  `$PYTHON_KERNEL_SECRET`. This is a flat-string equality check — fine for an internal Docker
  network, and trivially swappable for mTLS or AWS IAM later.

The `POST /analyze-document` handler:

1. Parses the body into an `AnalyzeDocumentRequest` Pydantic model. The `text_not_empty`
   validator rejects documents under 50 characters with HTTP 422.
2. Delegates to the singleton `document_analysis_service.analyze(req)`.
3. Catches `ValueError` (validation / parsing) → 422 with the reason.
4. Catches everything else → 500 `"Analysis failed. Please try again."` (the full traceback
   goes to `logger.exception`, never to the client).

### Step 5 — `DocumentAnalysisService`

This is where prompt engineering lives. Four system prompts are pre-built at module load:

- **`_SYSTEM_FULL`** — identity as "OpenAct Engine", senior legal AI for Uzbekistan-based
  practice. Demands *verbatim* excerpts, 8–40 highlights, `risk_score` scaling, and a strict
  JSON schema with all seven highlight categories.
- **`_SYSTEM_RISK`** — narrows the remit to risk only. Instructs the model to look for missing
  protections, liability exposure, unilateral termination, vague language, penalty and
  jurisdiction issues. Metrics reduced accordingly.
- **`_SYSTEM_CLAUSES`** — key contractual clauses only (definitions, payment, IP, confidentiality,
  warranties, termination, dispute resolution, governing law).
- **`_SYSTEM_COMPARE`** — two-document diff. Produces `highlights_a`, `highlights_b`, and a
  `compare_summary` narrating material differences.

`_analyze_single(req)`:

1. Selects the prompt via `_SYSTEM_MAP[analysis_type]` (defaults to `_SYSTEM_FULL`).
2. Truncates the document at `_MAX_CHARS = 60_000` to cap token spend and stay inside DeepSeek's
   context. Truncation is explicit — it appends `"[... document truncated for analysis ...]"`
   so the model knows the cut is not an artefact.
3. Composes a two-message conversation: the chosen system prompt + a user message containing
   filename and the framed document body.
4. Calls `deepseek_client.generate()` with `model="deepseek-v3"`, `temperature=0.1` (near-greedy
   — we want deterministic legal output), and `max_tokens=6000`.
5. Parses the response via `_safe_parse` → `_parse_json` → strips ```` ```json ```` fences and
   falls back to a brace-scan regex if the LLM slips in extra prose.
6. Hydrates highlights with `_build_highlights` (clamps text at 500 chars, assigns fallback
   ids `h1..hN`, skips malformed entries with a warning instead of failing the whole response).
7. Hydrates metrics with `_build_metrics` — clamps `risk_score` into `[0, 100]`, assigns the
   human label via `_RISK_TIERS`, and recomputes `flagged_count` as `max(claimed, actual)` so
   a model that lies-low on its own flag count still gets corrected.
8. Returns a fully validated `AnalyzeDocumentResponse`.

`_analyze_compare(req)` mirrors the above but halves `_MAX_CHARS` for each document, composes
an "A vs B" user message, uses `_SYSTEM_COMPARE`, and splits the output into
`highlights` (= A), `compare_highlights` (= B), and `compare_summary`.

### Step 6 — Worker persists

The JSON response flows back to the worker, which unpacks it into the `DocumentAnalysis` Eloquent
row. Because the model casts `highlights`, `compare_highlights`, and `metrics` as `array`,
PostgreSQL's JSON columns are written transparently via `json_encode`. The row is now in state
`done` and immediately visible to any subsequent `GET` by the frontend.

### Step 7 — Frontend poll & render

While the job is running, `useDocumentAnalysis._startPolling()` has been hitting
`GET /api/chats/.../analysis?analysis_type=full` every 2 500 ms. The `show` controller method
returns the latest row for that exact view (404 if none). As soon as the poller observes
`status === 'done'`, it stops, the composable's `analysisLoading` flips to `false`, and Vue's
reactivity chains through:

- `DocumentAnalysisPanel` re-computes `activeHighlights`.
- `DocumentAnalysisSidebar` renders the risk gauge, metrics row, parties/dates chips, and the
  grouped findings list.
- `DocumentViewer` fires its `watch(() => props.highlights, ...)` and calls `_applyHighlights()`.

`applyHighlights()` in `utils/documentHighlighter.js` is the interesting part. For each
highlight it walks the DOM of the viewer container with a `TreeWalker` filtered to text nodes
(skipping `<script>`, `<style>`, and existing `<mark>` nodes), looks for the verbatim substring,
and surgically splits the text node into three — `before`, a new `<mark data-hl-id="..."
data-hl-category="...">`, and `after`. The `<mark>` gets its own inline background + accent
border driven by `HIGHLIGHT_COLORS[category]`, plus click and hover listeners. Click events
bubble up through `DocumentViewer` → `DocumentAnalysisPanel` → `onHighlightClick`, which opens
the `DocumentHighlightTooltip` (a `Teleport`-ed popover anchored to the clicked `<mark>`'s
bounding rect).

The sidebar reverses the flow: clicking a finding calls `onFindingClick`, which sets the active
highlight id and asks the viewer to `scrollToHighlight(id)`. That helper finds the `<mark>`,
`scrollIntoView({behavior: 'smooth', block: 'center'})`, and pulses its `filter: brightness`
via a small CSS animation so the eye locks onto it.

### Step 8 — Subsequent interactions

- **Switching tabs (`full` → `risk`)** — `useDocumentAnalysis.setAnalysisType('risk')` first
  looks in the Pinia store for a cached `full` result; if present, it **derives** the risk view
  in-memory by filtering highlights to the risk categories and tagging the derived result
  `_derived: true`. No extra HTTP call. Only when the cache is cold does it `triggerAnalysis()`
  against the Laravel endpoint, which itself will either cache-hit or dispatch a fresh job.
- **Compare mode** — flipping the compare toggle sets `analysis_type = 'compare'` and triggers
  a new analysis that carries `compare_document_id`. Laravel and the kernel both treat this as
  a distinct row in the DB and a distinct cache key on the client.
- **Re-analyze** — the reload button sends `force=true`; the controller skips its idempotency
  check and always dispatches a new job.

---

## 3. Why Each Piece Exists

This section is a running commentary on the *design choices*, not just the code.

### 3.1 Why split API Gate and Kernel?

A monolith would be simpler — Laravel could call DeepSeek directly via `Http::post`. It wasn't
done that way for three reasons:

1. **Concurrency model fit.** The document-analysis workload is 90% waiting on a third-party
   LLM. Python's `asyncio` + FastAPI handles that trivially with a single event loop;
   PHP-FPM would have to tie up a worker process per in-flight request. The dedicated
   Laravel queue worker (`laravel-worker`) hands off to FastAPI and sleeps, so neither tier is
   blocked.
2. **Prompt evolution velocity.** Prompt engineering is its own discipline and changes often.
   Keeping it in a Python module alongside the DeepSeek client lets AI engineers iterate on
   `_SYSTEM_FULL` without touching Laravel, running PHP tests, or rolling the whole PHP image.
3. **Vendor substitution.** The kernel is the only place that knows DeepSeek exists. Switching
   to Claude, GPT-5, or a local model means editing `deepseek_client.py` — nothing else moves.

### 3.2 Why a queue at all?

LLM calls commonly take 10–60 seconds. Three problems this creates for a synchronous handler:

- The browser sits on an open TCP connection, which load balancers and CDNs dislike.
- A retry scenario (transient `502` from DeepSeek) would re-run the entire analysis from
  scratch, wasting tokens.
- A burst of 20 simultaneous uploads during a busy hour would lock 20 PHP-FPM workers.

The queue decouples "user asked for this" from "work is happening", lets the worker retry
cleanly (`$tries = 2`), and keeps PHP-FPM workers free for the fast endpoints that pollfor
results.

### 3.3 Why idempotency + `force` flag?

A lawyer clicking "Full Review" twice in five seconds should *not* run two inference jobs. The
controller's idempotency check collapses duplicates into cache hits, which is cheap, correct,
and feels instant in the UI. The `force=true` escape hatch is there for when the user has
updated their prompt (version of the engine), is debugging a bad result, or wants a fresh pass
after editing the document.

The uniqueness key is `(chat_document_id, analysis_type, compare_document_id)` — indexed as
`da_doc_type_compare`. Anything finer-grained would miss hits; anything coarser would leak
results across tabs.

### 3.4 Why polling over WebSockets / SSE?

At the traffic level the product needs today, polling is strictly simpler: no broadcaster, no
sticky sessions, no reverse-proxy WebSocket upgrade dance. The composable caps the poll at
`MAX_POLLS = 48` × 2 500 ms ≈ 2 minutes, which exceeds the worker's `$timeout = 120s`. If the
worker is going to succeed, the poller will see it. If it's going to fail, the poller will see
that too, and `analysisError` flips `true` in the sidebar.

The contract leaves the door open for a swap: the backend's REST pattern (`POST` to enqueue,
`GET` to observe) is equivalent to the control surface you'd want from a Server-Sent Events
stream.

### 3.5 Why Pydantic at the Kernel boundary?

Two independent reasons, each sufficient on its own:

1. It generates an OpenAPI schema that Laravel (or any other caller) can validate against.
2. It refuses to let a hallucinated or malformed LLM response escape the kernel — `AnalyzeDocumentResponse`
   is the last gate before the payload is handed back to the worker, and any structural violation
   throws a typed error we can report cleanly.

### 3.6 Why `temperature=0.1`?

Legal review is not a creative task. We want the same document to produce (near) the same
highlights on every run. `0.1` is low enough to make the output stable across retries and token
caches, high enough that the model doesn't latch onto pathological degenerate completions.

### 3.7 Why `_truncate` at 60 000 chars?

Three forces converge on that number:

- DeepSeek's context window comfortably fits this plus the system prompt + headroom for the
  response.
- 60 KB of legal text is around 25 pages — enough to cover the contracts the product targets,
  and above that marginal utility drops because the *later* pages of long agreements are almost
  always signature blocks, schedules, and exhibits.
- Token cost scales linearly with input size. Capping input bounds the worst-case cost per job.

For compare jobs we halve this so both documents fit into the single request.

### 3.8 Why derive `risk` / `clauses` on the frontend from a cached `full`?

Running a full analysis already yields all the data a risk-only or clauses-only view needs —
it's just a filter over `highlights`. The composable (`useDocumentAnalysis.analysis`) short-
circuits the trip to the server in that case, marking the result `_derived: true` for debugging
and saving both token spend and latency. The dedicated `risk` / `clauses` prompts still exist
for cases where the user opens the risk tab *first* without ever running `full`.

### 3.9 Why `pdf.js` + `mammoth` + plain-text, instead of a PDF-to-image server render?

Browser-side rendering keeps the backend lean and, crucially, preserves a **real text layer**
on top of the PDF canvas. That text layer is what `applyHighlights` paints into. If we server-
rendered pages as images, we'd have to also ship word-level bounding boxes and paint
absolutely-positioned `<mark>` overlays — a much more fragile architecture.

For DOCX, `mammoth` converts to HTML in the browser, the result is run through a minimal
sanitizer (`<script>/<style>/on*=/javascript:` removed), and the same highlight injection
works on the HTML DOM. Plain text gets a `<pre>` and the same treatment.

### 3.10 Why inject highlights with `TreeWalker` instead of Ranges?

Two reasons:

1. A `TreeWalker` filtered to text nodes lets us precisely skip `<script>`, `<style>`, and
   existing `<mark>` elements — preventing double-wrapping on re-render and preventing
   highlights from landing inside code-layer markup.
2. Splitting a text node and inserting a `<mark>` is a local DOM operation — O(1) per highlight.
   Using `Range + extractContents + surroundContents` is equivalent but harder to reason about
   when the target substring spans text node boundaries.

The current implementation stops at the first match for a given highlight. This is intentional:
LLM-returned excerpts are chosen to be unique, and matching every occurrence would produce
duplicate-looking overlays for boilerplate phrases like "Governing Law".

---

## 4. Data Model — Detailed

The migration file `database/migrations/2024_01_01_000001_create_document_analyses_table.php`
creates `document_analyses` with the following rules:

| Column                 | Type                   | Rationale                                                                            |
| ---------------------- | ---------------------- | ------------------------------------------------------------------------------------ |
| `id`                   | `uuid` PK              | Non-sequential, safe to expose in URLs, no race in distributed dispatch              |
| `chat_document_id`     | FK → `chat_documents` cascadeOnDelete | Deleting the doc removes its analyses — no orphan rows                    |
| `compare_document_id`  | FK nullable nullOnDelete | A compare analysis survives losing the other side; it just loses the pointer       |
| `user_id`              | FK → `users` cascadeOnDelete | Used for audit and per-user analytics via `da_user_created` index              |
| `analysis_type`        | `string(20)` default `full` | Matches the kernel's Literal set                                                |
| `status`               | `string(20)` default `pending` | Drives the state machine                                                   |
| `risk_score`           | `unsignedSmallInteger` nullable | Null while pending/processing; 0–100 when done                            |
| `risk_label`           | `string(30)` nullable  | Pre-computed label for index-friendly sorting and rendering                         |
| `highlights`           | `json` nullable        | Full array of `DocumentHighlight` objects                                           |
| `compare_highlights`   | `json` nullable        | Only populated for `analysis_type=compare`                                          |
| `metrics`              | `json` nullable        | Scoreboard payload (score, counts, parties, dates, summary)                         |
| `compare_summary`      | `text` nullable        | Diff summary for compare runs                                                       |
| `error_message`        | `text` nullable        | Populated only on `failed`; cleared on successful re-analyze                        |
| `timestamps`           | `created_at / updated_at` | Standard Eloquent                                                                |

The `DocumentAnalysis` Eloquent model casts the three JSON columns to PHP arrays and
`risk_score` to integer, and exposes convenience scopes:

- `scopeOfType($type, $compareDocumentId = null)` — encodes the "is-this-exact-view" query as
  a reusable chain, handling the nullable compare pointer with a `when()` clause.
- `scopeTerminal()` — `where status in (done, failed)`, useful for cleanup and reporting.
- `isReady()` / `isDone()` / `isFailed()` / `isPending()` / `isProcessing()` — guard helpers
  used by both the controller and the worker.

---

## 5. The JSON Contract in Detail

Every analysis response — whether cached, freshly-computed, or derived on the client — conforms
to this shape (as enforced by `DocumentAnalysisResource`):

```json
{
  "id": "…uuid…",
  "status": "done",
  "analysis_type": "full",
  "risk_score": 63,
  "risk_label": "High Risk",
  "highlights": [
    {
      "id": "h1",
      "category": "risk_high",
      "text": "The Service Provider may terminate this Agreement at any time without notice.",
      "explanation": "Unilateral termination without notice exposes the client to abrupt service loss.",
      "section": "Clause 12.1",
      "page_hint": 4
    }
  ],
  "compare_highlights": null,
  "metrics": {
    "risk_score": 63,
    "risk_label": "High Risk",
    "clause_count": 18,
    "obligation_count": 9,
    "flagged_count": 5,
    "parties": ["Acme LLC", "Beta Corp."],
    "key_dates": ["2026-06-30", "effective upon signature"],
    "summary": "Agreement is tilted in favour of the Service Provider..."
  },
  "compare_summary": null,
  "error_message": null,
  "created_at": "2026-04-14T10:20:00.000Z",
  "updated_at": "2026-04-14T10:20:12.340Z"
}
```

Notes:

- `error_message` is always `null` unless the row is in `failed`; the resource explicitly filters
  it so consumers don't mistake a stale message for a current error.
- For `analysis_type=compare`, `highlights` holds Document A findings, `compare_highlights`
  holds Document B findings, and `compare_summary` is the narrative overview.

---

## 6. Configuration & Secrets

### Laravel (`apigate/.env.example`)

```
DB_CONNECTION=pgsql
DB_HOST=127.0.0.1
DB_PORT=5432

QUEUE_CONNECTION=redis
REDIS_HOST=127.0.0.1
REDIS_PORT=6379

KERNEL_URL=http://127.0.0.1:9002
KERNEL_SECRET=1234

SANCTUM_STATEFUL_DOMAINS=localhost:5173,localhost:3000
SESSION_DOMAIN=localhost
```

`config/services.php` exposes exactly two kernel knobs — URL and secret — so the rest of the
codebase only knows "where is the kernel" and "how do I prove I'm allowed to talk to it".

### Kernel (`kernel/.env.example`)

```
APP_ENV=local
DEEPSEEK_API_KEY=1234
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
PYTHON_KERNEL_SECRET=1234
KERNEL_ALLOWED_ORIGINS=http://localhost:8000,http://localhost:5173
```

`APP_ENV=production` flips `/docs`, `/redoc`, and `/openapi.json` off — there is no route to the
schema in a production deploy.

### Frontend (`frontend/.env.example`)

```
VITE_API_BASE_URL=http://localhost:8000
```

In dev, Vite's `server.proxy['/api']` also forwards to `:8000`, so the SPA can run at
`:5173` without CORS contortions.

---

## 7. Observability

- **Correlation id** — each request to the kernel carries an `X-Request-ID` (generated by
  Laravel's HTTP client or passed from upstream), which the kernel middleware binds into the
  loguru context so every log line during that request carries it. The header is echoed back
  so Laravel can log the same id on its side.
- **Structured Laravel logs** — controllers and the job log `'[DocumentAnalysis] Dispatched'`,
  `'[ProcessDocumentAnalysis] Done'`, and `'[ProcessDocumentAnalysis] Failed'` with
  `analysis_id`, type, highlight counts, and risk score. Enough to reconstruct the
  request path without opening the DB.
- **DeepSeek usage logging** — `DeepSeekClient.generate` emits prompt and completion token
  counts per call at `DEBUG` level, so cost accounting is a `grep` away.
- **Failure visibility** — unexpected kernel errors land in `logger.exception` (full traceback)
  but the HTTP response is the sanitized message `"Analysis failed. Please try again."` —
  never the raw LLM output or exception text.

---

## 8. Extensibility Hooks

Where the system is *designed* to change:

1. **Add a new analysis type.** Add the literal to `AnalyzeDocumentRequest.analysis_type`, add
   a new `_SYSTEM_X` constant, register it in `_SYSTEM_MAP`, add the matching constant on the
   Laravel `DocumentAnalysis` model, and whitelist it in `DocumentAnalysisController::VALID_TYPES`.
   No DB migration needed — the column is a plain `string(20)`.
2. **Add a new highlight category.** Extend the `HighlightCategory` Literal, update the prompt
   rules, and add an entry to `HIGHLIGHT_COLORS` in `frontend/src/utils/documentHighlighter.js`.
   The sidebar, tooltip, and overlay all key off that map.
3. **Swap the LLM vendor.** Replace `DeepSeekClient` with a new adapter that implements the
   same `generate(messages, ...) -> str` interface. Nothing else moves.
4. **Stream tokens instead of returning a blob.** `DeepSeekClient.stream()` is already in the
   codebase (SSE from OpenAI); the kernel would expose `POST /analyze-document/stream`, the
   worker would buffer chunks and push partial results to the `analysis` row, and the frontend
   would render progressively. The polling loop would fall back cleanly.
5. **Replace polling with Laravel Echo + Reverb.** The resource shape is already a full snapshot
   of the row; a broadcast event carrying the resource payload on state change would make the
   UI push-driven without other code moves.

---

## 9. Known Constraints & Trade-offs

- **Single-node queue.** `QUEUE_CONNECTION=redis` with one `laravel-worker` container is a
  small deployment. For higher throughput, scale the worker horizontally — the job is stateless.
- **Shared secret, not mTLS.** `X-Kernel-Secret` is appropriate for an internal Docker
  network. In a multi-tenant or zero-trust environment, upgrade to mTLS or a service mesh.
- **Verbatim-substring highlight injection.** If the LLM paraphrases instead of quoting,
  the highlight will silently fail to render (the DOM walker won't find the substring). The
  system prompt aggressively tells the model "never paraphrase in the text field", but this
  remains a soft invariant. A future hardening step would fall back to fuzzy match (diff-match-patch)
  when the verbatim search fails.
- **Compare truncation.** Each document gets `_MAX_CHARS / 2 = 30 000` chars in compare mode.
  Very long contracts may lose material from later sections. A future mitigation is a
  chunk-and-reduce pipeline (analyze chunks, then summarize chunk findings into a final
  report).
- **PDF text layer fidelity.** `pdf.js` preserves a near-perfect text layer for modern PDFs but
  can struggle with scanned or image-only PDFs. The product assumes upstream text extraction
  (OCR) has already populated `ChatDocument::extracted_text` before `isReady()` returns true.

---

## 10. Summary

OpenAct's document analysis engine is a small, disciplined system. Three tiers, each with one
job. A queue between the HTTP layer and the AI so the user never waits on an open socket. A
typed contract at every boundary so a malformed LLM response can't poison the UI. A Pinia
cache and a Laravel idempotency check so the same click twice is free. And an in-browser
highlight pass so the review doesn't just *describe* the document — it annotates it, exactly
where the lawyer is already looking.
