# Render free test deployment

The user has explicitly declined paid Render resources. `render.yaml` now contains
only a `plan: free` web service. It has no disk, paid database, autoscaling or automatic
upgrade. Do not create paid resources or switch a plan without new authorization.

## Scope of the free link

The same web/API/worker container runs in explicit free-beta mode with temporary
SQLite and temporary private media. A visible notice in all nine languages explains
that accounts, drafts and files can be erased when Render sleeps, restarts or redeploys.
Provider generation and nonzero credit grants are blocked without PostgreSQL.
This is a test deployment, not production storage or the complete AI service.

The original application supports PostgreSQL and private S3 storage when separately
configured. The free runtime deliberately does not receive the cloud Gemini or Render
control key. Render's control key must never become a public service environment variable.

## Verified free-tier limits

Sources read during this task:
- https://render.com/docs/free
- https://render.com/docs/blueprint-spec
- https://render.com/docs/disks
- https://render.com/pricing

Render free web services can sleep after 15 minutes without traffic. Their local
filesystem is ephemeral, and they cannot attach a persistent disk. A workspace has
750 included free instance hours per month shared by its free web services. Other
monthly limits for bandwidth/build minutes apply; do not promise unlimited usage.

A workspace can have only one free Render Postgres database. It expires after
30 days; Render can delete it after the grace period. The authorized API attempt
to create a database explicitly on `plan: free` returned HTTP 403 HTML, as did its
list endpoint. No database was created and no paid fallback was attempted.

## Deployment process

Publish the tested source to the selected GitHub repository, then create a new
Docker web service through the Render API with an explicit `plan: free`, no disk,
`HAYTILE_FREE_BETA=1`, `DATABASE_URL=sqlite:////tmp/haytile/haytile.db` and
`HAYTILE_DATA_DIR=/tmp/haytile`. Derive the HTTPS origin from RENDER_EXTERNAL_URL.
Disable autodeploy for the first rollout. Obtain the actual URL from Render metadata
and validate it before sharing it as an application link. Preserve unrelated services.

Do not print tokens, database credentials, environment dumps, or full error bodies.
The cloud Render control key is used only against api.render.com through its binding.

## Local validation

The production Docker package was built with TLS verification enabled. The cloud
build uses an optional BuildKit CA secret instead of disabling verification; the CA
is not copied into the runtime image. A 512 MB / 0.1 CPU disposable container starts
with SQLite and the free-mode flags, and reports temporary database/media plus
disabled provider generation. PostgreSQL tests continue to verify the full backend.

Free-container browser checks: all three workflows passed on 512 MB / 0.1 CPU.
The first full workflow initially exceeded the suite's 30-second total budget;
a warmed rerun completed in 28.6 seconds. Individual functional assertions were
unchanged. `HAYTILE_TEST_SLOW=1` provides a bounded 120-second whole-test budget
for subsequent free-tier/cold-start checks.

`scripts/deploy_render_free.py` enforces the free plan, no persistent disk, no AI
or Render control key in service variables, source-push verification and guarded
creation without automatic mutation retries.

## Public free deployment verified

Actual Render service: https://haytile-ai.onrender.com

Render reports plan `free` and deploy status `live` for the initial application
commit `0473bed520db7340c2af666b434d3b1191b99077`. Public HTTPS checks passed for
HTML, all 8 referenced JavaScript/CSS assets, health and runtime flags. A temporary
smoke-test account exercised secure-cookie login, exact draft storage, private
download, rename, storyboard persistence, delete and logout; it was then removed.

Remote browser automation was blocked by this cloud browser's proxy/CA setup;
TLS verification was not disabled. The same browser workflows passed against the
local free-mode container, and the public HTTP functional smoke passed using the
system's verified HTTPS trust configuration. Do not describe remote browser tests
as passed. The public deployment is explicitly temporary and AI generation is disabled.
