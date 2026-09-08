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

## 2026-09-08 — `app/.env.production` is committed, on purpose

Cloudflare's hosted build kept failing because it was not passing build-time
variables to the build step, and the difference between its "build variables"
and "runtime variables" is not visible from a failure. Two attempts at
configuring it correctly did not stick.

Rather than keep guessing at a vendor UI, the dependency was removed: the file
is now in git.

This is safe because none of it is secret. `EXPO_PUBLIC_*` values are inlined
into the JavaScript every visitor downloads — verified by pulling the anon key
straight out of the live site's bundle, where it already sits. Keeping them out
of version control protects nothing and breaks any host that does not thread
build variables through.

Row level security is what makes publishing the anon key safe. Before migration
`0003` it granted read and write access to every table; now it grants nothing.

The boundary that matters is unchanged and stated in the file's header: the
`service_role` key, the database password and the JWT secret are server-side
only, live in Railway's variables, and never enter this repository.

## 2026-09-08 — Row level security: the API could be bypassed entirely — **found by Wes**

Wes asked whether RLS was needed. It was, urgently, and nothing else built so
far would have helped.

The database lives inside a Supabase project, and Supabase publishes every
`public` table over PostgREST at `/rest/v1/<table>`, authorised by the anon key.
That key is public by design — it ships inside the web bundle. With RLS off,
anyone who opened the site's JavaScript could read and write every table
directly, never touching this application.

Verified before fixing, using only the anon key:

    GET  /rest/v1/daily_logs   -> 200
    GET  /rest/v1/profiles     -> 200
    POST /rest/v1/exercises    -> 201 Created

The 19 cross-user authorisation tests written an hour earlier proved the API's
own endpoints were watertight, and were completely beside the point on this
path. Authorisation you can walk around is not authorisation. Worth remembering
that a proof only covers the route it tested.

Migration 0003 enables RLS on every table with **no policies**. That denies
everything to the `anon` and `authenticated` roles while leaving the API
untouched, because it connects as the table owner and owners bypass RLS.

Deliberately no per-user policies. They would restate this application's
authorisation rules in a second language, free to drift out of step with the
first, to guard a path that should not be reachable at all. Shutting the door
is simpler than furnishing the room behind it.

`check_config.py` now probes the REST API with the app's own anon key and fails
if any table returns rows — the check that would have caught this on day one.

## 2026-09-08 — Production web builds are verified, not trusted

The first production build came out pointing at `http://192.168.1.25:8000` —
the laptop's LAN address. It would have loaded perfectly on Cloudflare Pages
and failed every request for every user, with a "could not reach the server"
message aimed at their connection.

Two causes, both invisible:

1. Setting `EXPO_PUBLIC_*` on the command line does not override `.env`. Expo
   loads the file and exports those variables over the top.
2. Metro caches the Babel transform that inlines them, so even after fixing
   the environment the bundle kept the old value until `--clear`.

Production values now live in `app/.env.production`, and `npm run build:web`
builds with the cache cleared and then reads the bundle back, rejecting it if
it finds a private LAN address, or if the production API URL, Supabase URL or
privacy page are missing.

The check distinguishes LAN addresses from `localhost` deliberately. A private
IP is never a dependency's default, so its presence always means our
configuration leaked in. `localhost` does appear in dependencies — gotrue-js
carries an unused `http://localhost:9999` fallback — so flagging it outright
produced a false positive on a perfectly good build. A check that cries wolf
gets switched off.

Verified both directions: it passes the real build and rejects the same build
with a LAN address spliced in.

## 2026-09-07 — Sign-in throttling, and being honest about what it is

Wes asked for protection against someone repeatedly guessing a user's password.

Built: per-email, per-device progressive lockout in the sign-in form — four
free attempts, then 30s, 60s, 5m, 15m, counting down visibly so the person
locked out knows what is happening rather than watching a dead form.

**It is a deterrent, not a security control, and the code says so.** An
attacker guessing passwords does not use the form; they call Supabase's auth
endpoint directly, where none of this runs. Claiming otherwise would be worse
than not building it, because it invites the belief that the problem is
handled.

What it genuinely buys: someone poking at a friend's account on a shared laptop
gives up, a stuck client cannot loop against the auth endpoint, and a locked-out
user gets told why.

The real defences are all Supabase dashboard settings and all free — per-IP
auth rate limits, leaked-password protection via HaveIBeenPwned, a raised
minimum password length, and a CAPTCHA. Turnstile is the one that actually
defeats automated guessing rather than slowing it, and it is free on the
Cloudflare account already in use. Documented in DEPLOY.md; enabling CAPTCHA
needs a small client change to pass the token.

Storage failures degrade to no throttling rather than blocking sign-in. A
device with storage disabled should still be able to log in.

## 2026-09-07 — Password reset and a reveal toggle — **Wes's request**

§10 specified email/password sign-in and said nothing about recovery, so the
app shipped with no way back in for anyone who forgot their password. Fine
while Wes was the only user; not fine for family and friends.

Added: a forgot-password screen, an emailed reset link, a screen to set the new
password, and change-password for someone already signed in. Every password
field can now be unmasked — typing a password blind on a phone keyboard is how
people lock themselves out, and masking by default with an opt-in reveal costs
nothing.

One structural detail worth recording. `reset-password` sits at the top level,
outside both auth guards, because clicking the emailed link *creates a
session* — a screen gated on not having one would have bounced the user away
before they could type anything. That would have been an intermittent,
baffling bug.

The reset request resolves identically whether or not the address has an
account. Distinguishing them would let a stranger enumerate which emails are
registered.

Requires Supabase → Authentication → URL Configuration to list the redirect
URL, or the link is refused and it looks like a mail delivery problem.

## 2026-09-07 — Dashboard cut from 23 database round trips to 8

Measuring the region problem turned up the underlying issue: the endpoint asked
the database separately for every service it fed, including an N+1 in recent
PRs — one query per exercise found.

Latency multiplies by the number of trips, not the amount of data, so this is
invisible on a local socket and ruinous across a continent. It is now two
windowed reads (daily logs; sessions joined to sets and exercises) plus two
small aggregates, with every service deriving its answer from those in memory.
The row counts are tiny — a year of daily logs is 365 rows — so moving the work
out of SQL costs nothing.

    23 trips at 250 ms:  5.75 s
     8 trips at 250 ms:  2.00 s
     8 trips at   2 ms:  0.02 s

The remaining eight are: the auth profile lookup, the activity upsert, the
goal, two windowed reads, session dates (quick-logs have no sets, so they need
their own scan), and two PR baselines at different cutoffs.

All 335 tests passed unchanged across the rewrite, which is the evidence the
behaviour is identical — the point of having them.

Co-location remains the real fix; this is the optimisation that makes the
co-located case comfortable rather than merely adequate.

## 2026-09-07 — Region matters more than it looks: 23 round trips per dashboard

Wes's first Supabase project was in Seoul, chosen without thinking about it.
Measuring rather than assuming showed why that would have been painful: one
dashboard load makes **23 database round trips**, so latency between the API
and the database is multiplied by 23 on every page.

    at   2 ms per round trip:   0.05 s
    at 250 ms per round trip:   5.75 s

§12 allows one second. Co-located it is comfortable; split across continents it
is six times over before any work happens.

User latency behaves differently — one round trip per page — so the rule is:
put the API and database in the same region, and put that region near the
users. Users are mainly in Canada with some in the Middle East, and Railway has
no Canadian region, so `us-east-1` + `us-east4` (both Virginia) wins.
`ca-central-1` would keep data in Canada at the cost of ~350 ms per load.

Worth noting the endpoint could also be made less chatty — 23 queries is more
than it needs — and that would be better engineering regardless. But even five
queries at 250 ms is 1.25 s, so co-location is the fix and query batching is an
optimisation.

## 2026-09-07 — Privacy policy jurisdiction corrected

The policy was written citing UK GDPR and the ICO. I inferred that and never
checked; the users are actually in Canada and the Middle East. Now references
PIPEDA and the Office of the Privacy Commissioner of Canada, notes that local
law elsewhere is honoured too, and states plainly that the data is stored in the
United States because that is where the processors run. All three processors
are named rather than described vaguely.

A privacy policy asserting the wrong regulator is worse than a vague one — it
looks authoritative while being wrong.

## 2026-09-07 — Hosting: Cloudflare Pages, Railway, Supabase — **Wes's call**

- **Web on Cloudflare Pages.** Free, and `expo export --platform web` produces
  exactly the static folder it wants. The domain is on the same account.
- **API on Railway**, ~$5/month. Render's free tier was rejected outright: it
  sleeps after 15 minutes and a first visitor waits 30–60 seconds, which is how
  a "try my app" link dies. Cloud Run would have been near-free with a 1–3
  second cold start; Wes chose always-on simplicity over saving £4.
- **Database on the existing Supabase Postgres** rather than a fourth service.
  §3 allows it, it costs nothing, and it is already provisioned.

Two production details that are easy to get wrong and fail confusingly:

`TRUST_PROXY_HEADERS` must be **true** on Railway. It is a proxy, so without it
every request appears to come from the same address and the per-address rate
limit throttles all users collectively.

`ALLOWED_ORIGINS` must be set to the real site origin. Left unset, the API
falls back to allowing localhost only — so the deployed site is blocked by CORS
and every request reports "could not reach the server", pointing at the network
rather than at configuration. Verified by running the built image with a
production origin: the real origin is allowed and localhost is refused, which
is the fallback correctly switching itself off.

## 2026-09-07 — The web becomes the target; App Store dropped — **Wes's call**

Wes decided not to pay for the Apple Developer Program and will host the app as
a website instead. This reverses several things the spec fixed, recorded here
so nothing rots silently:

- §1's non-goal "no analytics SDKs" — analytics are now wanted (first-party
  only; see below).
- §3's "iOS first, Android later, web never" — the web is now the only target.
- §13's App Store checklist is moot. The account-deletion work stays: it is
  good practice and the GDPR expectation for a hosted app regardless.

Three things had to change for the web to work at all:

1. **Session storage.** `expo-secure-store` has no browser implementation, so
   the session throws on load. Split into `lib/sessionStorage.ts`: keychain on
   native, guarded `localStorage` on web. Guarded because private browsing makes
   every call throw, and a session that cannot persist should mean signing in
   again rather than a blank page.
2. **The offline queue.** `expo-sqlite@57.0.2` has a broken web build — its
   worker imports `wa-sqlite.wasm`, which the package does not ship. The queue
   now sits behind `lib/queueStore.ts` with an IndexedDB sibling for web.
   IndexedDB rather than localStorage specifically because a queue is written
   from every open tab, and localStorage's read-modify-write would let two tabs
   clobber each other's pending writes. The read cache does use localStorage —
   losing a cached read costs a spinner, losing a queued write costs a workout.
3. **Layout.** Every screen was laid out at phone width. Stretched across a
   monitor, the inputs became metre-wide. `components/AppFrame.tsx` holds the
   app to a 560 px centred column on web and is a no-op on native — cheaper and
   more honest than maintaining two layouts.

Verified in a real browser rather than by building alone: the page loads with no
console errors, styles apply, the frame centres with 360 px gutters at 1280 px
with no horizontal scroll, and IndexedDB behaves as the queue expects.

## 2026-09-07 — Photos use Supabase Storage, not S3 — **approved by Wes**

§3 and §9 specify S3 with presigned URLs. Supabase Storage was chosen instead:
the project already exists, the model is identical (private bucket, signed URLs
both directions, bytes never touching the API), and it avoids standing up an
AWS account, a credit card and IAM for one bucket.

A §14.1 item 6 stack deviation. The cost of reversing it is one file:
`app/core/storage.py` is the entire difference, and all 17 photo and account
tests passed unchanged across the swap — which is the evidence the boundary is
in the right place. §9's other rules are unaffected: keys stay
`{user_id}/{uuid}.jpg`, uploads are content-type restricted, view URLs live an
hour, and account deletion still sweeps by prefix.

`boto3` came out again; `httpx` moved from a dev dependency to a runtime one.

The service-role key is server-only and bypasses row-level security, so it
lives in `api/.env` and must never reach `app/.env`. Storage failures are
mapped to a bare 502 rather than passed through, because the provider's
response body can echo the key.

## 2026-09-07 — Settings resolve `.env` from the package, not the CWD

Found by running `scripts/check_storage.py` from the repo root: it printed
`replace-me.supabase.co` because pydantic-settings resolved `.env` relative to
the working directory and silently fell back to defaults. Any script run from
anywhere but `api/` was reading the wrong configuration — quietly, which is the
dangerous part.

## 2026-09-07 — `GET /dashboard?date=` — **approved by Wes**

§6 forbids the server deriving "today" from UTC, and specifies `GET /dashboard`
with no parameters. Those two are compatible until Phase 3: streaks are a
rolling 14-day count, volume rings are Monday-anchored, and the recap covers
the last completed Mon–Sun week — all need a real calendar day that only the
device knows.

The client now sends its local date, matching how `PUT /daily-logs/{date}`
already works. A §14.1 item 3 contract change; §6 should gain the parameter.
The alternative considered was storing a timezone on `profiles`, rejected
because it is a schema change that also goes stale the moment the user travels.

## 2026-09-07 — Weekly set targets live in `app/services/config.py`

§7.6 specifies 10 sets for the big groups and 6 for arms, calves and core, and
notes these become user-configurable later. Gathering them in one module is
what makes that a small change rather than a search-and-replace. Glutes were
put at 10 alongside the other large groups; the spec lists them among the
muscle groups but does not state a target.

## 2026-09-07 — TDEE reads ~90 kcal low in a user's first three weeks

A documented limitation of §7.2's method rather than a defect. The 7-day
average needs about six days to warm up, so a 21-day window that begins at the
user's very first weigh-in carries that ramp inside it and fits a flatter slope
than reality. Measured: exact from 28 days of history onwards, and under
150 kcal low before that.

Understating maintenance is the safer direction to be wrong in, and the card
says "collecting data" for the first fortnight anyway. Pinned by a test so it
cannot drift further.

## 2026-09-07 — Phase 2: what the offline queue does and does not carry — **needs Wes**

§8.1 says *all* writes go through the queue. Two do not, for reasons that are
about correctness rather than convenience:

- **Creating a custom exercise** returns the generated id that the session's
  sets hang from. Queueing it would mean inventing temporary ids and rewriting
  them on flush — real complexity for a rare action. Logging against exercises
  that already exist works fully offline.
- **Goals** are configuration, set once during onboarding, and the caller needs
  the created row back to proceed. Onboarding cannot complete offline anyway.

Daily logs and workout sessions — the writes that actually happen in a basement
gym with no signal — are queued.

The queue also **drops** operations the server rejected outright (4xx other
than timeouts). A 422 will still be a 422 tomorrow; retrying it forever would
block everything behind it and leave a permanent "unsynced" badge the user has
no way to clear.

§8 also says the queue is mandatory *before any logging UI is built*, while §12
schedules it in Phase 2 — so Phase 1's weight logging shipped without it. It is
retrofitted through the queue now.

## 2026-09-07 — A stale baseline now offers its own fix; `goal` block gained two fields — **needs Wes**

Reported as "the progress bar says 0". The arithmetic was right and the outcome
was still broken. Wes onboarded at 200 lb, set a 170 lb target, then logged
230 lb — so the baseline sat 30 lb behind him. The bar clamps to 0% and, worse,
*stays* there: losing 20 lb still reads 0%, because progress is measured from
200 lb. Real progress would have been invisible for weeks.

Re-anchoring already existed (`POST /goals`) but was buried inside the goal
editor, so the app never offered it in the one state that needs it. The goal
card now detects the case and offers a one-tap restart from the current weight,
keeping the same target.

To let the home tab explain the same thing inside §6's single request, the
dashboard `goal` block now also carries `start_weight_kg` and `goal_weight_kg`.
Additive, but still a §14.1 item 3 contract change — §6 should be updated.

The clamp itself stays. A progress bar cannot draw -233%, and un-clamping would
trade an unhelpful number for a nonsensical one.

## 2026-09-07 — `PATCH /goals/active` added to the contract — **needs Wes**

§6 defines only `POST /goals` and `GET /goals/active`, so there was no way to
change a target. Wes asked for one. Reusing POST would have been wrong: it
re-derives the start weight from the latest log, so nudging a target from 80 kg
to 78 kg would silently reset the baseline and wipe out visible progress.

The two operations are now distinct, and the editor presents them as such:

- `PATCH /goals/active` — move the target. `start_weight_kg` and `start_date`
  are untouched and the schema refuses them outright.
- `POST /goals` — start over, re-anchoring on the current weight. Progress
  resets, deliberately, behind a confirmation step.

This is a §14.1 item 3 contract addition. §6 should gain the endpoint.

## 2026-09-07 — A 0% progress bar now explains itself

Reported as a bug, and it was — just not in the arithmetic. Wes's latest weight
sat 15.87 kg above the weight his goal started from, so `progress_pct` clamped
to 0 and rendered an empty bar with nothing to explain it. Correct, and
indistinguishable from something broken.

The goal card now shows start, now and goal side by side, and says explicitly
when the current weight is the wrong side of the baseline. The clamp stays: a
progress bar cannot draw -233%.

## 2026-09-07 — Phase 1: onboarding ships without the optional starting photo — **needs Wes**

§12 Phase 1 lists "Onboarding flow (current weight, goal weight, optional photo)",
but the entire photo pipeline — private bucket, presigned PUT/GET, client-side
compression — is Phase 4 (§9). Building a one-off photo path for onboarding
would mean either shipping a second storage mechanism or pulling Phase 4 work
forward.

Onboarding therefore collects the two weights only. This is a deliberate scope
deferral under §14.1 item 9, not an oversight: say the word and it moves either
way. The natural fix is to add the photo step when Phase 4 lands, at which point
it is a few lines rather than a parallel implementation.

## 2026-09-07 — Goal projection formula — **needs Wes**

§6 and §2.4 fix the *shape* (`progress_pct`, `projected_date`, `on_track`) but
no formula, and §14.1 item 8 makes engine formulas Wes's call — so these are
proposals, not settled:

- Trend fitted by ordinary least squares over the smoothed series, 21-day
  window (matches §7.2's TDEE window, so the two dashboard numbers can never
  disagree about which way weight is moving).
- Regressing *smoothed* rather than raw values, because one bad morning
  otherwise swings the projected date by weeks.
- `progress_pct` clamped to 0–100: overshooting is still 100%, and moving the
  wrong way is 0%, not a negative a progress bar cannot draw.
- No projection at all when the trend is flat (< 0.005 kg/day), points away
  from the goal, or lands beyond 730 days. §2.6 says status comes from the
  trend, not wishful maths, so the honest answer is to refuse.
- `on_track` is null unless both a target date and a projection exist.

## 2026-09-07 — `POST /goals` derives start weight and start date from the log

§6's request body is `{goal_weight_kg, target_date?}` — no start weight — and
§2.6 says start weight is automatic from the log. The server therefore reads
the user's most recent weight observation. It also takes `start_date` from that
same observation rather than from a clock, which keeps the server out of
deciding what "today" is (§6). A goal cannot be created before a weight exists;
that returns 422 with a message saying so.

## 2026-09-07 — `GET /dashboard` has no notion of "today" — **needs Wes before Phase 3**

§6 forbids the server deriving "today" from UTC, and `GET /dashboard` takes no
parameters. Those two rules are compatible in Phase 1, because weight and goal
windows anchor to the user's most recent observation.

They collide in Phase 3. Streaks are "rolling 14-day" (§7.6), volume rings are
Monday-anchored, and the recap covers "the most recent completed Mon–Sun week"
(§7.7) — all need a real calendar today, which only the client knows. The
options are a `?date=` query parameter (a §14.1 item 3 contract change) or
storing a timezone on `profiles` (a §14.1 item 1 schema change). Flagged now
rather than discovered mid-Phase-3.

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
