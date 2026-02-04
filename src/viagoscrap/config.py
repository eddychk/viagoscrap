from dataclasses import dataclass
import os


@dataclass(slots=True)
class Settings:
    headless: bool = True
    timeout_ms: int = 30_000


    @classmethod
    def from_env(cls) -> "Settings":
        headless = os.getenv("HEADLESS", "true").lower() in {"1", "true", "yes", "y"}
        timeout_ms = int(os.getenv("TIMEOUT_MS", "30000"))
        return cls(headless=headless, timeout_ms=timeout_ms)
