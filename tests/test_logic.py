"""Pure-logic tests: no GenLayer stub needed, plain pytest."""

import json

import pytest

from pool_liquidity_logic import (
    _best_pair,
    _parse_usd,
    _usd_str,
    derive_signals,
    normalize_token_address,
    render_source_url,
    verdict_from_signals,
)
from conftest import (
    BRIANPEPE,
    DEAD,
    GOATT,
    NOUNY,
    WBNB,
    _dex_body,
    _pair,
    brianpepe_json,
    dex_url,
    empty_pairs_json,
    goatt_json,
    missing_pairs_json,
    nouny_json,
    null_pairs_json,
    wbnb_json,
)


# -- normalize_token_address ----------------------------------------------


def test_normalize_token_address_lowercases_and_accepts():
    assert (
        normalize_token_address("0xBB4CDB9CBD36B01BD1CBAEBF2DE08D9173BC095C")
        == WBNB
    )


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "0x123",
        "bb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c",
        "0x" + "zz" * 20,
        "0x" + "ab" * 19,
        "0x" + "ab" * 21,
        123,
    ],
)
def test_normalize_token_address_rejects(bad):
    with pytest.raises(ValueError):
        normalize_token_address(bad)


# -- render_source_url ------------------------------------------------------


def test_render_source_url():
    assert render_source_url(WBNB) == (
        "https://api.dexscreener.com/latest/dex/tokens/" + WBNB
    )
    assert render_source_url(GOATT.upper()) == (
        "https://api.dexscreener.com/latest/dex/tokens/" + GOATT
    )


def test_render_source_url_rejects_bad_address():
    with pytest.raises(ValueError):
        render_source_url("not-an-address")


# -- _parse_usd / _usd_str --------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        (1000, 1000.0),
        (0.54, 0.54),
        (0, 0.0),
        ("500", 500.0),
        ("1.09", 1.09),
        (None, None),
        ("", None),
        ("abc", None),
        (True, None),
        (False, None),
    ],
)
def test_parse_usd(raw, expected):
    assert _parse_usd(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        (34643680.07, "34643680.07"),
        (1000, "1000"),
        (1.09, "1.09"),
        (None, ""),
        ("500", "500"),
        (True, ""),
    ],
)
def test_usd_str(raw, expected):
    assert _usd_str(raw) == expected


# -- _best_pair -------------------------------------------------------------


def test_best_pair_picks_highest_liquidity():
    pairs = [
        _pair("bsc", "pancakeswap", "0x" + "aa" * 20, 100),
        _pair("bsc", "pancakeswap", "0x" + "bb" * 20, 5000),
        _pair("bsc", "pancakeswap", "0x" + "cc" * 20, 250),
    ]
    best, usd = _best_pair(pairs)
    assert best["pairAddress"] == "0x" + "bb" * 20
    assert usd == 5000.0


def test_best_pair_missing_liquidity_counts_as_zero():
    pairs = [
        _pair("bsc", "pancakeswap", "0x" + "aa" * 20, omit_liquidity=True),
        _pair("bsc", "pancakeswap", "0x" + "bb" * 20, None),
    ]
    best, usd = _best_pair(pairs)
    assert usd == 0.0
    # First pair wins the tie at 0.
    assert best["pairAddress"] == "0x" + "aa" * 20


def test_best_pair_skips_non_dict_entries():
    best, usd = _best_pair(["not-a-pair", 42, None])
    assert best is None
    assert usd == 0.0


# -- derive_signals: real fixtures ------------------------------------------


def test_derive_wbnb_real_body_liquid():
    signals = derive_signals(
        WBNB, dex_url(WBNB), 200, wbnb_json()
    )
    assert signals["parse_ok"] is True
    assert signals["liquidity_bucket"] == "liquid"
    assert signals["pair_chain_id"] == "bsc"
    assert signals["pair_dex_id"] == "pancakeswap"
    assert (
        signals["pair_address"]
        == "0x16b9a82891338f9ba80e2d6970fdda79d1eb0dae"
    )
    assert signals["best_liquidity_usd"] == "34643680.07"
    assert signals["status_code"] == "200"
    assert verdict_from_signals(signals) == "liquid"


def test_derive_goatt_real_body_no_pool():
    signals = derive_signals(GOATT, dex_url(GOATT), 200, goatt_json())
    assert signals["parse_ok"] is True
    assert signals["liquidity_bucket"] == "none"
    assert signals["pair_chain_id"] == ""
    assert signals["pair_dex_id"] == ""
    assert signals["pair_address"] == ""
    assert signals["best_liquidity_usd"] == ""
    assert verdict_from_signals(signals) == "no_pool"


def test_derive_brianpepe_real_body_thin():
    signals = derive_signals(
        BRIANPEPE, dex_url(BRIANPEPE), 200, brianpepe_json()
    )
    assert signals["parse_ok"] is True
    assert signals["liquidity_bucket"] == "thin"
    assert signals["pair_chain_id"] == "robinhood"
    assert signals["pair_dex_id"] == "uniswap"
    assert (
        signals["pair_address"]
        == "0xb989dbdd6df5ec86b80659e19483cd5362dd8394"
    )
    assert signals["best_liquidity_usd"] == "1.09"
    assert verdict_from_signals(signals) == "thin"


def test_derive_nouny_real_body_thin():
    signals = derive_signals(NOUNY, dex_url(NOUNY), 200, nouny_json())
    assert signals["parse_ok"] is True
    assert signals["liquidity_bucket"] == "thin"
    assert signals["best_liquidity_usd"] == "0.54"
    assert verdict_from_signals(signals) == "thin"


# -- derive_signals: synthetic shapes ---------------------------------------


def test_derive_empty_pairs_list_is_no_pool():
    signals = derive_signals(
        GOATT, dex_url(GOATT), 200, empty_pairs_json()
    )
    assert signals["parse_ok"] is True
    assert verdict_from_signals(signals) == "no_pool"


def test_derive_null_pairs_is_no_pool():
    signals = derive_signals(
        GOATT, dex_url(GOATT), 200, null_pairs_json()
    )
    assert signals["parse_ok"] is True
    assert verdict_from_signals(signals) == "no_pool"


@pytest.mark.parametrize("usd,expected", [(1000, "liquid"), (999.99, "thin")])
def test_derive_threshold_boundary(usd, expected):
    body = _dex_body([_pair("bsc", "pancakeswap", "0x" + "aa" * 20, usd)])
    signals = derive_signals(WBNB, dex_url(WBNB), 200, body)
    assert signals["parse_ok"] is True
    assert signals["liquidity_bucket"] == expected
    assert verdict_from_signals(signals) == expected


def test_derive_missing_liquidity_is_thin_not_liquid():
    body = _dex_body(
        [_pair("bsc", "pancakeswap", "0x" + "aa" * 20, omit_liquidity=True)]
    )
    signals = derive_signals(WBNB, dex_url(WBNB), 200, body)
    assert signals["parse_ok"] is True
    assert signals["liquidity_bucket"] == "thin"
    assert signals["best_liquidity_usd"] == ""
    assert verdict_from_signals(signals) == "thin"


def test_derive_string_liquidity_parses():
    body = _dex_body(
        [_pair("bsc", "pancakeswap", "0x" + "aa" * 20, "2500")]
    )
    signals = derive_signals(WBNB, dex_url(WBNB), 200, body)
    assert signals["liquidity_bucket"] == "liquid"
    assert signals["best_liquidity_usd"] == "2500"


def test_derive_best_pair_wins_over_first_pair():
    body = _dex_body(
        [
            _pair("bsc", "pancakeswap", "0x" + "aa" * 20, 50),
            _pair("ethereum", "uniswap", "0x" + "bb" * 20, 50000),
        ]
    )
    signals = derive_signals(WBNB, dex_url(WBNB), 200, body)
    assert signals["pair_chain_id"] == "ethereum"
    assert signals["pair_dex_id"] == "uniswap"
    assert signals["pair_address"] == "0x" + "bb" * 20
    assert signals["best_liquidity_usd"] == "50000"
    assert verdict_from_signals(signals) == "liquid"


def test_derive_pair_address_lowercased():
    body = _dex_body(
        [_pair("bsc", "pancakeswap", "0x" + "AA" * 20, 100)]
    )
    signals = derive_signals(WBNB, dex_url(WBNB), 200, body)
    assert signals["pair_address"] == "0x" + "aa" * 20


# -- derive_signals: failures write nothing ---------------------------------


def test_derive_non_200_writes_nothing():
    signals = derive_signals(WBNB, dex_url(WBNB), 404, "not found")
    assert signals["parse_ok"] is False
    assert verdict_from_signals(signals) == "unchecked"


def test_derive_malformed_json_writes_nothing():
    signals = derive_signals(WBNB, dex_url(WBNB), 200, "{not json")
    assert signals["parse_ok"] is False
    assert verdict_from_signals(signals) == "unchecked"


def test_derive_non_dict_body_writes_nothing():
    signals = derive_signals(WBNB, dex_url(WBNB), 200, "[1, 2, 3]")
    assert signals["parse_ok"] is False
    assert verdict_from_signals(signals) == "unchecked"


def test_derive_missing_pairs_key_writes_nothing():
    signals = derive_signals(
        WBNB, dex_url(WBNB), 200, missing_pairs_json()
    )
    assert signals["parse_ok"] is False
    assert verdict_from_signals(signals) == "unchecked"


def test_derive_pairs_not_a_list_writes_nothing():
    body = json.dumps({"schemaVersion": "1.0.0", "pairs": "nope"})
    signals = derive_signals(WBNB, dex_url(WBNB), 200, body)
    assert signals["parse_ok"] is False
    assert verdict_from_signals(signals) == "unchecked"


def test_derive_all_non_dict_pairs_is_no_pool():
    body = _dex_body(["junk", 42])
    signals = derive_signals(WBNB, dex_url(WBNB), 200, body)
    assert signals["parse_ok"] is True
    assert verdict_from_signals(signals) == "no_pool"


# -- verdict_from_signals ---------------------------------------------------


def test_verdict_from_signals_buckets():
    base = {
        "token_address": WBNB,
        "pair_chain_id": "bsc",
        "pair_dex_id": "pancakeswap",
        "pair_address": "0x" + "aa" * 20,
        "liquidity_bucket": "thin",
        "status_code": "200",
        "source_url": dex_url(WBNB),
        "parse_ok": True,
    }
    assert verdict_from_signals({**base, "liquidity_bucket": "none"}) == "no_pool"
    assert verdict_from_signals({**base, "liquidity_bucket": "thin"}) == "thin"
    assert verdict_from_signals({**base, "liquidity_bucket": "liquid"}) == "liquid"
    assert verdict_from_signals({**base, "parse_ok": False}) == "unchecked"


def test_derive_dead_address_body_is_no_pool_when_pairs_null():
    # A token with no pairs at all parses to NO_POOL, even for the
    # dead address shape (pairs null). Contrast: a fetch failure
    # (non-200 / unparseable) writes nothing.
    signals = derive_signals(DEAD, dex_url(DEAD), 200, null_pairs_json())
    assert signals["parse_ok"] is True
    assert verdict_from_signals(signals) == "no_pool"
