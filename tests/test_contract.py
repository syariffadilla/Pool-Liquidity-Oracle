"""Contract end-to-end tests with the fake genlayer stub (conftest.py)."""

import json

import pytest

from conftest import (
    ADMIN,
    BRIANPEPE,
    DEAD,
    GOATT,
    NOUNY,
    OTHER,
    WEB_CALLS,
    WEB_RESPONSES,
    WBNB,
    _dex_body,
    _pair,
    brianpepe_json,
    dex_url,
    empty_pairs_json,
    goatt_json,
    load_contract,
    missing_pairs_json,
    nouny_json,
    reset_web,
    set_sender,
    wbnb_json,
)


@pytest.fixture
def oracle():
    reset_web()
    module, fake = load_contract()
    contract = module.PoolLiquidityOracle()
    set_sender(fake, ADMIN)
    return contract, fake


def _seed(address, body):
    WEB_RESPONSES[dex_url(address)] = (200, body)


# -- admin ------------------------------------------------------------------


def test_deploy_defaults(oracle):
    contract, _ = oracle
    stats = contract.get_stats()
    assert stats["total_entries"] == 0
    assert stats["check_count"] == 0
    assert stats["no_pool"] == 0
    assert stats["thin"] == 0
    assert stats["liquid"] == 0
    assert stats["ttl_checks"] == 1000


def test_admin_guards(oracle):
    contract, fake = oracle
    set_sender(fake, OTHER)
    with pytest.raises(fake.UserError):
        contract.set_ttl_checks(10)


def test_set_ttl_checks(oracle):
    contract, _ = oracle
    assert contract.set_ttl_checks(5) == {"ttl_checks": 5}
    with pytest.raises(Exception):
        contract.set_ttl_checks(0)


# -- checking: LIQUID -------------------------------------------------------


def test_check_wbnb_liquid(oracle):
    contract, _ = oracle
    _seed(WBNB, wbnb_json())
    result = contract.check_token(WBNB)
    assert result["verdict"] == "liquid"
    assert result["pair_chain_id"] == "bsc"
    assert result["pair_dex_id"] == "pancakeswap"
    assert (
        result["pair_address"]
        == "0x16b9a82891338f9ba80e2d6970fdda79d1eb0dae"
    )
    assert result["best_liquidity_usd"] == "34643680.07"
    assert result["cached"] is False
    assert dex_url(WBNB) in WEB_CALLS
    assert contract.is_liquid(WBNB) is True


def test_check_uppercase_address_normalized(oracle):
    contract, _ = oracle
    _seed(WBNB, wbnb_json())
    result = contract.check_token(WBNB.upper())
    assert result["token_address"] == WBNB
    assert result["verdict"] == "liquid"


def test_check_bad_address_rejected(oracle):
    contract, _ = oracle
    with pytest.raises(Exception):
        contract.check_token("not-an-address")


# -- checking: NO_POOL / THIN -----------------------------------------------


def test_check_goatt_no_pool(oracle):
    contract, _ = oracle
    _seed(GOATT, goatt_json())
    result = contract.check_token(GOATT)
    assert result["verdict"] == "no_pool"
    assert result["pair_address"] == ""
    assert result["liquidity_bucket"] == "none"
    assert contract.is_liquid(GOATT) is False


def test_check_empty_pairs_list_is_no_pool(oracle):
    contract, _ = oracle
    _seed(GOATT, empty_pairs_json())
    result = contract.check_token(GOATT)
    assert result["verdict"] == "no_pool"
    assert contract.get_stats()["no_pool"] == 1


def test_check_brianpepe_thin(oracle):
    contract, _ = oracle
    _seed(BRIANPEPE, brianpepe_json())
    result = contract.check_token(BRIANPEPE)
    assert result["verdict"] == "thin"
    assert result["pair_chain_id"] == "robinhood"
    assert result["pair_dex_id"] == "uniswap"
    assert result["best_liquidity_usd"] == "1.09"
    assert contract.is_liquid(BRIANPEPE) is False


def test_check_nouny_thin_backup_demo(oracle):
    contract, _ = oracle
    _seed(NOUNY, nouny_json())
    result = contract.check_token(NOUNY)
    assert result["verdict"] == "thin"
    assert result["best_liquidity_usd"] == "0.54"


# -- caching, disputes, failures --------------------------------------------


def test_fresh_entry_is_cached_no_refetch(oracle):
    contract, _ = oracle
    _seed(WBNB, wbnb_json())
    contract.check_token(WBNB)
    calls_before = len(WEB_CALLS)
    result = contract.check_token(WBNB)
    assert result["cached"] is True
    assert len(WEB_CALLS) == calls_before


def test_dispute_forces_recheck(oracle):
    contract, _ = oracle
    _seed(WBNB, wbnb_json())
    contract.check_token(WBNB)
    disputed = contract.dispute_token(WBNB, "wrong verdict?")
    assert disputed["disputed"] is True
    assert disputed["disputes"] == 1
    calls_before = len(WEB_CALLS)
    result = contract.check_token(WBNB)
    assert result["cached"] is False
    assert len(WEB_CALLS) > calls_before


def test_request_recheck_marks_disputed(oracle):
    contract, _ = oracle
    _seed(WBNB, wbnb_json())
    contract.check_token(WBNB)
    result = contract.request_recheck(WBNB)
    assert result["disputed"] is True
    assert result["last_dispute_reason"] == "recheck requested"


def test_dispute_unknown_check_rejected(oracle):
    contract, _ = oracle
    with pytest.raises(Exception):
        contract.dispute_token(WBNB, "nothing here")


def test_fetch_404_writes_nothing(oracle):
    contract, _ = oracle
    WEB_RESPONSES[dex_url(WBNB)] = (404, "not found")
    with pytest.raises(Exception):
        contract.check_token(WBNB)
    assert contract.get_stats()["check_count"] == 0
    assert contract.get_verdict(WBNB)["verdict"] == "unchecked"


def test_unparseable_body_writes_nothing(oracle):
    contract, _ = oracle
    _seed(WBNB, "{not json")
    with pytest.raises(Exception):
        contract.check_token(WBNB)
    assert contract.get_stats()["check_count"] == 0


def test_missing_pairs_key_writes_nothing(oracle):
    contract, _ = oracle
    _seed(WBNB, missing_pairs_json())
    with pytest.raises(Exception):
        contract.check_token(WBNB)
    assert contract.get_stats()["check_count"] == 0


def test_validator_disagreement_writes_nothing(oracle):
    contract, _ = oracle
    # Leader sees the LIQUID WBNB record; the validator's re-fetch
    # sees the same token with the best pair's liquidity dropped below
    # the threshold — the record still parses, but the signals
    # disagree (bucket + pair identity), so nothing is written.
    thin_wbnb = json.loads(wbnb_json())
    for pair in thin_wbnb["pairs"]:
        pair["liquidity"]["usd"] = 10
    WEB_RESPONSES[dex_url(WBNB)] = [
        (200, wbnb_json()),
        (200, json.dumps(thin_wbnb)),
    ]
    with pytest.raises(RuntimeError):
        contract.check_token(WBNB)
    assert contract.get_stats()["check_count"] == 0
    assert contract.get_verdict(WBNB)["verdict"] == "unchecked"


def test_ttl_expiry_forces_recheck(oracle):
    contract, _ = oracle
    contract.set_ttl_checks(1)
    _seed(WBNB, wbnb_json())
    _seed(GOATT, goatt_json())
    contract.check_token(WBNB)
    contract.check_token(GOATT)
    # WBNB was checked at seq 1; check_count is now 2, so 2 - 1 = 1
    # is not < ttl 1: the entry is stale and re-checks.
    calls_before = len(WEB_CALLS)
    result = contract.check_token(WBNB)
    assert result["cached"] is False
    assert len(WEB_CALLS) > calls_before


# -- views / stats ----------------------------------------------------------


def test_stats_counters_and_list_entries(oracle):
    contract, _ = oracle
    _seed(WBNB, wbnb_json())
    _seed(GOATT, goatt_json())
    _seed(BRIANPEPE, brianpepe_json())
    assert contract.is_liquid(WBNB) is False
    contract.check_token(WBNB)
    contract.check_token(GOATT)
    contract.check_token(BRIANPEPE)
    assert contract.is_liquid(WBNB) is True
    stats = contract.get_stats()
    assert stats["liquid"] == 1
    assert stats["no_pool"] == 1
    assert stats["thin"] == 1
    assert stats["check_count"] == 3
    entries = contract.list_entries(0, 10)
    assert entries["total"] == 3
    # Newest first.
    assert entries["entries"][0]["token_address"] == BRIANPEPE
    assert entries["entries"][2]["token_address"] == WBNB


def test_recheck_updates_counters(oracle):
    contract, _ = oracle
    _seed(WBNB, wbnb_json())
    contract.check_token(WBNB)
    assert contract.get_stats()["liquid"] == 1
    contract.dispute_token(WBNB, "recheck")
    # The validator now sees the same token with all pairs thin.
    thin_wbnb = json.loads(wbnb_json())
    for pair in thin_wbnb["pairs"]:
        pair["liquidity"]["usd"] = 10
    WEB_RESPONSES[dex_url(WBNB)] = (200, json.dumps(thin_wbnb))
    result = contract.check_token(WBNB)
    assert result["verdict"] == "thin"
    stats = contract.get_stats()
    assert stats["liquid"] == 0
    assert stats["thin"] == 1
    assert stats["check_count"] == 2


def test_get_verdict_unknown_is_unchecked(oracle):
    contract, _ = oracle
    view = contract.get_verdict(DEAD)
    assert view["verdict"] == "unchecked"
    assert contract.is_liquid(DEAD) is False
