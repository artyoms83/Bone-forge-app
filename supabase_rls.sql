-- BoneForge — Supabase Row Level Security
-- Run this in the Supabase SQL Editor (Project > SQL > New Query).
--
-- CONTEXT
-- -------
-- The Flask server authenticates users itself (password hashes in `users`,
-- session cookie stores the email). It talks to Supabase with a single
-- service key (SUPABASE_KEY env var) which BYPASSES RLS. That's intentional:
-- per-user scoping already happens in app.py via `.eq("email", email)` on
-- every query.
--
-- The purpose of RLS here is defense-in-depth:
--   * anon key (if it ever leaks or is used by a second client) reads nothing
--   * authenticated role (Supabase Auth users, if you adopt it later) reads
--     only rows whose `email` column matches their JWT email
--   * service_role (the Flask server) continues to work unchanged
--
-- Safe to re-run. All statements are idempotent where possible.

begin;

-- ---------------------------------------------------------------------------
-- 0. Schema additions (idempotent)
-- ---------------------------------------------------------------------------
-- Cache the grader output on the history row so opening a concept later does
-- not re-burn the grader API call. Stores {overall_score, grade, scores,
-- issues, fixed_script, formula, target_word_count, timestamp}.
alter table public.history
  add column if not exists score jsonb;

-- ---------------------------------------------------------------------------
-- 1. Enable RLS on every table the app touches
-- ---------------------------------------------------------------------------

alter table public.users             enable row level security;
alter table public.usage             enable row level security;
alter table public.characters        enable row level security;
alter table public.history           enable row level security;
alter table public.reference_images  enable row level security;
alter table public.password_resets   enable row level security;

-- ---------------------------------------------------------------------------
-- 2. Deny-by-default for anon
-- ---------------------------------------------------------------------------
-- With RLS on and no policies granting access to `anon`, the anon role sees
-- zero rows and cannot write. We make this explicit with a RESTRICTIVE policy
-- so even if someone later adds a permissive policy by mistake, anon is still
-- blocked.

drop policy if exists "deny anon" on public.users;
create policy "deny anon" on public.users
  as restrictive for all to anon
  using (false) with check (false);

drop policy if exists "deny anon" on public.usage;
create policy "deny anon" on public.usage
  as restrictive for all to anon
  using (false) with check (false);

drop policy if exists "deny anon" on public.characters;
create policy "deny anon" on public.characters
  as restrictive for all to anon
  using (false) with check (false);

drop policy if exists "deny anon" on public.history;
create policy "deny anon" on public.history
  as restrictive for all to anon
  using (false) with check (false);

drop policy if exists "deny anon" on public.reference_images;
create policy "deny anon" on public.reference_images
  as restrictive for all to anon
  using (false) with check (false);

drop policy if exists "deny anon" on public.password_resets;
create policy "deny anon" on public.password_resets
  as restrictive for all to anon
  using (false) with check (false);

-- ---------------------------------------------------------------------------
-- 3. Email-scoped policies for `authenticated`
-- ---------------------------------------------------------------------------
-- These kick in automatically if you ever migrate users to Supabase Auth.
-- Until then they are harmless — the Flask server uses service_role and
-- bypasses them entirely.
--
-- Pattern: a row belongs to the user whose JWT `email` claim matches the
-- `email` column on that row. `(select auth.jwt() ->> 'email')` is wrapped
-- in a subselect so Postgres caches the value once per statement (Supabase's
-- documented perf pattern).

-- users: a user can read and update their own row, but cannot insert or
-- delete (account creation/deletion stays server-side).
drop policy if exists "users read own"   on public.users;
drop policy if exists "users update own" on public.users;
create policy "users read own" on public.users
  for select to authenticated
  using ( email = (select auth.jwt() ->> 'email') );
create policy "users update own" on public.users
  for update to authenticated
  using  ( email = (select auth.jwt() ->> 'email') )
  with check ( email = (select auth.jwt() ->> 'email') );

-- usage: full CRUD on own row.
drop policy if exists "usage own" on public.usage;
create policy "usage own" on public.usage
  for all to authenticated
  using  ( email = (select auth.jwt() ->> 'email') )
  with check ( email = (select auth.jwt() ->> 'email') );

-- characters: full CRUD on own rows.
drop policy if exists "characters own" on public.characters;
create policy "characters own" on public.characters
  for all to authenticated
  using  ( email = (select auth.jwt() ->> 'email') )
  with check ( email = (select auth.jwt() ->> 'email') );

-- history: full CRUD on own rows.
drop policy if exists "history own" on public.history;
create policy "history own" on public.history
  for all to authenticated
  using  ( email = (select auth.jwt() ->> 'email') )
  with check ( email = (select auth.jwt() ->> 'email') );

-- reference_images: this table is keyed on `character_key` (not email), so
-- rows are scoped via the owning character. A user can touch a reference
-- image only if they own a character whose key matches.
--
-- Note: if `character_key` is not actually unique-per-user today (the current
-- app.py does not compose the key from email), two users with identically
-- named characters could collide. Worth auditing the key format later.
drop policy if exists "reference_images via owned character" on public.reference_images;
create policy "reference_images via owned character" on public.reference_images
  for all to authenticated
  using (
    exists (
      select 1 from public.characters c
      where c.email = (select auth.jwt() ->> 'email')
        and reference_images.character_key = c.name  -- adjust if your key format differs
    )
  )
  with check (
    exists (
      select 1 from public.characters c
      where c.email = (select auth.jwt() ->> 'email')
        and reference_images.character_key = c.name
    )
  );

-- password_resets: no `authenticated` access. Password reset is handled by
-- the Flask server using service_role (token lookup happens server-side).
-- No policy added here => authenticated sees nothing, which is correct.

commit;

-- ---------------------------------------------------------------------------
-- Verification: run these after committing
-- ---------------------------------------------------------------------------
-- select schemaname, tablename, rowsecurity
-- from pg_tables
-- where schemaname = 'public'
--   and tablename in ('users','usage','characters','history','reference_images','password_resets');
--
-- select schemaname, tablename, policyname, permissive, roles, cmd
-- from pg_policies
-- where schemaname = 'public'
-- order by tablename, policyname;
