"""
Device client for the Christie M 4K25 RGB integration.

Projection-only: all protocol parsing and device quirks (TruLife+'s partial
API coverage, the ERR-reply desync trap, LAS/WRP/NET needing subcodes, ...)
live in the standalone ``christie-mseries`` PyPI library
(github/py-christie-mseries), the same client used by the Home Assistant
integration and the Control4 driver for this projector. This module turns its
state into ucapi entity attributes and nothing more.

``ChristieM4K25`` is a synchronous, blocking-socket client that opens a new
TCP connection for every call rather than holding one open (see the Home
Assistant integration's coordinator.py, which does the same thing via
``hass.async_add_executor_job``) -- so every device interaction here runs
through ``asyncio.to_thread``.

Because there's no persistent connection, ENTER_STANDBY/EXIT_STANDBY has
nothing to physically tear down or reconnect. What *does* need to happen is
stopping and restarting the background poll loop: the remote suspends this
whole process during its own sleep, so the last-known Snapshot must be
treated as stale on wake, and the driver must re-sync rather than resume
polling on the old cadence as if no time had passed.

:license: MIT, see LICENSE for more details.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from christie_mseries import (
    ChristieConnectionError,
    ChristieError,
    ChristieM4K25,
    PowerState,
    Snapshot,
)

from uc_intg_christie_m4k25 import const

_LOG = logging.getLogger(__name__)

EVENT_UPDATE = "update"
EVENT_UNAVAILABLE = "unavailable"

# Raised by asyncio.to_thread(...) when the blocking call fails to reach the
# projector at all. ChristieError is different: the projector answered, but
# refused the request (e.g. "Disabled Control" for SIN/ITP/lens moves while
# in standby) -- that's a command-level CONFLICT, not a connectivity problem.
_CONNECTION_ERRORS = (OSError, TimeoutError, ChristieConnectionError)

# PowerState.WARMING/COOLING/AUTO_SHUTDOWN_* have no dedicated equivalent in
# either ucapi entity's state enum beyond "still powered" -- only the
# media_player entity has a STANDBY state to map PowerState.STANDBY onto.
# Shared by media_player.py and remote.py so both entities agree on it.
ON_LIKE_POWER_STATES = {PowerState.ON, PowerState.WARMING, PowerState.COOLING}


class ChristieDevice:
    """Poll-only device client with a suspend/resume-driven poll loop."""

    def __init__(self, host: str, port: int, loop: asyncio.AbstractEventLoop) -> None:
        self.host = host
        self.port = port
        self._loop = loop
        self.snapshot: Snapshot | None = None
        self.available = False
        self._listeners: list[Callable[[str, Any], None]] = []
        self._poll_task: asyncio.Task | None = None

    def on(self, callback: Callable[[str, Any], None]) -> None:
        """Register a callback for device events (EVENT_UPDATE/EVENT_UNAVAILABLE)."""
        self._listeners.append(callback)

    def _emit(self, event: str, data: Any) -> None:
        for callback in self._listeners:
            callback(event, data)

    def _client(self) -> ChristieM4K25:
        return ChristieM4K25(self.host, port=self.port, timeout=const.COMMAND_TIMEOUT)

    # -- Polling -----------------------------------------------------------

    def start_polling(self) -> None:
        """Start the background poll loop. Safe to call again after stop_polling()."""
        if self._poll_task is None:
            self._poll_task = self._loop.create_task(self._poll_loop())

    def stop_polling(self) -> None:
        """Stop the background poll loop."""
        if self._poll_task is not None:
            self._poll_task.cancel()
            self._poll_task = None

    async def _poll_loop(self) -> None:
        while True:
            await self.refresh()
            await asyncio.sleep(const.POLL_INTERVAL)

    async def refresh(self) -> None:
        """Poll the projector once and emit the result to listeners.

        A failed poll -- including the few seconds right after a power
        command where the projector accepts the TCP connection but answers
        nothing -- is reported as unavailable rather than raised, matching
        the "UNAVAILABLE, not OFF" distinction the protocol docs draw.
        """
        try:
            self.snapshot = await asyncio.to_thread(self._blocking_snapshot)
            self.available = True
            self._emit(EVENT_UPDATE, self.snapshot)
        except _CONNECTION_ERRORS as exc:
            _LOG.warning("Poll failed for %s:%d: %s", self.host, self.port, exc)
            self.available = False
            self._emit(EVENT_UNAVAILABLE, None)

    def _blocking_snapshot(self) -> Snapshot:
        with self._client() as projector:
            return projector.snapshot()

    # -- Suspend/resume ------------------------------------------------------

    async def suspend(self) -> None:
        """Called on ENTER_STANDBY: stop polling. There's no persistent
        connection to close -- every call already opens and closes its own."""
        _LOG.info("Suspending poll loop")
        self.stop_polling()

    async def resume(self) -> None:
        """Called on EXIT_STANDBY: re-sync immediately, then resume polling.

        The snapshot from before suspend cannot be trusted -- the projector
        may have been power-cycled, reconfigured, or simply drifted while
        this process was frozen.
        """
        _LOG.info("Resuming poll loop")
        await self.refresh()
        self.start_polling()

    # -- Commands --------------------------------------------------------
    #
    # Each wraps one short-lived connection. A command that changes state the
    # next poll would otherwise catch late (power, input, shutter, ...)
    # triggers an immediate refresh so the UI doesn't wait a full poll
    # interval; a command with no fast externally-visible effect worth
    # confirming (lens nudges) does not.

    async def _run(self, fn: Callable[[ChristieM4K25], None]) -> None:
        def _blocking() -> None:
            with self._client() as projector:
                fn(projector)

        await asyncio.to_thread(_blocking)

    async def power_on(self) -> None:
        await self._run(lambda p: p.power_on())
        await self.refresh()

    async def power_off(self) -> None:
        await self._run(lambda p: p.power_off())
        await self.refresh()

    async def select_input(self, source: str) -> None:
        await self._run(lambda p: p.select_input(source))
        await self.refresh()

    async def set_test_pattern(self, pattern: str) -> None:
        await self._run(lambda p: p.set_test_pattern(pattern))
        await self.refresh()

    async def open_shutter(self) -> None:
        await self._run(lambda p: p.open_shutter())
        await self.refresh()

    async def close_shutter(self) -> None:
        await self._run(lambda p: p.close_shutter())
        await self.refresh()

    async def set_liteloc(self, enabled: bool) -> None:
        await self._run(lambda p: p.set_liteloc(enabled))
        await self.refresh()

    async def auto_setup(self) -> None:
        await self._run(lambda p: p.auto_setup())

    async def home_lens(self) -> None:
        await self._run(lambda p: p.home_lens())

    async def calibrate_lens(self) -> None:
        await self._run(lambda p: p.calibrate_lens())

    async def freeze_toggle(self) -> None:
        def _toggle(p: ChristieM4K25) -> None:
            p.set_frozen(not p.is_frozen())

        await self._run(_toggle)

    async def step_brightness(self, delta_percent: float) -> None:
        def _step(p: ChristieM4K25) -> None:
            current = p.get_brightness()
            p.set_brightness(current + delta_percent)

        await self._run(_step)
        await self.refresh()

    async def step_focus(self, delta: int) -> None:
        await self._step_lens(
            lambda p: p.get_focus(), lambda p, v: p.set_focus(v), delta
        )

    async def step_zoom(self, delta: int) -> None:
        await self._step_lens(lambda p: p.get_zoom(), lambda p, v: p.set_zoom(v), delta)

    async def step_lens_horizontal(self, delta: int) -> None:
        await self._step_lens(
            lambda p: p.get_lens_horizontal(),
            lambda p, v: p.set_lens_horizontal(v),
            delta,
        )

    async def step_lens_vertical(self, delta: int) -> None:
        await self._step_lens(
            lambda p: p.get_lens_vertical(), lambda p, v: p.set_lens_vertical(v), delta
        )

    async def _step_lens(
        self,
        get_position: Callable[[ChristieM4K25], int],
        set_position: Callable[[ChristieM4K25, int], None],
        delta: int,
    ) -> None:
        def _step(p: ChristieM4K25) -> None:
            position = get_position(p)
            new_position = max(
                const.LENS_POSITION_MIN, min(const.LENS_POSITION_MAX, position + delta)
            )
            set_position(p, new_position)

        await self._run(_step)


def is_protocol_error(exc: Exception) -> bool:
    """True if `exc` is the projector refusing a command it understood
    (e.g. "Disabled Control" for SIN/ITP/lens writes while in standby),
    as opposed to a connectivity failure. Used by entity command handlers to
    pick between StatusCodes.CONFLICT and StatusCodes.SERVER_ERROR."""
    return isinstance(exc, ChristieError)
