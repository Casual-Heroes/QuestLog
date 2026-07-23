import hashlib
import importlib.util
import json
import logging
import sys
import tempfile
from pathlib import Path
from unittest import TestCase


_MODULE_PATH = (
    Path(__file__).parent / 'docs' / 'examples' /
    'eldentracker_catalog_sync.py'
)
_SPEC = importlib.util.spec_from_file_location(
    'eldentracker_catalog_sync_reference', _MODULE_PATH
)
sync = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = sync
_SPEC.loader.exec_module(sync)


def _canonical(payload):
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')
    ).encode('utf-8')


class _FakeStore(sync.CatalogStore):
    def __init__(self, cache_dir, bundled_dir, manifest, dataset_body):
        super().__init__(
            'https://questlog.example', cache_dir, bundled_dir, '1.2.3',
            logging.getLogger(__name__),
        )
        self.manifest = manifest
        self.dataset_body = dataset_body

    def _request(self, url, etag=None):
        if url.endswith('/manifest/'):
            return 200, _canonical(self.manifest), '"manifest-etag"'
        return 200, self.dataset_body, None


class EldenTrackerCatalogSyncReferenceTests(TestCase):
    def _fixtures(self, body):
        digest = hashlib.sha256(body).hexdigest()
        manifest = {
            'api_version': 1,
            'schema_version': 1,
            'calculation_contract_version': 1,
            'account_required': False,
            'poll_after_seconds': 21600,
            'datasets': {
                'bosses_err': {
                    'schema_version': 1,
                    'revision': digest,
                    'sha256': digest,
                    'bytes': len(body),
                    'url': (
                        'https://questlog.example/api/soulslike/data/'
                        f'bosses_err/{digest}/'
                    ),
                },
            },
        }
        return manifest

    def test_verified_dataset_is_installed_and_loaded(self):
        body = _canonical({
            'schema_version': 1,
            'dataset': 'bosses_err',
            'bosses': [{'key': 'test'}],
        })
        with tempfile.TemporaryDirectory() as cache, tempfile.TemporaryDirectory() as bundled:
            store = _FakeStore(cache, bundled, self._fixtures(body), body)
            result = store.refresh()

            self.assertEqual(result.updated, ['bosses_err'])
            self.assertFalse(result.offline)
            self.assertEqual(store.load('bosses_err')['bosses'][0]['key'], 'test')

    def test_bad_hash_preserves_existing_verified_cache(self):
        old_payload = {
            'schema_version': 1,
            'dataset': 'bosses_err',
            'bosses': [{'key': 'old'}],
        }
        advertised = _canonical({
            'schema_version': 1,
            'dataset': 'bosses_err',
            'bosses': [{'key': 'new'}],
        })
        corrupted = advertised + b' '
        with tempfile.TemporaryDirectory() as cache, tempfile.TemporaryDirectory() as bundled:
            destination = Path(cache) / 'datasets' / 'bosses_err.json'
            destination.parent.mkdir(parents=True)
            destination.write_bytes(_canonical(old_payload))
            store = _FakeStore(
                cache, bundled, self._fixtures(advertised), corrupted
            )
            result = store.refresh()

            self.assertEqual(result.updated, [])
            self.assertTrue(result.warnings)
            self.assertEqual(store.load('bosses_err')['bosses'][0]['key'], 'old')

    def test_newer_calculation_contract_retains_old_calculations(self):
        body = _canonical({
            'schema_version': 1,
            'dataset': 'err_calculations',
            'payload': {'regulation_version': 'new'},
        })
        manifest = self._fixtures(body)
        metadata = manifest['datasets'].pop('bosses_err')
        manifest['datasets']['err_calculations'] = metadata
        manifest['calculation_contract_version'] = 2
        with tempfile.TemporaryDirectory() as cache, tempfile.TemporaryDirectory() as bundled:
            store = _FakeStore(cache, bundled, manifest, body)
            result = store.refresh()

            self.assertTrue(result.app_update_required)
            self.assertEqual(result.updated, [])
            self.assertFalse(
                (Path(cache) / 'datasets' / 'err_calculations.json').exists()
            )
