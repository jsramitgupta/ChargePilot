import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { BatteryCharging, ChevronLeft, ChevronRight, Search } from 'lucide-react'

import { useRef, useState } from 'react'

import { NavLink } from 'react-router-dom'

import { useSession } from '../../shared/hooks'

import type { EndpointPageSize, EndpointStatusFilter, TenantInfo, Endpoint, EndpointDetails } from '../../shared/types'

import { apiFetch } from '../../shared/api'

import { ENDPOINTS_REFRESH_INTERVAL, sortEndpointsByLastSeen, PLATFORM_NAMES, formatTimestamp, formatTimestampWithSeconds } from '../../shared/lib'

import { LoadingCard, ErrorCard, LiveRefreshControl, PlatformMark } from '../../shared/components'

import { EndpointDetailsPanel } from './EndpointDetails'

export function EndpointsPage() {
  const queryClient = useQueryClient()
  const { data: user } = useSession()
  const [endpointSearch, setEndpointSearch] = useState('')
  const [pageSize, setPageSize] = useState<EndpointPageSize>(50)
  const [statusFilter, setStatusFilter] = useState<EndpointStatusFilter>('all')
  const [platformFilter, setPlatformFilter] = useState('all')
  const [currentPage, setCurrentPage] = useState(1)
  const [assignedTenantId, setAssignedTenantId] = useState('')
  const [editingEndpointId, setEditingEndpointId] = useState<string | null>(null)
  const [selectedEndpointId, setSelectedEndpointId] = useState<string | null>(null)
  const endpointDetailTriggerRef = useRef<HTMLAnchorElement | null>(null)
  const [labelDraft, setLabelDraft] = useState('')
  const [statusMessage, setStatusMessage] = useState('')
  const canManageEndpoints = user?.role === 'super_admin' || user?.is_admin || user?.role === 'manager'
  const tenantsQuery = useQuery({
    queryKey: ['admin-tenants'],
    queryFn: () => apiFetch<TenantInfo[]>('/api/v1/admin/tenants'),
    enabled: user?.role === 'super_admin',
  })
  const { data, isLoading, error, dataUpdatedAt, isFetching, refetch } = useQuery({
    queryKey: ['endpoints'],
    queryFn: async () => apiFetch<Endpoint[]>('/api/v1/endpoints'),
    refetchInterval: ENDPOINTS_REFRESH_INTERVAL,
    refetchIntervalInBackground: false,
  })
  const endpointDetailsQuery = useQuery({
    queryKey: ['endpoint-details', selectedEndpointId],
    queryFn: () => apiFetch<EndpointDetails>(`/api/v1/endpoints/${selectedEndpointId}/details?limit=100`),
    enabled: Boolean(selectedEndpointId),
    refetchInterval: selectedEndpointId ? ENDPOINTS_REFRESH_INTERVAL : false,
    refetchIntervalInBackground: false,
  })
  const assignTenantMutation = useMutation({
    mutationFn: ({ endpointId, tenantId }: { endpointId: string; tenantId: string }) =>
      apiFetch<{ tenant_id: string; tenant_name: string }>(`/api/v1/endpoints/${endpointId}/tenant`, {
        method: 'PATCH',
        body: JSON.stringify({ tenant_id: tenantId }),
      }),
    onSuccess: ({ tenant_id, tenant_name }) => {
      setAssignedTenantId(tenant_id)
      setStatusMessage(`Endpoint assigned to ${tenant_name}. Reconfigure its agent using that tenant's token.`)
      queryClient.invalidateQueries({ queryKey: ['endpoints'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      queryClient.invalidateQueries({ queryKey: ['mappings'] })
    },
  })
  const revokeCredentialMutation = useMutation({
    mutationFn: (endpointId: string) =>
      apiFetch<{ status: string }>(`/api/v1/endpoints/${endpointId}/credential/revoke`, { method: 'POST' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['endpoints'] }),
  })

  const renameMutation = useMutation({
    mutationFn: ({ endpointId, label }: { endpointId: string; label: string }) =>
      apiFetch<{ id: string; display_name: string }>(`/api/v1/endpoints/${endpointId}/label`, {
        method: 'PATCH',
        body: JSON.stringify({ label }),
      }),
    onSuccess: ({ display_name }) => {
      setEditingEndpointId(null)
      setAssignedTenantId('')
      setStatusMessage(`Device label changed to ${display_name}.`)
      queryClient.invalidateQueries({ queryKey: ['endpoints'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      queryClient.invalidateQueries({ queryKey: ['mappings'] })
      queryClient.invalidateQueries({ queryKey: ['events'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (endpointId: string) => apiFetch<void>(`/api/v1/endpoints/${endpointId}`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['endpoints'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })

  if (isLoading) return <LoadingCard />
  if (error && !data) return <ErrorCard message={error.message} />
  if (!data) return <ErrorCard message="The endpoint list returned no data." />

  const searchTerm = endpointSearch.trim().toLocaleLowerCase()
  const filteredEndpoints = sortEndpointsByLastSeen(data).filter((endpoint) => {
    if (statusFilter !== 'all' && endpoint.status !== statusFilter) return false
    if (platformFilter !== 'all' && endpoint.platform !== platformFilter) return false
    if (!searchTerm) return true
    const searchable = [
      endpoint.display_name ?? '',
      endpoint.hostname,
      endpoint.platform,
      endpoint.tenant_name ?? '',
      endpoint.ip_address ?? '',
      endpoint.status,
    ].join(' ').toLocaleLowerCase()
    return searchable.includes(searchTerm)
  })
  const totalPages = Math.max(1, Math.ceil(filteredEndpoints.length / pageSize))
  const visiblePage = Math.min(currentPage, totalPages)
  const firstRow = filteredEndpoints.length ? (visiblePage - 1) * pageSize + 1 : 0
  const lastRow = Math.min(visiblePage * pageSize, filteredEndpoints.length)
  const visibleEndpoints = filteredEndpoints.slice(firstRow - 1, lastRow)
  const onlineCount = data.filter((endpoint) => endpoint.status === 'online').length
  const offlineCount = data.length - onlineCount
  const mappedEndpointCount = data.filter((endpoint) => Boolean(endpoint.mapped_device)).length

  return (
    <div className="endpoint-management-page">
      <div className="page-header endpoint-page-header">
        <div>
          <h1>Endpoints</h1>
          <p className="page-description">Manage enrolled devices, check health, and review recent reports.</p>
        </div>
        <LiveRefreshControl updatedAt={dataUpdatedAt} isFetching={isFetching} onRefresh={() => { void refetch() }} />
      </div>
      <section className="endpoint-overview-strip" aria-label="Endpoint fleet summary">
        <div><span>All devices</span><strong>{data.length}</strong></div>
        <div><span>Online</span><strong className="endpoint-count-online">{onlineCount}</strong></div>
        <div><span>Offline</span><strong className="endpoint-count-offline">{offlineCount}</strong></div>
        <div><span>Mapped to switches</span><strong>{mappedEndpointCount}</strong></div>
      </section>
      {statusMessage && <p className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800" role="status">{statusMessage}{assignedTenantId && <> <NavLink to={`/agent?tenant_id=${assignedTenantId}`} className="font-semibold underline">Open tenant agent setup</NavLink></>}</p>}
      {assignTenantMutation.error && <ErrorCard message={assignTenantMutation.error.message} />}
      {renameMutation.error && <ErrorCard message={renameMutation.error.message} />}
      {deleteMutation.isError && <ErrorCard message={deleteMutation.error.message} />}
      {revokeCredentialMutation.error && <ErrorCard message={revokeCredentialMutation.error.message} />}
      {error && <ErrorCard message={`Could not refresh endpoints: ${error.message}. Showing the last successful data.`} />}
      <section className="panel table-panel endpoint-inventory">
        <div className="panel-header endpoint-panel-header">
          <div className="endpoint-panel-title">
            <h3>Device inventory</h3>
            <p>{filteredEndpoints.length} {filteredEndpoints.length === 1 ? 'device' : 'devices'} shown · sorted by most recent report</p>
          </div>
        </div>
        <div className="endpoint-list-toolbar">
          <label className="switch-search endpoint-search" htmlFor="endpoint-search">
            <Search size={17} aria-hidden="true" />
            <input id="endpoint-search" type="search" value={endpointSearch} onChange={(event) => {
              setEndpointSearch(event.target.value)
              setCurrentPage(1)
            }} placeholder="Search devices, platform, tenant, IP" />
          </label>
          <label className="endpoint-filter-select">
            <span className="sr-only">Filter by platform</span>
            <select value={pageSize} onChange={(event) => {
              setPageSize(event.target.value === '100' ? 100 : 50)
              setCurrentPage(1)
            }}>
              <option value={50}>50 per page</option>
              <option value={100}>100 per page</option>
            </select>
          </label>
          <label className="endpoint-filter-select">
            <span className="sr-only">Platform</span>
            <select value={platformFilter} onChange={(event) => { setPlatformFilter(event.target.value); setCurrentPage(1) }}>
              <option value="all">All platforms</option>
              {Object.entries(PLATFORM_NAMES).map(([platform, label]) => <option key={platform} value={platform}>{label}</option>)}
            </select>
          </label>
        </div>
        <div className="endpoint-status-tabs" role="group" aria-label="Filter by device status">
          {([
            ['all', 'All devices', data.length],
            ['online', 'Online', onlineCount],
            ['offline', 'Offline', offlineCount],
          ] as const).map(([filter, label, count]) => <button
            type="button"
            key={filter}
            className={statusFilter === filter ? 'is-active' : ''}
            aria-pressed={statusFilter === filter}
            onClick={() => { setStatusFilter(filter); setCurrentPage(1) }}
          >{label}<span>{count}</span></button>)}
        </div>
        <div className="table-wrap">
          <table className="endpoint-inventory-table">
            <thead><tr><th>Device</th><th>Workspace</th><th>Enrollment</th><th>Battery</th><th aria-sort="descending">Last report</th><th>Status</th><th className="align-right">Actions</th></tr></thead>
            <tbody>
              {visibleEndpoints.map((endpoint) => <tr key={endpoint.id}>
                <td className="endpoint-device-cell">
                  <div className="endpoint-device-row">
                    <PlatformMark platform={endpoint.platform} />
                    <div className="endpoint-device-copy">
                      <a
                        href="#endpoint-details"
                        className="endpoint-device-link"
                        aria-haspopup="dialog"
                        aria-expanded={selectedEndpointId === endpoint.id}
                        onClick={(event) => {
                          event.preventDefault()
                          endpointDetailTriggerRef.current = event.currentTarget
                          setSelectedEndpointId(endpoint.id)
                        }}
                      >{endpoint.display_name || endpoint.hostname}</a>
                      <span>{PLATFORM_NAMES[endpoint.platform]}{endpoint.device_class ? ` · ${endpoint.device_class}` : ''} · {endpoint.hostname}</span>
                    </div>
                  </div>
                  <div className="endpoint-label-actions">
                    {canManageEndpoints && editingEndpointId === endpoint.id ? (
                      <form className="endpoint-label-form" onSubmit={(event) => {
                        event.preventDefault()
                        renameMutation.mutate({ endpointId: endpoint.id, label: labelDraft })
                      }}>
                        <input
                          autoFocus
                          aria-label={`New label for ${endpoint.display_name || endpoint.hostname}`}
                          className="field min-w-32 py-2"
                          maxLength={160}
                          required
                          value={labelDraft}
                          onChange={(event) => setLabelDraft(event.target.value)}
                        />
                        <button type="submit" className="btn-secondary px-3 py-2" disabled={renameMutation.isPending}>Save</button>
                        <button type="button" className="secondary-btn px-3 py-2" disabled={renameMutation.isPending} onClick={() => setEditingEndpointId(null)}>Cancel</button>
                      </form>
                    ) : canManageEndpoints ? (
                      <button type="button" className="endpoint-row-action" onClick={() => {
                        setEditingEndpointId(endpoint.id)
                        setLabelDraft(endpoint.display_name || endpoint.hostname)
                        renameMutation.reset()
                      }}>Edit label</button>
                    ) : null}
                  </div>
                </td>
                <td>{endpoint.tenant_id ? endpoint.tenant_name ?? 'Unknown workspace' : user?.role === 'super_admin' ? <div className="flex min-w-56 flex-col gap-2"><span className="badge muted w-fit">Unassigned</span><form className="flex items-center gap-2" onSubmit={(event) => {
                  event.preventDefault()
                  const tenantId = String(new FormData(event.currentTarget).get('tenant_id') ?? '')
                  if (tenantId) assignTenantMutation.mutate({ endpointId: endpoint.id, tenantId })
                }}>
                  <select name="tenant_id" aria-label={`Tenant for ${endpoint.hostname}`} required className="field min-w-32 py-2"><option value="">Unassigned</option>{(tenantsQuery.data ?? []).map((tenant) => <option key={tenant.id} value={tenant.id}>{tenant.name}</option>)}</select>
                  <button type="submit" className="btn-secondary px-3 py-2" disabled={assignTenantMutation.isPending}>Assign</button>
                </form></div> : 'Unassigned'}</td>
                <td><span className={`endpoint-enrollment ${endpoint.credential_enrolled ? 'is-enrolled' : 'is-legacy'}`}><span />{endpoint.credential_enrolled ? 'Managed' : 'Legacy token'}</span></td>
                <td><div className="endpoint-battery-cell"><BatteryCharging size={16} aria-hidden="true" /><strong>{endpoint.battery}%</strong><span>{endpoint.charging ? 'Charging' : endpoint.ac_connected ? 'On AC' : 'On battery'}</span></div></td>
                <td className="endpoint-last-seen"><time dateTime={endpoint.last_seen_at ?? undefined}>{formatTimestamp(endpoint.last_seen_at)}</time><small>{formatTimestampWithSeconds(endpoint.last_seen_at)}</small></td>
                <td><span className={`badge ${endpoint.status === 'online' ? 'success' : 'muted'}`}>{endpoint.status}</span></td>
                <td className="align-right"><div className="endpoint-row-actions">
                  {endpoint.credential_enrolled && <button type="button" className="endpoint-row-action is-danger" disabled={revokeCredentialMutation.isPending} onClick={() => {
                    if (window.confirm(`Revoke the installation credential for ${endpoint.display_name || endpoint.hostname}? Its agent will stop reporting.`)) revokeCredentialMutation.mutate(endpoint.id)
                  }}>Revoke</button>}
                  <button type="button" className="endpoint-row-action is-danger" disabled={deleteMutation.isPending} onClick={() => {
                    if (window.confirm(`Delete endpoint ${endpoint.display_name || endpoint.hostname}? Its mappings and event history will also be removed.`)) deleteMutation.mutate(endpoint.id)
                  }}>Remove</button>
                </div></td>
              </tr>)}
              {!filteredEndpoints.length && <tr><td colSpan={7} className="empty-state">{data.length ? 'No devices match these filters. Clear a filter or try another search.' : 'No endpoints have reported telemetry yet. Enroll a device to see it here.'}</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="endpoint-pagination">
          <p aria-live="polite">{filteredEndpoints.length ? `Showing ${firstRow}–${lastRow} of ${filteredEndpoints.length} endpoints` : 'No endpoints to display'}</p>
          <nav aria-label="Endpoint pages">
            <button type="button" className="secondary-btn" disabled={visiblePage <= 1} onClick={() => setCurrentPage(visiblePage - 1)}><ChevronLeft size={15} aria-hidden="true" />Previous</button>
            <span>Page {visiblePage} of {totalPages}</span>
            <button type="button" className="secondary-btn" disabled={visiblePage >= totalPages} onClick={() => setCurrentPage(visiblePage + 1)}>Next<ChevronRight size={15} aria-hidden="true" /></button>
          </nav>
        </div>
      </section>
      {selectedEndpointId && <EndpointDetailsPanel
        details={endpointDetailsQuery.data}
        isLoading={endpointDetailsQuery.isLoading}
        error={endpointDetailsQuery.error}
        onClose={() => {
          setSelectedEndpointId(null)
          window.requestAnimationFrame(() => endpointDetailTriggerRef.current?.focus())
        }}
      />}
    </div>
  )
}
