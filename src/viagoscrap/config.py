from dataclasses import dataclass
import os


@dataclass(slots=True)
class Settings:
    headless: bool = False
    timeout_ms: int = 30_000


    @classmethod
    def from_env(cls) -> "Settings":
        headless = os.getenv("HEADLESS", "false").lower() in {"1", "true", "yes", "y"}
        timeout_ms = int(os.getenv("TIMEOUT_MS", "30000"))
        return cls(headless=headless, timeout_ms=timeout_ms)
