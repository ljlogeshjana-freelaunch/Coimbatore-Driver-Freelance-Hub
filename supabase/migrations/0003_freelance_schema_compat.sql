-- Correct earlier freelance table shape without dropping rows. The initial schema
-- created a narrow table; add request fields needed by the validated API.
alter table public.freelancing_requests add column if not exists customer_name text not null default '';
alter table public.freelancing_requests add column if not exists email text not null default '';
alter table public.freelancing_requests alter column status set default 'pending';
create index if not exists freelance_email_created on public.freelancing_requests(email, created_at desc);

-- Assignment ids/status are needed by the driver UI; avoid broad direct client grants.
