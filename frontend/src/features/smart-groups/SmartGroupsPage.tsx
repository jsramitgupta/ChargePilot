import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { useState } from 'react'

import { useSession } from '../../shared/hooks'

import { apiFetch } from '../../shared/api'

import { type SmartGroup, type SensorDefinition, type Endpoint, type SmartGroupTenant, type SmartGroupCriteria } from '../../shared/types'

import { ENDPOINTS_REFRESH_INTERVAL } from '../../shared/lib'

import { LoadingCard, ErrorCard, PageHeader } from '../../shared/components'

export function SmartGroupsPage() {
  const { data: user } = useSession()
  const queryClient = useQueryClient()
  const isSuperAdmin = user?.role === 'super_admin'
  const canManage = isSuperAdmin || user?.role === 'tenant_admin' || user?.role === 'manager'
  const [name, setName] = useState('')
  const [targetMode, setTargetMode] = useState<'rules' | 'devices'>('rules')
  const [platforms, setPlatforms] = useState<Array<'windows' | 'macos'>>(['windows', 'macos'])
  const [selectedEndpointIds, setSelectedEndpointIds] = useState<string[]>([])
  const [nameContains, setNameContains] = useState('')
  const [batteryMin, setBatteryMin] = useState('')
  const [batteryMax, setBatteryMax] = useState('')
  const [sensorIds, setSensorIds] = useState<string[]>(['os_version'])
  const [tenantId, setTenantId] = useState(user?.tenant_id ?? '')
  const [editingGroupId, setEditingGroupId] = useState<string | null>(null)
  const [deletingGroupId, setDeletingGroupId] = useState<string | null>(null)

  const groupsQuery = useQuery({
    queryKey: ['smart-groups'],
    queryFn: () => apiFetch<SmartGroup[]>('/api/v1/smart-groups'),
    refetchInterval: 15_000,
  })
  const catalogQuery = useQuery({
    queryKey: ['sensor-catalog'],
    queryFn: () => apiFetch<SensorDefinition[]>('/api/v1/smart-groups/catalog'),
  })
  const endpointsQuery = useQuery({
    queryKey: ['sensor-endpoints'],
    queryFn: () => apiFetch<Endpoint[]>('/api/v1/endpoints'),
    refetchInterval: ENDPOINTS_REFRESH_INTERVAL,
  })
  const tenantsQuery = useQuery({
    queryKey: ['smart-group-tenants'],
    queryFn: () => apiFetch<SmartGroupTenant[]>('/api/v1/smart-groups/tenants'),
    enabled: Boolean(isSuperAdmin),
  })
  const selectedTenantId = tenantId || user?.tenant_id || tenantsQuery.data?.[0]?.id || ''

  const saveMutation = useMutation({
    mutationFn: () => {
      const selectedEndpoints = (endpointsQuery.data ?? []).filter((endpoint) => selectedEndpointIds.includes(endpoint.id))
      const selectedPlatforms = targetMode === 'devices'
        ? [...new Set(selectedEndpoints.map((endpoint) => endpoint.platform))] as Array<'windows' | 'macos'>
        : platforms
      if (!selectedPlatforms.length) throw new Error('Choose at least one Windows or macOS platform.')
      if (targetMode === 'devices' && !selectedEndpoints.length) throw new Error('Select at least one enrolled device.')
      const criteria: SmartGroupCriteria = {
        platforms: selectedPlatforms,
        endpoint_ids: targetMode === 'devices' ? selectedEndpointIds : null,
        name_contains: nameContains.trim() || null,
        battery_min: batteryMin === '' ? null : Number(batteryMin),
        battery_max: batteryMax === '' ? null : Number(batteryMax),
      }
      const payload = { name: name.trim(), criteria, sensor_ids: sensorIds }
      const basePath = '/api/v1/smart-groups'
      if (editingGroupId) {
        return apiFetch<SmartGroup>(`${basePath}/${editingGroupId}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        })
      }
      const tenantQuery = isSuperAdmin ? `?tenant_id=${encodeURIComponent(selectedTenantId)}` : ''
      return apiFetch<SmartGroup>(`${basePath}${tenantQuery}`, {
        method: 'POST',
        body: JSON.stringify(payload),
      })
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['smart-groups'] })
      setEditingGroupId(null)
      setName('')
      setTargetMode('rules')
      setPlatforms(['windows', 'macos'])
      setSelectedEndpointIds([])
      setNameContains('')
      setBatteryMin('')
      setBatteryMax('')
      setSensorIds(['os_version'])
    },
  })
  const runMutation = useMutation({
    mutationFn: (groupId: string) => apiFetch<{ queued_endpoints: number; queued_sensors: number }>(
      `/api/v1/smart-groups/${groupId}/run`,
      { method: 'POST' },
    ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['smart-groups'] }),
  })
  const deleteMutation = useMutation({
    mutationFn: (groupId: string) => apiFetch<void>(`/api/v1/smart-groups/${groupId}`, { method: 'DELETE' }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['smart-groups'] })
      setDeletingGroupId(null)
      if (editingGroupId === deletingGroupId) resetEditor()
    },
  })

  const eligibleEndpoints = (endpointsQuery.data ?? []).filter((endpoint) => (
    (endpoint.platform === 'windows' || endpoint.platform === 'macos')
      && endpoint.credential_enrolled
    && endpoint.enabled
      && (!isSuperAdmin || !selectedTenantId || endpoint.tenant_id === selectedTenantId)
  ))

  function resetEditor() {
    setEditingGroupId(null)
    setName('')
    setTargetMode('rules')
    setPlatforms(['windows', 'macos'])
    setSelectedEndpointIds([])
    setNameContains('')
    setBatteryMin('')
    setBatteryMax('')
    setSensorIds(['os_version'])
  }

  function editGroup(group: SmartGroup) {
    setEditingGroupId(group.id)
    setTenantId(group.tenant_id)
    setName(group.name)
    setTargetMode(group.criteria.endpoint_ids?.length ? 'devices' : 'rules')
    setPlatforms(group.criteria.platforms)
    setSelectedEndpointIds(group.criteria.endpoint_ids ?? [])
    setNameContains(group.criteria.name_contains ?? '')
    setBatteryMin(group.criteria.battery_min == null ? '' : String(group.criteria.battery_min))
    setBatteryMax(group.criteria.battery_max == null ? '' : String(group.criteria.battery_max))
    setSensorIds(group.sensor_ids)
    window.scrollTo({
      top: 0,
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth',
    })
  }

  function togglePlatform(platform: 'windows' | 'macos') {
    setPlatforms((current) => current.includes(platform)
      ? current.filter((value) => value !== platform)
      : [...current, platform])
  }

  function toggleEndpoint(endpointId: string) {
    setSelectedEndpointIds((current) => current.includes(endpointId)
      ? current.filter((value) => value !== endpointId)
      : [...current, endpointId])
  }

  function toggleSensor(sensorId: string) {
    setSensorIds((current) => current.includes(sensorId)
      ? current.filter((value) => value !== sensorId)
      : [...current, sensorId])
  }

  if (groupsQuery.isLoading || catalogQuery.isLoading) return <LoadingCard />
  if (groupsQuery.error && !groupsQuery.data) return <ErrorCard message={groupsQuery.error.message} />
  if (catalogQuery.error && !catalogQuery.data) return <ErrorCard message={catalogQuery.error.message} />

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Endpoint inventory"
        title="Smart Groups & Sensors"
        description="Target enrolled Windows and macOS devices, then collect a small set of approved system facts."
      />
      <p className="panel-muted p-4 text-sm leading-6">
        Sensors are fixed, read-only checks. ChargePilot does not send shell commands or uploaded scripts.
        Windows collection runs as a service; macOS collection runs while the menu-bar agent is open in a signed-in session.
      </p>
      {(groupsQuery.error || catalogQuery.error || endpointsQuery.error || tenantsQuery.error) && (
        <ErrorCard message={
          groupsQuery.error?.message
            ?? catalogQuery.error?.message
            ?? endpointsQuery.error?.message
            ?? tenantsQuery.error?.message
            ?? 'Could not load sensor management data.'
        } />
      )}
      {!canManage && (
        <p className="panel-muted p-4 text-sm">You can review Smart Groups and recent sensor results. Ask a workspace manager to create or run a group.</p>
      )}
      <div className="grid items-start gap-5 xl:grid-cols-[minmax(19rem,0.82fr)_minmax(0,1.18fr)]">
        {canManage && (
          <section className="panel p-5 sm:p-6" aria-labelledby="sensor-group-editor-title">
            <div className="mb-5">
              <h3 id="sensor-group-editor-title" className="text-lg font-semibold text-slate-900">
                {editingGroupId ? 'Edit Smart Group' : 'Create a Smart Group'}
              </h3>
              <p className="mt-1 text-sm leading-5 text-slate-600">Choose the devices and the read-only values to collect.</p>
            </div>
            <form className="space-y-5" onSubmit={(event) => { event.preventDefault(); saveMutation.mutate() }}>
              {isSuperAdmin && (
                <label className="label" htmlFor="sensor-tenant">
                  Workspace
                  <select id="sensor-tenant" className="field" value={selectedTenantId} onChange={(event) => { setTenantId(event.target.value); setSelectedEndpointIds([]) }} required disabled={Boolean(editingGroupId)}>
                    <option value="">Choose a workspace</option>
                    {(tenantsQuery.data ?? []).map((tenant) => <option key={tenant.id} value={tenant.id}>{tenant.name}</option>)}
                  </select>
                </label>
              )}
              <label className="label" htmlFor="sensor-group-name">
                Group name
                <input id="sensor-group-name" className="field" value={name} onChange={(event) => setName(event.target.value)} maxLength={120} required placeholder="Field laptops" />
              </label>
              <fieldset className="space-y-2">
                <legend className="label">Target devices</legend>
                <label className="flex items-start gap-2 text-sm">
                  <input type="radio" name="sensor-target-mode" checked={targetMode === 'rules'} onChange={() => setTargetMode('rules')} />
                  <span><strong>Use group rules</strong><small className="block text-slate-500">Keep matching enrolled devices in the group as they report.</small></span>
                </label>
                <label className="flex items-start gap-2 text-sm">
                  <input type="radio" name="sensor-target-mode" checked={targetMode === 'devices'} onChange={() => setTargetMode('devices')} />
                  <span><strong>Choose specific devices</strong><small className="block text-slate-500">Run against one or more endpoints you select.</small></span>
                </label>
              </fieldset>
              {targetMode === 'rules' ? (
                <fieldset className="space-y-3 rounded-xl border border-slate-200 p-4">
                  <legend className="px-1 text-sm font-semibold">Match rules</legend>
                  <div className="flex flex-wrap gap-4">
                    {(['windows', 'macos'] as const).map((platform) => (
                      <label key={platform} className="flex items-center gap-2 text-sm">
                        <input type="checkbox" checked={platforms.includes(platform)} onChange={() => togglePlatform(platform)} />
                        {platform === 'macos' ? 'macOS' : 'Windows'}
                      </label>
                    ))}
                  </div>
                  <label className="label" htmlFor="sensor-name-match">
                    Device name contains
                    <input id="sensor-name-match" className="field" value={nameContains} onChange={(event) => setNameContains(event.target.value)} maxLength={80} placeholder="Optional" />
                  </label>
                </fieldset>
              ) : (
                <fieldset className="space-y-2 rounded-xl border border-slate-200 p-4">
                  <legend className="px-1 text-sm font-semibold">Select enrolled devices</legend>
                  {!endpointsQuery.data && <p className="text-sm text-slate-500">Loading endpoint inventory…</p>}
                  {endpointsQuery.data && eligibleEndpoints.length === 0 && (
                    <p className="text-sm text-slate-500">No enrolled Windows or macOS devices are available in this workspace.</p>
                  )}
                  <div className="max-h-56 space-y-1 overflow-y-auto">
                    {eligibleEndpoints.map((endpoint) => (
                      <label key={endpoint.id} className="flex cursor-pointer items-center justify-between gap-3 rounded-lg px-2 py-2 text-sm hover:bg-slate-50">
                        <span className="flex min-w-0 items-center gap-2">
                          <input type="checkbox" checked={selectedEndpointIds.includes(endpoint.id)} onChange={() => toggleEndpoint(endpoint.id)} />
                          <span className="truncate">{endpoint.display_name || endpoint.hostname}</span>
                        </span>
                        <span className="shrink-0 text-xs text-slate-500">{endpoint.platform === 'macos' ? 'macOS' : 'Windows'} · {endpoint.status}</span>
                      </label>
                    ))}
                  </div>
                  <p className="text-xs text-slate-500">Only the selected endpoints are included. Offline devices queue nothing until they report again.</p>
                </fieldset>
              )}
              <fieldset className="space-y-3 rounded-xl border border-slate-200 p-4">
                <legend className="px-1 text-sm font-semibold">Optional battery filter</legend>
                <div className="grid grid-cols-2 gap-3">
                  <label className="label" htmlFor="sensor-battery-min">At least
                    <input id="sensor-battery-min" className="field" inputMode="numeric" type="number" min={0} max={100} value={batteryMin} onChange={(event) => setBatteryMin(event.target.value)} placeholder="Any" />
                  </label>
                  <label className="label" htmlFor="sensor-battery-max">At most
                    <input id="sensor-battery-max" className="field" inputMode="numeric" type="number" min={0} max={100} value={batteryMax} onChange={(event) => setBatteryMax(event.target.value)} placeholder="Any" />
                  </label>
                </div>
              </fieldset>
              <fieldset className="space-y-2">
                <legend className="label">Sensors</legend>
                {(catalogQuery.data ?? []).map((sensor) => (
                  <label key={sensor.id} className="flex cursor-pointer items-start gap-3 rounded-xl border border-slate-200 p-3">
                    <input type="checkbox" checked={sensorIds.includes(sensor.id)} onChange={() => toggleSensor(sensor.id)} />
                    <span><strong className="block text-sm">{sensor.name}</strong><small className="text-xs text-slate-500">{sensor.description}</small></span>
                  </label>
                ))}
              </fieldset>
              {saveMutation.error && <ErrorCard message={saveMutation.error.message} />}
              <div className="flex flex-wrap gap-2">
                <button type="submit" className="btn-primary" disabled={saveMutation.isPending || !name.trim() || sensorIds.length === 0 || (isSuperAdmin && !selectedTenantId)}>
                  {saveMutation.isPending ? 'Saving…' : editingGroupId ? 'Save changes' : 'Create group'}
                </button>
                {editingGroupId && <button type="button" className="btn-secondary" onClick={resetEditor}>Cancel</button>}
              </div>
            </form>
          </section>
        )}
        <div className="space-y-5">
          <section className="panel overflow-hidden" aria-labelledby="smart-groups-title">
            <div className="flex flex-wrap items-end justify-between gap-3 border-b border-slate-200 px-5 py-4">
              <div>
                <h3 id="smart-groups-title" className="text-lg font-semibold text-slate-900">Your Smart Groups</h3>
                <p className="mt-1 text-sm text-slate-600">Membership uses tenant ownership, enrollment, and fresh endpoint reports.</p>
              </div>
              <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold">{groupsQuery.data?.length ?? 0} groups</span>
            </div>
            {!groupsQuery.data?.length ? (
              <div className="p-6 text-sm text-slate-600">{canManage ? 'Create a group to begin collecting system facts.' : 'No Smart Groups have been created for this workspace.'}</div>
            ) : (
              <div className="divide-y divide-slate-100">
                {groupsQuery.data.map((group) => (
                  <article key={group.id} className="p-5">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <h4 className="font-semibold text-slate-900">{group.name}</h4>
                        {isSuperAdmin && <p className="mt-1 text-xs text-slate-500">{group.tenant_name}</p>}
                        <p className="mt-1 text-sm text-slate-600">
                          {group.matching_endpoint_count} fresh device{group.matching_endpoint_count === 1 ? '' : 's'} · {group.sensor_ids.length} sensor{group.sensor_ids.length === 1 ? '' : 's'}
                        </p>
                      </div>
                      <div className="flex gap-2">
                        {canManage && <button type="button" className="btn-secondary px-3 py-2 text-xs" onClick={() => editGroup(group)}>Edit</button>}
                        {canManage && <button type="button" className="btn-secondary px-3 py-2 text-xs" onClick={() => setDeletingGroupId(group.id)} disabled={deleteMutation.isPending}>Delete</button>}
                        {canManage && <button type="button" className="btn-primary px-3 py-2 text-xs" disabled={runMutation.isPending || group.matching_endpoint_count === 0 || group.sensor_ids.length === 0} onClick={() => runMutation.mutate(group.id)}>{runMutation.isPending ? 'Queueing…' : 'Run now'}</button>}
                      </div>
                    </div>
                    {deletingGroupId === group.id && (
                      <div className="alert error mt-4 flex flex-wrap items-center justify-between gap-3 p-3 text-sm">
                        <span>Delete this group and its stored sensor results?</span>
                        <div className="flex gap-2">
                          <button type="button" className="btn-secondary px-3 py-2 text-xs" onClick={() => setDeletingGroupId(null)}>Keep group</button>
                          <button type="button" className="danger-btn small-btn" disabled={deleteMutation.isPending} onClick={() => deleteMutation.mutate(group.id)}>{deleteMutation.isPending ? 'Deleting…' : 'Delete group'}</button>
                        </div>
                      </div>
                    )}
                    <div className="mt-3 flex flex-wrap gap-2">
                      {group.sensor_ids.map((sensorId) => (
                        <span key={sensorId} className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs">
                          {(catalogQuery.data ?? []).find((sensor) => sensor.id === sensorId)?.name ?? sensorId}
                        </span>
                      ))}
                    </div>
                    {!!group.matching_endpoints.length && (
                      <p className="mt-3 text-xs leading-5 text-slate-500">
                        Ready now: {group.matching_endpoints.slice(0, 5).map((endpoint) => endpoint.name).join(', ')}
                        {group.matching_endpoints.length > 5 ? ` and ${group.matching_endpoint_count - 5} more` : ''}
                      </p>
                    )}
                    {!!group.recent_executions.length && (
                      <div className="mt-4 overflow-x-auto">
                        <table className="w-full min-w-[34rem] text-left text-xs">
                          <thead><tr className="border-b border-slate-200 text-slate-500"><th className="py-2 pr-3 font-medium">Device</th><th className="py-2 pr-3 font-medium">Sensor</th><th className="py-2 pr-3 font-medium">Result</th><th className="py-2 font-medium">State</th></tr></thead>
                          <tbody>
                            {group.recent_executions.slice(0, 8).map((execution) => (
                              <tr key={execution.id} className="border-b border-slate-100 last:border-0">
                                <td className="max-w-40 truncate py-2 pr-3">{execution.endpoint_name}</td>
                                <td className="py-2 pr-3">{execution.sensor_name}</td>
                                <td className="max-w-48 truncate py-2 pr-3" title={execution.error ?? undefined}>
                                  {execution.result?.value === undefined ? execution.error ?? '—' : String(execution.result.value)}
                                </td>
                                <td className="py-2">{execution.status}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </article>
                ))}
              </div>
            )}
          </section>
          {runMutation.error && <ErrorCard message={runMutation.error.message} />}
          {deleteMutation.error && <ErrorCard message={deleteMutation.error.message} />}
          {runMutation.data && (
            <p className="panel-muted p-4 text-sm" role="status">
              Queued {runMutation.data.queued_sensors} sensor check{runMutation.data.queued_sensors === 1 ? '' : 's'} across {runMutation.data.queued_endpoints} fresh device{runMutation.data.queued_endpoints === 1 ? '' : 's'}.
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
