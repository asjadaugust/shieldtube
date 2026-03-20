import yt_dlp


def resolve_stream(video_id: str, prefer_hdr: bool = True) -> dict:
    """Resolve a YouTube video ID into separate video and audio stream URLs."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
    }

    if prefer_hdr:
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

        return {
            "video_url": video_url,
            "audio_url": audio_url,
            "duration": info["duration"],
            "title": info["title"],
            "filesize": filesize if filesize > 0 else 100_000_000,
        }
