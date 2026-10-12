# CineMatch AI Architecture

## Implemented foundation (Phases 1–5)

FastAPI exposes health/readiness/system endpoints and a movie catalog backed
by MySQL. The React dashboard checks the real API and searches real catalog
records. `backend/data/movies.json` is the source-controlled seed; local
development startup creates the schema and inserts missing IDs without
deleting or overwriting existing movie rows. Production startup disables this
operation and performs a read-only database check. The MySQL connection is
configured with `MYSQL_HOST`, `MYSQL_PORT`,
`MYSQL_USER`, `MYSQL_PASSWORD`, and `MYSQL_DATABASE`; the JSON path is configured
with `MOVIES_CATALOG_PATH`. The Workbench setup script creates `cinematch_db`
and the separate `cinematch_test_db`.
The test fixture only permits a schema named with the `cinematch_test_` prefix,
checks that it differs from the configured production schema, and clears data
only inside that test schema. Tests must be run with both schemas configured;
they never point at or truncate `cinematch_db`.

RAG data is separate from MySQL. The existing movie JSON and optional
`backend/data/rag_documents.json` file are its input sources; a generated,
Git-ignored local index stores embedding vectors. Indexing and retrieval do
not create or modify MySQL tables.

The 13-record seed is manually curated from linked English Wikipedia film
articles (11 Tamil records; Malayalam and Telugu represented once each).
Article links provide provenance, but the seed is intentionally small and is
not an official or comprehensive movie database. Ratings are omitted (`null`)
for every record because no stable, consistent source was selected; runtime is
also unknown for most records. Missing values stay null rather than being
estimated. The one populated runtime (Baashha, 144 minutes) comes from the
linked article infobox. See the README for the data limitations and API use.

## Movie catalog and deterministic tools

`app/database` owns MySQL connections, schema setup, and safe seed loading.
Genres use a normalized many-to-many relation in InnoDB tables with `utf8mb4`
text. The database uses stable
`movie_id` keys and indexes title, language, release year, and genre lookups.
Initialization is idempotent and additive: rerunning it does not duplicate
records or remove local records.

`app/tools/movie_tools.py` implements deterministic `search_movies`,
`filter_movies`, and `get_movie_details` functions. They validate parameters,
build only parameterized MySQL predicates, enforce result caps, and preserve
unknown metadata as null. The FastAPI movie routes expose search, strict
filtering, exact-ID details (404 for unknown IDs), and database-derived stats.
No arbitrary SQL, external service calls, LLM, or pretend execution records are
involved.

The current API routes call the movie functions directly; Phase 3 also exposes
them to the harness through a separate explicit registry and validated tool
boundary.

## Agent harness and tool calling (Phase 3)

`POST /api/agent/run` enters `app/agent/orchestrator.py`. The orchestration
loop requests a structured decision from the provider, validates its shape,
then checks tool registration and policy before validating arguments and
calling a tool. Results/errors become observations for the next provider
decision. A final provider response, policy denial, error threshold, timeout,
invalid decision, or iteration cap terminates the run.

Responsibilities are separated into:

- `provider.py`: asynchronous provider protocol, deterministic `MockProvider`,
  and opt-in `OpenAIChatProvider` implemented with the existing `httpx`
  dependency. OpenAI requests use server-side credentials, HTTPS, bounded
  timeout/retries, the fixed JSON-schema tools, sanitized failures, and
  structured-decision validation. The mock remains the default and is used
  by automated tests. Recommendation phrasing with recognized catalog
  criteria uses existing filters to return matches, not personalized or
  ranked recommendations.
- `tool_registry.py`: a fixed allowlist with each tool name, description,
  argument schema, execution function, and permitted flag. There is no dynamic
  import, raw SQL, shell, filesystem mutation, or arbitrary-function route.
- `retrieve_movie_context`: the fourth registered, read-only tool. Its
  arguments are validated before it reaches the local retriever; it has the
  same authorization and execution policies as catalog tools.
- `policy.py`: rejects unregistered/unpermitted calls and repeated identical
  call signatures. The model's request alone never grants permission.
- `orchestrator.py`: enforces a maximum of five iterations, three consecutive
  tool errors, configurable request timeout (30 seconds by default to allow
  the first local model load), 8 KiB tool arguments, and
  structured terminal statuses. Database tools run off the event loop and
  reuse the Phase 2 tool functions.
- `trace.py`: creates sequence-numbered UTC events and stores the latest 100
  run traces in process memory. Events contain actual validated decisions,
  authorization outcomes, and factual result summaries; the original user
  message and final response text are not copied into traces, and common
  credential-shaped argument strings are redacted. `GET
  /api/agent/runs/{run_id}/trace` retrieves the trace; it is process-local and
  is not durable audit storage.

`GET /api/health` is a liveness check. `GET /api/ready` performs a bounded,
read-only MySQL/schema check and returns only a safe readiness state.

The browser dashboard submits a movie question, displays the returned run
status/answer/counts and active provider mode, and retrieves the actual event
timeline. `GET /api/agent/provider` exposes only mode, model label, and
credential availability, never the credential itself.

## Guardrails (Phase 4)

The default provider remains `MockProvider`; OpenAI can be enabled explicitly
with server-side environment configuration.
Guardrails are explicit checks at trust boundaries, implemented in
`app/agent/guardrails.py` and orchestrated by
`app/agent/orchestrator.py`:

- **Request parsing/input:** Pydantic validates message type, non-blank content,
  2,000-character maximum, and run configuration. FastAPI returns a uniform
  HTTP 422 body without echoing submitted values. A multi-signal contextual
  heuristic looks for instruction override plus protected-action or secret
  disclosure intent. It can block clear suspicious input before provider
  execution; ordinary movie questions are allowed.
- **Tool proposals:** only the four pre-registered tools may be selected.
  The existing policy authorizes registration, permitted status, and duplicate
  call signatures. JSON argument size and each registered Pydantic schema are
  checked before dispatch. Rejected proposals receive a denied guardrail trace
  event with a stable reason code and `execution_blocked=true`.
- **Tool observations:** results are structured as `ToolObservation` and
  marked `untrusted_catalog_data` or `untrusted_retrieved_content`. Catalog
  strings and passages are content, not instructions; they cannot change
  registry membership or authorization. The current mock is rule-based and
  has no model prompt.
- **Final output:** responses must be non-empty and within the per-request
  response cap (maximum 4,000 characters). Checks reject detected credential
  patterns, traceback-shaped content, and runtime/rating assertions about a
  mentioned movie when that value is absent in the observed catalog record.
  Rejection ends with `output_denied` and a fixed safe message; internal
  exceptions are represented by safe diagnostics, not returned to the client.

Traces record each guardrail stage, allow/deny result, reason code, blocked
execution flag, authorization decision, and final status in sequence. They do
not include the entire user message or final response. Prompt-injection
detection is a heuristic layer and cannot guarantee detection of every attack;
authorization and the fixed tool registry are the actual capability boundary.

## Retrieval-augmented generation (Phase 5)

The `app/rag` package keeps ingestion and vector search out of the MySQL movie
catalog. It loads records from `data/movies.json` and locally maintained
records from `data/rag_documents.json`. Movie documents use only existing
record fields and preserve source article URLs. Unknown runtime/rating values
remain null in metadata and are described as unavailable rather than guessed.
Supporting records require a stable document ID, source title, HTTPS URL or
`source:<identifier>`, text, optional movie ID, and bounded JSON metadata.
There is no website scraping or network access during tests.

The pipeline is:

1. Validate each source document and normalize whitespace.
2. Split text deterministically into configurable overlapping chunks. Chunk
   IDs derive from the stable document ID and chunk text.
3. Encode chunks through the `EmbeddingEncoder` interface. The default
   `SentenceTransformerEncoder` uses the local CPU model
   `sentence-transformers/all-MiniLM-L6-v2`; it does not fall back to
   synthetic vectors.
4. Persist model identity/revision, index format version, dimension, chunk
   metadata, and vectors to the ignored `data/rag_index.json`. Rebuild writes
   a temporary file and atomically replaces the prior index only after all
   vectors validate. Duplicate chunk IDs are removed and conflicting IDs
   rejected.
5. Encode the query and perform cosine-similarity retrieval with deterministic
   tie ordering, a minimum score, top-k cap of five, and optional exact
   movie/source filters. An empty index or a query with no passing scores
   returns an explicit empty result.

The registered retrieval-tool boundary enforces a minimum cosine similarity
of 0.30, or the higher configured `RAG_MINIMUM_SIMILARITY`; a provider cannot
lower that floor through tool arguments. This floor was checked against the
current local model and golden cases and should be re-evaluated if the model or
source corpus changes.

The Sentence Transformers Python package and model weights must be available
for real indexing/retrieval. The first model use may need a one-time download;
`python -m app.rag.ingest` from `backend` reports missing dependencies/model
cache and leaves an existing index unchanged. Model name/revision and chunk
settings are configured by `RAG_EMBEDDING_MODEL`, `RAG_EMBEDDING_REVISION`,
`RAG_CHUNK_SIZE`, and `RAG_CHUNK_OVERLAP`. A model identity or index format
mismatch requires rebuilding. Automated tests use a clearly test-only
deterministic encoder and temporary files; no fake embedding implementation
is available in the application default path.

The orchestrator screens each retrieved passage for sensitive values and
filesystem paths, records a `retrieved_content` guardrail event, removes
blocked content, and marks the remaining observation as
`untrusted_retrieved_content`. This check does not strip every instruction-like
sentence: retrieved text is never authorized as an instruction, and the
fixed registry/policy remains the capability boundary. Heuristic
prompt-injection detection is not exhaustive.

When asked for sources/evidence, `MockProvider` returns retrieved excerpts
verbatim with their indexed source title and reference. It is deterministic,
not a live LLM or a natural-language evidence synthesizer. The opt-in
OpenAI-compatible provider can select registered tools and produce
natural-language responses from returned observations. Tool observations are
explicitly marked untrusted and separated from system instructions. The
harness remains authoritative for tool registration, authorization, argument
validation, loop limits, and execution. For answers using retrieved evidence,
the adapter rejects missing or altered citations; this validates citation
membership, not semantic entailment of every claim. The prompt asks for
abstention when evidence is insufficient and for missing metadata to remain
unknown, but model answer quality is not guaranteed. Trace events include
bounded excerpts, source references, similarity scores, and movie IDs; they
omit vector values and internal document/chunk IDs. The browser shows those
real evidence records in the timeline. The default retriever is process-local
and reloads on API restart after an index rebuild.

No RAG content is written to `cinematch_db` or `cinematch_test_db`; test
indexes live under pytest temporary directories. MySQL test cleanup remains
restricted to the configured `cinematch_test_db` fixture checks.

## Planned component separation

- **Frontend:** React and TypeScript provide the project dashboard, live
  backend status, catalog search/detail view, and bounded agent interaction
  panel with the actual run timeline and retrieved source evidence. Planned
  expansions include a dedicated execution dashboard, tool inspector,
  guardrail controls, and evaluation lab. The frontend presents returned
  state rather than inventing results.
- **Backend API:** FastAPI owns request validation and response contracts.
  Health/system endpoints, movie search/filter/detail/statistics routes, and
  agent execution/trace routes are implemented; future route groups should
  remain thin and delegate domain work to backend modules.
- **Agent harness:** The bounded run lifecycle, provider decision protocol,
  explicit movie tool registry, policy checks, and trace retrieval are
  implemented. The provider is the deterministic mock by default or the
  configured OpenAI-compatible adapter; neither provider can directly execute
  tools.
- **Tools:** Deterministic movie search, filter, and exact-ID lookup use
  validated inputs, parameterized MySQL queries, bounded results, and
  structured outputs. The registered retrieval tool uses validated bounded
  inputs and the local vector index. The execution boundary uses an allowlist
  and policy checks, not simulated successes.
- **Guardrails:** Input risk checks, tool registry/policy/schema enforcement,
  and final-output checks run at defined points in each agent run. Safe reason
  codes and block outcomes are available in the trace. Heuristics are not a
  complete prompt-injection detector.
- **RAG:** `app/rag` separates source loading, chunking, embeddings, local
  vector-index persistence, and cosine retrieval. Retrieved passages preserve
  source metadata and enter the harness as untrusted tool observations.
- **Traces:** Agent runs emit ordered events for lifecycle transitions,
  provider decisions, tool authorization, execution, errors, guardrails, and
  actual retrieval evidence. The dashboard reads stored run traces; it does
  not fabricate traces or metrics.
- **Evaluations (Phase 6):** `app/evals` runs deterministic retrieval and
  safety checks from the versioned `data/rag_golden_set.json`. It records
  actual Recall@K, MRR, coverage, empty-result accuracy, source attribution,
  per-case evidence, safety checks, and failures in an ignored JSON report.
  It loads the real local index read-only and does not write to MySQL.
  These checks do not evaluate LLM answer quality. Tests and evaluations
  remain distinct: unit tests validate code, while evals measure actual
  retrieval against curated expectations.
  Provider adapter tests use mocked HTTP responses for parsing, authorization,
  timeouts, missing credentials, untrusted observations, and citation
  validation. They do not make a live model request or score answer quality.

  The Phase 10 test scenarios in
  `backend/tests/data/llm_answer_quality_cases.json` exercise catalog facts,
  filter-based recommendations, retrieved evidence and citation membership,
  empty-evidence abstention, prompt injection, unsupported catalog metadata,
  provider failures, malformed responses, and unauthorized tool proposals. They
  run against mocked provider HTTP responses through the real harness boundary;
  they verify deterministic safety/contract behavior, not semantic entailment
  or live model quality. A live smoke test is separate and requires both an
  available backend key and explicit user authorization.
  See [Phase 10 verification](PHASE10_REPORT.md) for the current regression
  results and live-provider blockers.

## Phase 7 provider configuration

Set `LLM_PROVIDER=openai` and configure `OPENAI_API_KEY` in the ignored
`backend/.env` to enable the OpenAI-compatible adapter. `OPENAI_MODEL`,
`OPENAI_BASE_URL`, `OPENAI_TIMEOUT_SECONDS`, and `OPENAI_MAX_RETRIES` are
configurable; the default mode is `mock`, and an unsupported mode fails
explicitly rather than falling back. Credentials never enter frontend code,
API responses, or traces. Missing credentials produce a safe terminal
provider error. Automated tests use an in-memory `httpx` transport and do not
require credentials, internet access, or paid calls.

The Phase 6 evaluation command continues to report deterministic retrieval
and safety metrics only. Any future LLM answer-quality evaluation must be
separate and evaluate claim support, citation entailment, abstention, and
prompt-injection resistance; a successful provider HTTP response alone is not
evidence of answer correctness.

## Intended request flow

The frontend submits a run request to the API. Request validation and input
guardrails run before provider invocation. The harness validates provider
decisions, applies registry/policy authorization, validates tool arguments,
and only then executes a registered movie or retrieval tool. Movie tools use
the existing parameterized MySQL functions; retrieval uses the versioned local
index. Retrieved observations are untrusted, screened evidence with source
attribution. Final output is checked before return. Guardrail outcomes and
retrieval excerpts are returned in the bounded in-memory trace. The selected
provider may be the mock or the opt-in OpenAI adapter; current evaluation
metrics measure retrieval and deterministic safety, not generated answer
quality.

Tests are isolated to `cinematch_test_db`; the fixture requires the exact
production/test schema names, verifies the selected schema before test cleanup,
and never truncates or deletes from `cinematch_db`.

## Production configuration and deployment

The backend validates production settings at startup, disables automatic
schema/catalog initialization in production, enforces TLS certificate and
identity verification for MySQL, limits request-body size and per-process
agent-run rates, and logs request metadata without bodies, query strings,
secrets, or raw provider/database errors. CORS uses exact configured origins,
requires HTTPS in production, and does not allow credentialed browser
requests. Readiness and liveness are separate. In-process rate limits are not
shared across workers; deployment must also configure host-level rate limits.

The app is prepared for a static frontend host plus a private FastAPI service,
connected to MySQL over a private network. HTTPS termination, secret-manager
configuration, persistent RAG index/model storage, database provisioning, and
host-specific health checks remain operator responsibilities. See
[DEPLOYMENT.md](DEPLOYMENT.md); this repository does not provision or deploy
infrastructure.
