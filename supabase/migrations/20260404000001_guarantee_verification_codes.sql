-- Email verification codes for gated Breach Response Guarantee document (public marketing)

create table if not exists public.guarantee_verification_codes (
  id uuid primary key default gen_random_uuid(),
  email text not null,
  full_name text not null,
  company text not null,
  code_hash text not null,
  expires_at timestamptz not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_guarantee_ver_email_created
  on public.guarantee_verification_codes (lower(email), created_at desc);

alter table public.guarantee_verification_codes enable row level security;

-- No anon/authenticated policies — backend uses service role only
