"""
Remote entity for the Christie M 4K25 RGB integration.

The projector's protocol-native command set (shutter, lens motors, LiteLoc,
brightness, freeze, auto setup) doesn't map onto any single ucapi feature
list, and there's no ucapi `number` entity type for the lens/brightness
values anyway -- so this remote entity's simple_commands is the natural home
for all of it (see references/protocol-and-entities.md: "often a better fit
than media_player for ... a video processor with a large, protocol-native
command set"). Power lives here too, alongside the media_player entity, the
same overlap uc-intg-madvr uses for one physical device.

There is no relative-move command in the wire protocol for the lens motors
(FCS/ZOM/LHO/LVO) -- only absolute positions -- so the nudge commands here
read the current position and write position +/- const.LENS_STEP; see
device.py's step_focus/step_zoom/step_lens_horizontal/step_lens_vertical.

:license: MIT, see LICENSE for more details.
"""

from __future__ import annotations

import logging
from typing import Any

from ucapi import StatusCodes
from ucapi.remote import Attributes, Commands, Features, Remote, States
from ucapi.ui import Size, UiPage, create_ui_text

from uc_intg_christie_m4k25 import const
from uc_intg_christie_m4k25.config import ChristieConfig, entity_id
from uc_intg_christie_m4k25.device import (
    ON_LIKE_POWER_STATES,
    ChristieDevice,
    is_protocol_error,
)

_LOG = logging.getLogger(__name__)


def power_state_to_remote_state(power_code: int) -> States:
    """Map the projector's PWR code to the remote entity state (ON/OFF only
    -- unlike media_player, the remote entity has no STANDBY state)."""
    return States.ON if power_code in ON_LIKE_POWER_STATES else States.OFF


class ChristieRemote(Remote):
    """Representation of the Christie M 4K25 RGB as a remote entity."""

    def __init__(self, config: ChristieConfig, device: ChristieDevice) -> None:
        self._config = config
        self._device = device
        self._command_map = _build_command_map(device)

        super().__init__(
            identifier=entity_id("remote", config.host),
            name=config.name,
            features=[Features.ON_OFF, Features.TOGGLE, Features.SEND_CMD],
            attributes={Attributes.STATE: States.UNKNOWN},
            simple_commands=list(const.SIMPLE_COMMANDS),
            ui_pages=[self._create_control_page()],
            cmd_handler=self.command_handler,
        )

    def _create_control_page(self) -> UiPage:
        page = UiPage(
            page_id="christie_control", name="Christie Control", grid=Size(4, 8)
        )
        page.add(create_ui_text("Shutter Open", 0, 0, cmd=const.CMD_SHUTTER_OPEN))
        page.add(create_ui_text("Shutter Close", 1, 0, cmd=const.CMD_SHUTTER_CLOSE))
        page.add(create_ui_text("Freeze", 2, 0, cmd=const.CMD_FREEZE_TOGGLE))
        page.add(create_ui_text("Auto Setup", 3, 0, cmd=const.CMD_AUTO_SETUP))

        page.add(create_ui_text("Bright +", 0, 1, cmd=const.CMD_BRIGHTNESS_UP))
        page.add(create_ui_text("Bright -", 1, 1, cmd=const.CMD_BRIGHTNESS_DOWN))
        page.add(create_ui_text("LiteLOC On", 2, 1, cmd=const.CMD_LITELOC_ON))
        page.add(create_ui_text("LiteLOC Off", 3, 1, cmd=const.CMD_LITELOC_OFF))

        page.add(create_ui_text("Focus Near", 0, 2, cmd=const.CMD_FOCUS_NEAR))
        page.add(create_ui_text("Focus Far", 1, 2, cmd=const.CMD_FOCUS_FAR))
        page.add(create_ui_text("Zoom In", 2, 2, cmd=const.CMD_ZOOM_IN))
        page.add(create_ui_text("Zoom Out", 3, 2, cmd=const.CMD_ZOOM_OUT))

        page.add(create_ui_text("Lens Up", 1, 3, cmd=const.CMD_LENS_UP))
        page.add(create_ui_text("Lens Left", 0, 4, cmd=const.CMD_LENS_LEFT))
        page.add(create_ui_text("Lens Home", 1, 4, cmd=const.CMD_LENS_HOME))
        page.add(create_ui_text("Lens Right", 2, 4, cmd=const.CMD_LENS_RIGHT))
        page.add(create_ui_text("Lens Down", 1, 5, cmd=const.CMD_LENS_DOWN))
        page.add(create_ui_text("Calibrate Lens", 2, 5, cmd=const.CMD_LENS_CALIBRATE))
        return page

    async def command_handler(
        self, entity: Remote, cmd_id: str, params: dict[str, Any] | None = None
    ) -> StatusCodes:
        """Handle entity_command messages for this entity."""
        _LOG.info("Remote command: %s params: %s", cmd_id, params)
        try:
            if cmd_id == Commands.ON:
                await self._device.power_on()
                return StatusCodes.OK

            if cmd_id in (Commands.OFF, Commands.TOGGLE):
                if cmd_id == Commands.TOGGLE:
                    is_on = (
                        self._device.snapshot is not None
                        and self._device.snapshot.is_on
                    )
                    await (
                        self._device.power_off() if is_on else self._device.power_on()
                    )
                else:
                    await self._device.power_off()
                return StatusCodes.OK

            if cmd_id == Commands.SEND_CMD:
                if not params or "command" not in params:
                    return StatusCodes.BAD_REQUEST
                return await self._send_simple_command(params["command"])

            if cmd_id == Commands.SEND_CMD_SEQUENCE:
                if not params or "sequence" not in params:
                    return StatusCodes.BAD_REQUEST
                for command in params["sequence"]:
                    status = await self._send_simple_command(command)
                    if status != StatusCodes.OK:
                        return status
                return StatusCodes.OK

            _LOG.debug("Ignoring unsupported command: %s", cmd_id)
            return StatusCodes.OK
        except Exception as exc:
            _LOG.error("Command %s failed: %s", cmd_id, exc)
            return (
                StatusCodes.CONFLICT
                if is_protocol_error(exc)
                else StatusCodes.SERVER_ERROR
            )

    async def _send_simple_command(self, command: str) -> StatusCodes:
        """Dispatch one of const.SIMPLE_COMMANDS to the device client."""
        handler = self._command_map.get(command)
        if handler is None:
            _LOG.debug("Unknown simple command: %s", command)
            return StatusCodes.NOT_IMPLEMENTED
        await handler()
        return StatusCodes.OK


def _build_command_map(device: ChristieDevice) -> dict[str, Any]:
    """Map each of const.SIMPLE_COMMANDS to a zero-arg async callable on
    `device`. A module-level function (not a method) so tests can assert
    every entry in const.SIMPLE_COMMANDS has a handler here without
    constructing a full ChristieRemote -- see tests/test_remote.py."""
    return {
        const.CMD_SHUTTER_OPEN: device.open_shutter,
        const.CMD_SHUTTER_CLOSE: device.close_shutter,
        const.CMD_FREEZE_TOGGLE: device.freeze_toggle,
        const.CMD_AUTO_SETUP: device.auto_setup,
        const.CMD_LITELOC_ON: lambda: device.set_liteloc(True),
        const.CMD_LITELOC_OFF: lambda: device.set_liteloc(False),
        const.CMD_BRIGHTNESS_UP: lambda: device.step_brightness(const.BRIGHTNESS_STEP),
        const.CMD_BRIGHTNESS_DOWN: lambda: device.step_brightness(
            -const.BRIGHTNESS_STEP
        ),
        const.CMD_LENS_HOME: device.home_lens,
        const.CMD_LENS_CALIBRATE: device.calibrate_lens,
        const.CMD_FOCUS_NEAR: lambda: device.step_focus(-const.LENS_STEP),
        const.CMD_FOCUS_FAR: lambda: device.step_focus(const.LENS_STEP),
        const.CMD_ZOOM_IN: lambda: device.step_zoom(const.LENS_STEP),
        const.CMD_ZOOM_OUT: lambda: device.step_zoom(-const.LENS_STEP),
        const.CMD_LENS_UP: lambda: device.step_lens_vertical(const.LENS_STEP),
        const.CMD_LENS_DOWN: lambda: device.step_lens_vertical(-const.LENS_STEP),
        const.CMD_LENS_LEFT: lambda: device.step_lens_horizontal(-const.LENS_STEP),
        const.CMD_LENS_RIGHT: lambda: device.step_lens_horizontal(const.LENS_STEP),
    }
