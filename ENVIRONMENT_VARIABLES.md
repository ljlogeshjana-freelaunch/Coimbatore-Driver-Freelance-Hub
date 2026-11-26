# Environment variables

Never commit real secrets. Copy the relevant example file into a local, ignored `.env` file and configure production values in Vercel/Render dashboards.

## Frontend (`frontend/.env.example`)

| Variable | Required | Description |
|---|---:|---|
| `VITE_API_URL` | Yes for API features | Deployed FastAPI origin, without trailing slash. Local default is `http://localhost:8000`. |
| `VITE_SUPABASE_URL` | Yes for authentication | Supabase project URL. |
| `VITE_SUPABASE_ANON_KEY` | Yes for authentication | Supabase publishable/anon key; safe for browser use when RLS is configured. Never put service-role keys here. |
| `VITE_APP_URL` | Recommended | Canonical frontend origin used for auth redirect setup. |

For the GitHub Pages workflow, configure these three values as repository Actions variables. `VITE_API_URL` must be the real deployed FastAPI origin; the build intentionally does not guess a Render hostname. The Supabase anon/publishable key is public by design. Do not configure any server-side secrets as `VITE_*` variables.

## Backend (`backend/.env.example`)

| Variable | Required | Description |
|---|---:|---|
| `DATABASE_URL` | Yes in production | SQLAlchemy URL for PostgreSQL, e.g. `postgresql+psycopg://...`. Local default is SQLite. |
| `SUPABASE_JWT_SECRET` | One JWT option | Legacy HS256 signing secret, if your Supabase project uses it. Treat as a secret. Configure this or `SUPABASE_JWKS_URL`, not both. |
| `SUPABASE_JWKS_URL` | One JWT option | Asymmetric signing key endpoint, typically `https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json`. Prefer this for projects using asymmetric keys. Configure this or `SUPABASE_JWT_SECRET`, not both. |
| `SUPABASE_ISSUER` | Yes in production | `https://<project-ref>.supabase.co/auth/v1`. Must match the project token issuer. |
| `CORS_ORIGINS` | Yes in production | Comma-separated exact allowed frontend origins; no wildcard in production. |
| `ADMIN_EMAIL` | Recommended | The sole company administrator address; defaults to `ljlogeshjana@gmail.com`. |
| `RESEND_API_KEY` | Optional | Server-only Resend API key. If set, `EMAIL_FROM` is also required. |
| `EMAIL_FROM` | Optional | Verified Resend sender, e.g. `Coimbatore Hub <notifications@example.com>`. |
| `FRONTEND_URL` | Recommended | Production frontend URL for auth links. |
| `ENVIRONMENT` | No | `development` or `production`; defaults to development. |
| `PORT` | Render supplies | Listening port; Render start command reads `$PORT`. |

Resend sender domains must be verified with the provider. Password reset and email verification messages are issued by Supabase Auth; set the provider's SMTP settings if you want Supabase auth emails delivered through Resend. The API's Resend client sends booking, registration/login and freelance enquiry alerts to the configured admin email.

Production backend startup requires a PostgreSQL `DATABASE_URL`, a matching issuer and one JWT verification method, and explicit non-local CORS origins. If Resend is enabled, configure both `RESEND_API_KEY` and `EMAIL_FROM`.
