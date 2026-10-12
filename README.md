# CineMatch AI

CineMatch AI is an **Agent Harness Engineering Platform** for exploring
reliable agent systems. It includes a source-linked movie catalog,
deterministic tools, a bounded agent harness, guardrails, and a local RAG
pipeline with source-attributed evidence. A deterministic offline mock is the
default provider; an opt-in OpenAI-compatible adapter can generate
source-grounded natural-language responses when configured with local
credentials.

## Technology

- **Frontend:** React, TypeScript, Vite, and responsive CSS
- **Backend:** Python, FastAPI, Uvicorn, Pydantic, MySQL Connector/Python, and Sentence Transformers for local embeddings
- **Tests:** pytest and FastAPI `TestClient`
- **Database:** MySQL, managed locally with MySQL Workbench

## Project structure

```text
backend/
  app/
    api/        API routes
    agent/      Provider interface, tool registry, policy, orchestration, traces
    core/       Environment-backed settings
    database/   MySQL connections and idempotent catalog initialization
    rag/        Source loading, chunking, embeddings, local vector index, retrieval
    schemas/    Pydantic response contracts
    tools/      Deterministic movie catalog functions
    main.py     FastAPI application
  data/
    movies.json Source-controlled, curated seed catalog
    rag_documents.json Locally maintained supporting documents (starts empty)
    rag_index.json Generated, ignored local vector index
  sql/
    mysql_setup.sql  MySQL Workbench schema setup script
  tests/        Backend endpoint tests
frontend/
  src/
    components/ Reusable UI components (planned)
    pages/      Page-level views (planned)
    services/   API client
    App.tsx     Project dashboard, movie catalog, agent run panel
data/           Reserved for project data
docs/           Architecture and design notes
```

## Local setup

### Backend

From the project root, create and activate a virtual environment:

```powershell
py -m venv backend/.venv
.\backend\.venv\Scripts\Activate.ps1
```

Install dependencies and copy the local environment template:

```powershell
python -m pip install -r backend/requirements.txt
Copy-Item backend/.env.example backend/.env
```

In MySQL Workbench, open and run [`backend/sql/mysql_setup.sql`](backend/sql/mysql_setup.sql)
with an account allowed to create schemas. It creates `cinematch_db` and the
separate `cinematch_test_db`, including the movie and genre tables. Configure
`MYSQL_USER` and `MYSQL_PASSWORD` in the ignored local `backend/.env` for an
account that can connect to `127.0.0.1:3306`. Do not commit that file. The
account needs `SELECT`, `INSERT`, and table-creation privileges on
`cinematch_db`, plus `SELECT`, `INSERT`, `DELETE`, and table-creation privileges
on `cinematch_test_db`. Tests only clear tables in the test schema; the fixture
rejects the production schema and only accepts names prefixed with
`cinematch_test_`.

For a local account, an administrator can grant the needed access in Workbench
(replace the password placeholder before running):

```sql
CREATE USER IF NOT EXISTS 'cinematch_app'@'localhost'
    IDENTIFIED BY 'REPLACE_WITH_A_LOCAL_PASSWORD';
GRANT SELECT, INSERT, CREATE, INDEX, REFERENCES
    ON cinematch_db.* TO 'cinematch_app'@'localhost';
GRANT SELECT, INSERT, DELETE, CREATE, INDEX, REFERENCES
    ON cinematch_test_db.* TO 'cinematch_app'@'localhost';
```

Set the same local password in `MYSQL_PASSWORD` in `backend/.env`. Use a
separate, strong value locally; the example is not a usable credential.

To seed the production catalog and verify the configured connection, run this
from the backend directory:

```powershell
python -m app.database.init_db
```

The initializer validates and loads the 13 records in `data/movies.json`,
creates any missing tables, and inserts only absent movie IDs without
overwriting or deleting existing rows. It prints the resulting row count.

### Build the local RAG index

The movie catalog remains in MySQL. RAG reads the source JSON and an optional
local support-document file, writes embeddings to an ignored local vector
index, and does not create or modify MySQL tables.

```powershell
cd backend
python -m app.rag.ingest
```

The default embedding adapter is the real CPU-based
`sentence-transformers/all-MiniLM-L6-v2` model. Install backend dependencies
first. The first index build needs the model available in the local Sentence
Transformers cache and may require internet access to download it; subsequent
retrieval and the automated tests run offline. If `sentence-transformers` or
the model is unavailable, indexing fails explicitly and does not replace an
existing index. There is no production fallback to synthetic embeddings.
Configure `RAG_EMBEDDING_MODEL` and `RAG_EMBEDDING_REVISION` to choose/version
another locally available model, then rebuild the index. A model identity
change makes the previous index incompatible until rebuilt.

`backend/data/rag_documents.json` starts as `[]`. Add only locally maintained,
verified supporting documents in this format:

```json
[
  {
    "document_id": "notes:stable-id",
    "source_title": "Maintained source title",
    "source_reference": "source:maintained-source-id",
    "movie_id": null,
    "text": "Verified supporting text maintained by the project.",
    "metadata": {}
  }
]
```

Use a real HTTPS URL or stable `source:<identifier>`; document IDs must be
unique. Do not add credentials, filesystem paths, guessed facts, or fabricated
references. The generated `data/rag_index.json` and temporary rebuild files
are excluded from Git. `RAG_CHUNK_SIZE` and `RAG_CHUNK_OVERLAP` set deterministic
character chunking (chunks are capped at 2,000 characters). Retrieval accepts
queries up to 500 characters, returns at most five passages, supports optional
movie/source filters, and applies a cosine-similarity threshold. Rebuilds are
atomic, deduplicate stable chunk IDs, and validate index format, model
identity/revision, and vector dimensions. `RAG_DEFAULT_TOP_K` and
`RAG_MINIMUM_SIMILARITY` set the default retrieval count and relevance
threshold. Registered retrieval calls enforce a 0.30 minimum similarity floor
(or the configured higher threshold), even if a provider proposes a lower
value; raise the setting to make retrieval stricter. Recheck this floor if the
embedding model or source corpus changes.

Start the API:

```powershell
cd backend
python -m uvicorn app.main:app --reload
```

Run backend tests (from the project root, with the environment active and both
MySQL schemas configured):

```powershell
$env:PYTHONPATH = "backend"
python -m pytest backend/tests
```

The test fixture requires the exact `MYSQL_DATABASE=cinematch_db` and
`MYSQL_TEST_DATABASE=cinematch_test_db` configuration, opens and verifies the
test schema before cleanup, and performs destructive test cleanup only in
`cinematch_test_db`.

### Frontend

In a separate terminal from the project root:

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```

`VITE_API_BASE_URL` defaults in `.env.example` to `http://localhost:8000`.
The frontend calls the live `/api/health` endpoint and shows checking,
connected, or actionable unavailable states. The movie catalog section
searches the actual backend and fetches selected details from the API. The
agent panel sends a question to the backend, then fetches and displays the
trace associated with that run, including actual retrieved excerpts and source
references when the retrieval tool was used.

Connection settings are `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`,
`MYSQL_PASSWORD`, and `MYSQL_DATABASE`; tests use `MYSQL_TEST_DATABASE` (default
`cinematch_test_db`). The JSON source path is configurable through
`MOVIES_CATALOG_PATH`. Credentials belong only in the ignored local
`backend/.env`, never in source control.

## Local URLs

- Frontend: <http://localhost:5173>
- Backend root: <http://localhost:8000/>
- Health check: <http://localhost:8000/api/health>
- Database readiness: <http://localhost:8000/api/ready>
- System information: <http://localhost:8000/api/system/info>
- Movie search: <http://localhost:8000/api/movies>
- Movie catalog statistics: <http://localhost:8000/api/movies/stats>
- Agent run: `POST http://localhost:8000/api/agent/run`
- Agent trace: `GET http://localhost:8000/api/agent/runs/{run_id}/trace`
- Interactive API docs: <http://localhost:8000/docs>

## Phase 2 movie catalog

The local seed currently contains 13 manually curated records: 11 Tamil films
and one each in Malayalam and Telugu. Every record includes a source article
URL, and the short overview is an original paraphrase of that article's
description. The references are English Wikipedia film articles, which are
secondary sources rather than an official structured dataset. This small seed
was chosen to avoid inventing a larger catalog. All ratings are `null` because
no consistent rating source was selected; runtimes remain `null` except for
the Baashha article's 144-minute runtime. Missing values are never inferred.
This is a development catalog, not a complete or authoritative filmography.
The article URLs are recorded per movie for attribution and verification; the
overview text is paraphrased rather than copied from the articles.

The catalog JSON is [backend/data/movies.json](backend/data/movies.json).
MySQL normalizes genres into `genres` and `movie_genres`; the database is
managed by MySQL and is not stored in the repository.

### Movie API

- `GET /api/movies?query=robot&language=Tamil&genre=Action&release_year=2010&limit=20`
  searches title and overview and optionally applies metadata filters.
- `POST /api/movies/filter` applies strict constraints. For example:

  ```json
  {
    "language": "Tamil",
    "genre": "Action",
    "min_year": 2000,
    "max_year": 2022,
    "min_runtime": 120,
    "min_rating": 7,
    "limit": 10
  }
  ```

- `GET /api/movies/{movie_id}` returns a record or HTTP 404.
- `GET /api/movies/stats` calculates total records, distinct languages and
  genres, and missing runtime/rating counts from MySQL.

Search/filter results include the total match count before limiting and at
most 50 returned records. Runtime/rating constraints exclude rows where that
metadata is missing. The deterministic Python entry points are
`search_movies`, `filter_movies`, and `get_movie_details` in
`backend/app/tools/movie_tools.py`; they use parameterized MySQL statements,
do not call external services, and never accept SQL from callers.

## Phase 3 agent harness

`POST /api/agent/run` accepts a JSON request and runs an async provider/harness
loop. The included `MockProvider` uses simple deterministic rules to choose
registered movie tools; it is not an LLM. `OpenAIChatProvider` can be selected
explicitly through `LLM_PROVIDER=openai`. Both providers propose decisions
only; the fixed backend registry, authorization policy, argument validation,
and bounded orchestrator remain authoritative. The mock remains the default
and is used by the automated suite.
Recommendation phrasing with detected genre/language criteria uses the
existing catalog filters and returns matching records; it is not a
personalized or ranked recommendation system.

The harness owns the bounded loop, strict registered-tool lookup, input
validation, authorization, repeated-call detection, timeouts, consecutive
tool-error handling, and final status. The provider only proposes a structured
tool call or a final response. A proposed call is not authorization. Only
`search_movies`, `filter_movies`, `get_movie_details`, and
`retrieve_movie_context` are registered; unknown tools are denied and never
dispatched. Existing catalog implementations are reused without duplication.

Limits default to five iterations, three consecutive tool errors, and thirty
seconds per run. The longer default allows the local embedding model to load on
the first RAG request; later retrievals use the process-cached model. Request
configuration can lower/adjust these within hard caps
(1–5 iterations, 1–3 consecutive errors, and a positive timeout up to 30
seconds). Tool argument JSON is capped at 8 KiB. Only the latest 100 traces are
kept in process memory; traces disappear on backend restart and are not an
audit log. Trace data excludes the original user message and final response
contents; common credential-shaped strings and sensitive-named tool arguments
are redacted before trace storage.

## Phase 4 guardrails

The provider mode defaults to offline, deterministic `MockProvider`; there is
no real LLM configured unless `LLM_PROVIDER=openai` and a key is supplied.
`backend/app/agent/guardrails.py` performs
checks at the input, tool, retrieved-content, and output boundaries:

1. **Input:** request schemas reject malformed, unsupported, blank, and
   oversized request values with a safe HTTP 422 response. A contextual,
   multi-signal heuristic blocks some clear instruction-hijacking attempts
   before the provider is called; normal movie questions remain allowed.
2. **Tool call:** the harness checks the fixed registry and existing
   authorization/repeat-call policy, checks JSON argument size, then validates
   the registered Pydantic schema before execution. Unknown tools such as
   `delete_movie_database` cannot execute. Tools remain read-only movie
   lookups; no SQL, shell, Python, filesystem, or database mutation dispatch
   is exposed.
3. **Retrieved content:** Phase 5 screens returned passages for sensitive
   values and local filesystem paths, records a guardrail event, and marks
   allowed evidence as untrusted content. Instruction-like passages remain
   data and cannot authorize tools.
4. **Output:** final responses must be non-empty, within the configured
   `max_response_chars` cap (at most 4,000), and free of detected credentials,
   traceback-shaped text, and runtime/rating claims contradicted by missing
   catalog values. Rejected responses return a safe explanation and terminal
   `output_denied` status, not a success-shaped fallback.

Each run trace records ordered guardrail stage/result, a safe reason code,
whether execution was blocked, authorization decisions, and the terminal
status. It does not store the full user message or final answer. Catalog and
retrieved observations are explicitly marked as untrusted data, not
instructions. Detection is heuristic and cannot guarantee detection of every
prompt-injection attempt. The fixed registry and policy checks remain the
enforcement boundary even if detection misses an attempt.

## Phase 5 retrieval-augmented generation

The `backend/app/rag` package separates source loading, normalization and
chunking, embedding generation, local indexing, retrieval, and evidence
formatting. It ingests the 13 existing JSON catalog records (preserving their
real article URLs and null metadata) plus optional maintained documents from
`backend/data/rag_documents.json`. No websites are scraped, and the MySQL
catalog/schema are unchanged.

`SentenceTransformerEncoder` is the production adapter for the local CPU model
`sentence-transformers/all-MiniLM-L6-v2`. Encoded vectors are cached in the
ignored `backend/data/rag_index.json` small-corpus index. Similarity uses
cosine scores with stable tie ordering, an adjustable minimum, at most five
results, and optional movie/source filters. The index stores its format
version, model/revision identity, and vector dimension. Rebuilds deduplicate
chunk IDs and atomically replace the previous index only after a successful
embedding pass.

`retrieve_movie_context` is a fixed registered tool. It uses existing
authorization, schema validation, argument-size limits, bounded iterations,
timeout, repeat-call detection, and trace policies. Retrieved text and metadata
are screened for sensitive data and filesystem paths, then passed as
`untrusted_retrieved_content`; instruction-like text remains data and cannot
authorize another tool or change loop policy. Traces include bounded evidence
excerpts and the exact indexed source title/reference, but not vector values,
index paths, or internal document/chunk IDs.

The deterministic mock provider can quote retrieved passages and include
their source references when asked for sources/evidence. It is not an LLM and
does not generate natural-language answers grounded in evidence. An empty
retrieval result is reported as insufficient knowledge-base coverage. The
source seed is small and not comprehensive; missing movie ratings/runtimes
remain unknown. Prompt-injection and sensitive-content checks are defense in
depth, not guarantees.

Rebuild an index after source changes with `python -m app.rag.ingest` from the
backend directory, then restart the API to reload its process-local retriever.
The first model use requires `sentence-transformers` and cached model weights;
the model may need to be downloaded once. Automated tests use an explicitly
test-only fixed-vector encoder and temporary indexes, not a live service or
internet. If the production dependency/model is missing, the index command
fails clearly and agent retrieval ends with the safe
`retrieval_unavailable` status; the runtime never substitutes fake embeddings.

## Phase 6 deterministic evaluations

`backend/data/rag_golden_set.json` is a versioned set of locally verified
retrieval cases. It defines expected movie document IDs, source references,
supported facts, explicitly unsupported claims, an unanswerable query, and
acceptance thresholds. It does not contain generated answer labels for an
LLM.

After installing dependencies and building the real index, run from
`backend`:

```powershell
python -m app.evals.run_eval
```

This command loads the existing local index read-only, uses the same cached
embedding model, makes no MySQL writes, and writes
`data/rag_eval_report.json` (Git-ignored). `RAG_EVAL_REPORT_PATH` can change
the report destination. The report includes dataset/evaluation versions,
model identity, index version and dimension, timestamp, per-case evidence and
citation checks, metric values, safety checks, and failures. The exit code is
nonzero for failed acceptance thresholds, failed safety checks, or missing/
incompatible local model/index configuration.

Metrics are computed from actual retrieved passages: **Recall@K** is the
fraction of expected relevant documents retrieved in the first K results;
**MRR** averages the reciprocal rank of the first relevant result over
answerable cases; **retrieval coverage** is the fraction of answerable cases
with a relevant hit; **empty-result accuracy** is the fraction of unanswerable
cases returning no passages; **source-attribution correctness** is the
fraction of returned movie passages whose source reference exactly matches the
indexed and golden-set reference. Safety checks exercise unsupported rating
claims, citation mismatch, input validation, insufficient-evidence
abstention, malicious retrieved text, and unregistered-tool denial.

These are deterministic retrieval and guardrail checks, not an evaluation of
natural-language model quality. The mock provider is not a live LLM. Golden
facts and the 13-record corpus are small; scores do not establish broad
retrieval quality.

## Phase 7: optional OpenAI-compatible provider

The backend includes `OpenAIChatProvider`, implemented with the existing
`httpx` dependency. It calls the OpenAI Chat Completions API by default; a
compatible HTTPS endpoint can be selected with `OPENAI_BASE_URL`. The default
mode remains the offline mock. Configure these entries only in the ignored
local `backend/.env`:

```dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=your-local-provider-key
OPENAI_MODEL=gpt-4o-mini
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_TIMEOUT_SECONDS=20
OPENAI_MAX_RETRIES=1
```

Never put a real key in source files or frontend configuration. The
`GET /api/agent/provider` endpoint and dashboard show only provider mode,
model name, and whether configuration is available; they do not return the
credential. If OpenAI is selected without a key, agent runs fail safely with a
provider error instead of silently falling back to the mock. The provider uses
HTTPS, a bounded per-request timeout, at most two retries, safe error messages,
and validates every returned decision against the harness decision schema.

The model receives only the four registered tool schemas. Its tool calls are
proposals: unknown names and invalid arguments are still rejected by the
existing registry and harness policy before execution. Retrieved passages are
sent as explicitly untrusted observations, and final responses containing
retrieved evidence must cite exact references present in those observations.
The provider prompt asks for evidence-grounded answers and abstention, while
the existing output guardrails reject detected unsupported runtime/rating
claims, secrets, tracebacks, and oversized responses. These controls cannot
prove every free-form claim semantically; injection detection and answer
grounding are not guarantees.

The Phase 6 command continues to measure actual retrieval and deterministic
safety only. It does not score LLM answer quality. The provider adapter has
offline mocked HTTP tests for response parsing, timeout/retry, missing
credentials, tool authorization/schema enforcement, malicious observations,
and citation validation. A live request requires a locally configured key and
is intentionally not run by the automated tests.

Phase 10 adds the versioned `backend/tests/data/llm_answer_quality_cases.json`
scenario set. Run its HTTP-mocked harness checks without a live key or paid
request using:

```powershell
Set-Location 'C:\Users\kgoku\Desktop\CineMatch\backend'
$env:PYTHONPATH = '.'
.\.venv\Scripts\python.exe -m pytest tests/test_llm_provider.py tests/test_llm_answer_quality.py -q
```

These scenarios validate deterministic boundaries—tool authorization,
supported source citations, known-fact inclusion, abstention, metadata
guardrails, and sanitized provider failures—using mocked provider responses.
They are not an evaluation score for live model answer quality or a semantic
proof that arbitrary claims are entailed by cited sources. No live request is
made by this command or the normal test suite.

To use the real provider, set `LLM_PROVIDER=openai` and the local
`OPENAI_API_KEY`, then start the backend from `backend`. To switch back to the
deterministic mock, set `LLM_PROVIDER=mock` and restart the backend. Provider
selection is server-side only.

See [Phase 10 verification](docs/PHASE10_REPORT.md) for the mocked answer
quality scenarios, provider failure regression results, retrieval evaluation,
and live-provider limitations. No live request is made without explicit
authorization.

### Agent API

- `POST /api/agent/run`

  ```json
  {
    "message": "Tell me about Baashha",
    "config": {
      "max_iterations": 5,
      "max_consecutive_tool_errors": 3,
      "timeout_seconds": 30,
      "max_response_chars": 4000
    }
  }
  ```

  Returns the run ID, final response, terminal status, iteration/tool-request
  counts, and trace summary.
- `GET /api/agent/runs/{run_id}/trace` returns the ordered events for a stored
  run, or `404` when the ID is unknown or its trace has been evicted.

Example from PowerShell:

```powershell
$body = @{ message = "Tell me about Baashha" } | ConvertTo-Json
$run = Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/api/agent/run `
  -ContentType "application/json" -Body $body
Invoke-RestMethod "http://localhost:8000/api/agent/runs/$($run.run_id)/trace"
```

Terminal statuses include `completed`, `input_denied`, `policy_denied`,
`output_denied`, `tool_error_limit`, `iteration_limit`, `timeout`,
`provider_error`, `retrieval_unavailable`, and `invalid_decision`.

The dashboard displays actual RAG evidence and the active provider mode in
the agent timeline. The backend includes an opt-in OpenAI-compatible adapter;
live answer quality still requires a configured key and separate evaluation.
See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the intended separation of
responsibilities. The local catalog, deterministic movie tools, bounded
harness, guardrails, local retrieval pipeline, and deterministic retrieval
evaluation are implemented.

## Production deployment preparation (Phase 8)

Production configuration and release guidance are in
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). The backend requires an explicit
production environment, exact HTTPS frontend origins, secret-manager-managed
credentials, and a private MySQL connection. Automatic schema initialization
is disabled in production; database setup is an explicit operator action.
`GET /api/health` is the liveness endpoint and `GET /api/ready` checks the
read-only MySQL/schema readiness state. Deployment has not been performed.
