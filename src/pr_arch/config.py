from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    github_token: str | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    
    data_dir: Path = Path(".pr-arch")

    @property
    def db_path(self) -> Path:
        """Path to the single SQLite database file."""
        return self.data_dir / "memory.db"

    @property
    def raw_dir(self) -> Path:
        """Directory for content-addressed raw artifacts."""
        return self.data_dir / "raw"


def load_settings() -> Settings:
    return Settings()