"""Tests for the remote entity's simple-command surface -- the exact class of
test references/testing-and-conventions.md calls out as cheap and valuable
for "a device with dozens of mapped commands ... where a typo silently breaks
one button": every command name's validity, and every command in
const.SIMPLE_COMMANDS actually having a dispatch entry in _build_command_map.
"""

import re
import unittest
from unittest import mock

from uc_intg_christie_m4k25 import const
from uc_intg_christie_m4k25.remote import _build_command_map

# Remote entity simple commands: uppercase, no whitespace, <=20 chars -- the
# looser of the two naming rules in references/protocol-and-entities.md
# (media_player's is stricter: a fixed character set).
_VALID_REMOTE_COMMAND = re.compile(r"^\S{1,20}$")


class TestSimpleCommandNames(unittest.TestCase):
    def test_every_command_is_uppercase_and_within_length(self):
        for command in const.SIMPLE_COMMANDS:
            with self.subTest(command=command):
                self.assertRegex(command, _VALID_REMOTE_COMMAND)
                self.assertEqual(command, command.upper())

    def test_no_duplicate_commands(self):
        self.assertEqual(len(const.SIMPLE_COMMANDS), len(set(const.SIMPLE_COMMANDS)))


class TestCommandMap(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.device = mock.AsyncMock()
        self.command_map = _build_command_map(self.device)

    def test_every_simple_command_has_a_handler(self):
        self.assertEqual(set(const.SIMPLE_COMMANDS), set(self.command_map))

    async def test_every_handler_is_callable_without_error(self):
        for command, handler in self.command_map.items():
            with self.subTest(command=command):
                await handler()


if __name__ == "__main__":
    unittest.main()
