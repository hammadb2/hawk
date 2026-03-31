-- Storage bucket for PDF reports (create via Dashboard if this fails on permissions)
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'reports',
  'reports',
  false,
  52428800,
  array['application/pdf', 'image/png', 'image/jpeg']::text[]
)
on conflict (id) do nothing;
