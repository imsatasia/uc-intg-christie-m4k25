"""Tests for the 3D entities and commands -- no network, no real projector.

The behaviour being pinned down was read off a real M 4K25 RGB: the projector
refuses the sync output, sync delay and dark interval outside the packed 3D
modes and the eye inversion inside them, and silently clamps out-of-range
values, so the driver clamps before writing.
"""

import tempfile
import unittest
from unittest import mock

import ucapi
from christie_mseries import (
    THREE_D_DARK_INTERVAL_MAX,
    THREE_D_DARK_INTERVAL_MIN,
    THREE_D_EMITTER_DELAY_MAX,
    THREE_D_EMITTER_DELAY_MIN,
    THREE_D_MODES,
    THREE_D_SYNC_OUTPUTS,
    ChristieError,
    Snapshot,
)
from ucapi import StatusCodes

from uc_intg_christie_m4k25 import const, driver
from uc_intg_christie_m4k25.config import ChristieConfig
from uc_intg_christie_m4k25.device import ChristieDevice
from uc_intg_christie_m4k25.select import (
    ChristieThreeDModeSelect,
    ChristieThreeDSyncOutputSelect,
)
from uc_intg_christie_m4k25.sensor import (
    build_three_d_darktime_sensor,
    build_three_d_sync_sensor,
)
from uc_intg_christie_m4k25.switch import (
    ChristieThreeDInvertSwitch,
    ChristieThreeDTestPatternSwitch,
)


def _config() -> ChristieConfig:
    with tempfile.TemporaryDirectory() as tmp:
        config = ChristieConfig(config_dir=tmp)
        config.set_config("192.0.2.50", 3002, "Test Projector")
        return config


def _snapshot(**overrides) -> Snapshot:
    fields = dict(
        power="On",
        power_code=1,
        is_on=True,
        in_transition=False,
        shutter_open=True,
        input=3,
        input_name="One-Port VOM-HDMI",
        input_label="HDMI 2.1 Port 3",
        inputs=["HDMI 2.1 Port 3"],
        input_map={"HDMI 2.1 Port 3": 3},
        hours="3:14 (h:m)",
        model="Christie M 4K25 RGB",
        serial="12345",
        alarms=0,
        brightness=70.0,
        liteloc=True,
        test_pattern="Off",
        test_patterns=["Off"],
        test_pattern_map={"Off": 0},
        focus=0,
        zoom=0,
        lens_horizontal=0,
        lens_vertical=0,
    )
    fields.update(overrides)
    return Snapshot(**fields)


class FakeProjector:
    """Records calls and reads back what was last written, like the real one."""

    def __init__(self, delay=0, dark=1500):
        self.delay = delay
        self.dark = dark
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_3d_emitter_delay(self):
        return self.delay

    def set_3d_emitter_delay(self, value):
        self.calls.append(("delay", value))
        self.delay = value

    def get_3d_dark_interval(self):
        return self.dark

    def set_3d_dark_interval(self, value):
        self.calls.append(("dark", value))
        self.dark = value

    def set_3d_mode(self, mode):
        self.calls.append(("mode", mode))

    def set_3d_sync_output(self, output):
        self.calls.append(("sync_output", output))

    def set_3d_input_inverted(self, inverted):
        self.calls.append(("invert", inverted))

    def enable_3d_test_pattern(self):
        self.calls.append(("test_pattern", True))

    def disable_3d_test_pattern(self):
        self.calls.append(("test_pattern", False))


def _device(projector: FakeProjector) -> ChristieDevice:
    device = ChristieDevice("192.0.2.50", 3002, mock.Mock())
    device._client = lambda: projector  # type: ignore[method-assign]
    device.refresh = mock.AsyncMock()  # type: ignore[method-assign]
    return device


class TestDeviceCommands(unittest.IsolatedAsyncioTestCase):
    async def test_mode_and_sync_output_pass_the_names_through(self):
        projector = FakeProjector()
        device = _device(projector)
        await device.set_3d_mode("Side-by-Side 3D")
        await device.set_3d_sync_output("To Next Input")
        self.assertEqual(
            projector.calls,
            [("mode", "Side-by-Side 3D"), ("sync_output", "To Next Input")],
        )
        self.assertEqual(device.refresh.await_count, 2)

    async def test_switches(self):
        projector = FakeProjector()
        device = _device(projector)
        await device.set_3d_input_inverted(True)
        await device.set_3d_test_pattern(True)
        await device.set_3d_test_pattern(False)
        self.assertEqual(
            projector.calls,
            [("invert", True), ("test_pattern", True), ("test_pattern", False)],
        )

    async def test_delay_step_moves_from_the_current_value(self):
        projector = FakeProjector(delay=100)
        await _device(projector).step_3d_delay(10)
        self.assertEqual(projector.calls, [("delay", 110)])

    async def test_delay_steps_negative_too(self):
        projector = FakeProjector(delay=-5)
        await _device(projector).step_3d_delay(-10)
        self.assertEqual(projector.calls, [("delay", -15)])

    async def test_delay_is_clamped_at_both_ends(self):
        projector = FakeProjector(delay=THREE_D_EMITTER_DELAY_MAX - 3)
        await _device(projector).step_3d_delay(10)
        self.assertEqual(projector.calls, [("delay", THREE_D_EMITTER_DELAY_MAX)])
        projector = FakeProjector(delay=THREE_D_EMITTER_DELAY_MIN + 3)
        await _device(projector).step_3d_delay(-10)
        self.assertEqual(projector.calls, [("delay", THREE_D_EMITTER_DELAY_MIN)])

    async def test_dark_interval_step_and_clamp(self):
        projector = FakeProjector(dark=1500)
        await _device(projector).step_3d_dark_interval(50)
        self.assertEqual(projector.calls, [("dark", 1550)])
        projector = FakeProjector(dark=THREE_D_DARK_INTERVAL_MAX - 10)
        await _device(projector).step_3d_dark_interval(50)
        self.assertEqual(projector.calls, [("dark", THREE_D_DARK_INTERVAL_MAX)])
        projector = FakeProjector(dark=THREE_D_DARK_INTERVAL_MIN + 10)
        await _device(projector).step_3d_dark_interval(-50)
        self.assertEqual(projector.calls, [("dark", THREE_D_DARK_INTERVAL_MIN)])

    async def test_a_step_refreshes_so_the_entities_follow(self):
        device = _device(FakeProjector())
        await device.step_3d_delay(10)
        await device.step_3d_dark_interval(50)
        self.assertEqual(device.refresh.await_count, 2)


class TestSelects(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.device = mock.AsyncMock()
        self.mode = ChristieThreeDModeSelect(_config(), self.device)
        self.output = ChristieThreeDSyncOutputSelect(_config(), self.device)

    def test_options_are_the_librarys_names_and_ids_are_stable(self):
        self.assertEqual(
            self.mode.attributes[ucapi.select.Attributes.OPTIONS],
            list(THREE_D_MODES.values()),
        )
        self.assertEqual(
            self.output.attributes[ucapi.select.Attributes.OPTIONS],
            list(THREE_D_SYNC_OUTPUTS.values()),
        )
        self.assertEqual(self.mode.id, "select.christie_m4k25_192_0_2_50_3d_mode")
        self.assertEqual(
            self.output.id, "select.christie_m4k25_192_0_2_50_3d_sync_output"
        )

    async def _select(self, entity, option):
        return await entity.command_handler(
            entity, ucapi.select.Commands.SELECT_OPTION, {"option": option}
        )

    async def test_selecting_a_mode_calls_the_device_with_the_name(self):
        self.assertEqual(
            await self._select(self.mode, "Frame Packing 3D"), StatusCodes.OK
        )
        self.device.set_3d_mode.assert_awaited_once_with("Frame Packing 3D")

    async def test_selecting_a_sync_output(self):
        self.assertEqual(await self._select(self.output, "To Emitter"), StatusCodes.OK)
        self.device.set_3d_sync_output.assert_awaited_once_with("To Emitter")

    async def test_an_unknown_option_is_a_bad_request(self):
        self.device.set_3d_mode.side_effect = ValueError("Unknown 3D mode")
        self.assertEqual(
            await self._select(self.mode, "Native 3D"), StatusCodes.BAD_REQUEST
        )

    async def test_a_projector_refusal_is_a_conflict(self):
        self.device.set_3d_sync_output.side_effect = ChristieError(
            105, "TDO: Disabled Control"
        )
        self.assertEqual(
            await self._select(self.output, "To Emitter"), StatusCodes.CONFLICT
        )

    async def test_losing_the_projector_is_a_server_error(self):
        self.device.set_3d_mode.side_effect = TimeoutError()
        self.assertEqual(await self._select(self.mode, "Off"), StatusCodes.SERVER_ERROR)

    async def test_a_missing_option_is_a_bad_request(self):
        result = await self.mode.command_handler(
            self.mode, ucapi.select.Commands.SELECT_OPTION, {}
        )
        self.assertEqual(result, StatusCodes.BAD_REQUEST)


class TestSwitches(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.device = mock.AsyncMock()
        self.invert = ChristieThreeDInvertSwitch(_config(), self.device)
        self.pattern = ChristieThreeDTestPatternSwitch(_config(), self.device)

    def test_ids_are_stable(self):
        self.assertEqual(self.invert.id, "switch.christie_m4k25_192_0_2_50_3d_invert")
        self.assertEqual(
            self.pattern.id, "switch.christie_m4k25_192_0_2_50_3d_test_pattern"
        )

    async def test_invert_on_and_off(self):
        await self.invert.command_handler(self.invert, ucapi.switch.Commands.ON, None)
        self.device.set_3d_input_inverted.assert_awaited_with(True)
        await self.invert.command_handler(self.invert, ucapi.switch.Commands.OFF, None)
        self.device.set_3d_input_inverted.assert_awaited_with(False)

    async def test_test_pattern_on_and_off(self):
        await self.pattern.command_handler(self.pattern, ucapi.switch.Commands.ON, None)
        self.device.set_3d_test_pattern.assert_awaited_with(True)
        await self.pattern.command_handler(
            self.pattern, ucapi.switch.Commands.OFF, None
        )
        self.device.set_3d_test_pattern.assert_awaited_with(False)

    async def test_toggle_follows_the_current_state(self):
        self.invert.attributes[ucapi.switch.Attributes.STATE] = ucapi.switch.States.ON
        await self.invert.command_handler(
            self.invert, ucapi.switch.Commands.TOGGLE, None
        )
        self.device.set_3d_input_inverted.assert_awaited_with(False)

    async def test_a_projector_refusal_is_a_conflict(self):
        self.device.set_3d_input_inverted.side_effect = ChristieError(
            105, "TDN: Disabled Control"
        )
        result = await self.invert.command_handler(
            self.invert, ucapi.switch.Commands.ON, None
        )
        self.assertEqual(result, StatusCodes.CONFLICT)


class TestSensors(unittest.TestCase):
    def test_ids_and_names(self):
        sync = build_three_d_sync_sensor(_config())
        darktime = build_three_d_darktime_sensor(_config())
        self.assertEqual(sync.id, "sensor.christie_m4k25_192_0_2_50_3d_sync")
        self.assertEqual(darktime.id, "sensor.christie_m4k25_192_0_2_50_3d_darktime")
        self.assertEqual(sync.name["en"], "Test Projector 3D Sync")


class TestSnapshotReachesTheEntities(unittest.IsolatedAsyncioTestCase):
    """driver._apply_snapshot() is the only thing that moves the 3D state from
    a poll onto the entities."""

    def setUp(self):
        config = _config()
        device = mock.AsyncMock()
        self.entities = {
            "_three_d_mode_select": ChristieThreeDModeSelect(config, device),
            "_three_d_sync_output_select": ChristieThreeDSyncOutputSelect(
                config, device
            ),
            "_three_d_invert_switch": ChristieThreeDInvertSwitch(config, device),
            "_three_d_test_pattern_switch": ChristieThreeDTestPatternSwitch(
                config, device
            ),
            "_three_d_sync_sensor": build_three_d_sync_sensor(config),
            "_three_d_darktime_sensor": build_three_d_darktime_sensor(config),
        }
        self.updates = {}
        api = mock.MagicMock()
        api.set_device_state = mock.AsyncMock()
        api.configured_entities.contains.return_value = True
        api.configured_entities.update_attributes.side_effect = (
            lambda entity_id, attributes: self.updates.setdefault(entity_id, {}).update(
                attributes
            )
        )
        patches = [mock.patch.object(driver, "api", api)] + [
            mock.patch.object(driver, name, entity)
            for name, entity in self.entities.items()
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def _attrs(self, name):
        return self.updates[self.entities[name].id]

    async def test_a_packed_mode_snapshot_is_applied(self):
        await driver._apply_snapshot(
            _snapshot(
                three_d_mode="Side-by-Side 3D",
                three_d_sync_output="To Next Input",
                three_d_input_inverted=True,
                three_d_test_pattern=True,
                three_d_sync="Valid HDMI 3D Sync",
                three_d_darktime="Not Achieved",
            )
        )
        self.assertEqual(
            self._attrs("_three_d_mode_select")[ucapi.select.Attributes.CURRENT_OPTION],
            "Side-by-Side 3D",
        )
        self.assertEqual(
            self._attrs("_three_d_sync_output_select")[
                ucapi.select.Attributes.CURRENT_OPTION
            ],
            "To Next Input",
        )
        self.assertEqual(
            self._attrs("_three_d_invert_switch")[ucapi.switch.Attributes.STATE],
            ucapi.switch.States.ON,
        )
        self.assertEqual(
            self._attrs("_three_d_test_pattern_switch")[ucapi.switch.Attributes.STATE],
            ucapi.switch.States.ON,
        )
        self.assertEqual(
            self._attrs("_three_d_sync_sensor")[ucapi.sensor.Attributes.VALUE],
            "Valid HDMI 3D Sync",
        )
        self.assertEqual(
            self._attrs("_three_d_darktime_sensor")[ucapi.sensor.Attributes.VALUE],
            "Not Achieved",
        )

    async def test_the_idle_snapshot_turns_the_switches_off(self):
        await driver._apply_snapshot(_snapshot())
        for name in ("_three_d_invert_switch", "_three_d_test_pattern_switch"):
            self.assertEqual(
                self._attrs(name)[ucapi.switch.Attributes.STATE],
                ucapi.switch.States.OFF,
                name,
            )
        self.assertEqual(
            self._attrs("_three_d_mode_select")[ucapi.select.Attributes.CURRENT_OPTION],
            "Off",
        )

    async def test_a_failed_poll_marks_every_3d_entity_unavailable(self):
        await driver._apply_unavailable()
        for name in ("_three_d_invert_switch", "_three_d_test_pattern_switch"):
            self.assertEqual(
                self._attrs(name)[ucapi.switch.Attributes.STATE], "UNAVAILABLE", name
            )
        for name in ("_three_d_sync_sensor", "_three_d_darktime_sensor"):
            self.assertEqual(
                self._attrs(name)[ucapi.sensor.Attributes.STATE], "UNAVAILABLE", name
            )
        for name in ("_three_d_mode_select", "_three_d_sync_output_select"):
            self.assertEqual(
                self._attrs(name)[ucapi.select.Attributes.STATE], "UNAVAILABLE", name
            )


class TestSimpleCommands(unittest.TestCase):
    def test_3d_commands_are_offered(self):
        for command in (
            const.CMD_3D_OFF,
            const.CMD_3D_AUTO,
            const.CMD_3D_TEST_ON,
            const.CMD_3D_TEST_OFF,
            const.CMD_3D_DELAY_UP,
            const.CMD_3D_DELAY_DOWN,
            const.CMD_3D_DARK_UP,
            const.CMD_3D_DARK_DOWN,
        ):
            self.assertIn(command, const.SIMPLE_COMMANDS)


class TestRemoteCommandsReachTheDevice(unittest.IsolatedAsyncioTestCase):
    async def test_each_3d_command_calls_the_right_device_method(self):
        from uc_intg_christie_m4k25.remote import _build_command_map

        device = mock.AsyncMock()
        commands = _build_command_map(device)

        await commands[const.CMD_3D_OFF]()
        device.set_3d_mode.assert_awaited_with("Off")
        await commands[const.CMD_3D_AUTO]()
        device.set_3d_mode.assert_awaited_with("Auto Detect")
        await commands[const.CMD_3D_TEST_ON]()
        device.set_3d_test_pattern.assert_awaited_with(True)
        await commands[const.CMD_3D_TEST_OFF]()
        device.set_3d_test_pattern.assert_awaited_with(False)
        await commands[const.CMD_3D_DELAY_UP]()
        device.step_3d_delay.assert_awaited_with(const.THREE_D_DELAY_STEP)
        await commands[const.CMD_3D_DELAY_DOWN]()
        device.step_3d_delay.assert_awaited_with(-const.THREE_D_DELAY_STEP)
        await commands[const.CMD_3D_DARK_UP]()
        device.step_3d_dark_interval.assert_awaited_with(
            const.THREE_D_DARK_INTERVAL_STEP
        )
        await commands[const.CMD_3D_DARK_DOWN]()
        device.step_3d_dark_interval.assert_awaited_with(
            -const.THREE_D_DARK_INTERVAL_STEP
        )

    def test_the_names_the_remote_sends_are_the_librarys(self):
        # 3D_OFF and 3D_AUTO hard-code mode names; a rename in the library
        # would otherwise break two buttons silently.
        self.assertIn("Off", THREE_D_MODES.values())
        self.assertIn("Auto Detect", THREE_D_MODES.values())


if __name__ == "__main__":
    unittest.main()
