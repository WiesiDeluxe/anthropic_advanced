"""Tool definitions for Anthropic Advanced Conversation.

This module defines the tools that Claude can call to interact with
Home Assistant. Unlike the native Anthropic integration (which only
uses the Assist API/Intents), this provides FULL access to HA services.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Tool definitions sent to Claude API
TOOLS = [
    {
        "name": "execute_services",
        "description": (
            "Execute one or more Home Assistant services. "
            "Use this for ALL device control: lights, switches, covers, climate, "
            "media players, TTS, scripts, automations, scenes, input helpers, etc. "
            "You can call ANY Home Assistant service."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "list": {
                    "type": "array",
                    "description": "List of services to execute",
                    "items": {
                        "type": "object",
                        "properties": {
                            "domain": {
                                "type": "string",
                                "description": "Service domain (e.g. light, switch, tts, media_player, script, automation, input_text, input_select)",
                            },
                            "service": {
                                "type": "string",
                                "description": "Service to call (e.g. turn_on, turn_off, toggle, speak, set_value, select_option)",
                            },
                            "entity_id": {
                                "type": "string",
                                "description": "Target entity ID (e.g. light.living_room, tts.home_assistant_cloud)",
                            },
                            "service_data": {
                                "type": "object",
                                "description": "Additional service data (e.g. brightness, message, media_player_entity_id)",
                            },
                        },
                        "required": ["domain", "service"],
                    },
                }
            },
            "required": ["list"],
        },
    },
    {
        "name": "get_entity_state",
        "description": (
            "Get the current state and attributes of one or more entities. "
            "Use this to check device states, sensor values, or any entity details."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_ids": {
                    "type": "array",
                    "description": "List of entity IDs to query",
                    "items": {"type": "string"},
                }
            },
            "required": ["entity_ids"],
        },
    },
    {
        "name": "get_history",
        "description": (
            "Get the state history of an entity for a given time period. "
            "Useful for answering questions like 'What was the temperature yesterday?' "
            "or 'When was the last time the garage door opened?'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "Entity ID to get history for",
                },
                "hours": {
                    "type": "number",
                    "description": "Number of hours to look back (default: 24)",
                },
            },
            "required": ["entity_id"],
        },
    },
    {
        "name": "search_entities",
        "description": (
            "Search for entities by name, domain, or area. "
            "Use this when you need to find entity IDs or discover available devices."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term (matches entity ID, friendly name, or area)",
                },
                "domain": {
                    "type": "string",
                    "description": "Optional domain filter (e.g. light, sensor, switch)",
                },
            },
            "required": ["query"],
        },
    },
]


def get_all_tools() -> list[dict]:
    """Get all tool definitions (base + extended)."""
    from .tools_extended import EXTENDED_TOOLS
    return TOOLS + EXTENDED_TOOLS


async def execute_tool(
    hass: HomeAssistant, tool_name: str, tool_input: dict[str, Any]
) -> str:
    """Execute a tool call from Claude and return the result as a string."""
    try:
        if tool_name == "execute_services":
            return await _execute_services(hass, tool_input)
        elif tool_name == "get_entity_state":
            return await _get_entity_state(hass, tool_input)
        elif tool_name == "get_history":
            return await _get_history(hass, tool_input)
        elif tool_name == "search_entities":
            return await _search_entities(hass, tool_input)
        else:
            # Try extended tools
            from .tools_extended import execute_extended_tool
            return await execute_extended_tool(hass, tool_name, tool_input)
    except Exception as e:
        _LOGGER.error("Error executing tool %s: %s", tool_name, e)
        return json.dumps({"error": str(e)})


async def _execute_services(
    hass: HomeAssistant, tool_input: dict[str, Any]
) -> str:
    """Execute Home Assistant services — the core power of this integration."""
    results = []
    for service_call in tool_input.get("list", []):
        domain = service_call.get("domain", "")
        service = service_call.get("service", "")
        entity_id = service_call.get("entity_id")
        service_data = service_call.get("service_data", {})

        # Build the service data dict
        data: dict[str, Any] = {**service_data}
        if entity_id:
            data["entity_id"] = entity_id

        try:
            await hass.services.async_call(
                domain, service, data, blocking=True
            )
            results.append({
                "domain": domain,
                "service": service,
                "entity_id": entity_id,
                "success": True,
            })
        except Exception as e:
            results.append({
                "domain": domain,
                "service": service,
                "entity_id": entity_id,
                "success": False,
                "error": str(e),
            })

    return json.dumps({"results": results})


async def _get_entity_state(
    hass: HomeAssistant, tool_input: dict[str, Any]
) -> str:
    """Get current state and attributes of entities."""
    entity_ids = tool_input.get("entity_ids", [])
    results = []

    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        if state is None:
            results.append({
                "entity_id": entity_id,
                "error": "Entity not found",
            })
        else:
            # Filter out large/noisy attributes
            attrs = dict(state.attributes)
            skip_keys = {"entity_picture", "icon", "supported_features",
                        "attribution", "device_class"}
            filtered_attrs = {
                k: v for k, v in attrs.items()
                if k not in skip_keys
            }
            results.append({
                "entity_id": entity_id,
                "state": state.state,
                "attributes": filtered_attrs,
                "last_changed": state.last_changed.isoformat(),
            })

    return json.dumps(results, default=str)


async def _get_history(
    hass: HomeAssistant, tool_input: dict[str, Any]
) -> str:
    """Get state history for an entity."""
    from homeassistant.components.recorder import get_instance
    from homeassistant.components.recorder.history import state_changes_during_period

    entity_id = tool_input.get("entity_id", "")
    hours = tool_input.get("hours", 24)

    end_time = datetime.now()
    start_time = end_time - timedelta(hours=hours)

    try:
        history = await get_instance(hass).async_add_executor_job(
            state_changes_during_period,
            hass,
            start_time,
            end_time,
            entity_id,
        )

        states = []
        for entity_states in history.values():
            for state in entity_states:
                states.append({
                    "state": state.state,
                    "last_changed": state.last_changed.isoformat(),
                    "attributes": {
                        k: v for k, v in state.attributes.items()
                        if k in ("friendly_name", "unit_of_measurement",
                                "temperature", "humidity")
                    },
                })

        return json.dumps({
            "entity_id": entity_id,
            "period_hours": hours,
            "state_changes": len(states),
            "states": states[-50:],  # Limit to last 50 changes
        }, default=str)
    except Exception as e:
        return json.dumps({"error": f"Could not get history: {e}"})


async def _search_entities(
    hass: HomeAssistant, tool_input: dict[str, Any]
) -> str:
    """Search for entities matching a query."""
    query = tool_input.get("query", "").lower()
    domain_filter = tool_input.get("domain")
    results = []

    for state in hass.states.async_all():
        if domain_filter and not state.entity_id.startswith(f"{domain_filter}."):
            continue

        name = state.attributes.get("friendly_name", "").lower()
        entity_id = state.entity_id.lower()

        if query in name or query in entity_id:
            results.append({
                "entity_id": state.entity_id,
                "state": state.state,
                "friendly_name": state.attributes.get("friendly_name"),
                "domain": state.domain,
            })

    return json.dumps({
        "query": query,
        "count": len(results),
        "results": results[:30],  # Limit results
    }, default=str)
