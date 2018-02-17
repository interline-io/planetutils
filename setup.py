from setuptools import setup, find_packages
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(name='interline-planetutils',
    version='0.1',
    description='Interline Planet Utilities',
    long_description=long_description,
    url='https://github.com/interline-io/osm-planet-update',
    author='Ian Rees',
    author_email='ian@interline.io',
    license='MIT',
    packages=find_packages(exclude=['contrib', 'docs', 'tests']),
    install_requires=['boto3'],
    entry_points={
        'console_scripts': [
            'planet_update=planetutils.planet_update:main',
            'planet_extract=planetutils.planet_extract:main',
            'elevation_download=planetutils.elevation_download:main'
        ],
    },
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 2'
    ]
)
