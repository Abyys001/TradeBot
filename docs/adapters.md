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
| **Hyperliquid** | EIP-712 agent wallet | perps | ✅ | trigger orders, cancel+replace | Official SDK, run off-thread. Q11 unverified. |
| **Bybit** | HMAC-SHA256 hex | spot + linear | ✅ | native, **amend in place** | Best fit: no cancel/replace window. |
| **Binance** | HMAC-SHA256 hex | USDⓈ-M | ✅ | conditional orders, cancel+replace | Rate limits are per-IP as well as per-key. Key permissions live on the **spot** host. |
| **Toobit** | HMAC-SHA256 hex | USDT-M | ❌ | native, **amend in place** | Signing is query-only (`X-BB-APIKEY`); contract ids via `exchangeInfo.contracts[]`. No test environment (Q9). |
| **OKX** | HMAC-SHA256 base64 | spot + swap | ✅ header | native at entry, OCO algo orders, cancel+replace | **Sizes in contracts** — `ctVal` conversion. |
| **KuCoin** | HMAC-SHA256 base64 | futures only | ✅ | stop orders, cancel+replace | Passphrase is HMAC'd too. XBT naming. Key permissions live on the **spot** host. |
| **Gate.io** | HMAC-SHA512 hex | futures | ✅ | price-triggered orders, cancel+replace | Direction is the **sign of size**. |
| **LBank** | MD5 + HMAC-SHA256 | **spot only** | ❌ | ❌ | Futures impossible — see below. Spot buy/sell round trip works. |

## Per-exchange caveats worth knowing before you trade

**Contract sizing.** OKX, KuCoin and Gate.io size positions in *contracts*, not
base units. Each adapter converts base units ↔ contracts using the exchange's
own multiplier (`ctVal`, `multiplier`, `quanto_multiplier`) and reports steps to
the sizing layer in base units, so `apps/trading/sizing.py` stays
exchange-agnostic. A wrong multiplier is a 10x or 100x position, so these
conversions are unit-tested explicitly.

**Exit recovery is not uniform.** When a position ends on the venue rather than
from the panel — a stop or take profit firing, a liquidation, a close made in
the exchange's own app — the exit price and the realised PnL exist only in that
exchange's fill record. `possync` asks for them through
`ExchangeAdapter.get_closed_pnl`, which **only Hyperliquid** (via
`userFillsByTime`, whose per-fill `closedPnl` is the venue's own realised
number, fees subtracted here) and the paper adapter implement today. Every
other adapter inherits the default `None` = "cannot answer", and on those the
trade log shows an em dash for that leg's exit and PnL. That is deliberate:
nothing is estimated from a mark price, because a number the exchange did not
say is not a fill. Adding a venue means one method on its adapter — the branch
in `possync` is already there.

**Spec §7 verification is not uniform.** Bybit, OKX, Binance and KuCoin expose
API-key permissions, so those four can *prove* a key is non-withdrawable.
Binance exposes it on the **spot** host (`api.binance.com/sapi/v1/account/
apiRestrictions`) while every other Binance call goes to the futures host, so
that one request is made with an absolute URL — and a futures-only key cannot
reach it at all, in which case the account is flagged rather than refused. The
futures testnet has no `/sapi` namespace, so a testnet Binance account can
never be verified from the API. KuCoin is the same shape: `GET
/api/v1/user/api-key` lives on `api.kucoin.com`, and a `Transfer` permission is
refused (`InnerTransfer` only moves funds between the user's own accounts and is
not a withdrawal right). Toobit, Gate.io, Hyperliquid and LBank publish no
permission endpoint at all — accounts on those connect **paused and flagged**
`withdrawal rights unverified` in the panel rather than silently claiming a
check that never happened.

The check is re-run on **resume**, not just at connect: a key can gain
withdrawal rights while an account sits paused, and resume is the moment it
starts routing partner capital again.

**Amending SL/TP does not stack orders (Q5d).** Only Bybit and Toobit amend TP/SL
in place (Toobit via `position/trading-stop`). On the other six, SL/TP are
ordinary reduce-only conditional orders, so `engine/executor.apply_sltp`
snapshots the live ones with `list_conditional_orders()`, places the new pair,
then cancels the snapshot.
Per exchange that snapshot is: Binance `openOrders` filtered to the stop
types → `DELETE .../order`; OKX `orders-algo-pending?ordType=oco` →
`cancel-algos`; KuCoin `stopOrders` → `DELETE /api/v1/orders/{id}`; Gate.io
`price_orders?status=open` → `DELETE .../price_orders/{id}`; Hyperliquid
`frontendOpenOrders` filtered to `isTrigger`+`reduceOnly` → `cancel`. Each
filters to *this platform's* protection orders, so a working order the partner
placed by hand is never cancelled. Every one of these paths is taken from a
vendored doc or SDK in `reference/`; none has been run against a live exchange,
so amend twice on testnet and count the resting orders.

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
request shape. Tracked as `questions.md` Q10.

**LBank spot is a round trip, and its market orders are asymmetric.** A market
**buy** carries the *quote* amount to spend in `price`; a market **sell**
carries the *base* quantity in `amount` (`api/spot.md`). `close_position` sells
back what this adapter bought, capped by the free balance — a fresh adapter
with no memory of the entry falls back to the whole free balance, so a partner
holding that asset outside the platform should know a close sells it. Spot
still has no SL/TP, so with the default Q5e policy a spot leg with SL/TP set
buys and immediately sells back; leave SL/TP blank on LBank spot.

## Before going live — checklist

1. Connect each account on **testnet** first (`testnet: true`) and run a full
   round trip: open → amend SL/TP → close.
2. Confirm the position size the exchange reports matches what the panel shows.
   This is where a contract-multiplier mistake surfaces.
3. Confirm SL/TP actually landed on the exchange, not just that the call
   returned 200.
4. **Amend SL/TP twice and count the open orders.** There must be exactly one
   stop and one take-profit left, at the newest prices. Two live stops means
   `list_conditional_orders`/`cancel_orders` did not match that exchange's
   shapes and the position is carrying a price the admin already replaced.
5. On exchanges with no permission endpoint, confirm by hand in the exchange
   dashboard that the key cannot withdraw.
6. Then one live trade at minimum size before any partner capital.
