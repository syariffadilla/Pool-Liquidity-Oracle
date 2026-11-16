"""Test harness: a minimal fake ``genlayer`` module.

Adapted from the Token Safety Oracle's tests/conftest.py (same stub
semantics), GET-only — the Pool Liquidity Oracle fetches DexScreener
with GET and nothing else. The real GenLayer SDK / GenVM runner is NOT
installed here, so the contract is loaded with this stub. The stub
emulates the documented semantics just enough to exercise the contract
end to end off-chain:

* ``@gl.public.view`` / ``@gl.public.write`` are identity decorators.
* ``gl.message.sender_address`` is a settable attribute (the caller).
* ``gl.nondet.web.get(url)`` serves canned responses from
  ``WEB_RESPONSES`` and records every call in ``WEB_CALLS``.
* ``gl.vm.run_nondet_unsafe(leader_fn, validator_fn)`` calls the leader,
  wraps the result in ``gl.vm.Return``, calls the validator, and returns
  the leader's value only if the validator agrees. Disagreement (or a
  leader error the validator does not agree with) raises RuntimeError —
  the stub's emulation of "transaction undetermined, no state change".
* ``TreeMap`` / ``DynArray`` are dict / list subclasses; ``u64`` etc.
  are plain ``int``; ``Address`` is ``str``.

These are DIRECT-mode tests: they prove the contract's logic, state
machine and validator agreement — they do NOT prove the contract passes
GenVM lint or Studio consensus. That step is still open; see README.md.
"""

import importlib.util
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_DIR = ROOT / "contracts"
FIXTURES_DIR = ROOT / "tests-direct" / "fixtures"
sys.path.insert(0, str(CONTRACTS_DIR))

import pool_liquidity_logic  # noqa: E402  (pure logic, no GenLayer import)

# ---------------------------------------------------------------- fake gl

WEB_RESPONSES = {}
WEB_CALLS = []


class _FakeResponse:
    def __init__(self, status, body):
        # Mirrors the real SDK Response dataclass: fields are `status`
        # (not `status_code`) and `body` (bytes).
        self.status = status
        self.body = body.encode("utf-8") if isinstance(body, str) else body


def _serve(store, calls, key):
    calls.append(key)
    if key not in store:
        return _FakeResponse(404, "not found")
    value = store[key]
    if isinstance(value, list):
        # Consumed in order: lets tests change the source between the
        # leader's fetch and the validator's re-fetch.
        status_code, body = value.pop(0)
    else:
        status_code, body = value
    return _FakeResponse(status_code, body)


class _FakeWeb:
    @staticmethod
    def get(url):
        return _serve(WEB_RESPONSES, WEB_CALLS, url)


class _UserError(Exception):
    pass


class _VMError(Exception):
    pass


class _Return:
    def __init__(self, calldata):
        self.calldata = calldata


class _LeaderError:
    """Non-Return result: the leader raised instead of returning."""

    def __init__(self, error):
        self.error = error


def _run_nondet_unsafe(leader_fn, validator_fn):
    try:
        value = leader_fn()
    except Exception as exc:  # leader raised (e.g. UserError on 404)
        agreed = validator_fn(_LeaderError(exc))
        if agreed:
            raise exc
        raise RuntimeError("consensus failed: leader error not agreed")
    if validator_fn(_Return(value)):
        return value
    raise RuntimeError("consensus failed: validator disagreed")


def _make_fake_genlayer():
    fake = types.ModuleType("genlayer")

    class _TreeMap(dict):
        def __class_getitem__(cls, item):
            return cls

    class _DynArray(list):
        def __class_getitem__(cls, item):
            return cls

    def _storage_default(annotation):
        if annotation is _TreeMap:
            return {}
        if annotation is _DynArray:
            return []
        if annotation is int:
            return 0
        if annotation is bool:
            return False
        if annotation is str:
            return ""
        return None

    class _ContractBase:
        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__(**kwargs)
            orig_init = cls.__init__

            def wrapped_init(self, *args, **kwargs):
                for name, ann in cls.__annotations__.items():
                    setattr(self, name, _storage_default(ann))
                orig_init(self, *args, **kwargs)

            cls.__init__ = wrapped_init

    class _Public:
        @staticmethod
        def view(fn):
            return fn

        @staticmethod
        def write(fn):
            return fn

    class _Message:
        sender_address = "0x00000000000000000000000000000000000000A1"

    fake.public = _Public()
    fake.message = _Message()
    fake.UserError = _UserError
    fake.VMError = _VMError
    fake.allow_storage = lambda cls: cls
    fake.Contract = _ContractBase
    fake.Address = str
    fake.TreeMap = _TreeMap
    fake.DynArray = _DynArray
    fake.u64 = int
    fake.u256 = int
    fake.u32 = int
    fake.i32 = int
    fake.i64 = int
    fake.vm = types.SimpleNamespace(
        Return=_Return,
        Result=_Return,
        UserError=_UserError,
        VMError=_VMError,
        run_nondet_unsafe=_run_nondet_unsafe,
    )
    fake.nondet = types.SimpleNamespace(web=_FakeWeb())
    fake.gl = fake
    fake.__all__ = [
        "gl",
        "allow_storage",
        "Contract",
        "public",
        "message",
        "UserError",
        "VMError",
        "Address",
        "TreeMap",
        "DynArray",
        "u64",
        "u256",
        "u32",
        "i32",
        "i64",
        "vm",
        "nondet",
    ]
    return fake


def load_contract():
    """Load contracts/pool_liquidity_oracle.py with the fake genlayer module."""
    fake = _make_fake_genlayer()
    # The contract imports UserError from the REAL SDK location
    # (genlayer.gl.vm) — the fake must expose that submodule path too.
    # NOTE (15 Nov 2026, found on the Oracle): real SDK v0.2.5/v0.2.16
    # has NO gl.UserError; it lives in genlayer.gl.vm. The fake
    # mirrors that, and the contract imports it from there.
    gl_mod = types.ModuleType("genlayer.gl")
    vm_mod = types.ModuleType("genlayer.gl.vm")
    vm_mod.UserError = _UserError
    vm_mod.VMError = _VMError
    vm_mod.Return = _Return
    vm_mod.run_nondet_unsafe = _run_nondet_unsafe
    gl_mod.vm = vm_mod
    fake.__path__ = []  # make the fake importable as a package
    sys.modules["genlayer"] = fake
    sys.modules["genlayer.gl"] = gl_mod
    sys.modules["genlayer.gl.vm"] = vm_mod
    spec = importlib.util.spec_from_file_location(
        "pool_liquidity_contract",
        CONTRACTS_DIR / "pool_liquidity_oracle.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, fake


def reset_web():
    WEB_RESPONSES.clear()
    WEB_CALLS.clear()


def set_sender(fake, address):
    fake.message.sender_address = address


ADMIN = "0x00000000000000000000000000000000000000A1"
OTHER = "0x00000000000000000000000000000000000000B2"

# Live-verified demo data (16 Nov 2026, DexScreener fetched live by
# curl; full bodies saved at tests-direct/fixtures/).
WBNB = "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c"
GOATT = "0x47c9c2e3cdd0855aa18b1cbe1b0e18f0bae32ab0"
# Brian Pepe on Robinhood Chain — THIN demo, best pair $1.09 (verified
# twice, stable). Brand-new token; re-verify live before Studio deploy.
BRIANPEPE = "0xe327312b1d3e562614516e391462fbf8d2b3c636"
# Nouny on Robinhood Chain — backup THIN demo, best pair $0.54.
NOUNY = "0xcaeed5281bd1eeb26d5f8bd550bf5c3727ba6514"
DEAD = "0x0000000000000000000000000000000000000001"
DEX_URL = "https://api.dexscreener.com/latest/dex/tokens/{address}"


def dex_url(address):
    return DEX_URL.format(address=address)


def _dex_body(pairs):
    return json.dumps({"schemaVersion": "1.0.0", "pairs": pairs})


def _pair(chain_id, dex_id, pair_address, usd=None, omit_liquidity=False):
    pair = {
        "chainId": chain_id,
        "dexId": dex_id,
        "pairAddress": pair_address,
    }
    if not omit_liquidity:
        pair["liquidity"] = {"usd": usd}
    return pair


def wbnb_json():
    """WBNB — 30 pairs, best PancakeSwap $34,643,680.07, LIQUID.

    Real DexScreener body, fetched live 16 Nov 2026.
    """
    return (FIXTURES_DIR / "dexscreener-wbnb.json").read_text()


def goatt_json():
    """GOATT — pairs null, NO_POOL. Real body, fetched live 16 Nov 2026."""
    return (FIXTURES_DIR / "dexscreener-goatt.json").read_text()


def brianpepe_json():
    """Brian Pepe — 1 pair, Uniswap $1.09, THIN.

    Real body, fetched live 16 Nov 2026.
    """
    return (FIXTURES_DIR / "dexscreener-brianpepe.json").read_text()


def nouny_json():
    """Nouny — 1 pair, Uniswap $0.54, THIN (backup demo).

    Real body, fetched live 16 Nov 2026.
    """
    return (FIXTURES_DIR / "dexscreener-nouny.json").read_text()


def empty_pairs_json():
    """pairs: [] — parses fine, NO_POOL."""
    return _dex_body([])


def null_pairs_json():
    """pairs: null — parses fine, NO_POOL."""
    return _dex_body(None)


def missing_pairs_json():
    """No 'pairs' key at all — malformed, writes nothing."""
    return json.dumps({"schemaVersion": "1.0.0"})
