ckanext-series-explorer
========================

This extension adds a `/series` page to CKAN: a search, comparison and
detail viewer for time series data from Argentina's national
[Time Series API](https://apis.datos.gob.ar/series/api/) (`apis.datos.gob.ar/series`).

Features:

* Free-text search with facets (theme, source, publisher, unit).
* Select several series and compare them on one chart.
* Series detail page with chart, metadata and CSV download.

Charts are rendered with the native
[Poncho `TSComponents.Graphic`](https://github.com/datosgobar/series-tiempo-ar-explorer)
component, loaded from CDN. The extension does not use any local dataset —
all data is fetched live from the public national API.

Tested on CKAN 2.11.

## Installation

Use `pip` to install this plugin, assuming you have
[set up a virtualenv](http://docs.ckan.org/en/latest/maintaining/installing/install-from-source.html#install-ckan-into-a-python-virtual-environment):

```
pip install -e 'git+https://github.com/datosgobar/ckanext-series-explorer.git#egg=ckanext-series-explorer'
pip install -r requirements.txt
```

Add `series_explorer` to `ckan.plugins` in your config file:

```
ckan.plugins = series_explorer
```

## Configuration

None at present — the API endpoints are fixed in `views.py`
(`SERIES_API_URL` / `SERIES_METADATA_URL`).

## Tests

```
pytest --ckan-ini=test.ini
```

## License

Released under the GNU Affero General Public License (AGPL) v3.0. See the
file `LICENSE` for details.
