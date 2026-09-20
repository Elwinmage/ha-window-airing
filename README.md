# Window Airing

Home Assistant integration that watches a **room** and tells you when it is no
longer useful to keep a window open — plus optional climate cut-off and a
rain alert. Everything is discovered from the room; you only pick the area and
the shared outdoor temperature sensor.

## Architecture

The integration does the **mechanism**, a bundled blueprint does the
**notification policy**:

- **Integration** (`custom_components/window_airing/`)
  - Discovers, per configured area: window contacts (by `device_class`),
    temperature sensors (averaged) and `climate` entities.
  - Computes the indoor/outdoor delta and an indoor temperature **trend**
    (replaces the manual Derivative helper).
  - Keeps its own **persisted state** (alert-sent, clim-memorised) — no
    `input_boolean` helpers to create.
  - **Acts** on the climate (turn off when open long enough, restore on close).
  - **Signals** via `window_airing_alert` events (`type: airing | rain`),
    de-duplicated on the edge.
  - Exposes entities: delta sensor, indoor-average sensor, and binary sensors
    *airing recommended*, *open in rain*, *temperature rising*.
- **Notification blueprint** (bundled, appears under "Window Airing")
  - Listens to the events and routes them to your `notify.*` service, with
    optional quiet hours. One instance for the whole home.

This split keeps user policy (who/how/when to notify) out of the integration.

## Install

1. HACS → custom repository → this repo, type *Integration*. Install, restart.
2. Settings → Devices & services → **Add integration** → *Window Airing*.
   Pick a room + the outdoor sensor. Repeat per room.
3. Tune each room in the integration's **Configure** (options): threshold,
   open delay, trend, climate, rain, and overrides.
4. Settings → Automations → **Create from blueprint** → *Surveillance fenêtre
   — Notifications*. Set your notify service (and quiet hours).

## Notes / to validate

- **Shelly BLU DoorWindow** `device_class`: check it in Developer tools →
  States. Adjust the "device_class" option if it is not window/door/opening.
- If a room has an irrelevant temperature sensor, use the indoor override.
- The `open_delay` gates both the climate cut-off and the airing alert.
- Rain uses the rain `binary_sensor` and/or the `weather` entity's current
  state. Forecast look-ahead (`weather.get_forecasts`) is a possible addition.
