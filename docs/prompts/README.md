# Prompt library — FROZEN ONCE SHIPPED (N51)

These `*.md` files are the versioned prompt/rubric texts that seed the `prompt` table. A migration
(e.g. `0010_prompt_table`, `0025_scoring_v2_rubrics`) reads a file here **at run time** and inserts
its contents as a `prompt` row. That makes each file part of a shipped migration's behavior.

**Therefore: once a prompt file has been referenced by a migration that has run anywhere (dev or
prod), it is FROZEN — never edit it.** Editing a shipped file makes a fresh-DB `alembic upgrade`
seed different text than the DB that migrated earlier, so the two environments silently diverge and
the migration is no longer reproducible.

To change a prompt:

1. Add a NEW file with the next version suffix (e.g. `fit-scoring-rubric-v2.md`), leaving the old
   one untouched.
2. Add a NEW migration that inserts it as the next `prompt` version for its `stage` (the latest
   version is the active one — the app reads `ORDER BY version DESC`).

The only edits permitted to an existing file are ones that do NOT change the text a migration reads
(this README, or a comment in a file no migration has shipped yet).
