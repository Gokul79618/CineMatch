export interface HealthResponse {
  status: string;
  service: string;
  version: string;
}

export interface Movie {
  movie_id: string;
  title: string;
  language: string;
  genres: string[];
  release_year: number;
  runtime_minutes: number | null;
  overview: string;
  rating: number | null;
  source_url: string;
}

export interface MovieSearchResponse {
  count: number;
  limit: number;
  items: Movie[];
}

export interface MovieSearchParams {
  query?: string;
  language?: string;
  genre?: string;
  release_year?: number;
  limit?: number;
}

export interface AgentRunResponse {
  run_id: string;
  final_response: string;
  status: string;
  provider_mode: string;
  provider_model: string;
  iteration_count: number;
  tool_call_count: number;
  trace_summary: {
    event_count: number;
    event_types: Record<string, number>;
  };
}

export interface AgentProviderStatus {
  mode: string;
  model: string;
  available: boolean;
}

export interface AgentTraceEvent {
  run_id: string;
  sequence: number;
  timestamp: string;
  event_type: string;
  iteration: number;
  decision: Record<string, unknown> | null;
  requested_tool: string | null;
  arguments: Record<string, unknown> | null;
  authorized: boolean | null;
  denial_reason: string | null;
  result_summary: string | null;
  error: string | null;
  execution_status?: string | null;
  guardrail_stage: string | null;
  guardrail_result: "allowed" | "denied" | null;
  reason_code: string | null;
  execution_blocked: boolean | null;
  evidence: AgentTraceEvidence[] | null;
}

export interface AgentTraceEvidence {
  source_title: string;
  source_reference: string;
  movie_id: string | null;
  excerpt: string;
  similarity: number;
}

export interface AgentTrace {
  run_id: string;
  status: string;
  iteration_count: number;
  tool_call_count: number;
  events: AgentTraceEvent[];
}

const apiBaseUrl = (
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"
).replace(/\/+$/, "");

function isHealthResponse(value: unknown): value is HealthResponse {
  return (
    typeof value === "object" &&
    value !== null &&
    "status" in value &&
    typeof value.status === "string" &&
    "service" in value &&
    typeof value.service === "string" &&
    "version" in value &&
    typeof value.version === "string"
  );
}

function isMovie(value: unknown): value is Movie {
  return (
    typeof value === "object" &&
    value !== null &&
    "movie_id" in value &&
    typeof value.movie_id === "string" &&
    "title" in value &&
    typeof value.title === "string" &&
    "language" in value &&
    typeof value.language === "string" &&
    "genres" in value &&
    Array.isArray(value.genres) &&
    value.genres.every((genre: unknown) => typeof genre === "string") &&
    "release_year" in value &&
    typeof value.release_year === "number" &&
    "runtime_minutes" in value &&
    (typeof value.runtime_minutes === "number" || value.runtime_minutes === null) &&
    "overview" in value &&
    typeof value.overview === "string" &&
    "rating" in value &&
    (typeof value.rating === "number" || value.rating === null) &&
    "source_url" in value &&
    typeof value.source_url === "string"
  );
}

function isMovieSearchResponse(value: unknown): value is MovieSearchResponse {
  return (
    typeof value === "object" &&
    value !== null &&
    "count" in value &&
    typeof value.count === "number" &&
    "limit" in value &&
    typeof value.limit === "number" &&
    "items" in value &&
    Array.isArray(value.items) &&
    value.items.every(isMovie)
  );
}

function isAgentRunResponse(value: unknown): value is AgentRunResponse {
  return (
    typeof value === "object" &&
    value !== null &&
    "run_id" in value &&
    typeof value.run_id === "string" &&
    "final_response" in value &&
    typeof value.final_response === "string" &&
    "status" in value &&
    typeof value.status === "string" &&
    "provider_mode" in value &&
    typeof value.provider_mode === "string" &&
    "provider_model" in value &&
    typeof value.provider_model === "string" &&
    "iteration_count" in value &&
    typeof value.iteration_count === "number" &&
    "tool_call_count" in value &&
    typeof value.tool_call_count === "number" &&
    "trace_summary" in value &&
    typeof value.trace_summary === "object" &&
    value.trace_summary !== null &&
    "event_count" in value.trace_summary &&
    typeof value.trace_summary.event_count === "number" &&
    "event_types" in value.trace_summary &&
    typeof value.trace_summary.event_types === "object" &&
    value.trace_summary.event_types !== null
  );
}

function isAgentProviderStatus(value: unknown): value is AgentProviderStatus {
  return (
    typeof value === "object" &&
    value !== null &&
    "mode" in value &&
    typeof value.mode === "string" &&
    "model" in value &&
    typeof value.model === "string" &&
    "available" in value &&
    typeof value.available === "boolean"
  );
}

function isAgentTraceEvent(value: unknown): value is AgentTraceEvent {
  return (
    typeof value === "object" &&
    value !== null &&
    "run_id" in value &&
    typeof value.run_id === "string" &&
    "sequence" in value &&
    typeof value.sequence === "number" &&
    "timestamp" in value &&
    typeof value.timestamp === "string" &&
    "event_type" in value &&
    typeof value.event_type === "string" &&
    "iteration" in value &&
    typeof value.iteration === "number" &&
    "requested_tool" in value &&
    (typeof value.requested_tool === "string" || value.requested_tool === null) &&
    "authorized" in value &&
    (typeof value.authorized === "boolean" || value.authorized === null) &&
    "denial_reason" in value &&
    (typeof value.denial_reason === "string" || value.denial_reason === null) &&
    "result_summary" in value &&
    (typeof value.result_summary === "string" || value.result_summary === null) &&
    "error" in value &&
    (typeof value.error === "string" || value.error === null) &&
    "decision" in value &&
    (typeof value.decision === "object" || value.decision === null) &&
    "arguments" in value &&
    (typeof value.arguments === "object" || value.arguments === null) &&
    "guardrail_stage" in value &&
    (typeof value.guardrail_stage === "string" || value.guardrail_stage === null) &&
    "guardrail_result" in value &&
    (value.guardrail_result === "allowed" ||
      value.guardrail_result === "denied" ||
      value.guardrail_result === null) &&
    "reason_code" in value &&
    (typeof value.reason_code === "string" || value.reason_code === null) &&
    "execution_blocked" in value &&
    (typeof value.execution_blocked === "boolean" ||
      value.execution_blocked === null) &&
    "evidence" in value &&
    (value.evidence === null ||
      (Array.isArray(value.evidence) && value.evidence.every(isAgentTraceEvidence)))
  );
}

function isAgentTraceEvidence(value: unknown): value is AgentTraceEvidence {
  return (
    typeof value === "object" &&
    value !== null &&
    "source_title" in value &&
    typeof value.source_title === "string" &&
    "source_reference" in value &&
    typeof value.source_reference === "string" &&
    "movie_id" in value &&
    (typeof value.movie_id === "string" || value.movie_id === null) &&
    "excerpt" in value &&
    typeof value.excerpt === "string" &&
    "similarity" in value &&
    typeof value.similarity === "number"
  );
}

function isAgentTrace(value: unknown): value is AgentTrace {
  return (
    typeof value === "object" &&
    value !== null &&
    "run_id" in value &&
    typeof value.run_id === "string" &&
    "status" in value &&
    typeof value.status === "string" &&
    "iteration_count" in value &&
    typeof value.iteration_count === "number" &&
    "tool_call_count" in value &&
    typeof value.tool_call_count === "number" &&
    "events" in value &&
    Array.isArray(value.events) &&
    value.events.every(isAgentTraceEvent)
  );
}

async function getJson<T>(
  path: string,
  init?: RequestInit,
  timeoutMs = 15_000,
): Promise<T> {
  let response: Response;
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    try {
      response = await fetch(`${apiBaseUrl}${path}`, {
        ...init,
        signal: controller.signal,
      });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        throw new Error("The backend request timed out. Please try again.");
      }
      throw new Error(
        `Unable to reach the backend at ${apiBaseUrl}. Confirm that the API is running and try again.`,
      );
    }

    if (!response.ok) {
      let message = `The backend returned HTTP ${response.status}.`;
      try {
        const body: unknown = await response.json();
        if (
          typeof body === "object" &&
          body !== null &&
          "detail" in body &&
          typeof body.detail === "string"
        ) {
          message = body.detail;
        } else if (
          typeof body === "object" &&
          body !== null &&
          "detail" in body &&
          typeof body.detail === "object" &&
          body.detail !== null &&
          "message" in body.detail &&
          typeof body.detail.message === "string"
        ) {
          message = body.detail.message;
        }
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          throw new Error("The backend request timed out. Please try again.");
        }
        // Keep the HTTP status message when the error response has no JSON body.
      }
      throw new Error(message);
    }

    try {
      return (await response.json()) as T;
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        throw new Error("The backend request timed out. Please try again.");
      }
      throw new Error("The backend returned an invalid JSON response.");
    }
  } finally {
    window.clearTimeout(timeoutId);
  }
}

export async function getHealth(): Promise<HealthResponse> {
  const health: unknown = await getJson<unknown>("/api/health");
  if (!isHealthResponse(health)) {
    throw new Error("The backend returned an invalid health response.");
  }

  return health;
}

export async function getMovies(
  params: MovieSearchParams = {},
): Promise<MovieSearchResponse> {
  const query = new URLSearchParams();
  for (const key of ["query", "language", "genre"] as const) {
    const value = params[key]?.trim();
    if (value) query.set(key, value);
  }
  if (params.release_year !== undefined) {
    query.set("release_year", String(params.release_year));
  }
  if (params.limit !== undefined) query.set("limit", String(params.limit));

  const suffix = query.size ? `?${query.toString()}` : "";
  const result: unknown = await getJson<unknown>(`/api/movies${suffix}`);
  if (!isMovieSearchResponse(result)) {
    throw new Error("The backend returned an invalid movie search response.");
  }
  return result;
}

export async function getMovie(movieId: string): Promise<Movie> {
  const movie: unknown = await getJson<unknown>(
    `/api/movies/${encodeURIComponent(movieId)}`,
  );
  if (!isMovie(movie)) {
    throw new Error("The backend returned an invalid movie detail response.");
  }
  return movie;
}

export async function runAgent(message: string): Promise<AgentRunResponse> {
  const result: unknown = await getJson<unknown>("/api/agent/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  }, 35_000);
  if (!isAgentRunResponse(result)) {
    throw new Error("The backend returned an invalid agent run response.");
  }
  return result;
}

export async function getAgentProviderStatus(): Promise<AgentProviderStatus> {
  const result: unknown = await getJson<unknown>("/api/agent/provider");
  if (!isAgentProviderStatus(result)) {
    throw new Error("The backend returned an invalid provider status.");
  }
  return result;
}

export async function getAgentTrace(runId: string): Promise<AgentTrace> {
  const trace: unknown = await getJson<unknown>(
    `/api/agent/runs/${encodeURIComponent(runId)}/trace`,
  );
  if (!isAgentTrace(trace)) {
    throw new Error("The backend returned an invalid agent trace.");
  }
  return trace;
}
