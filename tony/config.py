"""Runtime configuration for Tony."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("TONY_DATA_DIR", BASE_DIR.parent / "data"))


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, "1" if default else "0").strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    # Core
    base_url: str = field(default_factory=lambda: os.getenv("TONY_BASE_URL", "http://localhost:8000").rstrip("/"))
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "").strip())
    secret_key: str = field(default_factory=lambda: os.getenv("TONY_SECRET_KEY", "").strip())
    admin_token: str = field(default_factory=lambda: os.getenv("TONY_ADMIN_TOKEN", "").strip())

    # Behaviour
    demo_open: bool = field(default_factory=lambda: _bool("TONY_DEMO_OPEN", True))
    demo_rate_limit: int = field(default_factory=lambda: int(os.getenv("TONY_DEMO_RATE_LIMIT", "60")))
    demo_ttl_hours: float = field(default_factory=lambda: float(os.getenv("TONY_DEMO_TTL_HOURS", "24")))
    demo_gc_hours: float = field(default_factory=lambda: float(os.getenv("TONY_DEMO_GC_HOURS", "168")))
    require_approval: bool = field(default_factory=lambda: _bool("TONY_REQUIRE_APPROVAL", True))
    max_response_chars: int = field(default_factory=lambda: int(os.getenv("TONY_MAX_RESPONSE_CHARS", "12000")))
    http_timeout: float = field(default_factory=lambda: float(os.getenv("TONY_HTTP_TIMEOUT", "25")))
    execution_deadline: float = field(default_factory=lambda: float(os.getenv("TONY_EXECUTION_DEADLINE", "30")))
    http_retries: int = field(default_factory=lambda: int(os.getenv("TONY_HTTP_RETRIES", "2")))
    allow_private_networks: bool = field(default_factory=lambda: _bool("TONY_ALLOW_PRIVATE", False))
    poll_interval: int = field(default_factory=lambda: int(os.getenv("TONY_POLL_INTERVAL", "30")))
    google_client_id: str = field(default_factory=lambda: os.getenv("GOOGLE_CLIENT_ID", "").strip())
    google_allowed_origins: str = field(default_factory=lambda: os.getenv("TONY_GOOGLE_ORIGINS", "").strip())
    session_days: int = field(default_factory=lambda: int(os.getenv("TONY_SESSION_DAYS", "30")))
    self_url: str = field(default_factory=lambda: (os.getenv("RENDER_EXTERNAL_URL") or os.getenv("TONY_BASE_URL", "")).rstrip("/"))
    ping_seconds: int = field(default_factory=lambda: int(os.getenv("TONY_PING_SECONDS", "240")))
    log_level: str = field(default_factory=lambda: os.getenv("TONY_LOG_LEVEL", "INFO"))

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith(("postgres://", "postgresql://"))

    @property
    def sqlalchemy_url(self) -> str:
        if self.is_postgres:
            return self.database_url.replace("postgres://", "postgresql://", 1)
        if self.database_url:
            return self.database_url
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{(DATA_DIR / 'tony.db').as_posix()}"


settings = Settings()
