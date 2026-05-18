"""
Client API TIDAL officielle (OAuth client credentials + recherche catalogue).
"""

from __future__ import annotations

import base64
import json
import os
import time
from typing import Any
from urllib.parse import quote

import requests

from config import (
    TIDAL_API_BASE,
    TIDAL_AUTH_URL,
    TIDAL_CLIENT_ID,
    TIDAL_CLIENT_SECRET,
    TIDAL_COUNTRY_CODE,
    TIDAL_ENABLED,
    TIDAL_TOKEN_CACHE_PATH,
)

_TOKEN: dict[str, Any] = {"access_token": None, "expires_at": 0.0}
_HEADERS = {
    "accept": "application/vnd.tidal.v1+json",
    "Content-Type": "application/vnd.tidal.v1+json",
}


def is_configured() -> bool:
    return bool(TIDAL_ENABLED and TIDAL_CLIENT_ID and TIDAL_CLIENT_SECRET)


def _save_token_cache(token: str, expires_in: int) -> None:
    try:
        payload = {
            "access_token": token,
            "expires_at": time.time() + max(60, int(expires_in) - 120),
        }
        with open(TIDAL_TOKEN_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f)
    except OSError:
        pass


def _load_token_cache() -> str | None:
    if not os.path.isfile(TIDAL_TOKEN_CACHE_PATH):
        return None
    try:
        with open(TIDAL_TOKEN_CACHE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("expires_at", 0) > time.time() and data.get("access_token"):
            return data["access_token"]
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    return None


def get_access_token(force_refresh: bool = False) -> tuple[str | None, str | None]:
    """Token client_credentials. Retourne (token, erreur)."""
    if not is_configured():
        return None, "TIDAL non configure (.env : TIDAL_CLIENT_ID et TIDAL_CLIENT_SECRET)"

    if not force_refresh:
        if _TOKEN.get("access_token") and _TOKEN.get("expires_at", 0) > time.time():
            return _TOKEN["access_token"], None
        cached = _load_token_cache()
        if cached:
            _TOKEN["access_token"] = cached
            _TOKEN["expires_at"] = time.time() + 3600
            return cached, None

    raw = f"{TIDAL_CLIENT_ID}:{TIDAL_CLIENT_SECRET}".encode("utf-8")
    b64 = base64.b64encode(raw).decode("ascii")
    try:
        r = requests.post(
            TIDAL_AUTH_URL,
            headers={"Authorization": f"Basic {b64}"},
            data={"grant_type": "client_credentials"},
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        token = data.get("access_token")
        if not token:
            return None, "Reponse token invalide"
        expires_in = int(data.get("expires_in", 86400))
        _TOKEN["access_token"] = token
        _TOKEN["expires_at"] = time.time() + expires_in - 120
        _save_token_cache(token, expires_in)
        return token, None
    except requests.RequestException as e:
        return None, str(e)


def _api_get(path: str, params: dict | None = None) -> tuple[dict | None, str | None]:
    token, err = get_access_token()
    if err or not token:
        return None, err or "Pas de token"
    url = f"{TIDAL_API_BASE}{path}"
    headers = {**_HEADERS, "Authorization": f"Bearer {token}"}
    try:
        r = requests.get(url, headers=headers, params=params or {}, timeout=20)
        if r.status_code == 401:
            token, err = get_access_token(force_refresh=True)
            if err or not token:
                return None, err
            headers["Authorization"] = f"Bearer {token}"
            r = requests.get(url, headers=headers, params=params or {}, timeout=20)
        r.raise_for_status()
        return r.json(), None
    except requests.RequestException as e:
        body = ""
        if hasattr(e, "response") and e.response is not None:
            try:
                body = e.response.text[:300]
            except Exception:
                pass
        return None, f"{e}" + (f" — {body}" if body else "")


def search_top_hit(query: str) -> tuple[dict | None, str | None]:
    """
    Premier resultat (topHits) pour une requete.
    Retourne dict: id, type, title, artist, url
    """
    q = (query or "").strip()
    if not q:
        return None, "Requete vide"
    path = f"/searchResults/{quote(q, safe='')}"
    params = {"countryCode": TIDAL_COUNTRY_CODE, "include": "topHits,tracks,artists,albums"}
    data, err = _api_get(path, params)
    if err:
        return None, err
    if not data:
        return None, "Reponse vide"

    included = {f"{i.get('type')}:{i.get('id')}": i for i in (data.get("included") or [])}
    rel = (data.get("data") or {}).get("relationships") or {}
    top = (rel.get("topHits") or {}).get("data") or []
    if not top:
        tracks = (rel.get("tracks") or {}).get("data") or []
        top = tracks[:1]
    if not top:
        return None, f"Aucun resultat pour « {q} »"

    hit = top[0]
    hit_type = hit.get("type", "tracks")
    hit_id = hit.get("id")
    item = included.get(f"{hit_type}:{hit_id}")
    if not item:
        item = next((v for v in included.values() if v.get("id") == hit_id), None)
    attrs = (item or {}).get("attributes") or {}
    title = attrs.get("title") or attrs.get("name") or q
    artist = ""
    if hit_type == "tracks":
        artists = attrs.get("artist") or attrs.get("artists")
        if isinstance(artists, dict):
            artist = artists.get("name", "")
        elif isinstance(artists, list) and artists:
            artist = artists[0].get("name", "") if isinstance(artists[0], dict) else str(artists[0])

    url = f"https://listen.tidal.com/{hit_type}/{hit_id}"
    if hit_type == "tracks":
        url = f"https://listen.tidal.com/track/{hit_id}"

    return {
        "id": hit_id,
        "type": hit_type,
        "title": title,
        "artist": artist,
        "url": url,
    }, None


def status() -> dict:
    ok_cfg = is_configured()
    out = {
        "enabled": TIDAL_ENABLED,
        "configured": ok_cfg,
        "client_id_set": bool(TIDAL_CLIENT_ID),
        "secret_set": bool(TIDAL_CLIENT_SECRET),
        "country": TIDAL_COUNTRY_CODE,
    }
    if ok_cfg:
        token, err = get_access_token()
        out["token_ok"] = bool(token)
        out["token_error"] = err
        if token:
            _, api_err = _api_get(
                "/albums/59727856",
                {"countryCode": TIDAL_COUNTRY_CODE},
            )
            out["catalog_api"] = api_err is None
            if api_err:
                out["catalog_hint"] = (
                    "API catalogue en 404 : mode dev Tidal ou scopes manquants. "
                    "Jarvis utilise listen.tidal.com en secours."
                )
    return out
