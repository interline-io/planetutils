from __future__ import absolute_import, unicode_literals
from future.standard_library import install_aliases
install_aliases()
from urllib.parse import urlparse, urlencode, urlsplit, parse_qs, urlunsplit
from urllib.request import urlopen

import subprocess
import json

from . import log
from . import download

class OsmExtractDownloader(object):
    HOST = 'https://app.interline.io'
    def download(self, outpath, osm_extract_id, osm_extract_version='latest', data_format='pbf', api_token=None):
        # Endpoint
        url = '%s/osm_extracts/%s/download'%(self.HOST, osm_extract_version)
        if osm_extract_version == 'latest':
            url = '%s/osm_extracts/download_latest'%(self.HOST)

        # Make url
        u = list(urlsplit(url))
        q = parse_qs(u[3])
        q['data_format'] = data_format
        if osm_extract_version == "latest":
            q['string_id'] = osm_extract_id
        if api_token:
            q['api_token'] = api_token
        u[3] = urlencode(q)
        url = urlunsplit(u)

        # Download
        download.download_curl(url, outpath)