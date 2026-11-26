# User experience and deployment checklist

## Website pages
- `/` landing page with distinct driver and freelance pathways.
- `/drivers` trip request form, live package pricing and WhatsApp booking follow-up.
- `/freelance` service descriptions, project enquiry form and contextual WhatsApp contact.
- `/login` Supabase email/password sign-up and sign-in; supports customer and driver applications.
- `/account` customer booking history, loaded from the API.
- `/driver` driver bookings and server-backed duty timer.
- `/admin` administrator metrics and bookings, gated in the API and interface.

## Connect services
1. Deploy the FastAPI backend and configure its database and Supabase JWT verification values as in `backend/.env.example`.
2. In the frontend host set `VITE_API_URL`, `VITE_SUPABASE_URL`, and `VITE_SUPABASE_ANON_KEY` (Vercel environment variables or GitHub Actions repository variables). The anon key is intended for browser use; never use the Supabase service-role key in the frontend.
3. Configure Supabase Auth email/password and the redirect URLs for the deployed domain. Configure API JWT validation to match the project's signing algorithm and issuer.
4. Apply Supabase migrations `0001` through `0004` in order. The first migration seeds non-commercial packages. Configure commercial rates only after administrator review.
5. Set the API CORS origins to the exact Vercel production and preview domains required.

The GitHub Pages workflow publishes only `frontend/dist` at `https://ljlogeshjana-freelaunch.github.io/Coimbatore-Driver-Freelance-Hub/`. Set repository Actions variables `VITE_API_URL`, `VITE_SUPABASE_URL`, and `VITE_SUPABASE_ANON_KEY` to the real deployed public endpoints/anon key. GitHub Pages hosts no API or database; keep FastAPI on Render and PostgreSQL/Supabase private. Its CORS origin is `https://ljlogeshjana-freelaunch.github.io` (without the repository path).

Driver duty displays a client-side elapsed-time estimate for convenience, but only API/server timestamps are used to calculate the final invoice. Install the driver app using the browser's Add to Home Screen/Install action. Verify PWA install behavior, mobile layouts, keyboard access, account confirmation and API connectivity on real devices before launch.

Freelance enquiry and contextual WhatsApp buttons prepare messages in WhatsApp; the user must press Send. The backend's Resend integration sends admin event notifications only when `RESEND_API_KEY` and a verified `EMAIL_FROM` are configured. Supabase Auth verification and password-reset emails need an SMTP provider configured in Supabase. An accepted API request or opened WhatsApp link is not proof of email or message delivery.
