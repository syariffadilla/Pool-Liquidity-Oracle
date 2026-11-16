"""Sync guard: the pure functions in contracts/pool_liquidity_oracle.py
must stay byte-identical (AST-identical) to
contracts/pool_liquidity_logic.py.

The contract is self-contained because a single-file GenLayer contract
cannot import a sibling module on-chain, so the logic is duplicated.
If this test fails, copy the changed function from
pool_liquidity_logic.py into pool_liquidity_oracle.py (or vice versa)
and re-run.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGIC = ROOT / "contracts" / "pool_liquidity_logic.py"
CONTRACT = ROOT / "contracts" / "pool_liquidity_oracle.py"

PURE_FUNCTIONS = [
    "normalize_token_address",
    "render_source_url",
    "_parse_usd",
    "_usd_str",
    "_best_pair",
    "derive_signals",
    "verdict_from_signals",
]


def _functions(path):
    tree = ast.parse(path.read_text())
    return {
        node.name: ast.dump(node)
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }


def test_pure_functions_in_sync():
    logic_fns = _functions(LOGIC)
    contract_fns = _functions(CONTRACT)
    for name in PURE_FUNCTIONS:
        assert name in logic_fns, f"{name} missing from pool_liquidity_logic.py"
        assert (
            name in contract_fns
        ), f"{name} missing from pool_liquidity_oracle.py"
        assert logic_fns[name] == contract_fns[name], (
            f"{name} drifted between pool_liquidity_logic.py and "
            "pool_liquidity_oracle.py — copy the change across and re-run"
        )


def test_contract_header_pins_stable_runner():
    first_line = CONTRACT.read_text().splitlines()[0]
    assert first_line == (
        '# { "Depends": "py-genlayer:'
        "1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6"
        '" }'
    )
    assert "py-genlayer:test" not in CONTRACT.read_text()
    assert "py-genlayer:latest" not in CONTRACT.read_text()


def test_no_llm_calls_in_contract():
    text = CONTRACT.read_text()
    assert "exec_prompt" not in text
    assert "nondet.llm" not in text


def test_no_bare_gl_user_error():
    # 15 Nov 2026 (Oracle): gl.UserError does not exist in SDK
    # v0.2.5/v0.2.16 — it lives in genlayer.gl.vm only. The contract
    # must import UserError from there, never use gl.UserError.
    text = CONTRACT.read_text()
    assert "gl.UserError" not in text
    assert "from genlayer.gl.vm import UserError" in text


def test_no_raw_liquidity_float_in_consensus():
    # The raw liquidity.usd number must never be a compared field:
    # only the bucket + pair identity are compared. Parse the
    # COMPARED_SIGNAL_KEYS tuple from the contract and check its
    # exact contents.
    tree = ast.parse(CONTRACT.read_text())
    compared = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "COMPARED_SIGNAL_KEYS"
            for t in node.targets
        ):
            compared = [
                elt.value
                for elt in node.value.elts
                if isinstance(elt, ast.Constant)
            ]
    assert compared is not None, "COMPARED_SIGNAL_KEYS not found"
    assert compared == [
        "token_address",
        "pair_chain_id",
        "pair_dex_id",
        "pair_address",
        "liquidity_bucket",
        "status_code",
        "source_url",
    ]
    assert "best_liquidity_usd" not in compared
