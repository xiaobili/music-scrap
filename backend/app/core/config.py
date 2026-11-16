from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    music_roots: str = ""
    db_path: Path = BACKEND_DIR / "data" / "music-scrap.db"
    backup_dir: Path = BACKEND_DIR / "data" / "backups"
    secret_key: str = ""
    max_fetch_concurrency: int = 3
    enable_unofficial_providers: bool = False
    musicbrainz_user_agent: str = "music-scrap/0.1 (https://example.local/music-scrap)"
    log_level: str = "info"
    tz: str = "Asia/Shanghai"
    frontend_dist: Path = BACKEND_DIR.parent / "frontend" / "dist"

    @property
    def roots(self) -> list[Path]:
        return [Path(item).expanduser() for item in self.music_roots.split(":") if item.strip()]

    @property
    def effective_secret(self) -> str:
        return self.secret_key or "dev-insecure-secret-key-change-me"


@lru_cache
def get_settings() -> Settings:
    return Settings()
