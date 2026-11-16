"""Direct-mode tests: the REAL Pool Liquidity Oracle contract executed
by the GenVM direct engine (gltest).

Run from the pool-liquidity-oracle/ directory with SafeLink's venv
(it already has genlayer-test 0.29.2 + the cached v0.2.16 GenVM
tarball):
    ../../genlayer-intelligent-contracts-submission/safelink/.venv/bin/gltest tests-direct -q

These tests live OUTSIDE tests/ on purpose: plain `pytest` cannot run
them (they need the gltest direct fixtures), and the stub suite in
tests/ cannot run under gltest's direct plugin. See TEST_LOG.md.

Web in gltest direct mode is ALWAYS mocked (unmocked fetches raise
MockNotFoundError — there is no live fallthrough). So every demo uses
REAL DexScreener response bytes, fetched live 16 Nov 2026 by curl and
saved at tests-direct/fixtures/dexscreener-*.json:
* WBNB — 30 pairs, best PancakeSwap $34,643,680.07, LIQUID.
* GOATT — pairs null, NO_POOL.
* Brian Pepe — 1 pair, Uniswap $1.09, THIN.
* Nouny — 1 pair, Uniswap $0.54, THIN (backup demo).
The contract parses genuine DexScreener data under the real engine.
"""

import json
from pathlib import Path

import pytest

# Pin the GenVM release explicitly: the loader's "latest" resolution
# currently points at v0.3.0-rc7, whose genvm-universal.tar.xz asset
# 404s (see SafeLink TEST_LOG.md). v0.2.16 is the release GrantFlow's
# direct tests pinned in Oct 2026.
SDK_VERSION = "v0.2.16"

HERE = Path(__file__).resolve().parent
CONTRACT = str(HERE.parent / "contracts" / "pool_liquidity_oracle.py")
FIXTURES = HERE / "fixtures"

WBNB = "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c"
GOATT = "0x47c9c2e3cdd0855aa18b1cbe1b0e18f0bae32ab0"
BRIANPEPE = "0xe327312b1d3e562614516e391462fbf8d2b3c636"
NOUNY = "0xcaeed5281bd1eeb26d5f8bd550bf5c3727ba6514"
DEAD = "0x0000000000000000000000000000000000000001"

WBNB_BODY = (FIXTURES / "dexscreener-wbnb.json").read_text()
GOATT_BODY = (FIXTURES / "dexscreener-goatt.json").read_text()
BRIANPEPE_BODY = (FIXTURES / "dexscreener-brianpepe.json").read_text()
NOUNY_BODY = (FIXTURES / "dexscreener-nouny.json").read_text()


def _deploy(direct_deploy):
    return direct_deploy(CONTRACT, sdk_version=SDK_VERSION)


def _mock_dex(direct_vm, body):
    direct_vm.mock_web(
        r"api\.dexscreener\.com",
        {"method": "GET", "status": 200, "body": body},
    )


def test_deploy_defaults(direct_deploy, direct_owner):
    oracle = _deploy(direct_deploy)
    stats = oracle.get_stats()
    assert stats["total_entries"] == 0
    assert stats["check_count"] == 0
    assert stats["no_pool"] == 0
    assert stats["thin"] == 0
    assert stats["liquid"] == 0
    assert stats["ttl_checks"] == 1000
    assert stats["admin"].lower() == "0x" + direct_owner.hex()


def test_wbnb_real_body_liquid_and_validator_agrees(
    direct_deploy, direct_vm
):
    oracle = _deploy(direct_deploy)
    _mock_dex(direct_vm, WBNB_BODY)
    result = oracle.check_token(WBNB)
    assert result["verdict"] == "liquid"
    assert result["pair_chain_id"] == "bsc"
    assert result["pair_dex_id"] == "pancakeswap"
    assert (
        result["pair_address"]
        == "0x16b9a82891338f9ba80e2d6970fdda79d1eb0dae"
    )
    assert result["best_liquidity_usd"] == "34643680.07"
    assert result["status_code"] == 200
    assert direct_vm.run_validator() is True
    assert oracle.get_stats()["liquid"] == 1
    assert oracle.is_liquid(WBNB) is True


def test_goatt_real_body_no_pool_and_validator_agrees(
    direct_deploy, direct_vm
):
    oracle = _deploy(direct_deploy)
    _mock_dex(direct_vm, GOATT_BODY)
    result = oracle.check_token(GOATT)
    assert result["verdict"] == "no_pool"
    assert result["pair_address"] == ""
    assert result["liquidity_bucket"] == "none"
    assert direct_vm.run_validator() is True
    assert oracle.get_stats()["no_pool"] == 1
    assert oracle.is_liquid(GOATT) is False


def test_brianpepe_real_body_thin_and_validator_agrees(
    direct_deploy, direct_vm
):
    oracle = _deploy(direct_deploy)
    _mock_dex(direct_vm, BRIANPEPE_BODY)
    result = oracle.check_token(BRIANPEPE)
    assert result["verdict"] == "thin"
    assert result["pair_chain_id"] == "robinhood"
    assert result["pair_dex_id"] == "uniswap"
    assert result["best_liquidity_usd"] == "1.09"
    assert direct_vm.run_validator() is True
    assert oracle.get_stats()["thin"] == 1


def test_nouny_real_body_thin_backup_demo(direct_deploy, direct_vm):
    oracle = _deploy(direct_deploy)
    _mock_dex(direct_vm, NOUNY_BODY)
    result = oracle.check_token(NOUNY)
    assert result["verdict"] == "thin"
    assert result["best_liquidity_usd"] == "0.54"
    assert direct_vm.run_validator() is True


def test_empty_pairs_list_is_no_pool(direct_deploy, direct_vm):
    oracle = _deploy(direct_deploy)
    _mock_dex(
        direct_vm, json.dumps({"schemaVersion": "1.0.0", "pairs": []})
    )
    result = oracle.check_token(GOATT)
    assert result["verdict"] == "no_pool"
    assert direct_vm.run_validator() is True


def test_validator_disagrees_when_body_changes(direct_deploy, direct_vm):
    oracle = _deploy(direct_deploy)
    _mock_dex(direct_vm, WBNB_BODY)
    result = oracle.check_token(WBNB)
    assert result["verdict"] == "liquid"
    # The validator re-fetches and now sees the same token with every
    # pair's liquidity dropped below the threshold — the record still
    # parses, but the signals disagree (bucket + pair identity).
    thin_wbnb = json.loads(WBNB_BODY)
    for pair in thin_wbnb["pairs"]:
        pair["liquidity"]["usd"] = 10
    direct_vm.clear_mocks()
    _mock_dex(direct_vm, json.dumps(thin_wbnb))
    assert direct_vm.run_validator() is False


def test_fetch_failure_writes_nothing(direct_deploy, direct_vm):
    oracle = _deploy(direct_deploy)
    direct_vm.mock_web(
        r"api\.dexscreener\.com",
        {"method": "GET", "status": 404, "body": "not found"},
    )
    with pytest.raises(Exception):
        oracle.check_token(WBNB)
    assert oracle.get_stats()["total_entries"] == 0
    assert oracle.get_stats()["check_count"] == 0


def test_malformed_body_writes_nothing(direct_deploy, direct_vm):
    oracle = _deploy(direct_deploy)
    _mock_dex(direct_vm, "{not json")
    with pytest.raises(Exception):
        oracle.check_token(WBNB)
    assert oracle.get_stats()["total_entries"] == 0
    assert oracle.get_stats()["check_count"] == 0


def test_bad_address_rejected(direct_deploy, direct_vm):
    oracle = _deploy(direct_deploy)
    _mock_dex(direct_vm, WBNB_BODY)
    with pytest.raises(Exception):
        oracle.check_token("not-an-address")
