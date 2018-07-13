from __future__ import absolute_import, unicode_literals
import os
import subprocess
from . import log

def download(url, outpath):
    pass

def download_gzip(url, outpath):
    with open(outpath, 'wb') as f:
        ps1 = subprocess.Popen(['curl', '-L', '--fail', '-s', url], stdout=subprocess.PIPE)
        ps2 = subprocess.Popen(['gzip', '-d'], stdin=ps1.stdout, stdout=f)
        ps2.wait()

def download_curl(url, outpath, compressed=False):
    if os.path.exists(outpath):
        log.warning("Warning: output path %s already exists."%outpath)
    args = ['curl', '-L', '--fail', '-o', outpath, url]
    if not compressed:
        args.append('--compressed')

    log.info("Downloading to %s"%outpath)
    log.debug(url)
    log.debug(' '.join(args))
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = p.communicate()
    e = p.wait()
    if e != 0:
        raise Exception("Error downloading: %s"%err.split("curl:")[-1])
    else:
        log.info("Done")
        