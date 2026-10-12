"""Bounded, process-local storage for truthful completed-run traces."""

from collections import OrderedDict, Counter
from datetime import datetime, timezone
from threading import Lock
from uuid import UUID

from app.agent.schemas import AgentTraceResponse, TraceEvent, TraceSummary


class RunTrace:
    def __init__(self, run_id: UUID):
        self.run_id = run_id
        self.events: list[TraceEvent] = []

    def add(self, event_type: str, iteration: int, **fields: object) -> TraceEvent:
        event = TraceEvent(
            run_id=self.run_id,
            sequence=len(self.events) + 1,
            timestamp=datetime.now(timezone.utc),
            event_type=event_type,
            iteration=iteration,
            **fields,
        )
        self.events.append(event)
        return event

    def summary(self) -> TraceSummary:
        counts = Counter(event.event_type for event in self.events)
        return TraceSummary(event_count=len(self.events), event_types=dict(counts))


class TraceStore:
    """Keeps the most recent 100 run traces in this backend process."""

    def __init__(self, max_runs: int = 100):
        self._max_runs = max_runs
        self._runs: OrderedDict[UUID, AgentTraceResponse] = OrderedDict()
        self._lock = Lock()

    def save(
        self,
        run_trace: RunTrace,
        status: str,
        iteration_count: int,
        tool_call_count: int,
    ) -> AgentTraceResponse:
        response = AgentTraceResponse(
            run_id=run_trace.run_id,
            status=status,
            iteration_count=iteration_count,
            tool_call_count=tool_call_count,
            events=run_trace.events,
        )
        with self._lock:
            self._runs[run_trace.run_id] = response
            self._runs.move_to_end(run_trace.run_id)
            while len(self._runs) > self._max_runs:
                self._runs.popitem(last=False)
        return response

    def get(self, run_id: UUID) -> AgentTraceResponse | None:
        with self._lock:
            return self._runs.get(run_id)
