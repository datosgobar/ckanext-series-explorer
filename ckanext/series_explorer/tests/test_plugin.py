import pytest

from ckan.plugins.toolkit import plugin_loaded


@pytest.mark.ckan_config("ckan.plugins", "series_explorer")
@pytest.mark.usefixtures("with_plugins")
def test_plugin():
    assert plugin_loaded("series_explorer")
