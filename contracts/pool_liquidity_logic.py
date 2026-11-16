"""Pure, deterministic Pool Liquidity Oracle logic.

Stdlib only — no GenLayer imports — so this module is unit-testable with
plain pytest and no GenVM. The contract file
``contracts/pool_liquidity_oracle.py`` contains byte-identical copies of
these functions (checked by ``tests/test_contract_sync.py``); the
contract is self-contained because a single-file GenLayer contract
cannot import a sibling module on-chain.

Design (see DESIGN.md for the full story):

* The verdict is a DETERMINISTIC rule over a DexScreener pair list
  (see verdict_from_signals). No LLM is called anywhere in v1.
  Validators re-fetch the same DexScreener URL and compare the
  derived signals exactly.
* Only the signal fields listed in ``COMPARED_SIGNAL_KEYS`` are part of
  consensus. The raw ``liquidity.usd`` number is NEVER compared: it
  moves between validator fetches. What is compared is the liquidity
  BUCKET (none / thin / liquid) plus the best pair identity
  (chainId, dexId, pairAddress). The raw number is recorded as an
  observation only (``best_liquidity_usd``).
* Best pair = the pair with the highest ``liquidity.usd``. A pair with
  a missing or unparseable ``liquidity.usd`` counts as 0 for ranking:
  it can never win over a pair with a real value, and a list of only
  such pairs yields THIN, not LIQUID.
* A verdict is written ONLY on exact agreement. A fetch failure, a
  non-200 status, an unparseable body, or validator disagreement
  writes nothing — the same safe-failure as SafeLink and the Token
  Safety Oracle.
* This is NOT a price oracle: it gives no price verdict, only pool
  existence and depth.
"""

import json

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
