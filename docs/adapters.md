# Exchange adapters — status and caveats

All eight are implemented behind `apps/exchanges/base.py`. Signing schemes were
taken from the vendored docs in `reference/` and each is unit-tested against an
independently computed expected signature (`backend/tests/test_adapters.py`).

> **None of these has been run against a live exchange or testnet.** They are
> correct against the published documentation and the fixtures, which is not the
> same as correct against the real API. Run each on testnet — and with a tiny
> balance on mainnet where no testnet exists — before connecting partner capital.

| Exchange | Auth | Markets | Testnet | SL/TP | Notes |
|---|---|---|---|---|---|
| **Hyperliquid** | EIP-712 agent wallet | perps | ✅ | trigger orders | Official SDK, run off-thread. Q11 unverified. |
| **Bybit** | HMAC-SHA256 hex | spot + linear | ✅ | native, **amend in place** | Best fit: no cancel/replace window. |
| **Binance** | HMAC-SHA256 hex | spot + USDⓈ-M | ✅ | conditional orders | Rate limits are per-IP as well as per-key. |
| **Toobit** | HMAC-SHA256 hex | spot + USDT-M | ❌ | native at entry | Binance-style. No test environment (Q9). |
| **OKX** | HMAC-SHA256 base64 | spot + swap | ✅ header | native at entry, algo orders | **Sizes in contracts** — `ctVal` conversion. |
| **KuCoin** | HMAC-SHA256 base64 | futures only | ✅ | stop orders | Passphrase is HMAC'd too. XBT naming. |
| **Gate.io** | HMAC-SHA512 hex | futures | ✅ | price-triggered orders | Direction is the **sign of size**. |
| **LBank** | MD5 + HMAC-SHA256 | **spot only** | ❌ | ❌ | Futures impossible — see below. |

## Per-exchange caveats worth knowing before you trade

**Contract sizing.** OKX, KuCoin and Gate.io size positions in *contracts*, not
base units. Each adapter converts base units ↔ contracts using the exchange's
own multiplier (`ctVal`, `multiplier`, `quanto_multiplier`) and reports steps to
the sizing layer in base units, so `apps/trading/sizing.py` stays
exchange-agnostic. A wrong multiplier is a 10x or 100x position, so these
conversions are unit-tested explicitly.

**Spec §7 verification is not uniform.** Only Bybit and OKX expose API-key
permissions, so only those can *prove* a key is non-withdrawable. Binance
exposes it on the spot host only. Toobit, KuCoin, Gate.io and LBank publish no
permission endpoint at all — accounts on those connect **paused and flagged**
`withdrawal rights unverified` in the panel rather than silently claiming a
check that never happened.

**Spec §2 isolation.** Every adapter instance owns its own HTTP client and rate
limiter, and the registry never caches or shares them. The one exchange where
isolation is not fully in our control is **Binance**, whose weight limits are
partly per-IP: several Binance accounts behind one egress IP can contend. This
is declared as `per_key_rate_limits=False` and is worth watching if you connect
many Binance partners.

**Hyperliquid rate limits** are unusual: 1 request per 1 USDC of lifetime volume,
after an initial 10,000-request buffer. A fresh low-volume partner account can
exhaust it. Cancels get a larger allowance, so closing always remains possible.

**LBank futures cannot be built.** Their published contract API documents only
the public namespace `/cfd/openApi/v1/pub` — no private order, position, or
balance endpoints exist in any published document. Every futures method raises
`NotSupported` with that explanation rather than guessing at an undocumented
request shape. Spot works. Tracked as `questions.md` Q10.

## Before going live — checklist

1. Connect each account on **testnet** first (`testnet: true`) and run a full
   round trip: open → amend SL/TP → close.
2. Confirm the position size the exchange reports matches what the panel shows.
   This is where a contract-multiplier mistake surfaces.
3. Confirm SL/TP actually landed on the exchange, not just that the call
   returned 200.
4. On exchanges with no permission endpoint, confirm by hand in the exchange
   dashboard that the key cannot withdraw.
5. Then one live trade at minimum size before any partner capital.
