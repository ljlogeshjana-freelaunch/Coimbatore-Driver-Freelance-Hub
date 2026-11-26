-- Public freelance requests have no authenticated actor; keep their audit record
-- without inventing a value for the UUID actor column.
alter table public.audit_logs alter column actor_id drop not null;
