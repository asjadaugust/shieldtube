from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    backend_host: str = "0.0.0.0"
    backend_port: int = 8080
    cache_dir: str = "./cache"
    ffmpeg_threads: int = 2
    db_path: str = "./shieldtube.db"

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""

    # Bootstrap token (alternative to device flow)
    youtube_access_token: str = ""
    youtube_refresh_token: str = ""

    # Thumbnail settings
    thumbnail_concurrency: int = 10

    # Download settings
    download_wait_timeout: int = 30

    # Security
    api_secret: str = ""
    token_encryption_key: str = ""

    model_config = {"env_file": ".env"}


settings = Settings()
