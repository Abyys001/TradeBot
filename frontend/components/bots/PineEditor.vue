<script setup lang="ts">
/**
 * The Pine editor: a textarea, a gutter, and a highlight layer under it.
 *
 * Not CodeMirror, for the same reason there is no icon package and no charting
 * framework beyond the seam — a code editor is ~250KB of dependency for four
 * behaviours this needs, and the panel has to build on a machine with no CDN
 * reachable. What it actually needs is small and known:
 *
 *   - line numbers, so an error at "line 14, column 9" can be found;
 *   - a Tab that inserts four spaces, because Pine is whitespace-significant
 *     and a literal tab makes the script indent differently here than on
 *     TradingView (the lexer counts a tab as four columns; the editor should
 *     never create the ambiguity in the first place);
 *   - auto-indent after a line that opens a block, for the same reason;
 *   - the validator's errors marked on the lines they belong to.
 *
 * Highlighting is a regex pass over a subset the platform already defines as
 * data. It is a reading aid, not a parser — `apps/pine/` is the parser, and
 * anything this layer gets wrong shows up as a colour, never as a behaviour.
 */
const props = withDefaults(
  defineProps<{
    modelValue: string
    diagnostics?: PineDiagnostic[]
    readonly?: boolean
    minRows?: number
  }>(),
  { diagnostics: () => [], readonly: false, minRows: 18 },
)

const emit = defineEmits<{ 'update:modelValue': [string]; save: [] }>()

const area = ref<HTMLTextAreaElement | null>(null)
const scroller = ref<HTMLDivElement | null>(null)
const scrollTop = ref(0)
const caretLine = ref(1)

const lines = computed(() => props.modelValue.split('\n'))

/** line number → the worst diagnostic on it. An error outranks a warning. */
const marks = computed(() => {
  const out = new Map<number, PineDiagnostic>()
  for (const item of props.diagnostics) {
    const line = item.span?.line ?? 1
    const existing = out.get(line)
    if (!existing || (existing.kind === 'warning' && item.kind === 'error')) out.set(line, item)
  }
  return out
})

// --- highlighting -----------------------------------------------------------

const KEYWORDS =
  /\b(if|else|for|to|by|in|while|switch|break|continue|var|varip|and|or|not|true|false|na|import|export|type|method|enum|series|simple|const|int|float|bool|string|color)\b/
const NAMESPACES = /\b(ta|math|str|input|strategy|barstate|color|shape|location|size|plot|request|array|matrix|map|line|label|box|table)(?=\.)/
const BUILTINS =
  /\b(open|high|low|close|volume|hl2|hlc3|ohlc4|hlcc4|time|bar_index|last_bar_index|nz|fixnan|timestamp|dayofweek|hour|minute|second|year|month|dayofmonth|plot|plotshape|plotchar|hline|fill|bgcolor|alert|alertcondition)\b/

const escape = (text: string) =>
  text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

/**
 * One line, as spans. Comments and strings are taken first so a keyword inside
 * either is left alone — the only ordering that matters here.
 */
function paint(line: string): string {
  const comment = line.indexOf('//')
  let code = line
  let tail = ''
  if (comment >= 0 && !insideString(line, comment)) {
    code = line.slice(0, comment)
    tail = `<span class="pine-comment">${escape(line.slice(comment))}</span>`
  }

  const pieces: string[] = []
  const pattern = new RegExp(
    `("[^"]*"|'[^']*')|(#[0-9a-fA-F]{6,8})|(\\b\\d[\\d.]*(?:[eE][+-]?\\d+)?\\b)|${NAMESPACES.source}|${KEYWORDS.source}|${BUILTINS.source}`,
    'g',
  )
  let cursor = 0
  for (const match of code.matchAll(pattern)) {
    const at = match.index ?? 0
    if (at > cursor) pieces.push(escape(code.slice(cursor, at)))
    const [text, str, colour, num, namespace, keyword] = match
    const kind = str || colour
      ? 'pine-string'
      : num
        ? 'pine-number'
        : namespace
          ? 'pine-namespace'
          : keyword
            ? 'pine-keyword'
            : 'pine-builtin'
    pieces.push(`<span class="${kind}">${escape(text)}</span>`)
    cursor = at + text.length
  }
  if (cursor < code.length) pieces.push(escape(code.slice(cursor)))
  return pieces.join('') + tail
}

function insideString(line: string, at: number): boolean {
  let quote = ''
  for (let index = 0; index < at; index += 1) {
    const char = line[index]
    if (quote) {
      if (char === quote && line[index - 1] !== '\\') quote = ''
    } else if (char === '"' || char === "'") {
      quote = char
    }
  }
  return Boolean(quote)
}

const painted = computed(() => lines.value.map(paint))

// --- editing ----------------------------------------------------------------

const INDENT = '    '

function onInput(event: Event) {
  emit('update:modelValue', (event.target as HTMLTextAreaElement).value)
  nextTick(trackCaret)
}

function onKeydown(event: KeyboardEvent) {
  const element = area.value
  if (!element) return

  if ((event.ctrlKey || event.metaKey) && event.key === 's') {
    event.preventDefault()
    emit('save')
    return
  }

  if (event.key === 'Tab') {
    event.preventDefault()
    const { selectionStart: from, selectionEnd: to } = element
    if (event.shiftKey) return outdent(element, from, to)
    replace(element, from, to, INDENT, from + INDENT.length)
    return
  }

  if (event.key === 'Enter') {
    // Carry this line's indentation onto the next, and add one level after a
    // line that opens a block. Pine has no braces; the indentation *is* the
    // block, so an editor that drops back to column one every line is asking
    // for an IndentationError on every third keystroke.
    const { selectionStart: from } = element
    const before = props.modelValue.slice(0, from)
    const current = before.slice(before.lastIndexOf('\n') + 1)
    const indent = /^[ \t]*/.exec(current)?.[0] ?? ''
    const opens = /(^|\s)(if|else|for|while|switch)\b.*$/.test(current.trim()) ||
      current.trimEnd().endsWith('=>')
    const insert = `\n${indent}${opens ? INDENT : ''}`
    event.preventDefault()
    replace(element, from, element.selectionEnd, insert, from + insert.length)
  }
}

function replace(
  element: HTMLTextAreaElement,
  from: number,
  to: number,
  text: string,
  caret: number,
) {
  const next = props.modelValue.slice(0, from) + text + props.modelValue.slice(to)
  emit('update:modelValue', next)
  nextTick(() => {
    element.selectionStart = element.selectionEnd = caret
    trackCaret()
  })
}

function outdent(element: HTMLTextAreaElement, from: number, to: number) {
  const start = props.modelValue.lastIndexOf('\n', from - 1) + 1
  const head = props.modelValue.slice(start, from)
  const removed = head.startsWith(INDENT) ? INDENT.length : head.startsWith(' ') ? 1 : 0
  if (!removed) return
  const next =
    props.modelValue.slice(0, start) + props.modelValue.slice(start + removed)
  emit('update:modelValue', next)
  nextTick(() => {
    element.selectionStart = element.selectionEnd = Math.max(start, to - removed)
  })
}

function trackCaret() {
  const element = area.value
  if (!element) return
  caretLine.value = props.modelValue.slice(0, element.selectionStart).split('\n').length
}

function onScroll(event: Event) {
  scrollTop.value = (event.target as HTMLElement).scrollTop
}

/** Put the caret on a line — what clicking a diagnostic does. */
function goTo(line: number, col = 1) {
  const element = area.value
  if (!element) return
  const offset =
    lines.value.slice(0, line - 1).reduce((total, text) => total + text.length + 1, 0) + (col - 1)
  element.focus()
  element.selectionStart = element.selectionEnd = offset
  trackCaret()
  const target = (line - 1) * 21 - element.clientHeight / 2
  element.scrollTop = Math.max(0, target)
}

defineExpose({ goTo })
</script>

<template>
  <div class="pine-editor panel overflow-hidden flex min-h-0" :style="{ '--rows': minRows }">
    <!-- The gutter scrolls with the text rather than beside it: two independent
         scroll positions is how line 40's number ends up next to line 12. -->
    <div class="pine-gutter shrink-0 overflow-hidden select-none" aria-hidden="true">
      <div :style="{ transform: `translateY(${-scrollTop}px)` }">
        <div
          v-for="(_, index) in lines"
          :key="index"
          class="pine-line pine-gutter-line"
          :class="{
            'pine-gutter-current': index + 1 === caretLine,
            'pine-gutter-error': marks.get(index + 1)?.kind === 'error',
            'pine-gutter-warning': marks.get(index + 1)?.kind === 'warning',
          }"
        >
          {{ index + 1 }}
        </div>
      </div>
    </div>

    <div ref="scroller" class="relative flex-1 min-w-0">
      <!-- The painted copy sits under a transparent textarea. Both use the same
           font metrics, so the caret lands where the colour is. -->
      <div class="pine-layer" :style="{ transform: `translateY(${-scrollTop}px)` }">
        <div
          v-for="(html, index) in painted"
          :key="index"
          class="pine-line"
          :class="{
            'pine-row-error': marks.get(index + 1)?.kind === 'error',
            'pine-row-warning': marks.get(index + 1)?.kind === 'warning',
          }"
          v-html="html || '&nbsp;'"
        />
      </div>
      <textarea
        ref="area"
        class="pine-input"
        :value="modelValue"
        :readonly="readonly"
        spellcheck="false"
        autocapitalize="off"
        autocomplete="off"
        autocorrect="off"
        wrap="off"
        @input="onInput"
        @keydown="onKeydown"
        @scroll="onScroll"
        @click="trackCaret"
        @keyup="trackCaret"
      />
    </div>
  </div>
</template>

<style scoped>
.pine-editor {
  height: calc(var(--rows) * 21px + 1.5rem);
}

.pine-line {
  font-family: theme('fontFamily.mono');
  font-size: 13px;
  line-height: 21px;
  height: 21px;
  white-space: pre;
}

.pine-gutter {
  @apply bg-sunken border-e border-line py-3 px-3 text-end;
  min-width: 3.25rem;
}

.pine-gutter-line {
  @apply text-ink-faint;
}
.pine-gutter-current {
  @apply text-ink;
}
.pine-gutter-error {
  @apply text-short font-semibold;
}
.pine-gutter-warning {
  @apply text-signal font-semibold;
}

.pine-layer {
  @apply absolute inset-0 py-3 px-4 pointer-events-none overflow-hidden;
}

.pine-row-error {
  @apply bg-short-dim;
}
.pine-row-warning {
  @apply bg-signal-dim;
}

.pine-input {
  @apply absolute inset-0 w-full h-full resize-none bg-transparent py-3 px-4
         text-transparent caret-ink outline-none overflow-auto;
  font-family: theme('fontFamily.mono');
  font-size: 13px;
  line-height: 21px;
  tab-size: 4;
}

/* The palette leans on the same tokens the rest of the panel uses rather than
   introducing an editor theme nobody else shares. */
:deep(.pine-keyword) {
  @apply text-brand;
}
:deep(.pine-namespace) {
  @apply text-long;
}
:deep(.pine-builtin) {
  @apply text-ink;
  font-weight: 500;
}
:deep(.pine-number) {
  @apply text-signal;
}
:deep(.pine-string) {
  @apply text-ok;
}
:deep(.pine-comment) {
  @apply text-ink-faint italic;
}
</style>
