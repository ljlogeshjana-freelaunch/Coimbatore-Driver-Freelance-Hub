# Coimbatore Driver & Freelance Hub

Responsive React/Vite website and installable driver PWA backed by a FastAPI API and PostgreSQL/Supabase Auth.

## Applications and routes
- `/` public landing page
- `/drivers` customer driver booking form and database pricing
- `/freelance` service enquiry form, persisted through the API and WhatsApp follow-up
- `/login` Supabase registration, sign-in, email verification, and password reset
- `/account` customer driver bookings and freelance enquiry history
- `/driver` driver assigned bookings, accept/decline and server-authoritative duty timer
- `/earnings` completed driver shifts and earnings
- `/admin` admin metrics, driver approvals, assignment, pricing, freelance status and login history

## Architecture
`frontend/src/App.tsx` provides responsive route/page UI. `frontend/src/lib/api.ts` attaches Supabase access tokens to the REST calls. FastAPI verifies tokens with Supabase JWKS (preferred) or legacy HS256 config, persists API entities with SQLAlchemy and applies role authorization on protected endpoints. Supabase migrations define database schema/RLS; the API uses a private PostgreSQL connection. Browser code uses only Supabase URL and publishable anon key.

## Local development
Prerequisites: Node.js 22+, Python 3.12+, PostgreSQL/Supabase for integrated auth. Copy environment templates and configure values.

```sh
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

In another terminal:

```sh
cd frontend
npm install
cp .env.example .env
npm run dev
```

For local API-only exploration SQLite creates its ORM tables on startup. A Supabase Auth account and valid JWT config are needed for protected endpoint integration. Do not use the SQLite default in production.

## Database and security setup
Apply `supabase/migrations/0001_platform.sql` through `0004_anonymous_audit_actor.sql` in order to a new Supabase database. The SQL migrations are additive. RLS denies direct browser access except owner-scoped reads/profile operations and public pricing read. Do not configure frontend service-role credentials. The backend accesses PostgreSQL through a server-only `DATABASE_URL`; keep that credential restricted and private. Set backend Supabase issuer and exactly one of the JWKS URL or JWT secret to your project's values.

Admin role bootstrap is from the verified JWT email matching `ADMIN_EMAIL` (`ljlogeshjana@gmail.com` by default), never user metadata. Driver signup only creates a pending application; the API requires approval for driver endpoints. Production CORS requires explicit origins.

## Email and WhatsApp
Resend admin notifications are sent only when `RESEND_API_KEY` and a verified `EMAIL_FROM` are configured. Supabase Auth email confirmation and password recovery email need an SMTP provider configured in Supabase; configure Resend SMTP there if desired. WhatsApp click-to-chat links open the user's WhatsApp app/web; the user must press Send. These are not delivery receipts.

## Checks
```sh
cd backend && python -m pytest -v
cd frontend && npm ci && npm run build
```

GitHub Actions runs the backend tests and frontend production build on pushes to `main` and pull requests. Authentication, PostgreSQL, and provider integrations still require project credentials and deployed-service configuration.

## Deployment
See `DEPLOYMENT.md` and `ENVIRONMENT_VARIABLES.md`. The existing GitHub Pages workflow deploys only `frontend/dist` to `https://ljlogeshjana-freelaunch.github.io/Coimbatore-Driver-Freelance-Hub/`; set its repository Actions variables to the real API and Supabase public configuration. Vercel can alternatively use root `frontend`, build `npm run build`, output `dist`. Render uses root `backend`, requirements install, and `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Set Postgres URL, JWT verification, explicit CORS, environment, and optional Resend secrets in Render. Never put backend secrets in the frontend.
