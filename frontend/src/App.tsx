import { useCallback, useEffect, useState, type FormEvent } from "react";

import {
  getHealth,
  getAgentProviderStatus,
  getAgentTrace,
  getMovie,
  getMovies,
  runAgent,
  type AgentRunResponse,
  type AgentProviderStatus,
  type AgentTrace,
  type HealthResponse,
  type Movie,
  type MovieSearchResponse,
} from "./services/api";
import "./App.css";

const capabilities = [
  {
    number: "01",
    title: "Agent Harness",
    description:
      "Orchestration, context management, and loop engineering for reliable agent runs.",
    icon: "↻",
    status: "Phase 3 harness active",
  },
  {
    number: "02",
    title: "Guardrails",
    description:
      "Input, tool-authorization, and output checks protect each agent run.",
    icon: "◇",
    status: "Phase 4 guardrails active",
  },
  {
    number: "03",
    title: "Tool Calls",
    description:
      "Deterministic movie search, filtering, and exact-ID lookup are available.",
    icon: "⌘",
    status: "Phase 2 tools available",
  },
  {
    number: "04",
    title: "RAG",
    description:
      "Local vector retrieval returns bounded, source-attributed evidence.",
    icon: "⌕",
    status: "Phase 5 · local index support",
  },
  {
    number: "05",
    title: "Evals & Golden Set",
    description:
      "Deterministic retrieval metrics and safety checks against a versioned golden set.",
    icon: "◎",
    status: "Phase 6 · evaluation command available",
  },
];

function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [movieQuery, setMovieQuery] = useState("");
  const [language, setLanguage] = useState("");
  const [genre, setGenre] = useState("");
  const [movieResults, setMovieResults] = useState<MovieSearchResponse | null>(
    null,
  );
  const [moviesLoading, setMoviesLoading] = useState(true);
  const [moviesError, setMoviesError] = useState<string | null>(null);
  const [selectedMovie, setSelectedMovie] = useState<Movie | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [agentMessage, setAgentMessage] = useState("");
  const [agentLoading, setAgentLoading] = useState(false);
  const [agentError, setAgentError] = useState<string | null>(null);
  const [agentRun, setAgentRun] = useState<AgentRunResponse | null>(null);
  const [agentTrace, setAgentTrace] = useState<AgentTrace | null>(null);
  const [traceError, setTraceError] = useState<string | null>(null);
  const [providerStatus, setProviderStatus] =
    useState<AgentProviderStatus | null>(null);
  const [providerStatusError, setProviderStatusError] = useState<string | null>(
    null,
  );

  const checkBackend = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      setHealth(await getHealth());
    } catch (checkError) {
      setHealth(null);
      setError(
        checkError instanceof Error
          ? checkError.message
          : "The backend health check failed unexpectedly.",
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void checkBackend();
  }, [checkBackend]);

  useEffect(() => {
    void getAgentProviderStatus()
      .then(setProviderStatus)
      .catch((statusError: unknown) => {
        setProviderStatus(null);
        setProviderStatusError(
          statusError instanceof Error
            ? statusError.message
            : "Unable to load the configured provider mode.",
        );
      });
  }, []);

  const runMovieSearch = useCallback(
    async (searchQuery: string, searchLanguage: string, searchGenre: string) => {
      setMoviesLoading(true);
      setMoviesError(null);
      setSelectedMovie(null);
      setDetailError(null);
      try {
        setMovieResults(
          await getMovies({
            query: searchQuery,
            language: searchLanguage,
            genre: searchGenre,
          }),
        );
      } catch (searchError) {
        setMovieResults(null);
        setMoviesError(
          searchError instanceof Error
            ? searchError.message
            : "The movie search failed unexpectedly.",
        );
      } finally {
        setMoviesLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    void runMovieSearch("", "", "");
  }, [runMovieSearch]);

  const searchCatalog = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void runMovieSearch(movieQuery, language, genre);
  };

  const selectMovie = async (movieId: string) => {
    setSelectedMovie(null);
    setDetailError(null);
    setDetailLoading(true);
    try {
      setSelectedMovie(await getMovie(movieId));
    } catch (fetchError) {
      setDetailError(
        fetchError instanceof Error
          ? fetchError.message
          : "Unable to load movie details.",
      );
    } finally {
      setDetailLoading(false);
    }
  };

  const submitAgentRequest = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAgentLoading(true);
    setAgentError(null);
    setTraceError(null);
    setAgentRun(null);
    setAgentTrace(null);
    try {
      const run = await runAgent(agentMessage);
      setAgentRun(run);
      try {
        setAgentTrace(await getAgentTrace(run.run_id));
      } catch (fetchError) {
        setTraceError(
          fetchError instanceof Error
            ? fetchError.message
            : "The run completed, but its trace could not be loaded.",
        );
      }
    } catch (runError) {
      setAgentError(
        runError instanceof Error
          ? runError.message
          : "The agent request failed unexpectedly.",
      );
    } finally {
      setAgentLoading(false);
    }
  };

  const agentEvidence = agentTrace
    ? [
        ...new Map(
          agentTrace.events
            .flatMap((traceEvent) => traceEvent.evidence ?? [])
            .map((evidence) => [evidence.source_reference, evidence]),
        ).values(),
      ]
    : [];

  const connectionLabel = isLoading
    ? "Checking backend"
    : health
      ? "Backend connected"
      : "Backend unavailable";

  return (
    <main className="dashboard-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="CineMatch AI home">
          <span className="brand-mark" aria-hidden="true">
            C
          </span>
          <span>CineMatch</span>
          <span className="brand-ai">AI</span>
        </a>
        <div
          className={`connection-status ${isLoading ? "is-loading" : health ? "is-connected" : "is-error"}`}
          role="status"
          aria-live="polite"
        >
          <span className="status-dot" />
          <span>{connectionLabel}</span>
        </div>
      </header>

      <section className="hero">
        <div className="hero-copy">
          <div className="eyebrow">
            <span className="eyebrow-line" />
            THE AGENT ENGINEERING WORKSPACE
          </div>
          <h1>
            Build agents
            <br />
            <span>with intention.</span>
          </h1>
          <p className="hero-description">
            A focused platform for designing, inspecting, and evaluating
            reliable AI agent systems.
          </p>
          <div className="hero-caption">
            <span className="caption-dot" />
            Agent Harness Engineering Platform
          </div>
        </div>

        <aside className="connection-card" aria-label="Backend connection">
          <div className="connection-card-top">
            <span className="card-kicker">API CONNECTION</span>
            <span className="connection-icon" aria-hidden="true">
              ↗
            </span>
          </div>
          <div className="connection-card-state">
            <span
              className={`large-status-dot ${isLoading ? "is-loading" : health ? "is-connected" : "is-error"}`}
            />
            <span>{connectionLabel}</span>
          </div>
          {health ? (
            <p className="connection-detail">
              {health.service} <span>·</span> v{health.version}
            </p>
          ) : error ? (
            <p className="connection-error">{error}</p>
          ) : (
            <p className="connection-detail">Contacting local API…</p>
          )}
          {!isLoading && !health && (
            <button className="retry-button" onClick={() => void checkBackend()}>
              Retry connection <span aria-hidden="true">↻</span>
            </button>
          )}
        </aside>
      </section>

      <section className="capabilities-section" aria-labelledby="capabilities-title">
        <div className="section-heading">
          <div>
            <p className="section-kicker">THE BUILDING BLOCKS</p>
            <h2 id="capabilities-title">Platform capabilities</h2>
          </div>
          <span className="section-count">01 — 05</span>
        </div>

        <div className="capability-grid">
          {capabilities.map((capability) => (
            <article className="capability-card" key={capability.number}>
              <div className="capability-card-top">
                <span className="capability-icon" aria-hidden="true">
                  {capability.icon}
                </span>
                <span className="capability-number">{capability.number}</span>
              </div>
              <h3>{capability.title}</h3>
              <p>{capability.description}</p>
              <div className="card-footer">
                <span
                  className={`planned-dot ${capability.number === "03" ? "available-dot" : ""}`}
                />
                {capability.status}
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="catalog-section" aria-labelledby="catalog-title">
        <div className="section-heading">
          <div>
            <p className="section-kicker">LOCAL DATA · DETERMINISTIC TOOLS</p>
            <h2 id="catalog-title">Movie catalog</h2>
          </div>
          <span className="section-count">PHASE 02</span>
        </div>
        <form className="catalog-search" onSubmit={searchCatalog}>
          <label className="catalog-field catalog-query-field">
            <span>Title or overview</span>
            <input
              type="search"
              value={movieQuery}
              onChange={(event) => setMovieQuery(event.target.value)}
              placeholder="Search the catalog"
            />
          </label>
          <label className="catalog-field">
            <span>Language</span>
            <input
              type="text"
              value={language}
              onChange={(event) => setLanguage(event.target.value)}
              placeholder="e.g. Tamil"
              maxLength={50}
            />
          </label>
          <label className="catalog-field">
            <span>Genre</span>
            <input
              type="text"
              value={genre}
              onChange={(event) => setGenre(event.target.value)}
              placeholder="e.g. Drama"
              maxLength={80}
            />
          </label>
          <button
            className="catalog-search-button"
            type="submit"
            disabled={moviesLoading}
          >
            {moviesLoading ? "Searching…" : "Search movies"}
          </button>
        </form>

        {moviesLoading ? (
          <p className="catalog-state" role="status">Loading movie catalog…</p>
        ) : moviesError ? (
          <p className="catalog-state catalog-state-error" role="alert">
            {moviesError}
          </p>
        ) : movieResults && movieResults.items.length === 0 ? (
          <p className="catalog-state" role="status">
            No movies match these filters. Try a broader search.
          </p>
        ) : movieResults ? (
          <>
            <p className="catalog-result-count" role="status">
              Showing {movieResults.items.length} of {movieResults.count} matching
              movies
            </p>
            <div className="movie-grid">
              {movieResults.items.map((movie) => (
                <button
                  className={`movie-card ${selectedMovie?.movie_id === movie.movie_id ? "is-selected" : ""}`}
                  key={movie.movie_id}
                  onClick={() => void selectMovie(movie.movie_id)}
                  type="button"
                >
                  <span className="movie-card-meta">
                    {movie.language} <span>·</span> {movie.release_year}
                  </span>
                  <span className="movie-card-title">{movie.title}</span>
                  <span className="movie-card-genres">
                    {movie.genres.join(" · ")}
                  </span>
                  <span className="movie-card-overview">{movie.overview}</span>
                  <span className="movie-card-link">View verified record ↗</span>
                </button>
              ))}
            </div>
            {detailLoading && (
              <p className="catalog-state" role="status">Loading movie details…</p>
            )}
            {detailError && (
              <p className="catalog-state catalog-state-error" role="alert">
                {detailError}
              </p>
            )}
            {selectedMovie && (
              <article className="movie-detail" aria-live="polite">
                <div className="movie-detail-heading">
                  <div>
                    <p className="section-kicker">CATALOG RECORD</p>
                    <h3>{selectedMovie.title}</h3>
                  </div>
                  <span className="movie-id">{selectedMovie.movie_id}</span>
                </div>
                <p>{selectedMovie.overview}</p>
                <dl className="movie-facts">
                  <div><dt>Language</dt><dd>{selectedMovie.language}</dd></div>
                  <div><dt>Released</dt><dd>{selectedMovie.release_year}</dd></div>
                  <div>
                    <dt>Runtime</dt>
                    <dd>
                      {selectedMovie.runtime_minutes === null
                        ? "Not verified"
                        : `${selectedMovie.runtime_minutes} min`}
                    </dd>
                  </div>
                  <div>
                    <dt>Rating</dt>
                    <dd>
                      {selectedMovie.rating === null
                        ? "Not sourced"
                        : selectedMovie.rating}
                    </dd>
                  </div>
                  <div>
                    <dt>Genres</dt>
                    <dd>{selectedMovie.genres.join(", ")}</dd>
                  </div>
                </dl>
                <a
                  href={selectedMovie.source_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  Record source ↗
                </a>
              </article>
            )}
          </>
        ) : null}
      </section>

      <section className="agent-section" aria-labelledby="agent-title">
        <div className="section-heading">
          <div>
            <p className="section-kicker">BOUNDED · TOOL-AWARE · TRACEABLE</p>
            <h2 id="agent-title">CineMatch agent</h2>
          </div>
          <span className="section-count">
            {providerStatus
              ? `${providerStatus.mode.toUpperCase()} · ${providerStatus.model}`
              : "CHECKING PROVIDER"}
          </span>
        </div>
        <p className="agent-disclaimer">
          {providerStatus?.mode === "openai"
            ? "OpenAI model decisions are proposed through the existing bounded tool harness. Tool authorization remains local; retrieved evidence is untrusted."
            : providerStatus?.mode === "mock"
              ? "Offline deterministic provider for development. It routes movie questions to registered tools and returns cited evidence excerpts; it is not an LLM."
              : "Provider selection is loading. Tool execution remains restricted to the backend registry and authorization policy."}
        </p>
        {providerStatusError ? (
          <p className="catalog-state catalog-state-error" role="alert">
            {providerStatusError}
          </p>
        ) : providerStatus?.mode === "unavailable" ? (
          <p className="catalog-state catalog-state-error" role="alert">
            The configured provider mode is unsupported. Set LLM_PROVIDER to
            "mock" or "openai"; agent requests will fail safely until corrected.
          </p>
        ) : providerStatus && !providerStatus.available ? (
          <p className="catalog-state catalog-state-error" role="alert">
            The {providerStatus.mode} provider is selected but is not
            configured. Agent requests will fail safely until its credentials
            are configured.
          </p>
        ) : null}
        <form className="agent-form" onSubmit={submitAgentRequest}>
          <label className="agent-message-label" htmlFor="agent-message">
            Ask a movie-related question
          </label>
          <textarea
            id="agent-message"
            value={agentMessage}
            onChange={(event) => setAgentMessage(event.target.value)}
            placeholder="For example: Tell me about Baashha with sources, or find Tamil action movies."
            maxLength={2000}
            required
            rows={3}
          />
          <div className="agent-form-footer">
            <span>Guardrails · Untrusted evidence · Up to 5 iterations</span>
            <button
              className="catalog-search-button"
              type="submit"
              disabled={agentLoading || !agentMessage.trim()}
            >
              {agentLoading ? "Running…" : "Run agent"}
            </button>
          </div>
        </form>

        {agentLoading ? (
          <p className="catalog-state" role="status">
            Running the bounded agent loop and recording actual events…
          </p>
        ) : agentError ? (
          <p className="catalog-state catalog-state-error" role="alert">
            {agentError}
          </p>
        ) : agentRun ? (
          <div className="agent-result" aria-live="polite">
            <section className="agent-answer-panel" aria-labelledby="agent-answer-title">
              <p className="section-kicker">FINAL ANSWER</p>
              <h3 id="agent-answer-title">CineMatch response</h3>
              <p className="agent-answer">{agentRun.final_response}</p>
            </section>
            <section className="agent-evidence-section" aria-labelledby="agent-evidence-title">
              <h3 id="agent-evidence-title">Citations &amp; evidence</h3>
              {traceError ? (
                <p className="agent-evidence-state">
                  Evidence could not be loaded because the run trace is
                  unavailable.
                </p>
              ) : !agentTrace ? (
                <p className="agent-evidence-state" role="status">
                  Checking the run trace for retrieved evidence…
                </p>
              ) : agentEvidence.length === 0 ? (
                <p className="agent-evidence-state">
                  No retrieved source evidence was recorded for this run.
                </p>
              ) : (
                <div className="agent-evidence-list">
                  {agentEvidence.map((evidence) => (
                    <article
                      className="agent-evidence-card"
                      key={evidence.source_reference}
                    >
                      <strong>{evidence.source_title}</strong>
                      {evidence.movie_id && (
                        <span className="evidence-movie-id">
                          {evidence.movie_id}
                        </span>
                      )}
                      <p>{evidence.excerpt}</p>
                      {evidence.source_reference.startsWith("https://") ? (
                        <a
                          href={evidence.source_reference}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Source reference ↗
                        </a>
                      ) : (
                        <span className="evidence-reference">
                          {evidence.source_reference}
                        </span>
                      )}
                    </article>
                  ))}
                </div>
              )}
            </section>
            <div className="agent-result-header">
              <div className="agent-status">
                <span
                  className={`agent-status-dot ${agentRun.status === "completed" ? "is-connected" : "is-error"}`}
                />
                <span>Execution status: {agentRun.status.replace(/_/g, " ")}</span>
              </div>
              <div className="agent-run-metrics">
                <span>{agentRun.tool_call_count} tool requests</span>
                <span>{agentRun.iteration_count} iterations</span>
              </div>
              <span className="section-count">
                {agentRun.provider_mode.toUpperCase()} · {agentRun.provider_model}
              </span>
            </div>
            <div className="agent-trace-heading">
              <h3>Execution timeline</h3>
              <span>Run {agentRun.run_id}</span>
            </div>
            {traceError ? (
              <p className="catalog-state catalog-state-error" role="alert">
                {traceError}
              </p>
            ) : !agentTrace ? (
              <p className="catalog-state" role="status">
                Loading run trace…
              </p>
            ) : agentTrace.events.length === 0 ? (
              <p className="catalog-state" role="status">
                This run has no recorded events.
              </p>
            ) : (
              <ol className="agent-timeline">
                {agentTrace.events.map((traceEvent) => (
                  <li className="timeline-event" key={traceEvent.sequence}>
                    <span className="timeline-sequence">
                      {String(traceEvent.sequence).padStart(2, "0")}
                    </span>
                    <div className="timeline-content">
                      <div className="timeline-title">
                        <strong>{traceEvent.event_type.replace(/_/g, " ")}</strong>
                        <span>
                          Iteration {traceEvent.iteration} ·{" "}
                          {new Date(traceEvent.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                      {traceEvent.requested_tool && (
                        <p className="timeline-tool">
                          {traceEvent.requested_tool}
                          {traceEvent.authorized === null
                            ? ""
                            : traceEvent.authorized
                              ? " · authorized"
                              : " · denied"}
                        </p>
                      )}
                      {traceEvent.guardrail_stage && (
                        <p
                          className={`timeline-guardrail ${traceEvent.guardrail_result === "denied" ? "is-denied" : "is-allowed"}`}
                        >
                          Guardrail {traceEvent.guardrail_stage} ·{" "}
                          {traceEvent.guardrail_result ?? "checked"}
                          {traceEvent.reason_code
                            ? ` · ${traceEvent.reason_code}`
                            : ""}
                          {traceEvent.execution_blocked
                            ? " · execution blocked"
                            : ""}
                        </p>
                      )}
                      {traceEvent.denial_reason && (
                        <p className="timeline-error">{traceEvent.denial_reason}</p>
                      )}
                      {traceEvent.error && (
                        <p className="timeline-error">{traceEvent.error}</p>
                      )}
                      {traceEvent.result_summary && (
                        <p className="timeline-summary">
                          {traceEvent.result_summary}
                        </p>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </div>
        ) : (
          <p className="catalog-state agent-empty">
            Submit a question to see the provider decision, authorized tool
            calls, and final outcome.
          </p>
        )}
      </section>

      <section className="project-status" aria-labelledby="project-status-title">
        <div className="project-status-icon" aria-hidden="true">
          <span>✳</span>
        </div>
        <div className="project-status-copy">
          <p className="section-kicker">PROJECT STATUS</p>
          <h2 id="project-status-title">Phase 6 · Deterministic evaluations</h2>
          <p>
            Model-backed local retrieval, source evidence, and a versioned
            deterministic evaluation command are available. The mock provider
            returns evidence excerpts; it is not a generated LLM answer.
          </p>
        </div>
        <span className="phase-pill">
          <span className="phase-dot" />
          PHASE 06
        </span>
      </section>

      <footer className="page-footer">
        <span>CINEMATCH AI</span>
        <span>Built for clarity. Designed for reliable agents.</span>
      </footer>
    </main>
  );
}

export default App;
