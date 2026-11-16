"""Live GenVM test on glsim: deploy the Pool Liquidity Oracle to a local
5-validator GenLayer network and run real consensus checks against the
LIVE DexScreener API (no mocks anywhere).

Run with SafeLink's venv, while glsim is up on :4000 (FRESH server —
one deploy per glsim server process, see Oracle TEST_LOG 15 Nov; and
with SANITIZED no_proxy — the sandbox no_proxy breaks httpx, see
Token Safety TEST_LOG 16 Nov):
    no_proxy='localhost,127.0.0.1,198.19.0.1,198.19.0.2' NO_PROXY='localhost,127.0.0.1,198.19.0.1,198.19.0.2' ../../genlayer-intelligent-contracts-submission/safelink/.venv/bin/glsim --port 4000 --no-browser
    no_proxy='localhost,127.0.0.1,198.19.0.1,198.19.0.2' NO_PROXY='localhost,127.0.0.1,198.19.0.1,198.19.0.2' ../../genlayer-intelligent-contracts-submission/safelink/.venv/bin/python scripts/glsim_live_test.py

Writes results to scripts/glsim_live_result.json (timings included).
Each consensus round makes the leader AND every validator fetch the
DexScreener record independently.
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(
    0,
    str(ROOT.parent.parent / "genlayer-intelligent-contracts-submission" / "safelink" / ".venv" / "lib" / "python3.12" / "site-packages"),
)

from genlayer_py import create_account, create_client
from genlayer_py.chains import localnet
from genlayer_py.types import TransactionStatus
from gltest.utils import extract_contract_address

CONTRACT_PATH = ROOT / "contracts" / "pool_liquidity_oracle.py"

# Pinned demo tokens (all live-verified by curl 16 Nov 2026; fixtures in
# tests-direct/fixtures/). THIN demos re-verified live by Muse just
# before this run: Brian Pepe $1.09, Nouny $0.54.
WBNB = "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c"            # LIQUID
GOATT = "0x47c9c2e3cdd0855aa18b1cbe1b0e18f0bae32ab0"          # NO_POOL
BRIANPEPE = "0xe327312b1d3e562614516e391462fbf8d2b3c636"      # THIN ($1.09)
NOUNY = "0xcaeed5281bd1eeb26d5f8bd550bf5c3727ba6514"          # THIN ($0.54, backup)

RESULTS = {"checks": []}


def record(name, ok, detail, seconds=None):
    RESULTS["checks"].append(
        {"name": name, "ok": bool(ok), "detail": detail, "seconds": seconds}
    )
    print(f"[{'PASS' if ok else 'FAIL'}] {name} ({seconds}s)" if seconds is not None else f"[{'PASS' if ok else 'FAIL'}] {name}")
    print(f"    {detail}")


def wait(client, tx_hash, label):
    receipt = client.wait_for_transaction_receipt(
        transaction_hash=tx_hash,
        status=TransactionStatus.ACCEPTED,
        interval=2,
        retries=120,
        full_transaction=True,
    )
    print(f"    {label} receipt status: {receipt.get('status')} ({receipt.get('status_name')})")
    return receipt


def extract_address(receipt):
    for path in (
        ("tx_data_decoded", "contract_address"),
        ("data", "contract_address"),
    ):
        node = receipt.get(path[0]) or {}
        if isinstance(node, dict) and node.get(path[1]):
            return node[path[1]]
    if receipt.get("contract_address"):
        return receipt["contract_address"]
    return None


def main():
    admin = create_account()
    print(f"admin: {admin.address}")
    client = create_client(chain=localnet, account=admin)
    try:
        client.fund_account(admin.address, 10**21)
    except Exception as exc:
        # genlayer-py 0.16.3 mis-parses the sim_fundAccount reply
        # (expects a tx hash, gets {"balance": ...}) — the funding
        # itself lands server-side; continue.
        print(f"fund_account parse quirk (ignored): {exc}")
    print("funded admin")

    code = CONTRACT_PATH.read_text()
    t0 = time.time()
    tx_hash = client.deploy_contract(code=code, account=admin)
    receipt = wait(client, tx_hash, "deploy")
    address = extract_address(receipt)
    if not address:
        raise SystemExit(f"deploy receipt has no contract address: {json.dumps(receipt, default=str)[:1500]}")
    RESULTS["contract_address"] = address
    print(f"deployed at {address} in {time.time() - t0:.1f}s")

    def write(fn, *args):
        t0 = time.time()
        tx = client.write_contract(
            address=address, function_name=fn, account=admin, args=list(args)
        )
        wait(client, tx, fn)
        return time.time() - t0

    def read(fn, *args):
        return client.read_contract(
            address=address, function_name=fn, account=admin, args=list(args)
        )

    # --- deploy defaults ---
    stats = read("get_stats")
    record(
        "deploy_defaults",
        stats.get("check_count") == 0 and stats.get("total_entries") == 0,
        f"stats={stats}",
    )

    # --- WBNB live: LIQUID ---
    dt = write("check_token", WBNB)
    got = read("get_verdict", WBNB)
    record(
        "wbnb_live_liquid",
        got.get("verdict") == "liquid",
        f"verdict={got.get('verdict')} bucket={got.get('liquidity_bucket')} pair={got.get('pair_address')}",
        round(dt, 1),
    )

    # --- GOATT live: NO_POOL ---
    dt = write("check_token", GOATT)
    got = read("get_verdict", GOATT)
    record(
        "goatt_live_no_pool",
        got.get("verdict") == "no_pool",
        f"verdict={got.get('verdict')} bucket={got.get('liquidity_bucket')}",
        round(dt, 1),
    )

    # --- Brian Pepe live: THIN ---
    dt = write("check_token", BRIANPEPE)
    got = read("get_verdict", BRIANPEPE)
    record(
        "brianpepe_live_thin",
        got.get("verdict") == "thin",
        f"verdict={got.get('verdict')} bucket={got.get('liquidity_bucket')} pair={got.get('pair_address')} usd_obs={got.get('best_liquidity_usd')}",
        round(dt, 1),
    )

    # --- Nouny live: THIN (backup) ---
    dt = write("check_token", NOUNY)
    got = read("get_verdict", NOUNY)
    record(
        "nouny_live_thin",
        got.get("verdict") == "thin",
        f"verdict={got.get('verdict')} bucket={got.get('liquidity_bucket')} usd_obs={got.get('best_liquidity_usd')}",
        round(dt, 1),
    )

    stats = read("get_stats")
    RESULTS["stats"] = stats
    print(f"stats: {stats}")

    out = ROOT / "scripts" / "glsim_live_result.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(RESULTS, indent=2))
    print(f"results -> {out}")
    failed = [c for c in RESULTS["checks"] if not c["ok"]]
    print(f"{len(RESULTS['checks']) - len(failed)}/{len(RESULTS['checks'])} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
