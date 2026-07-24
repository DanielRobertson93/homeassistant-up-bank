"""Shared device-info wiring for Up Bank entities (sensor, event, ...)."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import UpDataCoordinator


class UpBaseEntity(CoordinatorEntity[UpDataCoordinator]):
    _attr_should_poll = False

    def __init__(
        self, coordinator: UpDataCoordinator, entry: ConfigEntry, is_joint: bool = False
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        if is_joint:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"{entry.entry_id}_2up")},
                name="Up Bank (2Up)",
                manufacturer="Up",
            )
        else:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, entry.entry_id)},
                name="Up Bank",
                manufacturer="Up",
            )
