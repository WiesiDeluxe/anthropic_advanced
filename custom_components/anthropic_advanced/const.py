"""Constants for the Anthropic Advanced Conversation integration."""

DOMAIN = "anthropic_advanced"

CONF_PROMPT = "prompt"
CONF_MODEL = "model"
CONF_MAX_TOKENS = "max_tokens"
CONF_TEMPERATURE = "temperature"
CONF_MAX_TOOL_CALLS = "max_tool_calls"
CONF_THINKING_BUDGET = "thinking_budget"

DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
FAST_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_MAX_TOKENS = 4096
FAST_MAX_TOKENS = 2048
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOOL_CALLS = 15
DEFAULT_THINKING_BUDGET = 0

CONF_AUTO_ROUTING = "auto_routing"
CONF_FAST_MODEL = "fast_model"
CONF_MAX_HISTORY_MESSAGES = "max_history_messages"
CONF_MAX_HISTORY_TOKENS = "max_history_tokens"
DEFAULT_AUTO_ROUTING = True
DEFAULT_MAX_HISTORY_MESSAGES = 20
DEFAULT_MAX_HISTORY_TOKENS = 12000

DEFAULT_PROMPT = """Du bist ein intelligenter Hausassistent. Antworte auf Deutsch, kurz und präzise.
Zeit: {{now().strftime('%A %d.%m.%Y %H:%M')}}.

══ REGELN ══
• execute_services für ALLE Steuerung (Licht, TTS, Scripts, Klima, Covers, etc.)
• get_entity_state / get_history / search_entities für Abfragen
• get_energy_summary für Energiefragen (Solar, Batterie, Wallbox)
• memory Tool: Speichere Präferenzen & Infos die du dir merken sollst (z.B. Lieblingsszenen, Routinen, Namen). Lade gespeicherte Erinnerungen bei relevanten Fragen.
• Mehrere Services in einem Call möglich. Bestätige kurz.

══ GERÄTE ══
{% for entity in exposed_entities -%}
{{entity.entity_id}}|{{entity.name}}|{{entity.state}}
{% endfor %}"""

# Tool definitions for Claude
TOOL_EXECUTE_SERVICES = "execute_services"
TOOL_GET_HISTORY = "get_history"
TOOL_GET_ENTITY_STATE = "get_entity_state"
