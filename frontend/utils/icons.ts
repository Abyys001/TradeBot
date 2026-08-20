/**
 * The icon set, inline.
 *
 * A whole icon package for two dozen glyphs is a dependency the panel does not
 * need, and an icon font would be a network fetch — this UI has to work on a
 * machine behind a proxy with no CDN reachable.
 *
 * Every path is drawn on a 24-grid and stroked at 1.6, so the glyphs sit at the
 * same optical weight as the Inter text beside them.
 */
export const ICON_PATHS = {
  dashboard: 'M4 13h6V4H4v9Zm0 7h6v-5H4v5Zm10 0h6v-9h-6v9Zm0-16v5h6V4h-6Z',
  terminal: 'M4 17V7m5 10V4m5 13v-7m5 7V9',
  // Candles with wicks — the trading screen, distinct from the bar-chart glyph
  // the dashboard uses.
  chart:
    'M6 4v3m0 10v3M6 7h2.5v10H6V7Zm6-5v4m0 12v4m0-16h2.5v12H12V6Zm6 1v2m0 8v3m0-11h2.5v8H18V9Z',
  bell: 'M18 9a6 6 0 1 0-12 0c0 5-2 6-2 6h16s-2-1-2-6M10.5 20a1.8 1.8 0 0 0 3 0',
  accounts: 'M3 7h18M3 12h18M3 17h18',
  history: 'M12 8v4l3 2m6-2a9 9 0 1 1-2.6-6.4M21 3v5h-5',
  // An open ledger book with ruled lines — the financial management page.
  ledger:
    'M6 3h10a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Zm0 2v14h10V5H6Zm3 3h4M9 11h4M9 15h4',
  risk: 'M12 3 2 20h20L12 3Zm0 6v5m0 3h.01',
  settings:
    'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm7.4-3a7.4 7.4 0 0 0-.1-1.2l2-1.6-2-3.4-2.4 1a7.5 7.5 0 0 0-2-1.2L14.5 2h-4l-.4 2.6c-.7.3-1.4.7-2 1.2l-2.4-1-2 3.4 2 1.6a7.4 7.4 0 0 0 0 2.4l-2 1.6 2 3.4 2.4-1c.6.5 1.3.9 2 1.2l.4 2.6h4l.4-2.6c.7-.3 1.4-.7 2-1.2l2.4 1 2-3.4-2-1.6c.1-.4.1-.8.1-1.2Z',
  logout: 'M15 17l5-5-5-5M20 12H9M13 21H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h8',
  close: 'M6 6l12 12M18 6L6 18',
  menu: 'M4 7h16M4 12h16M4 17h16',
  plus: 'M12 5v14M5 12h14',
  refresh: 'M20 11a8 8 0 1 0-1.5 5.7M20 5v6h-6',
  check: 'M4 12.5 9 17.5 20 6.5',
  alert:
    'M12 9v4m0 3h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z',
  pause: 'M9 5v14M15 5v14',
  play: 'M7 4l13 8-13 8V4Z',
  trash: 'M4 7h16M10 11v6M14 11v6M5 7l1 13a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1l1-13M9 7V4h6v3',
  // Pencil over a rule: correcting a record that already exists, as
  // distinct from `plus`, which makes a new one.
  edit: 'M4 20h4L19 9a2.1 2.1 0 0 0-3-3L5 17v3ZM14.5 6.5l3 3',
  sun: 'M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10ZM12 1v3m0 16v3M4.2 4.2l2.1 2.1m11.4 11.4 2.1 2.1M1 12h3m16 0h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1',
  moon: 'M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z',
  arrowRight: 'M5 12h14M13 6l6 6-6 6',
  arrowUp: 'M12 19V5M6 11l6-6 6 6',
  arrowDown: 'M12 5v14M18 13l-6 6-6-6',
  shield: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z',
  bolt: 'M13 2 4 14h7l-1 8 9-12h-7l1-8Z',
  wallet:
    'M3 7a2 2 0 0 1 2-2h13a1 1 0 0 1 1 1v2M3 7v11a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-3M3 7h16a2 2 0 0 1 2 2v2h-5a2 2 0 0 0 0 4h5',
  search: 'M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16Zm10 2-4.3-4.3',
  filter: 'M3 5h18l-7 8v6l-4 2v-8L3 5Z',
  chevronDown: 'M6 9l6 6 6-6',
  chevronRight: 'M9 6l6 6-6 6',
  external: 'M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5',
  /** Tray with a down arrow: saving a slice of the log to a file. */
  download: 'M12 3v11m0 0 4-4m-4 4-4-4M4 17v2a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-2',
  eye: 'M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7Zm10 3a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z',
  eyeOff: 'M3 3l18 18M10.6 5.2A9.6 9.6 0 0 1 12 5c6.4 0 10 7 10 7a17 17 0 0 1-3.2 4M6.2 6.2A17 17 0 0 0 2 12s3.6 7 10 7c1.6 0 3-.4 4.3-1M9.9 9.9a3 3 0 0 0 4.2 4.2',
  /** Corners drawing inward: re-fit the chart to the data. */
  fit: 'M8 3H5a2 2 0 0 0-2 2v3m13-5h3a2 2 0 0 1 2 2v3M8 21H5a2 2 0 0 1-2-2v-3m13 5h3a2 2 0 0 0 2-2v-3',
  /** A quarter arc, spun by `animate-spin`: the "working" glyph. */
  spinner: 'M12 2a10 10 0 0 1 10 10',
  /** A rising line with an arrowhead: profit direction. */
  trend: 'M3 17l6-6 4 4 8-8M15 7h6v6',
  /** A terminal/console with lines — the system log page. */
  logs: 'M4 5h16M4 9h16M4 13h10M4 17h7',
} as const

export type IconName = keyof typeof ICON_PATHS
