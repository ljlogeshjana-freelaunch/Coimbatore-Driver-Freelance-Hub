# Deployment guide

## 1. Supabase
1. Create a Supabase project and set Authentication → Providers → Email to enabled.
2. In Authentication → URL Configuration, set the Site URL to the deployed Vercel origin. Add local `http://localhost:5173/**`, the production frontend origin and any trusted Vercel preview patterns to Redirect URLs.
3. Apply migrations in order from `supabase/migrations/` using the SQL editor or Supabase CLI. Do not rerun an already applied migration manually if it is not idempotent.
4. Copy the project URL and publishable/anon key into Vercel. Never expose the database password, JWT signing secret, or service-role key to the browser.
5. For backend token verification, set `SUPABASE_ISSUER` and either `SUPABASE_JWKS_URL` (recommended for asymmetric signing keys) or `SUPABASE_JWT_SECRET` for HS256 projects. Use the signing-key configuration actually active in your project.

## 2. Render backend
1. Connect the repository to Render and use the included `render.yaml` Blueprint, or create a Python web service with root directory `backend`.
2. Build command: `pip install -r requirements.txt`.
3. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
4. Set `DATABASE_URL`, `SUPABASE_ISSUER`, `SUPABASE_JWKS_URL` or `SUPABASE_JWT_SECRET`, `CORS_ORIGINS`, `ENVIRONMENT=production`, `FRONTEND_URL`. Add `RESEND_API_KEY` and `EMAIL_FROM` only when verified sender is ready.
5. Apply SQL migrations before serving traffic. Health check path: `/health`.
6. Use exact origins, e.g. `https://your-site.vercel.app`; add preview origins only if intentionally supported.

## 3. Vercel frontend
1. Import the repository in Vercel and set Root Directory to `frontend`.
2. Build command `npm run build`; output directory `dist`; install command `npm install`.
3. Set `VITE_API_URL` to the Render service origin, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, and `VITE_APP_URL` to the Vercel domain.
4. Vite SPA fallback is configured in `frontend/vercel.json`; verify direct navigation to `/drivers`, `/login`, `/account`, `/driver`, and `/admin`.
5. Once the domain is known, set Supabase Site URL/redirect URLs and update Render `CORS_ORIGINS`.

## 4. Local testing
Backend: `cd backend && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt && pytest`.
Frontend: `cd frontend && npm install && npm run build`.

## 5. Production checks
Create a customer and driver account; verify the driver's approval gate. Use the company admin email to bootstrap the admin role only after email authentication is configured. Submit a booking, manually assign an approved driver, accept it, exercise pause/resume/end, verify invoice amount and customer history. Submit freelance enquiry and check provider logs/admin inbox. Validate CORS, auth redirects, real mobile PWA install, and backups. Email sending is not confirmed unless Resend responds successfully.
