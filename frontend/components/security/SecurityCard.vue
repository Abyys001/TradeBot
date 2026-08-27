<script setup lang="ts">
/**
 * The security layer as one card: a switch per control, every one off until
 * somebody turns it on.
 *
 * Three rules shape the layout, and all three come from `docs/security-plan.md`:
 *
 *   1. **Off is the default and it costs nothing.** So the card leads with how
 *      many controls are on, not with an exhortation to turn them on. A panel
 *      that nags is a panel whose warnings stop being read.
 *   2. **Each switch owns its own settings.** The tunables appear underneath
 *      the row that uses them and only while it is on — a lockout window with
 *      nothing to lock out is a number nobody can act on.
 *   3. **A refusal is an answer, not a failure.** "Enrol an authenticator app
 *      first" is what the second-factor row says instead of springing back.
 *
 * The one thing the operator can lose here is their own access, so the two
 * rows that could do it — the second factor and the address allowlist — carry
 * their escape in the row: enrolment must be finished before the first can be
 * armed, and the server adds the caller's own address to the second.
 *
 * None of it is on the order-routing path; the halt stays reachable from an
 * address the allowlist does not know.
 */
const { t, te } = useI18n()
const { dateTime } = useFormat()
const security = useSecurityStore()

const enrolling = ref(false)
const disabling = ref(false)
const disablePassword = ref('')
const disableError = ref('')

/** The last change the operator asked for, replayed once step-up is granted. */
const retry = ref<{ changes: Partial<SecurityPolicy>; key: string } | null>(null)

onMounted(() => security.load())

const policy = computed(() => security.policy)
const locked = computed(() => !security.loading && !security.available)

/**
 * The rows, in the server's own order. `switches` comes from the API so a new
 * control does not need a second list here to be remembered.
 */
type Row = {
  name: SecuritySwitch
  /** Why this row cannot be armed yet, if it cannot. */
  blocked?: string
  icon: IconName
}

const ICONS: Record<string, IconName> = {
  two_factor: 'lock',
  trusted_devices: 'key',
  login_rate_limit: 'clock',
  new_device_notice: 'bell',
  idle_timeout: 'clock',
  single_session: 'accounts',
  ip_allowlist: 'globe',
  step_up: 'shield',
  audit_log: 'logs',
  admin_write_rate_limit: 'gauge',
}

const rows = computed<Row[]>(() =>
  security.switches.map((name) => ({
    name,
    icon: ICONS[name] ?? 'shield',
    blocked:
      name === 'two_factor' && !security.twoFactorReady
        ? t('security.rows.two_factor.blocked')
        : name === 'trusted_devices' && !policy.value?.two_factor
          ? t('security.rows.trusted_devices.blocked')
          : undefined,
  })),
)

function isOn(name: SecuritySwitch): boolean {
  return Boolean(policy.value?.[name])
}

async function onToggle(row: Row, on: boolean) {
  if (on && row.blocked) return
  const changes = { [row.name]: on } as Partial<SecurityPolicy>
  retry.value = { changes, key: row.name }
  await security.save(changes, row.name)
}

/** A tunable, saved on blur rather than per keystroke — one write per edit. */
async function saveNumber(name: keyof SecurityPolicy, raw: string | number) {
  const value = Number(raw)
  if (!Number.isFinite(value) || value <= 0) return
  if (policy.value?.[name] === value) return
  const changes = { [name]: value } as Partial<SecurityPolicy>
  retry.value = { changes, key: String(name) }
  await security.save(changes, String(name))
}

const allowedIps = ref('')
watch(
  () => policy.value?.allowed_ips,
  (value) => (allowedIps.value = value ?? ''),
  { immediate: true },
)

async function saveAllowlist() {
  if (allowedIps.value === policy.value?.allowed_ips) return
  const changes = { ip_allowlist: true, allowed_ips: allowedIps.value }
  retry.value = { changes, key: 'allowed_ips' }
  await security.save(changes, 'allowed_ips')
}

const cspMode = computed({
  get: () => policy.value?.csp_mode ?? 'off',
  set: (mode: string) => {
    const changes = { csp_mode: mode } as Partial<SecurityPolicy>
    retry.value = { changes, key: 'csp_mode' }
    security.save(changes, 'csp_mode')
  },
})

const CSP_OPTIONS = computed(() =>
  (['off', 'report', 'enforce'] as const).map((value) => ({
    value,
    label: t(`security.csp.${value}`),
    tone: value === 'enforce' ? ('ok' as const) : value === 'report' ? ('signal' as const) : undefined,
  })),
)

/** After the password prompt: replay the click that raised it. */
async function afterStepUp() {
  if (!retry.value) return
  const { changes, key } = retry.value
  retry.value = null
  await security.save(changes, key)
}

async function forgetTrusted() {
  security.applyTotp(await useApi().forgetTrustedDevices())
}

async function disableTotp() {
  disableError.value = ''
  try {
    security.policy = await useApi().totpDisable(disablePassword.value)
    disabling.value = false
    disablePassword.value = ''
  } catch (e: unknown) {
    disableError.value = errorMessage(e)
  }
}

function rowHint(name: string) {
  const key = `security.rows.${name}.hint`
  return te(key) ? t(key) : ''
}
</script>

<template>
  <UiCard :title="t('security.title')" :hint="t('security.hint')" flush>
    <template #actions>
      <UiBadge v-if="locked" tone="neutral">{{ t('security.pinnedOff') }}</UiBadge>
      <UiBadge v-else :tone="security.activeCount ? 'ok' : 'neutral'" dot>
        {{ t('security.activeCount', { n: security.activeCount, total: security.switches.length }) }}
      </UiBadge>
    </template>

    <div v-if="security.loading" class="p-4 space-y-3">
      <div v-for="i in 6" :key="i" class="skeleton h-10" />
    </div>

    <template v-else>
      <!-- The environment pinned the layer off; every row below is inert and
           says so rather than moving and springing back. -->
      <p v-if="locked" class="px-4 py-3 text-xs text-ink-muted leading-relaxed border-b border-line">
        {{ t('security.pinnedOffBody') }}
      </p>

      <p v-if="security.error" class="px-4 py-2.5 alert text-xs rounded-none border-x-0 border-t-0">
        {{ security.error }}
      </p>

      <ul class="divide-y divide-line">
        <li v-for="row in rows" :key="row.name" class="px-4 py-3.5">
          <div class="flex items-start gap-3">
            <span
              class="mt-0.5 w-7 h-7 rounded-lg grid place-items-center shrink-0"
              :class="isOn(row.name) ? 'bg-ok-dim text-ok' : 'bg-raised text-ink-faint'"
            >
              <UiIcon :name="row.icon" :size="14" />
            </span>

            <div class="min-w-0 flex-1">
              <UiSwitch
                :model-value="isOn(row.name)"
                :label="t(`security.rows.${row.name}.label`)"
                :hint="rowHint(row.name)"
                :disabled="locked || Boolean(row.blocked && !isOn(row.name)) || security.saving === row.name"
                @update:model-value="onToggle(row, $event)"
              />

              <p v-if="row.blocked && !isOn(row.name)" class="text-xs text-signal mt-1.5">
                {{ row.blocked }}
              </p>

              <!-- Each switch's own settings, only while it is on. -->
              <div v-if="isOn(row.name)" class="mt-3 ps-0.5 border-s-2 border-line ps-3 space-y-3">
                <template v-if="row.name === 'two_factor'">
                  <div class="flex flex-wrap items-center gap-2 text-xs">
                    <UiBadge tone="ok" dot>
                      {{ t('security.totp.recoveryLeft', { n: policy?.totp.recovery_remaining ?? 0 }) }}
                    </UiBadge>
                    <button class="btn-ghost btn-sm" @click="enrolling = true">
                      {{ t('security.totp.replace') }}
                    </button>
                    <button class="btn-ghost btn-sm text-short" @click="disabling = true">
                      {{ t('security.totp.remove') }}
                    </button>
                  </div>
                </template>

                <template v-else-if="row.name === 'trusted_devices'">
                  <div class="flex flex-wrap items-end gap-3">
                    <UiField v-slot="{ id }" :label="t('security.fields.trusted_device_days')" class="w-32">
                      <input
                        :id="id"
                        class="field num"
                        inputmode="numeric"
                        :value="policy?.trusted_device_days"
                        @change="saveNumber('trusted_device_days', ($event.target as HTMLInputElement).value)"
                      />
                    </UiField>
                    <button class="btn-ghost btn-sm mb-0.5" @click="forgetTrusted">
                      {{ t('security.totp.forgetAll', { n: policy?.totp.trusted_devices ?? 0 }) }}
                    </button>
                  </div>
                </template>

                <template v-else-if="row.name === 'login_rate_limit'">
                  <div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
                    <UiField v-slot="{ id }" :label="t('security.fields.login_max_attempts')">
                      <input :id="id" class="field num" inputmode="numeric" :value="policy?.login_max_attempts"
                        @change="saveNumber('login_max_attempts', ($event.target as HTMLInputElement).value)" />
                    </UiField>
                    <UiField v-slot="{ id }" :label="t('security.fields.login_window_seconds')">
                      <input :id="id" class="field num" inputmode="numeric" :value="policy?.login_window_seconds"
                        @change="saveNumber('login_window_seconds', ($event.target as HTMLInputElement).value)" />
                    </UiField>
                    <UiField v-slot="{ id }" :label="t('security.fields.login_lockout_seconds')">
                      <input :id="id" class="field num" inputmode="numeric" :value="policy?.login_lockout_seconds"
                        @change="saveNumber('login_lockout_seconds', ($event.target as HTMLInputElement).value)" />
                    </UiField>
                  </div>
                </template>

                <template v-else-if="row.name === 'idle_timeout'">
                  <div class="grid grid-cols-2 gap-3">
                    <UiField v-slot="{ id }" :label="t('security.fields.idle_timeout_minutes')">
                      <input :id="id" class="field num" inputmode="numeric" :value="policy?.idle_timeout_minutes"
                        @change="saveNumber('idle_timeout_minutes', ($event.target as HTMLInputElement).value)" />
                    </UiField>
                    <UiField v-slot="{ id }" :label="t('security.fields.session_max_hours')">
                      <input :id="id" class="field num" inputmode="numeric" :value="policy?.session_max_hours"
                        @change="saveNumber('session_max_hours', ($event.target as HTMLInputElement).value)" />
                    </UiField>
                  </div>
                  <p class="text-[0.7rem] text-ink-faint leading-relaxed">
                    {{ t('security.fields.idleCost') }}
                  </p>
                </template>

                <template v-else-if="row.name === 'ip_allowlist'">
                  <UiField
                    v-slot="{ id }"
                    :label="t('security.fields.allowed_ips')"
                    :hint="t('security.fields.allowed_ipsHint')"
                  >
                    <textarea
                      :id="id"
                      v-model="allowedIps"
                      class="field num min-h-[5rem]"
                      spellcheck="false"
                      @blur="saveAllowlist"
                    />
                  </UiField>
                  <p class="text-[0.7rem] text-ink-faint leading-relaxed">
                    {{ t('security.fields.allowlistEscape') }}
                  </p>
                </template>

                <template v-else-if="row.name === 'step_up'">
                  <UiField v-slot="{ id }" :label="t('security.fields.step_up_grace_seconds')" class="w-40">
                    <input :id="id" class="field num" inputmode="numeric" :value="policy?.step_up_grace_seconds"
                      @change="saveNumber('step_up_grace_seconds', ($event.target as HTMLInputElement).value)" />
                  </UiField>
                  <p class="text-[0.7rem] text-ink-faint leading-relaxed">
                    {{ t('security.fields.stepUpScope') }}
                  </p>
                </template>

                <template v-else-if="row.name === 'admin_write_rate_limit'">
                  <UiField v-slot="{ id }" :label="t('security.fields.admin_write_max_per_minute')" class="w-40">
                    <input :id="id" class="field num" inputmode="numeric" :value="policy?.admin_write_max_per_minute"
                      @change="saveNumber('admin_write_max_per_minute', ($event.target as HTMLInputElement).value)" />
                  </UiField>
                  <p class="text-[0.7rem] text-ink-faint leading-relaxed">
                    {{ t('security.fields.writeLimitScope') }}
                  </p>
                </template>
              </div>

              <!-- Not yet enrolled: the row cannot be armed, so offer the thing
                   that would change that instead of only saying no. -->
              <button
                v-else-if="row.name === 'two_factor' && !security.twoFactorReady && !locked"
                class="btn-ghost btn-sm mt-2.5"
                @click="enrolling = true"
              >
                <UiIcon name="lock" :size="14" />
                {{ t('security.totp.enrol') }}
              </button>
            </div>
          </div>
        </li>

        <!-- CSP is three states, not two, so it is a segmented control rather
             than a switch: report-only is how it is meant to be introduced. -->
        <li class="px-4 py-3.5">
          <div class="flex items-start gap-3">
            <span
              class="mt-0.5 w-7 h-7 rounded-lg grid place-items-center shrink-0"
              :class="cspMode !== 'off' ? 'bg-ok-dim text-ok' : 'bg-raised text-ink-faint'"
            >
              <UiIcon name="layers" :size="14" />
            </span>
            <div class="min-w-0 flex-1">
              <p class="text-sm">{{ t('security.rows.csp_mode.label') }}</p>
              <p class="text-xs text-ink-muted mt-0.5 leading-relaxed">
                {{ t('security.rows.csp_mode.hint') }}
              </p>
              <div class="mt-2.5 max-w-xs">
                <UiSegmented v-model="cspMode" :options="CSP_OPTIONS" size="sm" />
              </div>
            </div>
          </div>
        </li>
      </ul>

      <p
        v-if="policy?.updated_at"
        class="px-4 py-2.5 text-[0.7rem] text-ink-faint border-t border-line"
      >
        {{ t('security.updated', { user: policy.updated_by || '—', when: dateTime(policy.updated_at) }) }}
      </p>
    </template>

    <SecurityTotpDialog v-model="enrolling" />
    <SecurityStepUpDialog @confirmed="afterStepUp" />

    <UiModal v-model="disabling" :title="t('security.totp.removeTitle')" size="sm">
      <form id="totp-disable" class="space-y-4" @submit.prevent="disableTotp">
        <p class="text-sm leading-relaxed">{{ t('security.totp.removeBody') }}</p>
        <UiField v-slot="{ id }" :label="t('login.password')">
          <input :id="id" v-model="disablePassword" type="password" class="field"
            autocomplete="current-password" required />
        </UiField>
        <p v-if="disableError" class="alert p-2.5 text-xs">{{ disableError }}</p>
      </form>
      <template #footer>
        <div class="flex gap-2 justify-end">
          <button class="btn-ghost" @click="disabling = false">{{ t('common.cancel') }}</button>
          <button class="btn-danger" type="submit" form="totp-disable" :disabled="!disablePassword">
            {{ t('security.totp.remove') }}
          </button>
        </div>
      </template>
    </UiModal>
  </UiCard>
</template>
