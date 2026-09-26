"""Pi-specific limits; do not change the shared Pico protocol constants."""

from dataclasses import dataclass
import math

RC_PERIOD_S = 0.020
STATUS_PERIOD_S = 0.200
SHUTDOWN_FRAMES = 50
THROTTLE_MIN = 1000
THROTTLE_MAX = 1200


@dataclass(frozen=True)
class Config:
    uart: str = "/dev/serial0"
    baud: int = 420000
    port: int = 5005
    link_timeout_ms: int = 500
    dry_run: bool = False
    verbose: bool = False
    mode: str = "dry-run"
    alt_config: str | None = None
    log: str = "altitude.jsonl"
    duration: float | None = None
    replay: str | None = None
    enable_live: bool = False

    def __post_init__(self):
        if not 1 <= self.port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        if self.baud <= 0 or self.link_timeout_ms <= 0:
            raise ValueError("baud and link-timeout-ms must be positive")
        if self.duration is not None and (not math.isfinite(self.duration) or self.duration < 0):
            raise ValueError("duration must be finite and nonnegative")
