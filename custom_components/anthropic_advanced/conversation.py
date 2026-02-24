"""Conversation platform for Anthropic Advanced.

This uses the modern ConversationEntity platform approach (HA 2025+),
not the deprecated async_set_agent method. The entity provides Claude
with FULL access to all Home Assistant services via tool calls.
"""
from __future__ import annotations

import json
import logging
from functools import partial
from typing import Any, Literal

import re

import anthropic
from anthropic.types import (
    ContentBlock,
    Message,
    TextBlock,
    ToolResultBlockParam,
    ToolUseBlock,
)

from homeassistant.components.conversation import (
    ConversationEntity,
    ConversationEntityFeature,
    ConversationInput,
    ConversationResult,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, area_registry as ar, template
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import ulid
import homeassistant.helpers.intent as intent

from .const import (
    CONF_AUTO_ROUTING,
    CONF_FAST_MODEL,
    CONF_MAX_HISTORY_MESSAGES,
    CONF_MAX_HISTORY_TOKENS,
    CONF_MAX_TOKENS,
    CONF_MAX_TOOL_CALLS,
    CONF_MODEL,
    CONF_PROMPT,
    CONF_TEMPERATURE,
    CONF_THINKING_BUDGET,
    DEFAULT_AUTO_ROUTING,
    DEFAULT_MAX_HISTORY_MESSAGES,
    DEFAULT_MAX_HISTORY_TOKENS,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MAX_TOOL_CALLS,
    DEFAULT_MODEL,
    DEFAULT_PROMPT,
    DEFAULT_TEMPERATURE,
    DEFAULT_THINKING_BUDGET,
    DOMAIN,
    FAST_MAX_TOKENS,
    FAST_MODEL,
)
from .tools import get_all_tools, execute_tool

_LOGGER = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# Conversation History Management
# ═══════════════════════════════════════════════════════════════

# TTL for inactive conversations (seconds)
_CONVERSATION_TTL = 3600  # 1 hour

class ConversationHistory:
    """Manages conversation history with token budgeting and tool compression."""

    def __init__(self, max_messages: int = 20, max_tokens: int = 12000):
        self._histories: dict[str, list[dict[str, Any]]] = {}
        self._timestamps: dict[str, float] = {}
        self._max_messages = max_messages
        self._max_tokens = max_tokens

    def get(self, conv_id: str) -> list[dict[str, Any]]:
        """Get messages for a conversation, creating if needed."""
        self._cleanup_expired()
        return self._histories.get(conv_id, [])

    def update(self, conv_id: str, messages: list[dict[str, Any]]) -> None:
        """Store messages after trimming and compressing."""
        import time
        self._timestamps[conv_id] = time.time()

        # Step 1: Compress tool interactions in older messages
        messages = self._compress_tool_history(messages)

        # Step 2: Trim by message count
        if len(messages) > self._max_messages * 2:
            messages = messages[-(self._max_messages * 2):]

        # Step 3: Trim by estimated token budget
        messages = self._trim_to_token_budget(messages)

        self._histories[conv_id] = messages

    def _estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        """Rough token estimation: ~4 chars per token for mixed content."""
        total_chars = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            total_chars += len(block.get("text", ""))
                        elif block.get("type") == "tool_use":
                            total_chars += len(str(block.get("input", {}))) + 50
                        elif block.get("type") == "tool_result":
                            total_chars += len(str(block.get("content", "")))
                        elif block.get("type") == "tool_summary":
                            total_chars += len(block.get("text", ""))
        return total_chars // 4

    def _compress_tool_history(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Replace old tool request/result pairs with compact summaries.
        
        Keeps the last 2 tool interactions intact (needed for context),
        compresses older ones into a single text summary.
        """
        if len(messages) <= 6:
            return messages  # Too short to compress

        # Find tool interaction pairs (assistant with tool_use + user with tool_result)
        tool_pairs: list[tuple[int, int]] = []
        i = 0
        while i < len(messages) - 1:
            msg = messages[i]
            next_msg = messages[i + 1]

            if (msg.get("role") == "assistant" 
                and isinstance(msg.get("content"), list)
                and any(b.get("type") == "tool_use" for b in msg["content"] if isinstance(b, dict))
                and next_msg.get("role") == "user"
                and isinstance(next_msg.get("content"), list)
                and any(b.get("type") == "tool_result" for b in next_msg["content"] if isinstance(b, dict))):
                tool_pairs.append((i, i + 1))
                i += 2
            else:
                i += 1

        if len(tool_pairs) <= 2:
            return messages  # Keep last 2 pairs intact

        # Compress all but last 2 pairs
        pairs_to_compress = tool_pairs[:-2]
        indices_to_remove = set()
        summaries: list[dict[str, Any]] = []

        for asst_idx, user_idx in pairs_to_compress:
            asst_msg = messages[asst_idx]
            user_msg = messages[user_idx]

            # Build compact summary
            parts = []
            for block in asst_msg.get("content", []):
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_name = block.get("name", "unknown")
                    tool_input = block.get("input", {})
                    # Extract key info from input
                    if isinstance(tool_input, dict):
                        input_summary = ", ".join(
                            f"{k}={v}" for k, v in tool_input.items()
                            if k != "entity_id" or True  # keep entity_id
                        )[:150]
                    else:
                        input_summary = str(tool_input)[:100]
                    parts.append(f"→ {tool_name}({input_summary})")

            for block in user_msg.get("content", []):
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    result_str = str(block.get("content", ""))[:200]
                    parts.append(f"  = {result_str}")

            if parts:
                summary_text = "[Tool] " + " | ".join(parts)
                summaries.append(summary_text)

            indices_to_remove.add(asst_idx)
            indices_to_remove.add(user_idx)

        # Build new message list
        result = []
        summary_inserted = False

        for idx, msg in enumerate(messages):
            if idx in indices_to_remove:
                if not summary_inserted and summaries:
                    # Insert compressed summary as assistant message
                    result.append({
                        "role": "assistant",
                        "content": [{"type": "text", "text": "\n".join(summaries)}],
                    })
                    summary_inserted = True
                continue
            result.append(msg)

        return result

    def _trim_to_token_budget(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Remove oldest messages until within token budget."""
        while len(messages) > 2 and self._estimate_tokens(messages) > self._max_tokens:
            # Always keep at least the last user + assistant pair
            messages.pop(0)
        return messages

    def _cleanup_expired(self) -> None:
        """Remove conversations older than TTL."""
        import time
        now = time.time()
        expired = [
            cid for cid, ts in self._timestamps.items()
            if now - ts > _CONVERSATION_TTL
        ]
        for cid in expired:
            self._histories.pop(cid, None)
            self._timestamps.pop(cid, None)
        if expired:
            _LOGGER.debug("Cleaned up %d expired conversations", len(expired))


# Global conversation history manager
_history_manager = ConversationHistory()


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the conversation entity."""
    async_add_entities([AnthropicAdvancedConversationEntity(hass, config_entry)])


class AnthropicAdvancedConversationEntity(ConversationEntity):
    """Anthropic Advanced conversation entity with full HA service access."""

    _attr_has_entity_name = True
    _attr_name = "Conversation"
    _attr_supported_features = ConversationEntityFeature.CONTROL

    def __init__(
        self, hass: HomeAssistant, config_entry: ConfigEntry
    ) -> None:
        """Initialize the entity."""
        self.hass = hass
        self._config_entry = config_entry
        self._client: anthropic.AsyncAnthropic | None = None
        self._attr_unique_id = config_entry.entry_id

    @property
    def device_info(self):
        """Return device info to tie this entity to a device."""
        from homeassistant.helpers.device_registry import DeviceEntryType
        return {
            "identifiers": {(DOMAIN, self._config_entry.entry_id)},
            "name": self._config_entry.title or "Anthropic Advanced",
            "manufacturer": "Anthropic",
            "model": "Claude",
            "entry_type": DeviceEntryType.SERVICE,
        }

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        """Return supported languages."""
        return MATCH_ALL

    async def _get_client(self) -> anthropic.AsyncAnthropic:
        """Get or create the Anthropic client (lazy init)."""
        if self._client is None:
            self._client = await self.hass.async_add_executor_job(
                partial(
                    anthropic.AsyncAnthropic,
                    api_key=self._config_entry.data[CONF_API_KEY],
                )
            )
        return self._client

    @staticmethod
    def _classify_complexity(text: str) -> str:
        """Classify user input as 'simple' or 'complex'.
        
        Simple: direct device control, status queries, TTS announcements
        Complex: history analysis, explanations, multi-step reasoning, energy summaries
        """
        text_lower = text.lower().strip()
        
        # Simple patterns — direct commands and quick queries
        simple_patterns = [
            r"^(schalte|mach|dreh|setz|stell)\b",      # Steuerungsbefehle
            r"^(licht|lampe)\b",                         # Lichtbefehle
            r"\b(ein|aus|an|ab)schalten\b",
            r"^sag\b.*\ban\b",                           # TTS "sag ... an"
            r"^durchsage\b",                             # Durchsage
            r"\b(öffne|schließe|sperre)\b",              # Covers/Locks
            r"^(wie warm|temperatur|wie kalt)\b",        # Schnelle Temperatur
            r"^(wie spät|uhrzeit|zeit)\b",               # Zeitfragen
            r"^(starte|stoppe|pause)\b",                 # Media control
            r"^(aktiviere|deaktiviere)\b",               # Automations
        ]
        
        # Complex patterns — need more reasoning
        complex_patterns = [
            r"\b(warum|weshalb|wieso|erkläre)\b",        # Erklärungen
            r"\b(verlauf|history|gestern|letzte.+stunde)\b",  # History
            r"\b(vergleich|unterschied)\b",              # Vergleiche
            r"\b(energie|solar|batterie|wallbox|strom)\b",    # Energieanalyse
            r"\b(automation|erstell|generier)\b",        # Automationen erstellen
            r"\b(dashboard|karte)\b",                    # Dashboard
            r"\b(zusammenfassung|überblick|status)\b",   # Zusammenfassungen
            r"\b(wann|wie oft|wie lange)\b",             # Zeitliche Analyse
        ]
        
        for pattern in complex_patterns:
            if re.search(pattern, text_lower):
                return "complex"
        
        for pattern in simple_patterns:
            if re.search(pattern, text_lower):
                return "simple"
        
        # Default: if short (<8 words) → simple, else complex
        return "simple" if len(text_lower.split()) < 8 else "complex"

    async def async_process(
        self, user_input: ConversationInput
    ) -> ConversationResult:
        """Process a sentence."""
        options = self._config_entry.options
        auto_routing = options.get(CONF_AUTO_ROUTING, DEFAULT_AUTO_ROUTING)
        
        # Auto-routing: pick model based on complexity
        if auto_routing:
            complexity = self._classify_complexity(user_input.text)
            if complexity == "simple":
                model = options.get(CONF_FAST_MODEL, FAST_MODEL)
                max_tokens = FAST_MAX_TOKENS
            else:
                model = options.get(CONF_MODEL, DEFAULT_MODEL)
                max_tokens = options.get(CONF_MAX_TOKENS, DEFAULT_MAX_TOKENS)
            _LOGGER.debug("Auto-routing: '%s' → %s (%s)", user_input.text[:50], complexity, model)
        else:
            model = options.get(CONF_MODEL, DEFAULT_MODEL)
            max_tokens = options.get(CONF_MAX_TOKENS, DEFAULT_MAX_TOKENS)
        
        temperature = options.get(CONF_TEMPERATURE, DEFAULT_TEMPERATURE)
        max_tool_calls = options.get(CONF_MAX_TOOL_CALLS, DEFAULT_MAX_TOOL_CALLS)
        thinking_budget = options.get(CONF_THINKING_BUDGET, DEFAULT_THINKING_BUDGET)

        # Update history manager limits from options
        _history_manager._max_messages = options.get(
            CONF_MAX_HISTORY_MESSAGES, DEFAULT_MAX_HISTORY_MESSAGES
        )
        _history_manager._max_tokens = options.get(
            CONF_MAX_HISTORY_TOKENS, DEFAULT_MAX_HISTORY_TOKENS
        )

        # Build the system prompt with Jinja2 rendering
        system_prompt = await self._render_prompt(
            options.get(CONF_PROMPT, DEFAULT_PROMPT)
        )

        # Get or create conversation history
        conv_id = user_input.conversation_id or ulid.ulid_now()
        messages = _history_manager.get(conv_id)

        # Append user message
        messages.append({"role": "user", "content": user_input.text})

        # Build API params
        api_params: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": messages,
            "tools": get_all_tools(),
        }

        # Only enable thinking for complex model (Haiku doesn't support it)
        is_fast_model = "haiku" in model.lower()
        if thinking_budget and thinking_budget >= 1024 and not is_fast_model:
            api_params["thinking"] = {
                "type": "enabled",
                "budget_tokens": thinking_budget,
            }
        else:
            api_params["temperature"] = temperature

        try:
            response = await self._call_with_tools(api_params, max_tool_calls)
        except anthropic.APIError as e:
            _LOGGER.error("Anthropic API error: %s", e)
            return self._error_response(
                conv_id, f"Anthropic API Fehler: {e.message}"
            )
        except Exception as e:
            _LOGGER.exception("Unexpected error during conversation")
            return self._error_response(
                conv_id, f"Unerwarteter Fehler: {e}"
            )

        # Extract text from response
        response_text = self._extract_text(response)

        # Update conversation history via manager (compresses + trims)
        assistant_content = self._serialize_content(response.content)
        messages.append({"role": "assistant", "content": assistant_content})
        _history_manager.update(conv_id, messages)

        intent_response = intent.IntentResponse(language=user_input.language)
        intent_response.async_set_speech(response_text)

        return ConversationResult(
            response=intent_response,
            conversation_id=conv_id,
        )

    async def _call_with_tools(
        self, api_params: dict[str, Any], max_tool_calls: int
    ) -> Message:
        """Call Claude API with iterative tool use."""
        tool_call_count = 0
        client = await self._get_client()

        while True:
            response = await client.messages.create(**api_params)

            # Check if Claude wants to use tools
            tool_use_blocks = [
                block for block in response.content
                if isinstance(block, ToolUseBlock)
            ]

            if not tool_use_blocks or response.stop_reason == "end_turn":
                return response

            if tool_call_count >= max_tool_calls:
                _LOGGER.warning("Maximum tool calls (%s) reached", max_tool_calls)
                return response

            # Execute each tool call
            tool_results: list[ToolResultBlockParam] = []
            for tool_block in tool_use_blocks:
                _LOGGER.debug(
                    "Executing tool: %s with input: %s",
                    tool_block.name, tool_block.input,
                )
                result = await execute_tool(
                    self.hass, tool_block.name, tool_block.input
                )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_block.id,
                    "content": result,
                })
                tool_call_count += 1

            # Append assistant response + tool results to messages
            assistant_content = self._serialize_content(response.content)
            api_params["messages"].append(
                {"role": "assistant", "content": assistant_content}
            )
            api_params["messages"].append(
                {"role": "user", "content": tool_results}
            )

    async def _render_prompt(self, prompt_template: str) -> str:
        """Render the system prompt with Jinja2 templates."""
        exposed_entities = self._get_exposed_entities()

        try:
            tpl = template.Template(prompt_template, self.hass)
            return tpl.async_render(
                {"exposed_entities": exposed_entities},
                parse_result=False,
            )
        except Exception as e:
            _LOGGER.error("Error rendering prompt template: %s", e)
            return prompt_template

    def _get_exposed_entities(self) -> list[dict[str, Any]]:
        """Get list of exposed entities."""
        entity_reg = er.async_get(self.hass)
        area_reg = ar.async_get(self.hass)
        entities = []

        try:
            from homeassistant.components.homeassistant.exposed_entities import (
                async_get_assistant_settings,
            )
            exposed_settings = async_get_assistant_settings(self.hass, "conversation")
        except (ImportError, Exception):
            exposed_settings = {}

        exposed_entity_ids = set()
        if exposed_settings:
            for entity_id, settings in exposed_settings.items():
                if settings.get("should_expose", False):
                    exposed_entity_ids.add(entity_id)

        use_default_filter = not exposed_entity_ids
        default_domains = {
            "light", "switch", "cover", "climate", "fan", "media_player",
            "script", "scene", "automation", "input_boolean", "input_number",
            "input_text", "input_select", "input_datetime", "lock", "vacuum",
        }

        for state in self.hass.states.async_all():
            if not use_default_filter and state.entity_id not in exposed_entity_ids:
                continue
            if use_default_filter and state.domain not in default_domains:
                continue

            entity_entry = entity_reg.async_get(state.entity_id)
            name = state.attributes.get("friendly_name", state.entity_id)

            area_name = None
            if entity_entry and entity_entry.area_id:
                area = area_reg.async_get_area(entity_entry.area_id)
                if area:
                    area_name = area.name
            elif entity_entry and entity_entry.device_id:
                from homeassistant.helpers import device_registry as dr
                device_reg = dr.async_get(self.hass)
                device = device_reg.async_get(entity_entry.device_id)
                if device and device.area_id:
                    area = area_reg.async_get_area(device.area_id)
                    if area:
                        area_name = area.name

            aliases = []
            if entity_entry and entity_entry.aliases:
                aliases = list(entity_entry.aliases)

            entities.append({
                "entity_id": state.entity_id,
                "name": name,
                "state": state.state,
                "domain": state.domain,
                "area": area_name,
                "aliases": aliases,
            })

        return entities

    def _serialize_content(
        self, content: list[ContentBlock]
    ) -> list[dict[str, Any]]:
        """Serialize Claude response content for conversation history."""
        serialized = []
        for block in content:
            if isinstance(block, TextBlock):
                serialized.append({"type": "text", "text": block.text})
            elif isinstance(block, ToolUseBlock):
                serialized.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })
            elif hasattr(block, "type") and block.type == "thinking":
                pass  # Skip thinking blocks
        return serialized

    def _extract_text(self, response: Message) -> str:
        """Extract text content from Claude's response."""
        texts = []
        for block in response.content:
            if isinstance(block, TextBlock):
                texts.append(block.text)
        return "\n".join(texts) if texts else "Ich konnte keine Antwort generieren."

    def _error_response(
        self, conv_id: str, message: str
    ) -> ConversationResult:
        """Create an error response."""
        intent_response = intent.IntentResponse(language="de")
        intent_response.async_set_error(
            intent.IntentResponseErrorCode.UNKNOWN,
            message,
        )
        return ConversationResult(
            response=intent_response,
            conversation_id=conv_id,
        )
