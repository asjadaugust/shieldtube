import yt_dlp

QUALITY_FORMATS = {
    "4K_HDR": "bestvideo[vcodec=vp09.02][height<=2160]+bestaudio/bestvideo[height<=2160]+bestaudio/best",
    "4K": "bestvideo[height<=2160]+bestaudio/best",
    "1080p": "bestvideo[height<=1080]+bestaudio/best",
    "720p": "bestvideo[height<=720]+bestaudio/best",
    "auto": None,  # Use existing HDR-preference logic
}


def resolve_stream(video_id: str, prefer_hdr: bool = True, quality: str = "auto") -> dict:
    """Resolve a YouTube video ID into separate video and audio stream URLs."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
    }

    if quality != "auto" and quality in QUALITY_FORMATS:
        opts["format"] = QUALITY_FORMATS[quality]
    elif prefer_hdr:
        opts["format"] = (
            "bestvideo[vcodec=vp09.02][height<=2160]+bestaudio/"
            "bestvideo[vcodec^=vp9][height<=2160]+bestaudio/"
            "bestvideo[height<=2160]+bestaudio/best"
        )
    else:
        opts["format"] = (
            "bestvideo[ext=webm][vcodec^=vp9]+bestaudio[ext=webm]/"
            "bestvideo[height<=2160]+bestaudio/best"
        )

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(
            f"https://www.youtube.com/watch?v={video_id}",
            download=False,
        )
        if "requested_formats" in info:
            video_fmt = info["requested_formats"][0]
            audio_fmt = info["requested_formats"][1]
            video_url = video_fmt["url"]
            audio_url = audio_fmt["url"]
            filesize = (
                (video_fmt.get("filesize") or video_fmt.get("filesize_approx") or 0)
                + (audio_fmt.get("filesize") or audio_fmt.get("filesize_approx") or 0)
            )
        else:
            video_url = info["url"]
            audio_url = None
            filesize = info.get("filesize") or info.get("filesize_approx") or 0

        # Build subtitle map: prefer manual subtitles over automatic captions.
        # Within each language prefer vtt format; fall back to first available format.
        subtitles: dict = {}
        for lang, subs in (info.get("subtitles") or {}).items():
            for sub in subs:
                if sub.get("ext") == "vtt":
                    subtitles[lang] = {
                        "url": sub["url"],
                        "ext": "vtt",
                        "name": sub.get("name", lang),
                    }
                    break
            if lang not in subtitles and subs:
                subtitles[lang] = {
                    "url": subs[0]["url"],
                    "ext": subs[0].get("ext", "vtt"),
                    "name": subs[0].get("name", lang),
                }

        for lang, subs in (info.get("automatic_captions") or {}).items():
            if lang not in subtitles:
                for sub in subs:
                    if sub.get("ext") == "vtt":
                        subtitles[lang] = {
                            "url": sub["url"],
                            "ext": "vtt",
                            "name": f"{sub.get('name', lang)} (auto)",
                            "auto": True,
                        }
                        break

        return {
            "video_url": video_url,
            "audio_url": audio_url,
            "duration": info["duration"],
            "title": info["title"],
            "filesize": filesize if filesize > 0 else 100_000_000,
            "chapters": info.get("chapters") or [],
            "subtitles": subtitles,
        }
