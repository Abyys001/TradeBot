import type { Config } from 'tailwindcss'

/**
 * Design tokens.
 *
 * Direction: an instrument, not a dashboard. Quiet ground so the only bright
 * things on screen are numbers that carry risk.
 *
 * Every colour resolves through a CSS variable declared in
 * `assets/css/main.css`, as an `R G B` triplet so Tailwind's `/opacity`
 * modifiers keep working. That indirection is what makes the light theme a
 * variable swap rather than a second set of classes on every element.
 *
 * The roles are strict, and the strictness is the point:
 *
 *   brand         chrome only — nav selection, focus rings, links. Never data.
 *   long / short  direction. Cyan and rose rather than the generic
 *                 green/red that reads as exchange boilerplate.
 *   signal        reserved *exclusively* for failure — spec §4 notifications,
 *                 liquidation, unprotected positions, budget breaches. If amber
 *                 appears anywhere decorative, the reservation is broken.
 *   ok            confirmation of a healthy state, nothing else.
 *
 * Each role carries a `dim` companion: the flat tinted *surface* for that role
 * (selected short chip, amber failure band, highlighted row). It is a token
 * rather than `bg-short/10` because no single alpha works in both themes —
 * 10% rose over near-black is a tint, over near-white it is nothing.
 */
export default <Partial<Config>>{
  theme: {
    extend: {
      screens: {
        xs: '440px',
        // Height query: the terminal needs a different layout on a laptop
        // than on a desk monitor, and width alone does not tell them apart.
        tall: { raw: '(min-height: 800px)' },
      },
      colors: {
        base: 'rgb(var(--c-base) / <alpha-value>)',
        panel: 'rgb(var(--c-panel) / <alpha-value>)',
        raised: 'rgb(var(--c-raised) / <alpha-value>)',
        sunken: 'rgb(var(--c-sunken) / <alpha-value>)',
        line: {
          DEFAULT: 'rgb(var(--c-line) / <alpha-value>)',
          strong: 'rgb(var(--c-line-strong) / <alpha-value>)',
        },
        ink: {
          DEFAULT: 'rgb(var(--c-ink) / <alpha-value>)',
          muted: 'rgb(var(--c-ink-muted) / <alpha-value>)',
          faint: 'rgb(var(--c-ink-faint) / <alpha-value>)',
          invert: 'rgb(var(--c-ink-invert) / <alpha-value>)',
        },
        brand: {
          DEFAULT: 'rgb(var(--c-brand) / <alpha-value>)',
          dim: 'rgb(var(--c-brand-dim) / <alpha-value>)',
        },
        long: {
          DEFAULT: 'rgb(var(--c-long) / <alpha-value>)',
          dim: 'rgb(var(--c-long-dim) / <alpha-value>)',
        },
        short: {
          DEFAULT: 'rgb(var(--c-short) / <alpha-value>)',
          dim: 'rgb(var(--c-short-dim) / <alpha-value>)',
        },
        signal: {
          DEFAULT: 'rgb(var(--c-signal) / <alpha-value>)',
          dim: 'rgb(var(--c-signal-dim) / <alpha-value>)',
        },
        ok: {
          DEFAULT: 'rgb(var(--c-ok) / <alpha-value>)',
          dim: 'rgb(var(--c-ok-dim) / <alpha-value>)',
        },
      },
      /* Type system — one face per role, so the custom fonts read as a
         system rather than a mix:

           display  Manrope    headings of every size (page titles, panel and
                               card headers). Enforced at the base layer too,
                               so no heading can slip back to the body face.
           sans     Inter      reading text, buttons, nav, inputs. Tabular
                               numerals ship with the face.
           ui       DM Sans    the micro layer — table headers, field labels,
                               timestamps, captions (.label). Designed for
                               small on-screen sizes.
           mono     JetBrains  numbers that can change — prices, PnL, sizes
                               (.num), so a ticking figure never reflows.

           Every stack ends in Vazirmatn: the Latin fonts carry no Arabic
           glyphs, so Persian text resolves to it per-character with no
           [lang='fa'] overrides anywhere.
      */
      fontFamily: {
        display: ['"Manrope"', 'Vazirmatn', 'system-ui', 'sans-serif'],
        sans: ['Inter', 'Vazirmatn', 'system-ui', 'sans-serif'],
        ui: ['"DM Sans"', 'Vazirmatn', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'Vazirmatn', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        tick: ['0.6875rem', { lineHeight: '1rem', letterSpacing: '0.06em' }],
        hero: ['clamp(2.25rem, 6.5vw, 4.75rem)', { lineHeight: '0.95', letterSpacing: '-0.035em' }],
        stat: ['clamp(1.5rem, 3.5vw, 2rem)', { lineHeight: '1.1', letterSpacing: '-0.02em' }],
      },
      borderRadius: {
        panel: '0.75rem',
      },
      boxShadow: {
        // Themed, like the colours: neutral black at dark-theme strength turns
        // into a grey smudge on a light page. The values live beside the colour
        // tokens in main.css so a theme is one block to read.
        lift: 'var(--shadow-lift)',
        pop: 'var(--shadow-pop)',
      },
      transitionTimingFunction: {
        out: 'cubic-bezier(0.2, 0.7, 0.3, 1)',
      },
      keyframes: {
        // The fan-out signature: a pulse travelling from the origin outward.
        travel: {
          '0%': { strokeDashoffset: 'var(--dash)', opacity: '0' },
          '10%': { opacity: '1' },
          '100%': { strokeDashoffset: '0', opacity: '1' },
        },
        arrive: {
          '0%': { transform: 'scale(0.2)', opacity: '0' },
          '100%': { transform: 'scale(1)', opacity: '1' },
        },
        shimmer: {
          '100%': { transform: 'translateX(100%)' },
        },
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(6px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'slide-in': {
          '0%': { transform: 'translateX(-100%)' },
          '100%': { transform: 'translateX(0)' },
        },
        'pulse-ring': {
          '0%': { transform: 'scale(1)', opacity: '0.6' },
          '100%': { transform: 'scale(2.4)', opacity: '0' },
        },
      },
      animation: {
        'fade-up': 'fade-up 0.24s cubic-bezier(0.2, 0.7, 0.3, 1) both',
        'slide-in': 'slide-in 0.22s cubic-bezier(0.2, 0.7, 0.3, 1)',
        'pulse-ring': 'pulse-ring 1.8s cubic-bezier(0.2, 0.7, 0.3, 1) infinite',
      },
    },
  },
}
