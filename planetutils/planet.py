#!/usr/bin/env python
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.request import urlopen

from . import download, log
from .bbox import validate_bbox

try:
    import boto3
except ImportError:
    boto3 = None

# osm_planet_extract is the one command that still needs a system binary:
# a correct bbox extract requires reference completion (osmium's
# complete_ways/smart strategies), which pyosmium does not expose.
INSTALL_HINTS = {
    'osmium': (
        'osmium-tool is required for --toolchain=osmium.\n'
        '  macOS:          brew install osmium-tool\n'
        '  Debian/Ubuntu:  apt install osmium-tool\n'
        '  Windows:        conda install conda-forge::osmium-tool\n'
        '  or use the container: ghcr.io/interline-io/planetutils'
    ),
    'osmconvert': (
        'osmconvert (osmctools) is required for --toolchain=osmctools.\n'
        '  macOS:          brew install osmctools\n'
        '  Debian/Ubuntu:  apt install osmctools\n'
        '  or use the container: ghcr.io/interline-io/planetutils'
    ),
    'pyosmium-up-to-date': (
        'pyosmium-up-to-date ships in the `osmium` wheel, which is a\n'
        'dependency of this package, so it is normally installed alongside\n'
        'it. If it is missing, reinstall planetutils in a clean environment,\n'
        'or install it directly with: pip install "osmium>=4,<5"'
    ),
    'osmosis': (
        'osmosis is required for --toolchain=osmosis, and it needs a JRE.\n'
        '  macOS:          brew install osmosis\n'
        '  Debian/Ubuntu:  apt install osmosis\n'
        '  or use the container: ghcr.io/interline-io/planetutils\n'
        'For updates, --toolchain=osmium needs no system binaries at all.'
    ),
}


class MissingBinaryError(Exception):
    """Raised when a required external tool is not on PATH."""


class PlanetPathError(Exception):
    """Raised when the input/output planet paths are unusable."""


def require_binary(name):
    """Resolve `name` on PATH, raising an actionable error if absent.

    Console scripts installed alongside this package (pyosmium-up-to-date)
    may not be on PATH when the package was pip-installed into a venv that
    is not activated, so look next to the running interpreter first.
    """
    local = os.path.join(os.path.dirname(sys.executable), name)
    for candidate in (local, local + '.exe'):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    found = shutil.which(name)
    if found:
        return found
    raise MissingBinaryError(
        '%s not found on PATH.\n%s' % (name, INSTALL_HINTS.get(name, '')))


def check_update_paths(osmpath, outpath):
    """Refuse to write an updated planet over its own input.

    Both toolchains read the input while writing the output, so passing the
    same file for both produces a corrupt planet rather than an error -- the
    command appears to succeed. Catches the same file reached by a different
    spelling (a relative path, a symlink, a hardlink, or a case-insensitive
    filesystem) too.

    Takes plain paths so the CLI can call it before downloading a planet
    that may be tens of gigabytes.
    """
    if os.path.exists(outpath) and os.path.exists(osmpath):
        try:
            same = os.path.samefile(osmpath, outpath)
        except OSError:
            same = False
    else:
        same = (os.path.normcase(os.path.realpath(osmpath)) ==
                os.path.normcase(os.path.realpath(outpath)))
    if same:
        raise PlanetPathError(
            'input and output are the same file: %s\n'
            'The planet is read while the update is written, so this would '
            'corrupt it. Write to a new path and replace the original '
            'afterwards.' % outpath)


class PlanetBase:
    # Set by extract_commands(): when commands are only being printed, any
    # config file they reference has to outlive the call.
    keep_config = False

    def __init__(self, osmpath=None, grain='hour', changeset_url=None, osmosis_workdir=None):
        self.osmpath = osmpath
        d, p = os.path.split(osmpath)
        self.osmosis_workdir = osmosis_workdir or os.path.join(d, '%s.workdir'%p)

    def _run(self, args):
        # Single seam through which every external command is executed.
        # Tests replace this to capture argv without needing the binaries.
        #
        # The binary is resolved here, at execution time, rather than when
        # the argv is built: --commands only prints commands, and must work
        # on a machine that does not have the toolchain installed.
        args = [require_binary(args[0])] + list(args[1:])
        return subprocess.check_output(
            args,
            shell=False,
            text=True,
            encoding='utf-8',
            errors='replace',
        )

    def command(self, args):
        log.debug(args)
        return self._run(args)

    def check_update_paths(self, outpath):
        if not os.path.exists(self.osmpath):
            raise PlanetPathError(
                'planet file does not exist: %s' % self.osmpath)
        check_update_paths(self.osmpath, outpath)

    def osmosis(self, *args):
        return self.command(['osmosis'] + list(args))

    def osmconvert(self, *args):
        return self.command(['osmconvert'] + list(args))

    TIMESTAMP_FORMAT = '%Y-%m-%dT%H:%M:%SZ'

    def get_timestamp(self):
        """Return the planet file's timestamp as an ISO-8601 Z string.

        Uses pyosmium, so this needs no external binary on any platform.
        Mirrors what osmconvert did: prefer the header's replication
        timestamp, and fall back to scanning for the newest object when the
        header does not carry one (which is the case for most extracts).
        """
        import osmium

        header = osmium.io.Reader(
            osmium.io.File(self.osmpath),
            osmium.osm.osm_entity_bits.NOTHING,
        )
        try:
            timestamp = header.header().get('osmosis_replication_timestamp')
        finally:
            header.close()
        if timestamp:
            return timestamp.strip()

        log.debug('no replication timestamp in header; scanning for the newest object')
        newest = None
        for obj in osmium.FileProcessor(self.osmpath):
            t = obj.timestamp
            if t and (newest is None or t > newest):
                newest = t
        if newest is None:
            raise Exception('could not determine timestamp for %s' % self.osmpath)
        return newest.strftime(self.TIMESTAMP_FORMAT)

class Planet(PlanetBase):
    pass

def warn_if_polygon_reduced(name, bbox, toolchain):
    """Warn when a polygon extent is about to be reduced to its bbox.

    Only the osmium toolchain honours polygon geometry; osmosis and
    osmconvert take a bounding box. Silently widening a multi-polygon to its
    bounding box can pull in far more than the user asked for, so say so.
    """
    is_rectangle = getattr(bbox, 'is_rectangle', None)
    if is_rectangle is not None and not is_rectangle():
        log.warning(
            '%s: the %s toolchain extracts bounding boxes, so this polygon '
            'is being widened to %s. Use --toolchain=osmium to honour the '
            'polygon.' % (name, toolchain, bbox.bbox()))


class PlanetExtractor(PlanetBase):
    def extract_bboxes(self, bboxes, workers=1, outpath='.'):
        raise NotImplementedError

    def extract_bbox(self, name, bbox, workers=1, outpath='.'):
        return self.extract_bboxes({name: bbox}, outpath=outpath, workers=workers)

    def extract_commands(self, bboxes, outpath='.', **kw):
        args = []
        self.command = lambda x:args.append(x)
        self.keep_config = True
        try:
            self.extract_bboxes(bboxes, outpath=outpath, **kw)
        finally:
            del self.command
            self.keep_config = False
        return args

class PlanetExtractorOsmosis(PlanetExtractor):
    def extract_bboxes(self, bboxes, workers=1, outpath='.', **kw):
        args = []
        args += ['--read-pbf-fast', self.osmpath, 'workers=%s'%int(workers)]
        args += ['--tee', str(len(bboxes))]
        for name, bbox in bboxes.items():
            warn_if_polygon_reduced(name, bbox, 'osmosis')
            validate_bbox(bbox)
            left, bottom, right, top = bbox
            arg = [
                '--bounding-box',
                'left=%0.5f'%left,
                'bottom=%0.5f'%bottom,
                'right=%0.5f'%right,
                'top=%0.5f'%top,
                '--write-pbf',
                os.path.join(outpath, '%s.osm.pbf'%name)
            ]
            args += arg
        self.osmosis(*args)

class PlanetExtractorOsmconvert(PlanetExtractor):
    def extract_bboxes(self, bboxes, workers=1, outpath='.', **kw):
        for name, bbox in bboxes.items():
            self.extract_bbox(name, bbox, outpath=outpath)

    def extract_bbox(self, name, bbox, workers=1, outpath='.', **kw):
        warn_if_polygon_reduced(name, bbox, 'osmctools')
        validate_bbox(bbox)
        left, bottom, right, top = bbox
        args = [
            self.osmpath,
            '-b=%s,%s,%s,%s'%(left, bottom, right, top),
            '-o=%s'%os.path.join(outpath, '%s.osm.pbf'%name)
        ]
        self.osmconvert(*args)

class PlanetExtractorOsmium(PlanetExtractor):
    def extract_bboxes(self, bboxes, workers=1, outpath='.', strategy='complete_ways', **kw):
        extracts = []
        for name, bbox in bboxes.items():
            ext = {
                'output': '%s.osm.pbf'%name,
                'output_format': 'pbf',
            }
            if bbox.is_rectangle():
                left, bottom, right, top = bbox.bbox()
                ext['bbox'] = {'left': left, 'right': right, 'top': top, 'bottom':bottom}
            else:
                ftype = bbox.geometry.get('type', '').lower()
                ext[ftype] = bbox.geometry.get('coordinates', [])
            extracts.append(ext)
        config = {'directory': outpath, 'extracts': extracts}
        with tempfile.NamedTemporaryFile(mode='w', delete=False,
                                         suffix='.json',
                                         encoding='utf-8') as f:
            json.dump(config, f)
            path = f.name
        try:
            self.command(['osmium', 'extract', '-s', strategy, '-c', path,
                          self.osmpath])
        finally:
            # Under --commands the command is printed rather than run, so the
            # config must survive for the user to run it by hand. Otherwise
            # clean up, including when osmium fails.
            if not self.keep_config:
                os.unlink(path)

class PlanetDownloader(PlanetBase):
    def download_planet(self):
        raise NotImplementedError

class PlanetDownloaderHttp(PlanetBase):
    def _download(self, url, outpath):
        # Uses the requests-based helper rather than shelling out to curl,
        # which is not installed in the container and is not available by
        # default on Windows. The planet file is tens of gigabytes and the
        # transfer is not resumable, so it gets the long read timeout.
        download.download_curl(url, outpath, compressed=True,
                               timeout=download.LARGE_FILE_TIMEOUT)

    def download_planet(self, url=None):
        if os.path.exists(self.osmpath):
            raise Exception('planet file exists: %s'%self.osmpath)
        url = url or 'https://planet.openstreetmap.org/pbf/planet-latest.osm.pbf'
        self._download(url, self.osmpath)

class PlanetDownloaderS3(PlanetBase):
    def download_planet(self):
        self.download_planet_latest()

    def download_planet_latest(self, bucket=None, prefix=None, match=None):
        if os.path.exists(self.osmpath):
            raise Exception('planet file exists: %s'%self.osmpath)
        match = match or '.*(planet[-_:T0-9]+.osm.pbf)$'
        bucket = bucket or 'osm-pds'
        objs = self._get_planets(bucket, prefix, match)
        objs = sorted(objs, key=lambda x:x.key)
        for i in objs:
            log.info('found planet: s3://%s/%s'%(i.bucket_name, i.key))
        planet = objs[-1]
        log.info('downloading: s3://%s/%s to %s'%(planet.bucket_name, planet.key, self.osmpath))
        self._download(planet.bucket_name, planet.key)

    def _download(self, bucket_name, key):
        if not boto3:
            raise Exception('please install boto3')
        s3 = boto3.client('s3')
        s3.download_file(bucket_name, key, self.osmpath)

    def _get_planets(self, bucket, prefix, match):
        if not boto3:
            raise Exception('please install boto3')
        r = re.compile(match)
        s3 = boto3.resource('s3')
        s3bucket = s3.Bucket(bucket)
        objs = []
        for obj in s3bucket.objects.filter(Prefix=(prefix or '')):
            if r.match(obj.key):
                objs.append(obj)
        return objs


class PlanetUpdater(PlanetBase):
    def update_planet(self, outpath, grain='hour', changeset_url=None, **kw):
        raise NotImplementedError

class PlanetUpdaterOsmium(PlanetBase):
    def update_planet(self, outpath, grain='minute', changeset_url=None, size='1024', **kw):
        changeset_url = changeset_url or 'https://planet.openstreetmap.org/replication/%s'%grain
        self.check_update_paths(outpath)
        self.command(['pyosmium-up-to-date', '-s', size, '--server',
                      changeset_url, '-v', self.osmpath, '-o', outpath])

class PlanetUpdaterOsmosis(PlanetBase):
    def update_planet(self, outpath, grain='minute', changeset_url=None, **kw):
        self.check_update_paths(outpath)
        self.changeset_url = changeset_url or 'https://planet.openstreetmap.org/replication/%s'%grain
        self._initialize()
        self._initialize_state()
        self._get_changeset()
        self._apply_changeset(outpath)

    def _initialize(self):
        configpath = os.path.join(self.osmosis_workdir, 'configuration.txt')
        if os.path.exists(configpath):
            return
        if os.path.exists(self.osmosis_workdir) and not os.path.isdir(self.osmosis_workdir):
            raise Exception('workdir exists and is not a directory: %s'%self.osmosis_workdir)
        try:
            os.makedirs(self.osmosis_workdir)
        except OSError:
            pass
        self.osmosis(
            '--read-replication-interval-init',
            'workingDirectory=%s'%self.osmosis_workdir
        )
        with open(configpath, 'w', encoding='utf-8') as f:
            f.write('''
                baseUrl=%s
                maxInterval=0
            '''%self.changeset_url)

    def _initialize_state(self):
        statepath = os.path.join(self.osmosis_workdir, 'state.txt')
        if os.path.exists(statepath):
            return
        timestamp = self.get_timestamp()
        url = 'https://replicate-sequences.osm.mazdermind.de/?%s'%timestamp
        state = urlopen(url).read().decode('utf-8')
        with open(statepath, 'w', encoding='utf-8') as f:
            f.write(state)

    def _get_changeset(self):
        self.osmosis(
            '--read-replication-interval',
            'workingDirectory=%s'%self.osmosis_workdir,
            '--simplify-change',
            '--write-xml-change',
            os.path.join(self.osmosis_workdir, 'changeset.osm.gz')
        )

    def _apply_changeset(self, outpath):
        self.osmosis(
            '--read-xml-change',
            os.path.join(self.osmosis_workdir, 'changeset.osm.gz'),
            '--read-pbf',
            self.osmpath,
            '--apply-change',
            '--write-pbf',
            outpath
        )
