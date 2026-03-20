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
        return {
            "video_url": info["requested_formats"][0]["url"],
            "audio_url": info["requested_formats"][1]["url"],
            "duration": info["duration"],
            "title": info["title"],
        }
