import urllib
import urlparse
import subprocess

class Tilepack(object):
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
        u[3] = urllib.urlencode(q)
        url = urlparse.urlunsplit(u)
        # Download
        args = ['curl', '-L', '--fail', '-o', outpath, url]
        if not compressed:
            args.append('--compressed')
        print "Downloading to %s"%outpath
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = p.communicate()
        e = p.wait()
        if e != 0:
            print "Error downloading: %s"%err.split("curl:")[-1]
        else:
            print "Done"
            
