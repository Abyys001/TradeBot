<script setup lang="ts">
/**
 * Manual control — the tab for when TradingView and the bot disagree (Q41).
 *
 * The bot was stopped when the signal fired, the feed was repairing a gap, a
 * bar arrived late. The chart says long and the platform is flat, and waiting
 * for the *next* signal means sitting out the trade the strategy is in. So:
 * two buttons, and above them everything a decision needs.
 *
 * Three rules shape the layout.
 *
 *   **The verdict comes first.** The page opens with one line — aligned, or
 *   the exact way the two differ — because that is the question the operator
 *   came with. Everything under it is the evidence for that line.
 *
 *   **Nothing is recomputed here.** The PnL, the totals, the eligible-account
 *   count and the divergence itself all arrive from the server, priced by the
 *   same function the positions panel uses. A browser holding a second opinion
 *   about what is held is how two screens start disagreeing about a live book.
 *
 *   **A refusal is an answer.** A press that was not routed comes back with a
 *   code and a sentence; both are shown in place, and nothing is retried
 *   silently.
 */
const props = defineProps<{ botId: number }>()

const { t, te } = useI18n()
const api = useApi()
const live = useLiveStore()
const { money, qty, pct, signed, dateTime } = useFormat()

const desk = ref<BotDesk | null>(null)
const loading = ref(true)
const error = ref('')
/** The verb in flight. One press at a time — see `press()`. */
const sending = ref<'' | 'open_long' | 'open_short' | 'close'>('')
const result = ref<{ tone: 'ok' | 'signal'; text: string } | null>(null)
/** Which button the confirm step is waiting on. Market orders are one click
 *  from a live book, so the second click is the one that sends. */
const confirming = ref<'' | 'open_long' | 'open_short' | 'close'>('')

async function load(quiet = false) {
  if (!quiet) loading.value = true
  try {
    desk.value = await api.botDesk(props.botId)
    error.value = ''
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

/**
 * A code the server sent, in the reader's language — or the server's own
 * sentence when there is no key for it.
 *
 * The risk gate's codes are open-ended (`outside_window`, a `StopReason`, a
 * cap that was hit), so the panel translates the ones it knows and shows the
 * server's English for the rest. Printing a raw key would be worse than either.
 */
function say(prefix: string, code: string, fallback: string): string {
  const key = `bots.desk.${prefix}.${code}`
  if (te(key)) return t(key)
  return fallback || code
}

/**
 * Send one instruction, then re-read.
 *
 * The re-read is not optional: a press changes the position, the balances and
 * the hold-off state at once, and a panel showing the old three beside a new
 * confirmation is the screen that gets pressed twice.
 */
async function press(verb: 'open_long' | 'open_short' | 'close') {
  if (confirming.value !== verb) {
    confirming.value = verb
    return
  }
  confirming.value = ''
  sending.value = verb
  result.value = null
  try {
    const answer = await api.interveneBot(props.botId, verb)
    result.value = {
      tone: answer.ok ? 'ok' : 'signal',
      text: say('result', answer.code, answer.detail),
    }
  } catch (e: any) {
    result.value = {
      tone: 'signal',
      text: e?.data?.code
        ? say('refused', e.data.code, e.data.detail)
        : errorMessage(e),
    }
  } finally {
    sending.value = ''
    await load(true)
  }
}

const divergence = computed(() => desk.value?.divergence.code ?? 'unknown')
const held = computed(() => desk.value?.position.trade ?? null)
const totals = computed(() => desk.value?.position.totals ?? null)
const pnl = computed(() => Number(totals.value?.pnl ?? NaN))

/** Amber for a difference, quiet green for agreement. A colour per state, and
 *  `unknown` is not "fine" — it is a bot with nothing to compare against. */
const TONE: Record<string, 'ok' | 'signal' | 'neutral'> = {
  aligned: 'ok',
  strategy_wants_in: 'signal',
  strategy_wants_out: 'signal',
  side_mismatch: 'signal',
  unknown: 'neutral',
}

let timer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  void load()
  // Faster than the activity tab's thirty seconds: this one carries a live
  // PnL and a position the operator is deciding about right now.
  timer = setInterval(() => load(true), 5_000)
})
watch(() => props.botId, () => load())
// A bar or a routed action changes the answer this tab gives, so the socket
// re-reads it rather than leaving the operator on a five-second-old verdict.
watch(
  () => [live.botBars[props.botId]?.at, live.botActions[props.botId]?.at],
  () => load(true),
)
onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <div class="space-y-4">
    <p v-if="error" class="alert px-3 py-2.5 text-xs">{{ error }}</p>
    <div v-if="loading && !desk" class="space-y-3">
      <div class="skeleton h-24" />
      <div class="skeleton h-40" />
    </div>

    <template v-else-if="desk">
      <!-- The verdict, and the two buttons that act on it. One card, because
           reading the difference and acting on it is one thought. -->
      <UiCard :tone="TONE[divergence] === 'signal' ? 'signal' : 'default'">
        <template #header>
          <div class="flex items-center gap-2 flex-wrap">
            <UiBadge :tone="TONE[divergence] === 'ok' ? 'ok' : TONE[divergence] === 'signal' ? 'signal' : 'neutral'">
              {{ t(`bots.desk.divergence.${divergence}`) }}
            </UiBadge>
            <span class="num text-xs text-ink-muted">
              {{ desk.bot.symbol }} · {{ desk.bot.interval }} · {{ desk.bot.leverage }}×
            </span>
            <span v-if="desk.bot.dry_run" class="chip border-line text-ink-muted">
              {{ t('bots.dryRun') }}
            </span>
          </div>
        </template>

        <div class="space-y-3">
          <p class="text-xs text-ink-muted leading-relaxed">
            {{ t(`bots.desk.divergenceBody.${divergence}`, {
              wants: desk.divergence.wants ? t(`side.${desk.divergence.wants}`) : t('bots.flat'),
              holds: desk.divergence.holds ? t(`side.${desk.divergence.holds}`) : t('bots.flat'),
            }) }}
          </p>

          <!-- What the strategy last said, in its own words. `entry_signal`
               matters: "it wants to be long" and "it asked to enter on this
               bar" are different facts, and only the second is a signal. -->
          <dl v-if="desk.strategy" class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
            <div>
              <dt class="text-ink-faint">{{ t('bots.desk.lastSignal') }}</dt>
              <dd class="num mt-0.5">
                {{ desk.strategy.desired_side ? t(`side.${desk.strategy.desired_side}`) : t('bots.flat') }}
                <span v-if="desk.strategy.entry_signal" class="text-brand">
                  · {{ t('bots.desk.entrySignal') }}
                </span>
              </dd>
            </div>
            <div>
              <dt class="text-ink-faint">{{ t('bots.desk.lastBar') }}</dt>
              <dd class="num mt-0.5">
                {{ dateTime(new Date(desk.strategy.bar_time * 1000).toISOString()) }}
              </dd>
            </div>
            <div>
              <dt class="text-ink-faint">{{ t('bots.desk.barClose') }}</dt>
              <dd class="num mt-0.5">{{ money(desk.strategy.close) }}</dd>
            </div>
            <div>
              <dt class="text-ink-faint">{{ t('bots.desk.mark') }}</dt>
              <dd class="num mt-0.5">
                {{ money(desk.mark?.price) }}
                <span v-if="desk.mark && !desk.mark.live" class="text-signal">
                  {{ t('terminal.feedDown') }}
                </span>
                <span v-else-if="!desk.mark" class="text-signal">{{ t('bots.desk.noFeed') }}</span>
              </dd>
            </div>
          </dl>
          <p v-else class="text-xs text-ink-faint">{{ t('bots.desk.noBars') }}</p>

          <p v-if="desk.strategy?.reason" class="text-tick text-ink-faint leading-relaxed">
            “{{ desk.strategy.reason }}”
          </p>

          <!-- The buttons. Two clicks: the first arms, the second sends — a
               market order across every partner account is not an undo. -->
          <div class="flex flex-wrap gap-2 pt-1">
            <button
              class="btn bg-long text-ink-invert btn-sm"
              :disabled="!desk.can.open || sending !== '' || desk.divergence.holds === 'long'"
              @click="press('open_long')"
            >
              {{ sending === 'open_long' ? t('ticket.sending')
                : confirming === 'open_long' ? t('bots.desk.confirm')
                : t('bots.desk.open_long') }}
            </button>
            <button
              class="btn bg-short text-ink-invert btn-sm"
              :disabled="!desk.can.open || sending !== '' || desk.divergence.holds === 'short'"
              @click="press('open_short')"
            >
              {{ sending === 'open_short' ? t('ticket.sending')
                : confirming === 'open_short' ? t('bots.desk.confirm')
                : t('bots.desk.open_short') }}
            </button>
            <button
              class="btn-danger btn-sm"
              :disabled="!desk.can.close || sending !== ''"
              @click="press('close')"
            >
              {{ sending === 'close' ? t('ticket.sending')
                : confirming === 'close' ? t('bots.desk.confirm')
                : t('bots.desk.close') }}
            </button>
            <button
              v-if="confirming"
              class="btn-ghost btn-sm"
              @click="confirming = ''"
            >
              {{ t('common.cancel') }}
            </button>
          </div>

          <p
            v-if="result"
            class="text-xs leading-relaxed"
            :class="result.tone === 'ok' ? 'text-ok' : 'alert px-2.5 py-2'"
          >
            {{ result.text }}
          </p>

          <!-- Why a button is dead, said here rather than discovered by
               pressing it. -->
          <p v-if="desk.can.code" class="text-xs text-ink-faint leading-relaxed">
            {{ say('refused', desk.can.code, '') }}
          </p>
          <p v-else-if="!desk.capital.eligible" class="alert px-2.5 py-2 text-xs leading-relaxed">
            {{ t('bots.desk.noEligibleAccounts') }}
          </p>

          <!-- Q41's guard. An operator who closed by hand and sees nothing
               reopen deserves to know which of the two it is. -->
          <p v-if="desk.hold_off" class="text-xs text-ink-muted leading-relaxed">
            {{ t('bots.desk.holdOff', { side: t(`side.${desk.hold_off.side}`) }) }}
          </p>

          <p class="text-tick text-ink-faint leading-relaxed">
            {{ t('bots.desk.samePathNote') }}
          </p>
        </div>
      </UiCard>

      <!-- The money, four tiles. Total capital and free balance are over the
           accounts this bot can actually reach — a total counting an account
           it cannot route to is a number the next entry will not be sized
           from. -->
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <UiStat
          :label="t('bots.desk.equity')"
          :value="money(desk.capital.equity)"
          :sub="t('bots.desk.acrossN', { n: desk.capital.eligible })"
          icon="wallet"
        />
        <UiStat
          :label="t('bots.desk.available')"
          :value="money(desk.capital.available)"
          :sub="desk.capital.asset"
          icon="wallet"
        />
        <UiStat
          :label="t('position.size')"
          :value="totals ? qty(totals.qty) : '—'"
          :sub="totals ? `${money(totals.margin)} ${t('position.margin')}` : t('bots.flat')"
          icon="gauge"
        />
        <UiStat
          :label="t('position.pnl')"
          :value="totals && totals.pnl !== null ? signed(totals.pnl) : '—'"
          :sub="totals && totals.roe_pct !== null ? pct(totals.roe_pct) : ''"
          :tone="Number.isNaN(pnl) ? 'default' : pnl >= 0 ? 'long' : 'short'"
          icon="trend"
        />
      </div>

      <div class="grid gap-4 xl:grid-cols-2">
        <!-- The position, per account. Same rows the positions panel draws,
             from the same server arithmetic. -->
        <UiCard :title="t('bots.desk.position')" flush>
          <div v-if="!held" class="p-4">
            <UiEmpty icon="gauge" :title="t('bots.flat')" :body="t('bots.desk.flatBody')" />
          </div>
          <div v-else>
            <dl class="grid grid-cols-2 sm:grid-cols-4 gap-3 px-4 py-3 border-b border-line text-xs">
              <div>
                <dt class="text-ink-faint">{{ t('bots.desk.side') }}</dt>
                <dd class="mt-0.5" :class="held.side === 'long' ? 'text-long' : 'text-short'">
                  {{ t(`side.${held.side}`) }}
                </dd>
              </div>
              <div>
                <dt class="text-ink-faint">{{ t('position.entry') }}</dt>
                <dd class="num mt-0.5">{{ money(held.admin_entry_price) }}</dd>
              </div>
              <div>
                <dt class="text-ink-faint">SL / TP</dt>
                <dd class="num mt-0.5">
                  {{ held.sl_pct ? `${held.sl_pct}%` : '—' }} /
                  {{ held.tp_pct ? `${held.tp_pct}%` : '—' }}
                </dd>
              </div>
              <div>
                <dt class="text-ink-faint">{{ t('bots.desk.opened') }}</dt>
                <dd class="num mt-0.5">{{ dateTime(held.opened_at) }}</dd>
              </div>
            </dl>
            <ul class="divide-y divide-line">
              <li
                v-for="leg in desk.position.legs"
                :key="leg.account"
                class="px-4 py-2.5 flex items-center gap-3 text-xs"
              >
                <UiBadge :tone="leg.ok ? 'ok' : 'short'">{{ leg.account_label }}</UiBadge>
                <span class="num text-ink-muted">{{ qty(leg.qty) }}</span>
                <span class="num text-ink-muted">@ {{ money(leg.entry_price) }}</span>
                <span
                  class="num ms-auto"
                  :class="Number(leg.pnl) >= 0 ? 'text-long' : 'text-short'"
                >
                  {{ leg.pnl === null ? '—' : signed(leg.pnl) }}
                </span>
              </li>
            </ul>
          </div>
        </UiCard>

        <!-- The bars behind the verdict. Not a chart — the chart tab is a
             chart — but enough to see where the last entry signal was and
             what the script has said since. -->
        <UiCard :title="t('bots.desk.signals')" flush>
          <UiEmpty
            v-if="!desk.strategy || !desk.strategy.bars.length"
            icon="history"
            :title="t('bots.desk.noBars')"
            :body="t('bots.desk.noBarsBody')"
          />
          <table v-else class="w-full text-xs">
            <thead class="text-ink-faint">
              <tr class="border-b border-line">
                <th class="text-start font-normal px-4 py-2">{{ t('bots.desk.lastBar') }}</th>
                <th class="text-start font-normal px-2 py-2">{{ t('bots.desk.side') }}</th>
                <th class="text-end font-normal px-2 py-2">{{ t('bots.desk.barClose') }}</th>
                <th class="text-start font-normal px-4 py-2">{{ t('bots.desk.why') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="bar in desk.strategy.bars" :key="bar.bar_time" class="border-b border-line/60">
                <td class="num px-4 py-1.5 text-ink-muted">
                  {{ dateTime(new Date(bar.bar_time * 1000).toISOString()) }}
                </td>
                <td class="px-2 py-1.5">
                  <span :class="bar.side === 'long' ? 'text-long' : bar.side === 'short' ? 'text-short' : 'text-ink-faint'">
                    {{ bar.side ? t(`side.${bar.side}`) : t('bots.flat') }}
                  </span>
                  <span v-if="bar.entry_signal" class="text-brand"> ·&nbsp;{{ t('bots.desk.entrySignal') }}</span>
                </td>
                <td class="num px-2 py-1.5 text-end">{{ money(bar.close) }}</td>
                <td class="px-4 py-1.5 text-ink-faint truncate max-w-[16rem]">
                  {{ bar.exit_reason || bar.reason }}
                </td>
              </tr>
            </tbody>
          </table>
        </UiCard>
      </div>

      <!-- What was actually sent, most recent first. The activity tab is the
           full log; this is the tail, so a press and its legs are on the same
           screen as the button that made them. -->
      <UiCard :title="t('bots.desk.recent')" flush>
        <UiEmpty
          v-if="!desk.actions.length"
          icon="history"
          :title="t('bots.noActions')"
          :body="t('bots.noActionsBody')"
        />
        <ul v-else class="divide-y divide-line">
          <li v-for="action in desk.actions" :key="action.id" class="px-4 py-2.5 space-y-1">
            <div class="flex items-center gap-2 flex-wrap text-xs">
              <UiBadge :tone="action.action_type === 'shadow' ? 'neutral' : action.ok ? 'ok' : 'short'">
                {{ t(`bots.action.${action.action_type}`) }}
              </UiBadge>
              <UiBadge v-if="action.intent?.origin === 'manual'" tone="brand">
                {{ t('bots.desk.byHand') }}
              </UiBadge>
              <UiBadge v-if="action.intent?.held_off" tone="signal">
                {{ t('bots.desk.heldOff') }}
              </UiBadge>
              <span v-if="action.side" :class="action.side === 'long' ? 'text-long' : 'text-short'">
                {{ t(`side.${action.side}`) }}
              </span>
              <span class="num text-ink-muted">{{ dateTime(action.created_at) }}</span>
              <span v-if="action.error" class="text-short">{{ action.error }}</span>
            </div>
            <p v-if="action.reason" class="text-tick text-ink-faint">{{ action.reason }}</p>
          </li>
        </ul>
      </UiCard>
    </template>
  </div>
</template>
