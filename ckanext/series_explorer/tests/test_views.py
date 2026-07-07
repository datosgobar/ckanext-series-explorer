"""Tests for views.py — buscador de series de tiempo."""

import pytest

import ckan.plugins.toolkit as tk
import ckanext.series_explorer.views as views


def test_series_frequency_label():
    assert views._series_frequency_label("R/P1M") == "Mensual"
    assert views._series_frequency_label("R/P1Y") == "Anual"
    # Fallback: código desconocido se devuelve crudo, no se oculta.
    assert views._series_frequency_label("R/P2W") == "R/P2W"
    assert views._series_frequency_label(None) is None


def test_series_build_url(app):
    with app.flask_app.test_request_context("/series/?q=pbi&page=2&sort_by=frequency"):
        # Override reemplaza; page eliminada con None.
        url = views._series_build_url({"sort_by": "relevance", "page": None})
        assert url.startswith("/series/?")
        assert "sort_by=relevance" in url
        assert "q=pbi" in url
        assert "page=" not in url
        # Lista setea múltiples valores repitiendo la key.
        url = views._series_build_url({"dataset_theme": ["Empleo", "Salud"]})
        assert "dataset_theme=Empleo" in url
        assert "dataset_theme=Salud" in url


def test_series_format_number():
    # Estilo argentino: miles con ".", decimales con ",".
    assert views._series_format_number("11831.9766") == "11.831,98"
    assert views._series_format_number(1234567.5) == "1.234.567,50"
    assert views._series_format_number("-42.1") == "-42,10"
    assert views._series_format_number(1000, 0) == "1.000"
    # None / no-castea → None (el template decide si oculta el bloque).
    assert views._series_format_number(None) is None
    assert views._series_format_number("abc") is None


def test_series_format_date():
    assert views._series_format_date("2026-05-01") == "may. 26"
    assert views._series_format_date("2017-09-28") == "sep. 17"
    assert views._series_format_date(None) is None
    assert views._series_format_date("mal") is None


def test_series_facet_buckets():
    # Forma real de la API: {"label": ..., "series_count": ...} (no "key"/"count").
    aggregations = {
        "dataset_theme": [
            {"label": "Empleo e Ingresos", "series_count": 422},
            {"label": "Precios", "series_count": 90},
        ]
    }
    buckets = views._series_facet_buckets(aggregations, "dataset_theme", [])
    assert buckets == {"Empleo e Ingresos": 422, "Precios": 90}
    # Valor seleccionado que la API no devolvió como bucket: aparece con count 0.
    buckets = views._series_facet_buckets(aggregations, "dataset_theme", ["Salud"])
    assert buckets["Salud"] == 0
    # Faceta sin aggregations ni selección: vacío.
    assert views._series_facet_buckets({}, "units", []) == {}


def test_series_facet_href_toggle(app):
    qs = "/series/?dataset_theme=Empleo&dataset_theme=Salud&page=3"
    with app.flask_app.test_request_context(qs):
        # Sacar un valor activo: queda el otro, page reseteada.
        url = views._series_facet_href("dataset_theme", "Empleo", is_active=True)
        assert "dataset_theme=Salud" in url
        assert "dataset_theme=Empleo" not in url
        assert "page=" not in url
        # Agregar un valor nuevo: conserva los existentes.
        url = views._series_facet_href("dataset_theme", "Educacion", is_active=False)
        assert "dataset_theme=Empleo" in url
        assert "dataset_theme=Salud" in url
        assert "dataset_theme=Educacion" in url


@pytest.mark.ckan_config("ckan.plugins", "series_explorer")
@pytest.mark.usefixtures("with_plugins")
def test_series_degrada_con_api_caida(app, monkeypatch):
    import ckanext.series_explorer.views as v

    def boom(*a, **k):
        raise v.requests.RequestException("down")

    monkeypatch.setattr(v.requests, "get", boom)
    resp = app.get(tk.h.url_for("series.series"))
    # No 500: la API externa caída degrada con gracia.
    assert resp.status_code == 200


class _FakeResp:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


@pytest.mark.ckan_config("ckan.plugins", "series_explorer")
@pytest.mark.usefixtures("with_plugins")
def test_series_detail_404_cuando_no_existe(app, monkeypatch):
    import ckanext.series_explorer.views as v

    # La API responde OK pero sin datos → 404 legítimo (no 500).
    monkeypatch.setattr(
        v.requests, "get", lambda *a, **k: _FakeResp({"count": 0, "meta": []})
    )
    resp = app.get(
        tk.h.url_for("series.detail", series_id="999.9_NO_EXISTE"),
        expect_errors=True,
    )
    assert resp.status_code == 404


@pytest.mark.ckan_config("ckan.plugins", "series_explorer")
@pytest.mark.usefixtures("with_plugins")
def test_series_detail_404_cuando_api_responde_400(app, monkeypatch):
    import ckanext.series_explorer.views as v

    # La API responde 400 "Serie inexistente" para un id inválido/inexistente
    # — es un "no encontrado", no una falla de red (no debe degradar a error=True).
    monkeypatch.setattr(
        v.requests,
        "get",
        lambda *a, **k: _FakeResp(
            {"errors": [{"error": "Serie inexistente: no_existe"}]}, status_code=400
        ),
    )
    resp = app.get(
        tk.h.url_for("series.detail", series_id="no_existe"),
        expect_errors=True,
    )
    assert resp.status_code == 404


def test_series_compare_parse_ambos_formatos(app):
    # ?compare=a,b y ?compare=a&compare=b deben parsear igual.
    for qs in ("/series/?compare=a,b", "/series/?compare=a&compare=b"):
        with app.flask_app.test_request_context(qs):
            args = views.toolkit.request.args
            compare = [c for v in args.getlist("compare") for c in v.split(",") if c]
            assert compare == ["a", "b"]
