from ckan.plugins import SingletonPlugin, implements, IConfigurer, IBlueprint
import ckan.plugins.toolkit as toolkit

from ckanext.series_explorer.views import series_bp


class SeriesExplorerPlugin(SingletonPlugin):
    implements(IConfigurer)
    implements(IBlueprint)

    # ── IConfigurer ──
    def update_config(self, config_):
        toolkit.add_template_directory(config_, 'templates')
        toolkit.add_public_directory(config_, 'public')
        toolkit.add_resource('assets', 'series_explorer')

    # ── IBlueprint ──
    def get_blueprint(self):
        return [series_bp]
