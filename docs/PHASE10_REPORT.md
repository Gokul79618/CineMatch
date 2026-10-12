# Phase 10 — Live LLM Integration and Answer-Quality Validation

**Date:** 2026-10-12  
**Final status:** Offline Phase 10 work and regression verification are complete.
Live-provider verification is blocked. No live provider request or paid usage
was authorized or performed.

## Summary

| Area | Status | Evidence |
|---|---|---|
| Existing provider audit | PASS | The OpenAI-compatible Chat Completions adapter, provider protocol, strict decision schema, trace, and fixed tool allowlist were retained. |
| Provider configuration | PASS | Runtime selected `mock`; configured model label is `gpt-4o-mini`; backend OpenAI credential availability was false. The key value was not read out or printed. |
| Mock provider | PASS | The updated local backend completed a catalog run as `mock/deterministic`, calling `search_movies` and `get_movie_details`. |
| Mocked OpenAI provider boundary | PASS | 30 focused provider and answer-quality tests passed without external requests or credentials; final full suite also passed. |
| Guardrails and authorization | PASS | Tests verify prompt-injection rejection before provider invocation, unknown-tool denial, argument-schema validation, bounded iterations, citation membership, and output rejection for unsupported catalog rating claims. |
| Retrieval evaluation | PASS | Actual local index evaluation completed with zero failures; see retrieval metrics below. |
| Live OpenAI smoke test | BLOCKED | No backend key is configured and explicit live-request authorization was not provided. No live call was made. |
| Local-configured frontend build | PASS | TypeScript/Vite build completed in development mode with `VITE_API_BASE_URL=http://127.0.0.1:8001`. |
| Production frontend build | BLOCKED | No real production HTTPS API origin was provided. A placeholder URL was not used as deployment verification. |
| MySQL integrity | PASS | Read-only counts: 13 movies in `cinematch_db`; 3 in `cinematch_test_db`. Tests are guarded to clean only the test schema. |

## Provider audit and handling

The existing adapter uses `LLM_PROVIDER` (default `mock`), backend-only
`OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_BASE_URL`,
`OPENAI_TIMEOUT_SECONDS`, and `OPENAI_MAX_RETRIES`. The API provider-status
route exposes mode/model/availability, not credentials. OpenAI requests use
the existing HTTPS HTTPX client and fixed function schemas. Provider outputs
are validated as either a final answer or one proposed tool call; the harness
then enforces its own registered-tool, policy, schema, and iteration limits.

Mocked HTTP tests verified:

- A valid structured tool proposal is parsed.
- Timeouts and retryable 429/5xx responses are bounded; authentication 401/403
  responses are not retried.
- Exhausted HTTP errors, missing credentials, malformed JSON, absent choices,
  empty content, invalid decisions, and invalid tool arguments fail safely.
- Provider response details and a test credential do not appear in client
  errors, traces, or captured logs.
- Exact retrieved citation membership is enforced; absent, altered, and
  fabricated citations are rejected.
- Unknown tools are denied without execution. The mock provider remains the
  default and does not silently substitute for an OpenAI failure.

No adapter implementation change was needed. The changes add regression
coverage around its existing behavior.

## Deterministic answer-quality scenarios

`backend/tests/data/llm_answer_quality_cases.json` is a versioned set of ten
scenarios covering:

1. Catalog title/details.
2. Recommendations using catalog filters (not a ranked recommendation
   algorithm).
3. Answers grounded in retrieved evidence.
4. Exact source attribution.
5. An out-of-corpus query and abstention.
6. Prompt injection blocked before provider invocation.
7. Unsupported catalog rating claims rejected by the output guardrail.
8. Provider failure.
9. Malformed provider response.
10. Unauthorized tool and invalid arguments.

The targeted provider and answer-quality tests passed **30/30**. These tests
use deterministic HTTP responses and test-schema records. Their assertions
verify harness contracts, expected facts, citations, and safe outcomes; they
are **not** a live model answer-quality score or proof of semantic entailment
for arbitrary generated claims.

## Retrieval evaluation

The existing real-index evaluation command completed with exit code 0:

```text
Dataset cinematch-rag-golden-v1
model sentence-transformers/all-MiniLM-L6-v2@1110a243fdf4706b3f48f1d95db1a4f5529b4d41
index v1
Recall@K=1.000
MRR=1.000
coverage=1.000
empty-result accuracy=1.000
source attribution=1.000
0 failures
```

These retrieval results come from the existing small golden set and local
index. They measure retrieval and deterministic safety checks only—not
generated-answer quality. The report is written to the ignored
`backend/data/rag_eval_report.json`.

## Regression results

- Focused: `pytest tests/test_llm_provider.py tests/test_llm_answer_quality.py
  -q` — **30 passed**.
- Full backend, rerun for final closeout: `.\.venv\Scripts\python.exe -m
  pytest tests -q` — **150 passed**, one existing Starlette `BlockingPortal`
  deprecation warning; exit code 0.
- Retrieval evaluation: `python -m app.evals.run_eval` — **PASS**, zero
  failures; all reported retrieval metrics were 1.000 on the existing golden
  dataset.
- Frontend local configuration: `npm run build -- --mode development` with
  `VITE_API_BASE_URL=http://127.0.0.1:8001` — **PASS**, TypeScript and Vite
  production-bundling steps completed successfully for the development-mode
  configuration.
- Production frontend build with the deployment API origin — **BLOCKED**;
  no real HTTPS API origin was supplied.
- Local API with database auto-initialization disabled and mock provider
  selected: readiness returned `ready`; provider status returned
  `mock/deterministic`; movie stats reported 13; a Baashha query completed
  with two registered, authorized catalog-tool executions and a retrievable
  trace.
- Database verification used read-only queries; production row count was 13.
  Tests ran against `cinematch_test_db`, not `cinematch_db`.

The test API fixture now assigns a unique synthetic client identity per test.
This isolates the pre-existing per-process rate limiter between tests without
changing or weakening its configured runtime limit.

## Files created or changed

- `backend/tests/data/llm_answer_quality_cases.json` — versioned representative
  scenario data.
- `backend/tests/test_llm_answer_quality.py` — mocked provider-to-harness
  grounded-answer and safety checks.
- `backend/tests/test_llm_provider.py` — retry, authentication, terminal HTTP,
  malformed/empty-response regressions.
- `backend/tests/conftest.py` — isolates rate-limit client identity per API
  test; production rate-limit behavior is unchanged.
- `README.md` and `docs/ARCHITECTURE.md` — test command, scenario scope, and
  limitations.
- `docs/PHASE10_REPORT.md` — this verification record.

No provider code, database schema/data, RAG index, or credentials were
modified.

## Phase 10 closeout and Phase 11 handoff

Phase 10 is complete for offline implementation and verification. Final checks
confirmed `LLM_PROVIDER=mock`, model label `gpt-4o-mini`, and no configured
OpenAI credential. **No live API call was made.** Live LLM verification remains
**BLOCKED** pending both backend-only credential configuration and explicit
user authorization for the live requests.

Production frontend verification and deployment remain **BLOCKED** until the
actual HTTPS API origin and hosting configuration are supplied. No deployment
was performed.

### Exact Phase 11 steps

1. **Confirm scope and authorization.** Agree on Phase 11 deliverables and
   deployment target. If live-provider verification is wanted, explicitly
   authorize the two bounded smoke requests before they are sent. Until then,
   keep `LLM_PROVIDER=mock`; do not make provider requests.
2. **Configure credentials privately.** In `backend\.env` (ignored by Git),
   set `LLM_PROVIDER=openai`, `OPENAI_API_KEY` to the user's own key,
   `OPENAI_MODEL=gpt-4o-mini` (or the user-approved model), and retain the
   intended `OPENAI_BASE_URL`, timeout, and retry bounds. Never place the key
   in frontend variables, source, command-line arguments, logs, or report.
3. **Start and verify the backend without exposing secrets.** In a PowerShell
   window:

```powershell
Set-Location 'C:\Users\kgoku\Desktop\CineMatch\backend'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

   In a second PowerShell window, verify health and provider mode. Do not print
   or retrieve the key:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/api/health'
Invoke-RestMethod 'http://127.0.0.1:8000/api/agent/provider'
```

4. **After explicit authorization only**, send one catalog question and one
   question from the existing RAG golden set. Use the bounded existing agent
   endpoint and schema; do not raise its configured execution limits:

```powershell
$body = @{ message = 'Find Baashha in the catalog and tell me its title and release year.'; config = @{ max_iterations = 5; timeout_seconds = 30 } } | ConvertTo-Json -Depth 5
Invoke-RestMethod 'http://127.0.0.1:8000/api/agent/run' -Method Post -ContentType 'application/json' -Body $body

$body = @{ message = 'Summarize Baashha using retrieved evidence and show the sources.'; config = @{ max_iterations = 5; timeout_seconds = 30 } } | ConvertTo-Json -Depth 5
Invoke-RestMethod 'http://127.0.0.1:8000/api/agent/run' -Method Post -ContentType 'application/json' -Body $body
```

   Record only sanitized provider/model mode, status, latency, registered
   tool calls, citations, and errors. Stop immediately for unexpected cost,
   errors, unauthorized tool proposals, unsafe output, or citation problems.
   Do not claim answer quality based only on HTTP success.
5. **Run offline regressions and retrieval evaluation** from the backend
   directory; these commands do not call the live provider:

```powershell
Set-Location 'C:\Users\kgoku\Desktop\CineMatch\backend'
$env:PYTHONPATH = '.'
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m app.evals.run_eval
```

6. **Verify deployment inputs before building or deploying.** Obtain the real
   HTTPS backend origin and hosting settings. Set
   `VITE_API_BASE_URL` to that origin and run `npm run build`; verify deployed
   CORS, HTTPS, health/readiness, safe logs, and private MySQL connectivity.
   Deployment remains a separate, explicitly authorized operation.
7. **Restore mock mode when live testing is finished** by setting
   `LLM_PROVIDER=mock` in the backend environment and restarting the backend.
