"""Tests for planetutils.download.

This layer used to shell out to curl, and piped curl into `gzip -d` for the
Skadi format. It is now pure requests + stdlib gzip. The tests that
previously documented the silent-failure bugs now assert the fixed behavior.
"""
import gzip
import io

import pytest
import requests
import responses

from planetutils import download

URL = 'https://example.org/tile.tif'


class TestDownload:
    @responses.activate
    def test_writes_body_to_outpath(self, tmp_path):
        responses.add(responses.GET, URL, body=b'RASTERBYTES', status=200)
        out = tmp_path / 'tile.tif'
        download.download(URL, str(out))
        assert out.read_bytes() == b'RASTERBYTES'

    @responses.activate
    def test_error_response_raises_and_writes_nothing(self, tmp_path):
        """A 403 body must never be cached as if it were a tile.

        This is what produced a permanently-cached bad .hgt in a real data
        directory: the error body was written, and tile_exists() then
        reported the tile present forever.
        """
        responses.add(responses.GET, URL, body=b'<Error>AccessDenied</Error>',
                      status=403)
        out = tmp_path / 'tile.tif'
        with pytest.raises(requests.HTTPError):
            download.download(URL, str(out))
        assert not out.exists()

    @responses.activate
    def test_404_raises(self, tmp_path):
        responses.add(responses.GET, URL, status=404)
        with pytest.raises(requests.HTTPError):
            download.download(URL, str(tmp_path / 'tile.tif'))

    @responses.activate
    def test_no_part_file_is_left_behind_on_failure(self, tmp_path):
        responses.add(responses.GET, URL, status=500)
        out = tmp_path / 'tile.tif'
        with pytest.raises(requests.HTTPError):
            download.download(URL, str(out))
        assert list(tmp_path.iterdir()) == []

    def test_passes_a_timeout(self, tmp_path, monkeypatch):
        captured = {}

        class FakeResponse:
            status_code = 200
            raw = io.BytesIO(b'x')

            def raise_for_status(self):
                pass

        def spy(url, **kw):
            captured.update(kw)
            return FakeResponse()

        monkeypatch.setattr(download.requests, 'get', spy)
        download.download(URL, str(tmp_path / 'o'))
        assert captured.get('timeout') is not None


class TestDownloadGzip:
    @responses.activate
    def test_decompresses_body(self, tmp_path):
        payload = b'ELEVATIONDATA' * 100
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode='wb') as f:
            f.write(payload)
        responses.add(responses.GET, URL, body=buf.getvalue(), status=200)
        out = tmp_path / 'tile.hgt'
        download.download_gzip(URL, str(out))
        assert out.read_bytes() == payload

    @responses.activate
    def test_http_error_raises(self, tmp_path):
        responses.add(responses.GET, URL, status=404)
        out = tmp_path / 'tile.hgt'
        with pytest.raises(requests.HTTPError):
            download.download_gzip(URL, str(out))
        assert not out.exists()

    @responses.activate
    def test_requests_identity_encoding(self, tmp_path):
        """The payload is already gzipped, so don't ask for transfer
        compression on top of it -- this is what curl's absent --compressed
        flag used to express."""
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode='wb') as f:
            f.write(b'x')
        responses.add(responses.GET, URL, body=buf.getvalue(), status=200)
        download.download_gzip(URL, str(tmp_path / 'o'))
        assert responses.calls[0].request.headers['Accept-Encoding'] == 'identity'


class TestDownloadCurl:
    """Still named download_curl (it is public API) but no longer uses curl."""

    @responses.activate
    def test_writes_body(self, tmp_path):
        responses.add(responses.GET, URL, body=b'DATA', status=200)
        out = tmp_path / 'o'
        download.download_curl(URL, str(out))
        assert out.read_bytes() == b'DATA'

    @responses.activate
    def test_raises_on_error_status(self, tmp_path):
        responses.add(responses.GET, URL, status=500)
        with pytest.raises(requests.HTTPError):
            download.download_curl(URL, str(tmp_path / 'o'))

    @responses.activate
    def test_compressed_true_requests_identity(self, tmp_path):
        responses.add(responses.GET, URL, body=b'DATA', status=200)
        download.download_curl(URL, str(tmp_path / 'o'), compressed=True)
        assert responses.calls[0].request.headers['Accept-Encoding'] == 'identity'

    @responses.activate
    def test_compressed_false_allows_transfer_compression(self, tmp_path):
        responses.add(responses.GET, URL, body=b'DATA', status=200)
        download.download_curl(URL, str(tmp_path / 'o'), compressed=False)
        assert responses.calls[0].request.headers.get(
            'Accept-Encoding') != 'identity'

    @responses.activate
    def test_does_not_log_the_url(self, tmp_path, caplog):
        """The URL can carry an api_token; it must not reach the logs."""
        secret = URL + '?api_token=SECRET'
        responses.add(responses.GET, secret, body=b'DATA', status=200)
        with caplog.at_level('DEBUG'):
            download.download_curl(secret, str(tmp_path / 'o'))
        assert 'SECRET' not in caplog.text


class TestConnectionHandling:
    @responses.activate
    def test_error_response_is_closed(self, tmp_path):
        """With stream=True the pooled connection is only released once the
        body is read or closed; an unread error body leaks it."""
        responses.add(responses.GET, URL, body=b'<Error/>', status=403)
        closed = []
        real_get = download.requests.get

        def spy(url, **kw):
            r = real_get(url, **kw)
            original_close = r.close

            def tracking_close():
                closed.append(True)
                original_close()

            r.close = tracking_close
            return r

        download.requests.get = spy
        try:
            with pytest.raises(requests.HTTPError):
                download.download(URL, str(tmp_path / 'o'))
        finally:
            download.requests.get = real_get
        assert closed, 'error response was not closed'
