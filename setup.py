from setuptools import setup, find_packages

setup(
    name='ckanext-series_explorer',
    packages=find_packages(),
    entry_points={
        'ckan.plugins': [
            'series_explorer=ckanext.series_explorer.plugin:SeriesExplorerPlugin'
        ]
    },
    message_extractors={
        'ckanext': [
            ('**.py', 'python', None),
            ('**.html', 'jinja2', None),
        ]
    },
    i18n_domain='ckanext-series_explorer',
)
