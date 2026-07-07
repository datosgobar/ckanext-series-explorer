# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
from math import ceil
from urllib.parse import urlencode

import requests
from flask import Blueprint
import ckan.plugins.toolkit as toolkit

log = logging.getLogger(__name__)

# ── Blueprint de series de tiempo ──
series_bp = Blueprint(
    "series",
    __name__,
    url_prefix="/series",
)

SERIES_API_URL = "https://apis.datos.gob.ar/series/api/search/"
SERIES_PER_PAGE = 12
SERIES_SORT_OPTIONS = ("relevance", "hits_90_days", "frequency")
SERIES_FACETS = (
    ("dataset_theme", "Tema"),
    ("dataset_source", "Fuente"),
    ("dataset_publisher_name", "Publicador"),
    ("units", "Unidad"),
)
# field.frequency viene en ISO 8601 (repeating interval): R/P<n><unidad>.
SERIES_FREQUENCY_LABELS = {
    "R/P1D": "Diaria",
    "R/P1W": "Semanal",
    "R/P1M": "Mensual",
    "R/P3M": "Trimestral",
    "R/P6M": "Semestral",
    "R/P1Y": "Anual",
}


def _series_frequency_label(code):
    # Fallback: dejar el código crudo si no matchea, para no ocultar el dato.
    return SERIES_FREQUENCY_LABELS.get(code, code)


def _series_build_url(overrides):
    """path + querystring del request actual con overrides aplicados.

    overrides: {key: str} reemplaza, {key: list} setea múltiples valores,
    {key: None} elimina la key. Usa lista de tuplas para poder repetir keys.
    """
    params = []
    for key in toolkit.request.args:
        if key in overrides:
            continue
        for value in toolkit.request.args.getlist(key):
            params.append((key, value))
    for key, value in overrides.items():
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            params.extend((key, v) for v in value)
        else:
            params.append((key, value))
    query = urlencode(params)
    path = toolkit.request.path
    return f"{path}?{query}" if query else path


def _series_facet_href(key, value, is_active):
    current = toolkit.request.args.getlist(key)
    if is_active:
        new_values = [v for v in current if v != value]
    else:
        new_values = current + [value]
    # page=None: al cambiar un filtro se vuelve a la página 1 (como el search de CKAN).
    return _series_build_url({key: new_values or None, "page": None})


def _series_facet_buckets(aggregations, key, selected_values):
    """{label: count} para una faceta, combinando lo que devolvió la API
    (campos `label`/`series_count`) con los valores ya seleccionados, para
    que se puedan deseleccionar aunque la API no los devuelva como bucket."""
    buckets = {}
    for bucket in aggregations.get(key, []):
        label = bucket.get("label")
        if label is None:
            continue
        buckets[label] = bucket.get("series_count", 0)
    for value in selected_values:
        buckets.setdefault(value, 0)
    return buckets


# Endpoint de metadata completa (un id) y gráfico/CSV (por id, coma-separados).
SERIES_METADATA_URL = "https://apis.datos.gob.ar/series/api/series/"

# Atajos de tema en la landing: labels EXACTOS de dataset_theme vistos en la API.
SERIES_TOPIC_CHIPS = (
    "Precios",
    "Empleo e Ingresos",
    "Actividad",
    "Finanzas Públicas",
    "Sociedad",
)

SERIES_MONTHS_ABBR = (
    "ene.", "feb.", "mar.", "abr.", "may.", "jun.",
    "jul.", "ago.", "sep.", "oct.", "nov.", "dic.",
)


def _series_format_number(value, decimals=2):
    """Número estilo argentino: miles con `.`, decimales con `,`.

    11831.9766 → "11.831,98". None si no castea a float (el template decide
    si oculta el bloque). ponytail: format US + swap, sin locale (compartido
    entre requests, no thread-safe).
    """
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    s = f"{num:,.{decimals}f}"  # "11,831.98"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _series_format_date(iso_date):
    """"2026-05-01" → "may. 26". None si iso_date es falsy/mal formado."""
    if not iso_date:
        return None
    try:
        year = int(iso_date[:4])
        month = int(iso_date[5:7])
        return f"{SERIES_MONTHS_ABBR[month - 1]} {year % 100:02d}"
    except (ValueError, IndexError):
        return None


def _series_fetch_meta(series_id):
    """Metadata full de UNA serie.

    Devuelve (count, entry):
      - (None, None)  → error de red/parse (degradar sin 500).
      - (count, None) → la API respondió pero no hay entrada de metadata full.
      - (count, dict) → `count` total de valores y el dict con claves
        catalog/dataset/distribution/field.
    ponytail: un id por request (más simple, evita ambigüedad de orden en `meta`).
    """
    try:
        resp = requests.get(
            SERIES_METADATA_URL,
            params={"ids": series_id, "metadata": "full", "limit": 1},
            timeout=5,
        )
    except requests.RequestException:
        log.warning("Fallo la consulta de metadata a la API de series", exc_info=True)
        return None, None
    if resp.status_code == 400:
        # La API responde 400 para un id inexistente/mal formado (ej.
        # {"errors": [{"error": "Serie inexistente: <id>"}]}) — es un "no
        # encontrado", no una falla de red/servicio. No confundir con (None, None).
        return 0, None
    try:
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError):
        log.warning("Fallo la consulta de metadata a la API de series", exc_info=True)
        return None, None
    count = payload.get("count", 0)
    meta = payload.get("meta", [])
    # meta[0] es el objeto genérico de frecuencia; la entrada por-serie es la
    # que trae las claves de metadata full.
    entry = next((m for m in meta if "field" in m and "dataset" in m), None)
    return count, entry


def _series_meta_common(entry):
    """Campos extraídos comunes de una entrada de metadata full."""
    field = entry.get("field", {})
    dataset = entry.get("dataset", {})
    catalog = entry.get("catalog", {})
    publisher = dataset.get("publisher") or catalog.get("publisher") or {}
    theme = dataset.get("theme")
    return {
        "field": field,
        "dataset": dataset,
        "catalog": catalog,
        "publisher_name": publisher.get("name"),
        "theme_label": theme[0].get("label") if theme else None,
        # Título mostrado: description con fallback a title (el slug técnico).
        "title": field.get("description") or field.get("title"),
    }


def _series_topic_chips():
    return [
        {"label": label, "href": _series_build_url({"dataset_theme": [label]})}
        for label in SERIES_TOPIC_CHIPS
    ]


def _series_compare_items(compare):
    """{id, title, publisher, remove_href} por cada id de `compare`, en orden.
    Saltea los ids cuya metadata falla."""
    items = []
    for cid in compare:
        _count, entry = _series_fetch_meta(cid)
        if entry is None:
            continue
        c = _series_meta_common(entry)
        items.append({
            "id": cid,
            "title": c["title"],
            "publisher": c["publisher_name"],
            "remove_href": _series_build_url(
                {"compare": [i for i in compare if i != cid] or None}
            ),
        })
    return items


def _series_graphic_url(ids):
    return SERIES_METADATA_URL + "?ids=" + ",".join(ids)


@series_bp.route("/")
def series():
    args = toolkit.request.args
    q = args.get("q", "")
    sort_by = args.get("sort_by", "relevance")
    if sort_by not in SERIES_SORT_OPTIONS:
        sort_by = "relevance"
    try:
        page = int(args.get("page", 1))
    except (TypeError, ValueError):
        page = 1
    if page < 1:
        page = 1

    selected = {key: args.getlist(key) for key, _ in SERIES_FACETS}
    # ponytail: parse robusto de `compare`, acepta tanto ?compare=a,b como
    # ?compare=a&compare=b (esta última la produce _series_build_url con listas).
    compare = [c for v in args.getlist("compare") for c in v.split(",") if c]

    searching = bool(q) or any(selected[key] for key in selected)
    if searching:
        mode = "results"
    elif compare:
        mode = "focus_compare"
    else:
        mode = "landing"

    ctx = {
        "page_title": "Series de Tiempo",
        "mode": mode,
        "q": q,
        "compare": compare,
        "topic_chips": _series_topic_chips(),
        "sort_by": sort_by,
        "sort_options": [],
        "facets": [],
        "results": [],
        "count": 0,
        "page": 1,
        "pages": 1,
        "prev_url": None,
        "next_url": None,
        "error": False,
        "compare_items": [],
        "compare_graphic_url": None,
    }

    if mode == "landing":
        return toolkit.render("series/index.html", extra_vars=ctx)

    if mode == "focus_compare":
        compare_items = _series_compare_items(compare)
        ctx["compare_items"] = compare_items
        ctx["compare_graphic_url"] = _series_graphic_url(compare)
        # Si TODOS los ids fallaron, degradamos como error (igual que la vista).
        ctx["error"] = not compare_items
        return toolkit.render("series/index.html", extra_vars=ctx)

    # ── mode == "results" ──
    params = [
        ("limit", SERIES_PER_PAGE),
        ("start", (page - 1) * SERIES_PER_PAGE),
        ("sort_by", sort_by),
        ("aggregations", ""),
    ]
    if q:
        params.append(("q", q))
    for key, values in selected.items():
        if values:
            params.append((key, "||".join(values)))

    data = []
    count = 0
    aggregations = {}
    error = False
    try:
        resp = requests.get(SERIES_API_URL, params=params, timeout=5)
        resp.raise_for_status()
        payload = resp.json()
        data = payload.get("data", [])
        count = payload.get("count", 0)
        aggregations = payload.get("aggregations", {})
    except (requests.RequestException, ValueError):
        log.warning("Fallo la consulta a la API de series", exc_info=True)
        error = True

    pages = max(1, ceil(count / SERIES_PER_PAGE)) if count else 1
    # Clamp: si count nos deja fuera de rango no reconsultamos (lazy), pero la
    # paginación no ofrece un "siguiente" inválido. ponytail: sin re-fetch,
    # basta con no mostrar next más allá de pages.
    if page > pages:
        page = pages

    sort_labels = {
        "relevance": "Relevancia",
        "hits_90_days": "Más consultadas",
        "frequency": "Frecuencia",
    }
    sort_options = [
        {
            "key": key,
            "label": sort_labels[key],
            "href": _series_build_url({"sort_by": key, "page": None}),
            "active": sort_by == key,
        }
        for key in SERIES_SORT_OPTIONS
    ]

    facets = []
    for key, title in SERIES_FACETS:
        buckets = _series_facet_buckets(aggregations, key, selected[key])
        if not buckets:
            continue
        items = [
            {
                "label": label,
                "count": cnt,
                "active": label in selected[key],
                "href": _series_facet_href(key, label, label in selected[key]),
            }
            for label, cnt in buckets.items()
        ]
        facets.append({"key": key, "title": title, "items": items})

    results = []
    for item in data:
        field = item.get("field", {})
        dataset = item.get("dataset", {})
        publisher = dataset.get("publisher") or {}
        sid = field.get("id")
        in_compare = sid in compare
        if in_compare:
            new_compare = [i for i in compare if i != sid] or None
        else:
            new_compare = compare + [sid]
        results.append({
            "id": sid,
            # title = slug técnico; description = texto legible. El template
            # muestra description con fallback a title (nunca title directo).
            "title": field.get("title"),
            "description": field.get("description"),
            "dataset_title": dataset.get("title"),
            "source": dataset.get("source"),
            "publisher": publisher.get("name"),
            "theme": dataset.get("theme"),
            "units": field.get("units"),
            "frequency_label": _series_frequency_label(field.get("frequency")),
            "date_start": _series_format_date(field.get("time_index_start")),
            "date_end": _series_format_date(field.get("time_index_end")),
            "hits_90_days": field.get("hits_90_days"),
            "in_compare": in_compare,
            "compare_toggle_href": _series_build_url({"compare": new_compare}),
            "href": toolkit.url_for("series.detail", series_id=sid) if sid else None,
        })

    prev_url = _series_build_url({"page": page - 1}) if page > 1 else None
    next_url = _series_build_url({"page": page + 1}) if page < pages else None

    ctx.update({
        "sort_options": sort_options,
        "facets": facets,
        "results": results,
        "count": count,
        "page": page,
        "pages": pages,
        "prev_url": prev_url,
        "next_url": next_url,
        "error": error,
    })

    if compare:
        # No se resuelven títulos/gráfico acá: en resultados solo se muestra un
        # contador + botón "Comparar" (el detalle vive en la vista enfocada), así
        # nos ahorramos N consultas a la API de metadata en cada búsqueda.
        # Ir a la vista de comparación enfocada: deja compare, saca q y facets.
        ctx["compare_full_href"] = _series_build_url(
            {"q": None, **{k: None for k in selected}}
        )

    return toolkit.render("series/index.html", extra_vars=ctx)


@series_bp.route("/<path:series_id>")
def detail(series_id):
    count, entry = _series_fetch_meta(series_id)
    graphic_url = f"{SERIES_METADATA_URL}?ids={series_id}"
    csv_url = f"{SERIES_METADATA_URL}?ids={series_id}&format=csv"

    if count is None:
        # Error de red/parse: degradamos con gracia, no 500.
        return toolkit.render("series/detail.html", extra_vars={
            "page_title": "Serie de Tiempo",
            "series_id": series_id,
            "error": True,
        })
    if entry is None or count == 0:
        # La API respondió pero el id no existe: 404 legítimo (ruta por id explícito).
        return toolkit.abort(404, toolkit._("No encontramos esa serie de tiempo."))

    c = _series_meta_common(entry)
    field = c["field"]
    dataset = c["dataset"]

    return toolkit.render("series/detail.html", extra_vars={
        "page_title": c["title"] or "Serie de Tiempo",
        "series_id": series_id,
        "title": c["title"],
        "code": field.get("title"),  # slug técnico, para mostrar chico/mono
        "publisher": c["publisher_name"],
        "source": dataset.get("source"),
        "theme": c["theme_label"],
        "dataset_title": dataset.get("title"),
        "dataset_description": dataset.get("description"),
        "units": field.get("units"),
        "frequency_label": _series_frequency_label(field.get("frequency")),
        "date_start": field.get("time_index_start"),
        "date_end": field.get("time_index_end"),
        "issued": _series_format_date(dataset.get("issued")),
        "value_count": count,
        "last_value": _series_format_number(field.get("last_value")),
        "hits_90_days": field.get("hits_90_days"),
        "hits_total": field.get("hits_total"),
        "graphic_url": graphic_url,
        "csv_url": csv_url,
        "breadcrumb_theme": c["theme_label"],
        # ponytail: "Agregar a comparación" arranca una comparación nueva con
        # solo esta serie. Encadenar el compare previo pediría pasar ?from_compare
        # desde la vista principal; no hace falta para la v1.
        "add_to_compare_href": toolkit.url_for("series.series", compare=series_id),
        "error": False,
    })
