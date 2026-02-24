"""Config flow for Anthropic Advanced Conversation."""
from __future__ import annotations

import logging
from typing import Any

import anthropic
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_API_KEY
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

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
    FAST_MODEL,
)

_LOGGER = logging.getLogger(__name__)


class AnthropicAdvancedConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Anthropic Advanced."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                from functools import partial
                client = await self.hass.async_add_executor_job(
                    partial(anthropic.AsyncAnthropic, api_key=user_input[CONF_API_KEY])
                )
                await client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=10,
                    messages=[{"role": "user", "content": "Hi"}],
                )
            except anthropic.AuthenticationError:
                errors["base"] = "invalid_auth"
            except anthropic.APIConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title="Anthropic Advanced",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow."""
        return AnthropicAdvancedOptionsFlow()


class AnthropicAdvancedOptionsFlow(OptionsFlow):
    """Handle options flow.
    
    Note: In HA 2025.12+, self.config_entry is a read-only property
    set automatically by HA. Do NOT set it in __init__.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_AUTO_ROUTING,
                        default=self.config_entry.options.get(
                            CONF_AUTO_ROUTING, DEFAULT_AUTO_ROUTING
                        ),
                    ): bool,
                    vol.Optional(
                        CONF_MODEL,
                        default=self.config_entry.options.get(
                            CONF_MODEL, DEFAULT_MODEL
                        ),
                    ): str,
                    vol.Optional(
                        CONF_FAST_MODEL,
                        default=self.config_entry.options.get(
                            CONF_FAST_MODEL, FAST_MODEL
                        ),
                    ): str,
                    vol.Optional(
                        CONF_MAX_TOKENS,
                        default=self.config_entry.options.get(
                            CONF_MAX_TOKENS, DEFAULT_MAX_TOKENS
                        ),
                    ): int,
                    vol.Optional(
                        CONF_TEMPERATURE,
                        default=self.config_entry.options.get(
                            CONF_TEMPERATURE, DEFAULT_TEMPERATURE
                        ),
                    ): vol.Coerce(float),
                    vol.Optional(
                        CONF_MAX_TOOL_CALLS,
                        default=self.config_entry.options.get(
                            CONF_MAX_TOOL_CALLS, DEFAULT_MAX_TOOL_CALLS
                        ),
                    ): int,
                    vol.Optional(
                        CONF_THINKING_BUDGET,
                        default=self.config_entry.options.get(
                            CONF_THINKING_BUDGET, DEFAULT_THINKING_BUDGET
                        ),
                    ): int,
                    vol.Optional(
                        CONF_MAX_HISTORY_MESSAGES,
                        default=self.config_entry.options.get(
                            CONF_MAX_HISTORY_MESSAGES, DEFAULT_MAX_HISTORY_MESSAGES
                        ),
                    ): int,
                    vol.Optional(
                        CONF_MAX_HISTORY_TOKENS,
                        default=self.config_entry.options.get(
                            CONF_MAX_HISTORY_TOKENS, DEFAULT_MAX_HISTORY_TOKENS
                        ),
                    ): int,
                    vol.Optional(
                        CONF_PROMPT,
                        default=self.config_entry.options.get(
                            CONF_PROMPT, DEFAULT_PROMPT
                        ),
                    ): TextSelector(TextSelectorConfig(multiline=True)),
                }
            ),
        )
