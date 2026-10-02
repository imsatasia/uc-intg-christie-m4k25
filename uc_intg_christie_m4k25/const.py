"""
Constants for the Christie M 4K25 RGB integration.

:license: MIT, see LICENSE for more details.
"""

from christie_mseries.client import DEFAULT_PORT as CHRISTIE_DEFAULT_PORT

DEFAULT_PORT = CHRISTIE_DEFAULT_PORT  # 3002
DEFAULT_NAME = "Christie M 4K25 RGB"

# Per-call connection timeout. The library opens a short-lived TCP connection
# for every poll and every command rather than holding one open -- see
# device.py and py-christie-mseries's own AGENTS.md for why it stays
# synchronous and per-call. 8s matches the Home Assistant integration's
# coordinator, which needs headroom for the few seconds after a power command
# where the projector accepts the TCP connection but answers nothing.
COMMAND_TIMEOUT = 8.0

# How often the background poll loop refreshes the snapshot. Suspended
# entirely across ENTER_STANDBY/EXIT_STANDBY -- see device.py.
POLL_INTERVAL = 10.0

# Absolute motor position range shared by FCS/ZOM/LHO/LVO (confirmed in
# py-christie-mseries's projector.py docstrings).
LENS_POSITION_MIN = -1200
LENS_POSITION_MAX = 1200

# Step size used by the remote entity's nudge commands (FOCUS_NEAR/FAR,
# ZOOM_IN/OUT, LENS_UP/DOWN/LEFT/RIGHT) -- there is no relative-move command
# in the protocol, only absolute positions, so the driver reads the current
# position and writes position +/- this step.
LENS_STEP = 10

# Step size for the remote entity's BRIGHTNESS_UP/BRIGHTNESS_DOWN commands.
# Requests are clamped to ChristieM4K25.set_brightness()'s own
# [BRIGHTNESS_MIN_PERCENT, BRIGHTNESS_MAX_PERCENT] range (30-100%).
BRIGHTNESS_STEP = 5.0

# Simple command names for the remote entity. Uppercase, no whitespace,
# <=20 chars -- see references/protocol-and-entities.md.
CMD_SHUTTER_OPEN = "SHUTTER_OPEN"
CMD_SHUTTER_CLOSE = "SHUTTER_CLOSE"
CMD_FREEZE_TOGGLE = "FREEZE_TOGGLE"
CMD_AUTO_SETUP = "AUTO_SETUP"
CMD_LITELOC_ON = "LITELOC_ON"
CMD_LITELOC_OFF = "LITELOC_OFF"
CMD_BRIGHTNESS_UP = "BRIGHTNESS_UP"
CMD_BRIGHTNESS_DOWN = "BRIGHTNESS_DOWN"
CMD_LENS_HOME = "LENS_HOME"
CMD_LENS_CALIBRATE = "LENS_CALIBRATE"
CMD_FOCUS_NEAR = "FOCUS_NEAR"
CMD_FOCUS_FAR = "FOCUS_FAR"
CMD_ZOOM_IN = "ZOOM_IN"
CMD_ZOOM_OUT = "ZOOM_OUT"
CMD_LENS_UP = "LENS_UP"
CMD_LENS_DOWN = "LENS_DOWN"
CMD_LENS_LEFT = "LENS_LEFT"
CMD_LENS_RIGHT = "LENS_RIGHT"

SIMPLE_COMMANDS = [
    CMD_SHUTTER_OPEN,
    CMD_SHUTTER_CLOSE,
    CMD_FREEZE_TOGGLE,
    CMD_AUTO_SETUP,
    CMD_LITELOC_ON,
    CMD_LITELOC_OFF,
    CMD_BRIGHTNESS_UP,
    CMD_BRIGHTNESS_DOWN,
    CMD_LENS_HOME,
    CMD_LENS_CALIBRATE,
    CMD_FOCUS_NEAR,
    CMD_FOCUS_FAR,
    CMD_ZOOM_IN,
    CMD_ZOOM_OUT,
    CMD_LENS_UP,
    CMD_LENS_DOWN,
    CMD_LENS_LEFT,
    CMD_LENS_RIGHT,
]
