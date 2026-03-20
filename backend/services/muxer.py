import subprocess
from pathlib import Path


def mux_streams(video_url: str, audio_url: str | None, output_path: Path) -> Path:
    """Mux separate video+audio DASH streams into single MP4 via FFmpeg stream copy."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = ["ffmpeg", "-y", "-i", video_url]
    if audio_url is not None:
        cmd += ["-i", audio_url]
    cmd += [
        "-c:v", "copy",
        "-c:a", "copy",
        "-movflags", "+faststart+frag_keyframe",
        "-f", "mp4",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg muxing failed: {result.stderr}")

    return output_path
