"""Sensor platform for Anthropic Advanced — token usage tracking."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN

from datetime import timedelta

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=30)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up token usage sensors."""
    sensors = [
        AnthropicUsageSensor(hass, config_entry, "total_input_tokens", "Input Tokens", "tokens", "mdi:arrow-up-bold"),
        AnthropicUsageSensor(hass, config_entry, "total_output_tokens", "Output Tokens", "tokens", "mdi:arrow-down-bold"),
        AnthropicUsageSensor(hass, config_entry, "total_cost", "Total Cost", "USD", "mdi:currency-usd", decimals=4),
        AnthropicUsageSensor(hass, config_entry, "total_requests", "Total Requests", "requests", "mdi:message-processing"),
        AnthropicUsageSensor(hass, config_entry, "total_tool_calls", "Tool Calls", "calls", "mdi:wrench"),
        AnthropicUsageSensor(hass, config_entry, "last_model", "Last Model", None, "mdi:brain"),
        AnthropicUsageSensor(hass, config_entry, "last_input_tokens", "Last Input Tokens", "tokens", "mdi:arrow-up"),
        AnthropicUsageSensor(hass, config_entry, "last_output_tokens", "Last Output Tokens", "tokens", "mdi:arrow-down"),
        AnthropicUsageSensor(hass, config_entry, "last_cost", "Last Cost", "USD", "mdi:cash", decimals=6),
    ]
    async_add_entities(sensors)


class AnthropicUsageSensor(SensorEntity):
    """Sensor for Anthropic API usage statistics."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        stat_key: str,
        name: str,
        unit: str | None,
        icon: str,
        decimals: int | None = None,
    ) -> None:
        """Initialize the sensor."""
        self.hass = hass
        self._config_entry = config_entry
        self._stat_key = stat_key
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        self._attr_unique_id = f"{config_entry.entry_id}_{stat_key}"
        self._decimals = decimals

        # Numeric sensors get state_class for long-term statistics
        if stat_key.startswith("total_") and stat_key != "total_requests":
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        elif stat_key.startswith("last_") and unit and unit != "USD":
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def device_info(self):
        """Tie to the same device as the conversation entity."""
        from homeassistant.helpers.device_registry import DeviceEntryType
        return {
            "identifiers": {(DOMAIN, self._config_entry.entry_id)},
            "name": self._config_entry.title or "Anthropic Advanced",
            "manufacturer": "Anthropic",
            "model": "Claude",
            "entry_type": DeviceEntryType.SERVICE,
        }

    @property
    def native_value(self):
        """Return current value from usage stats."""
        stats = self.hass.data.get(DOMAIN, {}).get("usage", {})
        value = stats.get(self._stat_key, 0 if self._stat_key != "last_model" else "unknown")
        if self._decimals is not None and isinstance(value, (int, float)):
            return round(value, self._decimals)
        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes for the total_cost sensor."""
        if self._stat_key == "total_cost":
            stats = self.hass.data.get(DOMAIN, {}).get("usage", {})
            return {
                "total_input_tokens": stats.get("total_input_tokens", 0),
                "total_output_tokens": stats.get("total_output_tokens", 0),
                "total_requests": stats.get("total_requests", 0),
                "total_tool_calls": stats.get("total_tool_calls", 0),
            }
        return {}

    async def async_update(self) -> None:
        """Sensor updates by reading hass.data — no polling needed."""
        pass
