"""
Christie M 4K25 RGB integration driver.

Entry point and ucapi.IntegrationAPI lifecycle wiring. See
references/driver-lifecycle-and-setup.md for what each handler must do and
why -- especially ENTER_STANDBY/EXIT_STANDBY, which is the single most
consequential lifecycle pair to get right (see SKILL.md's "one rule that
matters most").

:license: MIT, see LICENSE for more details.
"""

from __future__ import annotations

import asyncio
import logging
import os

import ucapi
from christie_mseries import Snapshot
from ucapi import DeviceStates, Events

from uc_intg_christie_m4k25.config import ChristieConfig
from uc_intg_christie_m4k25.device import (
    EVENT_UNAVAILABLE,
    EVENT_UPDATE,
    ChristieDevice,
)
from uc_intg_christie_m4k25.media_player import (
    ChristieMediaPlayer,
    power_state_to_media_player_state,
)
from uc_intg_christie_m4k25.remote import ChristieRemote, power_state_to_remote_state
from uc_intg_christie_m4k25.select import ChristieInputSelect, ChristieTestPatternSelect
from uc_intg_christie_m4k25.sensor import (
    build_alarms_sensor,
    build_hours_sensor,
    build_input_name_sensor,
    build_intake_temperature_sensor,
    build_status_sensor,
)
from uc_intg_christie_m4k25.setup import ChristieSetup
from uc_intg_christie_m4k25.switch import ChristieLiteLocSwitch, ChristieShutterSwitch

_LOG = logging.getLogger(__name__)

api: ucapi.IntegrationAPI | None = None
_config: ChristieConfig | None = None
_device: ChristieDevice | None = None

_media_player: ChristieMediaPlayer | None = None
_remote: ChristieRemote | None = None
_input_select: ChristieInputSelect | None = None
_test_pattern_select: ChristieTestPatternSelect | None = None
_shutter_switch: ChristieShutterSwitch | None = None
_liteloc_switch: ChristieLiteLocSwitch | None = None
_status_sensor: ucapi.Sensor | None = None
_input_name_sensor: ucapi.Sensor | None = None
_hours_sensor: ucapi.Sensor | None = None
_intake_temperature_sensor: ucapi.Sensor | None = None
_alarms_sensor: ucapi.Sensor | None = None

# Every entity type's States enum defines the same literal value for this
# common state (see entity.py's CommonStates), so one plain string covers all
# of them in _apply_unavailable() without importing five separate enums.
_UNAVAILABLE = "UNAVAILABLE"


def _on_device_update(event: str, data: object) -> None:
    """Forward device state changes into the configured entities.

    Registered as a synchronous callback on ChristieDevice; schedules the
    actual (async) attribute update on the driver's event loop.
    """
    if api is None:
        return
    if event == EVENT_UPDATE and isinstance(data, Snapshot):
        asyncio.get_event_loop().create_task(_apply_snapshot(data))
    elif event == EVENT_UNAVAILABLE:
        asyncio.get_event_loop().create_task(_apply_unavailable())


def _update(entity_id: str | None, attributes: dict) -> None:
    if entity_id and api.configured_entities.contains(entity_id):
        api.configured_entities.update_attributes(entity_id, attributes)


async def _apply_snapshot(snapshot: Snapshot) -> None:
    """Push one poll's worth of state to every configured entity that cares.

    Also re-asserts DeviceStates.CONNECTED: a prior failed poll leaves the
    device state latched at DISCONNECTED (see _apply_unavailable()) with
    nothing to clear it otherwise, so the Remote would show the integration
    as disconnected forever after a single transient hiccup even though
    polling has since recovered.
    """
    await api.set_device_state(DeviceStates.CONNECTED)
    _update(
        _media_player.id if _media_player else None,
        {
            ucapi.media_player.Attributes.STATE: power_state_to_media_player_state(
                snapshot.power_code
            ),
            ucapi.media_player.Attributes.SOURCE: snapshot.input_label,
        },
    )
    _update(
        _remote.id if _remote else None,
        {
            ucapi.remote.Attributes.STATE: power_state_to_remote_state(
                snapshot.power_code
            )
        },
    )
    _update(
        _input_select.id if _input_select else None,
        {ucapi.select.Attributes.CURRENT_OPTION: snapshot.input_label},
    )
    _update(
        _test_pattern_select.id if _test_pattern_select else None,
        {ucapi.select.Attributes.CURRENT_OPTION: snapshot.test_pattern},
    )
    _update(
        _shutter_switch.id if _shutter_switch else None,
        {
            ucapi.switch.Attributes.STATE: (
                ucapi.switch.States.ON
                if snapshot.shutter_open
                else ucapi.switch.States.OFF
            )
        },
    )
    _update(
        _liteloc_switch.id if _liteloc_switch else None,
        {
            ucapi.switch.Attributes.STATE: (
                ucapi.switch.States.ON if snapshot.liteloc else ucapi.switch.States.OFF
            )
        },
    )
    _update(
        _status_sensor.id if _status_sensor else None,
        {
            ucapi.sensor.Attributes.STATE: ucapi.sensor.States.ON,
            ucapi.sensor.Attributes.VALUE: snapshot.power,
        },
    )
    _update(
        _input_name_sensor.id if _input_name_sensor else None,
        {
            ucapi.sensor.Attributes.STATE: ucapi.sensor.States.ON,
            ucapi.sensor.Attributes.VALUE: snapshot.input_name,
        },
    )
    _update(
        _hours_sensor.id if _hours_sensor else None,
        {
            ucapi.sensor.Attributes.STATE: ucapi.sensor.States.ON,
            ucapi.sensor.Attributes.VALUE: snapshot.hours,
        },
    )
    if snapshot.intake_temp is not None:
        _update(
            _intake_temperature_sensor.id if _intake_temperature_sensor else None,
            {
                ucapi.sensor.Attributes.STATE: ucapi.sensor.States.ON,
                ucapi.sensor.Attributes.VALUE: snapshot.intake_temp,
            },
        )
    _update(
        _alarms_sensor.id if _alarms_sensor else None,
        {
            ucapi.sensor.Attributes.STATE: ucapi.sensor.States.ON,
            ucapi.sensor.Attributes.VALUE: "on" if snapshot.alarms > 0 else "off",
        },
    )


async def _apply_unavailable() -> None:
    """Mark every configured entity UNAVAILABLE after a failed poll.

    UNAVAILABLE (real communication failure) rather than UNKNOWN (reachable,
    value just not known yet) -- see references/protocol-and-entities.md.
    """
    for entity, attr_cls in (
        (_media_player, ucapi.media_player.Attributes),
        (_remote, ucapi.remote.Attributes),
        (_shutter_switch, ucapi.switch.Attributes),
        (_liteloc_switch, ucapi.switch.Attributes),
    ):
        if entity:
            _update(entity.id, {attr_cls.STATE: _UNAVAILABLE})
    for sensor in (
        _status_sensor,
        _input_name_sensor,
        _hours_sensor,
        _intake_temperature_sensor,
        _alarms_sensor,
    ):
        if sensor:
            _update(sensor.id, {ucapi.sensor.Attributes.STATE: _UNAVAILABLE})
    for select_entity in (_input_select, _test_pattern_select):
        if select_entity:
            _update(select_entity.id, {ucapi.select.Attributes.STATE: _UNAVAILABLE})
    await api.set_device_state(DeviceStates.DISCONNECTED)


def _initialize_entities() -> bool:
    """Create the device client and entities once configuration exists."""
    global _device, _media_player, _remote, _input_select, _test_pattern_select
    global _shutter_switch, _liteloc_switch
    global _status_sensor, _input_name_sensor, _hours_sensor
    global _intake_temperature_sensor, _alarms_sensor

    if not _config or not _config.is_configured():
        _LOG.info("Integration not configured yet")
        return False

    try:
        loop = asyncio.get_running_loop()
        _device = ChristieDevice(_config.host, _config.port, loop)
        _device.on(_on_device_update)

        _media_player = ChristieMediaPlayer(_config, _device)
        _remote = ChristieRemote(_config, _device)
        _input_select = ChristieInputSelect(_config, _device)
        _test_pattern_select = ChristieTestPatternSelect(_config, _device)
        _shutter_switch = ChristieShutterSwitch(_config, _device)
        _liteloc_switch = ChristieLiteLocSwitch(_config, _device)
        _status_sensor = build_status_sensor(_config)
        _input_name_sensor = build_input_name_sensor(_config)
        _hours_sensor = build_hours_sensor(_config)
        _intake_temperature_sensor = build_intake_temperature_sensor(_config)
        _alarms_sensor = build_alarms_sensor(_config)

        api.available_entities.clear()
        for entity in (
            _media_player,
            _remote,
            _input_select,
            _test_pattern_select,
            _shutter_switch,
            _liteloc_switch,
            _status_sensor,
            _input_name_sensor,
            _hours_sensor,
            _intake_temperature_sensor,
            _alarms_sensor,
        ):
            api.available_entities.add(entity)

        _device.start_polling()
        return True
    except Exception as exc:
        _LOG.error("Failed to initialize entities: %s", exc, exc_info=True)
        return False


async def on_setup_complete() -> None:
    """Called once the setup flow finishes successfully."""
    if _initialize_entities():
        await api.set_device_state(DeviceStates.CONNECTED)
    else:
        await api.set_device_state(DeviceStates.ERROR)


async def on_connect() -> None:
    """The remote (re)connected. Reload config and (re)initialize on demand."""
    global _config
    if _config is None:
        _config = ChristieConfig()
    _config.reload_from_disk()

    if not _config.is_configured():
        await api.set_device_state(DeviceStates.DISCONNECTED)
        return

    if _device is None:
        if _initialize_entities():
            await api.set_device_state(DeviceStates.CONNECTED)
        else:
            await api.set_device_state(DeviceStates.ERROR)
        return

    _device.start_polling()
    await api.set_device_state(DeviceStates.CONNECTED)


async def on_disconnect() -> None:
    """The remote disconnected."""
    _LOG.info("Remote disconnected")


async def on_enter_standby() -> None:
    """The remote is entering standby: stop the poll loop.

    See SKILL.md's "one rule that matters most" -- the whole driver process
    is suspended, so anything left running is stale garbage on wake.
    """
    if _device:
        await _device.suspend()


async def on_exit_standby() -> None:
    """The remote exited standby: re-sync from scratch, then resume polling."""
    if _device:
        await _device.resume()


async def on_subscribe_entities(entity_ids: list[str]) -> None:
    """Push current state for newly subscribed entities.

    The remote never polls -- this is the only moment (besides an actual
    state change) a subscribed entity's value gets pushed proactively.
    """
    if _device and _device.snapshot is not None:
        await _apply_snapshot(_device.snapshot)


async def main() -> None:
    """Main entry point."""
    global api, _config

    logging.basicConfig(level=os.getenv("UC_LOG_LEVEL", "INFO").upper())

    loop = asyncio.get_running_loop()
    api = ucapi.IntegrationAPI(loop)

    api.listens_to(Events.CONNECT)(on_connect)
    api.listens_to(Events.DISCONNECT)(on_disconnect)
    api.listens_to(Events.SUBSCRIBE_ENTITIES)(on_subscribe_entities)
    api.listens_to(Events.ENTER_STANDBY)(on_enter_standby)
    api.listens_to(Events.EXIT_STANDBY)(on_exit_standby)

    _config = ChristieConfig()
    setup_handler = ChristieSetup(_config, on_setup_complete)

    if _config.is_configured():
        # Pre-initialize so a process restart (the remote can trigger one at
        # any time) doesn't require the user to re-run setup.
        _initialize_entities()

    await api.init("driver.json", setup_handler.handle_setup)
    await asyncio.Future()


def run() -> None:
    """Synchronous entry point for `python -m uc_intg_christie_m4k25`."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()
