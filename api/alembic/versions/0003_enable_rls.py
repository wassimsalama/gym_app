"""Close the PostgREST door: row level security on every table.

The database lives inside a Supabase project, and Supabase automatically
publishes every table in the `public` schema over PostgREST at
`/rest/v1/<table>`, authorised by the anon key. That key is *public by design* —
it ships inside the web bundle, where anyone can read it.

Without RLS this meant the entire application API could be bypassed. Verified
before this migration existed: a plain POST to `/rest/v1/exercises` carrying
only the anon key returned `201 Created`. Reads of every table returned `200`.
All the authorisation in `app/routers/` was irrelevant on that path, because
that path never touched it.

Enabling RLS with **no policies** denies everything to the `anon` and
`authenticated` roles, which is exactly right here: this application does its
own authorisation in the API, and no browser should ever reach these tables
directly. The API connects as the table owner, which bypasses RLS, so it is
unaffected.

Deliberately not writing per-user policies. They would be duplicated
authorisation logic in a second language, able to drift out of step with the
first, protecting a path that should not exist at all.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-08

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Every table this application owns. `alembic_version` is Alembic's own and is
#: covered too — its contents are uninteresting but there is no reason to serve
#: it to the internet either.
TABLES = (
    "profiles",
    "goals",
    "daily_logs",
    "exercises",
    "workout_sessions",
    "set_logs",
    "photos",
    "user_activity",
    "alembic_version",
)


def upgrade() -> None:
    for table in TABLES:
        op.execute(f"alter table {table} enable row level security")
        # FORCE also applies RLS to the table's owner. Not used: the API
        # connects as the owner and must keep working. The owner is our own
        # server, not an untrusted caller.


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"alter table {table} disable row level security")
