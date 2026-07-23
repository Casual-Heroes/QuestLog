"""Public, versioned data bundles for QuestLog desktop clients.

These endpoints contain no account or run state.  They let the desktop app use
the same regulation-derived calculation data and boss registry as the website,
while retaining an atomically cached copy for offline use.
"""

import hashlib
import json
from pathlib import Path

from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET
from django_ratelimit.decorators import ratelimit
from sqlalchemy import text

from app.db import get_db_session
from .soulslike_boss_catalog import supplemental_bosses
from .views_pages import (
    _err_builder_regulation,
    _vanilla_builder_regulation,
)


CATALOG_API_VERSION = 1
CATALOG_SCHEMA_VERSION = 1
CALCULATION_CONTRACT_VERSION = 1
CATALOG_POLL_SECONDS = 6 * 60 * 60
_APP_ROOT = Path(__file__).resolve().parents[1]
_CLIENT_HANDOFF_PATH = _APP_ROOT / 'docs' / 'eldentracker_data_sync_handoff.md'
_REFERENCE_CLIENT_PATH = (
    _APP_ROOT / 'docs' / 'examples' / 'eldentracker_catalog_sync.py'
)


def _canonical_json(payload):
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')


def _boss_dataset(mode):
    with get_db_session() as db:
        rows = db.execute(text(
            "SELECT boss_key, boss_name, location, region, tier "
            "FROM sl_boss_registry "
            "WHERE game='elden_ring' AND game_mode=:mode "
            "ORDER BY sort_order, boss_key"
        ), {'mode': mode}).fetchall()

    bosses = [
        {
            'key': row[0],
            'name': row[1],
            'location': row[2] or '',
            'region': row[3] or '',
            'tier': row[4] or 'enemy',
        }
        for row in rows
    ]
    existing = {boss['key'] for boss in bosses}
    bosses.extend(
        boss for boss in supplemental_bosses('elden_ring', mode)
        if boss['key'] not in existing
    )
    return {
        'schema_version': CATALOG_SCHEMA_VERSION,
        'dataset': f'bosses_{mode}',
        'game': 'elden_ring',
        'mode': mode,
        'bosses': bosses,
    }


def _dataset_payload(dataset):
    if dataset == 'vanilla_calculations':
        regulation = _vanilla_builder_regulation()
        return {
            'schema_version': CATALOG_SCHEMA_VERSION,
            'dataset': dataset,
            'game': 'elden_ring',
            'regulation_sha256': regulation['regulation_sha256'],
            'calculation_contract_version': CALCULATION_CONTRACT_VERSION,
            'payload': regulation,
        }
    if dataset == 'err_calculations':
        regulation = _err_builder_regulation()
        return {
            'schema_version': CATALOG_SCHEMA_VERSION,
            'dataset': dataset,
            'game': 'err',
            'regulation_version': regulation['regulation_version'],
            'calculation_contract_version': CALCULATION_CONTRACT_VERSION,
            'payload': regulation,
        }
    if dataset == 'bosses_err':
        return _boss_dataset('err')
    if dataset == 'bosses_vanilla':
        return _boss_dataset('vanilla')
    return None


def _dataset_artifact(dataset):
    payload = _dataset_payload(dataset)
    if payload is None:
        return None
    content = _canonical_json(payload)
    digest = hashlib.sha256(content).hexdigest()
    return payload, content, digest


def _etag_matches(request, digest):
    requested = request.headers.get('If-None-Match', '')
    return any(
        value.strip().removeprefix('W/').strip('"') == digest
        for value in requested.split(',')
        if value.strip()
    )


def _set_public_headers(response, digest, cache_control):
    response['ETag'] = f'"{digest}"'
    response['Cache-Control'] = cache_control
    response['Access-Control-Allow-Origin'] = '*'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


def _public_error(payload, status):
    response = JsonResponse(payload, status=status)
    response['Cache-Control'] = 'no-store'
    response['Access-Control-Allow-Origin'] = '*'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


def _developer_asset_response(request, path, content_type, filename):
    """Serve a curated developer handoff file with conditional caching."""
    try:
        content = path.read_bytes()
    except OSError:
        return _public_error({'error': 'Developer asset unavailable'}, status=404)
    digest = hashlib.sha256(content).hexdigest()
    if _etag_matches(request, digest):
        return _set_public_headers(
            HttpResponse(status=304), digest,
            'public, max-age=300, must-revalidate',
        )
    response = HttpResponse(content, content_type=content_type)
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return _set_public_headers(
        response, digest, 'public, max-age=300, must-revalidate'
    )


@ratelimit(key='ip', rate='30/m', block=True)
@require_GET
def api_sl_data_handoff(request):
    """Return the human/developer integration guide as plain Markdown."""
    return _developer_asset_response(
        request,
        _CLIENT_HANDOFF_PATH,
        'text/markdown; charset=utf-8',
        'eldentracker_data_sync_handoff.md',
    )


@ratelimit(key='ip', rate='30/m', block=True)
@require_GET
def api_sl_data_reference_client(request):
    """Return reference source for developers; the app never auto-executes it."""
    return _developer_asset_response(
        request,
        _REFERENCE_CLIENT_PATH,
        'text/x-python; charset=utf-8',
        'eldentracker_catalog_sync.py',
    )


@ratelimit(key='ip', rate='60/m', block=True)
@require_GET
def api_sl_data_manifest(request):
    """Return current public dataset revisions and immutable download URLs."""
    datasets = {}
    for dataset in (
        'vanilla_calculations',
        'err_calculations',
        'bosses_err',
        'bosses_vanilla',
    ):
        artifact = _dataset_artifact(dataset)
        if artifact is None:
            continue
        payload, content, digest = artifact
        path = f'/api/soulslike/data/{dataset}/{digest}/'
        datasets[dataset] = {
            'schema_version': payload['schema_version'],
            'revision': digest,
            'sha256': digest,
            'bytes': len(content),
            'url': request.build_absolute_uri(path),
        }
        if payload.get('regulation_version'):
            datasets[dataset]['regulation_version'] = payload['regulation_version']
        if payload.get('regulation_sha256'):
            datasets[dataset]['regulation_sha256'] = payload[
                'regulation_sha256'
            ]

    manifest = {
        'api_version': CATALOG_API_VERSION,
        'schema_version': CATALOG_SCHEMA_VERSION,
        'calculation_contract_version': CALCULATION_CONTRACT_VERSION,
        'account_required': False,
        'poll_after_seconds': CATALOG_POLL_SECONDS,
        'developer_handoff': {
            'documentation_url': request.build_absolute_uri(
                '/api/soulslike/data/handoff/'
            ),
            'reference_client_url': request.build_absolute_uri(
                '/api/soulslike/data/reference-client/'
            ),
            'note': (
                'Developer reference only. Applications must download JSON '
                'datasets and must never auto-execute downloaded code.'
            ),
        },
        'datasets': datasets,
        # These existing public resources are database-backed rather than
        # content-addressed. Clients may refresh only the resources they use,
        # compare their canonical JSON hash locally, and retain the old cache
        # on any network/validation failure.
        'live_resource_poll_seconds': CATALOG_POLL_SECONDS,
        'live_resources': {
            'classes_vanilla': request.build_absolute_uri(
                '/api/soulslike/classes/?game=elden_ring'
            ),
            'weapons_vanilla': request.build_absolute_uri(
                '/api/soulslike/weapons/?game=elden_ring&limit=1000'
            ),
            'armor_vanilla': request.build_absolute_uri(
                '/api/soulslike/armor/?game=elden_ring&limit=1000'
            ),
            'talismans_vanilla': request.build_absolute_uri(
                '/api/soulslike/talismans/?game=elden_ring&limit=1000'
            ),
            'spells_vanilla': request.build_absolute_uri(
                '/api/soulslike/spells/?game=elden_ring&limit=1000'
            ),
            'spirit_ashes_vanilla': request.build_absolute_uri(
                '/api/soulslike/spirit-ashes/?game=elden_ring'
            ),
            'crystal_tears_vanilla': request.build_absolute_uri(
                '/api/soulslike/crystal-tears/?game=elden_ring'
            ),
            'classes_err': request.build_absolute_uri(
                '/api/soulslike/classes/?game=err'
            ),
            'weapons_err': request.build_absolute_uri(
                '/api/soulslike/weapons/?game=err&limit=1000'
            ),
            'armor_err': request.build_absolute_uri(
                '/api/soulslike/armor/?game=err&limit=1000'
            ),
            'talismans_err': request.build_absolute_uri(
                '/api/soulslike/talismans/?game=err&limit=1000'
            ),
            'spells_err': request.build_absolute_uri(
                '/api/soulslike/spells/?game=err&limit=1000'
            ),
            'spirit_ashes_err': request.build_absolute_uri(
                '/api/soulslike/spirit-ashes/?game=err'
            ),
            'crystal_tears_err': request.build_absolute_uri(
                '/api/soulslike/crystal-tears/?game=err'
            ),
            'affinities_err': request.build_absolute_uri(
                '/api/soulslike/err/affinities/'
            ),
            'fortunes_err': request.build_absolute_uri(
                '/api/soulslike/err/fortunes/'
            ),
            'curios_err': request.build_absolute_uri(
                '/api/soulslike/err/curios/'
            ),
            'runeforging_err': request.build_absolute_uri(
                '/api/soulslike/err/runeforging/'
            ),
            'aow_skills_err': request.build_absolute_uri(
                '/api/soulslike/err/aow-skills/'
            ),
            'enkindling_err': request.build_absolute_uri(
                '/api/soulslike/err/enkindling/'
            ),
        },
    }
    content = _canonical_json(manifest)
    digest = hashlib.sha256(content).hexdigest()
    if _etag_matches(request, digest):
        return _set_public_headers(
            HttpResponse(status=304), digest, 'public, max-age=300, must-revalidate'
        )
    response = HttpResponse(content, content_type='application/json; charset=utf-8')
    return _set_public_headers(
        response, digest, 'public, max-age=300, must-revalidate'
    )


@ratelimit(key='ip', rate='20/m', block=True)
@require_GET
def api_sl_data_download(request, dataset, revision):
    """Serve a content-addressed dataset; stale/unknown revisions return 404."""
    artifact = _dataset_artifact(dataset)
    if artifact is None:
        return _public_error({'error': 'Unknown dataset'}, status=404)
    _, content, digest = artifact
    if revision != digest:
        return _public_error({
            'error': 'Dataset revision is no longer current',
            'manifest_url': request.build_absolute_uri(
                '/api/soulslike/data/manifest/'
            ),
        }, status=404)
    if _etag_matches(request, digest):
        return _set_public_headers(
            HttpResponse(status=304), digest,
            'public, max-age=31536000, immutable'
        )
    response = HttpResponse(content, content_type='application/json; charset=utf-8')
    return _set_public_headers(
        response, digest, 'public, max-age=31536000, immutable'
    )
