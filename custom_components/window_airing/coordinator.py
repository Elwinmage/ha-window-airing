"""Coordinator: discovery, trend, state memory, clim control, event firing."""
from __future__ import annotations

import logging
import time
from collections import deque
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    ALERT_AIRING,
    ALERT_RAIN,
    CLIMATE_OFF_STATES,
    CONF_AREA,
    CONF_DEVICE_CLASSES,
    CONF_EXTERIOR_TEMP,
    CONF_MANAGE_CLIM,
    CONF_OPEN_DELAY,
    CONF_OVERRIDE_CLIM,
    CONF_OVERRIDE_INDOOR,
    CONF_OVERRIDE_WINDOWS,
    CONF_RAIN_ALERT,
    CONF_RAIN_SENSOR,
    CONF_THRESHOLD,
    CONF_USE_TREND,
    CONF_WEATHER,
    CONF_WEATHER_RAIN_STATES,
    DEFAULT_DEVICE_CLASSES,
    DEFAULT_NOTIFY_DELAY,
    DEFAULT_OPEN_DELAY,
    DEFAULT_THRESHOLD,
    DEFAULT_WEATHER_RAIN_STATES,
    DOMAIN,
    EVENT_ALERT,
    TREND_MIN_SAMPLES,
    TREND_RISING_SLOPE,
    TREND_WINDOW,
    UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1


class WindowAiringCoordinator(DataUpdateCoordinator):
    """Per-room coordinator."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self.entry = entry
        self._store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}")

        # Discovered entity_ids.
        self.windows: list[str] = []
        self.indoor_sensors: list[str] = []
        self.climates: list[str] = []

        # Persisted state memory (replaces the old input_booleans).
        self._airing_sent = False
        self._rain_sent = False
        self._clim_memorized = False

        # Live notify delay (seconds), driven by the per-room `number` entity,
        # which restores its own stored value on start.
        self.notify_delay_s = DEFAULT_NOTIFY_DELAY

        # Trend samples: (monotonic_ts, indoor_avg_temp).
        self._trend: deque[tuple[float, float]] = deque()

        self._unsub_state = None
        self._unsub_registry = None
        self._unsub_interval = None

    # ── config helpers ───────────────────────────────────────────────────────
    @property
    def _cfg(self) -> dict:
        """Merged config: options override data."""
        return {**self.entry.data, **self.entry.options}

    @property
    def area_id(self) -> str:
        return self.entry.data[CONF_AREA]

    def _opt(self, key, default):
        return self._cfg.get(key, default)

    @property
    def device_info(self) -> dr.DeviceInfo:
        """One device per room; its name prefixes every entity name.

        NOTE: this device is intentionally NOT placed in the monitored area,
        otherwise its own temperature sensors would be picked up by discovery.
        """
        area = ar.async_get(self.hass).async_get_area(self.area_id)
        return dr.DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name=area.name if area else self.area_id,
            manufacturer="Window Airing",
            model="Room airing monitor",
        )

    # ── lifecycle ────────────────────────────────────────────────────────────
    async def async_setup(self) -> None:
        """Load persisted memory, discover entities, subscribe to changes."""
        stored = await self._store.async_load()
        if stored:
            self._airing_sent = stored.get("airing_sent", False)
            self._rain_sent = stored.get("rain_sent", False)
            self._clim_memorized = stored.get("clim_memorized", False)

        self._discover()
        self._subscribe()

        # Re-discover when the entity registry changes (entities added/moved
        # between areas, device_class edited...). Cheap and keeps us honest.
        self._unsub_registry = self.hass.bus.async_listen(
            er.EVENT_ENTITY_REGISTRY_UPDATED, self._handle_registry_update
        )
        self._unsub_interval = async_track_time_interval(
            self.hass, self._handle_interval, timedelta(seconds=UPDATE_INTERVAL)
        )

    async def async_shutdown(self) -> None:
        for unsub in (self._unsub_state, self._unsub_registry, self._unsub_interval):
            if unsub:
                unsub()
        await super().async_shutdown()

    async def _persist(self) -> None:
        await self._store.async_save(
            {
                "airing_sent": self._airing_sent,
                "rain_sent": self._rain_sent,
                "clim_memorized": self._clim_memorized,
            }
        )

    # ── discovery ────────────────────────────────────────────────────────────
    def _entities_in_area(self) -> list[str]:
        """Entity ids whose (own or device) area matches this room."""
        ent_reg = er.async_get(self.hass)
        dev_reg = dr.async_get(self.hass)
        result: list[str] = []
        for entity in ent_reg.entities.values():
            # Never discover our own calculated entities (their delta/indoor
            # sensors carry device_class temperature and would loop).
            if entity.platform == DOMAIN:
                continue
            area = entity.area_id
            if area is None and entity.device_id:
                device = dev_reg.async_get(entity.device_id)
                area = device.area_id if device else None
            if area == self.area_id:
                result.append(entity.entity_id)
        return result

    def _device_class(self, entity_id: str) -> str | None:
        """Prefer the live state device_class, fall back to the registry."""
        state = self.hass.states.get(entity_id)
        if state and state.attributes.get("device_class"):
            return state.attributes["device_class"]
        entry = er.async_get(self.hass).async_get(entity_id)
        if entry:
            return entry.device_class or entry.original_device_class
        return None

    @callback
    def _discover(self) -> None:
        override_w = self._opt(CONF_OVERRIDE_WINDOWS, [])
        override_i = self._opt(CONF_OVERRIDE_INDOOR, None)
        override_c = self._opt(CONF_OVERRIDE_CLIM, [])
        dcs = self._opt(CONF_DEVICE_CLASSES, DEFAULT_DEVICE_CLASSES)

        entities = self._entities_in_area()

        if override_w:
            self.windows = list(override_w)
        else:
            self.windows = [
                e
                for e in entities
                if e.startswith("binary_sensor.")
                and self._device_class(e) in dcs
            ]

        if override_i:
            self.indoor_sensors = [override_i]
        else:
            self.indoor_sensors = [
                e
                for e in entities
                if e.startswith("sensor.")
                and self._device_class(e) == "temperature"
            ]

        if override_c:
            self.climates = list(override_c)
        else:
            self.climates = [e for e in entities if e.startswith("climate.")]

        _LOGGER.debug(
            "%s discovery: windows=%s indoor=%s clim=%s",
            self.name, self.windows, self.indoor_sensors, self.climates,
        )

    # ── subscriptions ────────────────────────────────────────────────────────
    @callback
    def _subscribe(self) -> None:
        if self._unsub_state:
            self._unsub_state()
        tracked = set(self.windows) | set(self.indoor_sensors)
        rain_sensor = self._opt(CONF_RAIN_SENSOR, None)
        weather = self._opt(CONF_WEATHER, None)
        if rain_sensor:
            tracked.add(rain_sensor)
        if weather:
            tracked.add(weather)
        tracked.add(self.entry.data[CONF_EXTERIOR_TEMP])
        if tracked:
            self._unsub_state = async_track_state_change_event(
                self.hass, list(tracked), self._handle_state_event
            )

    @callback
    def _handle_registry_update(self, event: Event) -> None:
        self._discover()
        self._subscribe()
        self.hass.async_create_task(self.async_request_refresh())

    @callback
    def _handle_state_event(self, event: Event) -> None:
        self.hass.async_create_task(self.async_request_refresh())

    @callback
    def _handle_interval(self, _now) -> None:
        self.hass.async_create_task(self.async_request_refresh())

    # ── temperature & trend ──────────────────────────────────────────────────
    def _indoor_avg(self) -> float | None:
        vals: list[float] = []
        for e in self.indoor_sensors:
            state = self.hass.states.get(e)
            if state is None:
                continue
            try:
                vals.append(float(state.state))
            except (ValueError, TypeError):
                continue
        return round(sum(vals) / len(vals), 2) if vals else None

    def _sample_trend(self, indoor: float | None) -> None:
        if indoor is None:
            return
        now = time.monotonic()
        self._trend.append((now, indoor))
        cutoff = now - TREND_WINDOW
        while self._trend and self._trend[0][0] < cutoff:
            self._trend.popleft()

    def _trend_rising(self) -> bool:
        """Least-squares slope over the sample window (°C/s)."""
        if len(self._trend) < TREND_MIN_SAMPLES:
            return False
        n = len(self._trend)
        t0 = self._trend[0][0]
        xs = [t - t0 for t, _ in self._trend]
        ys = [v for _, v in self._trend]
        mx = sum(xs) / n
        my = sum(ys) / n
        denom = sum((x - mx) ** 2 for x in xs)
        if denom == 0:
            return False
        slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
        return slope > TREND_RISING_SLOPE

    # ── rain detection ───────────────────────────────────────────────────────
    def _is_raining(self) -> bool:
        rain_sensor = self._opt(CONF_RAIN_SENSOR, None)
        if rain_sensor and self.hass.states.is_state(rain_sensor, "on"):
            return True
        weather = self._opt(CONF_WEATHER, None)
        if weather:
            states = self._opt(CONF_WEATHER_RAIN_STATES, DEFAULT_WEATHER_RAIN_STATES)
            wstate = self.hass.states.get(weather)
            if wstate and wstate.state in states:
                return True
        return False

    # ── window state ─────────────────────────────────────────────────────────
    def _open_windows(self) -> list[str]:
        return [
            e for e in self.windows if self.hass.states.is_state(e, "on")
        ]

    def _open_delayed(self, delay_s: int) -> bool:
        """True if at least one window has been open continuously for delay_s."""
        threshold = dt_util.utcnow() - timedelta(seconds=delay_s)
        for e in self._open_windows():
            state = self.hass.states.get(e)
            if state and state.last_changed <= threshold:
                return True
        return False

    def _open_names(self) -> list[str]:
        names = []
        for e in self._open_windows():
            state = self.hass.states.get(e)
            names.append(state.name if state else e)
        return names

    # ── main evaluation ──────────────────────────────────────────────────────
    async def _async_update_data(self) -> dict:
        indoor = self._indoor_avg()
        self._sample_trend(indoor)

        outdoor_state = self.hass.states.get(self.entry.data[CONF_EXTERIOR_TEMP])
        try:
            outdoor = float(outdoor_state.state) if outdoor_state else None
        except (ValueError, TypeError):
            outdoor = None

        delta = None
        if indoor is not None and outdoor is not None:
            delta = round(indoor - outdoor, 2)

        open_windows = self._open_windows()
        data = {
            "indoor": indoor,
            "outdoor": outdoor,
            "delta": delta,
            "open_count": len(open_windows),
            # Clim uses the static option delay; notifications use the live number.
            "open_delayed_clim": self._open_delayed(
                self._opt(CONF_OPEN_DELAY, DEFAULT_OPEN_DELAY)
            ),
            "open_delayed_notify": self._open_delayed(self.notify_delay_s),
            "trend_rising": self._trend_rising(),
            "raining": self._is_raining(),
            "open_names": self._open_names(),
        }

        await self._evaluate_and_act(data)
        return data

    async def _evaluate_and_act(self, data: dict) -> None:
        dirty = False

        # ── Climate control (deterministic action; stays in the integration) ─
        if self._opt(CONF_MANAGE_CLIM, False) and self.climates:
            clim_running = any(
                self.hass.states.get(c)
                and self.hass.states.get(c).state not in CLIMATE_OFF_STATES
                for c in self.climates
            )
            if data["open_delayed_clim"] and not self._clim_memorized and clim_running:
                await self.hass.services.async_call(
                    "climate", "turn_off",
                    {"entity_id": self.climates}, blocking=False,
                )
                self._clim_memorized = True
                dirty = True
            elif data["open_count"] == 0 and self._clim_memorized:
                await self.hass.services.async_call(
                    "climate", "turn_on",
                    {"entity_id": self.climates}, blocking=False,
                )
                self._clim_memorized = False
                dirty = True

        # ── Airing alert (signal the human via event; dedup on the edge) ─────
        threshold = self._opt(CONF_THRESHOLD, DEFAULT_THRESHOLD)
        use_trend = self._opt(CONF_USE_TREND, False)
        airing_now = (
            data["open_delayed_notify"]
            and data["delta"] is not None
            and data["delta"] < threshold
            and (not use_trend or not data["trend_rising"])
        )
        if airing_now and not self._airing_sent:
            self._fire(ALERT_AIRING, data)
            self._airing_sent = True
            dirty = True
        elif data["open_count"] == 0 and self._airing_sent:
            self._airing_sent = False
            dirty = True

        # ── Rain alert ───────────────────────────────────────────────────────
        rain_now = (
            self._opt(CONF_RAIN_ALERT, False)
            and data["open_delayed_notify"]
            and data["raining"]
        )
        if rain_now and not self._rain_sent:
            self._fire(ALERT_RAIN, data)
            self._rain_sent = True
            dirty = True
        elif (data["open_count"] == 0 or not data["raining"]) and self._rain_sent:
            self._rain_sent = False
            dirty = True

        if dirty:
            await self._persist()

    @callback
    def _fire(self, alert_type: str, data: dict) -> None:
        area = ar.async_get(self.hass).async_get_area(self.area_id)
        self.hass.bus.async_fire(
            EVENT_ALERT,
            {
                "entry_id": self.entry.entry_id,
                "type": alert_type,
                "area_id": self.area_id,
                "area_name": area.name if area else self.area_id,
                "delta": data["delta"],
                "indoor": data["indoor"],
                "outdoor": data["outdoor"],
                "windows": data["open_names"],
            },
        )
