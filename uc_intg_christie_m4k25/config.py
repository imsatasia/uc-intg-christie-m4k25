"""
Configuration persistence for the Christie M 4K25 RGB integration.

There is no framework-provided config store in ucapi (unlike Home Assistant's
Store helper) -- every real integration hand-rolls a small JSON file under
the config directory. UC_CONFIG_HOME is the only writable, persisted location
in the on-remote sandboxed deployment; always resolve through it rather than
a relative or hardcoded path.

:license: MIT, see LICENSE for more details.
"""

import json
import logging
import os
from typing import Any

from uc_intg_christie_m4k25 import const

_LOG = logging.getLogger(__name__)


class ChristieConfig:
    """Configuration manager for the Christie M 4K25 RGB integration."""

    def __init__(self, config_dir: str | None = None) -> None:
        if config_dir is None:
            config_dir = os.getenv("UC_CONFIG_HOME") or os.getenv("HOME") or "./"
        self._config_dir = config_dir
        self._config_file = os.path.join(config_dir, "christie_m4k25_config.json")
        self._config: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._config_file):
                with open(self._config_file, encoding="utf-8") as f:
                    self._config = json.load(f)
                _LOG.info("Configuration loaded from %s", self._config_file)
            else:
                self._config = {}
        except Exception as exc:
            _LOG.error("Failed to load configuration: %s", exc)
            self._config = {}

    def reload_from_disk(self) -> None:
        """Reload from disk. Call this on CONNECT: the remote can restart the
        driver process at any time, and the file is the source of truth
        across that boundary."""
        self._load()

    def _save(self) -> None:
        try:
            os.makedirs(self._config_dir, exist_ok=True)
            with open(self._config_file, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2)
            _LOG.info("Configuration saved to %s", self._config_file)
        except Exception as exc:
            _LOG.error("Failed to save configuration: %s", exc)

    def is_configured(self) -> bool:
        """Return True once a host has been set."""
        return bool(self._config.get("host"))

    def set_config(
        self, host: str, port: int | None = None, name: str | None = None
    ) -> None:
        """Set and save configuration."""
        self._config = {
            "host": host,
            "port": port if port is not None else const.DEFAULT_PORT,
            "name": name or const.DEFAULT_NAME,
        }
        self._save()

    @property
    def host(self) -> str | None:
        return self._config.get("host")

    @property
    def port(self) -> int:
        return self._config.get("port", const.DEFAULT_PORT)

    @property
    def name(self) -> str:
        return self._config.get("name", const.DEFAULT_NAME)

    def clear(self) -> None:
        """Clear configuration."""
        self._config = {}
        if os.path.exists(self._config_file):
            try:
                os.remove(self._config_file)
            except Exception as exc:
                _LOG.error("Failed to remove configuration file: %s", exc)


def entity_id(prefix: str, host: str, suffix: str | None = None) -> str:
    """Build a stable entity_id from the configured host, e.g.
    ``switch.christie_m4k25_192_0_2_50_shutter``.

    Pure function, easy to unit-test independently of ucapi or the network --
    see tests/test_config.py.
    """
    base = f"{prefix}.christie_m4k25_{host.replace('.', '_')}"
    return f"{base}_{suffix}" if suffix else base
