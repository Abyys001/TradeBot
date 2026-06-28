<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useStrategyStore } from '../../../stores/strategy'
import { useCredentialsStore } from '../../../stores/credentials'
import { useStrategyForm } from '../../../composables/useStrategyForm'
import StepCredential from './StepCredential.vue'
import StepStrategy from './StepStrategy.vue'
import StepRisk from './StepRisk.vue'
import StepDeploy from './StepDeploy.vue'

const emit = defineEmits<{ deployed: []; cancel: [] }>()

const { t } = useI18n()
const store = useStrategyStore()
const creds = useCredentialsStore()

const step = ref(0)
const credentialId = ref<number | null>(null)
const strategyId = ref(0)
const sf = useStrategyForm(strategyId)

const steps = [
  { key: 'step1', desc: 'step1Desc' },
  { key: 'step2', desc: 'step2Desc' },
  { key: 'step3', desc: 'step3Desc' },
  { key: 'step4', desc: 'step4Desc' },
]

const selectedCred = computed(() => creds.credentials.find((c) => c.id === credentialId.value) ?? null)
const strategy = computed(() => sf.selected.value)

const canNext = computed(() => {
  if (step.value === 0) return !!selectedCred.value?.is_active
  if (step.value === 1) return strategy.value?.validation_status === 'ok'
  return true
})

// keep strategy bound to the chosen credential
watch(credentialId, async (id) => {
  const s = strategy.value
  if (s && id && s.credential !== id) {
    await store.updateStrategy(s.id, { credential: id })
  }
})

async function ensureDraft() {
  if (strategyId.value) return
  const s = await store.createStrategy({
    name: 'Live Strategy',
    type: 'pine',
    credential: credentialId.value,
  })
  strategyId.value = s.id
}

async function next() {
  if (!canNext.value) return
  if (step.value === 0) await ensureDraft()
  if (step.value === 2) await sf.save()
  if (step.value < steps.length - 1) step.value += 1
}

function back() {
  if (step.value > 0) step.value -= 1
}
</script>

<template>
  <div class="mx-auto flex h-full w-full max-w-4xl gap-6 overflow-y-auto p-6">
    <!-- stepper rail -->
    <aside class="w-56 shrink-0">
      <div class="mb-5">
        <h2 class="text-base font-semibold text-zinc-100">{{ t('live.wizard.title') }}</h2>
        <p class="mt-1 text-xs text-zinc-500">{{ t('live.wizard.subtitle') }}</p>
      </div>
      <ol class="space-y-1">
        <li
          v-for="(s, i) in steps"
          :key="s.key"
          class="flex items-start gap-3 rounded-lg px-3 py-2.5"
          :class="i === step ? 'bg-zinc-800/60' : ''"
        >
          <span
            class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-medium"
            :class="i < step
              ? 'bg-emerald-600 text-white'
              : i === step
                ? 'bg-violet-600 text-white'
                : 'bg-zinc-800 text-zinc-500'"
          >
            {{ i < step ? '✓' : i + 1 }}
          </span>
          <div class="min-w-0">
            <div class="text-xs font-medium" :class="i === step ? 'text-zinc-100' : 'text-zinc-400'">
              {{ t(`live.wizard.${s.key}`) }}
            </div>
            <div class="mt-0.5 text-[10px] leading-tight text-zinc-600">{{ t(`live.wizard.${s.desc}`) }}</div>
          </div>
        </li>
      </ol>
      <button
        type="button"
        class="mt-4 text-xs text-zinc-500 hover:text-zinc-300"
        @click="emit('cancel')"
      >
        ← {{ t('health.cancel') }}
      </button>
    </aside>

    <!-- step content -->
    <section class="min-w-0 flex-1">
      <div class="rounded-xl border border-zinc-800 bg-zinc-900/40 p-6">
        <StepCredential v-if="step === 0" v-model:credential-id="credentialId" />
        <StepStrategy v-else-if="step === 1" :strategy-form="sf" />
        <StepRisk v-else-if="step === 2" :strategy-form="sf" />
        <StepDeploy
          v-else
          :strategy-form="sf"
          :credential-id="credentialId"
          @deployed="emit('deployed')"
        />
      </div>

      <div v-if="step < 3" class="mt-4 flex justify-between">
        <button
          type="button"
          class="rounded-lg border border-zinc-700 px-4 py-2 text-sm text-zinc-400 transition-colors hover:bg-zinc-800 disabled:opacity-40"
          :disabled="step === 0"
          @click="back"
        >
          {{ t('live.wizard.back') }}
        </button>
        <button
          type="button"
          class="rounded-lg bg-violet-700 px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-violet-600 disabled:opacity-40"
          :disabled="!canNext"
          @click="next"
        >
          {{ t('live.wizard.next') }}
        </button>
      </div>
    </section>
  </div>
</template>
