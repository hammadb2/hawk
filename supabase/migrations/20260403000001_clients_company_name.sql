-- Repair: legacy public.clients rows missing columns from phase1 (company_name, mrr_cents, etc.)

alter table public.clients add column if not exists prospect_id uuid;
alter table public.clients add column if not exists company_name text;
alter table public.clients add column if not exists domain text;
alter table public.clients add column if not exists plan text;
alter table public.clients add column if not exists mrr_cents integer;
alter table public.clients add column if not exists stripe_customer_id text;
alter table public.clients add column if not exists closing_rep_id uuid;
alter table public.clients add column if not exists status text;
alter table public.clients add column if not exists close_date timestamptz;
alter table public.clients add column if not exists created_at timestamptz;

update public.clients set mrr_cents = coalesce(mrr_cents, 0);
alter table public.clients alter column mrr_cents set default 0;
alter table public.clients alter column mrr_cents set not null;

update public.clients set status = coalesce(status, 'active');
alter table public.clients alter column status set default 'active';

update public.clients set close_date = coalesce(close_date, now());
alter table public.clients alter column close_date set default now();
alter table public.clients alter column close_date set not null;

update public.clients set created_at = coalesce(created_at, now());
alter table public.clients alter column created_at set default now();
alter table public.clients alter column created_at set not null;
