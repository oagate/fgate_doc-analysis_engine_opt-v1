# OpenAct — Document Analysis Engine: Architecture

> A polyglot, three-tier, event-driven system for AI-powered legal document review.
> Stack: **Vue 3 (SPA)** → **Laravel 11 (API + Queue)** → **FastAPI (AI Kernel)** → **DeepSeek LLM**.

---

## 1. System Landscape (C4 — Context)

```mermaid
C4Context
    title OpenAct Document Analysis — System Context

    Person(lawyer, "Legal User", "Lawyer / compliance officer uploading contracts for review")

    System_Boundary(openact, "OpenAct Platform") {
      System(frontend, "Vue 3 SPA", "Document viewer, highlights, compare UI")
      System(apigate, "Laravel API Gate", "Auth, persistence, job dispatch, ownership guard")
      System(kernel, "FastAPI Kernel", "Prompt orchestration & LLM response shaping")
    }

    System_Ext(deepseek, "DeepSeek v3", "Foundation LLM — JSON contract-review prompt")
    System_Ext(postgres, "PostgreSQL 16", "Relational store: users, chats, documents, analyses")
    System_Ext(redis,    "Redis 7",       "Queue broker + cache")

    Rel(lawyer, frontend, "HTTPS")
    Rel(frontend, apigate, "REST / Sanctum cookie", "JSON")
    Rel(apigate, postgres, "SQL (pgsql)")
    Rel(apigate, redis,   "Queue: streaming")
    Rel(apigate, kernel,  "POST /analyze-document", "HTTP + X-Kernel-Secret")
    Rel(kernel, deepseek, "Chat Completions API", "HTTPS")
```

---

## 2. Container View (C4 — Containers)

```mermaid
flowchart LR
    subgraph Browser["Browser"]
      VUE["Vue 3 SPA<br/>(Vite · Pinia · pdf.js · mammoth)"]
    end

    subgraph Edge["Application Tier"]
      LAR["Laravel 11<br/>PHP-FPM · Sanctum"]
      WRK["Queue Worker<br/>php artisan queue:work<br/>--queue=streaming"]
    end

    subgraph AI["AI Tier"]
      FAS["FastAPI Kernel<br/>Uvicorn · Pydantic v2 · loguru"]
    end

    subgraph Data["Data Tier"]
      PG[("PostgreSQL 16")]
      RDS[("Redis 7")]
    end

    DS["DeepSeek v3<br/>(external)"]

    VUE -- "REST /api/chats/.../analyze" --> LAR
    VUE -- "Poll /analysis" --> LAR
    LAR -- "Read/Write" --> PG
    LAR -- "Dispatch job" --> RDS
    RDS -- "Pop job" --> WRK
    WRK -- "POST /analyze-document<br/>X-Kernel-Secret" --> FAS
    WRK -- "Persist result" --> PG
    FAS -- "chat.completions" --> DS
    FAS -- "JSON response" --> WRK

    classDef db fill:#0d1117,stroke:#30363d,color:#e6edf3
    class PG,RDS db
```

---

## 3. Component View — Inside Each Tier

### 3.1 Laravel API Gate

```mermaid
flowchart TB
    R["routes/api.php<br/>auth:sanctum · throttle:60,1"]
    CTRL["DocumentAnalysisController<br/>@analyze / @show"]
    JOB["ProcessDocumentAnalysis<br/>(ShouldQueue · tries=2 · timeout=120)"]
    MDL["DocumentAnalysis<br/>(Eloquent · HasUuids)"]
    RES["DocumentAnalysisResource<br/>(API shape)"]
    CFG["config/services.php<br/>kernel.url / kernel.secret"]
    HTTP["Http::withHeaders(X-Kernel-Secret)"]

    R --> CTRL
    CTRL -->|create pending| MDL
    CTRL -->|dispatch onQueue streaming| JOB
    CTRL -->|return 202| RES
    JOB -->|load| MDL
    JOB --> CFG
    JOB --> HTTP
    HTTP -->|/analyze-document| K[("FastAPI Kernel")]
    JOB -->|write result| MDL
```

### 3.2 FastAPI Kernel

```mermaid
flowchart TB
    MAIN["main.py<br/>FastAPI app<br/>CORS · RequestID · Secret guard"]
    SCH["analysis_schemas.py<br/>Pydantic v2 models"]
    SVC["DocumentAnalysisService<br/>(singleton)"]
    PRMT["System prompts<br/>full · risk · clauses · compare"]
    CLT["DeepSeekClient<br/>(AsyncOpenAI)"]
    JSN["_parse_json<br/>(fence strip + brace rescue)"]
    METR["_build_metrics<br/>_build_highlights<br/>_risk_label"]

    MAIN -->|validates request| SCH
    MAIN --> SVC
    SVC --> PRMT
    SVC --> CLT
    CLT -->|chat.completions| DS[("DeepSeek v3")]
    CLT -->|raw str| JSN
    JSN -->|dict| METR
    METR -->|AnalyzeDocumentResponse| MAIN
```

### 3.3 Vue 3 Frontend

```mermaid
flowchart TB
    PANEL["DocumentAnalysisPanel.vue<br/>(orchestrator)"]
    VIEWER["DocumentViewer.vue<br/>(pdf.js · mammoth · plain)"]
    SIDE["DocumentAnalysisSidebar.vue<br/>(risk gauge · findings)"]
    CMP["DocumentCompareView.vue<br/>(dual-pane)"]
    TIP["DocumentHighlightTooltip.vue<br/>(Teleport)"]
    HL["utils/documentHighlighter.js<br/>(TreeWalker · <mark> injection)"]
    COMP["composables/useDocumentAnalysis.js<br/>(poll · derive risk/clauses)"]
    STORE["stores/documentAnalysis.js<br/>(Pinia cache)"]
    AX["services/axios.js<br/>(XSRF · withCredentials)"]

    PANEL --> VIEWER
    PANEL --> SIDE
    PANEL --> CMP
    PANEL --> TIP
    PANEL --> COMP
    COMP --> STORE
    STORE --> AX
    VIEWER --> HL
    CMP --> VIEWER
    SIDE -->|finding-click| PANEL
    VIEWER -->|highlight-click| PANEL
```

---

## 4. End-to-End Sequence — Triggering & Resolving an Analysis

```mermaid
sequenceDiagram
    autonumber
    actor U as Lawyer
    participant V as Vue SPA
    participant L as Laravel API
    participant DB as PostgreSQL
    participant Q as Redis Queue
    participant W as Queue Worker
    participant K as FastAPI Kernel
    participant D as DeepSeek v3

    U->>V: Open document panel
    V->>L: POST /api/chats/{c}/documents/{d}/analyze (type=full)
    L->>L: Sanctum + ownership check
    L->>DB: SELECT latest done analysis (cache hit?)
    alt cache hit & !force
      DB-->>L: existing row
      L-->>V: 200 + DocumentAnalysisResource
    else miss
      L->>DB: DELETE stale pending/failed rows
      L->>DB: INSERT status=pending
      L->>Q: dispatch ProcessDocumentAnalysis
      L-->>V: 202 + pending resource
      V->>V: start polling (2.5s · max 48)
      Q->>W: pop job
      W->>DB: UPDATE status=processing
      W->>K: POST /analyze-document (+ X-Kernel-Secret)
      K->>K: validate Pydantic request
      K->>D: chat.completions (system+user, temp=0.1)
      D-->>K: JSON payload (highlights + metrics)
      K->>K: _parse_json → Pydantic response
      K-->>W: 200 AnalyzeDocumentResponse
      W->>DB: UPDATE status=done + highlights/metrics
      loop Polling
        V->>L: GET /api/chats/{c}/documents/{d}/analysis
        L->>DB: SELECT latest
        DB-->>L: row (pending → processing → done)
        L-->>V: resource
      end
      V->>V: applyHighlights(container, highlights)
    end
```

---

## 5. Data Model — Entity Relationship

```mermaid
erDiagram
    USERS ||--o{ CHATS : owns
    USERS ||--o{ DOCUMENT_ANALYSES : requested
    CHATS ||--o{ CHAT_DOCUMENTS : contains
    CHAT_DOCUMENTS ||--o{ DOCUMENT_ANALYSES : "primary target"
    CHAT_DOCUMENTS ||--o{ DOCUMENT_ANALYSES : "compare target (optional)"

    USERS {
      uuid id PK
      string email
      string name
    }

    CHATS {
      uuid id PK
      uuid user_id FK
      timestamp created_at
    }

    CHAT_DOCUMENTS {
      uuid id PK
      uuid chat_id FK
      string original_name
      string mime_type
      text extracted_text
      string status
    }

    DOCUMENT_ANALYSES {
      uuid   id PK
      uuid   chat_document_id FK
      uuid   compare_document_id FK "nullable"
      uuid   user_id FK
      string analysis_type  "full|risk|clauses|compare"
      string status         "pending|processing|done|failed"
      smallint risk_score   "0–100"
      string risk_label     "Low|Medium|High|Critical"
      json   highlights
      json   compare_highlights
      json   metrics
      text   compare_summary
      text   error_message
      timestamp created_at
      timestamp updated_at
    }
```

### Indexes on `document_analyses`

| Name                  | Columns                                                 | Purpose                                                    |
| --------------------- | ------------------------------------------------------- | ---------------------------------------------------------- |
| `da_doc_status`       | `(chat_document_id, status)`                            | Worker/controller filtering by state                       |
| `da_doc_type_compare` | `(chat_document_id, analysis_type, compare_document_id)` | Cache lookup for "already computed this exact view"       |
| `da_user_created`     | `(user_id, created_at)`                                 | User-centric history / audit                               |

---

## 6. JSON Contract (Kernel ↔ DeepSeek ↔ Worker)

```mermaid
classDiagram
    class AnalyzeDocumentRequest {
      +string document_id
      +string filename
      +string text
      +enum   analysis_type  "full|risk|clauses|compare"
      +string? compare_text
      +string? compare_filename
      +string language = "uz"
    }

    class AnalyzeDocumentResponse {
      +string document_id
      +string analysis_type
      +DocumentHighlight[] highlights
      +DocumentAnalysisMetrics metrics
      +DocumentHighlight[]? compare_highlights
      +string? compare_summary
    }

    class DocumentHighlight {
      +string id
      +enum category
      +string text  "max 500"
      +string explanation
      +string? section
      +int? page_hint
    }

    class DocumentAnalysisMetrics {
      +int risk_score  "0–100"
      +string risk_label
      +int clause_count
      +int obligation_count
      +int flagged_count
      +string[] parties
      +string[] key_dates
      +string summary
    }

    AnalyzeDocumentResponse "1" o-- "*" DocumentHighlight
    AnalyzeDocumentResponse "1" o-- "1" DocumentAnalysisMetrics
```

Highlight categories form a closed enum:

```
risk_high · risk_medium · risk_low · clause_key · obligation · party · date
```

---

## 7. Analysis State Machine

```mermaid
stateDiagram-v2
    [*] --> pending: Controller inserts row
    pending --> processing: Worker picks up job
    processing --> done: Kernel returns JSON + worker writes result
    processing --> failed: Kernel error / timeout / parse failure
    failed --> pending: Re-analyze (force=true)
    done --> pending: Re-analyze (force=true)
    done --> [*]
    failed --> [*]
```

---

## 8. Deployment Topology (Docker Compose)

```mermaid
flowchart LR
    subgraph DockerHost["Docker Host"]
      direction TB
      subgraph Frontend_Net["frontend net"]
        V["vue (node:20-alpine)<br/>:5173"]
      end
      subgraph App_Net["app net"]
        L["laravel (php-fpm)<br/>:8000"]
        W["laravel-worker<br/>queue:work streaming"]
        F["fastapi (python:3.12-slim)<br/>:9002 · 2 uvicorn workers"]
      end
      subgraph Data_Net["data net"]
        P[("postgres:16-alpine<br/>:5432")]
        R[("redis:7-alpine<br/>:6379")]
      end
    end

    DS["api.deepseek.com"]

    V --> L
    L --> P
    L --> R
    W --> P
    W --> R
    W --> F
    F --> DS

    L -.healthcheck.-> P
    L -.healthcheck.-> R
```

**Ports exposed to host:** `5173` (Vite), `8000` (Laravel), `9002` (FastAPI — local only), `5432`, `6379`.

---

## 9. Security & Trust Boundaries

```mermaid
flowchart LR
    subgraph Internet
      B["Browser"]
    end
    subgraph PublicZone["Public Zone (TLS)"]
      L["Laravel<br/>Sanctum cookie · CSRF · throttle 60/min"]
    end
    subgraph PrivateZone["Private Zone (internal network)"]
      F["FastAPI Kernel<br/>X-Kernel-Secret guard<br/>CORS allowlist"]
      P[("PostgreSQL")]
      R[("Redis")]
    end
    subgraph VendorZone["Vendor"]
      D["DeepSeek"]
    end

    B <-- "HTTPS + cookie" --> L
    L <-- "internal HTTP<br/>shared secret" --> F
    L --> P
    L --> R
    F <-- "HTTPS + API key" --> D
```

**Trust rules enforced in code:**

| Boundary              | Mechanism                                                                                    |
| --------------------- | -------------------------------------------------------------------------------------------- |
| Browser → Laravel     | `auth:sanctum` cookie, XSRF header (`axios.js`), `throttle:60,1`                             |
| Chat / Document ACL   | `authorizeAccess()` verifies `chat.user_id === request->user->id` and document∈chat          |
| Laravel → Kernel      | `X-Kernel-Secret` header (`config/services.php::kernel.secret`)                              |
| Kernel middleware     | `verify_secret` rejects any non-`/health` request without matching secret                    |
| Kernel CORS           | `KERNEL_ALLOWED_ORIGINS` env — defaults to Laravel + Vite origins only                       |
| Docs exposure         | `docs_url`/`redoc_url` disabled when `APP_ENV=production`                                    |
| Prompt length         | `_truncate` caps doc text at 60 000 chars (30 000 × 2 on compare) to bound token spend       |
| Output shape          | Pydantic `AnalyzeDocumentResponse` rejects malformed LLM output before persistence           |
| DOCX sanitization     | `DocumentViewer._sanitize` strips `<script>/<style>/on*=/javascript:` before `v-html`        |

---

## 10. Runtime Characteristics

| Concern             | Value / Policy                                                                        |
| ------------------- | ------------------------------------------------------------------------------------- |
| Queue               | Redis, dedicated queue `streaming`                                                    |
| Worker retry policy | `$tries = 2`, `$timeout = 120s` (Laravel Job)                                         |
| Kernel HTTP timeout | `Http::timeout(110)` (Laravel → FastAPI)                                              |
| Uvicorn workers     | 2 (Dockerfile `CMD`)                                                                  |
| LLM call            | `deepseek-v3`, `temperature=0.1`, `max_tokens=6000` (single) / `8000` (compare)       |
| Frontend polling    | 2 500 ms interval, max 48 attempts (~2 min ceiling)                                   |
| Idempotency         | Controller returns cached `done` row unless `force=true`                              |
| Observability       | loguru `X-Request-ID` propagation, Laravel `Log::info` on dispatch / success / fail   |

---

## 11. Analysis Type Matrix

| `analysis_type` | System Prompt      | Output Highlights                      | Notes                                  |
| --------------- | ------------------ | -------------------------------------- | -------------------------------------- |
| `full`          | `_SYSTEM_FULL`     | 8–40 across all 7 categories           | Default end-to-end review              |
| `risk`          | `_SYSTEM_RISK`     | Only `risk_high/medium/low`            | Frontend can also derive from cached `full` |
| `clauses`       | `_SYSTEM_CLAUSES`  | Only `clause_key`                      | Frontend can also derive from cached `full` |
| `compare`       | `_SYSTEM_COMPARE`  | `highlights_a` + `highlights_b` + `compare_summary` | Two-doc diff, splits token budget in half |

---

## 12. File Map

```
fgate_doc-analysis_engine_opt-v1/
├── docker-compose.yml          # 5 services: postgres · redis · laravel · laravel-worker · fastapi · vue
├── apigate/                    # Laravel 11 API Gate
│   ├── routes/api.php          # POST /analyze · GET /analysis
│   ├── app/Http/Controllers/Api/DocumentAnalysisController.php
│   ├── app/Http/Resources/DocumentAnalysisResource.php
│   ├── app/Jobs/ProcessDocumentAnalysis.php
│   ├── app/Models/DocumentAnalysis.php
│   ├── config/services.php     # kernel.url / kernel.secret
│   └── database/migrations/…_create_document_analyses_table.php
├── kernel/                     # FastAPI AI kernel
│   ├── main.py                 # App · middlewares · routes
│   ├── api/analysis_schemas.py # Pydantic request/response
│   ├── core/deepseek_client.py # AsyncOpenAI wrapper
│   ├── core/document_analysis_service.py # Prompts + JSON parsing + metrics
│   ├── requirements.txt
│   └── Dockerfile
└── frontend/                   # Vue 3 SPA
    ├── vite.config.js          # @ alias, /api proxy → :8000
    ├── package.json            # vue, pinia, vue-router, pdfjs-dist, mammoth, axios
    └── src/
        ├── services/axios.js
        ├── stores/documentAnalysis.js
        ├── composables/useDocumentAnalysis.js
        ├── utils/documentHighlighter.js
        └── components/DocumentAnalysis/
            ├── DocumentAnalysisPanel.vue
            ├── DocumentAnalysisSidebar.vue
            ├── DocumentViewer.vue
            ├── DocumentCompareView.vue
            ├── DocumentHighlightTooltip.vue
            └── DocumentPreviewModal.vue
```
