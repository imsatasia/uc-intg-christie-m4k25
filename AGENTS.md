# AGENTS.md

Guidance for working on this repo: a `ucapi`-based Unfolded Circle Remote 3 integration driver for
a Christie M 4K25 RGB projector. Built with the homelab's `uc3-integration` skill
(`skills/uc3-integration/`) -- read that skill's references before making structural changes here,
the same way this file expects.

## What this repo is, and isn't

This driver is **projection-only**. It has no idea what `PWR`, `SIN`, or `LAS+POWR` mean -- all of
that lives in the `christie-mseries` PyPI library (`github/py-christie-mseries/`), which this
driver depends on the same way the Home Assistant integration and the Control4 driver for the same
projector do. If a command doesn't behave the way you expect, the bug is almost always in
`device.py`'s use of the library, not in the library itself -- check
`github/py-christie-mseries/README.md` and `AGENTS.md` first.

## The one thing every entity handler assumes

`ChristieM4K25` (the library's client class) is **synchronous and opens a new TCP connection for
every call** -- it does not hold a persistent socket open. That's a deliberate choice in the
library (see its own `AGENTS.md`), not an oversight here. Every device interaction in this repo
therefore runs through `asyncio.to_thread()` (see `device.py`'s `_run`/`_blocking_snapshot`), and
there is nothing to reconnect on `EXIT_STANDBY` -- only the background poll loop needs to
stop/restart, which `ChristieDevice.suspend()`/`resume()` do.

**If you ever change the device layer to hold a persistent connection, you must add real
reconnect logic to `resume()`.** The current suspend/resume implementation is correct only because
there's no persistent connection to go stale.

## Why there's no `number` entity for brightness or lens position

`ucapi` (as of 0.7.0) has no `number` entity type -- the full list is `button`, `switch`,
`climate`, `cover`, `light`, `media_player`, `remote`, `sensor`, `ir_emitter`, `select`,
`voice_assistant` (confirmed against `github/uc3-remote/docs/core-api/doc/entities/`). Home
Assistant's integration for this same projector uses `number` entities for brightness and the four
lens motors; there is no direct UC3 equivalent. Rather than force a misleading fit (e.g. a `light`
entity whose on/off has no real meaning for a projector's laser, which was considered and rejected
-- see the git history / prior design discussion if this file predates it), these are exposed as
stepped `remote` simple-commands instead (`BRIGHTNESS_UP`/`DOWN`, `FOCUS_NEAR`/`FAR`, etc.), which
also matches how a physical remote naturally offers them. If ucapi ever adds a `number` entity
type, revisit this.

## Command-name-to-protocol dispatch is a single dict, and it's tested

`remote.py`'s `_build_command_map()` is a module-level function (not a method) mapping every
`const.SIMPLE_COMMANDS` entry to a zero-arg async callable. `tests/test_remote.py` asserts every
command has an entry and that every entry is callable -- this is exactly the kind of "large
hand-written dict" the `uc3-integration` skill's testing doc calls out as cheap and valuable to
test, because a typo here silently breaks one button with no error anywhere. If you add a new
simple command, add it to `const.SIMPLE_COMMANDS` **and** to `_build_command_map()` -- the test
will fail loudly if you forget the second half.

## Status codes: CONFLICT vs SERVER_ERROR

`SIN` (input), `ITP` (test pattern), and the lens motors are rejected by the projector itself with
"Disabled Control" while it's in standby -- this is a `ChristieError` from the library, not a
connection failure. Every command handler in this repo distinguishes the two via
`device.is_protocol_error(exc)`: a `ChristieError` maps to `StatusCodes.CONFLICT` (the device
understood and refused), anything else (`OSError`, `TimeoutError`, `ChristieConnectionError`) maps
to `StatusCodes.SERVER_ERROR` (couldn't reach the device at all). Keep this distinction when adding
new commands -- returning a bare `OK` on failure makes the remote assume success it didn't get.

## Device-identifier hygiene

Never commit a real projector IP, serial number, or MAC address here -- same rule as every other
skill/repo in this homelab. Use `192.0.2.0/24`-style placeholders, including in tests and this
file.
