"""Base agent class — handles Claude API calls with tool use."""

import asyncio
import json
import logging
from typing import Any

from agents.tools import TOOL_DEFINITIONS, ToolExecutor
from config.settings import settings

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 10


class BaseAgent:
    """Agent that can reason and use tools via Claude API."""

    def __init__(self, name: str, system_prompt: str, tool_executor: ToolExecutor):
        self.name = name
        self.system_prompt = system_prompt
        self.tools = tool_executor
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import anthropic

                self._client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
            except Exception as e:
                logger.warning(
                    "Agent %s: Anthropic client unavailable: %s", self.name, e
                )
        return self._client

    async def run(
        self,
        task: str,
        context: dict[str, Any] | None = None,
        tools: list[dict] | None = None,
    ) -> str:
        """Run the agent with a task. Returns final text response."""
        client = self._get_client()
        if not client:
            return f"[{self.name}] AI unavailable — set ANTHROPIC_API_KEY"

        available_tools = tools or TOOL_DEFINITIONS
        messages: list[dict[str, Any]] = []

        # Build initial message with context
        content = task
        if context:
            content = (
                f"Context:\n{json.dumps(context, default=str)[:3000]}\n\nTask: {task}"
            )

        messages.append({"role": "user", "content": content})

        # Agent loop — reason, use tools, reason again
        for round_num in range(MAX_TOOL_ROUNDS):
            try:
                response = await asyncio.to_thread(
                    client.messages.create,
                    model=settings.AI_MODEL,
                    max_tokens=2048,
                    system=self.system_prompt,
                    tools=available_tools,
                    messages=messages,
                )
            except Exception as e:
                logger.warning("Agent %s round %d failed: %s", self.name, round_num, e)
                return f"[{self.name}] AI error: {e}"

            # Check if we got a final text response
            if response.stop_reason == "end_turn":
                text_parts = [b.text for b in response.content if hasattr(b, "text")]
                return (
                    "\n".join(text_parts)
                    if text_parts
                    else f"[{self.name}] No response"
                )

            # Process tool calls
            if response.stop_reason == "tool_use":
                # Add assistant message with tool use blocks
                messages.append({"role": "assistant", "content": response.content})

                # Execute each tool call
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        logger.info(
                            "Agent %s using tool: %s(%s)",
                            self.name,
                            block.name,
                            json.dumps(block.input)[:100],
                        )
                        result = await self.tools.execute(block.name, block.input)
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result[:4000],  # truncate large results
                            }
                        )

                messages.append({"role": "user", "content": tool_results})
            else:
                # Unexpected stop reason
                text_parts = [b.text for b in response.content if hasattr(b, "text")]
                return (
                    "\n".join(text_parts)
                    if text_parts
                    else f"[{self.name}] Stopped: {response.stop_reason}"
                )

        return f"[{self.name}] Reached max tool rounds ({MAX_TOOL_ROUNDS})"
