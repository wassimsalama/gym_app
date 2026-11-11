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

    #: Comma-separated browser origins allowed to call this API. Required in
    #: production; left empty, the app falls back to development origins only
    #: (see `dev_origin_regex`).
    allowed_origins: str = ""

    # Supabase signs access tokens with aud="authenticated".
    jwt_audience: str = "authenticated"
    # ES256 is Supabase's current default; RS256 covers projects on RSA keys.
    jwt_algorithms: list[str] = ["ES256", "RS256"]

    # How long a fetched JWKS stays usable before it is refetched. Supabase
    # rotates keys rarely, and PyJWKClient refetches on an unknown `kid` anyway.
    jwks_cache_seconds: int = 600

    # --- rate limiting ---------------------------------------------------
    #
    # Generous enough that no real person meets them: a determined logger might
    # make a few dozen requests an hour, not hundreds. They exist to stop
    # scripts and runaway retry loops, not to ration usage.
    rate_limit_enabled: bool = True
    #: Any request, keyed by client address. Catches unauthenticated flooding.
    rate_limit_ip_per_hour: int = 1200
    #: Reads by a signed-in user.
    rate_limit_read_per_hour: int = 600
    #: Writes by a signed-in user. Lower, since each one costs a database write.
    rate_limit_write_per_hour: int = 240

    #: Trust X-Forwarded-For. Set only when the API genuinely sits behind a
    #: proxy that overwrites it (Railway, Render, Cloudflare). Left on with no
    #: proxy in front, any client could spoof its address and evade every limit.
    trust_proxy_headers: bool = False

    #: Comma-separated Supabase user ids allowed to read /admin/metrics.
    #: Empty means nobody, which is the safe default — an unset variable must
    #: never mean "everyone".
    admin_user_ids: str = ""

    sql_echo: bool = Field(default=False)

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def admins(self) -> set[str]:
        return {a.strip() for a in self.admin_user_ids.split(",") if a.strip()}

    @property
    def is_production(self) -> bool:
        """Configured with real browser origins, i.e. not a developer machine.

        Reuses `allowed_origins` rather than introducing a separate flag: it is
        already the switch that turns off `dev_origin_regex`, and a second
        variable is a second thing to forget to set on the host.
        """
        return bool(self.origins)

    @property
    def dev_origin_regex(self) -> str | None:
        """Localhost and private-LAN origins, for development only.

        Returned only when `allowed_origins` is unset, so configuring a
        production origin list switches this off entirely. It is safe even if
        left on: a browser sends the *page's* own origin, and an attacker's
        page is served from a public domain, never from localhost or 192.168.x.
        """
        if self.origins:
            return None
        return (
            r"^http://(localhost|127\.0\.0\.1|"
            r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
            r"192\.168\.\d{1,3}\.\d{1,3}|"
            r"172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(:\d+)?$"
        )

    @property
    def jwks_url(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

    @property
    def storage_url(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/storage/v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
