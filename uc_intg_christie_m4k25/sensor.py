"""
Sensor entities for the Christie M 4K25 RGB integration: status text, input
name, operating hours, intake temperature, an alarm-present binary sensor, and
the two read-only 3D readings. Sensors take no cmd_handler -- ucapi's Sensor entity supports no
commands at all (see entity_sensor.md: "The sensor entity doesn't support
any commands.") -- so this module only builds the entities; driver.py's
_apply_snapshot() pushes their values.

:license: MIT, see LICENSE for more details.
"""

from __future__ import annotations

from ucapi.sensor import Attributes, DeviceClasses, Sensor, States

from uc_intg_christie_m4k25.config import ChristieConfig, entity_id

# There's no dedicated ucapi binary_sensor entity type (see
# references/protocol-and-entities.md's full entity list) -- a binary
# reading is a Sensor with device_class BINARY, whose `unit` attribute
# carries which Home Assistant-style binary-sensor kind it represents (see
# entity_sensor.md's "Binary Device Class" section). "problem" matches how
# Home Assistant's own binary_sensor.device_class enumerates an alarm/fault
# indicator.
_ALARM_UNIT = "problem"


def build_status_sensor(config: ChristieConfig) -> Sensor:
    """The projector's own power-state wording, e.g. "Standby Mode"."""
    return Sensor(
        identifier=entity_id("sensor", config.host, "status"),
        name=f"{config.name} Status",
        features=[],
        attributes={Attributes.STATE: States.ON, Attributes.VALUE: ""},
        device_class=DeviceClasses.CUSTOM,
    )


def build_input_name_sensor(config: ChristieConfig) -> Sensor:
    """The projector's own name for the active input, distinct from the
    port-label options offered by select_input()/the media_player source
    list -- see py-christie-mseries's INPUTS docstring."""
    return Sensor(
        identifier=entity_id("sensor", config.host, "input_name"),
        name=f"{config.name} Input Name",
        features=[],
        attributes={Attributes.STATE: States.ON, Attributes.VALUE: ""},
        device_class=DeviceClasses.CUSTOM,
    )


def build_hours_sensor(config: ChristieConfig) -> Sensor:
    """Total elapsed operating hours, as the projector formats it, e.g.
    "3:14 (h:m)" -- kept as the device's own string rather than parsed into a
    number, the same choice py-christie-mseries's get_hours() makes."""
    return Sensor(
        identifier=entity_id("sensor", config.host, "hours"),
        name=f"{config.name} Hours",
        features=[],
        attributes={Attributes.STATE: States.ON, Attributes.VALUE: ""},
        device_class=DeviceClasses.CUSTOM,
    )


def build_intake_temperature_sensor(config: ChristieConfig) -> Sensor:
    return Sensor(
        identifier=entity_id("sensor", config.host, "intake_temperature"),
        name=f"{config.name} Intake Temperature",
        features=[],
        attributes={Attributes.STATE: States.UNKNOWN, Attributes.VALUE: 0},
        device_class=DeviceClasses.TEMPERATURE,
    )


def build_alarms_sensor(config: ChristieConfig) -> Sensor:
    """value is "on"/"off" (a Christie alarm active or not), not the alarm
    count -- see the Binary Device Class docs cited above."""
    return Sensor(
        identifier=entity_id("sensor", config.host, "alarms"),
        name=f"{config.name} Alarm",
        features=[],
        attributes={
            Attributes.STATE: States.ON,
            Attributes.VALUE: "off",
            Attributes.UNIT: _ALARM_UNIT,
        },
        device_class=DeviceClasses.BINARY,
    )


def build_three_d_sync_sensor(config: ChristieConfig) -> Sensor:
    """The projector's own wording for the 3D sync state, e.g. "Valid HDMI 3D
    Sync"; "N/A" when no 3D signal is being shown."""
    return Sensor(
        identifier=entity_id("sensor", config.host, "3d_sync"),
        name=f"{config.name} 3D Sync",
        features=[],
        attributes={Attributes.STATE: States.ON, Attributes.VALUE: ""},
        device_class=DeviceClasses.CUSTOM,
    )


def build_three_d_darktime_sensor(config: ChristieConfig) -> Sensor:
    """Whether the 3D dark interval fits the frame rate: "Achieved" or "Not
    Achieved"; "N/A" when no 3D signal is being shown."""
    return Sensor(
        identifier=entity_id("sensor", config.host, "3d_darktime"),
        name=f"{config.name} 3D Darktime",
        features=[],
        attributes={Attributes.STATE: States.ON, Attributes.VALUE: ""},
        device_class=DeviceClasses.CUSTOM,
    )
