"""Characterization tests for planetutils.download.

These pin the current, partly-broken behavior of the HTTP layer before it is
rewritten onto requests. Two tests are marked xfail(strict=True): they assert
the DESIRED behavior, so when the rewrite lands they flip to passing and the
strict marker forces the marker itself to be removed.
"""
import pytest
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
    @pytest.mark.xfail(strict=True, reason='no raise_for_status(); rewrite on requests fixes this')
    def test_error_response_should_not_be_written_to_disk(self, tmp_path):
        """THE BUG: a 403 body is written as if it were a tile.

        tile_exists() then reports the file as present forever, which is how a
        0-byte / error-XML .hgt ends up permanently cached in a data dir.
        """
        responses.add(responses.GET, URL, body=b'<Error>AccessDenied</Error>',
                      status=403)
        out = tmp_path / 'tile.tif'
        with pytest.raises(Exception):
            download.download(URL, str(out))
        assert not out.exists()

    @responses.activate
    def test_current_behavior_writes_the_error_body(self, tmp_path):
        # CHARACTERIZATION of the bug above. Delete this when it is fixed.
        responses.add(responses.GET, URL, body=b'<Error>AccessDenied</Error>',
                      status=403)
        out = tmp_path / 'tile.tif'
        download.download(URL, str(out))
        assert out.read_bytes() == b'<Error>AccessDenied</Error>'

    @responses.activate
    @pytest.mark.xfail(strict=True, reason='no timeout passed; rewrite on requests fixes this')
    def test_should_pass_a_timeout(self, tmp_path):
        captured = {}
        real_get = download.requests.get

        def spy(url, **kw):
            captured.update(kw)
            return real_get(url, **kw)

        responses.add(responses.GET, URL, body=b'x', status=200)
        download.requests.get = spy
        try:
            download.download(URL, str(tmp_path / 'o'))
        finally:
            download.requests.get = real_get
        assert captured.get('timeout') is not None


class TestDownloadGzip:
    """download_gzip currently pipes curl into gzip -d via two Popens.

    It checks neither exit code, so a 404 silently produces a truncated or
    empty output file -- the direct cause of the 0-byte .hgt observed in a
    real data directory.
    """

    @pytest.mark.xfail(strict=True, reason='exit codes unchecked; rewrite on requests+gzip fixes this')
    def test_http_error_should_raise(self, tmp_path, monkeypatch):
        class FailingProc:
            def __init__(self, *a, **kw):
                self.stdout = None
                self.returncode = 22

            def wait(self):
                return 22

        monkeypatch.setattr(download.subprocess, 'Popen', FailingProc)
        out = tmp_path / 'tile.hgt'
        with pytest.raises(Exception):
            download.download_gzip(URL, str(out))

    def test_current_behavior_swallows_failure(self, tmp_path, monkeypatch):
        # CHARACTERIZATION: a failing pipeline leaves a 0-byte file behind and
        # raises nothing at all.
        class FailingProc:
            def __init__(self, *a, **kw):
                self.stdout = None

            def wait(self):
                return 22

        monkeypatch.setattr(download.subprocess, 'Popen', FailingProc)
        out = tmp_path / 'tile.hgt'
        download.download_gzip(URL, str(out))
        assert out.exists()
        assert out.stat().st_size == 0


class TestDownloadCurl:
    def test_raises_on_nonzero_exit(self, tmp_path, monkeypatch):
        class Proc:
            def communicate(self):
                return (b'', b'error')

            def wait(self):
                return 22

        monkeypatch.setattr(download.subprocess, 'Popen',
                            lambda *a, **kw: Proc())
        with pytest.raises(Exception, match='Error downloading'):
            download.download_curl(URL, str(tmp_path / 'o'))

    def test_succeeds_on_zero_exit(self, tmp_path, monkeypatch):
        class Proc:
            def communicate(self):
                return (b'', b'')

            def wait(self):
                return 0

        monkeypatch.setattr(download.subprocess, 'Popen',
                            lambda *a, **kw: Proc())
        download.download_curl(URL, str(tmp_path / 'o'))
