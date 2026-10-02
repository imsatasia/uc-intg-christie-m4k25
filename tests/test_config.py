"""Tests for pure, network-free logic -- the class of test every real UC3
integration can cheaply have, per references/testing-and-conventions.md."""

import os
import tempfile
import unittest

from uc_intg_christie_m4k25.config import ChristieConfig, entity_id


class TestEntityId(unittest.TestCase):
    def test_replaces_dots_with_underscores(self):
        self.assertEqual(
            "media_player.christie_m4k25_192_0_2_50",
            entity_id("media_player", "192.0.2.50"),
        )

    def test_with_suffix(self):
        self.assertEqual(
            "switch.christie_m4k25_192_0_2_50_shutter",
            entity_id("switch", "192.0.2.50", "shutter"),
        )

    def test_different_prefix(self):
        self.assertEqual(
            "select.christie_m4k25_192_0_2_50_test_pattern",
            entity_id("select", "192.0.2.50", "test_pattern"),
        )


class TestChristieConfig(unittest.TestCase):
    def test_not_configured_without_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = ChristieConfig(config_dir=tmp)
            self.assertFalse(config.is_configured())

    def test_set_config_persists_and_reloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = ChristieConfig(config_dir=tmp)
            config.set_config("192.0.2.50", 3002, "My Projector")

            reloaded = ChristieConfig(config_dir=tmp)
            self.assertTrue(reloaded.is_configured())
            self.assertEqual("192.0.2.50", reloaded.host)
            self.assertEqual(3002, reloaded.port)
            self.assertEqual("My Projector", reloaded.name)

    def test_default_port_and_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = ChristieConfig(config_dir=tmp)
            config.set_config("192.0.2.50")
            self.assertEqual(3002, config.port)
            self.assertEqual("Christie M 4K25 RGB", config.name)

    def test_clear_removes_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = ChristieConfig(config_dir=tmp)
            config.set_config("192.0.2.50")
            path = os.path.join(tmp, "christie_m4k25_config.json")
            self.assertTrue(os.path.exists(path))

            config.clear()
            self.assertFalse(os.path.exists(path))
            self.assertFalse(config.is_configured())


if __name__ == "__main__":
    unittest.main()
