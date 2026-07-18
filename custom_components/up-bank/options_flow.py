"""Options UI for Up Bank (set refresh interval)."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries

from .const import DEFAULT_REFRESH_MIN


class UpBankOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Up Bank options."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options.get("refresh_minutes", DEFAULT_REFRESH_MIN)
        schema = vol.Schema({
            vol.Required("refresh_minutes", default=current): vol.In([1, 2, 5, 10, 15, 30, 60]),
        })
        return self.async_show_form(step_id="init", data_schema=schema)
