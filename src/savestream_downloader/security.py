from __future__ import annotations

import hashlib
import hmac
import re
from urllib.parse import urlparse

from fastapi import Header, HTTPException, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import Settings


_ALLOWED_TIKTOK_HOSTS = {
    "tiktok.com",
    "www.tiktok.com",
    "m.tiktok.com",
    "vm.tiktok.com",
    "vt.tiktok.com",
}
_FILENAME_RE = re.compile(r"[^A-Za-z0-9._ -]+")


def validate_tiktok_url(value: str) -> str:
    value = value.strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("URL must use http or https")
    host = (parsed.hostname or "").lower().rstrip(".")
    if host not in _ALLOWED_TIKTOK_HOSTS and not host.endswith(".tiktok.com"):
        raise ValueError("Only TikTok URLs are supported")
    if not parsed.path:
        raise ValueError("TikTok URL has no path")
    return value


def url_cache_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def client_bucket(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def safe_filename(value: str, fallback: str = "tiktok-video.mp4") -> str:
    cleaned = _FILENAME_RE.sub("_", value).strip(" .")
    return cleaned[:180] or fallback


class DownloadTokenSigner:
    def __init__(self, secret: str) -> None:
        self._serializer = URLSafeTimedSerializer(secret, salt="savestream-download-v1")

    def create(self, request_id: str) -> str:
        return self._serializer.dumps({"rid": request_id})

    def verify(self, token: str, max_age: int) -> str:
        try:
            payload = self._serializer.loads(token, max_age=max_age)
        except SignatureExpired as exc:
            raise HTTPException(status_code=410, detail="Download link expired") from exc
        except BadSignature as exc:
            raise HTTPException(status_code=404, detail="Invalid download link") from exc
        rid = payload.get("rid") if isinstance(payload, dict) else None
        if not isinstance(rid, str) or not rid:
            raise HTTPException(status_code=404, detail="Invalid download link")
        return rid


async def require_internal_key(
    settings: Settings,
    x_savestream_service_key: str | None = Header(default=None),
) -> None:
    if not settings.internal_api_key:
        return
    if not x_savestream_service_key or not hmac.compare_digest(
        x_savestream_service_key, settings.internal_api_key
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
