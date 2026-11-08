"""
Select entities for the Christie M 4K25 RGB integration: input and test
pattern. ucapi's select entity has no cmd_handler-level restriction on option
text, so the library's own port-label/test-pattern names (INPUTS/
TEST_PATTERNS from py-christie-mseries) are used verbatim as the option
lists -- no separate label mapping to keep in sync.

The 3D mode and 3D sync output selects work the same way, using the library's
THREE_D_MODES/THREE_D_SYNC_OUTPUTS names. The projector refuses the sync output
outside the packed 3D modes ("Disabled Control"), which surfaces as a CONFLICT
like any other refused command rather than as a greyed-out entity -- ucapi's
select has no availability dimension besides the whole entity being UNAVAILABLE.

Input is also reachable via the media_player entity's select_source feature
(media_player.py) -- that's the more natural home for it, since select_source
is a first-class media_player concept for exactly this. This select entity is
a second, redundant control point for the same underlying SIN command, kept
for parity with the Home Assistant integration's dedicated input select and
for dashboards that want input and test pattern as two side-by-side select
widgets rather than one living inside the media_player card -- the same
"duplicate the control on purpose" reasoning switch.py uses for shutter and
LiteLOC against remote.py's simple-commands.

:license: MIT, see LICENSE for more details.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from christie_mseries import (
    INPUTS,
    TEST_PATTERNS,
    THREE_D_MODES,
    THREE_D_SYNC_OUTPUTS,
)
from ucapi import StatusCodes
from ucapi.select import Attributes, Commands, Select

from uc_intg_christie_m4k25.config import ChristieConfig, entity_id
from uc_intg_christie_m4k25.device import ChristieDevice, is_protocol_error

_LOG = logging.getLogger(__name__)

_INPUT_LIST = list(INPUTS.values())
_TEST_PATTERN_LIST = list(TEST_PATTERNS.values())
_THREE_D_MODE_LIST = list(THREE_D_MODES.values())
_THREE_D_SYNC_OUTPUT_LIST = list(THREE_D_SYNC_OUTPUTS.values())


class _ChristieSelect(Select):
    """Shared select_option command handling for a single-command select."""

    def __init__(
        self,
        identifier: str,
        name: str,
        options: list[str],
        current_option: str,
        apply: Callable[[str], Awaitable[None]],
    ) -> None:
        self._apply = apply

        super().__init__(
            identifier=identifier,
            name=name,
            attributes={
                Attributes.CURRENT_OPTION: current_option,
                Attributes.OPTIONS: options,
            },
            cmd_handler=self.command_handler,
        )

    async def command_handler(
        self, entity: Select, cmd_id: str, params: dict[str, Any] | None
    ) -> StatusCodes:
        """Handle entity_command messages for this entity.

        Only select_option is meaningful here -- select_first/last/next/
        previous would require knowing the current option first, which
        neither input nor test pattern gains much from cycling through
        (both lists are chosen by name, not position). Not implemented until
        a real use case shows up.
        """
        _LOG.info("Select command for %s: %s params: %s", self.id, cmd_id, params)
        if cmd_id != Commands.SELECT_OPTION:
            _LOG.debug("Ignoring unsupported command: %s", cmd_id)
            return StatusCodes.NOT_IMPLEMENTED
        if not params or "option" not in params:
            return StatusCodes.BAD_REQUEST
        try:
            await self._apply(params["option"])
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


class ChristieInputSelect(_ChristieSelect):
    """Selects the projector's main video input (SIN) by port label."""

    def __init__(self, config: ChristieConfig, device: ChristieDevice) -> None:
        super().__init__(
            identifier=entity_id("select", config.host, "input"),
            name=f"{config.name} Input",
            options=_INPUT_LIST,
            current_option=_INPUT_LIST[0],
            apply=device.select_input,
        )


class ChristieTestPatternSelect(_ChristieSelect):
    """Selects the projector's internal test pattern (ITP)."""

    def __init__(self, config: ChristieConfig, device: ChristieDevice) -> None:
        super().__init__(
            identifier=entity_id("select", config.host, "test_pattern"),
            name=f"{config.name} Test Pattern",
            options=_TEST_PATTERN_LIST,
            current_option=TEST_PATTERNS[0],
            apply=device.set_test_pattern,
        )


class ChristieThreeDModeSelect(_ChristieSelect):
    """Selects the 3D mode (TDM): Off, Auto Detect, Multi-Flash and the three
    packed formats."""

    def __init__(self, config: ChristieConfig, device: ChristieDevice) -> None:
        super().__init__(
            identifier=entity_id("select", config.host, "3d_mode"),
            name=f"{config.name} 3D Mode",
            options=_THREE_D_MODE_LIST,
            current_option=THREE_D_MODES[0],
            apply=device.set_3d_mode,
        )


class ChristieThreeDSyncOutputSelect(_ChristieSelect):
    """Selects where the 3D sync signal goes (TDO). Only accepted in the
    packed 3D modes."""

    def __init__(self, config: ChristieConfig, device: ChristieDevice) -> None:
        super().__init__(
            identifier=entity_id("select", config.host, "3d_sync_output"),
            name=f"{config.name} 3D Sync Output",
            options=_THREE_D_SYNC_OUTPUT_LIST,
            current_option=THREE_D_SYNC_OUTPUTS[0],
            apply=device.set_3d_sync_output,
        )
