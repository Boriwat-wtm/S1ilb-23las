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

    # Two models, pooled. Gemma, not Gemini — same endpoint, very different
    # free tier.
    #
    # Measured on a real key against ten deliberately awkward Thai shop names,
    # three runs each:
    #
    #   gemma-4-26b-a4b-it     10, 10, 10   1.71 s   30 RPM   14,400 RPD
    #   gemma-4-31b-it          8/10         2.14 s   30 RPM   14,400 RPD
    #   gemini-3.1-flash-lite   8,  6,  8    1.10 s   15 RPM      500 RPD
    #   gemini-3.5-flash-lite   7,  6        1.17 s   15 RPM      500 RPD
    #   gemini-3.5 / 3.6 flash    —            —       5 RPM       20 RPD
    #
    # Both Gemma variants have their own 30/16K per minute on the same key, so
    # pooling them doubles throughput without a second vendor. The 26B leads,
    # the 31B is the understudy.
    #
    # Note on the 31B: it only works with responseSchema set. Given just
    # responseMimeType, or nothing, it answers in prose and never produces
    # usable JSON. An earlier note here called it unusable outright — that was
    # a bug in the throwaway test script, which parsed with json.loads instead
    # of the fence-tolerant helper the real code uses.
    #
    # Configurable because ids get renamed and retired on Google's schedule,
    # not ours: the first default here, written from memory, was
    # gemini-2.0-flash, which had already been shut down.
    gemini_models: str = "gemma-4-26b-a4b-it,gemma-4-31b-it"

    # Per model, per minute — read off the account's own dashboard. Hitting
    # either puts that model to sleep for the cooldown rather than letting the
    # next call collect a 429.
    tagger_requests_per_minute: int = 30
    tagger_tokens_per_minute: int = 16_000
    tagger_cooldown_seconds: float = 90.0

    # A whole-day stop, well under the 14,400 the account allows, so a runaway
    # loop cannot burn the allowance while nobody is watching.
    tagger_max_per_day: int = 1000

    @property
    def gemini_model_list(self) -> list[str]:
        return [m.strip() for m in self.gemini_models.split(",") if m.strip()]

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
