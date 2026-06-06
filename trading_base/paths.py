from __future__ import annotations

from dataclasses import dataclass
from os import environ
from pathlib import Path

from trading_base.constants import TradingMode


@dataclass(frozen=True)
class RuntimePaths:
    log_dir: Path
    db_path: Path
    config_path: Path
    state_dir: Path


def paths_for(mode: TradingMode, base: Path | None = None) -> RuntimePaths:
    if base is None:
        data_root = Path(environ.get("DATA_ROOT", "data"))
        log_root = Path(environ.get("LOG_ROOT", "logs"))
    else:
        data_root = base / "data"
        log_root = base / "logs"

    mode_val = mode.value
    data_dir = Path(environ.get("DATA_DIR_OVERRIDE", str(data_root / mode_val)))
    log_dir = Path(environ.get("LOG_DIR_OVERRIDE", str(log_root / mode_val)))
    db_path = Path(environ.get("DB_PATH_OVERRIDE", str(data_dir / "trades.db")))
    config_path = Path(environ.get("CONFIG_PATH_OVERRIDE", "config.yaml"))
    state_dir = data_dir / "state"

    return RuntimePaths(
        log_dir=log_dir,
        db_path=db_path,
        config_path=config_path,
        state_dir=state_dir,
    )
