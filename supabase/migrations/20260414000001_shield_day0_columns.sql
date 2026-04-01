-- Shield Day 0 / certification timeline (set when Stripe confirms Shield subscription payment)
alter table public.clients
  add column if not exists certification_eligible_at timestamptz;

comment on column public.clients.certification_eligible_at is 'onboarded_at + 90 days — eligibility date for HAWK Certified';
