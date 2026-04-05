-- Go-live: throttle repeated aging WhatsApp nudges per prospect

alter table public.prospects
  add column if not exists last_aging_nudge_at timestamptz;

comment on column public.prospects.last_aging_nudge_at is 'Last time aging cron sent WhatsApp for 10+ day inactivity; next nudge after 48h';
