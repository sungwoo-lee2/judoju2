from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any

import requests

BASE = Path(__file__).resolve().parent
DATA = BASE / 'data'
LOCAL = DATA / 'history_v7.json'
ROW_ID = os.getenv('SUPABASE_STATE_ID', 'leader_finder_v8')
TABLE = os.getenv('SUPABASE_STATE_TABLE', 'leader_finder_state')


def _cfg():
    url = (os.getenv('SUPABASE_URL') or '').rstrip('/')
    key = os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_KEY') or ''
    return url, key


def storage_status():
    url, key = _cfg()
    return {
        'mode': 'supabase' if (url and key) else 'local',
        'configured': bool(url and key),
        'table': TABLE if (url and key) else None,
        'state_id': ROW_ID,
    }


def _headers(key: str):
    return {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
    }


def load_state(default: dict[str, Any]) -> dict[str, Any]:
    url, key = _cfg()
    if url and key:
        try:
            r = requests.get(
                f'{url}/rest/v1/{TABLE}',
                headers=_headers(key),
                params={'select': 'payload', 'id': f'eq.{ROW_ID}', 'limit': '1'},
                timeout=8,
            )
            r.raise_for_status()
            rows = r.json()
            if rows and isinstance(rows[0].get('payload'), dict):
                return rows[0]['payload']
        except Exception:
            # Never make the scanner unavailable because persistence is unavailable.
            pass
    try:
        if LOCAL.exists():
            data = json.loads(LOCAL.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return default


def save_state(state: dict[str, Any]) -> str:
    DATA.mkdir(exist_ok=True)
    # Always keep a local copy as an emergency fallback/cache.
    LOCAL.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')

    url, key = _cfg()
    if not (url and key):
        return 'local'
    try:
        headers = _headers(key)
        headers['Prefer'] = 'resolution=merge-duplicates,return=minimal'
        r = requests.post(
            f'{url}/rest/v1/{TABLE}',
            headers=headers,
            params={'on_conflict': 'id'},
            json={'id': ROW_ID, 'payload': state},
            timeout=10,
        )
        r.raise_for_status()
        return 'supabase'
    except Exception:
        return 'local'
