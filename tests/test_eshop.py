import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ns2_nup_tool.eshop import (OfficialRedirects, automatic_lookup, lookup_product, parse_product, save_artwork,
                              search_config, validate_url)
from tests.fixtures import PNG

URL = "https://www.nintendo.com/us/store/products/example-switch-2/"
ART = "https://assets.nintendo.com/image/upload/f_auto/example"
TITLE = "0400000000001000"


def product_html(application_id=TITLE):
    other = {"name": "Wrong related game", "urlKey": "related-game", "applicationId": "0400000000009999"}
    product = {"name": "Example game", "urlKey": "example-switch-2", "applicationId": application_id,
               "nsuid": "70010000000001", "softwarePublisher": "Example publisher",
               "platform": {"label": "Nintendo Switch 2"},
               'productImage({"shape":"square"})': {"url": ART}, "productImage": {"url": ART + "-wide"}}
    state = {"Product:related": other, "Product:example": product}
    return '<script id="__NEXT_DATA__" type="application/json">' + json.dumps({"props": {"pageProps": {"initialApolloState": state}}}) + '</script>'


class ShopTests(unittest.TestCase):
    def test_automatic_id_match_downloads_confirmed_artwork(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch("ns2_nup_tool.eshop.search_store", return_value={"results": [{"url": URL}]}), \
                patch("ns2_nup_tool.eshop.fetch", side_effect=[product_html().encode(), PNG]):
            result = automatic_lookup({"title_id": TITLE, "cache_dir": directory}, lambda: None, lambda *args: None)
            self.assertTrue(result["matched"])
            self.assertEqual(result["attempted_queries"], [TITLE])
            self.assertEqual(Path(result["product"]["values"]["icon"]).read_bytes(), PNG)

    def test_automatic_title_fallback_still_requires_exact_id(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch("ns2_nup_tool.eshop.search_store", side_effect=[{"results": []}, {"results": [{"url": URL}]}]), \
                patch("ns2_nup_tool.eshop.fetch", side_effect=[product_html().encode(), PNG]):
            result = automatic_lookup({"title_id": TITLE, "query": "Example game", "cache_dir": directory}, lambda: None, lambda *args: None)
        self.assertTrue(result["matched"])
        self.assertEqual(result["attempted_queries"], [TITLE, "Example game"])

    def test_automatic_unconfirmed_product_never_downloads_or_imports(self):
        with patch("ns2_nup_tool.eshop.search_store", return_value={"results": [{"url": URL}]}), \
                patch("ns2_nup_tool.eshop.fetch", return_value=product_html(None).encode()) as fetch:
            result = automatic_lookup({"title_id": TITLE, "cache_dir": "unused"}, lambda: None, lambda *args: None)
        self.assertFalse(result["matched"])
        self.assertNotIn("product", result)
        self.assertEqual(fetch.call_count, 1)

    def test_automatic_offline_and_missing_id_allow_manual_fallback(self):
        with patch("ns2_nup_tool.eshop.search_store", side_effect=ValueError("Offline")) as search:
            result = automatic_lookup({"title_id": "invalid"}, lambda: None, lambda *args: None)
            self.assertFalse(result["matched"])
            search.assert_not_called()
            result = automatic_lookup({"title_id": TITLE}, lambda: None, lambda *args: None)
            self.assertFalse(result["matched"])
            self.assertIn("continue with local metadata", result["message"])

    def test_automatic_changed_candidate_does_not_hide_later_match(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch("ns2_nup_tool.eshop.search_store", return_value={"results": [{"url": URL + "old/"}, {"url": URL}]}), \
                patch("ns2_nup_tool.eshop.lookup_product", side_effect=[ValueError("Changed page"), {"identity": "match"}]):
            result = automatic_lookup({"title_id": TITLE, "cache_dir": directory}, lambda: None, lambda *args: None)
        self.assertTrue(result["matched"])

    def test_product_matches_url_not_first_recommendation_and_prefers_square(self):
        result = parse_product(product_html(), URL)
        self.assertEqual(result["values"], {"name": "Example game", "publisher": "Example publisher", "title_id": TITLE})
        self.assertEqual(result["artwork_url"], ART)
        self.assertTrue(result["square_artwork"])

    def test_missing_application_id_does_not_use_nsuid(self):
        self.assertNotIn("title_id", parse_product(product_html(None), URL)["values"])

    def test_unknown_product_and_changed_page_fail_clearly(self):
        with self.assertRaisesRegex(ValueError, "matching game"):
            parse_product(product_html(), URL.replace("example-switch-2", "different-game"))
        with self.assertRaisesRegex(ValueError, "supported Nintendo"):
            parse_product("<html>Changed page</html>", URL)

    def test_only_official_https_product_urls_and_redirects(self):
        validate_url(URL, product=True)
        for url in ("http://www.nintendo.com/us/store/products/example/", "https://nintendo.com.evil.test/",
                    "https://localhost/", "file:///C:/private", "https://user:pass@www.nintendo.com/",
                    "https://www.nintendo.com:8080/", "https://assets.nintendo.com/image/test"):
            with self.assertRaises(ValueError, msg=url):
                validate_url(url, product=True)
        with self.assertRaises(ValueError):
            OfficialRedirects().redirect_request(None, None, 302, "", {}, "https://evil.test/")

    def test_public_search_config_and_changed_format(self):
        self.assertEqual(search_config('appId:"ABC12345",appKey:"' + 'a' * 32 + '",[P.GAMES]:{indexName:"store_game"}'),
                         ("ABC12345", "a" * 32, "store_game_en_us"))
        with self.assertRaisesRegex(ValueError, "changed"):
            search_config("different site")

    def test_mismatched_id_never_downloads_artwork(self):
        with patch("ns2_nup_tool.eshop.fetch", return_value=product_html().encode()) as fetch:
            result = lookup_product({"url": URL, "title_id": "0400000000009999"}, lambda: None, lambda *args: None)
        self.assertEqual(result["identity"], "mismatch")
        self.assertNotIn("icon", result["values"])
        self.assertEqual(fetch.call_count, 1)

    def test_artwork_cached_outside_dump_with_source_and_no_version_guess(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("ns2_nup_tool.eshop.fetch", side_effect=[product_html().encode(), PNG]):
                result = lookup_product({"url": URL, "title_id": TITLE, "cache_dir": directory}, lambda: None, lambda *args: None)
            icon = Path(result["values"]["icon"])
            self.assertEqual(icon.read_bytes(), PNG)
            self.assertEqual(json.loads(icon.with_suffix(".source.json").read_text())["product_url"], URL)
            self.assertEqual(result["identity"], "match")
            self.assertNotIn("display_version", result["values"])
            with patch("ns2_nup_tool.eshop.fetch", return_value=b"<html>Not an image</html>"):
                with self.assertRaisesRegex(ValueError, "PNG or JPEG"):
                    save_artwork(ART, directory, lambda: None)
