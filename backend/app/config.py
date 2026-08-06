from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- database (Neon) ---
    database_url: str = "postgresql://user:pass@localhost:5432/bank"

    # --- auth ---
    jwt_secret: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    # long-lived on purpose: a PWA that logs you out every hour gets abandoned
    jwt_expire_days: int = 30

    # --- cors ---
    # comma-separated. In prod set to the Vercel domain only.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- slip storage (Supabase Storage, private bucket) ---
    supabase_url: str = ""
    supabase_service_key: str = ""
    supabase_bucket: str = "slips"
    signed_url_ttl_seconds: int = 3600
    # slips get downscaled + EXIF-stripped before they ever leave the server
    slip_max_edge_px: int = 1200
    slip_jpeg_quality: int = 75

    # --- ocr ---
    # "none" = no extraction, the form just opens blank (manual entry).
    # "google" = Google Cloud Vision, wired later.
    ocr_provider: str = "none"
    google_vision_api_key: str = ""

    # --- display ---
    app_timezone: str = "Asia/Bangkok"

    @property
    def sqlalchemy_url(self) -> str:
        """Neon hands out `postgresql://...`; SQLAlchemy needs the psycopg3 driver."""
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def storage_enabled(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
