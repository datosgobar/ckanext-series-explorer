ckanext-series-explorer
========================

Esta extensión agrega una página `/series` a CKAN: un buscador, comparador y
visualizador de detalle para series de tiempo de la
[API Series de Tiempo](https://apis.datos.gob.ar/series/api/) de Argentina
(`apis.datos.gob.ar/series`).

Funcionalidades:

* Búsqueda de texto libre con filtros (tema, fuente, publicador, unidad).
* Selección de varias series para compararlas en un mismo gráfico.
* Página de detalle por serie, con gráfico, metadata y descarga de CSV.

Los gráficos se renderizan con el componente nativo
[Poncho `TSComponents.Graphic`](https://github.com/datosgobar/series-tiempo-ar-explorer),
cargado por CDN. La extensión no usa ningún dataset local — todos los datos
se consultan en vivo contra la API pública nacional.

Probado en CKAN 2.11.

## Instalación

Usá `pip` para instalar este plugin, asumiendo que ya
[armaste un virtualenv](http://docs.ckan.org/en/latest/maintaining/installing/install-from-source.html#install-ckan-into-a-python-virtual-environment):

```
pip install -e 'git+https://github.com/datosgobar/ckanext-series-explorer.git#egg=ckanext-series-explorer'
pip install -r requirements.txt
```

Agregá `series_explorer` a `ckan.plugins` en tu archivo de configuración:

```
ckan.plugins = series_explorer
```

## Configuración

Ninguna por el momento — los endpoints de la API están fijos en `views.py`
(`SERIES_API_URL` / `SERIES_METADATA_URL`).

## Tests

```
pytest --ckan-ini=test.ini
```
