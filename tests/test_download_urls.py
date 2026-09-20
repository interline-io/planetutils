"""Characterization tests for URL construction and the download layer.

These pin behavior that is about to be rewritten:
  * the api_token is currently a QUERY PARAMETER (and gets logged)
  * download_curl's `--compressed` flag reads inverted but may be deliberate
  * the region-aware S3 URLs added in PR #40 shipped with no test at all

Nothing here touches the network.
"""
import pytest
import responses

from planetutils import download
from planetutils.elevation_tile_downloader import (
    ElevationDownloader,
    ElevationGeotiffDownloader,
    ElevationSkadiDownloader,
)
from planetutils.osm_extract_downloader import OsmExtractDownloader
from planetutils.tilepack_downloader import TilepackDownloader


@pytest.fixture
def curl_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(
        download, 'download_curl',
        lambda url, outpath, **kw: calls.append((url, outpath, kw)))
    return calls


class TestOsmExtractDownloaderUrls:
    def test_latest_uses_download_latest_with_string_id(self, curl_calls):
        OsmExtractDownloader().download('/out.pbf', 'abidjan_ivory-coast')
        url, outpath, _kw = curl_calls[0]
        assert url.startswith(
            'https://app.interline.io/osm_extracts/download_latest?')
        assert 'string_id=abidjan_ivory-coast' in url
        assert 'data_format=pbf' in url
        assert outpath == '/out.pbf'

    def test_pinned_version_uses_version_path_and_no_string_id(self, curl_calls):
        OsmExtractDownloader().download('/out.pbf', 'abidjan_ivory-coast',
                                        osm_extract_version='2024-01-01')
        url, _outpath, _kw = curl_calls[0]
        assert url.startswith(
            'https://app.interline.io/osm_extracts/2024-01-01/download?')
        assert 'string_id' not in url

    def test_api_token_is_a_query_parameter(self, curl_calls):
        # CHARACTERIZATION: the token currently travels in the URL, where it is
        # also debug-logged and visible in the curl argv via `ps`. Moving it to
        # an Authorization header requires server-side support; re-baseline this
        # test in that commit.
        OsmExtractDownloader().download('/out.pbf', 'x', api_token='SECRET')
        url, _outpath, _kw = curl_calls[0]
        assert 'api_token=SECRET' in url

    def test_data_format_is_passed_through(self, curl_calls):
        OsmExtractDownloader().download('/out.pbf', 'x', data_format='geojson')
        assert 'data_format=geojson' in curl_calls[0][0]


class TestTilepackDownloaderUrls:
    def test_latest(self, curl_calls):
        TilepackDownloader().download('/out.tar')
        url, _outpath, kw = curl_calls[0]
        assert url.startswith(
            'https://app.interline.io/valhalla_planet_tilepacks/download_latest')
        assert kw == {'compressed': False}

    def test_pinned_version(self, curl_calls):
        TilepackDownloader().download('/out.tar', version='2024-01-01')
        assert curl_calls[0][0].startswith(
            'https://app.interline.io/valhalla_planet_tilepacks/'
            '2024-01-01/download')

    def test_api_token_is_a_query_parameter(self, curl_calls):
        TilepackDownloader().download('/out.tar', api_token='SECRET')
        assert 'api_token=SECRET' in curl_calls[0][0]

    def test_compressed_flag_forwarded(self, curl_calls):
        TilepackDownloader().download('/out.tar', compressed=True)
        assert curl_calls[0][2] == {'compressed': True}


class TestDownloadCompressionSemantics:
    """`compressed` used to control curl's --compressed flag; it now controls
    the Accept-Encoding header. The meaning is unchanged: when the payload is
    already compressed, ask for it verbatim."""

    @responses.activate
    def test_compressed_true_requests_identity(self, tmp_path):
        responses.add(responses.GET, 'https://example.org/x', body=b'D',
                      status=200)
        download.download_curl('https://example.org/x', str(tmp_path / 'o'),
                               compressed=True)
        assert responses.calls[0].request.headers[
            'Accept-Encoding'] == 'identity'

    @responses.activate
    def test_compressed_false_allows_transfer_compression(self, tmp_path):
        responses.add(responses.GET, 'https://example.org/x', body=b'D',
                      status=200)
        download.download_curl('https://example.org/x', str(tmp_path / 'o'),
                               compressed=False)
        assert responses.calls[0].request.headers.get(
            'Accept-Encoding') != 'identity'


class TestElevationTileUrls:
    """The region-aware S3 URLs from PR #40 -- previously untested."""

    @pytest.fixture
    def urls(self, monkeypatch):
        # ElevationSkadiDownloader overrides _download (it routes through
        # download_gzip), so patching only the base class would let the Skadi
        # cases make real network calls.
        captured = []
        recorder = lambda self, url, op: captured.append(url)  # noqa: E731
        for kls in (ElevationDownloader, ElevationGeotiffDownloader,
                    ElevationSkadiDownloader):
            monkeypatch.setattr(kls, '_download', recorder)
        return captured

    def test_geotiff_us_east_1(self, urls, tmp_path):
        d = ElevationGeotiffDownloader(str(tmp_path), zoom=5)
        d.download_tile('elevation-tiles-prod', 'geotiff', 5, 1, 2)
        assert urls[0] == (
            'https://elevation-tiles-prod.s3.amazonaws.com/geotiff/5/1/2.tif')

    def test_geotiff_eu_central_1(self, urls, tmp_path):
        d = ElevationGeotiffDownloader(str(tmp_path), region='eu-central-1',
                                       zoom=5)
        d.download_tile('elevation-tiles-prod', 'geotiff', 5, 1, 2)
        assert urls[0] == (
            'https://elevation-tiles-prod-eu.s3.eu-central-1.amazonaws.com/'
            'geotiff/5/1/2.tif')

    def test_skadi_us_east_1_appends_gz(self, urls, tmp_path):
        d = ElevationSkadiDownloader(str(tmp_path))
        d.download_tile('elevation-tiles-prod', 'skadi', 0, -123, 37)
        assert urls[0] == (
            'https://elevation-tiles-prod.s3.amazonaws.com/'
            'skadi/N37/N37W123.hgt.gz')

    def test_skadi_eu_central_1(self, urls, tmp_path):
        d = ElevationSkadiDownloader(str(tmp_path), region='eu-central-1')
        d.download_tile('elevation-tiles-prod', 'skadi', 0, -123, 37)
        assert urls[0] == (
            'https://elevation-tiles-prod-eu.s3.eu-central-1.amazonaws.com/'
            'skadi/N37/N37W123.hgt.gz')

    def test_unknown_region_falls_back_to_default_bucket(self, urls, tmp_path):
        # CHARACTERIZATION: an unrecognized region silently falls back to the
        # default bucket but keeps the region in the hostname, producing a URL
        # that cannot resolve. Arguably should raise.
        d = ElevationGeotiffDownloader(str(tmp_path), region='ap-south-1',
                                       zoom=5)
        d.download_tile('elevation-tiles-prod', 'geotiff', 5, 1, 2)
        assert urls[0] == (
            'https://elevation-tiles-prod.s3.ap-south-1.amazonaws.com/'
            'geotiff/5/1/2.tif')
