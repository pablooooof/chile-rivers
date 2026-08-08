---
name: update
description: Check Sernapesca/Subpesca for new recreational-fishing regulation documents, download them, diff against the current dataset, and report what changed for approval. Use when the user runs /update or asks to check for new fishing-season regulations.
---

# Update regulation sources

Goal: detect new or changed regulation documents, archive them, and produce a
human-reviewable diff. NEVER silently change `data/regulations/*.yaml` — always
show the proposed changes and get approval first.

## Steps

1. **Check the consolidated table** (primary signal):
   - Fetch `https://www.sernapesca.cl/manuales_y_publicaciones/temporadas-de-pesca-recreativa-en-chile/`
     with curl and a browser User-Agent, grep for
     `uploads/.../(pdf|xlsx)` links matching `medidas_de_administracion_de_pesca_recreativa`.
   - Compare the versioned filename (e.g. `_v20260522`) against `data/sources/index.yaml`.
   - New version → download both PDF and XLSX into `data/sources/`, record sha256
     (first 8 hex chars), add entries to `index.yaml` with `status: pending`.
   - **Watch especially for a 2026-2027 edition** (expected ~Sept 2026) — that is a
     new filename, not just a version bump.

2. **Check announcement feeds** for resolution news (secondary signal):
   - `https://www.sernapesca.cl/noticias/?area_trabajo%5B%5D=pesca-recreativa`
   - `https://www.subpesca.cl/portal/difusion/Noticias/`
   - Look for: apertura/cierre de temporada, nuevas resoluciones, vedas, regions
     Los Ríos / Los Lagos / Aysén.

3. **Parse and diff** when a new consolidated XLSX arrived:
   - Load it with openpyxl (see `scripts/` and the schema in
     `data/regulations/baseline.yaml`), extract rows for regions in scope plus
     national rows.
   - Diff against current `data/regulations/*.yaml` at the semantic level:
     changed season windows, new/removed water bodies, new resolution numbers.
   - Report as a table: water body / field / old / new / source row.

4. **Known open watch items** (check these every run):
   - La Araucanía chinook early season (15 Sept–31 Mar, Toltén and Imperial basins,
     Res. Ex. 01/2021) covered only through season 2025-26 — renewal expected
     ~Aug-Sept 2026. Until it appears, those basins map to the regional rule (13 Nov).
   - Río Calcurrupe (Los Ríos): 10-year C&R expired 2026-01-18 — expect a new
     resolution; until then it reverts to the regional rule.
   - Decreto 878 native-species veda expires 2026-10-05 — expect renewal.
   - May C&R extensions (lago Llanquihue Res. 1167/2026, río Petrohué Res.
     1168/2026) were season-2025-26 one-offs — check for 2027 repeats.
   - Aysén calendar (Res. 3004/2024) covers through 2027 — a new multi-year
     resolution is due for 2027-28.
   - Res. Ex. 2075/2025 Los Lagos: consolidated table says "segundo viernes de
     septiembre" but the D.O. text says "primer viernes" — if a corrected table
     version appears, note which wording it uses.

5. **After approval** of any YAML change: set the source's `status: parsed` in
   `index.yaml`, run `py scripts/build.py --season 2026-2027`, verify no errors,
   commit with a message describing the regulatory change, and push (GitHub Pages
   redeploys automatically).

## Trust rules

- Only Sernapesca / Subpesca / Diario Oficial / LeyChile count as sources of
  truth. Press or social media claims are leads: find the resolution before
  changing data.
- When the consolidated table and a resolution's D.O. text disagree, the D.O.
  text prevails; record the discrepancy in `index.yaml` notes.
