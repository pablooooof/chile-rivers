# Chile Rivers — Recreational Fishing Season Map

Interactive web map of major rivers and lakes from central Chile to Puerto Williams,
colored by 2026-season status, with per-water-body season dates, species, and
(later) monthly technique recommendations. Built on official Sernapesca/Subpesca
regulations, structured so new documents can be folded in as they appear.

## 1. How the regulation actually works (domain model)

Understanding the legal hierarchy is what makes the data model right:

1. **Baseline (national default)** — Ley 20.256 + Decreto 320/1981: the official
   recreational fishing season in continental waters runs from the **second Friday
   of November** to the **first Sunday of May**. This is the fallback for any water
   body with no specific rule.
2. **Regional resolutions (the interesting layer)** — Resoluciones Exentas issued by
   Subpesca zonal directorates, often following agreements of the regional Consejos
   de Pesca Recreativa. These create:
   - **Early openings** for named water bodies (e.g., Los Lagos: first Friday of
     September, catch-and-release only until the national season opens).
   - **Extensions, closures (vedas), bag limits, gear restrictions, size limits** —
     per region, per zone, or per named river/lake.
   - Some resolutions are **multi-year** (Los Lagos council approved a 2025–2028
     calendar in Aug 2025 — this is why "4 Sept 2026" is already determinable).
3. **Consolidation** — Sernapesca maintains a versioned consolidated table:
   *"Medidas de administración de pesca recreativa en Chile 2025-2026"*, published
   as **PDF and Excel** (e.g. `.../app/uploads/2025/09/medidas_de_administracion_de_
   pesca_recreativa_en_chile_2025-2026_v20250911.pdf`, note the `v20250911` version
   stamp). Columns: REGIÓN · ESPECIE(S) · ZONA(S) · VEDA · TEMPORADA DE PESCA.

**Consequence for the data model:** a water body's effective rules =
baseline ⊕ regional overrides ⊕ water-body-specific overrides, each with a source
document. Store rules, not conclusions, and compute the effective season.

## 2. Data sources

### Regulatory (truth)
| Source | Use |
|---|---|
| Sernapesca "Temporadas de Pesca Recreativa en Chile" page + consolidated **Excel/PDF** | Primary structured source. Versioned filename → easy change detection. |
| Subpesca Normativa (`subpesca.cl/portal/615`) | Official resolution texts (Res. Ex. numbers, exact wording, water-body lists). |
| LeyChile / Diario Oficial (bcn.cl) | Canonical legal text when a resolution needs verification. |
| Sernapesca noticias (pesca-recreativa filter) + Subpesca Difusión | **Change-detection signal** — announcements usually precede/accompany the consolidated table update. |
| Social media / press (e.g., the Instagram account) | Lead generator only — every claim must be traced to a resolution before entering the dataset. |

### Geospatial
| Layer | Source | Notes |
|---|---|---|
| Lakes (polygons) | DGA **Catastro de Lagos** via IDE Chile / Geoportal (shapefile, with names) | Official, named, ready to use. |
| Rivers (polygons) | **OpenStreetMap** water polygons / riverbank relations via Overpass, filtered to named major rivers | DGA's Red Hidrográfica is polylines only. OSM has real multipolygons for major rivers (Maullín, Petrohué, Puelo, Baker, etc.). |
| Fallback for thin rivers | Styled DGA/OSM polylines with width by zoom | A river that's 15 m wide doesn't need a polygon to read well on a map. |
| Regions (admin boundaries) | IDE Chile / BCN | For regional-default coloring and grouping. |

## 3. Repository layout

```
chile-rivers/
├── data/
│   ├── sources/            # downloaded PDFs/XLSX, named {date}_{sha8}_{orig-name}
│   │   └── index.yaml      # url, fetch date, hash, status (parsed/pending)
│   ├── regulations/
│   │   ├── baseline.yaml   # national default season rule
│   │   └── {region}/*.yaml # one file per resolution: seasons, species, gear,
│   │                       #   water-body list, source doc + resolution number
│   ├── waterbodies/
│   │   └── registry.yaml   # canonical id, name aliases, type, region, osm/dga ids
│   ├── geometry/           # one geojson per water body, keyed by registry id
│   └── advisory/
│       └── techniques.yaml # editorial: species × month × technique (NOT regulatory)
├── scripts/
│   ├── fetch_sources.py    # pull Sernapesca/Subpesca pages, detect new versions
│   ├── parse_medidas.py    # consolidated XLSX → draft regulation yaml (human-reviewed)
│   ├── fetch_geometry.py   # Overpass + IDE Chile downloads → geojson per id
│   ├── build.py            # join regulations + geometry → web/data/*.geojson
│   └── validate.py         # every water body has geometry, source, no date conflicts
└── web/                    # static site: MapLibre GL JS, no backend
    ├── index.html
    └── data/               # built geojson with computed season properties
```

**Principles:**
- Regulations are **hand-reviewed YAML with a source citation per record** — parsers
  produce drafts, a human (or Claude with human sign-off) approves them.
- Season windows stored as **rules** (`"first friday of september"` /
  `"second friday of november"`) *and* resolved dates per season, so 2027 computes itself
  where multi-year resolutions apply.
- Each season window carries a **mode**: `catch_and_release` | `retention` (with bag
  limit + species), so the Los Lagos "open Sept 4 but release-only until Nov" case is
  first-class, not a footnote.

## 4. Map design (MVP → later)

- **MVP:** MapLibre GL JS static site (GitHub Pages). Water bodies colored by
  **season opening date** (e.g., green = already open C&R, blue = opens with national
  season, gray = no data → regional default). Click → panel: water body name, season
  timeline bar (C&R window vs retention window), species list, source resolution link.
- **Later:** month slider ("what's fishable in October?"), species filter,
  technique-by-month table in the popup, "new regulation" badge when a document
  changed recently.

## 5. Update pipeline (staying current)

1. **Watcher** (weekly, more often Aug–Nov when resolutions drop):
   fetch Sernapesca uploads page + noticias feed + Subpesca normativa search;
   hash-compare against `data/sources/index.yaml`.
2. New/changed document → download to `data/sources/`, flag `pending`.
3. **Parse to draft** regulation YAML; produce a **diff report** ("Los Lagos: opening
   moved 5 Sep → 4 Sep; Río Ventisquero added") for review.
4. Approve → merge → `build.py` → redeploy (GitHub Action on push).
- Runner options: GitHub Action cron, or a Claude Code scheduled routine that opens
  the diff for review. (Decision item.)

## Decisions (2026-08-08)

- **MVP scope:** Los Lagos + Los Ríos + Aysén (extend north/south after).
- **River geometry:** OSM polygons where available + zoom-styled lines for narrow rivers; lakes from DGA Catastro de Lagos.
- **Stack:** MapLibre GL JS static site on GitHub Pages.
- **Updates:** manual `/update` command in Claude Code (fetch → diff → approve); automate later.

## 6. Phases

- **P0 — Bootstrap:** git init, layout above, download + archive the 2025-26
  consolidated Excel/PDF and the Los Lagos multi-year resolution.
- **P1 — Regulations dataset:** parse consolidated Excel → per-region YAML; chase the
  Los Lagos 2025–2028 resolution text (exact Res. Ex. number + full water-body list);
  watch for the 2026-27 consolidated table (expected ~Sept 2026 — imminent).
- **P2 — Geometry:** water-body registry for every name appearing in regulations;
  fetch lake polygons (IDE) + river polygons (OSM); name-match with manual fixes.
- **P3 — Map MVP:** build + deploy, colored by opening date, popup with season/species.
- **P4 — Advisory layer:** techniques by species × month (editorial content).
- **P5 — Automation:** the watcher pipeline from §5.

## 7. Verification of the Instagram claim (worked example)

Claim: Los Lagos season opens **4 Sept 2026**, release-only until November, for lakes
Llanquihue/Rupanco/Puyehue and rivers Maullín/Rahue/Pilmaiquén/Puelo/Ventisquero/
Manso/Traidor/Puelo Chico.

Status: **consistent with official acts.** The Los Lagos Consejo de Pesca Recreativa
approved (Aug 2025) a calendar for seasons 2025–2028 opening the **first Friday of
September** — which in 2026 is Sept 4. The 2025-26 implementation (Res. via Dirección
Zonal, opening 5 Sept 2025, C&R until 13 Nov 2025, regular season to 3 May 2026)
covered lakes Llanquihue, Rupanco, Puyehue and rivers Maullín, Pilmaiquén, Rahue,
Puelo — the same core list. **Open item:** fetch the exact resolution text for
2026-27 from Subpesca normativa to confirm the full river list (Ventisquero, Manso,
Traidor, Puelo Chico) and the exact C&R end date.
