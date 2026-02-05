from dataclasses import dataclass
import os


def _as_bool(raw: str, default: bool) -> bool:
    if raw is None:
        return default
    normalized = raw.strip().strip('"').strip("'").lower()
    return normalized in {"1", "true", "yes", "y", "on"}


@dataclass(slots=True)
class Settings:
    headless: bool = False
    timeout_ms: int = 30_000


    @classmethod
    def from_env(cls) -> "Settings":
        headless = _as_bool(os.getenv("HEADLESS"), default=False)
        timeout_ms = int(os.getenv("TIMEOUT_MS", "30000"))
        return cls(headless=headless, timeout_ms=timeout_ms)
