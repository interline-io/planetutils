from __future__ import absolute_import, unicode_literals, print_function
from future.standard_library import install_aliases
install_aliases()
from urllib.parse import urlparse, urlencode
from urllib.request import urlopen

import os
import subprocess
import json

from . import log
from . import download

class TilepackDownloader(object):
    HOST = 'https://app.interline.io'
    def download(self, outpath, version='latest', api_token=None, compressed=False):
        # Endpoint
        url = '%s/valhalla_planet_tilepacks/%s/download'%(self.HOST, version)
        if version == 'latest':
            url = '%s/valhalla_planet_tilepacks/download_latest'%(self.HOST)
        # Make url
        u = list(urlparse.urlsplit(url))
        q = urlparse.parse_qs(u[3])
        if api_token:
            q['api_token'] = api_token
        u[3] = urlencode(q)
        url = urlparse.urlunsplit(u)
        # Download
        download.download_curl(url, outpath, compressed=compressed)
   
    def list(self):
        url = "%s/valhalla_planet_tilepacks.json"%(self.HOST)
        contents = urlopen(url).read()
        tilepacks = json.loads(contents).get('data', [])
        tilepacks = sorted(tilepacks, key=lambda x:int(x.get('id')))
        for tilepack in tilepacks:
            a = tilepack.get('attributes', {})
            if a.get('bucket_provider') == 'gcp':
                bucket = 'gs://%s/%s'%(a['bucket_name'], a['bucket_key'])
            elif a.get('bucket_provider') == 's3':
                bucket = 's3://%s/%s'%(a['bucket_name'], a['bucket_key'])
            print("""
Tilepack ID: %s
    Timestamp: %s
    Filename: %s
    Storage provider: %s
    Data sources: %s
    URL: %s
    Versions:
        valhalla: %s
        planetutils: %s
        tilepack_cutter: %s
            """%(
                tilepack['id'],
                a['osm_planet_datetime'],
                os.path.basename(a['bucket_key']),
                a['bucket_provider'],
                ", ".join(a.get('data_contents', [])),
                tilepack.get('links',{}).get('self'),
                a['valhalla_version'],
                a['interline_planetutils_version'],
                a['interline_valhalla_tile_cutter_version']
            ))