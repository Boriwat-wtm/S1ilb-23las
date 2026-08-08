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
    # "google" = Google Cloud Vision.
    ocr_provider: str = "none"
    google_vision_api_key: str = ""

    # --- category tagger ---
    # Only consulted when the ledger's own keyword table has no match, and its
    # answer is written back as a keyword, so cost decays toward zero.
    # "none" = a miss stays a miss and the user picks. "gemini" = Google Gemini.
    tagger_provider: str = "none"
    gemini_api_key: str = ""
    # Self-imposed ceilings, well under any provider's free tier. The point is
    # to degrade to "no suggestion" on our side rather than collect a 429 from
    # theirs — a quiet miss is invisible, a rate-limit error is not.
    tagger_max_per_minute: int = 8
    tagger_max_per_day: int = 200
    # Configurable because model ids get renamed and retired on Google's
    # schedule, not ours, and swapping one should not need a code change —
    # the previous default here, gemini-2.0-flash, has already been shut down.
    #
    # A flash-lite is the right size for this job: sorting a short shop name
    # into one of about ten well-separated categories is near the ceiling for
    # any current model, so a larger one buys almost no accuracy and costs
    # requests-per-minute, which is the resource that actually binds when a
    # stack of slips is uploaded at once.
    gemini_model: str = "gemini-3.5-flash-lite"

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
