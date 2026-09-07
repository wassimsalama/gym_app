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

## 1. Database — Supabase Postgres

You already have the project. Use its database rather than adding another
service.

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

4. Check it: `curl https://<your-api>.up.railway.app/health` → `{"status":"ok"}`

---

## 3. Web — Cloudflare Pages

Build locally and upload the output. Expo's web export is a static folder, so
there is nothing to run.

```bash
cd app
EXPO_PUBLIC_API_URL=https://<your-api>.up.railway.app \
EXPO_PUBLIC_SUPABASE_URL=https://<ref>.supabase.co \
EXPO_PUBLIC_SUPABASE_ANON_KEY=<anon key> \
EXPO_PUBLIC_PRIVACY_URL=https://<your-site>/privacy.html \
npx expo export --platform web --output-dir dist
```

Then **Cloudflare → Workers & Pages → Create → Pages → Upload assets**, and drop
in `app/dist`.

`EXPO_PUBLIC_*` values are **baked into the bundle at build time**, not read at
runtime. Changing the API URL means rebuilding and re-uploading — there is no
environment variable to edit afterwards.

### Domain

Cloudflare → your Pages project → **Custom domains** → add the domain or
subdomain. DNS is automatic when the domain is on the same account.

---

## 4. Two Supabase settings

Both matter more once strangers can reach the site.

- **Authentication → Providers → Email → Confirm email: ON.**
  Otherwise anyone can register with an address they do not own.
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
