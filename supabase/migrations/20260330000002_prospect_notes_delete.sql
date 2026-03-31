-- Allow authors to delete their own prospect notes (matches update policy)

drop policy if exists "prospect_notes_delete" on public.prospect_notes;
create policy "prospect_notes_delete"
  on public.prospect_notes for delete
  using (author_id = auth.uid());
