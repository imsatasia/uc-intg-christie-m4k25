# uc-intg-christie-m4k25

An [Unfolded Circle Remote](https://www.unfoldedcircle.com/) integration driver for a
**Christie M 4K25 RGB** projector, built on its own Ethernet serial API (TCP 3002) via the
[`christie-mseries`](https://pypi.org/project/christie-mseries/) PyPI library -- the same client
used by this projector's Home Assistant integration
([christie-m4k25-homeassistant](https://github.com/imsatasia/christie-m4k25-homeassistant)) and
its Control4 driver ([christie-m4k25-control4](https://github.com/imsatasia/christie-m4k25-control4)).
This repo only turns that library's state into `ucapi` entities -- protocol details, TruLife+'s
partial API coverage, and every other device quirk live in the library itself.

## Installation

Two ways to run this integration -- pick one, or offer both:

### Docker (external driver, recommended for a home server/NAS setup)

Copy [`examples/docker-compose.yml`](examples/docker-compose.yml) (pulls the published image from
GHCR) to wherever you run Docker Compose, then:

```bash
docker compose up -d
```

To build the image from source instead, use the `docker-compose.yml` at the repo root:

```bash
docker compose build && docker compose up -d
```

`network_mode: host` is required either way -- mDNS discovery and the Remote's direct WebSocket
connection both need to see the real LAN, not a bridge-NAT'd container IP.

Then in the Remote's web-configurator: **Integrations -> Add new -> Discover** (it should appear
via mDNS within a few seconds), or add it manually with the container host's IP and port `9090`.

### On-remote (sandboxed custom driver)

Download the `.tar.gz` from the latest [Release](../../releases), then in the web-configurator:
**Integrations -> Add new -> Install custom**, and upload the archive.

Either way, complete setup with **Settings -> Devices & Services -> Add Integration -> Christie M
4K25 RGB** and enter the projector's IP. Give it a DHCP reservation -- this integration's entity
IDs are derived from the configured IP, so a changed IP means re-adding the integration.

## Entities

| Entity | Type | Notes |
|---|---|---|
| Christie M 4K25 RGB | `media_player` | Power on/off, input selection (`select_source`). `device_class: tv`. |
| Christie M 4K25 RGB | `remote` | Power on/off/toggle plus the full simple-command surface: shutter, freeze, auto setup, LiteLOC, brightness step, lens home/calibrate/nudge. Ships a "Christie Control" UI page. |
| Christie M 4K25 RGB Input | `select` | Main video input (SIN) by port label -- a second, redundant control point for the same command the media_player's `select_source` already offers, kept for a standalone input widget on a dashboard. |
| Christie M 4K25 RGB Test Pattern | `select` | Internal test patterns (ITP) -- refused while the projector is in standby. |
| Christie M 4K25 RGB 3D Mode | `select` | Off, Auto Detect, Multi-Flash 3D, Side-by-Side 3D, Top-and-Bottom 3D, Frame Packing 3D (TDM). Option names come from the library's `THREE_D_MODES`. |
| Christie M 4K25 RGB 3D Sync Output | `select` | To Emitter / To Next Input (TDO). The projector only accepts it in the packed modes (Side-by-Side, Top-and-Bottom, Frame Packing); elsewhere the command is refused with a conflict. |
| Christie M 4K25 RGB 3D Invert Eyes | `switch` | Swaps left and right (TDN). The opposite of the sync output: refused in the packed modes. |
| Christie M 4K25 RGB 3D Test Pattern | `switch` | The scrolling sync-check pattern (TDT). Works in every mode while the projector is on. |
| Christie M 4K25 RGB 3D Sync / 3D Darktime | `sensor` | Read-only: the projector's own wording, e.g. "Valid HDMI 3D Sync" and "Achieved" / "Not Achieved"; "N/A" with no 3D signal. |
| Christie M 4K25 RGB Shutter | `switch` | ON = shutter open (light reaches the screen). |
| Christie M 4K25 RGB LiteLOC | `switch` | Holds brightness/colour constant over time, trading off spare laser headroom. |
| Christie M 4K25 RGB Status | `sensor` | The projector's own power-state wording, e.g. "Standby Mode". |
| Christie M 4K25 RGB Input Name | `sensor` | The projector's own name for the active input (distinct from the port-label options offered by input selection). |
| Christie M 4K25 RGB Hours | `sensor` | Total elapsed operating hours, as the projector formats it. |
| Christie M 4K25 RGB Intake Temperature | `sensor` | `device_class: temperature`. |
| Christie M 4K25 RGB Alarm | `sensor` | `device_class: binary`, `unit: problem` -- there's no dedicated binary-sensor entity type in ucapi. |

There's no `number` entity type in ucapi (see `references/protocol-and-entities.md`'s full entity
list), so the lens motors (focus/zoom/horizontal/vertical shift) and laser brightness have no
continuous slider here -- unlike the Home Assistant integration's `number.*` entities. They're
reachable instead as stepped remote simple-commands (`FOCUS_NEAR`/`FOCUS_FAR`, `ZOOM_IN`/
`ZOOM_OUT`, `LENS_UP`/`DOWN`/`LEFT`/`RIGHT`, `BRIGHTNESS_UP`/`DOWN`), which also matches how a
physical remote would offer them.

The two numeric 3D controls are in the same position: the 3D sync delay and the 3D dark interval
are stepped with `3D_DELAY_UP`/`3D_DELAY_DOWN` (10 per press) and `3D_DARK_UP`/`3D_DARK_DOWN` (50
per press), clamped to the projector's own published ranges (−1000 to 1000 and 250 to 3000). The
projector publishes no unit for either, so they are raw steps. Both are only accepted in the packed
3D modes. `3D_OFF`, `3D_AUTO`, `3D_TEST_ON` and `3D_TEST_OFF` are shortcuts for the mode and test
pattern, and a second "Christie 3D" page on the remote entity puts all eight on screen.

## Development

Dependencies are managed with [uv](https://docs.astral.sh/uv/); `uv.lock` is committed, so
`uv sync`/`uv run` always use exactly the resolved versions CI and the Docker build use.

```bash
uv sync --group dev
uv run pytest
uv run black uc_intg_christie_m4k25 --check
uv run isort uc_intg_christie_m4k25/. --check
```

To add or bump a dependency, edit `pyproject.toml` and run `uv lock`, then commit the updated
`uv.lock` alongside it -- Dependabot also opens PRs for this automatically (see below).

## Design notes

- **Projection-only**: all protocol parsing lives in the `christie-mseries` library -- this repo
  turns its `Snapshot`/exceptions into `ucapi` entities and nothing more (see `device.py`).
- **Poll-only, short-lived connections**: `ChristieM4K25` is a synchronous, blocking-socket client
  that opens a new TCP connection per call rather than holding one open (matching the Home
  Assistant integration's coordinator). Every call here runs through `asyncio.to_thread`, and a
  background poll loop (10s) drives `entity_change` events, since the device doesn't push state.
- **Suspend/resume**: the remote suspends this driver's whole process during its own sleep. There's
  no persistent device connection to tear down (every call already opens and closes its own), so
  `ENTER_STANDBY`/`EXIT_STANDBY` stop and restart the poll loop instead, and `EXIT_STANDBY` forces
  an immediate re-sync rather than trusting the last snapshot from before the process was frozen.
- **Standby-refused commands**: `SIN` (input), `ITP` (test pattern), every 3D control, and the lens
  motors are rejected with "Disabled Control" while the projector is off; a `ChristieError` from the library
  maps to `StatusCodes.CONFLICT`, distinct from a connectivity failure (`SERVER_ERROR`).

## Layout

| Path | Purpose |
|---|---|
| `uc_intg_christie_m4k25/driver.py` | Entry point, `ucapi.IntegrationAPI` lifecycle wiring, snapshot-to-entity mapping |
| `uc_intg_christie_m4k25/device.py` | Device client: poll loop, commands, suspend/resume |
| `uc_intg_christie_m4k25/setup.py` | Setup flow: request input, test connection, persist config |
| `uc_intg_christie_m4k25/config.py` | JSON config file under `UC_CONFIG_HOME` |
| `uc_intg_christie_m4k25/{media_player,remote,select,switch,sensor}.py` | Entity platforms |
| `driver.json` | Manifest read by `ucapi.IntegrationAPI.init()` |
| `Dockerfile` / `docker-compose.yml` | External-driver deployment, built from source |
| `examples/docker-compose.yml` | Ready-to-run example pulling the published GHCR image |
| `.github/workflows/test.yml` | Runs on every push/PR to `main`: secret scan, pytest, black/isort checks |
| `.github/workflows/build.yml` | Tag-triggered release: builds the on-remote archive and the Docker image (gated on `secret-scan.yml`) |
| `.github/workflows/secret-scan.yml` | Reusable TruffleHog scan, called by both `test.yml` and `build.yml` |
| `.github/dependabot.yml` | Weekly PRs for GitHub Actions and `uv` (Python) dependencies |
| `uv.lock` | Resolved dependency versions -- committed, matching every other Python repo for this projector |

## Contributing

CI matches this author's other repos for the same projector (`py-christie-mseries`,
`christie-m4k25-homeassistant`, `christie-m4k25-control4`): a required TruffleHog secret scan gates
every build, and Dependabot keeps GitHub Actions and `uv` dependencies current. `main` is protected
-- changes go through a branch and pull request, with the `Secret scan / TruffleHog` check required.
Never commit a real projector IP, serial number, or MAC address; use `192.0.2.0/24`-style
placeholders in code, tests, and docs.
