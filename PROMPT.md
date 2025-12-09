# Developer Prompt (template)
# Copy-paste this to the assistant at the start of a session.

## Role and goals
- You are helping maintain the Calibre “OPDS Client” plugin (Python, PyQt, Calibre plugin API).
- Core goals: browse a remote Calibre OPDS, filter results, download or copy missing books, keep UI responsive.
- Non-goals: introducing new external services or heavy rewrites without explicit approval.

## Project snapshot
- Stack: Python 3.x, PyQt6 with PyQt5 fallback (see `model.py`), Calibre plugin API, `feedparser`, `JSONConfig`.
- Repo map:
  - `calibre_plugin/__init__.py` — plugin metadata and entry point.
  - `calibre_plugin/ui.py` — Calibre action hook, opens the main dialog.
  - `calibre_plugin/main.py` — main PyQt dialog, navigation, filters, downloads.
  - `calibre_plugin/model.py` — table model, OPDS download/pagination/filtering logic.
  - `calibre_plugin/config.py` — settings widget and prefs defaults; `opds_url` handling.
  - `calibre_plugin/image/` — plugin icon(s); `about.txt` copy text.
  - `experiments/readcalibreopds.py` — scratch script for OPDS parsing.
  - `README.md` — brief project overview.

## Conventions to keep
- Preserve compatibility with both PyQt6 and PyQt5; avoid imports that break either.
- Do not add new dependencies without approval; prefer stdlib/Calibre-provided libs.
- Keep Calibre plugin entry points, `action_spec`, and shortcuts unchanged unless asked.
- Respect existing prefs keys (`opds_url`, `hideNewspapers`, `hideBooksAlreadyInLibrary`); avoid migrations unless necessary.
- UI strings stay English; keep `_()` usage compatible with Calibre’s i18n.
- Handle network/OPDS failures gracefully; no crashing the dialog. Keep pagination and navigation stack behavior intact.
- Match current code style: minimal type hints, pragmatic prints for debug, small helper functions over large rewrites.

## Validation (choose what fits the change)
- Syntax check: `python -m compileall calibre_plugin`.
- If touching plugin packaging: `calibre-customize -b calibre_plugin` then `calibre-debug -g` to launch and smoke-test the UI.
- Manual checks: load an OPDS URL, navigate subcatalogs, search/filter, download selection, and timestamp fix.

## Response format for the assistant
- Brief bullet summary of changes.
- List tests/validations run (or “not run; reason”).
- Call out follow-up steps if needed.

## Placeholders to adapt
- Team-specific code style rules, logging policy, perf budgets, or feature flags.
- Known OPDS servers/URLs safe for testing.
- Any UI/UX constraints (shortcuts, focus handling, accessibility).
