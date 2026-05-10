"""Main poll loop wiring sources → mode."""

from __future__ import annotations

import logging
import signal
import time
from pathlib import Path

from .config import BridgeConfig
from .modes import MultiPetMode, SinglePetMode
from .sources import load_sources

log = logging.getLogger("openpets-bridge")


def _setup_logging(log_path: str) -> None:
    p = Path(log_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.FileHandler(p, mode="a"), logging.StreamHandler()],
    )


def run(cfg: BridgeConfig) -> int:
    _setup_logging(cfg.log_path)
    log.info("openpets-bridge starting; mode=%s log=%s", cfg.mode, cfg.log_path)

    sources = load_sources(cfg.sources)
    if not sources:
        log.error("No enabled sources — edit %s and set at least one [sources.*].enabled = true",
                  Path("~/.config/openpets-bridge/config.toml").expanduser())
        return 1
    log.info("Sources: %s", ", ".join(s.id for s in sources))

    auto_clear = cfg.auto_clear_after_s if cfg.auto_clear_after_s > 0 else None
    if cfg.mode == "multi":
        mode = MultiPetMode(cfg.sources,
                            push_throttle_s=cfg.push_throttle_s,
                            auto_clear_after_s=auto_clear)
    else:
        mode = SinglePetMode(cfg.sources,
                             push_throttle_s=cfg.push_throttle_s,
                             auto_clear_after_s=auto_clear)

    stop = {"flag": False}
    def _stop(*_): stop["flag"] = True
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    while not stop["flag"]:
        try:
            for s in sources:
                try:
                    mode.consume(s.poll())
                except Exception as e:  # noqa: BLE001
                    log.exception("source %s poll failed: %s", s.id, e)
            # Periodic upkeep — clears stale 'done' bubbles, etc.
            try:
                mode.tick()
            except Exception as e:  # noqa: BLE001
                log.exception("mode tick failed: %s", e)
        except Exception as e:  # noqa: BLE001
            log.exception("loop iteration failed: %s", e)
        time.sleep(cfg.poll_interval_s)

    if isinstance(mode, MultiPetMode):
        mode.shutdown()
    log.info("openpets-bridge stopped")
    return 0
