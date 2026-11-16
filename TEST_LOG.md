# Pool Liquidity Oracle — TEST_LOG

## 2026-11-16 ~22:40 WIB — Demo pinning (live curl)

- WBNB `0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c`: 30 pairs, best
  PancakeSwap `0x16b9a82891338f9bA80E2D6970FddA79D1eb0daE`,
  $34,643,680.07 (moved from $11,883,047.59 / pair 0x172f... at 16:09
  — the pair list moves; raw number is never compared).
- GOATT `0x47c9c2e3cdd0855aa18b1cbe1b0e18f0bae32ab0`: `pairs: null`
  → NO_POOL. FEG, NOMIO, CLAF also `pairs: null` (checked same run).
- THIN hunt: scanned 2 batches of DexScreener latest token profiles
  (30 each) + known small tokens. Most profiles are either far above
  $1,000 or pumpfun pairs with null liquidity. No major-chain
  (ethereum/bsc/base/arbitrum/polygon) token in the $1–$999 band
  turned up.
- THIN PINNED: Brian Pepe `0xe327312b1d3e562614516e391462fbf8d2b3c636`
  (Robinhood Chain): 1 pair, Uniswap
  `0xB989DBDd6df5EC86B80659E19483cD5362dd8394`, $1.09 — verified twice,
  stable across checks ~8 min apart. Brand-new token: re-verify live
  before Studio deploy.
- THIN BACKUP: Nouny `0xcaeed5281bd1eeb26d5f8bd550bf5c3727ba6514`
  (Robinhood Chain): 1 pair, Uniswap
  `0x65d67df8f1b50856f5dfb7ed1be77290353af40e4823012c7f980a49063ea4f2`,
  $0.54.
- Fixtures saved at `tests-direct/fixtures/dexscreener-{wbnb,goatt,
  brianpepe,nouny}.json` (fetched live 16 Nov 2026).

## Still open (NOT done by this build — parent's steps)

- glsim live consensus run, Studio deploy + live runs, GitHub repo
  (Syarif creates), Portal IC submission (1 slot left this week;
  Airdrop Eligibility Oracle is the other candidate).
- Per Syarif's 22:35 WIB submit rule: two full test runs before
  submit (builder run + Muse verification run).

## 2026-11-16 ~22:45 WIB — Build + test runs (SafeLink venv)

- `python3 -m py_compile` on both contract files: OK.
- Stub suite first run: **74 passed, 2 failed** — one REAL BUG found:
  the BRIANPEPE demo constant in `tests/conftest.py` was mixed-case
  (`0xe327312b1D3E562614516E391462Fbf8d2b3C636`, as DexScreener
  printed it), but the contract normalizes addresses to lower-case
  before rendering the URL, so the stub served a 404 and consensus
  failed. Fixed by lower-casing the constant (the direct-test file
  already had it lower-case). Lesson: demo address constants must be
  stored in canonical lower-case form, exactly like WBNB/GOATT.
  After fix: **76 passed, 0 failed.**
- GenVM direct suite (`gltest tests-direct -q`, SDK v0.2.16):
  **10 passed, 0 failed** (first run).
- Second full run (Syarif's test-2x rule): stub **76/76**, direct
  **10/10**, py_compile OK. Sanity: SafeLink suite still 55/55 in
  the same venv.
- gltest created `artifacts/` in the work dir (its default output
  dir, also present in the Token Safety Oracle's work dir) — build
  output only, not part of the submission.

## 2026-11-16 ~22:45 WIB — Muse verification run 1 + glsim LIVE consensus (parent)

- Muse re-ran the suites: stub **76/76**, direct **10/10**,
  py_compile OK on both contract files. Spot-checked: verdict rule
  matches DESIGN (NO_POOL / LIQUID >= 1000 / THIN else, unchecked on
  parse failure); sync guard passes (5/5, raw liquidity.usd never in
  consensus); fixtures match live data (Brian Pepe 1 pair $1.09,
  WBNB 30 pairs best $34,643,680.07, GOATT pairs null).
- THIN demos re-verified live by curl just before the glsim run:
  Brian Pepe $1.09 (stable), Nouny $0.54. WBNB best USD moved
  $34,643,680.07 → $34,639,460.47 within minutes — again proof the raw
  number must never be compared.
- glsim live (fresh server, sanitized no_proxy — same fix as Token
  Safety): **5/5 passed** — deploy defaults, WBNB LIQUID (17.4s, best
  pair 0x16b9a82891338f9ba80e2d6970fdda79d1eb0dae), GOATT NO_POOL
  (1.9s), Brian Pepe THIN (1.7s, usd_obs 1.09), Nouny THIN (1.8s,
  usd_obs 0.54). Stats: 4 checks, liquid 1, no_pool 1, thin 2.
  glsim contract address (local sim only):
  0x07e01768c9bdfcb7c061a5dd9ce4e3d8a52e4b7f.
- Still open (per Syarif's test-2x rule): SECOND full test run before
  Portal submit; Studio deploy + live runs; GitHub repo (Syarif
  creates); Portal IC submission (1 slot left this week — decision vs
  Airdrop Eligibility Oracle still open).

## 2026-11-16 22:50 WIB — Studio deploy + live runs on stable Studionet (browser task, verified by Muse on explorer)

- Studio (studio.genlayer.com, chain 61999 stable Studionet, NOT
  studio-next/Bradbury). Deployer/admin: Studio local account
  0x01ED7Ae5A842895C7E05a3CE5587d8DC67a6102F — same as SafeLink and
  Token Safety, already signed in; no faucet needed.
- Deployed contract: 0x162E4de929f77AFc30d39BDf566B0359D79a5f6a
  (explorer: https://explorer-studio.genlayer.com/address/0x162E4de929f77AFc30d39BDf566B0359D79a5f6a)
- Deploy tx: 0x1e2c36c373e62ce4f0ba0b60115177aff08b9420f44b08b64a54336d87182142 — FINALIZED, SUCCESS, consensus Accepted. Created Nov 16 2026 15:43:24 UTC.
- Live checks (check_token write → get_verdict read), all FINALIZED:
  - WBNB tx 0xae4eb046f8269edd966ce87a7f7b28f51c256e3a0bc6acb22ddfed160057c09b → LIQUID (best $34,658,427.3, PancakeSwap 0x16b9a82891338f9ba80e2d6970fdda79d1eb0dae)
  - GOATT tx 0x3e4e11bedf669700b822b3f14dad8da01aa975070f851a0c7e1a685bf1c4ed17 → NO_POOL (bucket none)
  - Brian Pepe tx 0x238b32baa7346880bd44e1d58047b6f04f93105927c74f36933c945a06735e5d → THIN (best $1.09, Uniswap robinhood)
  - Nouny tx 0x8dccca0c8bc20c412f1e25a6b4ef9eec7dc75f69c308dfa303a6c868b574ac06 → THIN (best $0.54, Uniswap robinhood)
- get_stats: admin 0x01ED…a6102F, check_count 4, liquid 1, no_pool 1, thin 2, total_entries 4, total_disputes 0, ttl_checks 1000.
- Explorer re-verified independently by Muse 22:50 WIB: contract page shows 5 txs (deploy + 4 checks), same hashes/statuses as the browser report. Minor: transient gen_getContractSchemaForCode error in Studio RPC log while the schema loaded — resolved, blocked nothing.
- SECOND FULL TEST RUN (test-2x rule, Muse, before submit): stub 76/76 + direct 10/10, py_compile OK. Test-2x now satisfied: builder 2x + Muse verification run 1 + Muse second run.
- Still open: GitHub repo Pool-Liquidity-Oracle (Syarif creates — does NOT exist yet); Portal IC submission (1 slot left this week — decision Pool vs Airdrop Eligibility Oracle open).
