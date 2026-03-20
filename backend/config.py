from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    backend_host: str = "0.0.0.0"
    backend_port: int = 8080
    cache_dir: str = "./cache"
    ffmpeg_threads: int = 2

    model_config = {"env_file": ".env"}


settings = Settings()
