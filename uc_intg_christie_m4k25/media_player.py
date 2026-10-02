"""
Media player entity for the Christie M 4K25 RGB integration.

Covers power and input selection -- the two concepts that map cleanly onto
the media_player feature list (see references/protocol-and-entities.md). The
rest of the projector's large, protocol-native command surface (shutter,
lens, brightness, test patterns, freeze, auto setup, LiteLoc) lives on the
remote entity instead, the same media_player + remote split uc-intg-madvr
uses for a single physical device.

:license: MIT, see LICENSE for more details.
"""

from __future__ import annotations

import logging
from typing import Any

from christie_mseries import INPUTS, PowerState
from ucapi import StatusCodes
from ucapi.media_player import (
    Attributes,
    Commands,
    DeviceClasses,
    Features,
    MediaPlayer,
    States,
)

from uc_intg_christie_m4k25.config import ChristieConfig, entity_id
from uc_intg_christie_m4k25.device import (
    ON_LIKE_POWER_STATES,
    ChristieDevice,
    is_protocol_error,
)

_LOG = logging.getLogger(__name__)

_INPUT_LIST = list(INPUTS.values())


def power_state_to_media_player_state(power_code: int) -> States:
    """Map the projector's PWR code to the media_player entity state."""
    if power_code in ON_LIKE_POWER_STATES:
        return States.ON
    if power_code == PowerState.STANDBY:
        return States.STANDBY
    return States.UNKNOWN


class ChristieMediaPlayer(MediaPlayer):
    """Representation of the Christie M 4K25 RGB as a media_player entity."""

    def __init__(self, config: ChristieConfig, device: ChristieDevice) -> None:
        self._config = config
        self._device = device

        super().__init__(
            identifier=entity_id("media_player", config.host),
            name=config.name,
            features=[Features.ON_OFF, Features.SELECT_SOURCE],
            attributes={
                Attributes.STATE: States.UNKNOWN,
                Attributes.SOURCE: "",
                Attributes.SOURCE_LIST: _INPUT_LIST,
            },
            device_class=DeviceClasses.TV,
            cmd_handler=self.command_handler,
        )

    async def command_handler(
        self, entity: MediaPlayer, cmd_id: str, params: dict[str, Any] | None
    ) -> StatusCodes:
        """Handle entity_command messages for this entity."""
        _LOG.info("Media player command: %s params: %s", cmd_id, params)
        try:
            if cmd_id == Commands.ON:
                await self._device.power_on()
                return StatusCodes.OK

            if cmd_id == Commands.OFF:
                await self._device.power_off()
                return StatusCodes.OK

            if cmd_id == Commands.SELECT_SOURCE:
                if not params or "source" not in params:
                    return StatusCodes.BAD_REQUEST
                await self._device.select_input(params["source"])
                return StatusCodes.OK

            _LOG.debug("Ignoring unsupported command: %s", cmd_id)
            return StatusCodes.OK
        except ValueError:
            return StatusCodes.BAD_REQUEST
        except Exception as exc:
            _LOG.error("Command %s failed: %s", cmd_id, exc)
            return (
                StatusCodes.CONFLICT
                if is_protocol_error(exc)
                else StatusCodes.SERVER_ERROR
            )
