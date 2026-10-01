"""Tests for osm_extract_download and its Interline, Geofabrik and SliceOSM
sources. Nothing here touches the network."""
import hashlib
import json
import os
from urllib.parse import parse_qs, urlsplit

import pytest
import responses

from planetutils import osm_extract_download
from planetutils.bbox import Feature
from planetutils.osm_extract_downloader import (
    ExtractDownloadError,
    GeofabrikDownloader,
    InterlineExtractDownloader,
    SliceOsmDownloader,
    user_agent,
)

PBF = b'not really a pbf'
TASK = '2637da98-20a1-428f-b6db-18ac2861b763'


def rect(left, bottom, right, top):
    f = Feature()
    f.set_bbox([left, bottom, right, top])
    return f


class TestInterline:
    def test_url_asks_for_the_latest_pbf(self):
        url = InterlineExtractDownloader().url('us-ca', api_token='SECRET')
        parts = urlsplit(url)
        assert parts.path == '/osm_extracts/download_latest'
        assert parse_qs(parts.query) == {
            'string_id': ['us-ca'], 'data_format': ['pbf'], 'api_token': ['SECRET']}

    @responses.activate
    def test_download(self, tmp_path):
        responses.add(responses.GET, InterlineExtractDownloader.HOST + '/osm_extracts/download_latest', body=PBF)
        out = tmp_path / 'us-ca.osm.pbf'
        InterlineExtractDownloader().download('us-ca', str(out), api_token='t')
        assert out.read_bytes() == PBF
        assert responses.calls[0].request.headers['User-Agent'] == user_agent()

    @responses.activate
    def test_forbidden_explains_the_token(self, tmp_path):
        responses.add(responses.GET, InterlineExtractDownloader.HOST + '/osm_extracts/download_latest', status=403)
        with pytest.raises(ExtractDownloadError, match='API token'):
            InterlineExtractDownloader().download('us-ca', str(tmp_path / 'x'), api_token='SECRET')

    @responses.activate
    def test_gone_shows_the_servers_explanation(self, tmp_path):
        responses.add(responses.GET, InterlineExtractDownloader.HOST + '/osm_extracts/download_latest', status=410,
                      json={'errors': [{'detail': 'no longer publishes berlin_germany'}]})
        with pytest.raises(ExtractDownloadError) as e:
            InterlineExtractDownloader().download('berlin_germany', str(tmp_path / 'x'), api_token='SECRET')
        assert 'HTTP 410' in str(e.value)
        assert 'no longer publishes berlin_germany' in str(e.value)
        assert 'SECRET' not in str(e.value)
        assert not (tmp_path / 'x').exists()


INDEX = {'features': [
    {'properties': {'id': 'us/california', 'name': 'California',
                    'urls': {'pbf': 'https://download.geofabrik.de/north-america/us/california-latest.osm.pbf'}}},
    {'properties': {'id': 'berlin', 'name': 'Berlin',
                    'urls': {'pbf': 'https://download.geofabrik.de/europe/germany/berlin-latest.osm.pbf'}}},
    {'properties': {'id': 'no-pbf', 'name': 'Nothing', 'urls': {}}},
]}
BERLIN = INDEX['features'][1]['properties']['urls']['pbf']


class TestGeofabrik:
    @pytest.fixture(autouse=True)
    def index(self):
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            rsps.add(responses.GET, GeofabrikDownloader.INDEX_URL, json=INDEX)
            yield rsps

    def test_search_matches_id_or_name_and_skips_regions_without_a_pbf(self):
        g = GeofabrikDownloader()
        assert [i['id'] for i in g.search()] == ['berlin', 'us/california']
        assert [i['id'] for i in g.search('CALIF')] == ['us/california']
        assert [i['id'] for i in g.search('berl')] == ['berlin']

    def test_unknown_region(self):
        with pytest.raises(ExtractDownloadError, match='--search'):
            GeofabrikDownloader().find('california')

    def test_filename_uses_the_last_part_of_a_nested_id(self):
        assert GeofabrikDownloader.filename('us/california') == 'california.osm.pbf'
        assert GeofabrikDownloader.filename('berlin') == 'berlin.osm.pbf'

    def test_download_verifies_the_checksum(self, index, tmp_path):
        index.add(responses.GET, BERLIN + '.md5',
                  body='%s  berlin-latest.osm.pbf\n' % hashlib.md5(PBF).hexdigest())
        index.add(responses.GET, BERLIN, body=PBF)
        out = tmp_path / 'berlin.osm.pbf'
        GeofabrikDownloader().download('berlin', str(out))
        assert out.read_bytes() == PBF

    def test_checksum_mismatch_removes_the_file(self, index, tmp_path):
        index.add(responses.GET, BERLIN + '.md5', body='0' * 32 + '  berlin-latest.osm.pbf\n')
        index.add(responses.GET, BERLIN, body=PBF)
        out = tmp_path / 'berlin.osm.pbf'
        with pytest.raises(ExtractDownloadError, match='checksum mismatch'):
            GeofabrikDownloader().download('berlin', str(out))
        assert not out.exists()

    def test_missing_checksum_still_downloads(self, index, tmp_path, caplog):
        index.add(responses.GET, BERLIN + '.md5', status=404)
        index.add(responses.GET, BERLIN, body=PBF)
        out = tmp_path / 'berlin.osm.pbf'
        GeofabrikDownloader().download('berlin', str(out))
        assert out.read_bytes() == PBF
        assert 'skipping verification' in caplog.text


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def slice_downloader(clock=None):
    clock = clock or FakeClock()
    return SliceOsmDownloader(sleep=clock.sleep, clock=clock)


class TestSliceOsm:
    def test_rectangle_is_sent_latitude_first(self):
        assert SliceOsmDownloader.region(rect(-122.41, 37.79, -122.40, 37.795)) == (
            'bbox', [37.79, -122.41, 37.795, -122.40])

    def test_polygon_is_sent_as_geojson(self):
        geometry = {'type': 'Polygon', 'coordinates': [[[0, 0], [2, 0], [1, 2], [0, 0]]]}
        assert SliceOsmDownloader.region(Feature(geometry=geometry)) == ('geojson', geometry)

    @responses.activate
    def test_download_submits_polls_and_fetches(self, tmp_path):
        responses.add(responses.POST, SliceOsmDownloader.API_URL, body=TASK, status=201)
        responses.add(responses.GET, SliceOsmDownloader.API_URL + TASK, json={'Complete': False})
        responses.add(responses.GET, SliceOsmDownloader.API_URL + TASK, json={'Complete': True})
        responses.add(responses.GET, SliceOsmDownloader.FILES_URL + TASK + '.osm.pbf', body=PBF)
        clock = FakeClock()
        out = tmp_path / 'sf.osm.pbf'
        slice_downloader(clock).download('sf', rect(-122.41, 37.79, -122.40, 37.795), str(out))
        assert out.read_bytes() == PBF
        assert json.loads(responses.calls[0].request.body) == {
            'Name': 'sf', 'RegionType': 'bbox', 'RegionData': [37.79, -122.41, 37.795, -122.40]}
        assert responses.calls[0].request.headers['User-Agent'] == user_agent()
        assert clock.sleeps == [2]

    @responses.activate
    def test_polling_backs_off_to_30_seconds(self):
        responses.add(responses.GET, SliceOsmDownloader.API_URL + TASK, json={'Complete': False})
        clock = FakeClock()
        with pytest.raises(ExtractDownloadError, match='24 hours'):
            slice_downloader(clock).wait(TASK, timeout=300)
        assert clock.sleeps[:3] == [2, 3, 4.5]
        assert max(clock.sleeps) == 30
        assert clock.now <= 300

    @responses.activate
    def test_rejected_submission(self):
        responses.add(responses.POST, SliceOsmDownloader.API_URL, body='', status=400)
        with pytest.raises(ExtractDownloadError, match='HTTP 400'):
            slice_downloader().submit('huge', rect(-10, -10, 10, 10))


class TestCli:
    def test_old_syntax_explains_the_change(self, capsys):
        with pytest.raises(SystemExit) as e:
            osm_extract_download.main(['abidjan_ivory-coast'])
        assert e.value.code == 2
        assert 'osm_extract_download interline abidjan_ivory-coast' in capsys.readouterr().err

    def test_interline_names_the_file_after_the_id(self, monkeypatch, tmp_path):
        seen = []
        monkeypatch.setenv('INTERLINE_API_TOKEN', 'from-env')
        monkeypatch.setattr(InterlineExtractDownloader, 'download',
                            lambda self, *a, **kw: seen.append((a, kw)))
        osm_extract_download.main(['interline', 'us-ca', '--outpath=%s' % tmp_path])
        assert seen == [((('us-ca', os.path.join(str(tmp_path), 'us-ca.osm.pbf'))), {'api_token': 'from-env'})]

    def test_existing_output_needs_overwrite(self, tmp_path, capsys):
        (tmp_path / 'us-ca.osm.pbf').write_bytes(b'')
        with pytest.raises(SystemExit) as e:
            osm_extract_download.main(['interline', 'us-ca', '--outpath=%s' % tmp_path])
        assert e.value.code == 1
        assert '--overwrite' in capsys.readouterr().err

    def test_geofabrik_needs_an_id_or_a_search(self, capsys):
        with pytest.raises(SystemExit) as e:
            osm_extract_download.main(['geofabrik'])
        assert e.value.code == 2

    def test_geofabrik_search_prints_ids(self, monkeypatch, capsys):
        monkeypatch.setattr(GeofabrikDownloader, 'search',
                            lambda self, q: [{'id': 'us/california', 'name': 'California'}])
        osm_extract_download.main(['geofabrik', '--search=calif'])
        assert capsys.readouterr().out == 'us/california\tCalifornia\n'

    def test_sliceosm_caps_extents_per_run(self, tmp_path, capsys, monkeypatch):
        csv = tmp_path / 'many.csv'
        csv.write_text(''.join('a%d,0,0,1,1\n' % i for i in range(SliceOsmDownloader.MAX_EXTENTS + 1)))
        monkeypatch.setattr(SliceOsmDownloader, 'download', lambda *a, **kw: pytest.fail('submitted'))
        with pytest.raises(SystemExit) as e:
            osm_extract_download.main(['sliceosm', '--csv=%s' % csv])
        assert e.value.code == 2
        assert 'not permitted' in capsys.readouterr().err

    def test_sliceosm_checks_every_output_before_submitting(self, tmp_path, capsys, monkeypatch):
        csv = tmp_path / 'two.csv'
        csv.write_text('a,0,0,1,1\nb,0,0,1,1\n')
        (tmp_path / 'b.osm.pbf').write_bytes(b'')
        monkeypatch.setattr(SliceOsmDownloader, 'download', lambda *a, **kw: pytest.fail('submitted'))
        with pytest.raises(SystemExit) as e:
            osm_extract_download.main(['sliceosm', '--csv=%s' % csv, '--outpath=%s' % tmp_path])
        assert e.value.code == 1

    def test_sliceosm_ids_select_from_a_file(self, tmp_path, monkeypatch):
        csv = tmp_path / 'two.csv'
        csv.write_text('a,0,0,1,1\nb,0,0,1,1\n')
        seen = []
        monkeypatch.setattr(SliceOsmDownloader, 'download',
                            lambda self, name, feature, outpath, timeout: seen.append(name))
        osm_extract_download.main(['sliceosm', '--csv=%s' % csv, '--ids=b', '--outpath=%s' % tmp_path])
        assert seen == ['b']
