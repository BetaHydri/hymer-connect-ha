"""Backup platform for HYMER Connect."""

from homeassistant.core import HomeAssistant


async def async_pre_backup(hass: HomeAssistant) -> None:
    """Perform operations before a backup starts."""


async def async_post_backup(hass: HomeAssistant) -> None:
    """Perform operations after a backup completes."""
