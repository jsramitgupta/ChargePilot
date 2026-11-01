import { BatteryCharging, CircleDashed, RefreshCw, X } from 'lucide-react'

import { useEffect } from 'react'

import type { ReactNode } from 'react'

import { type Endpoint } from './types'

import { PLATFORM_NAMES, formatTimestampWithSeconds, formatTimestamp, trapDialogFocus } from './lib'

export function PlatformMark({ platform }: { platform: Endpoint['platform'] }) {
  return (
    <span className={`platform-mark platform-mark-${platform}`} aria-hidden="true">
      <svg viewBox="0 0 24 24" focusable="false">
        {platform === 'windows' && <path d="M3 5.2 10.5 4v7H3V5.2Zm9-1.4L21 2.5V11h-9V3.8ZM3 13h7.5v7L3 18.8V13Zm9 0h9v8.5l-9-1.3V13Z" fill="currentColor" />}
        {platform === 'android' && <g fill="currentColor">
          <path d="m6.1 4.8 1.2-.7 1.4 2.1a8.8 8.8 0 0 1 6.6 0l1.4-2.1 1.2.7-1.3 2a6.8 6.8 0 0 1 2.8 5.2H4.6a6.8 6.8 0 0 1 2.8-5.2l-1.3-2Z" />
          <path d="M4.6 13.2h14.8v5.3a1 1 0 0 1-1 1h-1.2v2h-1.7v-2h-6v2H7.8v-2H6a1.4 1.4 0 0 1-1.4-1.4v-5Zm-2 0h1.4v4.6H2.6a1 1 0 0 1-1-1v-2.6a1 1 0 0 1 1-1Zm17.4 0h1.4a1 1 0 0 1 1 1v2.6a1 1 0 0 1-1 1H20v-4.6Z" />
        </g>}
        {platform === 'macos' && <g>
          <rect x="2.5" y="3.5" width="19" height="13.2" rx="1.6" fill="none" stroke="currentColor" strokeWidth="1.7" />
          <path d="M9 21h6m-3-4.3V21" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" />
          <g transform="translate(8.4 5.6) scale(.31)" fill="currentColor">
            <path d="M20.2 8.5c-1.8 0-3.2 1-4.3 1s-2.3-1-4.4-1c-3 0-6.1 2.5-6.1 6.8 0 2.6 1 5.5 2.3 7.8 1.1 1.8 2.2 3.4 3.8 3.4 1.3 0 1.8-.8 3.8-.8s2.4.8 3.8.8c1.6 0 2.7-1.5 3.7-3.2.8-1.3 1.3-2.6 1.6-3.4-4.9-1.8-5-8.4-.2-10.3-1.2-2-3.5-3.1-5.3-3.1Z" />
            <path d="M14.5 4c.9-1.1 2.5-1.9 3.8-2-.1 1.3-.6 2.6-1.6 3.6-.9.9-2.3 1.5-3.6 1.4-.1-1.1.5-2.2 1.4-3Z" />
          </g>
        </g>}
        {platform === 'ios' && <g>
          <rect x="5.2" y="1.7" width="13.6" height="20.6" rx="2.6" fill="none" stroke="currentColor" strokeWidth="1.7" />
          <path d="M10 4h4" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.3" />
          <circle cx="12" cy="19.7" r=".8" fill="currentColor" />
          <g transform="translate(9 7.8) scale(.25)" fill="currentColor">
            <path d="M20.2 8.5c-1.8 0-3.2 1-4.3 1s-2.3-1-4.4-1c-3 0-6.1 2.5-6.1 6.8 0 2.6 1 5.5 2.3 7.8 1.1 1.8 2.2 3.4 3.8 3.4 1.3 0 1.8-.8 3.8-.8s2.4.8 3.8.8c1.6 0 2.7-1.5 3.7-3.2.8-1.3 1.3-2.6 1.6-3.4-4.9-1.8-5-8.4-.2-10.3-1.2-2-3.5-3.1-5.3-3.1Z" />
            <path d="M14.5 4c.9-1.1 2.5-1.9 3.8-2-.1 1.3-.6 2.6-1.6 3.6-.9.9-2.3 1.5-3.6 1.4-.1-1.1.5-2.2 1.4-3Z" />
          </g>
        </g>}
      </svg>
    </span>
  )
}

export function EndpointIdentity({ endpoint }: { endpoint: Endpoint }) {
  return (
    <div className="endpoint-identity">
      <PlatformMark platform={endpoint.platform} />
      <span className="endpoint-identity-copy">
        <span className="endpoint-identity-hostname">{endpoint.display_name || endpoint.hostname}</span>
        <span className="endpoint-identity-platform">{PLATFORM_NAMES[endpoint.platform]}</span>
      </span>
    </div>
  )
}

export function RelativeTimestamp({ value, now }: { value: string | null; now: number }) {
  if (!value) return '—'
  const timestamp = Date.parse(value)
  if (!Number.isFinite(timestamp)) return value

  const differenceSeconds = (timestamp - now) / 1_000
  const absoluteSeconds = Math.abs(differenceSeconds)
  const unit: Intl.RelativeTimeFormatUnit = absoluteSeconds < 60
    ? 'second'
    : absoluteSeconds < 3_600
      ? 'minute'
      : absoluteSeconds < 86_400
        ? 'hour'
        : 'day'
  const divisor = unit === 'second' ? 1 : unit === 'minute' ? 60 : unit === 'hour' ? 3_600 : 86_400
  const amount = Math.round(differenceSeconds / divisor)
  const relativeTime = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' }).format(amount, unit)

  return <time dateTime={value} title={formatTimestampWithSeconds(value)}>{relativeTime}</time>
}

export function FieldError({ children }: { children: ReactNode }) {
  return <p className="mt-1.5 text-sm text-red-700" role="alert">{children}</p>
}

export function MetricMini({ label, value }: { label: string; value: string }) {
  return <div className="switch-metric"><p>{label}</p><strong>{value}</strong></div>
}

export function LoadingScreen() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100">
      <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white px-5 py-3 shadow-soft">
        <CircleDashed className="animate-spin text-brand-600" size={18} />
        <span className="text-sm font-medium text-slate-700">Loading ChargePilot…</span>
      </div>
    </div>
  )
}

export function LoadingCard() {
  return <div className="panel p-8 text-sm text-slate-600">Loading…</div>
}

export function ErrorCard({ message }: { message: string }) {
  return <div className="alert error" role="alert">{message}</div>
}

export function LiveRefreshControl({
  updatedAt,
  isFetching,
  onRefresh,
}: {
  updatedAt: number
  isFetching: boolean
  onRefresh: () => void
}) {
  const lastUpdated = updatedAt ? formatTimestamp(new Date(updatedAt).toISOString()) : 'Waiting for first update'

  return (
    <div className="live-refresh-control">
      <div className="live-refresh-copy" aria-live="polite">
        <span className="live-refresh-state"><span className="live-refresh-dot" />Auto refresh · 30 sec</span>
        <span>Updated {lastUpdated}</span>
      </div>
      <button type="button" className="secondary-btn live-refresh-button" disabled={isFetching} onClick={onRefresh}>
        <RefreshCw size={15} aria-hidden="true" />
        {isFetching ? 'Refreshing' : 'Refresh'}
      </button>
    </div>
  )
}

export function MetricCard({
  label,
  value,
  hint,
  icon: Icon,
}: {
  label: string
  value: string
  hint: string
  icon: typeof BatteryCharging
}) {
  return (
    <div className="panel metric-card">
      <div className="metric-card-copy">
        <p className="metric-card-label">{label}</p>
        <p className="metric-card-value">{value}</p>
        <p className="metric-card-hint">{hint}</p>
      </div>
      <div className="metric-icon">
        <Icon size={21} />
      </div>
    </div>
  )
}

export function AgentInstallInstructions({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [onClose])

  return <div className="install-guide-backdrop" role="presentation" onMouseDown={(event) => {
    if (event.target === event.currentTarget) onClose()
  }}>
    <section className="install-guide-dialog" role="dialog" aria-modal="true" aria-labelledby="install-guide-title" tabIndex={-1} onKeyDown={trapDialogFocus}>
      <div className="install-guide-heading">
        <div>
          <p className="page-context">Device setup</p>
          <h2 id="install-guide-title">Install instructions</h2>
          <p>Install the package on the device, then use an enrollment token created for its workspace.</p>
        </div>
        <button type="button" className="secondary-btn" autoFocus onClick={onClose}><X size={16} aria-hidden="true" />Close</button>
      </div>
      <ol className="install-guide-steps">
        <li><strong>Windows (.EXE)</strong><span>Open the executable and follow its setup window. Approve the Windows service prompt, enter the enrollment token, then save and start the service.</span></li>
        <li><strong>macOS (.DMG)</strong><span>Open the disk image, move ChargePilotAgent to Applications, launch it, and connect with the enrollment token. macOS may require approval for an unsigned or unnotarized build.</span></li>
        <li><strong>Android (.APK)</strong><span>Open the APK on the device and allow your browser or file manager to install it if asked. Launch ChargePilotAgent and enter the enrollment token. Android WorkManager may delay background reports and enforces a 15-minute minimum.</span></li>
        <li><strong>iPhone and iPad (.IPA)</strong><span>An IPA is not an App Store install. Install through Apple Configurator or Xcode with a valid provisioning profile; a release IPA can be installed only on devices in its ad-hoc profile. In Shortcuts, add “Report battery to ChargePilot” to both a Battery Level automation and a Charger Connected automation.</span></li>
      </ol>
      <p className="install-guide-note">Release signing varies by platform and release. Follow the operating system's installation warnings. iOS Shortcuts and mobile background reports are best-effort and do not guarantee exact reporting times.</p>
      <div className="install-guide-footer">
        <button type="button" className="btn-primary" onClick={onClose}>Done</button>
      </div>
    </section>
  </div>
}

export function PageHeader({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) {
  return (
    <div className="page-heading">
      <div className="page-heading-marker" aria-hidden="true" />
      <div>
        <p className="page-context">{eyebrow}</p>
        <h2>{title}</h2>
        <p className="page-description">{description}</p>
      </div>
    </div>
  )
}
