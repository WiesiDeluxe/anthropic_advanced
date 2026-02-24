"""Extended tools for Anthropic Advanced Conversation.

Additional tools for energy summaries, automation management,
and dashboard generation.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

EXTENDED_TOOLS = [
    {
        "name": "get_energy_summary",
        "description": (
            "Get a summary of the home's energy data: solar production, "
            "battery state, grid import/export, EV charging, and consumption. "
            "Use this when the user asks about energy, solar, battery, or power."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "description": "Time period: 'now' for current state, 'today' for daily totals, 'week' for last 7 days",
                    "enum": ["now", "today", "week"],
                },
            },
            "required": ["period"],
        },
    },
    {
        "name": "manage_automation",
        "description": (
            "Create, enable, disable, trigger, or list Home Assistant automations. "
            "Use this when the user wants to work with automations."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "What to do with the automation",
                    "enum": ["list", "enable", "disable", "trigger", "create"],
                },
                "entity_id": {
                    "type": "string",
                    "description": "automation.xxx entity_id (for enable/disable/trigger)",
                },
                "yaml_config": {
                    "type": "string",
                    "description": "YAML configuration for creating a new automation (for create action)",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "generate_dashboard_card",
        "description": (
            "Generate a Home Assistant dashboard card configuration in YAML. "
            "Use this when the user asks for a dashboard card, widget, or visualization."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "card_type": {
                    "type": "string",
                    "description": "Type of card to generate",
                    "enum": [
                        "entities", "gauge", "history-graph",
                        "energy", "weather", "area", "custom",
                    ],
                },
                "entities": {
                    "type": "array",
                    "description": "List of entity_ids to include",
                    "items": {"type": "string"},
                },
                "title": {
                    "type": "string",
                    "description": "Card title",
                },
                "description": {
                    "type": "string",
                    "description": "What the user wants to see (for custom cards)",
                },
            },
            "required": ["card_type"],
        },
    },
    {
        "name": "memory",
        "description": (
            "Persistent memory for storing and retrieving user preferences, "
            "frequently used settings, and personal information across sessions. "
            "Use 'save' to remember something, 'get' to recall a specific key, "
            "'list' to see all stored memories, 'delete' to remove one. "
            "Examples: light preferences, wake-up times, favorite scenes, names, "
            "room assignments, routine schedules."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Memory action",
                    "enum": ["save", "get", "list", "delete"],
                },
                "key": {
                    "type": "string",
                    "description": "Memory key (e.g. 'light_preference_office', 'wakeup_time_kids', 'favorite_scene')",
                },
                "value": {
                    "type": "string",
                    "description": "Value to store (for 'save' action)",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "analyze_home",
        "description": (
            "Proactive home analysis: scans all entities for anomalies, warnings, "
            "and status info. Detects: unavailable devices, temperature extremes, "
            "high/low humidity, low batteries, open doors/windows, lights left on. "
            "Use this when the user asks 'is everything ok?', 'any problems?', "
            "'home status', 'what should I know?', or for a morning briefing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
]


async def execute_extended_tool(
    hass: HomeAssistant, tool_name: str, tool_input: dict[str, Any]
) -> str:
    """Execute an extended tool call."""
    try:
        if tool_name == "get_energy_summary":
            return await _get_energy_summary(hass, tool_input)
        elif tool_name == "manage_automation":
            return await _manage_automation(hass, tool_input)
        elif tool_name == "generate_dashboard_card":
            return await _generate_dashboard_card(hass, tool_input)
        elif tool_name == "memory":
            return await _memory(hass, tool_input)
        elif tool_name == "analyze_home":
            return await _analyze_home(hass, tool_input)
        else:
            return json.dumps({"error": f"Unknown extended tool: {tool_name}"})
    except Exception as e:
        _LOGGER.error("Error executing extended tool %s: %s", tool_name, e)
        return json.dumps({"error": str(e)})


async def _get_energy_summary(
    hass: HomeAssistant, tool_input: dict[str, Any]
) -> str:
    """Get comprehensive energy summary."""
    period = tool_input.get("period", "now")
    summary: dict[str, Any] = {"period": period, "timestamp": datetime.now().isoformat()}

    # Common energy entity patterns from popular integrations
    # (Sigenergy, SolarEdge, Fronius, SMA, Huawei, Enphase, etc.)
    energy_entities = {
        "pv_power": [
            "sensor.sigenergy_plant_pv_power",
            "sensor.sigenergy_pv_power",
            "sensor.solaredge_current_power",
            "sensor.fronius_power_photovoltaics",
            "sensor.sma_solar_power",
            "sensor.huawei_solar_input_power",
            "sensor.enphase_current_power_production",
        ],
        "battery_soc": [
            "sensor.sigenergy_plant_battery_soc",
            "sensor.sigenergy_battery_soc",
            "sensor.solaredge_battery_level",
            "sensor.powerwall_charge",
            "sensor.huawei_solar_battery_state_of_capacity",
        ],
        "battery_power": [
            "sensor.sigenergy_plant_battery_power",
            "sensor.sigenergy_battery_power",
            "sensor.solaredge_battery_power",
            "sensor.powerwall_battery_power",
            "sensor.huawei_solar_battery_charge_discharge_power",
        ],
        "grid_power": [
            "sensor.sigenergy_plant_grid_power",
            "sensor.sigenergy_grid_power",
            "sensor.solaredge_grid_power",
            "sensor.fronius_power_grid",
            "sensor.sma_grid_power",
            "sensor.huawei_solar_power_meter_active_power",
        ],
        "consumption_power": [
            "sensor.sigenergy_plant_consumption_power",
            "sensor.sigenergy_consumption_power",
            "sensor.solaredge_consumption_power",
            "sensor.fronius_power_load",
            "sensor.huawei_solar_house_consumption_power",
        ],
        "daily_pv": [
            "sensor.sigenergy_plant_daily_pv_production",
            "sensor.sigenergy_daily_pv_production",
            "sensor.solaredge_energy_today",
            "sensor.fronius_energy_day",
            "sensor.huawei_solar_daily_yield",
        ],
        "daily_consumption": [
            "sensor.sigenergy_plant_daily_consumption",
            "sensor.sigenergy_daily_consumption",
        ],
        "daily_grid_import": [
            "sensor.sigenergy_plant_daily_grid_energy_import",
            "sensor.sigenergy_daily_grid_import",
        ],
        "daily_grid_export": [
            "sensor.sigenergy_plant_daily_grid_energy_export",
            "sensor.sigenergy_daily_grid_export",
        ],
        "wallbox_power": [
            "sensor.tesla_wall_connector_power",
            "sensor.wallbox_power",
            "sensor.ocpp_power_active_import",
            "sensor.easee_power",
            "sensor.go_echarger_power",
        ],
        "wallbox_daily": [
            "sensor.evcc_charge_energy_daily",
            "sensor.wallbox_daily_energy",
        ],
    }

    # Try to find and read each entity
    for key, entity_ids in energy_entities.items():
        for entity_id in entity_ids:
            state = hass.states.get(entity_id)
            if state and state.state not in ("unknown", "unavailable"):
                unit = state.attributes.get("unit_of_measurement", "")
                try:
                    value = float(state.state)
                    summary[key] = {"value": value, "unit": unit, "entity_id": entity_id}
                except ValueError:
                    summary[key] = {"value": state.state, "unit": unit, "entity_id": entity_id}
                break  # Use first found entity

    # Also scan for any energy-related entities not in our predefined list
    if period == "now":
        extra_entities = []
        for state in hass.states.async_all():
            if state.entity_id.startswith("sensor.") and state.state not in ("unknown", "unavailable"):
                attrs = state.attributes
                device_class = attrs.get("device_class", "")
                if device_class in ("power", "energy", "battery"):
                    if not any(state.entity_id in ids for ids in energy_entities.values()):
                        try:
                            extra_entities.append({
                                "entity_id": state.entity_id,
                                "name": attrs.get("friendly_name", ""),
                                "value": float(state.state),
                                "unit": attrs.get("unit_of_measurement", ""),
                                "device_class": device_class,
                            })
                        except ValueError:
                            pass
        if extra_entities:
            summary["additional_energy_entities"] = extra_entities[:20]

    return json.dumps(summary, default=str)


async def _manage_automation(
    hass: HomeAssistant, tool_input: dict[str, Any]
) -> str:
    """Manage Home Assistant automations."""
    action = tool_input.get("action", "list")

    if action == "list":
        automations = []
        for state in hass.states.async_all("automation"):
            automations.append({
                "entity_id": state.entity_id,
                "name": state.attributes.get("friendly_name", ""),
                "state": state.state,
                "last_triggered": str(state.attributes.get("last_triggered", "")),
            })
        return json.dumps({"automations": automations, "count": len(automations)})

    elif action in ("enable", "disable"):
        entity_id = tool_input.get("entity_id", "")
        if not entity_id:
            return json.dumps({"error": "entity_id required"})
        service = "turn_on" if action == "enable" else "turn_off"
        await hass.services.async_call(
            "automation", service, {"entity_id": entity_id}, blocking=True
        )
        return json.dumps({"success": True, "action": action, "entity_id": entity_id})

    elif action == "trigger":
        entity_id = tool_input.get("entity_id", "")
        if not entity_id:
            return json.dumps({"error": "entity_id required"})
        await hass.services.async_call(
            "automation", "trigger", {"entity_id": entity_id}, blocking=True
        )
        return json.dumps({"success": True, "action": "triggered", "entity_id": entity_id})

    elif action == "create":
        yaml_config = tool_input.get("yaml_config", "")
        if not yaml_config:
            return json.dumps({"error": "yaml_config required for create action"})
        # Return the YAML for manual review — creating automations via
        # the API requires writing to automations.yaml which is risky
        return json.dumps({
            "action": "create",
            "note": "Automation YAML generated. Please review and add to your automations.yaml:",
            "yaml": yaml_config,
        })

    return json.dumps({"error": f"Unknown action: {action}"})


async def _generate_dashboard_card(
    hass: HomeAssistant, tool_input: dict[str, Any]
) -> str:
    """Generate dashboard card YAML configuration."""
    import yaml

    card_type = tool_input.get("card_type", "entities")
    entities = tool_input.get("entities", [])
    title = tool_input.get("title", "")
    description = tool_input.get("description", "")

    card: dict[str, Any] = {}

    if card_type == "entities":
        card = {
            "type": "entities",
            "title": title or "Geräte",
            "entities": entities or [],
        }
    elif card_type == "gauge":
        entity = entities[0] if entities else ""
        card = {
            "type": "gauge",
            "entity": entity,
            "name": title,
            "min": 0,
            "max": 100,
        }
    elif card_type == "history-graph":
        card = {
            "type": "history-graph",
            "title": title or "Verlauf",
            "entities": [{"entity": e} for e in entities],
            "hours_to_show": 24,
        }
    elif card_type == "energy":
        card = {
            "type": "energy-distribution",
            "title": title or "Energieverteilung",
            "link_dashboard": True,
        }
    elif card_type == "weather":
        weather_entity = entities[0] if entities else "weather.home"
        card = {
            "type": "weather-forecast",
            "entity": weather_entity,
            "name": title or "Wetter",
            "show_current": True,
            "show_forecast": True,
        }
    elif card_type == "area":
        card = {
            "type": "area",
            "area": title or "Wohnzimmer",
            "show_camera": False,
        }
    elif card_type == "custom":
        # For custom cards, generate based on description
        card = {
            "type": "markdown",
            "title": title or "Info",
            "content": description or "Bitte beschreibe was du sehen möchtest.",
        }

    yaml_output = yaml.dump(card, default_flow_style=False, allow_unicode=True)
    return json.dumps({
        "card_type": card_type,
        "yaml": yaml_output,
        "note": "Kopiere dieses YAML in dein Dashboard (Dashboard bearbeiten → Karte hinzufügen → YAML-Editor)",
    })

# ═══════════════════════════════════════════════════════════════
# Memory — Persistent key-value storage via HA helpers
# ═══════════════════════════════════════════════════════════════

MEMORY_FILE = ".anthropic_memory.json"


def _get_memory_path(hass: HomeAssistant) -> str:
    """Get path to memory file in HA config directory."""
    return hass.config.path(MEMORY_FILE)


def _load_memory(hass: HomeAssistant) -> dict[str, str]:
    """Load memory from JSON file."""
    import os
    path = _get_memory_path(hass)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            _LOGGER.error("Failed to load memory: %s", e)
    return {}


def _save_memory(hass: HomeAssistant, data: dict[str, str]) -> None:
    """Save memory to JSON file."""
    path = _get_memory_path(hass)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except IOError as e:
        _LOGGER.error("Failed to save memory: %s", e)


async def _memory(
    hass: HomeAssistant, tool_input: dict[str, Any]
) -> str:
    """Persistent memory: save, get, list, or delete key-value pairs."""
    action = tool_input.get("action", "list")
    key = tool_input.get("key", "")
    value = tool_input.get("value", "")

    # Load from file (run in executor to avoid blocking)
    memory = await hass.async_add_executor_job(_load_memory, hass)

    if action == "save":
        if not key:
            return json.dumps({"error": "Key is required for save action"})
        memory[key] = value
        await hass.async_add_executor_job(_save_memory, hass, memory)
        return json.dumps({
            "action": "saved",
            "key": key,
            "value": value,
            "total_memories": len(memory),
        })

    elif action == "get":
        if not key:
            return json.dumps({"error": "Key is required for get action"})
        if key in memory:
            return json.dumps({"key": key, "value": memory[key]})
        else:
            return json.dumps({"key": key, "found": False})

    elif action == "list":
        if not memory:
            return json.dumps({"memories": [], "total": 0})
        return json.dumps({
            "memories": [{"key": k, "value": v} for k, v in memory.items()],
            "total": len(memory),
        })

    elif action == "delete":
        if not key:
            return json.dumps({"error": "Key is required for delete action"})
        if key in memory:
            deleted_value = memory.pop(key)
            await hass.async_add_executor_job(_save_memory, hass, memory)
            return json.dumps({"action": "deleted", "key": key, "previous_value": deleted_value})
        else:
            return json.dumps({"key": key, "found": False})

    return json.dumps({"error": f"Unknown memory action: {action}"})


async def _analyze_home(
    hass: HomeAssistant, tool_input: dict[str, Any]
) -> str:
    """Proactive home analysis — scan for anomalies and status."""
    anomalies = []
    warnings = []
    info = []

    for state in hass.states.async_all():
        entity_id = state.entity_id
        domain = state.domain
        attrs = state.attributes
        friendly = attrs.get("friendly_name", entity_id)
        val = state.state

        # Unavailable devices
        if val in ("unavailable", "unknown"):
            if domain in ("light", "switch", "climate", "cover", "sensor", "binary_sensor"):
                anomalies.append(f"⚠️ {friendly} ({entity_id}): {val}")
            continue

        # Temperature anomalies
        if domain == "sensor" and attrs.get("device_class") == "temperature":
            try:
                temp = float(val)
                if temp > 35:
                    anomalies.append(f"🔥 {friendly}: {temp}°C (sehr hoch!)")
                elif temp < 5 and "outdoor" not in entity_id and "außen" not in friendly.lower() and "outside" not in entity_id:
                    anomalies.append(f"🥶 {friendly}: {temp}°C (sehr kalt!)")
            except (ValueError, TypeError):
                pass

        # Humidity
        if domain == "sensor" and attrs.get("device_class") == "humidity":
            try:
                hum = float(val)
                if hum > 80:
                    warnings.append(f"💧 {friendly}: {hum}% (hohe Luftfeuchtigkeit)")
                elif hum < 20:
                    warnings.append(f"🏜️ {friendly}: {hum}% (sehr trocken)")
            except (ValueError, TypeError):
                pass

        # Battery
        if attrs.get("device_class") == "battery":
            try:
                batt = float(val)
                if batt < 15:
                    warnings.append(f"🪫 {friendly}: {batt}% Batterie")
            except (ValueError, TypeError):
                pass

        # Open doors/windows
        if domain == "binary_sensor" and val == "on":
            dc = attrs.get("device_class", "")
            if dc in ("door", "window", "garage_door"):
                info.append(f"🚪 {friendly}: offen")

        # Lights on
        if domain == "light" and val == "on":
            brightness = attrs.get("brightness")
            bri_str = f" ({round(brightness/255*100)}%)" if brightness else ""
            info.append(f"💡 {friendly}: an{bri_str}")

    result = {
        "anomalies": anomalies,
        "warnings": warnings,
        "lights_and_doors": info,
        "summary": f"{len(anomalies)} Probleme, {len(warnings)} Warnungen, "
                   f"{len(info)} aktive Geräte/Öffnungen"
    }
    return json.dumps(result, ensure_ascii=False)
