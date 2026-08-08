# Chile Rivers — working notes for Claude

## Git practice (required)

**Always work in a git worktree + feature branch, never directly on `main`.**
Multiple Claude sessions may work on this repo in parallel; branches keep them
from clobbering each other.

- New task → `git worktree add ../chile-rivers-<slug> -b <type>/<slug>` (or at
  minimum `git checkout -b <type>/<slug>` if a worktree is impractical).
- Commit on the branch, then merge to `main` (`git merge --no-ff`) and push.
- Remove the worktree when done: `git worktree remove ../chile-rivers-<slug>`.
- `main` must always be deployable — GitHub Pages serves `docs/` from it.

## Project map

- `PLAN.md` — architecture and phases. `README.md` — public description.
- `data/regulations/*.yaml` — hand-reviewed rules, one source citation each.
  Schema documented in `baseline.yaml`. NEVER change without citing a resolution.
- `data/waterbodies/registry.yaml` — canonical ids + OSM names. Ambiguous names
  (Río Blanco, Claro, Laja...) REQUIRE a `bbox` — many Chilean rivers share names.
- `data/advisory/techniques.yaml` — editorial layer (species presence + monthly
  fly/spin guides, bilingual `*_en` fields). Not regulatory.
- `scripts/fetch_geometry.py` — Overpass fetch. Gotchas: use `out geom` (not
  `out tags geom`); lakes need bbox not `(area:)`; rings are deduped; parts
  outside an entry bbox are clipped.
- `scripts/build.py` — regulations + geometry → `docs/data/`. Run after any data
  change: `py scripts/build.py --season 2026-2027`.
- `docs/` — static MapLibre site (GitHub Pages). Fully bilingual ES/EN via the
  I18N dict; any new UI string needs both languages.
- `/update` skill — checks Sernapesca/Subpesca for new documents; never applies
  changes without showing a diff.

## Verification before pushing

- `py scripts/build.py` must exit 0 with no ERRORS.
- Syntax-check the page: extract `<script>` → `node --check`.
- Simulate `showPanel` for all features in both languages (see git history for
  the harness pattern) when touching panel/advisory code.
