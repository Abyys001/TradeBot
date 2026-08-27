# Security plan — every control a switch, nothing on the money path

**Status: built.** Written and implemented 2026-08-27. Every control below
exists, every switch is off by default, and the two guarantees this document
opens with are pinned by `backend/tests/test_security_scope.py` (nothing on the
money path imports this layer) and `backend/tests/test_security_cost.py` (with
everything off the query count is unchanged; with everything on an order routes
identically). It landed as one package rather than the phased order in §4 —
the phases are kept below because they record *why* each control is shaped the
way it is, and the two calendar items in §5 are still open.

**Where it lives:** `backend/apps/security/` — `flags.py` (the switches),
`middleware.py` (the three that see every request), `totp.py`, `stepup.py`,
`ratelimit.py`, `audit.py`, `csp.py`, and `management/commands/security_off.py`.
The panel is `frontend/components/security/` and `stores/security.ts`, rendered
by `pages/settings.vue`.

The brief was three sentences long and all three are constraints, not features:

1. **Everything optional.** Each control is an On/Off row on `/settings`, and
   off is the default. Nothing arrives switched on.
2. **Nothing may make the panel slower.** This platform's whole reason to exist
   is that one click reaches N exchanges inside `FANOUT_TIMEOUT_SECONDS`. A
   security control that adds a query, a lock, or a round trip to that path is
   a loss dressed as a gain.
3. **Nothing may change how the app works.** With every switch off, the code
   that runs is the code that runs today, instruction for instruction.

Everything below is designed backwards from those three.

---

## 0. The risk that actually costs money here

It is not a break-in. It is **the admin locked out of a panel that is holding
live positions.**

Turn on a second factor, lose the phone, and the position that needed closing
at 03:00 stays open. Turn on an IP allowlist from an office and go home to a
different ISP. That failure is one toggle away and it costs real capital, where
a hardened login mostly saves reputation. So the lockout escapes are built
**first**, before the first switch exists:

| Escape | Where |
|---|---|
| `SECURITY_FEATURES=off` env pin | Master off. Overrides every stored flag, cannot be set from a browser — the mirror image of `STOP_ALL`, which cannot be *cleared* from a browser. |
| `python manage.py security_off [--flag NAME]` | Clears one flag or all of them from a shell on the box. The documented recovery. |
| Recovery codes | Ten single-use codes, shown once at enrolment. **The second factor cannot be armed until the admin has confirmed they are stored.** |
| Self-lockout guard on the IP allowlist | The requesting IP is added automatically; an empty list means the control is off, never "deny all". |
| `docs/deploy.md` runbook section | The lockout drill, written down before it is needed. |

`STOP_ALL` stays reachable while locked out — the halt is the thing you need
most when you cannot get in, so it is exempt from step-up and from the
allowlist. Say that in one line in the runbook and pin it with a test.

---

## 1. The mechanism — one row, one cache key, one struct

`/settings` today is honest about a distinction worth keeping (its own header
comment says so): the halt and the profit split are **live**, and the execution
policy is **read-only**, because a UI that appeared to change `.env` without
changing the deployment would be lying. Security switches have to be genuinely
live, so they need the halt's mechanism, not the policy's.

**`apps/security/flags.py`** — modelled on `apps/trading/killswitch.py`:

- A `SecurityPolicy` singleton row, one `BooleanField` per control.
- **One** cache key holding the whole struct — not one key per flag. A page
  that reads eight flags does one cache hit, not eight.
- Invalidated on save, TTL 300s behind that, so every worker sees a flip at
  once when the cache is Redis.
- Failure direction is the opposite of the kill switch's: a DB error resolves
  every flag to **off**. The kill switch fails to *halted* because trading
  other people's capital on a guess is the wrong side. Here the wrong side is
  locking the admin out of a live book on a guess.
- Synchronous, like `killswitch` — called from async code via `sync_to_async`,
  never on the event loop.

**Off means not executed, not executed-and-discarded.** Every control is
guarded at its earliest point: middleware returns before doing work, decorators
short-circuit before the first `await`. A flag that is off costs one dict
lookup on an already-cached struct.

### The boundary, enforced by a test

`apps/engine/`, `apps/trading/fanout.py`, `apps/trading/services.py`,
`apps/trading/sizing.py` and `apps/pine/` **may not import `apps.security`**.
Pinned the way `tests/test_pine_purity.py` pins the Pine engine's stdlib-only
rule — an import test, not a code review habit.

Every control in this plan lives on the **login, session, or admin-write**
path. None sits between the admin's click and the exchange.

### The performance budget, measured not asserted

`tests/test_security_cost.py` measures three claims, and they are three
different claims rather than one:

- **Off costs nothing.** A request's query count with every switch off is the
  same as with the middleware removed from `MIDDLEWARE` entirely. Not a fixed
  number written into the test — the baseline is measured both ways in the same
  run, so it stays true as the endpoint underneath it changes.
- **On costs nothing on the routing path.** With every control armed and both
  limiters set to fire on the next request, `/api/trading/orders/open/`,
  `close/` and `stop-all/` behave exactly as they do with none — step-up and the
  write limiter skip them by prefix, and the allowlist exempts the halt by name.
- **On costs one session write per request, everywhere else.** That is
  `idle_timeout` asking Django to move the session's deadline forward: one
  `UPDATE django_session`, and the test asserts it is exactly one write and
  names it. It is the only per-request write this layer can add, and pinning
  its price is what stops a second one appearing unnoticed.

The fan-out timing assertions that already exist run unchanged under both.

---

## 2. The controls

Grouped as `/settings` will group them. Every row: a switch, a one-line
description of what turning it on *changes for the admin*, and — where it can
lock someone out — the escape named inline rather than buried in docs.

### A. Login (default off, each independent)

| # | Control | What it costs when on | Lockout risk |
|---|---|---|---|
| A1 | **Second factor (authenticator app, TOTP)** — `pyotp`, ~6 lines of verify. | One HMAC on `/auth/login/`. Zero elsewhere. | **Yes** → recovery codes, `security_off`. |
| A2 | **Remember this browser** — signed cookie, so A1 is asked once per device per N days. | One signature check on login. | No (fails closed to asking A1). |
| A3 | **Login rate limit** — N failures per IP+username in a cache window, then a cooling-off. | 1–2 cache ops **on `/auth/login/` only**. | Self-clearing; window is short by default. |
| A4 | **Notify on new device or new IP** — writes an existing `Notification`. | One insert, on an unrecognised login only. Reuses `NotificationCenter`; no new UI. | No. |
| A5 | **Idle timeout / absolute session age** — a session unused for N minutes, or older than N days, ends. | **One session write per request** — the plan assumed zero, and it is not. Django itself enforces the window once `set_expiry` moves the deadline, which is the reason to use it rather than keep a second clock, but the write is real. It is the only per-request cost in this layer, it happens only while this one switch is on, and `test_security_cost.py` names it. | Mild — you sign in again. |
| A6 | **One browser at a time** — signing in ends other sessions. | One update on login. | Real, and peculiar to this platform: the login is *shared*, so this evicts the other participant. Ships off, with that sentence next to the switch. |
| A7 | **IP allowlist** | One set membership test in middleware, on panel routes only. | **Highest.** Requesting IP auto-added; empty means off. |

A7 aside, none of these touches a request that is not a login.

**Not doing: SMS.** Higher friction than an authenticator app and weaker than
one — SIM swap defeats it. It would be the only control here that is worse on
both axes at once.

**Session revoke** is not a switch: it is a button per row in
`components/dashboard/Sessions.vue`, which already lists every browser holding
the login with device, address and last-seen. The list exists; ending a row
from it is the missing verb, and it is strictly an addition.

### B. Hardening (changes no login)

| # | Control | Cost | Note |
|---|---|---|---|
| B1 | **Content-Security-Policy**, report-only → enforce as two settings of one switch. | A constant header string. | A switch because CSP and Nuxt's inline styles need a real pass; report-only first is the whole point. |
| B2 | **Step-up re-auth on dangerous writes** — rotating a credential, deleting a connection, editing the profit split, arming a bot for live. | One password check, on those endpoints only. | Deliberately **excludes** order routing, close, amend and `STOP_ALL`. Asking for a password mid-trade is a loss, not a control. |
| B3 | **Security audit log** — `SecurityEvent`, append-only: logins, failures, flag flips, credential decrypt-for-use, step-up prompts. | One insert per event; none of these events is on a per-order path. | The `LedgerEvent` pattern (`apps/accounts/bookkeeping.py`) applied to access instead of money — actor, before, after. |
| B4 | **Rate limit on admin writes** (not routing). | Cache ops on those routes. | Same exclusion as B2, for the same reason. |

### C. Build-time only — no switch, because there is nothing to switch

These run in CI and never in the running app, so their runtime cost is exactly
zero and "optional" does not apply. Recommend all on, permanently:

- **`bandit`** and **`semgrep`** over `backend/` — the credential handling in
  `apps/core/crypto.py` and the adapters is precisely what pattern SAST is good
  at.
- **`pip-audit`** in CI + **Dependabot** — this stack pins `cryptography`,
  `httpx`, `websockets` and eight exchange integrations.
- **`gitleaks` as a pre-commit hook** — the standing invariant is *no key
  material in `reference/`, fixtures, tests, or scratch files*. A hook enforces
  what a rule currently only states.
- **`trivy`** on the production images.

Built as `.github/workflows/security.yml` (four jobs: `gitleaks`, `bandit`,
`pip-audit`, `trivy`), `.gitleaks.toml`, `.pre-commit-config.yaml`, and
`.github/dependabot.yml`. There was no CI in this repository before; these are
the first workflows in it.

**What the first run found, and what it means.** `bandit -ll` came back clean
after one annotation: `apps/exchanges/lbank.py` canonicalises its parameters to
an MD5 digest before signing, which is LBank's scheme rather than a choice —
the secret and the strength are in the HMAC-SHA256 around it, and a stronger
digest there produces a signature the exchange rejects. It carries a `# nosec
B324` with that reasoning; it is the only one in the tree.

`pip-audit` found real advisories, and clearing them is **not** part of this
layer — it is a dependency upgrade on a stack that routes live capital, which
is the admin's call rather than a side effect of adding the job that found it.
Three were closed here because they are in-line patch bumps and the full suite
was re-run against them: `Django 5.1.5 → 5.1.15`, `daphne 4.1.2 → 4.2.2`,
`python-dotenv 1.0.1 → 1.2.2`. What is left needs a deliberate upgrade:

| Package | Pinned | Needs | Why it is not done here |
|---|---|---|---|
| `django` | 5.1.15 | 5.2.16+ | A minor-version upgrade. Supported path, but it is a release to plan, not a line to edit. |
| `cryptography` | 44.0.0 | 50.0.0 | Six majors, and it is `apps/core/crypto.py` — the Fernet vault every API key is encrypted with. The Fernet API is stable across all of them; the point is that this is the one dependency that must be verified deliberately, not bumped in passing. |
| `pyopenssl` | 25.1.0 (transitive) | 26.0.0 | Moves with `cryptography`. |
| `twisted` | 25.5.0 (transitive) | 26.4.0 | Already satisfied by `daphne 4.2.2` on a fresh resolve. |

The job is `--strict`, so it stays red until those are done. That is the
correct signal: a dependency audit that passes while the advisories stand is
worse than no audit.

One repo-specific warning worth writing down: this working tree is one
`.env` away from live trading credentials. **Do not install auto-updating
third-party agent plugins or MCP servers into it.** Demonstrated attacks in
2026 (dependency-hijack via a marketplace skill; hook-based approval bypass)
run with full user permissions and update silently. Official and first-party
vendor tooling only, and read the diff.

---

## 3. What the Settings page becomes

A new **Security** section, placed after Preferences — the halt keeps the top
of the page, because when it is wanted it is wanted fast.

```
Security                                        [ 3 of 11 on ]
─────────────────────────────────────────────────────────────
  Sign-in
    Second factor (authenticator app)               ( ) Off
      └ not enrolled — enrol before this can be armed
    Remember this browser for 30 days               ( ) Off
    Limit failed sign-in attempts                   (•) On
    Notify me when a new device signs in            (•) On
    End sessions idle for 8 hours                   (•) On
    Only one browser signed in at a time            ( ) Off
      └ the login is shared — this signs the other person out
    Restrict sign-in to known addresses             ( ) Off
      └ lock-out risk. Recovery: manage.py security_off

  Hardening
    Content-Security-Policy          ( ) Off  ( ) Report  ( ) On
    Ask for the password again before key changes   ( ) Off
    Keep a security audit log                       ( ) Off
─────────────────────────────────────────────────────────────
  Every switch here is off by default and takes effect at once.
  None of them runs while an order is being routed.
```

That last line is the page's contract with the person reading it, and §1's
import test and cost test are what make it true rather than reassuring.

---

## 4. Order of work

| Phase | What | Why here |
|---|---|---|
| 0 | `flags.py`, `SecurityPolicy`, `security_off`, `SECURITY_FEATURES` pin, the import test, the query-count test, the empty Security section rendering zero rows. | The escapes and the guarantees exist **before** the first control that can lock anyone out. Ships with no behaviour change at all. |
| 1 | A3, A4, A5 — rate limit, new-device notice, idle timeout. | Nothing here can lock the admin out, and A5 costs literally nothing. Cheapest real gain in the plan. |
| 2 | C entirely — CI tooling. | Independent of every other phase; no runtime surface. Done; see the note under §2 C for what its first run found. |
| 3 | B3 audit log, then B2 step-up. | The log first, so the step-up's own behaviour is visible from day one. |
| 4 | A1 + A2 together. | A second factor without "remember this browser" is the version that gets switched back off in a week. Never ship A1 alone. |
| 5 | B1 CSP in report-only, read the reports, then enforce. | |
| 6 | A6, A7. | The two with real lock-out or real social cost. Last, deliberately. |

---

## 5. Open questions

Appended to `questions.md` as **Q31** and **Q32**; numbering continues from
Q30.

- **Q31 — do passkeys replace the shared password, or sit beside it?** Passkeys
  are the strongest and *least* annoying second factor available, and A1/A2
  exist partly as the stepping stone to them. But this platform's access model
  is deliberate: **one** shared staff login, and the access list is
  `PanelSession` rows — one per browser, in `components/dashboard/Sessions.vue`.
  A passkey is per-device by construction, so adopting it either (a) makes each
  participant enrol their own key against the same account, which is strictly
  better and needs no new model, or (b) becomes an argument for per-person
  accounts, which is a different product decision with consequences for
  `visibility.py` and the audit log. (a) is buildable now; (b) is the admin's
  call.
- **Q32 — is a WAF in front of the panel worth a hop on `/ws/`?** Caddy in
  `docker-compose.prod.yml` short-circuits `/ws/*` straight to Channels
  precisely to save a hop, and the top bar shows that latency. A proxying WAF
  puts the hop back. Fronting HTTP while leaving the socket direct is the
  obvious compromise, and it is the admin's call whether that is worth the
  split configuration.
