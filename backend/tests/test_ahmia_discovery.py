"""
Tests for Ahmia hidden-service discovery.

Parsing is tested against fixture HTML rather than the live service: Ahmia is
a small volunteer site, the test suite should not hammer it, and a network
failure must not read as a code failure.

The boundary these tests defend is that a search-engine index entry is not
evidence. Ahmia's blurb describes a hidden service; it is not that service's
content, and storing it as an intercept would put text in the evidence table
that was never fetched from the address it is attributed to.
"""

import pytest

from scrapers.dark_web.ahmia_discovery import (
    AhmiaDiscovery, parse_results, ONION_V3_RE, CLEARNET_HOST, ONION_MIRROR,
)

# A syntactically valid v3 address (Ahmia's own), used as a harmless stand-in.
V3 = "juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion"
OTHER_V3 = "duskgytldkxiuqc6hLxqzp3jvcbfvbqhdvbqhdvbqhdvbqhdvbqhdvbq.onion"

RESULTS_HTML = f"""
<ol class="searchResults">
  <li class="result">
    <h4><a href="/search/redirect?search_term=x&amp;redirect_url=http://{V3}/">
      Example Hidden Service</a></h4>
    <p>An indexed description of the service.</p>
    <cite>http://{V3}/</cite>
  </li>
</ol>
"""


class TestParsing:

    def test_extracts_address_title_and_description(self):
        results = parse_results(RESULTS_HTML)
        assert len(results) == 1
        assert results[0]["onion_address"] == V3
        assert results[0]["url"] == f"http://{V3}"
        assert results[0]["title"] == "Example Hidden Service"
        assert "indexed description" in results[0]["description"]

    def test_empty_input_is_handled(self):
        assert parse_results("") == []
        assert parse_results(None) == []

    def test_a_page_with_no_results_yields_nothing(self):
        assert parse_results("<html><body><p>No results found</p></body></html>") == []

    def test_duplicate_addresses_are_collapsed(self):
        doubled = RESULTS_HTML + RESULTS_HTML
        assert len(parse_results(doubled)) == 1

    def test_markup_change_falls_back_to_a_raw_scan(self):
        """
        A silent parser break would look like "the search found nothing",
        which is the failure mode most likely to go unnoticed.
        """
        results = parse_results(f"<div><span>http://{V3}</span></div>")
        assert len(results) == 1
        assert results[0]["onion_address"] == V3
        assert "parser_note" in results[0]

    def test_only_v3_addresses_are_accepted(self):
        """v2 was retired in 2021; anything still advertising one is stale."""
        assert parse_results("<div>http://expyuzz4wqqyqhjn.onion</div>") == []

    def test_address_pattern_rejects_wrong_length(self):
        assert ONION_V3_RE.search("http://tooshort.onion") is None


class TestRouting:

    def test_clearnet_is_used_without_tor(self):
        assert AhmiaDiscovery(use_tor=False).base_url == CLEARNET_HOST

    def test_onion_mirror_is_used_with_tor(self):
        """A blocked clearnet host is reachable through the mirror."""
        assert AhmiaDiscovery(use_tor=True).base_url == ONION_MIRROR

    def test_tor_routing_uses_a_socks_proxy(self):
        kwargs = AhmiaDiscovery(use_tor=True)._client_kwargs()
        assert "proxy" in kwargs
        assert kwargs["proxy"].startswith("socks5h://"), (
            "socks5h keeps DNS inside Tor; socks5 would leak the lookup")

    def test_clearnet_routing_uses_no_proxy(self):
        assert "proxy" not in AhmiaDiscovery(use_tor=False)._client_kwargs()


class TestSearchGuards:

    async def test_an_empty_query_is_refused_before_any_request(self):
        result = await AhmiaDiscovery(use_tor=False).search("   ")
        assert result["status"] == "INVALID"
        assert result["results"] == []

    async def test_an_unreachable_endpoint_reports_an_actionable_hint(self):
        """
        The two failures an operator can act on are different: Tor not
        running, and the clearnet host being blocked by their network.
        """
        discovery = AhmiaDiscovery(use_tor=False)
        discovery.base_url = "http://127.0.0.1:9/blocked"   # discard port
        result = await discovery.search("chitta")
        assert result["status"] == "UNREACHABLE"
        assert result["results"] == []
        assert "nslookup" in result["hint"]


class TestTargetRegistration:

    async def test_discovered_services_become_targets(self, db):
        from sqlalchemy import select
        from database.postgres import Target

        outcome = await AhmiaDiscovery(use_tor=False).register_targets(
            [{"url": f"http://{V3}", "title": "Example Service"}], query="chitta")

        assert outcome["registered_count"] == 1
        rows = (await db.execute(select(Target))).scalars().all()
        assert len(rows) == 1
        assert rows[0].source_type == "DARK_WEB"
        assert rows[0].discovered_by == "AHMIA"

    async def test_index_entries_are_not_stored_as_intelligence(self, db):
        """
        The core boundary. Ahmia's blurb is not the service's content, and
        must not appear in the evidence table attributed to that address.
        """
        from sqlalchemy import select
        from database.postgres import ScrapedData

        await AhmiaDiscovery(use_tor=False).register_targets(
            [{"url": f"http://{V3}", "title": "Example",
              "description": "indexed blurb"}], query="chitta")

        records = (await db.execute(select(ScrapedData))).scalars().all()
        assert records == [], "discovery must not write evidence records"

    async def test_a_known_target_is_not_reactivated(self, db):
        """
        A service that was crawled and then paused must not be silently
        switched back on by a later search that happens to name it.
        """
        from sqlalchemy import select
        from database.postgres import Target

        discovery = AhmiaDiscovery(use_tor=False)
        await discovery.register_targets([{"url": f"http://{V3}", "title": "x"}],
                                         query="chitta")
        target = (await db.execute(select(Target))).scalars().first()
        target.status = "PAUSED"
        await db.commit()

        outcome = await discovery.register_targets(
            [{"url": f"http://{V3}", "title": "x"}], query="chitta")

        assert outcome["registered_count"] == 0
        assert outcome["already_known"] == [f"http://{V3}"]
        refreshed = (await db.execute(select(Target))).scalars().first()
        assert refreshed.status == "PAUSED"


class TestInterceptionIsNotWorkedAround:
    """
    A substituted certificate means the connection is being intercepted. The
    tempting fix - disabling verification - would accept the interception and
    store the filter's block page as though it came from Ahmia.
    """

    async def test_tls_interception_is_named_and_not_bypassed(self, monkeypatch):
        import httpx
        from scrapers.dark_web import ahmia_discovery as module

        class FailingClient:
            def __init__(self, *a, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def get(self, *a, **kw):
                raise httpx.ConnectError(
                    "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify "
                    "failed: self signed certificate")

        monkeypatch.setattr(httpx, "AsyncClient", FailingClient)
        result = await module.AhmiaDiscovery(use_tor=False).search("chitta")

        assert result["status"] == "UNREACHABLE"
        assert "intercepted" in result["hint"]
        assert "Do not disable certificate verification" in result["hint"]

    def test_verification_is_never_switched_off_in_the_client(self):
        """`verify=False` must not appear in the request configuration."""
        for use_tor in (True, False):
            kwargs = AhmiaDiscovery(use_tor=use_tor)._client_kwargs()
            assert kwargs.get("verify", True) is not False


class TestServiceOutageIsNotMisreported:
    """
    Ahmia's search backend sheds load with a gateway error while its front page
    keeps serving - observed on both the onion mirror and the clearnet host at
    once. Reporting that as "unreachable" would send an operator hunting a Tor
    or network fault that does not exist.
    """

    async def _search_returning(self, monkeypatch, status_code, use_tor=False):
        import httpx
        from scrapers.dark_web import ahmia_discovery as module

        attempts = []

        class Response:
            def __init__(self, code): self.status_code = code; self.text = ""

        class Client:
            def __init__(self, *a, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def get(self, url, **kw):
                attempts.append(url)
                return Response(status_code)

        monkeypatch.setattr(httpx, "AsyncClient", Client)
        monkeypatch.setattr(module.asyncio, "sleep", lambda *_: _noop())
        result = await module.AhmiaDiscovery(use_tor=use_tor).search("chitta")
        return result, attempts

    async def test_a_gateway_error_is_reported_as_an_outage(self, monkeypatch):
        result, _ = await self._search_returning(monkeypatch, 504)
        assert result["status"] == "SERVICE_BUSY"
        assert result["status_code"] == 504
        assert "outage on their side" in result["hint"]

    async def test_a_gateway_error_is_retried(self, monkeypatch):
        _, attempts = await self._search_returning(monkeypatch, 504)
        assert len(attempts) > 1, "a 504 must be retried before giving up"

    async def test_tor_routing_also_tries_the_clearnet_host(self, monkeypatch):
        """Over Tor the clearnet name resolves at the exit, dodging local DNS blocks."""
        _, attempts = await self._search_returning(monkeypatch, 504, use_tor=True)
        assert any("ahmia.fi" in url for url in attempts)
        assert any(".onion" in url for url in attempts)

    async def test_a_real_http_error_is_not_called_an_outage(self, monkeypatch):
        result, _ = await self._search_returning(monkeypatch, 404)
        assert result["status"] == "HTTP_ERROR"


async def _noop():
    return None
