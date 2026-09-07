from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, loaded from the environment / api/.env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://gym:gym@localhost:5432/gym"

    # Supabase signs access tokens with a rotating asymmetric key and publishes
    # the public half at <url>/auth/v1/.well-known/jwks.json. The API therefore
    # holds no secret capable of minting a token.
    supabase_url: str = "https://replace-me.supabase.co"

    # Phase 4 — photos. Unset until then.
    s3_bucket: str | None = None
    aws_region: str | None = None

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
