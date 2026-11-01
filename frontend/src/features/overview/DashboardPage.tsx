import { useQuery } from '@tanstack/react-query'

import { CheckCircle2, CircleDashed, MonitorSmartphone, PlugZap } from 'lucide-react'

import { useEffect, useState } from 'react'

import { NavLink } from 'react-router-dom'

import { fetchDashboardData } from '../../shared/api'

import { ENDPOINTS_REFRESH_INTERVAL, sortEndpointsByLastSeen, OVERVIEW_ENDPOINT_LIMIT } from '../../shared/lib'

import { LoadingCard, ErrorCard, MetricCard, LiveRefreshControl, EndpointIdentity, RelativeTimestamp } from '../../shared/components'

export function DashboardPage() {
  const [now, setNow] = useState(() => Date.now())
  const { data, isLoading, error, dataUpdatedAt, isFetching, refetch } = useQuery({
    queryKey: ['dashboard'],
    queryFn: fetchDashboardData,
    refetchInterval: ENDPOINTS_REFRESH_INTERVAL,
    refetchIntervalInBackground: false,
  })

  useEffect(() => {
    const interval = window.setInterval(() => setNow(Date.now()), ENDPOINTS_REFRESH_INTERVAL)
    return () => window.clearInterval(interval)
  }, [])

  if (isLoading) return <LoadingCard />
  if (error && !data) return <ErrorCard message={error.message} />
  if (!data) return <ErrorCard message="The overview returned no data." />

  const { endpoints, devices } = data
  const onlineCount = endpoints.filter((endpoint) => endpoint.status === 'online').length
  const recentEndpoints = sortEndpointsByLastSeen(endpoints).slice(0, OVERVIEW_ENDPOINT_LIMIT)

  return (
    <div className="dashboard-page">
      <div className="page-header dashboard-page-header">
        <div>
          <p className="eyebrow">Fleet</p>
          <h1>Overview</h1>
          <p className="page-description">Live battery reports and switch connections across your devices.</p>
        </div>
        <div className="dashboard-header-actions">
          <NavLink className="primary-btn" to="/mappings">Create mapping</NavLink>
          <NavLink className="secondary-btn" to="/devices">Manage switches</NavLink>
        </div>
      </div>

      <section className="stats-grid" aria-label="Fleet summary">
        <MetricCard label="Total endpoints" value={String(endpoints.length)} hint="registered devices" icon={MonitorSmartphone} />
        <MetricCard label="Online endpoints" value={String(onlineCount)} hint="seen in the last 10 minutes" icon={CheckCircle2} />
        <MetricCard label="Offline endpoints" value={String(endpoints.length - onlineCount)} hint="not recently reporting" icon={CircleDashed} />
        <MetricCard label="Smart switches" value={String(devices.length)} hint="configured devices" icon={PlugZap} />
      </section>

      <section className="panel table-panel">
        {error && <div className="endpoint-refresh-error"><ErrorCard message={`Could not refresh overview: ${error.message}. Showing the last successful data.`} /></div>}
        <div className="panel-header dashboard-activity-header">
          <div className="dashboard-activity-title">
            <h3>Latest reports</h3>
            <p>Most recently seen devices appear first.</p>
          </div>
          <div className="dashboard-activity-actions">
            <LiveRefreshControl updatedAt={dataUpdatedAt} isFetching={isFetching} onRefresh={() => { void refetch() }} />
            <NavLink to="/endpoints" className="secondary-btn">All endpoints</NavLink>
          </div>
        </div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Device</th><th>Tenant</th><th>Battery</th><th>Power</th><th>Switch</th><th>Switch tenant</th><th>State</th><th aria-sort="descending">Last seen</th></tr></thead>
            <tbody>
              {recentEndpoints.map((endpoint) => (
                <tr key={endpoint.id}>
                  <td><EndpointIdentity endpoint={endpoint} /></td>
                  <td>{endpoint.tenant_name ?? 'Unassigned'}</td>
                  <td>{endpoint.battery}%</td>
                  <td><span className={`badge ${endpoint.charging || endpoint.ac_connected ? 'success' : 'muted'}`}>{endpoint.charging ? 'Charging' : endpoint.ac_connected ? 'On AC' : 'On battery'}</span></td>
                  <td>{endpoint.mapped_device}</td>
                  <td>{endpoint.mapped_device_tenant ?? '—'}</td>
                  <td>{endpoint.switch_state === null ? '—' : endpoint.switch_state ? 'On' : 'Off'}</td>
                  <td><RelativeTimestamp value={endpoint.last_seen_at} now={now} /></td>
                </tr>
              ))}
              {!endpoints.length && <tr><td colSpan={8} className="empty-state">No endpoint telemetry has been received yet.</td></tr>}
            </tbody>
          </table>
        </div>
        {!!endpoints.length && <div className="dashboard-activity-footer">Showing {recentEndpoints.length} of {endpoints.length} endpoints</div>}
      </section>
    </div>
  )
}
