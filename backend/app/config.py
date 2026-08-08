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
    # "none" = a miss stays a miss and the user picks.
    # "gemini" = Google's AI Studio API, which serves both Gemini and Gemma.
    tagger_provider: str = "none"
    gemini_api_key: str = ""

    # Gemma, not Gemini — same endpoint, very different free tier.
    #
    # Measured on a real key against ten deliberately awkward Thai shop names,
    # three runs each:
    #
    #   gemma-4-26b-a4b-it     10, 10, 10   1.71 s   30 RPM   14,400 RPD
    #   gemini-3.1-flash-lite   8,  6,  8   1.10 s   15 RPM      500 RPD
    #   gemini-3.5-flash-lite   7,  6       1.17 s   15 RPM      500 RPD
    #   gemma-4-31b-it         unusable — ignores responseSchema entirely
    #
    # The small Gemma wins on both axes at once: twenty-eight times the daily
    # allowance, and the only one that answered identically on every run even
    # though all of them were called at temperature 0. The larger Gemma is the
    # reminder that bigger is not automatically better — it cannot produce
    # structured output here at all, which is the thing keeping wrong
    # categories out.
    #
    # Configurable because ids get renamed and retired on Google's schedule,
    # not ours: the first default here, written from memory, was
    # gemini-2.0-flash, which had already been shut down.
    gemini_model: str = "gemma-4-26b-a4b-it"

    # Self-imposed ceilings, deliberately under the provider's. Better to
    # degrade to "no suggestion" on our side than collect a 429 from theirs —
    # a quiet miss is invisible, a rate-limit error is not. Roughly 7% of the
    # measured daily allowance, still far beyond what this app can use once
    # the keyword table starts filling in.
    tagger_max_per_minute: int = 20
    tagger_max_per_day: int = 1000

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
