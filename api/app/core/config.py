from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Anchored to the package rather than the working directory, so scripts run
#: from the repo root read the same configuration the API does. Resolving it
#: relatively meant they silently fell back to defaults.
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """Application configuration, loaded from the environment / api/.env."""

    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://gym:gym@localhost:5432/gym"

    # Supabase signs access tokens with a rotating asymmetric key and publishes
    # the public half at <url>/auth/v1/.well-known/jwks.json. The API therefore
    # holds no secret capable of minting a token.
    supabase_url: str = "https://replace-me.supabase.co"

    # Photos (§9). Unset until a bucket exists; the photo endpoints then
    # return a clear 503 and the rest of the app is unaffected.
    supabase_storage_bucket: str | None = None
    # Server-side only. Bypasses row-level security, so it must never reach the
    # app — the device only ever sees short-lived signed URLs minted here.
    supabase_service_key: str | None = None

    allowed_origins: str = ""

    # Supabase signs access tokens with aud="authenticated".
    jwt_audience: str = "authenticated"
    # ES256 is Supabase's current default; RS256 covers projects on RSA keys.
    jwt_algorithms: list[str] = ["ES256", "RS256"]

    # How long a fetched JWKS stays usable before it is refetched. Supabase
    # rotates keys rarely, and PyJWKClient refetches on an unknown `kid` anyway.
    jwks_cache_seconds: int = 600

    sql_echo: bool = Field(default=False)

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def jwks_url(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

    @property
    def storage_url(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/storage/v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
