from __future__ import annotations

import os
import secrets
from dataclasses import dataclass


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    app_env: str
    host: str
    port: int
    log_level: str
    internal_api_key: str | None
    token_secret: str
    redis_url: str | None
    cache_ttl_seconds: int
    download_ttl_seconds: int
    media_refresh_after_seconds: int
    provider_timeout_seconds: int
    provider_order: tuple[str, ...]
    enable_ytdlp: bool
    cobalt_url: str | None
    cobalt_api_key: str | None
    dtk_url: str | None
    dtk_api_key: str | None
    dtk_wait_seconds: int
    resolve_rate_limit_per_minute: int
    download_rate_limit_per_minute: int
    max_duration_seconds: int
    max_file_size_bytes: int
    max_carousel_items: int

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.getenv("APP_ENV", "development").strip().lower()
        api_key = os.getenv("INTERNAL_API_KEY") or None
        token_secret = os.getenv("TOKEN_SECRET") or secrets.token_urlsafe(32)
        if env == "production":
            if not api_key:
                raise RuntimeError("INTERNAL_API_KEY is required in production")
            if not os.getenv("TOKEN_SECRET"):
                raise RuntimeError("TOKEN_SECRET is required in production")
        order = tuple(
            item.strip().lower()
            for item in os.getenv("PROVIDER_ORDER", "ytdlp,cobalt,dtk").split(",")
            if item.strip()
        )
        return cls(
            app_env=env,
            host=os.getenv("HOST", "0.0.0.0"),
            port=_int("PORT", 8787),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            internal_api_key=api_key,
            token_secret=token_secret,
            redis_url=os.getenv("REDIS_URL") or None,
            cache_ttl_seconds=_int("CACHE_TTL_SECONDS", 45),
            download_ttl_seconds=_int("DOWNLOAD_TTL_SECONDS", 300),
            media_refresh_after_seconds=_int("MEDIA_REFRESH_AFTER_SECONDS", 60),
            provider_timeout_seconds=_int("PROVIDER_TIMEOUT_SECONDS", 15),
            provider_order=order,
            enable_ytdlp=_bool("ENABLE_YTDLP", True),
            cobalt_url=os.getenv("COBALT_URL") or None,
            cobalt_api_key=os.getenv("COBALT_API_KEY") or None,
            dtk_url=os.getenv("DTK_URL") or None,
            dtk_api_key=os.getenv("DTK_API_KEY") or None,
            dtk_wait_seconds=_int("DTK_WAIT_SECONDS", 12),
            resolve_rate_limit_per_minute=_int("RESOLVE_RATE_LIMIT_PER_MINUTE", 30),
            download_rate_limit_per_minute=_int("DOWNLOAD_RATE_LIMIT_PER_MINUTE", 60),
            max_duration_seconds=_int("MAX_DURATION_SECONDS", 900),
            max_file_size_bytes=_int("MAX_FILE_SIZE_BYTES", 500 * 1024 * 1024),
            max_carousel_items=_int("MAX_CAROUSEL_ITEMS", 50),
        )
