from savestream_downloader.providers.cobalt import CobaltProvider


def test_cobalt_parses_photo_picker() -> None:
    provider = CobaltProvider("http://cobalt:9000")
    media = provider._parse_response(
        "https://www.tiktok.com/@vnt.1.8/photo/7691561538561346837",
        {
            "status": "picker",
            "picker": [
                {"type": "photo", "url": "https://cdn.example/one"},
                {"type": "photo", "url": "https://cdn.example/two"},
                {"type": "photo", "url": "https://cdn.example/three"},
            ],
        },
    )

    assert media.media_type == "photo_carousel"
    assert media.media_url is None
    assert media.filename == "tiktok-7691561538561346837-photos.zip"
    assert len(media.assets) == 3
    assert [asset.kind for asset in media.assets] == ["photo", "photo", "photo"]
    assert media.assets[0].filename == "tiktok-7691561538561346837-01.jpg"


def test_cobalt_still_parses_picker_video() -> None:
    provider = CobaltProvider("http://cobalt:9000")
    media = provider._parse_response(
        "https://www.tiktok.com/@user/video/123",
        {
            "status": "picker",
            "picker": [
                {"type": "video", "url": "https://cdn.example/video.mp4"},
                {"type": "photo", "url": "https://cdn.example/photo.jpg"},
            ],
        },
    )

    assert media.media_type == "video"
    assert media.media_url == "https://cdn.example/video.mp4"
    assert media.assets == []
