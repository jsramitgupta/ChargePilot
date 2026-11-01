import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { zodResolver } from '@hookform/resolvers/zod'

import { List, LayoutGrid, PlugZap, Plus, Search } from 'lucide-react'

import { useEffect, useRef, useState } from 'react'

import { useForm, useWatch } from 'react-hook-form'

import { NavLink } from 'react-router-dom'

import { deviceSchema } from '../../shared/types'

import type { Device, DeviceMeterSettings, LanDevice, SmartLifeDevice, DevicesPageData, DeviceChannel, DeviceStatusRefresh, Connector, DeviceFormInput, DeviceFormValues } from '../../shared/types'

import { formatTimestamp } from '../../shared/lib'

import { apiFetch, setDeviceState, waitForConnectorCommands } from '../../shared/api'

import { useSession } from '../../shared/hooks'

import { LoadingCard, ErrorCard, MetricMini, FieldError } from '../../shared/components'

import { DeviceMeterPanel } from './DeviceMeterPanel'

export function DevicesPage() {
  const queryClient = useQueryClient()
  const { data: user } = useSession()
  const [currentMonth, setCurrentMonth] = useState(() => new Date().toISOString().slice(0, 7))
  const [meterNow, setMeterNow] = useState(() => Date.now())
  const [manualOpen, setManualOpen] = useState(false)
  const [switchView, setSwitchView] = useState<'cards' | 'list'>('cards')
  const [switchFilter, setSwitchFilter] = useState<'all' | 'on' | 'off' | 'unassigned'>('all')
  const [switchSearch, setSwitchSearch] = useState('')
  const [smartLifeOpen, setSmartLifeOpen] = useState(false)
  const [scanLocation, setScanLocation] = useState('server')
  const [discovered, setDiscovered] = useState<LanDevice[]>([])
  const [selectedLanDeviceId, setSelectedLanDeviceId] = useState('')
  const selectedLanDeviceIdRef = useRef('')
  const [linkedDevices, setLinkedDevices] = useState<SmartLifeDevice[]>([])
  const [qr, setQr] = useState('')
  const [smartLifeStatus, setSmartLifeStatus] = useState('')
  const [statusMessage, setStatusMessage] = useState('')

  useEffect(() => {
    const interval = window.setInterval(() => {
      setCurrentMonth(new Date().toISOString().slice(0, 7))
      setMeterNow(Date.now())
    }, 60_000)
    return () => window.clearInterval(interval)
  }, [])
  const [smartLifeUserCode, setSmartLifeUserCode] = useState<string | null>(null)
  const [qrScheme, setQrScheme] = useState('smartlife')
  const [rememberUserCode, setRememberUserCode] = useState<boolean | null>(null)
  const smartLifeAccountCode = smartLifeUserCode ?? user?.smartlife_user_code ?? ''
  const shouldRememberUserCode = rememberUserCode ?? Boolean(user?.smartlife_user_code)
  const pollTimer = useRef<number | null>(null)

  const { data, isLoading, error } = useQuery<DevicesPageData>({
    queryKey: ['devices'],
    queryFn: async () => {
      const devices = await apiFetch<Device[]>('/api/v1/devices')
      return {
        devices: await Promise.all(devices.map(async (device) => ({
          ...device,
          channels: await apiFetch<DeviceChannel[]>(`/api/v1/devices/${device.id}/channels`),
        }))),
      }
    },
    refetchInterval: 5 * 60 * 1000,
    refetchIntervalInBackground: false,
  })
  const {
    data: statusRefresh,
    dataUpdatedAt: statusRefreshUpdatedAt,
    error: statusRefreshError,
  } = useQuery<DeviceStatusRefresh>({
    queryKey: ['device-status-refresh'],
    queryFn: async () => {
      const refresh = await apiFetch<DeviceStatusRefresh>('/api/v1/devices/status/refresh', {
        method: 'POST',
      })
      await waitForConnectorCommands(refresh.commands, 30_000)
      return refresh
    },
    enabled: data !== undefined,
    retry: false,
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
    refetchIntervalInBackground: false,
  })
  useEffect(() => {
    if (statusRefreshUpdatedAt) {
      void queryClient.invalidateQueries({ queryKey: ['devices'] })
    }
  }, [queryClient, statusRefreshUpdatedAt])
  const { data: connectors = [] } = useQuery({
    queryKey: ['connectors'],
    queryFn: () => apiFetch<Connector[]>('/api/v1/connectors'),
  })

  const form = useForm<DeviceFormInput, unknown, DeviceFormValues>({
    resolver: zodResolver(deviceSchema),
    defaultValues: {
      name: '',
      device_id: '',
      ip_address: '',
      device_type: 'switch',
      protocol_version: '3.5',
      encrypted_local_key: '',
      enabled: true,
      channel_count: 1,
      connector_id: '',
    },
  })
  const selectedSetupConnectorId = useWatch({ control: form.control, name: 'connector_id' })

  const connectorMutation = useMutation({
    mutationFn: ({ deviceId, connectorId }: { deviceId: string; connectorId: string }) =>
      apiFetch<{ message: string }>(`/api/v1/devices/${deviceId}/connector`, {
        method: 'PUT',
        body: JSON.stringify({ connector_id: connectorId || null }),
      }),
    onSuccess: ({ message }) => {
      setStatusMessage(message)
      queryClient.invalidateQueries({ queryKey: ['devices'] })
    },
  })

  const meterMutation = useMutation({
    mutationFn: ({ deviceId, settings }: { deviceId: string; settings: DeviceMeterSettings }) =>
      apiFetch<Device>(`/api/v1/devices/${deviceId}/meter-settings`, {
        method: 'PUT',
        body: JSON.stringify(settings),
      }),
    onSuccess: () => {
      setStatusMessage('Meter settings saved. The site connector will collect the next reading within about a minute.')
      queryClient.invalidateQueries({ queryKey: ['devices'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })

  const mutation = useMutation({
    mutationFn: async (values: DeviceFormValues) => {
      const { channel_count, connector_id, ...devicePayload } = values
      const routeConnector = connectors.find((connector) => connector.id === connector_id)
      const deviceTenantId = user?.role === 'super_admin'
        ? routeConnector?.tenant_id ?? null
        : user?.tenant_id ?? null
      const device = await apiFetch<Device>('/api/v1/devices', {
        method: 'POST',
        body: JSON.stringify({ ...devicePayload, tenant_id: deviceTenantId }),
      })
      for (let index = 1; index <= channel_count; index += 1) {
        await apiFetch<DeviceChannel>(`/api/v1/devices/${device.id}/channels`, {
          method: 'POST',
          body: JSON.stringify({
            channel_index: index,
            name: `Channel ${index}`,
            dp_id: String(index),
            enabled: true,
          }),
        })
      }
      return { device, connectorId: connector_id }
    },
    onSuccess: ({ device, connectorId }) => {
      queryClient.invalidateQueries({ queryKey: ['devices'] })
      form.reset()
      setManualOpen(false)
      setSelectedLanDeviceId('')
      setStatusMessage('Switch added.')
      if (connectorId) connectorMutation.mutate({ deviceId: device.id, connectorId })
    },
    onError: () => queryClient.invalidateQueries({ queryKey: ['devices'] }),
  })
  const scanMutation = useMutation({
    mutationFn: () => {
      const connectorId = scanLocation.startsWith('connector:') ? scanLocation.slice('connector:'.length) : null
      return apiFetch<{ devices: LanDevice[] }>('/devices/scan', {
        method: 'POST',
        body: JSON.stringify({
          source: connectorId ? 'connector' : 'server',
          connector_id: connectorId,
        }),
      })
    },
    onSuccess: (result) => setDiscovered(result.devices),
  })
  const switchMutation = useMutation({
    mutationFn: ({ deviceId, channelId, desiredState }: { deviceId: string; channelId: string | null; desiredState: boolean }) =>
      setDeviceState(deviceId, channelId || null, desiredState),
    onSuccess: (message) => {
      setStatusMessage(message)
      queryClient.invalidateQueries({ queryKey: ['devices'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
  const deleteMutation = useMutation({
    mutationFn: (deviceId: string) => apiFetch<void>(`/api/v1/devices/${deviceId}`, { method: 'DELETE' }),
    onSuccess: () => {
      setStatusMessage('Switch deleted.')
      queryClient.invalidateQueries({ queryKey: ['devices'] })
      queryClient.invalidateQueries({ queryKey: ['mappings'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })

  useEffect(() => {
    return () => {
      if (pollTimer.current !== null) window.clearTimeout(pollTimer.current)
    }
  }, [])

  function applyLinkedDeviceKey(deviceId: string, devices: SmartLifeDevice[]): void {
    const matched = devices.find((device) => device.device_id === deviceId)
    if (matched) {
      form.setValue('encrypted_local_key', matched.local_key)
      setStatusMessage('Smart Life key matched to the selected LAN device.')
    }
  }

  async function pollSmartLife(loginId: string): Promise<void> {
    try {
      const result = await apiFetch<{ status: 'pending' | 'expired' | 'connected'; devices?: SmartLifeDevice[] }>(
        `/devices/smartlife/${encodeURIComponent(loginId)}`,
      )
      if (result.status === 'pending') {
        setSmartLifeStatus('Waiting for you to scan the QR code and approve sign-in in the app…')
        pollTimer.current = window.setTimeout(() => void pollSmartLife(loginId), 2000)
      } else if (result.status === 'expired') {
        setSmartLifeStatus('This QR code expired. Start again to generate a fresh code.')
        setQr('')
      } else {
        const devices = result.devices ?? []
        setLinkedDevices(devices)
        if (selectedLanDeviceIdRef.current) {
          applyLinkedDeviceKey(selectedLanDeviceIdRef.current, devices)
        }
        setSmartLifeStatus(`Connected. ${result.devices?.length ?? 0} local key(s) retrieved. Select the matching LAN scan result to fill its key.`)
      }
    } catch (pollError) {
      setSmartLifeStatus(pollError instanceof Error ? pollError.message : 'Could not check Smart Life sign-in.')
    }
  }

  const smartLifeMutation = useMutation({
    mutationFn: async () => {
      const userCode = smartLifeAccountCode.trim()
      if (!userCode) throw new Error('Enter your Smart Life account ID / user code to continue.')
      await apiFetch<{ saved: boolean }>('/devices/smartlife/preferences', {
        method: 'POST',
        body: JSON.stringify({ user_code: userCode, remember: shouldRememberUserCode }),
      })
      return apiFetch<{ login_id: string; qr: string }>('/devices/smartlife/start', {
        method: 'POST',
        body: JSON.stringify({ user_code: userCode, qr_scheme: qrScheme }),
      })
    },
    onSuccess: (result) => {
      setQr(result.qr)
      setSmartLifeStatus('QR ready. Scan it in the Smart Life app, then approve the sign-in request.')
      if (pollTimer.current !== null) window.clearTimeout(pollTimer.current)
      void pollSmartLife(result.login_id)
    },
    onError: (error) => setSmartLifeStatus(error.message),
  })

  if (isLoading) return <LoadingCard />
  if (error && !data) return <ErrorCard message={error.message} />

  const channelCount = data?.devices.reduce((total, device) => total + (device.channels?.length ?? 0), 0) ?? 0
  const canManageConnectors = user?.role === 'super_admin' || user?.role === 'tenant_admin' || user?.role === 'manager'
  const isSuperAdmin = user?.role === 'super_admin'
  const setupConnectors = connectors.filter((connector) => (
    connector.is_active && connector.is_enrolled && (
      isSuperAdmin || connector.tenant_id === user?.tenant_id
    )
  ))
  const onlineSetupConnectors = setupConnectors.filter((connector) => connector.is_online)
  const filteredDevices = (data?.devices ?? []).filter((device) => {
    const matchesSearch = `${device.name} ${device.device_id} ${device.ip_address ?? ''}`
      .toLocaleLowerCase()
      .includes(switchSearch.trim().toLocaleLowerCase())
    const matchesState = switchFilter === 'all'
      || (switchFilter === 'on' && device.current_state)
      || (switchFilter === 'off' && !device.current_state)
      || (switchFilter === 'unassigned' && !device.connector_id)
    return matchesSearch && matchesState
  })

  return (
    <div className="switch-page">
      <header className="switch-page-hero">
        <div className="switch-page-heading">
          <div className="switch-page-copy"><p className="switch-section-caption">Device control</p><h1>Smart switches</h1><p>Discover devices, confirm their connection route, and manage live state.</p></div>
          <div className="switch-page-metrics">
            <MetricMini label="Total" value={String(data?.devices.length ?? 0)} />
            <MetricMini label="On" value={String(data?.devices.filter((device) => device.current_state).length ?? 0)} />
            <MetricMini label="Channels" value={String(channelCount)} />
          </div>
        </div>
      </header>

      <section className="switch-discovery-panel">
        <div className="switch-discovery-heading">
          <div><p className="switch-section-caption">Local device discovery</p><h2>Scan a switch network</h2><p>Scan where ChargePilot runs, or choose an online site connector for a remote LAN.</p></div>
          <div className="switch-location-actions">
            <label className="label" htmlFor="scan-location">Scan location
              <select id="scan-location" className="field min-w-56" value={scanLocation} onChange={(event) => setScanLocation(event.target.value)}>
                <option value="server">ChargePilot server network</option>
                {connectors.filter((connector) => connector.is_active && connector.is_enrolled).map((connector) => <option key={connector.id} value={`connector:${connector.id}`} disabled={!connector.is_online}>{connector.name}{connector.is_online ? '' : ' (offline)'}</option>)}
              </select>
            </label>
            <button type="button" className="btn-primary" disabled={scanMutation.isPending} onClick={() => scanMutation.mutate()}>
              {scanMutation.isPending ? 'Scanning…' : 'Scan local network'}
            </button>
          </div>
        </div>
        {scanMutation.isError && <ErrorCard message={scanMutation.error.message} />}
        {scanMutation.isSuccess && (
          <section className="switch-scan-results" aria-live="polite">
            <div className="switch-scan-heading"><h3>Devices found on your network</h3><span className="switch-scan-count">{discovered.length}</span></div>
            {!discovered.length ? <p className="switch-scan-empty">No Tuya devices were found. Make sure a switch is powered on and the selected network can reach it.</p> : <div className="switch-scan-grid">
              {discovered.map((device) => <article key={device.device_id} className="switch-scan-card">
                <div className="switch-scan-card-copy"><h4>{device.name}</h4><p>{device.ip_address} · {device.device_id} · Protocol {device.protocol_version}</p></div><button type="button" className="btn-primary shrink-0 px-3 py-2 text-xs" disabled={device.already_added} onClick={() => {
                  selectedLanDeviceIdRef.current = device.device_id
                  setSelectedLanDeviceId(device.device_id)
                  applyLinkedDeviceKey(device.device_id, linkedDevices)
                  form.setValue('name', device.name)
                  form.setValue('device_id', device.device_id)
                  form.setValue('ip_address', device.ip_address === 'unknown' ? '' : device.ip_address)
                  form.setValue('device_type', device.device_type || 'switch')
                  form.setValue('protocol_version', device.protocol_version || '3.5')
                  if (!linkedDevices.some((linked) => linked.device_id === device.device_id)) {
                    form.setValue('encrypted_local_key', '')
                  }
                  const scannedConnectorId = scanLocation.startsWith('connector:')
                    ? scanLocation.slice('connector:'.length)
                    : ''
                  const defaultConnectorId = setupConnectors.some((connector) => connector.id === scannedConnectorId)
                    ? scannedConnectorId
                    : onlineSetupConnectors.length === 1
                      ? onlineSetupConnectors[0].id
                      : ''
                  form.setValue('connector_id', defaultConnectorId)
                  setManualOpen(true)
                  }}>{device.already_added ? 'Added' : 'Use device'}</button>
                  {device.already_added && <p className="switch-scan-note">This device is already configured.</p>}
                  </article>)}
            </div>}
          </section>
        )}
        {!connectors.some((connector) => connector.is_active && connector.is_enrolled) && <p className="switch-discovery-note">You can scan the ChargePilot server network now. To scan a remote site, <NavLink to="/connectors">enroll a site connector</NavLink>.</p>}
      </section>

      <section className="switch-add-panel">
        <div className="switch-add-heading">
          <div><p className="switch-section-caption">Add to inventory</p><h2>Add a switch</h2><p>Select a scan result or enter its local connection details.</p></div>
          <button type="button" className="btn-secondary" onClick={() => {
            setSelectedLanDeviceId('')
            setManualOpen((open) => {
              if (!open) form.setValue('connector_id', onlineSetupConnectors.length === 1 ? onlineSetupConnectors[0].id : '')
              return !open
            })
          }}>{manualOpen ? 'Close setup' : 'Add switch manually'}</button>
        </div>
        {statusMessage && <p className="switch-action-message" role="status">{statusMessage}</p>}
        {(mutation.isError || switchMutation.isError || connectorMutation.isError || meterMutation.isError || deleteMutation.isError) && <div className="mb-4"><ErrorCard message={mutation.error?.message ?? switchMutation.error?.message ?? connectorMutation.error?.message ?? meterMutation.error?.message ?? deleteMutation.error?.message ?? 'The action failed.'} /></div>}
        {manualOpen && <form className="switch-setup-form" onSubmit={form.handleSubmit((values) => mutation.mutate(values))}>
          <div className="switch-setup-step"><span>1</span><div><strong>Identify the switch</strong><small>Use LAN scan details or enter the device identity.</small></div></div>
          <div><label className="label" htmlFor="device-name">Display name</label><input id="device-name" className="field" placeholder="Living room plug" {...form.register('name')} />{form.formState.errors.name && <FieldError>{form.formState.errors.name.message}</FieldError>}</div>
          <div><label className="label" htmlFor="device-id">Device ID</label><input id="device-id" className="field" {...form.register('device_id')} />{form.formState.errors.device_id && <FieldError>{form.formState.errors.device_id.message}</FieldError>}</div>
          <div><label className="label" htmlFor="device-ip">Local IP address</label><input id="device-ip" className="field" placeholder="192.168.0.50" {...form.register('ip_address')} /></div>
          <div><label className="label" htmlFor="device-type">Device type</label><input id="device-type" className="field" {...form.register('device_type')} /></div>
          <div><label className="label" htmlFor="device-protocol">Protocol version</label><input id="device-protocol" className="field" {...form.register('protocol_version')} /></div>
          <div className="switch-setup-step"><span>2</span><div><strong>Add local access details</strong><small>Device keys are encrypted at rest and shared only for authorized control.</small></div></div>
          <div className="switch-key-field"><div className="switch-key-label"><label className="label" htmlFor="device-key">Local key</label><button type="button" className="switch-key-action" onClick={() => setSmartLifeOpen(true)}>Fetch with Smart Life</button></div><input id="device-key" type="password" autoComplete="new-password" className="field" placeholder="Blank until entered or retrieved" {...form.register('encrypted_local_key')} />{form.formState.errors.encrypted_local_key && <FieldError>{form.formState.errors.encrypted_local_key.message}</FieldError>}<p className="switch-form-help">The key stays blank until entered or matched from Smart Life.</p></div>
          <div><label className="label" htmlFor="channel-count">Number of channels</label><select id="channel-count" className="field" {...form.register('channel_count', { valueAsNumber: true })}>{Array.from({ length: 8 }, (_, index) => index + 1).map((count) => <option key={count} value={count}>{count} channel{count > 1 ? 's' : ''}</option>)}</select></div>
          <div className="switch-setup-step"><span>3</span><div><strong>Choose where commands run</strong><small>Choose the site that shares this switch’s local network.</small></div></div>
          <div className="switch-route-picker">
            <span className="label" id="new-device-connector-label">Control this switch through</span>
            <div className="switch-route-options" role="radiogroup" aria-labelledby="new-device-connector-label">
              <label className={`switch-route-choice ${selectedSetupConnectorId === '' ? 'is-selected' : ''}`}>
                <input type="radio" value="" {...form.register('connector_id')} />
                <span className="switch-route-choice-copy"><strong>ChargePilot host</strong><small>For switches on the API host’s local network</small></span>
                <span className="switch-route-choice-status">Direct</span>
              </label>
              {setupConnectors.map((connector) => <label key={connector.id} className={`switch-route-choice ${selectedSetupConnectorId === connector.id ? 'is-selected' : ''}`}>
                <input type="radio" value={connector.id} {...form.register('connector_id')} />
                <span className="switch-route-choice-copy"><strong>{connector.name}</strong><small>{isSuperAdmin && connector.tenant_name ? `${connector.tenant_name} · ` : ''}{connector.is_online ? 'Online now' : 'Offline · control resumes after reconnection'}</small></span>
                <span className={`switch-route-choice-status ${connector.is_online ? 'is-online' : 'is-offline'}`}>{connector.is_online ? 'Online' : 'Offline'}</span>
              </label>)}
            </div>
            {setupConnectors.length ? (
              <p className="switch-route-help">An offline connector can be assigned, but will control the switch only after it reconnects.</p>
            ) : (
              <p className="switch-route-warning">No enrolled connector is available for this workspace. The ChargePilot host option works only when the API host can reach the switch directly. <NavLink to="/connectors">Set up a site connector</NavLink>.</p>
            )}
          </div>
          <div className="switch-setup-submit"><button type="submit" className="btn-primary" disabled={mutation.isPending}><Plus size={16} />{mutation.isPending ? 'Adding switch…' : 'Save switch setup'}</button></div>
        </form>}
      </section>

      <section className="switch-inventory" aria-labelledby="switch-inventory-title">
        <div className="switch-inventory-heading">
          <div><p className="switch-section-caption">Your device inventory</p><h2 id="switch-inventory-title">Configured switches</h2><p>Check live state, connection route, and channel controls.</p></div>
          <span className="switch-inventory-count">{filteredDevices.length}<small>showing</small></span>
        </div>
        {error && <div className="mb-4"><ErrorCard message={`Could not load switch inventory: ${error.message}`} /></div>}
        {statusRefreshError && <div className="mb-4"><ErrorCard message={`Could not refresh live switch status: ${statusRefreshError.message}`} /></div>}
        {!!statusRefresh?.skipped_devices.length && <p className="switch-inventory-alert" role="status">{statusRefresh.skipped_devices.length} switch{statusRefresh.skipped_devices.length === 1 ? '' : 'es'} could not return live status. Check each switch’s assigned site connector and its heartbeat.</p>}
        <div className="switch-inventory-tools">
          <label className="switch-search" htmlFor="switch-search"><Search size={17} /><input id="switch-search" value={switchSearch} onChange={(event) => setSwitchSearch(event.target.value)} placeholder="Find a switch" /></label>
          <div className="switch-filter-group" role="group" aria-label="Filter switches">
            {([
              ['all', 'All'],
              ['on', 'On'],
              ['off', 'Off'],
              ['unassigned', 'Needs connector'],
            ] as const).map(([value, label]) => <button key={value} type="button" className={switchFilter === value ? 'is-active' : ''} aria-pressed={switchFilter === value} onClick={() => setSwitchFilter(value)}>{label}{value === 'all' ? ` · ${data?.devices.length ?? 0}` : value === 'unassigned' ? ` · ${data?.devices.filter((device) => !device.connector_id).length ?? 0}` : ''}</button>)}
          </div>
          <div className="switch-view-toggle" role="group" aria-label="Switch layout">
            <button type="button" className={switchView === 'cards' ? 'is-active' : ''} aria-label="Card view" aria-pressed={switchView === 'cards'} onClick={() => setSwitchView('cards')}><LayoutGrid size={17} /></button>
            <button type="button" className={switchView === 'list' ? 'is-active' : ''} aria-label="List view" aria-pressed={switchView === 'list'} onClick={() => setSwitchView('list')}><List size={17} /></button>
          </div>
        </div>
        <div className={`switch-inventory-grid ${switchView === 'list' ? 'is-list-view' : ''}`}>
          {filteredDevices.map((device) => {
            const assignedConnector = connectors.find((connector) => connector.id === device.connector_id)
            const assignableConnectors = connectors.filter((connector) => (
              connector.is_active && connector.is_enrolled && connector.tenant_id === device.tenant_id
            ))
            return <article key={device.id} className={`switch-device-card ${switchView === 'list' ? 'is-list-card' : ''}`} data-state={device.current_state ? 'on' : 'off'}>
              <div className="switch-card-heading">
                <div className="min-w-0">
                  <div className="switch-card-title"><span className={`switch-state-light ${device.current_state ? 'is-on' : ''}`} aria-hidden="true" /><h3>{device.name}</h3><span className={`switch-state-label ${device.current_state ? 'is-on' : ''}`}>{device.current_state ? 'On' : 'Off'}</span></div>
                  <p className="switch-card-tenant">{device.tenant_name ?? 'Unassigned tenant'}</p>
                </div>
                <span className={`switch-route-status ${assignedConnector?.is_online ? 'is-online' : device.connector_id ? 'is-offline' : 'is-unassigned'}`}>
                  {device.connector_id ? `${assignedConnector?.name ?? 'Site connector'} · ${assignedConnector?.is_online ? 'online' : 'offline'}` : 'No connector assigned'}
                </span>
              </div>
              <div className="switch-device-facts"><span>{device.device_type || 'Switch'}</span><span>{device.ip_address || 'IP not set'}</span><span>{device.channels?.length ?? 0} channel{device.channels?.length === 1 ? '' : 's'}</span><span>Last checked {formatTimestamp(device.last_seen_at ?? null)}</span></div>
              {!device.connector_id && <p className="switch-route-warning switch-unassigned-warning" role="status">Commands currently run from the ChargePilot host. In k3s or cloud hosting, assign a site connector on this switch’s LAN.</p>}
              {device.channels?.length ? <div className="channel-panel">{device.channels.map((channel) => <div key={channel.id} className="switch-channel-row">
                <div className="switch-channel-name"><span className="channel-number">{channel.channel_index}</span><span>{channel.name}</span><span className={`channel-state-label ${channel.current_state ? 'is-on' : ''}`}>{channel.current_state ? 'On' : 'Off'}</span></div>
                <button type="button" className="btn-secondary px-3 py-2 text-xs" disabled={switchMutation.isPending} aria-label={`Turn ${channel.current_state ? 'off' : 'on'} ${channel.name}`} onClick={() => switchMutation.mutate({ deviceId: device.id, channelId: channel.id, desiredState: !channel.current_state })}>{channel.current_state ? 'Turn off' : 'Turn on'}</button>
              </div>)}</div> : <div className="switch-card-actions">
                <span className="channel-state-label">Whole switch</span>
                <button type="button" className="btn-secondary px-3 py-2 text-xs" disabled={switchMutation.isPending} onClick={() => switchMutation.mutate({ deviceId: device.id, channelId: '', desiredState: !device.current_state })}>{device.current_state ? 'Turn off' : 'Turn on'}</button>
              </div>}
              <DeviceMeterPanel
                key={JSON.stringify([device.power_dp_id, device.power_multiplier, device.energy_dp_id, device.energy_multiplier, device.energy_counter_type])}
                device={device}
                isSaving={meterMutation.isPending}
                currentMonth={currentMonth}
                now={meterNow}
                onSave={(settings) => meterMutation.mutate({ deviceId: device.id, settings })}
              />
              {canManageConnectors && <form className="switch-route-editor" onSubmit={(event) => { event.preventDefault(); const body = new FormData(event.currentTarget); connectorMutation.mutate({ deviceId: device.id, connectorId: String(body.get('connector_id') ?? '') }) }}>
                <div className="switch-route-editor-copy"><strong>Command route</strong><small>{device.connector_id ? 'Commands are sent to the selected site.' : 'Choose a site connector to control this switch remotely.'}</small></div>
                <label className="sr-only" htmlFor={`connector-${device.id}`}>Select a command route for {device.name}</label>
                <select id={`connector-${device.id}`} name="connector_id" className="field" defaultValue={device.connector_id ?? ''}>
                  <option value="">ChargePilot host · local network only</option>
                  {assignableConnectors.map((connector) => <option key={connector.id} value={connector.id}>{connector.name} · {connector.is_online ? 'online' : 'offline'}</option>)}
                </select>
                <button type="submit" className="btn-secondary px-3 py-2 text-xs" disabled={connectorMutation.isPending}>{connectorMutation.isPending ? 'Saving…' : 'Save route'}</button>
                {!assignableConnectors.length && <NavLink to="/connectors" className="switch-connector-link">Set up a connector</NavLink>}
              </form>}
              <div className="switch-card-footer"><span className="switch-device-id">Device ID · {device.device_id}</span><button type="button" className="switch-delete-button" disabled={deleteMutation.isPending} onClick={() => { if (window.confirm('Delete this switch and all associated channels? This action cannot be undone.')) deleteMutation.mutate(device.id) }}>Delete switch</button></div>
            </article>
          })}
          {!filteredDevices.length && <div className="switch-inventory-empty"><PlugZap size={23} /><strong>{data?.devices.length ? 'No switches match this view' : 'No switches configured yet'}</strong><p>{data?.devices.length ? 'Change the filter or search another switch.' : 'Scan your network or add a switch to get started.'}</p>{!data?.devices.length && <button type="button" className="btn-primary" onClick={() => { setSelectedLanDeviceId(''); setManualOpen(true) }}>Add a switch</button>}</div>}
        </div>
      </section>

      {smartLifeOpen && <div className="smartlife-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setSmartLifeOpen(false) }}>
        <section className="smartlife-modal" role="dialog" aria-modal="true" aria-labelledby="smartlife-title">
          <header className="smartlife-modal-heading ui-modal-heading">
            <div><p className="smartlife-modal-kicker">Secure local key retrieval</p><h2 id="smartlife-title">Connect Smart Life</h2><p>ChargePilot retrieves local keys only. Device IP and other details come from the LAN scan.</p></div>
            <button type="button" className="smartlife-modal-close" onClick={() => setSmartLifeOpen(false)}>Close</button>
          </header>
          <div className="smartlife-modal-body">
            <div className="smartlife-modal-grid">
              <div className="smartlife-detail-panel"><label className="label" htmlFor="smartlife-code">Smart Life account ID</label><input id="smartlife-code" maxLength={120} autoComplete="username" className="field" value={smartLifeAccountCode} onChange={(event) => setSmartLifeUserCode(event.target.value)} /><p>Find it in Smart Life → Me → Settings → Account and Security.</p></div>
              <div className="smartlife-detail-panel"><label className="label" htmlFor="smartlife-scheme">Mobile app</label><select id="smartlife-scheme" className="field" value={qrScheme} onChange={(event) => setQrScheme(event.target.value)}><option value="smartlife">Smart Life</option><option value="tuyaSmart">Tuya Smart</option></select><label className="smartlife-remember"><input type="checkbox" checked={shouldRememberUserCode} onChange={(event) => setRememberUserCode(event.target.checked)} /><span>Remember this account ID on my ChargePilot account</span></label></div>
            </div>
            <div className="smartlife-qr-panel"><p className="smartlife-qr-title">Generate a secure sign-in QR</p><p>Scan it in your mobile app and approve the request.</p><button type="button" className="btn-primary" disabled={smartLifeMutation.isPending} onClick={() => smartLifeMutation.mutate()}>{smartLifeMutation.isPending ? 'Preparing…' : 'Generate secure QR'}</button>{smartLifeStatus && <p className="smartlife-qr-status" role="status" aria-live="polite">{smartLifeStatus}</p>}{qr && <img className="smartlife-qr-image" src={qr} alt="Smart Life sign-in QR code" />}</div>
            {linkedDevices.length > 0 && <div className="smartlife-match-list" aria-live="polite">{linkedDevices.map((linked) => <div key={linked.device_id} className={`smartlife-match ${selectedLanDeviceId === linked.device_id ? 'is-matched' : ''}`}><span>{linked.device_id}</span><span>{selectedLanDeviceId === linked.device_id ? 'Matched automatically' : 'Select matching LAN device'}</span></div>)}</div>}
          </div>
        </section>
      </div>}
    </div>
  )
}
