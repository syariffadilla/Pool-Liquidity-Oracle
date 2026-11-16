# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

"""Pool Liquidity Oracle — does a sellable DEX pool exist for this token, and how deep is it?

One contract, any EVM token with a DexScreener pair list. Any account
can ask the contract to check a token; the leader fetches the token's
DexScreener pairs, every validator independently re-fetches them and
re-derives the same signals, and a verdict is written ONLY when they
agree exactly on the compared signal fields. Disagreement means no
write (the transaction goes undetermined) — a verdict is never written
on one node's word alone.

The verdict is a DETERMINISTIC rule over the pair list (see
verdict_from_signals). No LLM is called anywhere in v1: pool existence
and depth here are checkable facts, not an LLM opinion. That is the
whole point of the primitive — the same token checked twice gives the
same verdict, and any reviewer can re-derive it by hand from the
stored evidence.

What is compared is the liquidity BUCKET (none / thin / liquid) plus
the best pair identity (chainId, dexId, pairAddress). The raw
liquidity.usd number is NEVER compared: it moves between validator
fetches. It is recorded as an observation only.

This is NOT a price oracle: it gives no price verdict, only pool
existence and depth. A verdict is a snapshot of pool depth now, not a
guarantee: depth can drain between the check and the sell, and a
LIQUID pool can still hold a token that cannot be sold for other
reasons (honeypot, paused transfers — that is what the Token Safety
Oracle checks). A pool on a DEX DexScreener does not index reads as a
false NO_POOL; a brand-new pool takes minutes to appear in the index.
The submission states these limits plainly.

Target: stable Studionet, GenVM runner py-genlayer v0.2.5
(1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6) — same as
SafeLink and the Token Safety Oracle. Do NOT deploy this file to
Studio-dev / v0.6 without re-pinning the header.

The pure functions below (normalize_token_address, render_source_url,
_parse_usd, _usd_str, _best_pair, derive_signals,
verdict_from_signals) are byte-identical copies of
contracts/pool_liquidity_logic.py, which is unit-tested with plain
pytest. They are duplicated here because a single-file GenLayer
contract cannot import a sibling module on-chain.
tests/test_contract_sync.py fails the build if the copies drift.
"""

import json

from genlayer import *

DEXSCREENER_BASE_URL = "https://api.dexscreener.com/latest/dex/tokens"

LIQUID_THRESHOLD_USD = 1000

VERDICT_NO_POOL = "no_pool"
VERDICT_THIN = "thin"
VERDICT_LIQUID = "liquid"
VERDICT_UNCHECKED = "unchecked"

BUCKET_NONE = "none"
BUCKET_THIN = "thin"
BUCKET_LIQUID = "liquid"

# Signal fields the validator must agree on exactly. Everything else in
# the signals dict is observation only. All compared values are strings.
COMPARED_SIGNAL_KEYS = (
    "token_address",
    "pair_chain_id",
    "pair_dex_id",
    "pair_address",
    "liquidity_bucket",
    "status_code",
    "source_url",
)

BODY_SAMPLE_LEN = 200

_HEX = "0123456789abcdef"

DEFAULT_TTL_CHECKS = 1000
MAX_LIST_LIMIT = 100


def normalize_token_address(raw_address):
    """Normalize a token contract address into its canonical registry key.

    Lower-case ``0x`` + 40 hex chars. Raises ValueError on anything
    else. The contract converts this to UserError.
    """
    if not isinstance(raw_address, str):
        raise ValueError("token address must be a string")
    address = raw_address.strip().lower()
    if not address.startswith("0x"):
        raise ValueError("token address must start with 0x")
    if len(address) != 42:
        raise ValueError("token address must be 0x + 40 hex chars")
    for ch in address[2:]:
        if ch not in _HEX:
            raise ValueError("token address contains a non-hex character")
    return address


def render_source_url(token_address):
    """Render the DexScreener token-pairs URL for a token address.

    The address is validated and normalized to lower-case. Raises
    ValueError on invalid input. DexScreener searches all chains in
    one lookup; each pair carries its own chainId, so v1 takes no
    chain parameter.
    """
    token_address = normalize_token_address(token_address)
    return DEXSCREENER_BASE_URL + "/" + token_address


def _parse_usd(raw):
    """Parse a DexScreener liquidity.usd value to a float or None.

    DexScreener returns a JSON number, but be defensive: accept
    int/float (never bool) and numeric strings. Missing, null, or
    unparseable values return None — the caller treats None as 0 for
    ranking, never as a real value.
    """
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        if raw == "":
            return None
        try:
            return float(raw)
        except ValueError:
            return None
    return None


def _usd_str(raw):
    """Render a liquidity.usd value as an observation string.

    Missing or null renders as "". Numbers render with str() (the
    shortest round-tripping form). Strings pass through unchanged.
    This string is recorded for audit only and is never compared.
    """
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, bool):
        return ""
    if isinstance(raw, (int, float)):
        return str(raw)
    return str(raw)


def _best_pair(pairs):
    """Pick the best pair from a list of DexScreener pair dicts.

    Best = highest parsed liquidity.usd (missing/unparseable counts
    as 0). Non-dict entries are skipped. Ties go to the first pair in
    list order, so the choice is deterministic for a given body.
    Returns (pair_dict_or_None, best_usd_float).
    """
    best = None
    best_usd = 0.0
    for pair in pairs:
        if not isinstance(pair, dict):
            continue
        liquidity = pair.get("liquidity")
        usd = 0.0
        if isinstance(liquidity, dict):
            parsed = _parse_usd(liquidity.get("usd"))
            if parsed is not None:
                usd = parsed
        if best is None or usd > best_usd:
            best = pair
            best_usd = usd
    return best, best_usd


def derive_signals(token_address, source_url, status_code, body):
    """Derive the check signals for one fetched DexScreener response.

    ``token_address`` must already be normalized, ``body`` is the
    decoded response text. Runs identically on leader and validator;
    the validator compares exactly the COMPARED_SIGNAL_KEYS fields of
    the result. A non-200 status, an unparseable body, a missing or
    non-list ``pairs`` field yields ``parse_ok`` False — the contract
    treats that as a failed fetch and writes nothing. ``pairs`` null
    or ``[]`` parses fine and yields NO_POOL.
    """
    signals = {
        "token_address": token_address,
        "source_url": source_url,
        "status_code": str(status_code),
        "parse_ok": False,
        "pair_chain_id": "",
        "pair_dex_id": "",
        "pair_address": "",
        "liquidity_bucket": BUCKET_NONE,
        "best_liquidity_usd": "",
        # Observation only — recorded for audit, never compared.
        "content_len": len(body),
        "body_sample": body[:BODY_SAMPLE_LEN],
    }
    if status_code != 200:
        return signals
    try:
        data = json.loads(body)
    except (ValueError, TypeError):
        return signals
    if not isinstance(data, dict):
        return signals
    if "pairs" not in data:
        return signals
    pairs = data.get("pairs")
    if pairs is None:
        signals["parse_ok"] = True
        return signals
    if not isinstance(pairs, list):
        return signals
    if len(pairs) == 0:
        signals["parse_ok"] = True
        return signals
    best, best_usd = _best_pair(pairs)
    if best is None:
        signals["parse_ok"] = True
        return signals
    liquidity = best.get("liquidity")
    raw_usd = None
    if isinstance(liquidity, dict):
        raw_usd = liquidity.get("usd")
    signals["pair_chain_id"] = str(best.get("chainId", "") or "")
    signals["pair_dex_id"] = str(best.get("dexId", "") or "")
    pair_address = best.get("pairAddress", "") or ""
    signals["pair_address"] = (
        str(pair_address).lower() if pair_address else ""
    )
    signals["best_liquidity_usd"] = _usd_str(raw_usd)
    if best_usd >= LIQUID_THRESHOLD_USD:
        signals["liquidity_bucket"] = BUCKET_LIQUID
    else:
        signals["liquidity_bucket"] = BUCKET_THIN
    signals["parse_ok"] = True
    return signals


def verdict_from_signals(signals):
    """Deterministic verdict rule. Pure function of the signals dict.

    no_pool: pairs null or empty.
    liquid: best pair liquidity.usd >= 1000.
    thin: best pair exists and its liquidity.usd < 1000 (including
        0 for pairs with missing or unparseable liquidity).
    unchecked: the source could not be fetched or parsed — no verdict
        is written for this case.
    """
    if not signals["parse_ok"]:
        return VERDICT_UNCHECKED
    if signals["liquidity_bucket"] == BUCKET_NONE:
        return VERDICT_NO_POOL
    if signals["liquidity_bucket"] == BUCKET_LIQUID:
        return VERDICT_LIQUID
    return VERDICT_THIN


from genlayer import allow_storage
from genlayer.gl.vm import UserError


@allow_storage
class Entry:
    """One token liquidity verdict. Stored as the value of TreeMap[str, Entry]."""

    token_address: str
    verdict: str
    pair_chain_id: str
    pair_dex_id: str
    pair_address: str
    liquidity_bucket: str
    best_liquidity_usd: str
    source_url: str
    status_code: u64
    checked_seq: u64
    disputes: u64
    last_dispute_reason: str
    disputed: bool

    def __init__(
        self,
        token_address="",
        verdict="unchecked",
        pair_chain_id="",
        pair_dex_id="",
        pair_address="",
        liquidity_bucket="none",
        best_liquidity_usd="",
        source_url="",
        status_code=0,
        checked_seq=0,
        disputes=0,
        last_dispute_reason="",
        disputed=False,
    ):
        self.token_address = token_address
        self.verdict = verdict
        self.pair_chain_id = pair_chain_id
        self.pair_dex_id = pair_dex_id
        self.pair_address = pair_address
        self.liquidity_bucket = liquidity_bucket
        self.best_liquidity_usd = best_liquidity_usd
        self.source_url = source_url
        self.status_code = status_code
        self.checked_seq = checked_seq
        self.disputes = disputes
        self.last_dispute_reason = last_dispute_reason
        self.disputed = disputed


@allow_storage
class PoolLiquidityOracle(gl.Contract):
    admin: Address
    entries: TreeMap[str, Entry]
    entry_order: DynArray[str]
    check_count: u64
    no_pool_count: u64
    thin_count: u64
    liquid_count: u64
    total_disputes: u64
    ttl_checks: u64

    def __init__(self):
        self.admin = gl.message.sender_address
        self.check_count = 0
        self.no_pool_count = 0
        self.thin_count = 0
        self.liquid_count = 0
        self.total_disputes = 0
        self.ttl_checks = DEFAULT_TTL_CHECKS

    # -- internal helpers (deterministic, no nondet calls) ------------

    def _require_admin(self):
        if gl.message.sender_address != self.admin:
            raise UserError("Pool Liquidity Oracle: only admin")

    def _normalize_token_or_raise(self, raw_address: str) -> str:
        try:
            return normalize_token_address(raw_address)
        except ValueError as exc:
            raise UserError(
                "Pool Liquidity Oracle: invalid token address: " + str(exc)
            )

    def _is_fresh(self, entry: Entry) -> bool:
        if entry.disputed:
            return False
        return (self.check_count - entry.checked_seq) < self.ttl_checks

    def _increment_counter(self, verdict: str):
        if verdict == VERDICT_NO_POOL:
            self.no_pool_count += 1
        elif verdict == VERDICT_THIN:
            self.thin_count += 1
        elif verdict == VERDICT_LIQUID:
            self.liquid_count += 1

    def _decrement_counter(self, verdict: str):
        if verdict == VERDICT_NO_POOL and self.no_pool_count > 0:
            self.no_pool_count -= 1
        elif verdict == VERDICT_THIN and self.thin_count > 0:
            self.thin_count -= 1
        elif verdict == VERDICT_LIQUID and self.liquid_count > 0:
            self.liquid_count -= 1

    def _entry_dict(self, entry: Entry, cached: bool = False) -> dict:
        return {
            "token_address": entry.token_address,
            "verdict": entry.verdict,
            "pair_chain_id": entry.pair_chain_id,
            "pair_dex_id": entry.pair_dex_id,
            "pair_address": entry.pair_address,
            "liquidity_bucket": entry.liquidity_bucket,
            "best_liquidity_usd": entry.best_liquidity_usd,
            "source_url": entry.source_url,
            "status_code": entry.status_code,
            "fresh": self._is_fresh(entry),
            "cached": cached,
            "checked_seq": entry.checked_seq,
            "disputes": entry.disputes,
            "last_dispute_reason": entry.last_dispute_reason,
            "disputed": entry.disputed,
        }

    def _dispute(self, key: str, reason: str) -> dict:
        entry = self.entries.get(key, None)
        if entry is None:
            raise UserError("Pool Liquidity Oracle: unknown check")
        entry.disputed = True
        entry.disputes += 1
        entry.last_dispute_reason = reason[:200]
        self.total_disputes += 1
        self.entries[key] = entry
        return self._entry_dict(entry)

    # -- views ---------------------------------------------------------

    @gl.public.view
    def get_verdict(self, token_address: str) -> dict:
        token_address = self._normalize_token_or_raise(token_address)
        entry = self.entries.get(token_address, None)
        if entry is None:
            return {
                "token_address": token_address,
                "verdict": VERDICT_UNCHECKED,
                "fresh": False,
                "cached": False,
            }
        return self._entry_dict(entry)

    @gl.public.view
    def get_entry(self, token_address: str) -> dict:
        return self.get_verdict(token_address)

    @gl.public.view
    def is_liquid(self, token_address: str) -> bool:
        token_address = self._normalize_token_or_raise(token_address)
        entry = self.entries.get(token_address, None)
        if entry is None:
            return False
        return entry.verdict == VERDICT_LIQUID and self._is_fresh(entry)

    @gl.public.view
    def list_entries(self, offset: u64, limit: u64) -> dict:
        total = len(self.entry_order)
        if limit == 0 or limit > MAX_LIST_LIMIT:
            limit = MAX_LIST_LIMIT
        result = []
        if offset < total:
            i = total - offset
            count = 0
            while i > 0 and count < limit:
                i -= 1
                key = self.entry_order[i]
                entry = self.entries.get(key, None)
                if entry is not None:
                    result.append(self._entry_dict(entry))
                    count += 1
        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "entries": result,
        }

    @gl.public.view
    def get_stats(self) -> dict:
        return {
            "total_entries": len(self.entry_order),
            "check_count": self.check_count,
            "no_pool": self.no_pool_count,
            "thin": self.thin_count,
            "liquid": self.liquid_count,
            "total_disputes": self.total_disputes,
            "ttl_checks": self.ttl_checks,
            "admin": str(self.admin),
        }

    # -- writes: checking ----------------------------------------------

    @gl.public.write
    def check_token(self, token_address: str) -> dict:
        token_address = self._normalize_token_or_raise(token_address)
        key = token_address
        existing = self.entries.get(key, None)
        # Fresh, non-disputed entries are returned without a new
        # consensus round. Disputed entries always re-check.
        if existing is not None and self._is_fresh(existing):
            return self._entry_dict(existing, cached=True)

        # Snapshot consensus inputs BEFORE the nondet block. Storage is
        # never read or written inside leader_fn / validator_fn.
        source_url = render_source_url(token_address)

        def leader_fn():
            response = gl.nondet.web.get(source_url)
            # The real SDK (py-lib-genlayer-std v0.2.16, Response
            # dataclass) exposes the field as `response.status`, and
            # `body` may be None. Same correction SafeLink learned.
            if response.status != 200:
                raise UserError(
                    "Pool Liquidity Oracle: fetch failed with status "
                    + str(response.status)
                )
            raw_body = response.body or b""
            if isinstance(raw_body, bytes):
                body_text = raw_body.decode("utf-8", "ignore")
            else:
                body_text = str(raw_body)
            signals = derive_signals(
                token_address,
                source_url,
                response.status,
                body_text,
            )
            if not signals["parse_ok"]:
                raise UserError(
                    "Pool Liquidity Oracle: DexScreener data unparseable"
                )
            return signals

        def validator_fn(leaders_res):
            # Leader errors are not agreed on in v1: a failed fetch
            # disagrees and retries with another leader instead of
            # writing anything. See SafeLink's CONSENSUS.md.
            if not isinstance(leaders_res, gl.vm.Return):
                return False
            mine = leader_fn()
            leader = leaders_res.calldata
            for key in COMPARED_SIGNAL_KEYS:
                if mine.get(key) != leader.get(key):
                    return False
            return True

        signals = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)
        verdict = verdict_from_signals(signals)

        self.check_count += 1
        entry = Entry(
            token_address=token_address,
            verdict=verdict,
            pair_chain_id=signals["pair_chain_id"],
            pair_dex_id=signals["pair_dex_id"],
            pair_address=signals["pair_address"],
            liquidity_bucket=signals["liquidity_bucket"],
            best_liquidity_usd=signals["best_liquidity_usd"],
            source_url=signals["source_url"],
            status_code=int(signals["status_code"]),
            checked_seq=self.check_count,
            disputes=0 if existing is None else existing.disputes,
            last_dispute_reason=(
                "" if existing is None else existing.last_dispute_reason
            ),
            disputed=False,
        )
        if existing is None:
            self.entry_order.append(key)
        else:
            self._decrement_counter(existing.verdict)
        self._increment_counter(verdict)
        self.entries[key] = entry
        return self._entry_dict(entry)

    # -- writes: disputes -----------------------------------------------

    @gl.public.write
    def dispute_token(self, token_address: str, reason: str) -> dict:
        token_address = self._normalize_token_or_raise(token_address)
        return self._dispute(token_address, reason)

    @gl.public.write
    def request_recheck(self, token_address: str) -> dict:
        token_address = self._normalize_token_or_raise(token_address)
        return self._dispute(token_address, "recheck requested")

    # -- writes: admin ---------------------------------------------------

    @gl.public.write
    def set_ttl_checks(self, ttl: u64) -> dict:
        self._require_admin()
        if ttl == 0:
            raise UserError("Pool Liquidity Oracle: ttl must be > 0")
        self.ttl_checks = ttl
        return {"ttl_checks": self.ttl_checks}
