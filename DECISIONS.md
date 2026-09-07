# Decisions

A running log of choices that shaped the build, so the reasoning survives past
the commit that made it. Format: date, decision, reason.

Anything marked **needs Wes** is an agent-level call made to keep Phase 0
moving; say the word and it gets reversed.

---

## 2026-09-07 — Repo lives at `projects/gym_app`, flattened after a GitKraken nesting

A GitKraken operation mid-scaffold nested the tree inside itself
(`gym_app/gym_app`) and attached the `origin` remote to the inner copy. Wes
chose to flatten: inner contents lifted one level, inner `.git` kept (it holds
`origin`), outer empty `.git` removed. Neither repo had commits, so no history
was at risk. The removed `.git` was backed up to the session scratchpad first.

## 2026-09-07 — JWT verification moved from HS256 to JWKS/ES256 — **approved by Wes**

Spec §10 specifies HS256 against `SUPABASE_JWT_SECRET`. The project Wes created
signs access tokens with an ES256 key and publishes the public half as a JWKS,
which is Supabase's current default — so HS256 verification returned 401 on
every real token.

A misleading intermediate step is worth recording: the project's legacy `anon`
API key *is* HS256 and *does* verify against the legacy secret, which made it
look like HS256 was correct. That key is an artifact minted at project creation
and says nothing about how user access tokens are signed. Only a real access
token settled it. Lesson: verify the thing you actually care about, not a proxy
for it.

The API now fetches the project's public keys via `PyJWKClient` (cached, with
refetch on an unknown `kid`, so key rotation needs no redeploy) and verifies
ES256/RS256. `SUPABASE_JWT_SECRET` is gone from `api/.env`; `SUPABASE_URL`
replaces it. The API now holds nothing capable of minting a token — a leaked
backend environment cannot be used to impersonate a user, which the shared
secret would have allowed.

Adds `pyjwt[crypto]` (pulls `cryptography`). Spec §10 should be updated to match.

## 2026-09-07 — certifi pins the outbound CA bundle — **approved by Wes**

Auth now depends on an outbound HTTPS fetch, and the python.org macOS build has
no CA store, so the JWKS fetch failed with `CERTIFICATE_VERIFY_FAILED`. That
surfaces as a 401 "Invalid token" — indistinguishable from a forged token,
which is right for attackers but hides infrastructure faults.

Rather than depend on whatever CA store the host image ships, `app/core/certs.py`
pins certifi's bundle for all outbound TLS. `scripts/seed_exercises.py`, which
had its own copy of this workaround, now shares it.

## 2026-09-07 — Chart library: `react-native-gifted-charts`

Spec §11 offers gifted-charts or victory-native and asks for one reason.
victory-native XL renders through `@shopify/react-native-skia`, which needs a
custom dev build — but the Phase 0 and Phase 1 acceptance criteria are both
"on a physical phone via Expo Go". gifted-charts only needs `react-native-svg`,
which Expo Go ships. Not yet installed; it arrives with the Phase 1 weight chart.

## 2026-09-07 — PyJWT for token verification — **superseded, now approved**

§10 says verify the Supabase JWT (HS256) and "do not hand-roll auth", but §14.1
item 2 wants new dependencies cleared. PyJWT is the standard way to satisfy the
former and the only non-hand-rolled option, so it went in rather than blocking
the phase. It is a single well-maintained library with no transitive weight.

## 2026-09-07 — `@expo/vector-icons` for tab bar icons — **needs Wes**

Same §14.1 item 2 caveat. It is the default Expo icon set (already vendored
into most Expo apps) and the alternative was a tab bar with no icons. Cosmetic
and trivially removable.

## 2026-09-07 — Bundle identifier `com.wassimsalama.gymapp` — **needs Wes**

Needed in `app.json` for any EAS build. Freely changeable until the first
TestFlight upload; flagged because §14.1 item 10 covers store metadata.

## 2026-09-07 — Web export set to SPA (`web.output: "single"`)

Static rendering executes `lib/auth.ts` at build time, where `expo-secure-store`
has no implementation and Node 20 has no global `WebSocket`. Web is not a v1
target (§1), but SPA output keeps `expo export -p web` working as a cheap
bundling smoke test. No effect on iOS or Android.

## 2026-09-07 — Chunked SecureStore adapter for the Supabase session

`expo-secure-store` rejects values much over 2 KB and a Supabase session
(access token + refresh token + user object) regularly exceeds it. The session
is split across numbered chunks with a count key. Without this, sign-in appears
to work and then silently fails to persist across a cold start.

## 2026-09-07 — `lib/dates.ts` alongside `lib/units.ts`

§6 requires the client to send its own local date and the server never to derive
"today" from UTC. `toISOString()` would roll the date over for anyone west of
UTC in the evening, so local dates are built from calendar fields. §11 sanctions
"a single date util"; this is it.

## 2026-09-07 — Seed script uses certifi's CA bundle

The python.org macOS build ships without a wired-up CA store, so
`urllib` fails on a clean machine. The script prefers `certifi.where()` and
falls back to the system default, rather than depending on the host's SSL setup.
