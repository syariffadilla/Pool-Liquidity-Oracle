# Pool Liquidity Oracle — GenLayer Intelligent Contract (v1)

Status: **BUILT 16 Nov 2026.** Awaiting Muse's verification, then:
glsim live consensus, Studionet deploy, GitHub repo, Portal IC
submission. This week's 2 IC slots: 1 used by Token Safety Oracle
(submitted 16 Nov 22:32 WIB), 1 left — the Airdrop Eligibility Oracle
is already BUILT and also waiting, so Syarif decides which goes this
week and which waits for next week's reset (Mon 23 Nov 07:00 WIB).

Design: `DESIGN.md`. Picked by Syarif 16 Nov 2026 ("oke lanjut ide
ke 2" — the second of the two new IC ideas; duplicate check CLEAR in
Project Explorer 16 Nov 16:23 WIB, 212 projects; nearest neighbours
RugBond, ProphetSyndicate, ParamCover, Intelligent Oracle — none is
a DEX pool existence/depth oracle).

## What it does

"Does a sellable DEX pool exist for this token, and how deep is it?"
One contract, any EVM token with a DexScreener pair list. Validators
fetch the token's DexScreener pairs and answer NO_POOL / THIN /
LIQUID — before anyone tries to sell. This is NOT a price oracle: it
gives no price verdict, only pool existence and depth. No LLM in v1:
deterministic rule + JSON parse only, exact-agreement consensus (the
SafeLink pattern).

The raw `liquidity.usd` number is NEVER compared: it moves between
validator fetches. What is compared is the liquidity bucket (none /
thin / liquid) plus the best pair identity (chainId, dexId,
pairAddress). The raw number is recorded as an observation only.

## Files

- `contracts/pool_liquidity_logic.py` — pure stdlib logic, unit-tested.
- `contracts/pool_liquidity_oracle.py` — the deployable single-file
  contract (pure functions byte-identical to pool_liquidity_logic.py;
  runner pinned to stable Studionet py-genlayer v0.2.5, same as
  SafeLink and the Token Safety Oracle).
- `tests/test_logic.py` — pure-logic tests (normalization, verdict
  rule boundaries, derive_signals on live-verified bodies).
- `tests/test_contract.py` — contract tests with the fake-genlayer
  stub (all 3 verdicts, caching, disputes, disagreement = no write,
  TTL expiry).
- `tests/test_contract_sync.py` — sync guard + runner pin + no-LLM
  guard + no-`gl.UserError` guard (the 15 Nov Oracle lesson) +
  compared-fields guard (raw liquidity.usd never in consensus).
- `tests/conftest.py` — fake genlayer stub (GET) + live-verified demo
  JSON builders.
- `tests-direct/test_pool_liquidity_direct.py` — real GenVM direct
  tests (gltest) with REAL DexScreener response bytes from
  `tests-direct/fixtures/dexscreener-*.json`, fetched live 16 Nov 2026.

## Verdict rule (deterministic, no LLM)

- **NO_POOL** = `pairs` is null or empty.
- **LIQUID** = best pair's `liquidity.usd` >= 1000.
- **THIN** = best pair exists and its `liquidity.usd` < 1000.
- **UNCHECKED** (no verdict written) = fetch failed, non-200,
  unparseable body, missing/non-list `pairs`, or validator
  disagreement.

Best pair = highest `liquidity.usd`. A pair with a missing or
unparseable `liquidity.usd` counts as 0 for ranking (it can never win
over a pair with a real value, and a list of only such pairs yields
THIN, not LIQUID).

## Demo tokens (all live-verified 16 Nov 2026 by curl)

1. **WBNB — LIQUID.** `0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c`:
   30 pairs, best PancakeSwap `0x16b9a82891338f9bA80E2D6970FddA79D1eb0daE`
   (BSC), $34,643,680.07. Note: at 16:09 the best pair was a different
   PancakeSwap pair ($11,883,047.59) — the pair list moves, which is
   exactly why the raw number is never compared.
2. **GOATT — NO_POOL.** `0x47c9c2e3cdd0855aa18b1cbe1b0e18f0bae32ab0`:
   `pairs: null` (matches Syarif's known state: GOATT has no pool).
   FEG, NOMIO and CLAF also return `pairs: null` (checked 16 Nov).
3. **Brian Pepe — THIN.** `0xe327312b1d3e562614516e391462fbf8d2b3c636`
   (Robinhood Chain): 1 pair, Uniswap
   `0xB989DBDd6df5EC86B80659E19483cD5362dd8394`, $1.09. Verified twice,
   stable across checks. Brand-new token: re-verify live before the
   Studio deploy, and have a backup ready.
4. **Nouny — THIN (backup demo).**
   `0xcaeed5281bd1eeb26d5f8bd550bf5c3727ba6514` (Robinhood Chain):
   1 pair, Uniswap `0x65d67df8f1b50856f5dfb7ed1be77290353af40e4823012c7f980a49063ea4f2`,
   $0.54.
5. **Dead address — NO_POOL when pairs null, UNCHECKED on failure.**
   A token with no pairs parses to NO_POOL; a fetch failure writes
   nothing. (Contrast with Token Safety, where an empty GoPlus result
   writes nothing.)

Not usable as demos: the latest token profiles on DexScreener are
mostly either far above $1,000 or pumpfun pairs with null liquidity.
No major-chain (ethereum/bsc/base/arbitrum/polygon) token in the
$1–$999 band turned up in two profile scans — the pinned THIN demos
are both Robinhood Chain memecoins.

## Test result (16 Nov 2026, SafeLink venv)

- Stub suite: **76 passed, 0 failed** (first run 74/76 — one real bug
  found and fixed, see TEST_LOG.md; second run 76/76).
- GenVM direct suite: **10 passed, 0 failed** (first run; second run
  10/10).
- `python3 -m py_compile` on both contract files: OK.
- SafeLink suite still passes (55/55) in the same venv.

Run stub tests: `python -m pytest -q` (venv with pytest; system
python has no pytest — see TEST_LOG.md).
Run direct tests:
`../../genlayer-intelligent-contracts-submission/safelink/.venv/bin/gltest tests-direct -q`
from this directory.

## Still to do (Muse / Syarif)

- Muse verifies the build (second full test run per Syarif's 22:35
  WIB submit rule); glsim live consensus (same no_proxy fix as Token
  Safety: sanitized `no_proxy`/`NO_PROXY` for the glsim server
  process); Studionet deploy + live runs (all 3 verdicts live with
  the pinned demo tokens — re-verify Brian Pepe live first).
- GitHub repo (Syarif creates + adds to the Muse GitHub App
  installation — the connector cannot create repos), Portal IC
  submission (1 slot left this week; Airdrop Eligibility Oracle is
  the other candidate — Syarif decides).
- Submission text: write it plain from the start, no em-dash
  constructions, short sentences — Syarif flagged the Token Safety
  draft's em-dash phrasing as obvious AI writing (16 Nov 22:29 WIB).
