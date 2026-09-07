"""Outbound TLS trust.

Auth depends on an outbound HTTPS fetch (the Supabase JWKS), so the trust store
is pinned explicitly rather than inherited from whatever the host image happens
to ship. Without this the python.org macOS builds have no CA store at all, and
the JWKS fetch fails in a way that is indistinguishable from a forged token.
"""

import ssl
from functools import lru_cache

import certifi


@lru_cache
def default_ssl_context() -> ssl.SSLContext:
    """A verifying TLS context backed by certifi's CA bundle."""
    return ssl.create_default_context(cafile=certifi.where())
