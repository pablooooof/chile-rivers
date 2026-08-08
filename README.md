# Chile Rivers — mapa de temporadas de pesca recreativa

Mapa web de ríos y lagos del sur de Chile (Los Ríos, Los Lagos y Aysén por ahora)
coloreados según la fecha de apertura de la temporada de pesca recreativa
2026-2027, con las fases de cada cuerpo de agua (devolución obligatoria vs.
retención), especies y fuentes normativas.

**Mapa:** https://pablooooof.github.io/chile-rivers/

## Estructura

- `data/sources/` — documentos oficiales descargados (Sernapesca/Subpesca/D.O.), con `index.yaml` como registro.
- `data/regulations/` — reglas estructuradas en YAML, cada una citando su resolución. Ver esquema en `baseline.yaml`.
- `data/waterbodies/registry.yaml` — registro canónico de cuerpos de agua y nombres OSM.
- `data/geometry/` — GeoJSON por cuerpo de agua (obtenido de OpenStreetMap).
- `data/advisory/techniques.yaml` — capa editorial (con qué pescar, por mes). No normativa.
- `scripts/fetch_geometry.py` — descarga geometrías desde Overpass.
- `scripts/build.py` — combina reglas + geometría → `docs/data/waterbodies.geojson`.
- `docs/` — sitio estático (MapLibre GL) servido por GitHub Pages.

## Actualizar

```
py scripts/fetch_geometry.py     # sólo si cambió el registro de cuerpos de agua
py scripts/build.py --season 2026-2027
```

En Claude Code, `/update` revisa Sernapesca/Subpesca por documentos nuevos y
propone los cambios (nunca los aplica sin aprobación).

## Fuentes

- Sernapesca, *Medidas de administración de pesca recreativa en Chile 2025-2026* (v20260522, PDF+XLSX).
- Res. Ex. N° 2075/2025 DZ Los Lagos (D.O. 04-09-2025) — apertura anticipada primer viernes de septiembre, temporadas 2025-26 a 2028-29.
- Res. Ex. N° 3004/2024 DZ Aysén (+ mod. 893/2025, 75/2026) — calendario por fases 2025-2027.
- Res. Ex. N° 04/2024 DZ La Araucanía-Los Ríos — apertura segundo viernes de octubre, temporadas hasta 2029-30.

⚠️ Proyecto informativo. Verifique la normativa vigente en sernapesca.cl antes de pescar.
