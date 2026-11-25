# Coimbatore Driver & Freelance Hub

A connected customer website, driver-first installable PWA, and administrator workspace backed by a FastAPI REST API and PostgreSQL/Supabase.

## Repository structure
- `frontend/` React, TypeScript, Vite, Tailwind, Framer Motion and Lucide UI; customer, driver and admin workspaces share one app.
- `backend/` FastAPI, SQLAlchemy, Pydantic, JWT authorization, duty timer and Decimal billing.
- `supabase/migrations/` database schema, constraints, indexes and RLS policies.

## Requirements
- Node.js 20+ and npm
- Python 3.11+
- PostgreSQL or Supabase project
- Supabase Auth project (JWT signing secret configured for API verification)

## Local development
1. Copy `backend/.env.example` to `backend/.env`, fill in database URL and the Supabase JWT secret. Never commit secrets.
2. Start the API: `cd backend && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && uvicorn app.main:app --reload`.
3. Apply `supabase/migrations/0001_platform.sql` to your PostgreSQL/Supabase database.
4. Start the web/PWA: `cd frontend && npm install && cp .env.example .env && npm run dev`.
5. Create accounts through Supabase Auth; the frontend posts onboarding to the API. Only `ljlogeshjana@gmail.com` receives the administrator role, on the server. Driver accounts remain pending until admin approval.

## Security and integrations
Supabase Auth issues the access token; the API validates its signature, issuer, expiration, and subject using `SUPABASE_JWT_SECRET`. Configure Supabase Auth to use the matching HS256 signing secret, or extend the verifier for your project's asymmetric signing keys. The API independently enforces roles on every protected endpoint. Database RLS is included as defense in depth; use Supabase's `auth.uid()` claims when accessing tables directly through Supabase clients. The application API uses a restricted database connection and never accepts a user-supplied role as authorization.

Email delivery is optional until `RESEND_API_KEY` is configured. WhatsApp actions use `wa.me` links with separate numbers and contextual messages. Commercial prices are intentionally unconfigured and must be entered by an administrator. Configure Vercel with `VITE_API_URL`; deploy the backend to Render with `DATABASE_URL`, `SUPABASE_JWT_SECRET`, and `CORS_ORIGINS`.

## Duty billing
The API stores UTC timestamps and calculates elapsed, non-paused time on the server. Partial minutes round upward. Billing uses Decimal package price/duration, the selected package's rate for all active minutes, and the acting-driver surcharge; final total rounds half-up to two decimals. Browser timers are display-only and recover by fetching the active session after reload/reconnection. Timer actions are state-checked and audited.

## Tests and API docs
- Backend: `cd backend && pip install -r requirements.txt && pytest`
- Frontend production build: `cd frontend && npm install && npm run build`
- OpenAPI docs: `http://localhost:8000/docs`

Tests should be run in the target environment before deployment. No external credentials or live email/WhatsApp delivery are included in this repository.
