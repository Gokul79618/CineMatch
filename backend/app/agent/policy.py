"""Bounded execution policy for agent decisions and registered tools."""

from dataclasses import dataclass

from app.agent.schemas import AgentRunConfig
from app.agent.tool_registry import RegisteredTool


@dataclass(frozen=True)
class Authorization:
    allowed: bool
    reason: str | None = None


class HarnessPolicy:
    def __init__(self, config: AgentRunConfig):
        self.config = config
        self._seen_tool_calls: set[str] = set()

    def authorize(self, tool: RegisteredTool | None, signature: str) -> Authorization:
        if tool is None:
            return Authorization(False, "Tool is not registered.")
        if not tool.permitted:
            return Authorization(False, "Tool is registered but not permitted.")
        if signature in self._seen_tool_calls:
            return Authorization(False, "Repeated identical tool call denied.")
        self._seen_tool_calls.add(signature)
        return Authorization(True)
