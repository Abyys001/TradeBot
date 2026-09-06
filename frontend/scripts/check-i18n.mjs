// Every locale must carry the whole catalogue.
//
// English is the source language, so a key that exists in en.json and nowhere
// else is a string the panel will silently render in English for five of the
// six locales — the failure mode is invisible, which is why it is a test
// rather than a convention. Placeholders and vue-i18n's `|` plural forms are
// checked too: a translation that drops {n} renders a sentence with a hole in
// it, and one that drops the pipe renders "1 account | 2 accounts" verbatim.
//
// Run: node scripts/check-i18n.mjs   (npm run check:i18n)

import { readFileSync, readdirSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const dir = join(dirname(fileURLToPath(import.meta.url)), '..', 'i18n', 'locales')
const SOURCE = 'en'

const flatten = (value, prefix = '', out = {}) => {
  for (const [key, child] of Object.entries(value)) {
    const path = prefix ? `${prefix}.${key}` : key
    if (child && typeof child === 'object' && !Array.isArray(child)) flatten(child, path, out)
    else out[path] = child
  }
  return out
}

const placeholders = (text) =>
  [...new Set(String(text).match(/\{\w+\}/g) ?? [])].sort().join(',')

const load = (code) => flatten(JSON.parse(readFileSync(join(dir, `${code}.json`), 'utf8')))

const source = load(SOURCE)
const codes = readdirSync(dir)
  .filter((name) => name.endsWith('.json'))
  .map((name) => name.slice(0, -5))
  .filter((code) => code !== SOURCE)
  .sort()

const problems = []

for (const code of codes) {
  const target = load(code)
  for (const key of Object.keys(source)) {
    if (!(key in target)) {
      problems.push(`${code}: missing ${key}`)
      continue
    }
    if (placeholders(source[key]) !== placeholders(target[key])) {
      problems.push(
        `${code}: ${key} placeholders ${placeholders(source[key]) || '(none)'} -> ${placeholders(target[key]) || '(none)'}`,
      )
    }
    const plural = (text) => String(text).split('|').length
    if (plural(source[key]) !== plural(target[key])) {
      problems.push(`${code}: ${key} has ${plural(target[key])} plural form(s), English has ${plural(source[key])}`)
    }
  }
  for (const key of Object.keys(target)) {
    if (!(key in source)) problems.push(`${code}: ${key} is not in ${SOURCE}.json`)
  }
}

if (problems.length) {
  console.error(`i18n: ${problems.length} problem(s)\n`)
  for (const line of problems.slice(0, 50)) console.error(`  ${line}`)
  if (problems.length > 50) console.error(`  … and ${problems.length - 50} more`)
  process.exit(1)
}

console.log(`i18n: ${codes.length + 1} locales, ${Object.keys(source).length} keys each, all complete.`)
