from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ResolveRequest(BaseModel):
    source: Literal["tiktok"] = "tiktok"
    url: str = Field(min_length=8, max_length=2048)


class MediaAsset(BaseModel):
    kind: Literal["video", "photo"]
    media_url: str
    filename: str
    content_type: str
    upstream_headers: dict[str, str] = Field(default_factory=dict)


class ResolvedMedia(BaseModel):
    source: Literal["tiktok"] = "tiktok"
    source_url: str
    provider: str
    media_type: Literal["video", "photo_carousel"] = "video"
    media_url: str | None = None
    assets: list[MediaAsset] = Field(default_factory=list)
    title: str | None = None
    author: str | None = None
    thumbnail: str | None = None
    duration: float | None = None
    filename: str
    content_type: str = "video/mp4"
    upstream_headers: dict[str, str] = Field(default_factory=dict)
    created_at: float


class ResolveItem(BaseModel):
    index: int
    kind: Literal["video", "photo"]
    filename: str
    content_type: str
    download_url: str


class ResolveResponse(BaseModel):
    request_id: str
    source: Literal["tiktok"]
    media_type: Literal["video", "photo_carousel"]
    title: str | None
    author: str | None
    thumbnail: str | None
    duration: float | None
    filename: str
    provider: str
    cached: bool
    expires_in: int
    download_url: str | None
    download_all_url: str | None = None
    items: list[ResolveItem] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    store: str
    providers: dict[str, bool]
