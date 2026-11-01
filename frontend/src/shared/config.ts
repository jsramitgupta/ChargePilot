declare global {
  interface Window {
    CHARGEPILOT_CONFIG?: {
      apiBaseUrl?: string
      frontendUrl?: string
      turnstileSiteKey?: string
    }
    turnstile?: {
      render: (container: HTMLElement, options: {
        sitekey: string
        action: string
        theme: 'auto'
        callback: (token: string) => void
        'expired-callback': () => void
        'error-callback': () => void
      }) => string
      remove: (widgetId: string) => void
    }
  }
}

export const API_BASE_URL = (
  window.CHARGEPILOT_CONFIG?.apiBaseUrl ?? import.meta.env.VITE_API_BASE_URL ?? ''
).replace(/\/+$/, '')

export const FRONTEND_BASE_URL = (
  window.CHARGEPILOT_CONFIG?.frontendUrl ?? ''
).replace(/\/+$/, '') || window.location.origin

export const TIME_ZONE_REGIONS = [
  'Africa',
  'America',
  'Antarctica',
  'Arctic',
  'Asia',
  'Atlantic',
  'Australia',
  'Europe',
  'Indian',
  'Pacific',
] as const

export const TIME_ZONE_OPTIONS = typeof Intl.supportedValuesOf === 'function'
  ? Intl.supportedValuesOf('timeZone')
  : [
      'Africa/Cairo',
      'America/Los_Angeles',
      'America/New_York',
      'Asia/Kolkata',
      'Asia/Tokyo',
      'Australia/Sydney',
      'Europe/London',
      'Europe/Paris',
      'Pacific/Auckland',
    ]

export function backendUrl(path: string) {
  return `${API_BASE_URL}${path}`
}

export function frontendUrl(path: string) {
  return `${FRONTEND_BASE_URL}${path}`
}
