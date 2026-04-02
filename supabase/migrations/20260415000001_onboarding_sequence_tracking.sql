-- Idempotent Shield onboarding Day 1 / 3 / 7 sends (cron marks timestamps)
alter table public.clients
  add column if not exists onboarding_day1_sent_at timestamptz,
  add column if not exists onboarding_day3_sent_at timestamptz,
  add column if not exists onboarding_day7_sent_at timestamptz;

comment on column public.clients.onboarding_day1_sent_at is '24h+ reminder: call booking + first findings email';
comment on column public.clients.onboarding_day3_sent_at is '72h progress WhatsApp';
comment on column public.clients.onboarding_day7_sent_at is 'Week one summary WhatsApp + email';
