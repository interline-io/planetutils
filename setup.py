from setuptools import setup, find_packages
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(name='interline-planetutils',
    version='0.4.1',
    description='Interline PlanetUtils',
    long_description=long_description,
    url='https://github.com/interline-io/planetutils',
    author='Ian Rees',
    author_email='ian@interline.io',
    license='MIT',
    packages=find_packages(exclude=['contrib', 'docs', 'tests']),
    install_requires=['future', 'requests','boto3', 'osmium'],
    tests_require=['nose'],
    test_suite = 'nose.collector',
    entry_points={
        'console_scripts': [
            'osm_planet_update=planetutils.osm_planet_update:main',
            'osm_planet_extract=planetutils.osm_planet_extract:main',
            'osm_planet_get_timestamp=planetutils.osm_planet_get_timestamp:main',
            'osm_extract_download=planetutils.osm_extract_download:main',
            'elevation_tile_download=planetutils.elevation_tile_download:main',
            'valhalla_tilepack_download=planetutils.tilepack_download:main',
            'valhalla_tilepack_list=planetutils.tilepack_list:main'
        ],
    },
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 2.7'
    ]
)
