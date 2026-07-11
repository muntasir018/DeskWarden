"""
DeskWarden - core/website_link.py

"""

import json
import urllib.request
import urllib.error


WEBSITE_LINK_URL = "https://deskwarden-update-proxy.mdmuntasir017.workers.dev/website-link"

FALLBACK_WEBSITE_URL = "https://deskwarden.netlify.app/"


def get_website_url(timeout: int = 5) -> str:
    
    try:
        req = urllib.request.Request(
            WEBSITE_LINK_URL,
            headers={
                "User-Agent": "DeskWarden-app",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
        url = (data.get("url") or "").strip()
        return url or FALLBACK_WEBSITE_URL
    except Exception:
        return FALLBACK_WEBSITE_URL
