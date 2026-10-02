# SaveStream integration contract

## Intended request path

```text
Homepage widget
  -> SaveStream public backend
  -> savestream-video-downloader (private service)
  -> yt-dlp / Cobalt / DTK fallback
  -> upstream media
```

Do not expose Cobalt or DTK directly to the browser.

## Homepage flow

1. User selects `TikTok` and pastes a URL.
2. SaveStream calls `POST /v1/resolve` on this service.
3. While the request is pending, the frontend may display the normal processing-state ad placement.
4. SaveStream returns preview metadata to the browser.
5. For a video post, the browser gets one MP4 download URL.
6. For a photo post, the browser gets a photo list plus a ZIP download-all URL.

There is no forced wait for advertising. If extraction is cached, return the result immediately.

## Resolve response types

### Video

```json
{
  "media_type": "video",
  "download_url": "/v1/download/<token>",
  "download_all_url": null,
  "items": []
}
```

### TikTok photo carousel

```json
{
  "media_type": "photo_carousel",
  "download_url": "/v1/download/<token>/all",
  "download_all_url": "/v1/download/<token>/all",
  "items": [
    {
      "index": 0,
      "kind": "photo",
      "filename": "tiktok-123-01.jpg",
      "content_type": "image/jpeg",
      "download_url": "/v1/download/<token>/item/0"
    }
  ]
}
```

The first item download URL is also used as the fallback thumbnail when the extractor does not provide a safe public thumbnail URL.

## Private service routes

```text
POST /v1/resolve
GET  /v1/download/{token}              # video
GET  /v1/download/{token}/item/{index} # one carousel photo
GET  /v1/download/{token}/all          # all carousel photos as ZIP
```

## Suggested SaveStream public routes

The frontend should never call the private downloader directly. Proxy these through the existing SaveStream backend, for example:

```text
POST /api/tools/video/resolve
GET  /api/tools/video/download/{token}
GET  /api/tools/video/download/{token}/item/{index}
GET  /api/tools/video/download/{token}/all
```

The SaveStream backend adds `X-SaveStream-Service-Key` when it calls the private downloader.

## Usage and monetization hooks

Count a `resolve` attempt separately from a completed download. This makes it possible to measure resolve requests, provider success rate, download starts, bytes served, and conversion from downloader visitor to SaveStream signup.

Anonymous homepage limits should be enforced in both the public SaveStream layer and this service. Logged-in/paid limits belong in the main SaveStream credits/usage system; this microservice is intentionally unaware of plans and billing.
