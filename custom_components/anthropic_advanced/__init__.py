"""Anthropic Advanced Conversation integration for Home Assistant.

A custom integration that provides Claude as a conversation agent with
FULL access to all Home Assistant services — not limited to Assist/Intents.
"""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CONVERSATION]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Anthropic Advanced from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # Register debug services (only once)
    if not hass.services.has_service(DOMAIN, "debug_history"):
        _register_debug_services(hass)

    _LOGGER.info("Anthropic Advanced Conversation set up successfully")
    return True


def _register_debug_services(hass: HomeAssistant) -> None:
    """Register diagnostic services."""

    async def handle_debug_history(call: ServiceCall) -> ServiceResponse:
        """Return conversation history statistics."""
        from .conversation import _history_manager

        conv_id = call.data.get("conversation_id")

        if conv_id:
            # Single conversation details
            messages = _history_manager.get(conv_id)
            tokens = _history_manager._estimate_tokens(messages)

            # Analyze message types
            user_msgs = sum(1 for m in messages if m.get("role") == "user")
            asst_msgs = sum(1 for m in messages if m.get("role") == "assistant")
            tool_blocks = 0
            compressed_blocks = 0
            for m in messages:
                content = m.get("content", [])
                if isinstance(content, list):
                    for b in content:
                        if isinstance(b, dict):
                            if b.get("type") == "tool_use":
                                tool_blocks += 1
                            elif b.get("type") == "tool_result":
                                tool_blocks += 1
                            text = b.get("text", "")
                            if isinstance(text, str) and text.startswith("[Tool]"):
                                compressed_blocks += 1

            return {
                "conversation_id": conv_id,
                "message_count": len(messages),
                "user_messages": user_msgs,
                "assistant_messages": asst_msgs,
                "active_tool_blocks": tool_blocks,
                "compressed_tool_summaries": compressed_blocks,
                "estimated_tokens": tokens,
                "token_budget": _history_manager._max_tokens,
                "budget_usage_pct": round(tokens / _history_manager._max_tokens * 100, 1) if _history_manager._max_tokens > 0 else 0,
            }
        else:
            # Overview of all conversations
            conversations = []
            for cid, msgs in _history_manager._histories.items():
                tokens = _history_manager._estimate_tokens(msgs)
                import time
                age_secs = time.time() - _history_manager._timestamps.get(cid, 0)
                conversations.append({
                    "conversation_id": cid,
                    "message_count": len(msgs),
                    "estimated_tokens": tokens,
                    "age_minutes": round(age_secs / 60, 1),
                })

            total_tokens = sum(c["estimated_tokens"] for c in conversations)
            return {
                "active_conversations": len(conversations),
                "total_estimated_tokens": total_tokens,
                "max_messages_per_conv": _history_manager._max_messages,
                "token_budget_per_conv": _history_manager._max_tokens,
                "conversations": conversations,
            }

    async def handle_clear_history(call: ServiceCall) -> ServiceResponse:
        """Clear conversation history."""
        from .conversation import _history_manager

        conv_id = call.data.get("conversation_id")

        if conv_id:
            _history_manager._histories.pop(conv_id, None)
            _history_manager._timestamps.pop(conv_id, None)
            return {"cleared": conv_id}
        else:
            count = len(_history_manager._histories)
            _history_manager._histories.clear()
            _history_manager._timestamps.clear()
            return {"cleared_all": count}

    hass.services.async_register(
        DOMAIN,
        "debug_history",
        handle_debug_history,
        schema=vol.Schema({
            vol.Optional("conversation_id"): str,
        }),
        supports_response=SupportsResponse.ONLY,
    )

    hass.services.async_register(
        DOMAIN,
        "clear_history",
        handle_clear_history,
        schema=vol.Schema({
            vol.Optional("conversation_id"): str,
        }),
        supports_response=SupportsResponse.ONLY,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update — reload the integration."""
    await hass.config_entries.async_reload(entry.entry_id)
