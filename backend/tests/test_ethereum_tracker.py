"""
Ethereum wallet lookups.

The defect this covers returned zeros when no RPC endpoint was configured:

    {"balance_eth": 0.0, "nonce_or_tx_count": 0}

Nothing had been asked of any blockchain. An investigator reading that
concludes the wallet is empty and drops the line of enquiry, when the address
may hold a substantial balance nobody looked for. "Not checked" and "checked,
holds nothing" are opposite findings and must never render identically.

The network is never touched here: a node being slow or rate-limited must not
turn into a failing test, and the logic under test is the reporting, not the
chain.
"""

import pytest

from blockchain.ethereum_tracker import EthereumTracker

REAL_ADDRESS = "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe"


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _client_returning(results, calls=None):
    """An httpx.AsyncClient stand-in; `results` maps method name to hex value."""

    class Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, **kw):
            if calls is not None:
                calls.append(url)
            method = json["method"]
            value = results[method]
            if isinstance(value, Exception):
                raise value
            return _Response({"jsonrpc": "2.0", "id": 1, "result": value})

    return Client


class TestAddressValidation:

    @pytest.mark.parametrize("address", [
        "0xnope", "", "de0B295669a9FD93d5F28D9Ec85E40f4cb697BAe",
        "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BA",     # one short
        "0xZZ0B295669a9FD93d5F28D9Ec85E40f4cb697BAe",    # not hex
    ])
    def test_malformed_addresses_are_rejected(self, address):
        assert EthereumTracker.is_valid_address(address) is False

    def test_a_well_formed_address_is_accepted(self):
        assert EthereumTracker.is_valid_address(REAL_ADDRESS) is True

    async def test_a_malformed_address_reports_no_balance(self):
        result = await EthereumTracker().get_address_overview("0xnope")
        assert result["valid"] is False
        assert result["checked"] is False
        assert "balance_eth" not in result, (
            "a figure must never appear for an address that was not queried")


class TestSuccessfulLookup:

    async def test_balance_and_nonce_are_reported(self, monkeypatch):
        import httpx

        monkeypatch.setattr(httpx, "AsyncClient", _client_returning({
            # 2 ETH, 5 outgoing transactions.
            "eth_getBalance": hex(2 * 10 ** 18),
            "eth_getTransactionCount": hex(5),
        }))

        result = await EthereumTracker().get_address_overview(REAL_ADDRESS)

        assert result["checked"] is True
        assert result["balance_eth"] == 2.0
        assert result["balance_wei"] == 2 * 10 ** 18
        assert result["nonce_or_tx_count"] == 5
        assert result["has_outgoing_activity"] is True

    async def test_a_never_used_address_is_distinguished_from_a_spender(
            self, monkeypatch):
        """
        A nonce of zero means the address has never sent anything - a deposit
        address that only receives. That is a different finding from an empty
        wallet, and both are different again from "not checked".
        """
        import httpx

        monkeypatch.setattr(httpx, "AsyncClient", _client_returning({
            "eth_getBalance": hex(57 * 10 ** 18),
            "eth_getTransactionCount": hex(0),
        }))

        result = await EthereumTracker().get_address_overview(REAL_ADDRESS)

        assert result["checked"] is True
        assert result["balance_eth"] == 57.0
        assert result["has_outgoing_activity"] is False

    async def test_a_genuinely_empty_wallet_reports_zero(self, monkeypatch):
        """Zero is a legitimate answer - when it was actually measured."""
        import httpx

        monkeypatch.setattr(httpx, "AsyncClient", _client_returning({
            "eth_getBalance": "0x0",
            "eth_getTransactionCount": "0x0",
        }))

        result = await EthereumTracker().get_address_overview(REAL_ADDRESS)

        assert result["checked"] is True
        assert result["balance_eth"] == 0.0


class TestUnreachableNodeNeverFabricates:
    """The original defect, in the case that produced it."""

    async def test_no_balance_is_reported_when_no_node_answers(self, monkeypatch):
        import httpx

        monkeypatch.setattr(httpx, "AsyncClient", _client_returning({
            "eth_getBalance": RuntimeError("node down"),
            "eth_getTransactionCount": RuntimeError("node down"),
        }))

        result = await EthereumTracker().get_address_overview(REAL_ADDRESS)

        assert result["checked"] is False
        assert "balance_eth" not in result
        assert "nonce_or_tx_count" not in result
        assert result["valid"] is True, (
            "the address is well-formed; it was the lookup that failed")
        assert result["error"]

    async def test_the_failure_says_what_to_do_about_it(self, monkeypatch):
        import httpx

        monkeypatch.setattr(httpx, "AsyncClient", _client_returning({
            "eth_getBalance": RuntimeError("rate limited"),
            "eth_getTransactionCount": RuntimeError("rate limited"),
        }))

        result = await EthereumTracker().get_address_overview(REAL_ADDRESS)
        assert "ETH_PROVIDER_URL" in result["remedy"]

    async def test_every_endpoint_tried_is_recorded(self, monkeypatch):
        import httpx

        monkeypatch.setattr(httpx, "AsyncClient", _client_returning({
            "eth_getBalance": RuntimeError("node down"),
            "eth_getTransactionCount": RuntimeError("node down"),
        }))

        tracker = EthereumTracker()
        result = await tracker.get_address_overview(REAL_ADDRESS)

        assert len(result["attempts"]) == len(tracker.endpoints)


class TestEndpointFallback:
    """
    A single default endpoint is a single point of failure. cloudflare-eth.com
    was the obvious choice until Cloudflare retired it, after which it answered
    every request with an internal error.
    """

    async def test_a_failing_endpoint_falls_through_to_the_next(self, monkeypatch):
        import httpx

        calls = []
        attempts = {"n": 0}

        class Client:
            def __init__(self, *a, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, json=None, **kw):
                calls.append(url)
                # The first endpoint fails; the second answers.
                if url == tracker.endpoints[0]:
                    attempts["n"] += 1
                    raise RuntimeError("Internal error")
                value = ("0x" + format(3 * 10 ** 18, "x")
                         if json["method"] == "eth_getBalance" else "0x1")
                return _Response({"result": value})

        tracker = EthereumTracker()
        monkeypatch.setattr(httpx, "AsyncClient", Client)

        result = await tracker.get_address_overview(REAL_ADDRESS)

        assert result["checked"] is True
        assert result["balance_eth"] == 3.0
        assert tracker.endpoints[1] in calls

    def test_a_configured_provider_replaces_the_public_list(self, monkeypatch):
        from config import settings

        monkeypatch.setattr(settings, "ETH_PROVIDER_URL",
                            "https://mainnet.infura.io/v3/key")
        tracker = EthereumTracker()

        assert tracker.endpoints == ["https://mainnet.infura.io/v3/key"]
        assert tracker.using_fallback is False
