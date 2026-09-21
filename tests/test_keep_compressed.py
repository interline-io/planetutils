"""Tests for --keep-compressed (issue #47).

Skadi tiles are served gzipped and were always inflated on write, so a full
planet took ~1.6 TB on disk against ~350-500 GB compressed. Valhalla reads
.hgt.gz natively, so keeping them packed is an option rather than a
conversion step.
"""
import gzip as gziplib
import io
import re

import pytest
import responses

from planetutils.elevation_tile_downloader import ElevationSkadiDownloader

BBOX = [-122.6, 37.6, -122.4, 37.8]
TILE_URL = re.compile(r'https://elevation-tiles-prod\.s3\..*')
PAYLOAD = b'ELEVATION' * 1000


def gzipped(payload=PAYLOAD):
    buf = io.BytesIO()
    with gziplib.GzipFile(fileobj=buf, mode='wb') as f:
        f.write(payload)
    return buf.getvalue()


class TestTilePath:
    def test_default_is_uncompressed(self, tmp_path):
        d = ElevationSkadiDownloader(str(tmp_path))
        assert d.tile_path(0, -123, 37) == ['N37', 'N37W123.hgt']

    def test_compressed_carries_the_gz_suffix(self, tmp_path):
        d = ElevationSkadiDownloader(str(tmp_path), keep_compressed=True)
        assert d.tile_path(0, -123, 37) == ['N37', 'N37W123.hgt.gz']


class TestUrl:
    """The remote object is always .hgt.gz, in either mode. The URL is built
    from tile_path plus a suffix, so the compressed local name must not
    produce .hgt.gz.gz."""

    def _url(self, tmp_path, **kw):
        seen = []
        d = ElevationSkadiDownloader(str(tmp_path), **kw)
        d._download = lambda url, op, session=None: seen.append((url, op))
        d.download_tile('elevation-tiles-prod', 'skadi', 0, -123, 37)
        return seen[0]

    def test_uncompressed(self, tmp_path):
        url, op = self._url(tmp_path)
        assert url.endswith('/skadi/N37/N37W123.hgt.gz')
        assert op.endswith('N37W123.hgt')

    def test_compressed(self, tmp_path):
        url, op = self._url(tmp_path, keep_compressed=True)
        assert url.endswith('/skadi/N37/N37W123.hgt.gz'), url
        assert '.gz.gz' not in url
        assert op.endswith('N37W123.hgt.gz')


class TestWrites:
    @responses.activate
    def test_compressed_stores_the_gzip_stream_verbatim(self, tmp_path):
        body = gzipped()
        responses.add(responses.GET, TILE_URL, body=body, status=200)
        d = ElevationSkadiDownloader(str(tmp_path), workers=1,
                                     keep_compressed=True)
        d.download_bbox(BBOX)
        written = list(tmp_path.rglob('*.hgt.gz'))
        assert written, 'no .hgt.gz written'
        assert written[0].read_bytes() == body
        assert not list(tmp_path.rglob('*.hgt')) == written

    @responses.activate
    def test_compressed_output_inflates_to_the_same_bytes(self, tmp_path):
        responses.add(responses.GET, TILE_URL, body=gzipped(), status=200)
        d = ElevationSkadiDownloader(str(tmp_path), workers=1,
                                     keep_compressed=True)
        d.download_bbox(BBOX)
        path = list(tmp_path.rglob('*.hgt.gz'))[0]
        with gziplib.open(str(path), 'rb') as f:
            assert f.read() == PAYLOAD

    @responses.activate
    def test_default_still_inflates(self, tmp_path):
        responses.add(responses.GET, TILE_URL, body=gzipped(), status=200)
        d = ElevationSkadiDownloader(str(tmp_path), workers=1)
        d.download_bbox(BBOX)
        written = list(tmp_path.rglob('*.hgt'))
        assert written
        assert written[0].read_bytes() == PAYLOAD
        assert not list(tmp_path.rglob('*.hgt.gz'))

    @responses.activate
    def test_requests_the_payload_verbatim(self, tmp_path):
        """The body is already gzipped, so asking for transfer compression on
        top of it would be wrong."""
        responses.add(responses.GET, TILE_URL, body=gzipped(), status=200)
        d = ElevationSkadiDownloader(str(tmp_path), workers=1,
                                     keep_compressed=True)
        d.download_bbox(BBOX)
        assert responses.calls[0].request.headers[
            'Accept-Encoding'] == 'identity'


class TestExistingTiles:
    """Switching the flag must not invalidate a cache that is already
    complete: Valhalla reads either form."""

    def _tile(self, tmp_path, name, body):
        p = tmp_path / 'N37' / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body)
        return p

    def test_compressed_cache_seen_in_uncompressed_mode(self, tmp_path):
        self._tile(tmp_path, 'N37W123.hgt.gz', gzipped())
        d = ElevationSkadiDownloader(str(tmp_path))
        assert d.tile_exists(str(tmp_path / 'N37' / 'N37W123.hgt'))

    def test_uncompressed_cache_seen_in_compressed_mode(self, tmp_path):
        d = ElevationSkadiDownloader(str(tmp_path), keep_compressed=True)
        self._tile(tmp_path, 'N37W123.hgt', b'\0' * d.HGT_SIZE)
        assert d.tile_exists(str(tmp_path / 'N37' / 'N37W123.hgt.gz'))

    def test_truncated_gz_is_re_downloaded(self, tmp_path):
        """A .gz has no predictable size, so the magic bytes stand in for the
        HGT_SIZE check that guards the inflated form."""
        self._tile(tmp_path, 'N37W123.hgt.gz', b'x')
        d = ElevationSkadiDownloader(str(tmp_path), keep_compressed=True)
        assert not d.tile_exists(str(tmp_path / 'N37' / 'N37W123.hgt.gz'))

    def test_empty_gz_is_re_downloaded(self, tmp_path):
        self._tile(tmp_path, 'N37W123.hgt.gz', b'')
        d = ElevationSkadiDownloader(str(tmp_path), keep_compressed=True)
        assert not d.tile_exists(str(tmp_path / 'N37' / 'N37W123.hgt.gz'))

    def test_error_body_stored_as_gz_is_re_downloaded(self, tmp_path):
        self._tile(tmp_path, 'N37W123.hgt.gz', b'<Error>AccessDenied</Error>')
        d = ElevationSkadiDownloader(str(tmp_path), keep_compressed=True)
        assert not d.tile_exists(str(tmp_path / 'N37' / 'N37W123.hgt.gz'))

    def test_truncated_hgt_is_still_re_downloaded(self, tmp_path):
        self._tile(tmp_path, 'N37W123.hgt', b'\0' * 100)
        d = ElevationSkadiDownloader(str(tmp_path))
        assert not d.tile_exists(str(tmp_path / 'N37' / 'N37W123.hgt'))

    def test_missing_tile(self, tmp_path):
        d = ElevationSkadiDownloader(str(tmp_path), keep_compressed=True)
        assert not d.tile_exists(str(tmp_path / 'N37' / 'N37W123.hgt.gz'))

    @responses.activate
    def test_a_complete_compressed_cache_downloads_nothing(self, tmp_path):
        self._tile(tmp_path, 'N37W123.hgt.gz', gzipped())
        responses.add(responses.GET, TILE_URL, body=gzipped(), status=200)
        d = ElevationSkadiDownloader(str(tmp_path), workers=1)
        d.download_bbox(BBOX)
        assert len(responses.calls) == 0


class TestCli:
    def test_flag_reaches_the_downloader(self, tmp_path, monkeypatch):
        import sys

        from planetutils import elevation_tile_download
        seen = {}
        monkeypatch.setattr(
            ElevationSkadiDownloader, 'download_bbox',
            lambda self, bbox: seen.update(kc=self.keep_compressed))
        monkeypatch.setattr(sys, 'argv', [
            'elevation_tile_download', '--format=skadi', '--keep-compressed',
            '--bbox=-122.6,37.6,-122.4,37.8', '--outpath=%s' % tmp_path])
        elevation_tile_download.main()
        assert seen['kc'] is True

    def test_rejected_for_geotiff(self, tmp_path, monkeypatch, capsys):
        """GeoTIFF tiles are not served gzipped, so the flag is meaningless
        there and silently ignoring it would mislead."""
        import sys

        from planetutils import elevation_tile_download
        monkeypatch.setattr(sys, 'argv', [
            'elevation_tile_download', '--keep-compressed',
            '--bbox=-122.6,37.6,-122.4,37.8', '--outpath=%s' % tmp_path])
        with pytest.raises(SystemExit) as e:
            elevation_tile_download.main()
        assert e.value.code == 2
        assert 'skadi' in capsys.readouterr().err
