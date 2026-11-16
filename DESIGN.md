# Pool Liquidity Oracle — Design v1 (2026-11-16)

Picked by Syarif 2026-11-16 22:33 WIB: "oke lanjut ide ke 2" — the
second of the two new IC ideas researched 16 Nov (Token Safety Oracle
was idea 1, submitted the same day). Duplicate check CLEAR in Project
Explorer 16 Nov 16:23 WIB (212 projects; nearest neighbours RugBond,
ProphetSyndicate, ParamCover, Intelligent Oracle — none is a DEX pool
existence/depth oracle). Docs read: GenLayer use-cases + ideas pages —
not on that list.

Concept: one Intelligent Contract answering "Does a sellable DEX pool
exist for this token, and how deep is it?" Validators fetch the token's
DexScreener pair list and answer NO_POOL / THIN / LIQUID — before
anyone tries to sell. This is NOT a price oracle: it gives no price
verdict, only pool existence and depth. That is what sets it apart
from the banned Multi-Source Price Oracle idea.

## Live source (verified 16 Nov 16:09–16:15 WIB by curl)

`GET https://api.dexscreener.com/latest/dex/tokens/{token_address}`
— free, no API key, ~300 req/min. Response envelope:
`{"schemaVersion":"1.0.0","pairs":[...]|null}`. Each pair carries
`chainId`, `dexId`, `pairAddress`, `liquidity: {"usd": <number>, ...}`.

- WBNB BSC `0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c` → LIQUID demo:
  best pair PancakeSwap `0x172fcD41E0913e95784454622d1c3724f546f849`,
  liquidity $11,883,047.59.
- GOATT `0x47c9c2e3cdd0855aa18b1cbe1b0e18f0bae32ab0` → NO_POOL demo:
  `pairs: null` (matches Syarif's known state: GOATT has no pool).
- THIN demo token NOT yet pinned — the builder must find and pin one
  before building the tests around it (a real token whose best pair
  has liquidity between $1 and $999, verified by live curl first).
  Do not invent liquidity values.

## Question, verdicts, rule (deterministic, no LLM in v1)

`check_token(token_address)` via `gl.vm.run_nondet_unsafe`
(SafeLink pattern). Verdict written ONLY on exact agreement (see
below). No verdict written (unchecked) on: checker unreachable,
non-200, unparseable JSON, or validator disagreement — same
safe-failure as SafeLink and Token Safety Oracle.

Verdict rule — total (every fetched result yields exactly one verdict):
- **NO_POOL** = `pairs` is null or empty.
- **LIQUID** = best pair's `liquidity.usd` ≥ 1000.
- **THIN** = best pair exists and its `liquidity.usd` < 1000.

Best pair = the pair with the highest `liquidity.usd`. A pair with a
missing or unparseable `liquidity.usd` counts as 0 for ranking (it can
never win over a pair with a real value, and a list of only such pairs
yields THIN, not LIQUID).

## Consensus — exact agreement fields

`token_address` (normalized lowercase), `pair_chain_id`,
`pair_dex_id`, `pair_address`, `liquidity_bucket`, `status_code`.
`liquidity_bucket` is derived from the best pair: `"none"` (no pairs),
`"thin"` (best liquidity < 1000), `"liquid"` (best liquidity ≥ 1000).
The raw `liquidity.usd` number is NEVER compared (it moves between
validator fetches) — it is recorded as observation only, like
`source_url` (rendered request URL, also compared, as in SafeLink).
For NO_POOL, the pair fields compare as `""` and the bucket as
`"none"`. All compared values normalized to strings; a field the API
omits compares as `""`.

## Normalization

- `token_address`: `0x` + 40 hex chars, lowercased, or the call is rejected.
- No chain parameter in v1: DexScreener searches all chains and each
  pair carries its own `chainId`. The same address on two chains is
  one lookup; the best pair wins globally.

## State / API (mirrors SafeLink + Token Safety Oracle)

- `TreeMap[token_address → Entry]`, `entry_order`, counters
  (`checks`, `no_pool`, `thin`, `liquid`, `disputes`), `ttl_checks`
  default 1000. Admin = deployer (same Studio account as SafeLink).
- Entry: `token_address`, `verdict`, all compared fields,
  `best_liquidity_usd` (observation string, as returned), `source_url`,
  `status_code`, `check_seq`, `disputes`.
- Anyone: `check_token`, `dispute`, `request_recheck`.
- Admin-only: `set_ttl_checks`.
- Views: `get_verdict`, `is_liquid` (verdict == LIQUID), `get_entry`,
  `list_entries`, `get_stats`.

## Tests (mirror Token Safety Oracle: stub + real GenVM direct)

- Stub tests (mocked web): LIQUID shape (WBNB), THIN shape, NO_POOL
  shape (`pairs: null` and `pairs: []`), non-200, malformed JSON,
  bad address, admin guards, TTL recheck, dispute flow,
  agreement-vs-disagreement.
- Real GenVM direct tests: live DexScreener fetch for WBNB (must parse
  LIQUID with the known pair) + GOATT (must parse NO_POOL); THIN live
  only if the pinned demo token verifies by curl first.
- Target: Studionet 61999, runner pin
  `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6`
  (v0.2.5). SDK v0.2.16; `Response` fields `.status` / `.headers` /
  `.body`. Storage structs need `@allow_storage`. `UserError` comes
  from `genlayer.gl.vm`, never `gl.UserError` (the 15 Nov Oracle
  lesson — enforced by a sync test, as in Token Safety Oracle).

## Build / submission plan

- Build now (delegated builder, Muse verifies — same cadence as Token
  Safety Oracle). Work dir:
  `~/workspace/goals/genlayer-intelligent-contracts-submission/pool-liquidity-oracle/`
  (mirror `token-safety-oracle/` layout: `contracts/`, `tests/`,
  `tests-direct/`, `scripts/`, `README.md`, `TEST_LOG.md`).
- Then: glsim live consensus run (same no_proxy fix as Token Safety:
  sanitized `no_proxy`/`NO_PROXY` for the glsim server process),
  Studionet deploy + live runs (all 3 verdicts live if demo tokens pin
  cleanly), GitHub repo (Syarif creates + adds to Muse GitHub App
  installation — connector cannot create repos), Portal IC submission.
- SLOT NOTE: this week's 2 IC slots — 1 used by Token Safety Oracle
  (submitted 16 Nov 22:32 WIB, 1 left). The Airdrop Eligibility Oracle
  is already BUILT and also waiting for a slot. Once Pool Liquidity is
  built there will be 2 candidates for 1 slot; Syarif decides which
  goes this week and which waits for next week's reset (Mon 23 Nov
  07:00 WIB).
- Submission text: write it plain from the start, no em-dash
  constructions, short sentences — Syarif flagged the Token Safety
  draft's em-dash phrasing as obvious AI writing (16 Nov 22:29 WIB)
  and had it rewritten before submit.

## Honest limits (state plainly in the submission)

- A pool on a DEX DexScreener does not index reads as a false
  NO_POOL; a brand-new pool takes minutes to appear in the index.
- A verdict is a snapshot of pool depth *now*, not a guarantee — depth
  can drain between the check and the sell, and a LIQUID pool can
  still have a token that cannot be sold for other reasons (honeypot,
  paused transfers — that is what the Token Safety Oracle checks).
- No price verdict in v1 by design.
