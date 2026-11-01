import { BatteryCharging, Activity, Cpu, HardDrive, MemoryStick, X } from 'lucide-react'

import { useEffect, useState } from 'react'

import type { EndpointDetails, EndpointReading } from '../../shared/types'

import { ENDPOINTS_REFRESH_INTERVAL, PLATFORM_NAMES, formatTimestamp, formatTimestampWithSeconds, trapDialogFocus, formatPercent, formatBytes, formatPower } from '../../shared/lib'

import { LoadingCard, ErrorCard } from '../../shared/components'

export function EndpointDetailsPanel({
  details,
  isLoading,
  error,
  onClose,
}: {
  details: EndpointDetails | undefined
  isLoading: boolean
  error: Error | null
  onClose: () => void
}) {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [onClose])

  useEffect(() => {
    const interval = window.setInterval(() => setNow(Date.now()), ENDPOINTS_REFRESH_INTERVAL)
    return () => window.clearInterval(interval)
  }, [])

  const latestReading = details?.readings.at(-1)
  const metrics = latestReading?.system_metrics
  const [readingView, setReadingView] = useState<'table' | 'chart'>('table')
  const currentMonth = new Date(now).toISOString().slice(0, 7)
  const memoryPercent = metrics?.memory_used_bytes !== null && metrics?.memory_used_bytes !== undefined &&
    metrics.memory_total_bytes !== null && metrics.memory_total_bytes !== undefined && metrics.memory_total_bytes > 0
    ? metrics.memory_used_bytes / metrics.memory_total_bytes * 100
    : null

  return (
    <div className="endpoint-detail-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose()
    }}>
      <aside className="endpoint-detail-drawer" role="dialog" aria-modal="true" aria-labelledby="endpoint-details-title" tabIndex={-1} onKeyDown={trapDialogFocus}>
        <div className="endpoint-detail-heading">
          <div>
            <p className="page-context">Device profile</p>
            <h2 id="endpoint-details-title">{details?.display_name ?? 'Device details'}</h2>
            {details && <p>{details.hostname} · {PLATFORM_NAMES[details.platform]}{details.device_class ? ` · ${details.device_class}` : ''}</p>}
          </div>
          <button type="button" className="secondary-btn" autoFocus onClick={onClose}><X size={16} aria-hidden="true" />Close</button>
        </div>
        <div className="endpoint-detail-content">
      {isLoading ? <LoadingCard />
        : error ? <ErrorCard message={`Could not load device details: ${error.message}`} />
          : !details ? <ErrorCard message="The device detail request returned no data." />
            : <>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <p className="text-sm text-[var(--muted)]">Latest device state and reporting history</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <DeviceMetricCard icon={BatteryCharging} label="Battery" value={`${details.battery}%`} hint={details.charging ? 'Charging' : details.ac_connected ? 'Connected to power' : 'On battery'} />
        <DeviceMetricCard icon={Activity} label="CPU" value={formatPercent(metrics?.cpu_usage_percent)} hint="System utilization at last report" />
        <DeviceMetricCard icon={MemoryStick} label="Memory" value={memoryPercent === null ? 'Not reported' : `${Math.round(memoryPercent)}%`} hint={metrics?.memory_used_bytes != null && metrics.memory_total_bytes != null ? `${formatBytes(metrics.memory_used_bytes)} of ${formatBytes(metrics.memory_total_bytes)}` : 'Unavailable on this platform'} />
        <DeviceMetricCard icon={Cpu} label="GPU" value={formatPercent(metrics?.gpu_usage_percent)} hint={metrics?.gpu_usage_percent == null ? 'Not available from this platform' : 'System utilization at last report'} />
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,0.8fr)]">
        <section className="rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] p-4" aria-labelledby="storage-title">
          <div className="mb-4 flex items-center gap-2 text-[var(--ink)]">
            <HardDrive size={17} aria-hidden="true" />
            <h3 id="storage-title" className="font-semibold">Storage</h3>
          </div>
          {metrics?.disks.length ? <ul className="space-y-4">
            {metrics.disks.map((disk) => {
              const usage = Math.min(100, disk.used_bytes / disk.total_bytes * 100)
              return <li key={disk.name}>
                <div className="mb-1 flex items-baseline justify-between gap-2 text-sm">
                  <strong className="truncate text-[var(--ink)]">{disk.name}</strong>
                  <span className="shrink-0 text-[var(--muted)]">{formatBytes(disk.used_bytes)} / {formatBytes(disk.total_bytes)}</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-[var(--line)]" role="meter" aria-label={`${disk.name} used`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(usage)}>
                  <div className="h-full rounded-full bg-[var(--leaf)]" style={{ width: `${usage}%` }} />
                </div>
              </li>
            })}
          </ul> : <p className="text-sm text-[var(--muted)]">Storage details are not available yet. Confirm the agent is updated and has sent a new report.</p>}
          {memoryPercent !== null && <div className="mt-5">
            <div className="mb-1 flex items-baseline justify-between gap-2 text-sm"><strong className="text-[var(--ink)]">Memory in use</strong><span className="text-[var(--muted)]">{Math.round(memoryPercent)}%</span></div>
            <div className="h-2 overflow-hidden rounded-full bg-[var(--line)]" role="meter" aria-label="Memory used" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(memoryPercent)}>
              <div className="h-full rounded-full bg-[var(--copper)]" style={{ width: `${Math.min(100, memoryPercent)}%` }} />
            </div>
          </div>}
          <p className="mt-4 text-xs text-[var(--muted)]">Snapshot from {formatTimestamp(latestReading?.timestamp ?? null)}. GPU readings depend on operating-system support.</p>
        </section>

        <section className="rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] p-4" aria-labelledby="identity-title">
          <h3 id="identity-title" className="mb-3 font-semibold text-[var(--ink)]">Identity and connection</h3>
          <dl className="grid grid-cols-[minmax(7rem,auto)_1fr] gap-x-3 gap-y-2 text-sm">
            <dt className="text-[var(--muted)]">Status</dt><dd className="text-[var(--ink)]">{details.status}</dd>
            <dt className="text-[var(--muted)]">Last report</dt><dd className="text-[var(--ink)]">{formatTimestampWithSeconds(details.last_seen_at)}</dd>
            <dt className="text-[var(--muted)]">Report target</dt><dd className="text-[var(--ink)]">Every {details.reporting_interval_minutes} minutes</dd>
            <dt className="text-[var(--muted)]">Agent version</dt><dd className="text-[var(--ink)]">{details.agent_version ?? 'Unknown'}</dd>
            <dt className="text-[var(--muted)]">Network address</dt><dd className="break-all text-[var(--ink)]">{details.ip_address ?? 'Not reported'}</dd>
            <dt className="text-[var(--muted)]">Installation ID</dt><dd className="break-all font-mono text-xs text-[var(--ink)]">{details.installation_id ?? details.hardware_uuid ?? 'Pending agent update'}</dd>
            <dt className="text-[var(--muted)]">Automation</dt><dd className="text-[var(--ink)]">{details.automation_enabled ? details.automation_available ? 'Enabled · fresh report' : 'Enabled · waiting for a fresh report' : 'Paused'}</dd>
          </dl>
        </section>
      </div>

      <section aria-labelledby="mapped-switches-title">
        <h3 id="mapped-switches-title" className="mb-3 font-semibold text-[var(--ink)]">Mapped switches</h3>
        {details.mappings.length ? <ul className="grid gap-2 sm:grid-cols-2">
          {details.mappings.map((mapping) => {
            const powerAge = mapping.meter_power_sample_at
              ? now - Date.parse(mapping.meter_power_sample_at)
              : Number.POSITIVE_INFINITY
            const hasCurrentPower = mapping.meter_power_watts != null
              && powerAge >= 0
              && powerAge <= 5 * 60 * 1000
            const hasCurrentMonthEnergy = mapping.meter_month_key === currentMonth
              && mapping.meter_energy_month_kwh != null
              && mapping.meter_energy_sample_at != null
            const powerReading = hasCurrentPower && mapping.meter_power_watts != null
              ? formatPower(mapping.meter_power_watts)
              : mapping.power_dp_id ? 'Waiting for a fresh reading' : 'Not configured'
            const energyReading = hasCurrentMonthEnergy && mapping.meter_energy_month_kwh != null
              ? `${mapping.meter_energy_month_kwh.toFixed(2)} kWh`
              : mapping.energy_dp_id ? 'No current-month reading' : 'Not configured'
            return <li key={mapping.id} className="rounded-lg border border-[var(--line)] px-3 py-3">
              <div className="flex items-start justify-between gap-3">
                <div><p className="font-medium text-[var(--ink)]">{mapping.name}</p><p className="mt-1 text-xs text-[var(--muted)]">{mapping.enabled ? 'Mapping active' : 'Mapping paused'} · {mapping.use_case === 'switch_off_only' ? 'switch off only' : mapping.use_case === 'switch_and_shutdown' ? 'switch off + shutdown request' : 'battery-managed switch cycle'} · Switch {mapping.switch_state ? 'on' : 'off'}</p></div>
                <span className="shrink-0 text-right text-xs text-[var(--muted)]">On ≤ {mapping.on_threshold}%<br />Off ≥ {mapping.off_threshold}%</span>
              </div>
              <dl className="mt-3 grid grid-cols-2 gap-3 border-t border-[var(--line)] pt-3">
                <div>
                  <dt className="text-xs text-[var(--muted)]">Live power</dt>
                  <dd className="mt-1 font-semibold text-[var(--ink)]">{powerReading}</dd>
                  <dd className="mt-1 text-xs text-[var(--muted)]">Sampled {formatTimestamp(mapping.meter_power_sample_at)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-[var(--muted)]">Energy this month (UTC)</dt>
                  <dd className="mt-1 font-semibold text-[var(--ink)]">{energyReading}</dd>
                  <dd className="mt-1 text-xs text-[var(--muted)]">Sampled {formatTimestamp(mapping.meter_energy_sample_at)}</dd>
                </div>
              </dl>
            </li>
          })}
        </ul> : <p className="text-sm text-[var(--muted)]">No switch mappings are assigned to this device.</p>}
      </section>

      <section aria-labelledby="report-history-title">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <h3 id="report-history-title" className="font-semibold text-[var(--ink)]">Recent reports</h3>
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-xs text-[var(--muted)]">Up to 100 reports · retained for 30 days</span>
            {details.readings.length > 0 && <div className="reading-view-toggle" role="group" aria-label="Recent report view">
              <button type="button" aria-pressed={readingView === 'table'} onClick={() => setReadingView('table')}>Table</button>
              <button type="button" aria-pressed={readingView === 'chart'} onClick={() => setReadingView('chart')}>Graph</button>
            </div>}
          </div>
        </div>
        {details.readings.length ? readingView === 'chart'
          ? <EndpointReadingChart readings={details.readings} />
          : <div className="max-h-72 overflow-auto rounded-lg border border-[var(--line)]">
          <table className="w-full text-left text-sm">
            <thead className="sticky top-0 bg-[var(--surface-muted)] text-xs text-[var(--muted)]"><tr><th className="px-3 py-2">Time</th><th className="px-3 py-2">Battery</th><th className="px-3 py-2">CPU</th><th className="px-3 py-2">Memory</th><th className="px-3 py-2">GPU</th></tr></thead>
            <tbody>{[...details.readings].reverse().map((reading) => <tr key={reading.timestamp} className="border-t border-[var(--line)]">
              <td className="whitespace-nowrap px-3 py-2 text-[var(--ink)]">{formatTimestampWithSeconds(reading.timestamp)}</td>
              <td className="px-3 py-2 text-[var(--ink)]">{reading.battery_percentage}%{reading.charging ? ' · charging' : ''}</td>
              <td className="px-3 py-2 text-[var(--ink)]">{formatPercent(reading.system_metrics?.cpu_usage_percent)}</td>
              <td className="px-3 py-2 text-[var(--ink)]">{reading.system_metrics?.memory_used_bytes != null && reading.system_metrics.memory_total_bytes != null ? `${formatBytes(reading.system_metrics.memory_used_bytes)} / ${formatBytes(reading.system_metrics.memory_total_bytes)}` : 'Not reported'}</td>
              <td className="px-3 py-2 text-[var(--ink)]">{formatPercent(reading.system_metrics?.gpu_usage_percent)}</td>
            </tr>)}</tbody>
          </table>
        </div> : <p className="rounded-lg border border-dashed border-[var(--line)] p-4 text-sm text-[var(--muted)]">No report history is available yet. Updated agents include CPU, memory, and storage details with each report.</p>}
      </section>
      </>}
        </div>
    </aside>
    </div>
  )
}

export function EndpointReadingChart({ readings }: { readings: EndpointReading[] }) {
  const chartWidth = 840
  const chartHeight = 300
  const plot = { left: 48, right: 18, top: 18, bottom: 44 }
  const plotWidth = chartWidth - plot.left - plot.right
  const plotHeight = chartHeight - plot.top - plot.bottom
  const timestamps = readings.map((reading) => Date.parse(reading.timestamp))
  const validTimestamps = timestamps.filter(Number.isFinite)
  const minTime = Math.min(...validTimestamps)
  const maxTime = Math.max(...validTimestamps)
  const xAt = (index: number) => {
    const time = timestamps[index]
    if (!Number.isFinite(time) || minTime === maxTime) {
      return plot.left + plotWidth * (readings.length === 1 ? 0.5 : index / (readings.length - 1))
    }
    return plot.left + ((time - minTime) / (maxTime - minTime)) * plotWidth
  }
  const yAt = (value: number) => plot.top + ((100 - value) / 100) * plotHeight
  const series = [
    {
      key: 'battery',
      label: 'Battery',
      value: (reading: EndpointReading) => reading.battery_percentage,
    },
    {
      key: 'cpu',
      label: 'CPU',
      value: (reading: EndpointReading) => reading.system_metrics?.cpu_usage_percent ?? null,
    },
    {
      key: 'memory',
      label: 'Memory',
      value: (reading: EndpointReading) => {
        const used = reading.system_metrics?.memory_used_bytes
        const total = reading.system_metrics?.memory_total_bytes
        return used != null && total != null && total > 0 ? used / total * 100 : null
      },
    },
    {
      key: 'gpu',
      label: 'GPU',
      value: (reading: EndpointReading) => reading.system_metrics?.gpu_usage_percent ?? null,
    },
  ] as const
  const timeLabel = (index: number) => formatTimestamp(readings[index]?.timestamp ?? null)

  return (
    <div className="endpoint-reading-chart">
      <ul className="reading-chart-legend" aria-label="Graph series">
        {series.map((item) => <li key={item.key}>
          <span className={`reading-chart-swatch reading-chart-${item.key}`} aria-hidden="true" />
          {item.label}
        </li>)}
      </ul>
      <svg
        className="reading-chart-svg"
        viewBox={`0 0 ${chartWidth} ${chartHeight}`}
        role="img"
        aria-label={`Battery and system resource percentages across ${readings.length} recent device reports. Unavailable values are not plotted.`}
      >
        {[0, 25, 50, 75, 100].map((tick) => {
          const y = yAt(tick)
          return <g key={tick}>
            <line className="reading-chart-grid" x1={plot.left} x2={chartWidth - plot.right} y1={y} y2={y} />
            <text className="reading-chart-axis-label" x={plot.left - 10} y={y + 4} textAnchor="end">{tick}%</text>
          </g>
        })}
        <text className="reading-chart-axis-label" x={plot.left} y={chartHeight - 10} textAnchor="start">{timeLabel(0)}</text>
        {readings.length > 1 && <text className="reading-chart-axis-label" x={chartWidth - plot.right} y={chartHeight - 10} textAnchor="end">{timeLabel(readings.length - 1)}</text>}
        {series.map((item) => {
          const segments: string[] = []
          let segment: string[] = []
          readings.forEach((reading, index) => {
            const value = item.value(reading)
            if (value === null || !Number.isFinite(value)) {
              if (segment.length) segments.push(segment.join(' '))
              segment = []
              return
            }
            segment.push(`${segment.length ? 'L' : 'M'} ${xAt(index).toFixed(2)} ${yAt(Math.max(0, Math.min(100, value))).toFixed(2)}`)
          })
          if (segment.length) segments.push(segment.join(' '))
          return <g key={item.key} className={`reading-chart-series reading-chart-${item.key}`}>
            {segments.map((path, index) => <path key={`${item.key}-${index}`} d={path} />)}
            {readings.map((reading, index) => {
              const value = item.value(reading)
              if (value === null || !Number.isFinite(value)) return null
              const plottedValue = Math.max(0, Math.min(100, value))
              return <circle key={`${reading.timestamp}-${item.key}`} cx={xAt(index)} cy={yAt(plottedValue)} r="3.5">
                <title>{`${item.label}: ${Math.round(value)}% at ${formatTimestampWithSeconds(reading.timestamp)}`}</title>
              </circle>
            })}
          </g>
        })}
      </svg>
      <p className="reading-chart-note">Each line uses the same 0–100% scale. Missing platform readings are left blank.</p>
    </div>
  )
}

export function DeviceMetricCard({
  icon: Icon,
  label,
  value,
  hint,
}: {
  icon: typeof BatteryCharging
  label: string
  value: string
  hint: string
}) {
  return <div className="rounded-xl border border-[var(--line)] bg-[var(--surface)] p-4">
    <div className="flex items-center gap-2 text-[var(--muted)]"><Icon size={16} aria-hidden="true" /><span className="text-sm font-medium">{label}</span></div>
    <p className="mt-3 text-xl font-semibold text-[var(--ink)]">{value}</p>
    <p className="mt-1 text-xs text-[var(--muted)]">{hint}</p>
  </div>
}
