# SaveStream Video Downloader

Internal FastAPI microservice for the small **paste a TikTok URL** tool on the SaveStream homepage. The public SaveStream backend calls this service; the browser should not talk to extractor engines directly.

## What v0.2 does

- TikTok public-link validation and SSRF-resistant input allowlist.
- Sequential provider fallback with per-provider timeouts.
- `yt-dlp` in-process provider.
- Self-hosted Cobalt provider in the included Docker Compose stack.
- Optional adapter for self-hosted `Evil0ctal/Douyin_TikTok_Download_API` v5.
- TikTok video posts -> one streamable/downloadable media file.
- TikTok photo posts -> individual photo downloads plus **Download all as ZIP**.
- Redis metadata caching with automatic in-memory fallback.
- Signed short-lived download links.
- HTTP Range support for individual video/photo downloads.
- Expired upstream URLs are re-resolved through the fallback chain once.
- Per-IP resolve/download rate limits and file-size/duration guards.
- Prometheus provider success/failure/latency metrics.
- No paid API dependency.

This service only processes publicly accessible TikTok URLs. It does not accept user cookies, private-account credentials, or DRM-protected media.

## Provider order

Default:

```text
yt-dlp -> Cobalt -> DTK
```

A failed provider is logged and the next configured provider is tried. Providers are intentionally not fired in parallel, which reduces duplicate upstream traffic and rate-limit pressure.

A real fixture test with a TikTok `/photo/...` post showed the reason for the fallback design: current `yt-dlp` rejected that URL while self-hosted Cobalt returned a three-photo picker successfully.

## Local Docker start

```bash
cp .env.example .env
# Set TOKEN_SECRET and, for production, INTERNAL_API_KEY.
docker compose up -d --build
curl http://127.0.0.1:8787/healthz
```

Cobalt is private to the Compose network. The downloader API is bound to `127.0.0.1:8787` by default.

## Resolve API

```bash
curl -X POST http://127.0.0.1:8787/v1/resolve \
  -H 'content-type: application/json' \
  -H 'X-SaveStream-Service-Key: YOUR_KEY' \
  -d '{"source":"tiktok","url":"https://www.tiktok.com/@user/video/123"}'
```

For a video, `media_type` is `video` and `download_url` points to `/v1/download/<token>`.

For a photo post, `media_type` is `photo_carousel`; `items` contains one signed download path per photo and `download_all_url` points to a ZIP endpoint. `download_url` is also set to the ZIP endpoint so a generic Download button still has a useful target.

## Production notes

- Keep this service on a private Docker/VPC network or loopback and let the SaveStream backend proxy it.
- Set strong `INTERNAL_API_KEY` and `TOKEN_SECRET` values.
- Keep Redis enabled when running multiple API replicas.
- Track `savestream_downloader_provider_attempts_total` and latency metrics to decide when to reorder providers.
- Start with conservative duration/size limits because media proxying consumes outbound bandwidth.
- `MAX_CAROUSEL_ITEMS` limits how many photos one resolve result may expose.

See `docs/SAVESTREAM_INTEGRATION.md` for the SaveStream-facing contract.
