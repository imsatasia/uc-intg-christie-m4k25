"""
Switch entities for the Christie M 4K25 RGB integration: shutter and
LiteLOC. Both are also reachable as remote.py simple_commands, for a physical
button mapping -- the same overlap between entities uc-intg-madvr uses for
one physical device's power state.

:license: MIT, see LICENSE for more details.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from ucapi import StatusCodes
from ucapi.switch import Attributes, Commands, Features, States, Switch

from uc_intg_christie_m4k25.config import ChristieConfig, entity_id
from uc_intg_christie_m4k25.device import ChristieDevice, is_protocol_error

_LOG = logging.getLogger(__name__)


class _ChristieSwitch(Switch):
    """Shared on/off command handling for a boolean device setting."""

    def __init__(
        self,
        identifier: str,
        name: str,
        turn_on: Callable[[], Awaitable[None]],
        turn_off: Callable[[], Awaitable[None]],
    ) -> None:
        self._turn_on = turn_on
        self._turn_off = turn_off

        super().__init__(
            identifier=identifier,
            name=name,
            features=[Features.ON_OFF, Features.TOGGLE],
            attributes={Attributes.STATE: States.UNKNOWN},
            cmd_handler=self.command_handler,
        )

    async def command_handler(
        self, entity: Switch, cmd_id: str, params: dict[str, Any] | None
    ) -> StatusCodes:
        _LOG.info("Switch command for %s: %s", self.id, cmd_id)
        try:
            if cmd_id == Commands.ON:
                await self._turn_on()
            elif cmd_id == Commands.OFF:
                await self._turn_off()
            elif cmd_id == Commands.TOGGLE:
                is_on = self.attributes.get(Attributes.STATE) == States.ON
                await (self._turn_off() if is_on else self._turn_on())
            else:
                _LOG.debug("Ignoring unsupported command: %s", cmd_id)
                return StatusCodes.OK
            return StatusCodes.OK
        except Exception as exc:
            _LOG.error("Command %s failed: %s", cmd_id, exc)
            return (
                StatusCodes.CONFLICT
                if is_protocol_error(exc)
                else StatusCodes.SERVER_ERROR
            )


class ChristieShutterSwitch(_ChristieSwitch):
    """ON = shutter open (light reaches the screen), OFF = shutter closed."""

    def __init__(self, config: ChristieConfig, device: ChristieDevice) -> None:
        super().__init__(
            identifier=entity_id("switch", config.host, "shutter"),
            name=f"{config.name} Shutter",
            turn_on=device.open_shutter,
            turn_off=device.close_shutter,
        )


class ChristieLiteLocSwitch(_ChristieSwitch):
    """LiteLOC holds brightness and colour constant over time by trading off
    spare laser headroom -- see py-christie-mseries's set_liteloc() docstring."""

    def __init__(self, config: ChristieConfig, device: ChristieDevice) -> None:
        super().__init__(
            identifier=entity_id("switch", config.host, "liteloc"),
            name=f"{config.name} LiteLOC",
            turn_on=lambda: device.set_liteloc(True),
            turn_off=lambda: device.set_liteloc(False),
        )
