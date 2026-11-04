"""Optional Nintendo US store search and metadata; no game files are uploaded.

Search uses the same public, search-only configuration published by Nintendo's
webpage. Website data can change, so product URLs also work without search.
"""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

STORE = "https://www.nintendo.com"
SEARCH_URL = STORE + "/us/search/"
MAX_RESPONSE = 8 * 1024 * 1024


def validate_url(url, *, product=False, search_host=None):
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or "").lower()
    official = host in ("nintendo.com", "www.nintendo.com", "assets.nintendo.com")
    official = official or host.endswith(".cdn.nintendo.net")
    if (parsed.scheme != "https" or parsed.username or parsed.password
            or parsed.port not in (None, 443) or not (official or host == search_host)):
        raise ValueError("Use an HTTPS Nintendo US product page URL.")
    if product and (host not in ("nintendo.com", "www.nintendo.com")
                    or not re.fullmatch(r"/us/store/products/[a-z0-9-]+/?", parsed.path)):
        raise ValueError("Paste a Nintendo US product URL, such as nintendo.com/us/store/products/game-name/.")
    return url


class OfficialRedirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, search_host=None):
        super().__init__()
        self.search_host = search_host

    def redirect_request(self, request, fp, code, message, headers, newurl):
        validate_url(newurl, search_host=self.search_host)
        return super().redirect_request(request, fp, code, message, headers, newurl)


def fetch(url, check, *, body=None, headers=None, search_host=None):
    validate_url(url, search_host=search_host)
    request = urllib.request.Request(url, data=body, headers={
        "User-Agent": "NS2-NUP-Tool/0.2 (Nintendo store metadata lookup)",
        "Accept": "text/html,application/json,image/png,image/jpeg,*/*;q=0.5",
        **(headers or {}),
    })
    check()
    try:
        with urllib.request.build_opener(OfficialRedirects(search_host)).open(request, timeout=15) as response:
            content = bytearray()
            while True:
                check()
                chunk = response.read(64 * 1024)
                if not chunk:
                    return bytes(content)
                content.extend(chunk)
                if len(content) > MAX_RESPONSE:
                    raise ValueError("Nintendo returned a response larger than the lookup limit.")
    except (urllib.error.URLError, TimeoutError) as error:
        raise ValueError(f"Nintendo lookup could not connect: {error}. Try again or paste a product URL.") from error


class StorePage(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.scripts = []
        self.next_data = ""
        self._in_next = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "script":
            if attributes.get("src"):
                self.scripts.append(attributes["src"])
            self._in_next = attributes.get("id") == "__NEXT_DATA__"

    def handle_endtag(self, tag):
        if tag == "script":
            self._in_next = False

    def handle_data(self, data):
        if self._in_next:
            self.next_data += data


def search_config(script):
    credentials = re.search(r'appId:"([A-Z0-9]{6,20})",appKey:"([a-f0-9]{32})"', script)
    index = re.search(r'\[\w+\.GAMES\]:\{indexName:"([a-z_]+)"', script)
    if not credentials or not index:
        raise ValueError("Nintendo's search page has changed. Paste a product URL to look it up directly.")
    return (*credentials.groups(), index[1] + "_en_us")


def search_store(request, check, report):
    query = request.get("query", "").strip()
    if not query or len(query) > 160:
        raise ValueError("Enter a game name (up to 160 characters).")
    report(0, 0, "Reading Nintendo's public search page…")
    page = StorePage(fetch(SEARCH_URL, check).decode("utf-8"))
    script_url = next((url for url in page.scripts if "/pages/_app-" in url), None)
    if not script_url:
        raise ValueError("Nintendo's search page has changed. Paste a product URL instead.")
    app_id, search_key, index = search_config(fetch(urllib.parse.urljoin(STORE, script_url), check).decode("utf-8"))
    host = f"{app_id.lower()}-dsn.algolia.net"
    params = urllib.parse.urlencode({"query": query, "hitsPerPage": 12, "analytics": "false",
                                    "clickAnalytics": "false", "attributesToHighlight": "[]"})
    body = json.dumps({"requests": [{"indexName": index, "params": params}]}).encode()
    report(0, 0, "Searching Nintendo US games…")
    data = json.loads(fetch(f"https://{host}/1/indexes/*/queries", check, body=body, search_host=host,
                           headers={"Content-Type": "application/json", "X-Algolia-Application-Id": app_id,
                                    "X-Algolia-API-Key": search_key}))
    results, seen = [], set()
    for hit in data.get("results", [{}])[0].get("hits", []):
        url = urllib.parse.urljoin(STORE, hit.get("url", ""))
        try:
            validate_url(url, product=True)
        except ValueError:
            continue
        if url not in seen and hit.get("title"):
            results.append({"name": str(hit["title"]), "platform": str(hit.get("platform", "")), "url": url})
            seen.add(url)
    return {"results": results}


def parse_product(html, url):
    validate_url(url, product=True)
    slug = urllib.parse.urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
    try:
        state = json.loads(StorePage(html).next_data)["props"]["pageProps"]["initialApolloState"]
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError("This page does not contain supported Nintendo product metadata.") from error
    # Related products are in the same state. Only the requested URL is eligible.
    product = next((value for key, value in state.items() if key.startswith("Product:")
                    and isinstance(value, dict) and value.get("urlKey") == slug), None)
    if not product or not product.get("name"):
        raise ValueError("No matching game was found in this Nintendo product page.")
    values = {"name": product["name"]}
    if product.get("softwarePublisher"):
        values["publisher"] = product["softwarePublisher"]
    title_id = str(product.get("applicationId") or "").upper()
    if re.fullmatch(r"[0-9A-F]{16}", title_id) and int(title_id, 16):
        values["title_id"] = title_id
    square = product.get('productImage({"shape":"square"})') or {}
    artwork = square.get("url") or (product.get("productImage") or {}).get("url", "")
    platform = product.get("platform") or {}
    return {"values": values, "url": url, "artwork_url": artwork, "square_artwork": bool(square.get("url")),
            "platform": platform.get("label", ""), "notices": []}


def save_artwork(url, cache_dir, check):
    # Force a broadly supported format; the site's f_auto may return AVIF/WebP.
    validate_url(url)
    download_url = url.replace("/f_auto/", "/f_png/")
    content = fetch(download_url, check)
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        extension = ".png"
    elif content.startswith(b"\xff\xd8\xff"):
        extension = ".jpg"
    else:
        raise ValueError("The store artwork was not a PNG or JPEG image.")
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    output = cache / (hashlib.sha256(content).hexdigest() + extension)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=cache, delete=False, suffix=".download") as file:
            temporary = Path(file.name)
            file.write(content)
        check()
        temporary.replace(output)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
    return str(output)


def lookup_product(request, check, report):
    url = validate_url(request.get("url", ""), product=True)
    report(0, 0, "Reading Nintendo product metadata…")
    result = parse_product(fetch(url, check).decode("utf-8"), url)
    expected = request.get("title_id", "").upper()
    found = result["values"].get("title_id", "")
    result["identity"] = "match" if expected and found and expected == found else (
        "mismatch" if expected and found else "unconfirmed")
    if result["identity"] == "mismatch":
        result["notices"].append(f"Different application ID: dump {expected}; store {found}. Import is disabled.")
        return result
    if request.get("require_match") and result["identity"] != "match":
        return result
    if result["artwork_url"]:
        report(0, 0, "Downloading Nintendo artwork…")
        try:
            icon = save_artwork(result["artwork_url"], request["cache_dir"], check)
            result["values"]["icon"] = icon
            Path(icon).with_suffix(".source.json").write_text(json.dumps({
                "product_url": url, "artwork_url": result["artwork_url"],
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
            }, indent=2), encoding="utf-8")
        except (OSError, ValueError) as error:
            result["notices"].append(f"Artwork unavailable: {error}")
    result["notices"].append("Version uses the newest included update number (or V0); executable build ID comes from the dump.")
    return result


def automatic_lookup(request, check, report):
    """Import candidates only after their product page confirms the exact ID."""
    expected = request.get("title_id", "").strip().upper()
    if not re.fullmatch(r"[0-9A-F]{16}", expected) or int(expected, 16) == 0:
        return {"matched": False, "message": "No title ID detected. Search Nintendo eShop by game title to choose a match."}
    queries = [expected]
    suggestion = request.get("query", "").strip()[:160]
    if suggestion and suggestion.upper() != expected:
        queries.append(suggestion)
    candidates, seen, attempted = [], set(), []
    try:
        for query in queries:
            check()
            attempted.append(query)
            report(0, 0, f"Automatic Nintendo lookup · {query}")
            results = search_store({"query": query}, check, report)["results"]
            for candidate in results:
                if candidate["url"] in seen:
                    continue
                if len(seen) >= 8:
                    break
                seen.add(candidate["url"])
                candidates.append(candidate)
                try:
                    product = lookup_product({"url": candidate["url"], "title_id": expected,
                        "cache_dir": request["cache_dir"], "require_match": True}, check, report)
                except (OSError, ValueError):
                    # A removed or changed product must not hide a later exact match.
                    continue
                if product["identity"] == "match":
                    return {"matched": True, "product": product, "attempted_queries": attempted,
                            "message": "Exact title ID found on Nintendo eShop."}
    except (OSError, ValueError) as error:
        return {"matched": False, "attempted_queries": attempted, "candidates": candidates,
                "message": f"Automatic Nintendo lookup unavailable: {error}. You can search manually or continue with local metadata."}
    return {"matched": False, "attempted_queries": attempted, "candidates": candidates,
            "message": "No exact Nintendo title-ID match found. Search by game title and select the correct product."}
