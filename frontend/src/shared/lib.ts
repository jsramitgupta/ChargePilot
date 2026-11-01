import type { KeyboardEvent as ReactKeyboardEvent } from 'react'

import { type MeterUnitScale, type MeterScaleParts, type Endpoint } from './types'

export function meterScaleParts(multiplier: number, units: MeterUnitScale[]): MeterScaleParts {
  for (const { unit, multiplier: unitMultiplier } of units) {
    for (let decimalPlaces = 0; decimalPlaces <= 6; decimalPlaces += 1) {
      const expected = unitMultiplier * (10 ** -decimalPlaces)
      if (Math.abs(multiplier - expected) <= Math.max(1, Math.abs(multiplier)) * 1e-9) {
        return { unit, decimalPlaces: String(decimalPlaces), customBaseScale: String(unitMultiplier) }
      }
    }
  }
  return { unit: 'custom', decimalPlaces: '0', customBaseScale: String(multiplier) }
}

export function meterMultiplier(unit: string, decimalPlaces: string, customBaseScale: string, units: MeterUnitScale[]) {
  const baseScale = unit === 'custom'
    ? Number(customBaseScale)
    : units.find((option) => option.unit === unit)?.multiplier ?? Number.NaN
  return baseScale * (10 ** -Number(decimalPlaces))
}

export const ENDPOINTS_REFRESH_INTERVAL = 30_000

export const OVERVIEW_ENDPOINT_LIMIT = 10

export function sortEndpointsByLastSeen(endpoints: Endpoint[]) {
  return [...endpoints].sort((first, second) => {
    const firstSeen = first.last_seen_at ? Date.parse(first.last_seen_at) : Number.NEGATIVE_INFINITY
    const secondSeen = second.last_seen_at ? Date.parse(second.last_seen_at) : Number.NEGATIVE_INFINITY
    const firstTimestamp = Number.isFinite(firstSeen) ? firstSeen : Number.NEGATIVE_INFINITY
    const secondTimestamp = Number.isFinite(secondSeen) ? secondSeen : Number.NEGATIVE_INFINITY

    return secondTimestamp - firstTimestamp
      || (first.display_name || first.hostname).localeCompare(second.display_name || second.hostname)
  })
}

export const PLATFORM_NAMES: Record<Endpoint['platform'], string> = {
  windows: 'Windows',
  macos: 'macOS',
  android: 'Android',
  ios: 'iOS',
}

export function trapDialogFocus(event: ReactKeyboardEvent<HTMLElement>) {
  if (event.key !== 'Tab') return
  const focusable = Array.from(event.currentTarget.querySelectorAll<HTMLElement>(
    'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
  )).filter((element) => element.getAttribute('aria-hidden') !== 'true')
  if (!focusable.length) {
    event.preventDefault()
    return
  }
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (event.shiftKey && (document.activeElement === first || !event.currentTarget.contains(document.activeElement))) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && (document.activeElement === last || !event.currentTarget.contains(document.activeElement))) {
    event.preventDefault()
    first.focus()
  }
}

export function formatPower(watts: number) {
  return watts >= 1000
    ? `${(watts / 1000).toFixed(2)} kW`
    : `${watts.toFixed(1)} W`
}

export function formatPercent(value: number | null | undefined) {
  return value === null || value === undefined || !Number.isFinite(value)
    ? 'Not reported'
    : `${Math.round(value)}%`
}

export function formatBytes(value: number) {
  if (!Number.isFinite(value) || value < 0) return 'Unknown'
  if (value < 1_000) return `${value} B`
  const units = ['KB', 'MB', 'GB', 'TB', 'PB']
  let scaled = value
  let unitIndex = -1
  do {
    scaled /= 1_000
    unitIndex += 1
  } while (scaled >= 1_000 && unitIndex < units.length - 1)
  return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(scaled)} ${units[unitIndex]}`
}

export function formatTimestamp(value: string | null) {
  if (!value) return '—'
  const timestamp = new Date(value)
  if (Number.isNaN(timestamp.getTime())) return value
  const timezone = document.body.dataset.userTimezone
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
      ...(timezone && timezone !== 'local' ? { timeZone: timezone } : {}),
    }).format(timestamp)
  } catch {
    return timestamp.toLocaleString()
  }
}

export function formatTimestampWithSeconds(value: string | null) {
  if (!value) return '—'
  const timestamp = new Date(value)
  if (Number.isNaN(timestamp.getTime())) return value
  const timezone = document.body.dataset.userTimezone
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium',
      timeStyle: 'medium',
      ...(timezone && timezone !== 'local' ? { timeZone: timezone } : {}),
    }).format(timestamp)
  } catch {
    return timestamp.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'medium' })
  }
}
