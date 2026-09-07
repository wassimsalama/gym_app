# Deploying

Three pieces, none of which talk to each other by magic:

```
  Cloudflare Pages          Railway              Supabase
  ────────────────          ───────              ────────
  the web app        ──▶    the API      ──▶     Postgres
  (static files)            (FastAPI)            Auth
                                                 photo storage
```

The order matters. The web build has the API's address **compiled into it**, so
the API must exist and have a URL before you build the site.

---

## 0. Region — do this before anything else

The dashboard makes **23 database round trips per load**, so the API and the
database must be in the same region. Split across continents this is the
difference between 0.05 s and 5.75 s.

Users are mainly in Canada, some in the Middle East. Railway has no Canadian
region, so:

| | |
| --- | --- |
| Supabase project | `us-east-1` (N. Virginia) |
| Railway service | `us-east4` (Virginia) |

Same metro, so the 23 round trips cost about 50 ms in total, and a Toronto user
is ~20 ms from the API.

`ca-central-1` would keep data in Canada but sits ~15 ms from Railway's nearest
region, which is 350 ms added to every dashboard load. Only worth it if
residency is a requirement rather than a preference.

**A Supabase project's region cannot be changed after creation.** If the
existing project is in the wrong region, make a new one now — it costs fifteen
minutes today and a data migration later.

### Moving to a new project

It is a new *project*, not a new account. Same login, `+ New project`, pick the
region at creation.

1. **Storage → New bucket** named `photos`, with *Public bucket* **off**.
2. **Authentication → Providers → Email → Confirm email: on**.
3. Update `api/.env`: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`.
4. Update `app/.env`: `EXPO_PUBLIC_SUPABASE_URL`, `EXPO_PUBLIC_SUPABASE_ANON_KEY`.
5. Sign up again in the app — accounts do not carry across projects.
6. Put your new user id in `ADMIN_USER_IDS`. Find it in **Authentication →
   Users**, or call `/health-auth` while signed in.
7. Verify:

   ```bash
   python scripts/check_config.py     # everything wired up
   python scripts/check_storage.py    # photos actually round-trip
   ```

`DATABASE_URL` stays pointed at local Docker for development; only Railway needs
the Supabase connection string.

---

## 1. Database — Supabase Postgres

Use the project's database rather than adding another service.

**Click the green "Connect" button at the top of the project dashboard.** It is
not under Settings — Supabase moved it, and it is easy to hunt for in the wrong
place.

In the dialog, choose **Session pooler** (port `5432`). Railway holds long-lived
connections, which is what the session pooler is for; the transaction pooler on
`6543` is for serverless.

Direct link, substituting your project ref:

```
https://supabase.com/dashboard/project/<ref>/?showConnect=true&method=session
```

It will look like:

```
postgres://postgres.<ref>:[YOUR-PASSWORD]@aws-<region>.pooler.supabase.com:5432/postgres
```

Replace `[YOUR-PASSWORD]` with your database password — the dialog shows a
placeholder, not the real thing. If you have forgotten it, reset it under
**Settings → Database → Database password**.

SQLAlchemy needs its driver named, so change the scheme:

```
postgresql+psycopg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
```

Nothing else to do — the API runs its own migrations on start.

---

## 2. API — Railway

1. **railway.app** → New Project → Deploy from GitHub repo → this repo.
   It reads `railway.json` and builds `api/Dockerfile`. No other configuration.

   The Dockerfile expects the **repository root** as build context, which is
   what Railway uses, so every `COPY` path starts with `api/`. Building it with
   `api/` as the context fails — to reproduce a Railway build locally:

   ```bash
   docker build -f api/Dockerfile -t gym-api .
   ```

2. **Variables** — set these before the first deploy finishes:

   | Variable | Value |
   | --- | --- |
   | `DATABASE_URL` | the Supabase URI above, with `+psycopg` |
   | `SUPABASE_URL` | `https://<ref>.supabase.co` |
   | `SUPABASE_STORAGE_BUCKET` | `photos` |
   | `SUPABASE_SERVICE_KEY` | Supabase → Settings → API Keys → `service_role` |
   | `ADMIN_USER_IDS` | your own user id, for `/admin/metrics` |
   | `TRUST_PROXY_HEADERS` | `true` — Railway *is* a proxy, and rate limiting counts the wrong address without it |
   | `ALLOWED_ORIGINS` | your site's origin, e.g. `https://gym.yourdomain.com` |

   `ALLOWED_ORIGINS` is the one that silently breaks everything. Leave it unset
   and the API falls back to allowing localhost only, so the deployed site gets
   blocked by CORS and every request reports "could not reach the server".

3. **Settings → Networking → Generate Domain.** Note the URL; the web build
   needs it.

   Check the domain's **target port** matches the `PORT` Railway injected —
   the logs show it as `Uvicorn running on http://0.0.0.0:<port>`. A mismatch
   gives `502 Application failed to respond` in front of a perfectly healthy
   process, which reads like a crash and is not one.

4. Check it: `curl https://<your-api>.up.railway.app/health` → `{"status":"ok"}`

---

## 3. Web — Cloudflare Pages

Build locally and upload the output. Expo's web export is a static folder, so
there is nothing to run.

Production values live in **`app/.env.production`** (gitignored), leaving `.env`
pointed at local development:

```
EXPO_PUBLIC_API_URL=https://<your-api>.up.railway.app
EXPO_PUBLIC_SUPABASE_URL=https://<ref>.supabase.co
EXPO_PUBLIC_SUPABASE_ANON_KEY=<anon key>
```

Then, from the repo root:

```bash
npm run build:web
```

That builds with the cache cleared and then verifies the output. **Do not
substitute `expo export` on its own.** Two things bite otherwise:

- Setting `EXPO_PUBLIC_*` on the command line does **not** work — Expo loads
  `.env` and exports those variables over the top of yours.
- Metro caches the inlined values, so an environment change with no `--clear`
  silently reuses the previous build's URLs.

Both produce a bundle that looks fine and points at your laptop. `npm run
build:web` refuses to produce one.

Then **Cloudflare → Workers & Pages → Create → Pages → Upload assets**, and drop
in `app/dist`.

`EXPO_PUBLIC_*` values are **baked into the bundle at build time**, not read at
runtime. Changing the API URL means rebuilding and re-uploading — there is no
environment variable to edit afterwards.

### Domain

Cloudflare → your Pages project → **Custom domains** → add the domain or
subdomain. DNS is automatic when the domain is on the same account.

---

## 4. Protecting accounts from password guessing

Someone who knows a user's email can try passwords against it. The app slows
this down in the sign-in form, but **that is a deterrent, not a defence** — an
attacker calls Supabase's auth endpoint directly, where no app code runs. These
settings are what actually stop it, and all four are free.

| Setting | Where | Why |
| --- | --- | --- |
| **Auth rate limits** | Authentication → Rate Limits | Caps sign-in attempts per IP per hour. The single most effective control; the default is generous, so lower it. |
| **Leaked password protection** | Authentication → Policies (or Providers → Email) | Rejects passwords found in known breaches, via HaveIBeenPwned. Stops credential stuffing, which is far more common than guessing. |
| **Minimum password length / required characters** | Authentication → Policies | Raise from the default 6. Length is what matters. |
| **CAPTCHA** | Authentication → Attack Protection | hCaptcha or **Cloudflare Turnstile**. Turnstile is free and you already have a Cloudflare account. This is the one that actually defeats automated guessing — the others slow it, this stops it. |

Enabling CAPTCHA also needs a small client change to pass the token, so tell me
if you turn it on and I will wire it up.

## 5. Two more Supabase settings

Both matter more once strangers can reach the site.

- **Authentication → Providers → Email → Confirm email: ON.**
  Otherwise anyone can register with an address they do not own.
- **Authentication → URL Configuration → Redirect URLs** — add
  `https://<your-site>/reset-password` and, for local work,
  `http://localhost:8081/reset-password`. Password-reset links go to an address
  Supabase has not been told to allow are silently refused, which looks like a
  broken email rather than a missing setting.
- **Authentication → Rate Limits** — sign-up and sign-in never touch the API, so
  they cannot be throttled there. This is the only place that governs them. (In
  some dashboard versions this sits under **Authentication → Attack Protection**.)

Supabase's built-in mailer is rate limited to a handful of messages an hour and
is only meant for testing. If your family hit that, add your own SMTP under
**Authentication → Emails → SMTP Settings** — a free Resend or Brevo account is
enough.

---

## Afterwards

Check these in order; each one fails distinctively.

| Check | Means |
| --- | --- |
| `curl https://<api>/health` | the API is up |
| Site loads | Pages served the build |
| Sign in works | Supabase URL and anon key are right |
| Dashboard loads | `ALLOWED_ORIGINS` is right — this is where CORS shows up |
| A photo uploads | storage bucket and service key are right |
| `/admin/metrics?date=YYYY-MM-DD` | `ADMIN_USER_IDS` contains your id |

---

## Updating

- **API** — push to the branch Railway watches. It rebuilds and runs migrations.
- **Web** — rebuild with the command above and re-upload to Pages.

## What this costs

| | |
| --- | --- |
| Cloudflare Pages | free |
| Domain | ~£8–10/year |
| Supabase | free tier |
| Railway | ~$5/month |
