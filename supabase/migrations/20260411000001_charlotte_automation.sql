-- Charlotte full automation: settings (industry rotation, optional Smartlead campaign id) + run logs

create table if not exists public.crm_settings (
  key text primary key,
  value text not null,
  updated_at timestamptz not null default now()
);

insert into public.crm_settings (key, value)
values ('charlotte_industry_day_index', '0')
on conflict (key) do nothing;

insert into public.crm_settings (key, value)
values ('smartlead_campaign_id', '')
on conflict (key) do nothing;

create table if not exists public.charlotte_runs (
  id uuid primary key default gen_random_uuid(),
  run_date date not null default ((timezone('America/Edmonton', now()))::date),
  industry text,
  leads_pulled integer not null default 0,
  emails_verified integer not null default 0,
  emails_suppressed integer not null default 0,
  domains_scanned integer not null default 0,
  scan_failures integer not null default 0,
  emails_written integer not null default 0,
  leads_uploaded integer not null default 0,
  created_at timestamptz not null default now()
);

create index if not exists idx_charlotte_runs_created on public.charlotte_runs (created_at desc);
create index if not exists idx_charlotte_runs_date on public.charlotte_runs (run_date desc);

alter table public.charlotte_runs enable row level security;
