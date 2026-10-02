"""
Setup flow handler for the Christie M 4K25 RGB integration.

driver.json's setup_data_schema only defines the first screen; everything
after is driven dynamically from here. See
references/driver-lifecycle-and-setup.md for the message sequence.

:license: MIT, see LICENSE for more details.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from ucapi import IntegrationSetupError, SetupAction, SetupComplete, SetupDriver
from ucapi.api_definitions import (
    AbortDriverSetup,
    DriverSetupRequest,
    RequestUserInput,
    SetupError,
    UserDataResponse,
)

from uc_intg_christie_m4k25 import const
from uc_intg_christie_m4k25.config import ChristieConfig
from uc_intg_christie_m4k25.device import ChristieDevice

_LOG = logging.getLogger(__name__)


class ChristieSetup:
    """Setup flow manager for the Christie M 4K25 RGB integration."""

    def __init__(
        self,
        config: ChristieConfig,
        on_setup_complete: Callable[[], Awaitable[None]],
    ) -> None:
        self._config = config
        self._on_setup_complete = on_setup_complete

    async def handle_setup(self, msg: SetupDriver) -> SetupAction:
        """Handle setup flow messages."""
        if isinstance(msg, DriverSetupRequest):
            return RequestUserInput(
                title={"en": "Christie M 4K25 RGB Connection"},
                settings=[
                    {
                        "id": "host",
                        "label": {"en": "IP Address"},
                        "field": {"text": {"value": self._config.host or ""}},
                    },
                    {
                        "id": "port",
                        "label": {"en": "Serial API Port"},
                        "field": {"number": {"value": self._config.port}},
                    },
                ],
            )

        if isinstance(msg, UserDataResponse):
            action = await self._handle_user_input(msg.input_values)
            if isinstance(action, SetupComplete) and self._on_setup_complete:
                await self._on_setup_complete()
            return action

        if isinstance(msg, AbortDriverSetup):
            _LOG.info("Setup aborted by user")
            return SetupError(IntegrationSetupError.OTHER)

        _LOG.error("Unknown setup message type: %s", type(msg).__name__)
        return SetupError(IntegrationSetupError.OTHER)

    async def _handle_user_input(self, input_values: dict[str, str]) -> SetupAction:
        """Validate input and test a real connection before accepting it."""
        host = input_values.get("host", "").strip()
        if not host:
            return SetupError(IntegrationSetupError.NOT_FOUND)

        try:
            port = int(input_values.get("port", str(const.DEFAULT_PORT)))
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            return SetupError(IntegrationSetupError.OTHER)

        # Save immediately: survives a process restart on retry (see
        # references/driver-lifecycle-and-setup.md).
        self._config.set_config(host, port)

        loop = asyncio.get_running_loop()
        test_device = ChristieDevice(host, port, loop)
        # snapshot() only reads (PWR/status groups/lens positions), which the
        # projector answers even in standby -- unlike SIN/ITP/lens *writes*,
        # which it rejects with "Disabled Control" until powered on. So this
        # is a valid connection test regardless of the projector's current
        # power state.
        await test_device.refresh()
        if not test_device.available:
            return SetupError(IntegrationSetupError.CONNECTION_REFUSED)
        return SetupComplete()
