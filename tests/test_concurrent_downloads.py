"""Tests for concurrent tile downloading.

Downloads ran one tile at a time; the work is latency-bound, so fetching
several at once is worth roughly an order of magnitude. Retries and pooling
come from requests/urllib3 rather than a hand-rolled loop.

Every assertion here is written to fail if the mechanism it covers is
removed. `responses` patches HTTPAdapter.send, so an end-to-end test through
it cannot distinguish requests.get from session.get -- checks that care about
the session therefore sit at the transport boundary instead.

Prompted by PR #32 from @nitrag.
"""
import gzip as gziplib
import io
import re
import threading

import pytest
import responses

from planetutils import download
from planetutils.elevation_tile_downloader import (
    DEFAULT_WORKERS,
    MAX_WORKERS,
    ElevationDownloader,
    ElevationGeotiffDownloader,
    ElevationSkadiDownloader,
)

CA = [-124.5, 32.4, -123.5, 33.4]
TILE_URL = re.compile(r'https://elevation-tiles-prod\.s3\..*')


def gzipped(payload):
    buf = io.BytesIO()
    with gziplib.GzipFile(fileobj=buf, mode='wb') as f:
        f.write(payload)
    return buf.getvalue()


class TestRetryPolicy:
    def test_comes_from_urllib3_not_hand_rolled(self):
        retries = download.RETRY
        assert retries.total == 5
        assert retries.backoff_factor > 0
        assert {429, 503}.issubset(set(retries.status_forcelist))
        assert retries.respect_retry_after_header is True

    def test_retry_after_is_capped(self):
        """An uncapped Retry-After lets one response park a worker for as
        long as the server asks."""
        assert download.RETRY.retry_after_max == 60

    def test_mounted_on_every_scheme(self):
        """A bare Session already reports both adapters and get_adapter never
        returns None, so identity of the policy is what must be asserted."""
        s = download.make_session()
        for scheme in ('https://example.org/', 'http://example.org/'):
            assert s.get_adapter(scheme).max_retries is download.RETRY

    def test_pool_is_sized_to_the_workers(self):
        assert download.make_session(32).get_adapter(
            'https://x/')._pool_maxsize == 32

    def test_default_session_also_retries(self):
        """Callers that pass no session must still get retries, rather than
        falling back to a bare requests.get."""
        s = download.get_default_session()
        assert s.get_adapter('https://x/').max_retries is download.RETRY


class TestSessionReachesTheTransport:
    """Mutation-checked: dropping `session=` from the submit call or from
    either subclass override must fail these."""

    def _spy(self, monkeypatch):
        seen = []
        real = download._get

        def spy(url, compressed=False, timeout=download.TIMEOUT, session=None):
            seen.append(session)
            return real(url, compressed=compressed, timeout=timeout,
                        session=session)

        monkeypatch.setattr(download, '_get', spy)
        return seen

    @responses.activate
    def test_geotiff(self, tmp_path, monkeypatch):
        responses.add(responses.GET, TILE_URL, body=b'TIF', status=200)
        seen = self._spy(monkeypatch)
        ElevationGeotiffDownloader(str(tmp_path), zoom=8,
                                   workers=4).download_bbox(CA)
        assert seen
        assert all(s is not None for s in seen), 'session was not forwarded'
        assert len({id(s) for s in seen}) == 1, 'session was not reused'

    @responses.activate
    def test_skadi(self, tmp_path, monkeypatch):
        responses.add(responses.GET, TILE_URL, body=gzipped(b'HGT'),
                      status=200)
        seen = self._spy(monkeypatch)
        ElevationSkadiDownloader(str(tmp_path),
                                 workers=2).download_bbox(
                                     [-122.6, 37.6, -122.4, 37.8])
        assert seen
        assert all(s is not None for s in seen), 'session was not forwarded'


class TestConcurrency:
    def test_downloads_run_in_parallel(self, tmp_path):
        """A Barrier only releases when `parties` downloads are genuinely in
        flight at once, so a serial implementation blocks and breaks it.
        Counting thread names would be racy: an instant mock can be drained
        by one worker before the pool spawns the others.
        """
        workers = 4
        d = ElevationGeotiffDownloader(str(tmp_path), zoom=8, workers=workers)
        tiles = len(d.get_bbox_tiles(CA))
        # A Barrier resets every `parties` arrivals, so a remainder would
        # block for the full timeout and look like a tile failure.
        parties = min(workers, tiles)
        assert tiles % parties == 0, 'fixture must divide evenly'
        barrier = threading.Barrier(parties, timeout=30)
        d.download_tile = (
            lambda self, *a, **kw: barrier.wait()).__get__(d)
        d.download_bbox(CA)

    def test_every_tile_is_downloaded_exactly_once(self, tmp_path):
        got = []
        lock = threading.Lock()

        def record(self, bucket, prefix, z, x, y, suffix='', session=None):
            with lock:
                got.append((z, x, y))

        d = ElevationGeotiffDownloader(str(tmp_path), zoom=8, workers=8)
        d.download_tile = record.__get__(d)
        expected = {tuple(t) for t in d.get_bbox_tiles(CA)}
        d.download_bbox(CA)
        assert sorted(got) == sorted(expected)

    def test_futures_are_bounded(self, tmp_path, monkeypatch):
        """Submitting every tile up front pins a Future per tile for the
        whole run, which is many GB at planet scale.

        Counts submit() calls, not executions: executions are capped by
        max_workers regardless, so they cannot distinguish a bounded window
        from an unbounded one. The mock blocks so the dispatcher cannot
        advance past its window.
        """
        import planetutils.elevation_tile_downloader as mod
        workers = 4
        submits = []
        real = mod.ThreadPoolExecutor

        class Counting(real):
            def submit(self, *a, **kw):
                submits.append(1)
                return super().submit(*a, **kw)

        monkeypatch.setattr(mod, 'ThreadPoolExecutor', Counting)
        d = ElevationGeotiffDownloader(str(tmp_path), zoom=6, workers=workers)
        tiles = [(6, x, y) for x in range(40) for y in range(10)]   # 400
        release = threading.Event()

        def blocking(self, bucket, prefix, z, x, y, suffix='', session=None):
            release.wait(timeout=10)

        d.download_tile = blocking.__get__(d)

        def run():
            try:
                d._download_all(tiles, 'b', 'p', None)
            except BaseException:
                pass

        t = threading.Thread(target=run)
        t.start()
        try:
            threading.Event().wait(0.5)      # let the dispatcher fill up
            submitted = len(submits)
        finally:
            release.set()
            t.join(timeout=15)
        assert submitted <= workers * 2 + 1, (
            'submission window is unbounded: %s of %s tiles submitted'
            % (submitted, len(tiles)))
        assert submitted >= workers, 'nothing was submitted concurrently'


class TestFailFast:
    def test_first_failure_propagates(self, tmp_path):
        """Matches the serial loop this replaces: a failure aborts the run
        rather than being swallowed."""
        d = ElevationGeotiffDownloader(str(tmp_path), zoom=8, workers=2)

        def boom(self, *a, **kw):
            raise OSError('simulated')

        d.download_tile = boom.__get__(d)
        with pytest.raises(OSError, match='simulated'):
            d.download_bbox(CA)

    def test_queued_work_is_cancelled_on_failure(self, tmp_path,
                                                 monkeypatch):
        """shutdown(wait=True) would drain whatever is still queued before
        propagating. The bounded window keeps that small, but cancelling is
        what makes a failure (or Ctrl-C) stop promptly.

        Asserted on the shutdown call itself: with a bounded window the
        observable difference is only a couple of dozen tiles, too small to
        distinguish reliably by counting completions.
        """
        import planetutils.elevation_tile_downloader as mod
        calls = []
        real = mod.ThreadPoolExecutor

        class Recording(real):
            def shutdown(self, wait=True, *, cancel_futures=False):
                calls.append({'wait': wait, 'cancel_futures': cancel_futures})
                return super().shutdown(wait=wait,
                                        cancel_futures=cancel_futures)

        monkeypatch.setattr(mod, 'ThreadPoolExecutor', Recording)
        d = ElevationGeotiffDownloader(str(tmp_path), zoom=8, workers=2)

        def boom(self, *a, **kw):
            raise OSError('simulated')

        d.download_tile = boom.__get__(d)
        with pytest.raises(OSError):
            d.download_bbox(CA)
        assert calls, 'shutdown was never called'
        assert calls[-1]['cancel_futures'] is True, (
            'queued work was not cancelled on failure')
        assert calls[-1]['wait'] is False


class TestWorkerClamping:
    def test_bounds(self, tmp_path):
        def mk(w):
            return ElevationGeotiffDownloader(str(tmp_path), workers=w).workers
        assert mk(None) == DEFAULT_WORKERS
        assert mk(0) == 1
        assert mk(-8) == 1
        assert mk(8) == 8
        assert mk(100000) == MAX_WORKERS

    def test_non_numeric_raises_clearly(self, tmp_path):
        with pytest.raises(ValueError, match='must be an integer'):
            ElevationGeotiffDownloader(str(tmp_path), workers='lots')


class TestSubclassCompatibility:
    def test_overrides_match_the_base_signatures(self):
        """download_tile and _download are both called by the base class, so
        an override with an older signature breaks every download."""
        import inspect
        for name in ('download_tile', '_download'):
            base_attr = getattr(ElevationDownloader, name)
            base = inspect.signature(base_attr)
            for kls in (ElevationGeotiffDownloader, ElevationSkadiDownloader):
                if getattr(kls, name) is base_attr:
                    continue
                sig = inspect.signature(getattr(kls, name))
                assert list(sig.parameters) == list(base.parameters), (
                    '%s.%s%s diverges from the base' % (kls.__name__, name, sig))

    @responses.activate
    def test_skadi_still_uses_the_skadi_prefix_and_gz(self, tmp_path):
        responses.add(responses.GET, TILE_URL, body=gzipped(b'HGT'),
                      status=200)
        d = ElevationSkadiDownloader(str(tmp_path), workers=2)
        d.download_bbox([-122.6, 37.6, -122.4, 37.8])
        url = responses.calls[0].request.url
        assert '/skadi/' in url and url.endswith('.hgt.gz')
        assert list(tmp_path.rglob('*.hgt'))
