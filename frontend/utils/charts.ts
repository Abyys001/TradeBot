/** Shapes the chart components consume. Kept here because `<script setup>` cannot export types. */

export interface BarRow {
  key: string | number
  label: string
  value: number
  /** Rendered at the end of the row. Pre-formatted by the caller. */
  display: string
  sub?: string
  tone?: 'default' | 'signal' | 'muted'
}

export interface ColumnPoint {
  key: string | number
  value: number
  label: string
  /** Secondary line in the tooltip — usually a timestamp. */
  meta?: string
  /** Marks the column as a breach of the reference line. */
  over?: boolean
}
