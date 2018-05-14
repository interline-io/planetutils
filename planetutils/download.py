import subprocess
import log

def download(url, outpath):
    pass

def download_curl(url, outpath, compressed=False):
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
        