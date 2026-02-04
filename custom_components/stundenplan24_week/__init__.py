from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.components import persistent_notification

from .const import DOMAIN
from .coordinator import SPlanCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor"]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    coordinator = SPlanCoordinator(hass, entry)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        raise ConfigEntryNotReady(str(err)) from err

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Card nach /config/www kopieren
    await _ensure_card_is_available_in_www(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def _ensure_card_is_available_in_www(hass: HomeAssistant) -> None:
    """
    Kopiert die mitgelieferte Card-JS nach:
      /config/www/stundenplan-card/stundenplan-card.js
    """
    integration_dir = Path(__file__).resolve().parent
    src = integration_dir / "www" / "stundenplan-card.js"

    if not src.exists():
        _LOGGER.warning("Stundenplan-Card JS nicht gefunden: %s", src)
        return

    dst_dir = Path(hass.config.path("www")) / "stundenplan-card"
    dst = dst_dir / "stundenplan-card.js"

    def _copy_if_needed() -> bool:
        dst_dir.mkdir(parents=True, exist_ok=True)

        if not dst.exists():
            dst.write_bytes(src.read_bytes())
            return True

        try:
            if src.stat().st_mtime > dst.stat().st_mtime:
                dst.write_bytes(src.read_bytes())
                return True
        except Exception:
            dst.write_bytes(src.read_bytes())
            return True

        return False

    changed = await hass.async_add_executor_job(_copy_if_needed)

    if changed:
        _LOGGER.info("Stundenplan-Card bereitgestellt: %s", dst)
        persistent_notification.async_create(
            hass,
            title="Stundenplan Card bereit",
            message=(
                "Die Stundenplan-Card wurde nach /config/www kopiert.\n\n"
                "Bitte als Lovelace-Resource hinzufügen:\n"
                "Einstellungen → Dashboards → Ressourcen\n"
                "URL: /local/stundenplan-card/stundenplan-card.js\n"
                "Typ: JavaScript Modul"
            ),
        )
