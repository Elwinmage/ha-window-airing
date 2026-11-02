"""House coordinator: the home-wide season (winter mode) and its auto switching.

A single dedicated config entry owns the winter switch. Rooms never decide the
season: they read it from here and are told when it changes.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    ALERT_SEASON,
    CONF_HEATING_CLIMATES,
    CONF_SUMMER_IDLE_DAYS,
    CONF_SUMMER_START_MONTH,
    CONF_WINTER_HEATING_MIN,
    CONF_WINTER_MAX_REMINDERS,
    CONF_WINTER_REMINDER_INTERVAL,
    CONF_WINTER_START_MONTH,
    DEFAULT_SUMMER_IDLE_DAYS,
    DEFAULT_SUMMER_START_MONTH,
    DEFAULT_WINTER_HEATING_MIN,
    DEFAULT_WINTER_MAX_OPEN,
    DEFAULT_WINTER_MAX_REMINDERS,
    DEFAULT_WINTER_REMINDER_INTERVAL,
    DEFAULT_WINTER_START_MONTH,
    DOMAIN,
    EVENT_ALERT,
    HEATING_ACTIONS,
    SIGNAL_SEASON,
    SOURCE_AUTO,
    SOURCE_MANUAL,
    STORAGE_VERSION,
    UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

# The heating counter changes every minute while heating: batch its writes.
SAVE_DELAY = 60
# Longest gap between two ticks still counted: a suspended host is not heating.
MAX_TICK_GAP = 300


def month_in_range(month: int, start: int, end: int) -> bool:
    """True if `month` is in the cyclic range [start, end[ (may cross new year)."""
    if start <= end:
        return start <= month < end
    return month >= start or month < end


class WindowAiringHouse(DataUpdateCoordinator):
    """Home-wide coordinator: winter switch, heating time, auto switching."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_house",
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self.entry = entry
        self._store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}")

        # Persisted.
        self.winter = False
        self.source: str | None = None
        self.changed_at: str | None = None
        self._day: date = dt_util.now().date()
        self._heating_s = 0.0
        self._last_heat_day: date | None = None
        self._manual_block_day: date | None = None

        # Live maximum open time (seconds), driven by the `number` entity, which
        # restores its own stored value on start.
        self.winter_max_open_s = DEFAULT_WINTER_MAX_OPEN

        # Accumulation state: not persisted, so downtime is never counted.
        self._last_tick: datetime | None = None
        self._was_heating = False

        self._unsub_state = None

    # ── config helpers ───────────────────────────────────────────────────────
    @property
    def _cfg(self) -> dict:
        return {**self.entry.data, **self.entry.options}

    @property
    def climates(self) -> list[str]:
        return list(self._cfg.get(CONF_HEATING_CLIMATES) or [])

    @property
    def heating_threshold_s(self) -> int:
        minutes = self._cfg.get(CONF_WINTER_HEATING_MIN, DEFAULT_WINTER_HEATING_MIN)
        return int(minutes) * 60

    @property
    def summer_idle_days(self) -> int:
        return int(self._cfg.get(CONF_SUMMER_IDLE_DAYS, DEFAULT_SUMMER_IDLE_DAYS))

    @property
    def winter_start_month(self) -> int:
        return int(self._cfg.get(CONF_WINTER_START_MONTH, DEFAULT_WINTER_START_MONTH))

    @property
    def summer_start_month(self) -> int:
        return int(self._cfg.get(CONF_SUMMER_START_MONTH, DEFAULT_SUMMER_START_MONTH))

    @property
    def reminder_interval_s(self) -> int:
        minutes = self._cfg.get(
            CONF_WINTER_REMINDER_INTERVAL, DEFAULT_WINTER_REMINDER_INTERVAL
        )
        return int(minutes) * 60

    @property
    def max_reminders(self) -> int:
        return int(
            self._cfg.get(CONF_WINTER_MAX_REMINDERS, DEFAULT_WINTER_MAX_REMINDERS)
        )

    @property
    def device_info(self) -> dr.DeviceInfo:
        return dr.DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name=self.entry.title,
            manufacturer="Window Airing",
            model="Season manager",
        )

    # ── lifecycle ────────────────────────────────────────────────────────────
    async def async_setup(self) -> None:
        stored = await self._store.async_load()
        if stored:
            self.winter = stored.get("winter", False)
            self.source = stored.get("source")
            self.changed_at = stored.get("changed_at")
            self._heating_s = float(stored.get("heating_s", 0.0))
            self._day = self._parse_day(stored.get("day")) or self._day
            self._last_heat_day = self._parse_day(stored.get("last_heat_day"))
            self._manual_block_day = self._parse_day(stored.get("manual_block_day"))

        if self.climates:
            self._unsub_state = async_track_state_change_event(
                self.hass, self.climates, self._handle_state_event
            )

    async def async_shutdown(self) -> None:
        if self._unsub_state:
            self._unsub_state()
            self._unsub_state = None
        await self._persist()
        await super().async_shutdown()

    @staticmethod
    def _parse_day(raw: str | None) -> date | None:
        if not raw:
            return None
        try:
            return date.fromisoformat(raw)
        except ValueError:
            return None

    def _snapshot(self) -> dict:
        def iso(day: date | None) -> str | None:
            return day.isoformat() if day else None

        return {
            "winter": self.winter,
            "source": self.source,
            "changed_at": self.changed_at,
            "day": iso(self._day),
            "heating_s": self._heating_s,
            "last_heat_day": iso(self._last_heat_day),
            "manual_block_day": iso(self._manual_block_day),
        }

    async def _persist(self) -> None:
        await self._store.async_save(self._snapshot())

    @callback
    def _handle_state_event(self, event: Event) -> None:
        self.hass.async_create_task(self.async_request_refresh())

    @callback
    def async_notify_rooms(self) -> None:
        """Tell the rooms that the season or its settings changed."""
        async_dispatcher_send(self.hass, SIGNAL_SEASON)

    # ── heating time ─────────────────────────────────────────────────────────
    def _heating_status(self, entity_id: str) -> bool | None:
        """True/False if heating, None when the climate state is unknown.

        `hvac_action` says what the unit is really doing. The state alone is
        only its mode: a radiator left in `heat` in June would count all day,
        so it is a fallback for climates that do not expose an action.
        """
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unavailable", "unknown"):
            return None
        action = state.attributes.get("hvac_action")
        if action is not None:
            return action in HEATING_ACTIONS
        return state.state == "heat"

    def _accumulate(self, now: datetime) -> None:
        """Add the elapsed heating time. Several climates count only once."""
        local = dt_util.as_local(now)
        today = local.date()
        last = self._last_tick

        if self._day != today:
            if last is not None and self._was_heating:
                midnight = dt_util.start_of_local_day(local)
                if last < midnight:
                    self._last_heat_day = self._day
                    last = midnight
            self._day = today
            self._heating_s = 0.0

        if last is not None and self._was_heating:
            elapsed = (now - last).total_seconds()
            if elapsed > 0:
                self._heating_s += min(elapsed, MAX_TICK_GAP)
                self._last_heat_day = today

        statuses = [self._heating_status(c) for c in self.climates]
        self._was_heating = any(s is True for s in statuses)
        self._last_tick = now

        # No readable climate means no information, not "no heating": do not
        # let a dead integration count as days without heating.
        if statuses and all(s is None for s in statuses):
            self._last_heat_day = today

    def idle_days(self, today: date) -> int:
        """Full days without heating. The current day is not over, so excluded."""
        if self._last_heat_day is None:
            return 0
        return max(0, (today - self._last_heat_day).days - 1)

    # ── season ───────────────────────────────────────────────────────────────
    def auto_allowed(self, to_winter: bool, month: int) -> bool:
        """Month guard: both periods share the two configured start months."""
        winter, summer = self.winter_start_month, self.summer_start_month
        if to_winter:
            return month_in_range(month, winter, summer)
        return month_in_range(month, summer, winter)

    def _apply_season(self, winter: bool, source: str, today: date) -> None:
        self.winter = winter
        self.source = source
        self.changed_at = dt_util.utcnow().isoformat()
        if winter:
            # Idle days count from now, or a manual switch to winter would be
            # undone at once by the heating-free months before it.
            self._last_heat_day = today

    async def async_set_winter(self, winter: bool) -> None:
        """Manual change: wins over the automation until the next day."""
        if winter == self.winter:
            return
        today = dt_util.now().date()
        self._apply_season(winter, SOURCE_MANUAL, today)
        self._manual_block_day = today
        await self._persist()
        self.async_update_listeners()
        self.async_notify_rooms()

    def _auto_target(self, today: date) -> bool | None:
        """The season to switch to automatically, None to stay as is."""
        if not self.climates or self._manual_block_day == today:
            return None
        if not self.winter:
            if self._heating_s >= self.heating_threshold_s and self.auto_allowed(
                True, today.month
            ):
                return True
            return None
        idle_days = self.summer_idle_days
        if (
            idle_days > 0
            and self.idle_days(today) >= idle_days
            and self.auto_allowed(False, today.month)
        ):
            return False
        return None

    async def _async_update_data(self) -> dict:
        now = dt_util.utcnow()
        self._accumulate(now)
        today = dt_util.as_local(now).date()
        heating_minutes = round(self._heating_s / 60, 1)
        idle_days = self.idle_days(today)

        target = self._auto_target(today) if self.hass.is_running else None
        if target is not None:
            self._apply_season(target, SOURCE_AUTO, today)
            await self._persist()
            self.hass.bus.async_fire(
                EVENT_ALERT,
                {
                    "entry_id": self.entry.entry_id,
                    "type": ALERT_SEASON,
                    "area_id": None,
                    "area_name": None,
                    "mode": "winter" if target else "summer",
                    "heating_minutes": heating_minutes,
                    "idle_days": idle_days,
                },
            )
            self.async_notify_rooms()
        else:
            self._store.async_delay_save(self._snapshot, SAVE_DELAY)

        return {
            "winter": self.winter,
            "heating_now": self._was_heating,
            "heating_minutes": heating_minutes,
            "idle_days": self.idle_days(today),
        }
