#!/usr/bin/env python3
"""Prove the photo pipeline works against the real bucket.

Round-trips a tiny image exactly as the app does — sign, upload, sign a view,
download, delete — then verifies it is gone. Run it once after creating the
bucket; if it passes, the Photos tab will work.

    python scripts/check_storage.py
"""

from __future__ import annotations

import sys
import urllib.request
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "api"))

from app.core import storage  # noqa: E402
from app.core.certs import default_ssl_context  # noqa: E402
from app.core.config import get_settings  # noqa: E402

# A 1x1 JPEG. Small enough to be free, real enough to be a genuine upload.
TINY_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb004300ffffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffc00011080001000103"
    "012200021101031101ffc4001f0000010501010101010100000000000000000102030405"
    "060708090a0bffc400b5100002010303020403050504040000017d0102030004110512213"
    "1410613516107227114328191a1082342b1c11552d1f02433627282090a161718191a2526"
    "2728292a3435363738393a434445464748494a535455565758595a636465666768696a737"
    "475767778797a838485868788898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5"
    "b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9eaf1f2f3f"
    "4f5f6f7f8f9faffda0008010100003f00fbfe8a28a2803fffd9"
)


def fail(message: str) -> None:
    print(f"  FAIL  {message}")
    raise SystemExit(1)


def main() -> int:
    settings = get_settings()

    print(f"project : {settings.supabase_url}")
    print(f"bucket  : {settings.supabase_storage_bucket or '(unset)'}")

    if not storage.is_configured():
        fail(
            "SUPABASE_STORAGE_BUCKET and SUPABASE_SERVICE_KEY are not both set "
            "in api/.env. See .env.example."
        )

    user_id = uuid.uuid4()
    key = storage.build_key(user_id)
    print(f"key     : {key}\n")

    print("1. signing an upload URL")
    upload_url = storage.presign_upload(key, "image/jpeg")
    print("   ok")

    print("2. uploading, as the device would")
    request = urllib.request.Request(
        upload_url, data=TINY_JPEG, method="PUT",
        headers={"Content-Type": "image/jpeg"},
    )
    with urllib.request.urlopen(request, context=default_ssl_context()) as response:  # noqa: S310
        if response.status not in (200, 201):
            fail(f"upload returned {response.status}")
    print("   ok")

    print("3. signing a view URL")
    view_url = storage.presign_view(key)
    print("   ok")

    print("4. downloading it back")
    with urllib.request.urlopen(view_url, context=default_ssl_context()) as response:  # noqa: S310
        downloaded = response.read()
    if downloaded != TINY_JPEG:
        fail(f"downloaded {len(downloaded)} bytes, expected {len(TINY_JPEG)}")
    print(f"   ok — {len(downloaded)} bytes, byte-identical")

    print("5. checking the bucket is private")
    unsigned = view_url.split("?")[0]
    try:
        with urllib.request.urlopen(unsigned, context=default_ssl_context()) as response:  # noqa: S310
            if response.status == 200:
                fail(
                    "the object is readable WITHOUT a signature — the bucket is "
                    "public. Turn off 'Public bucket' in the Supabase dashboard."
                )
    except urllib.error.HTTPError as exc:
        if exc.code not in (400, 401, 403, 404):
            fail(f"unexpected status {exc.code} on the unsigned URL")
    print("   ok — unsigned access refused")

    print("6. deleting the prefix, as account deletion would")
    removed = storage.delete_prefix(f"{user_id}/")
    print(f"   ok — removed {removed}")

    print("\nStorage is working. The Photos tab is good to go.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
