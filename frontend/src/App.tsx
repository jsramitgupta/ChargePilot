import { QueryClient, QueryClientProvider, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { zodResolver } from '@hookform/resolvers/zod'
import {
  BatteryCharging,
  Bell,
  Building2,
  Cable,
  CheckCircle2,
  CircleDashed,
  LayoutGrid,
  LogIn,
  LogOut,
  Menu,
  Moon,
  MonitorSmartphone,
  Network,
  PlugZap,
  Plus,
  ShieldCheck,
  Sun,
  Users,
} from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useForm } from 'react-hook-form'
import { BrowserRouter, NavLink, Navigate, Outlet, Route, Routes, useSearchParams } from 'react-router-dom'
import { z } from 'zod'

declare global {
  interface Window {
    CHARGEPILOT_CONFIG?: {
      apiBaseUrl?: string
      frontendUrl?: string
    }
  }
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      refetchOnWindowFocus: false,
    },
  },
})

type User = {
  id: string
  username: string
  role: string
  tenant_id?: string | null
  is_admin: boolean
  smartlife_user_code?: string | null
  timezone?: string
}

type Endpoint = {
  id: string
  hostname: string
  ip_address: string | null
  battery: number
  charging: boolean
  ac_connected: boolean
  last_seen_at: string | null
  status: 'online' | 'offline'
  mapped_device: string
  switch_state: boolean | null
}

type Device = {
  id: string
  device_id: string
  name: string
  ip_address?: string | null
  device_type?: string | null
  protocol_version?: string | null
  enabled?: boolean | null
  current_state?: boolean | null
  last_state_change_at?: string | null
  channels?: DeviceChannel[]
  connector_id?: string | null
}

type DeviceChannel = {
  id: string
  device_id: string
  channel_index: number
  name: string
  dp_id?: string | null
  enabled: boolean
  current_state: boolean
}

type LanDevice = {
  name: string
  device_id: string
  ip_address: string
  protocol_version: string
  device_type: string
  already_added: boolean
}

type Connector = {
  id: string
  name: string
  tenant_id: string | null
  is_active: boolean
  is_enrolled: boolean
  is_online: boolean
}

type SmartLifeDevice = {
  device_id: string
  local_key: string
}

type Mapping = {
  id: string
  endpoint_id: string
  device_id: string
  channel_id?: string | null
  on_threshold: number
  off_threshold: number
  minimum_state_change_interval: number
  enabled: boolean
}

type EventItem = {
  id: string
  event_type: string
  success: boolean
  reason?: string | null
  endpoint_id?: string | null
  endpoint?: string
  battery?: string
  activity?: string
  device_id?: string | null
  channel_id?: string | null
  previous_state?: string | null
  new_state?: string | null
  created_at?: string | null
}

type EventPage = {
  items: EventItem[]
  page: number
  per_page: number
  total_events: number
  total_pages: number
  first_row: number
  last_row: number
}

type DeviceFormValues = {
  name: string
  device_id: string
  ip_address?: string
  device_type?: string
  protocol_version?: string
  encrypted_local_key: string
  enabled?: boolean
  channel_count: number
}

const deviceSchema = z.object({
  name: z.string().min(1, 'Display name is required'),
  device_id: z.string().min(1, 'Device ID is required'),
  ip_address: z.string().default(''),
  device_type: z.string().default('switch'),
  protocol_version: z.string().default('3.5'),
  encrypted_local_key: z.string().min(1, 'Local key is required'),
  enabled: z.boolean().default(true),
  channel_count: z.number().int().min(1).max(8),
})

const API_BASE_URL = (
  window.CHARGEPILOT_CONFIG?.apiBaseUrl ?? import.meta.env.VITE_API_BASE_URL ?? ''
).replace(/\/+$/, '')
const FRONTEND_BASE_URL = (
  window.CHARGEPILOT_CONFIG?.frontendUrl ?? ''
).replace(/\/+$/, '') || window.location.origin

function backendUrl(path: string) {
  return `${API_BASE_URL}${path}`
}

function frontendUrl(path: string) {
  return `${FRONTEND_BASE_URL}${path}`
}

async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(backendUrl(path), {
    ...init,
    credentials: 'include',
    headers: {
      ...(init.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...(init.headers ?? {}),
    },
  })

  if (response.status === 204) {
    return undefined as T
  }

  const text = await response.text()
  const payload = text ? JSON.parse(text) : null

  if (!response.ok) {
    throw new Error(payload?.detail ?? payload?.message ?? 'Request failed.')
  }

  return payload as T
}

async function submitLegacyAction(path: string, values?: FormData): Promise<string> {
  const response = await fetch(backendUrl(path), {
    method: 'POST',
    credentials: 'include',
    headers: { 'X-Requested-With': 'XMLHttpRequest' },
    body: values,
  })
  const finalUrl = new URL(response.url)
  if (!response.ok) throw new Error(`The request failed (HTTP ${response.status}).`)
  if (finalUrl.pathname === '/login') throw new Error('Your session has expired. Sign in again and retry.')
  const error = finalUrl.searchParams.get('error')
  if (error) throw new Error(error.replaceAll('+', ' '))
  const message = finalUrl.searchParams.get('message')?.replaceAll('+', ' ')
  if (message?.toLowerCase().includes('failed')) throw new Error(message)
  return message ?? 'Saved.'
}

async function fetchSession(): Promise<User> {
  return apiFetch<User>('/api/v1/auth/me')
}

async function fetchDashboardData() {
  const [endpoints, devices] = await Promise.all([
    apiFetch<Endpoint[]>('/api/v1/endpoints'),
    apiFetch<Device[]>('/api/v1/devices'),
  ])

  return { endpoints, devices }
}

function useSession() {
  return useQuery({
    queryKey: ['session'],
    queryFn: fetchSession,
    retry: false,
  })
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route element={<ProtectedLayout />}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/devices" element={<DevicesPage />} />
            <Route path="/mappings" element={<MappingsPage />} />
            <Route path="/endpoints" element={<EndpointsPage />} />
            <Route path="/events" element={<EventsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

function ProtectedLayout() {
  const { data, isLoading, error } = useSession()

  if (isLoading) {
    return <LoadingScreen />
  }

  if (error || !data) {
    return <Navigate to="/login" replace />
  }

  return <AppShell user={data} />
}

function useAppTheme() {
  const [isDark, setIsDark] = useState(() => {
    const savedTheme = window.localStorage.getItem('chargepilot-theme')
    return savedTheme ? savedTheme === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches
  })

  useEffect(() => {
    document.body.classList.toggle('theme-dark', isDark)
    document.body.classList.add('bg-slate-50')
    window.localStorage.setItem('chargepilot-theme', isDark ? 'dark' : 'light')
  }, [isDark])

  return [isDark, setIsDark] as const
}

function ThemeToggleButton({ isDark, onToggle, className = '' }: { isDark: boolean; onToggle: () => void; className?: string }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className={`inline-flex h-11 w-11 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-700 shadow-sm transition hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark-card-shell ${className}`}
      aria-label={isDark ? 'Use light theme' : 'Use dark theme'}
    >
      {isDark ? <Sun size={18} aria-hidden="true" /> : <Moon size={18} aria-hidden="true" />}
    </button>
  )
}

function AppShell({ user }: { user: User }) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [isDark, setIsDark] = useAppTheme()

  useEffect(() => {
    document.body.dataset.userTimezone = user.timezone || 'UTC'
    return () => {
      delete document.body.dataset.userTimezone
    }
  }, [user.timezone])

  const navItems = [
    { to: '/', label: 'Dashboard', icon: LayoutGrid },
    { to: '/devices', label: 'Switches', icon: PlugZap },
    { to: '/mappings', label: 'Mappings', icon: Cable },
    { to: '/endpoints', label: 'Endpoints', icon: MonitorSmartphone },
    { to: '/connectors', label: 'Connectors', icon: Network, legacy: true },
    { to: '/events', label: 'Events', icon: Bell },
  ]

  return (
    <div className="min-h-screen">
      <header className="site-header dark-header">
        <div className="site-header-inner">
          <NavLink to="/" className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-3 py-2 shadow-soft dark-card-shell" aria-label="ChargePilot dashboard">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-100 text-base font-bold text-blue-700">C</span>
            <span>
              <span className="block text-sm font-bold tracking-tight text-slate-900">ChargePilot</span>
              <span className="block text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">Battery automation</span>
            </span>
          </NavLink>
          <div className="site-header-actions">
            <div className="hidden items-center gap-2 md:flex"><span className="mini-badge live-pill">Live telemetry</span></div>
            <ThemeToggleButton isDark={isDark} onToggle={() => setIsDark((value) => !value)} />
            <a href={backendUrl('/agent')} className="agent-header-button">Download Agent</a>
            <a href={backendUrl('/profile')} className="header-account-link">Profile</a>
            <a href={backendUrl('/logout')} className="header-account-link"><LogOut size={14} className="mr-1 inline" />Logout</a>
            <button className="nav-toggle" type="button" aria-label={mobileOpen ? 'Close navigation' : 'Open navigation'} aria-expanded={mobileOpen} aria-controls="mainNav" onClick={() => setMobileOpen((value) => !value)}>
              <span className="sr-only">Open menu</span><Menu size={18} aria-hidden="true" />
            </button>
          </div>
        </div>
        <nav id="mainNav" className={`site-nav ${mobileOpen ? 'is-open' : ''}`} aria-label="Main navigation">
          {navItems.map(({ to, label, icon: Icon, legacy }) => legacy ? (
            <a key={to} href={to} onClick={() => setMobileOpen(false)} className="rounded-xl px-3 py-2 text-sm font-semibold transition"><Icon size={15} className="mr-1 inline" />{label}</a>
          ) : (
            <NavLink key={to} to={to} end={to === '/'} onClick={() => setMobileOpen(false)} className="rounded-xl px-3 py-2 text-sm font-semibold transition"><Icon size={15} className="mr-1 inline" />{label}</NavLink>
          ))}
          {(user.role === 'super_admin' || user.role === 'tenant_admin' || user.role === 'manager') && (
            <a href={backendUrl('/users')} onClick={() => setMobileOpen(false)} className="rounded-xl px-3 py-2 text-sm font-semibold transition"><Users size={15} className="mr-1 inline" />Users</a>
          )}
          {user.role === 'super_admin' && <a href={backendUrl('/tenants')} onClick={() => setMobileOpen(false)} className="rounded-xl px-3 py-2 text-sm font-semibold transition"><Building2 size={15} className="mr-1 inline" />Tenants</a>}
        </nav>
      </header>
      <main className="page-shell">
        <div className="mb-5 text-xs text-slate-500" aria-label="Signed-in account"><ShieldCheck size={13} className="mr-1 inline" />{user.username} · {user.role.replaceAll('_', ' ')}</div>
        <Outlet />
      </main>
    </div>
  )
}

function LoginPage() {
  const [searchParams] = useSearchParams()
  const [isDark, setIsDark] = useAppTheme()

  return (
    <div className="auth-shell">
      <ThemeToggleButton isDark={isDark} onToggle={() => setIsDark((value) => !value)} className="auth-theme-toggle" />
      <section className="auth-card" aria-labelledby="login-title">
        <div className="flex items-center justify-center"><div className="brand-mark auth-brand-mark">C</div></div>
        <div className="auth-badges"><span>ChargePilot</span><span>Local-first control</span></div>
        <h1 id="login-title">Welcome back</h1>
        <p className="auth-subtle">Sign in to your tenant and manage your battery automation.</p>
        {searchParams.get('message') && <p className="alert success mt-5" role="status">{searchParams.get('message')}</p>}
        {searchParams.get('error') && <p className="alert error mt-4" role="alert">{searchParams.get('error')}</p>}
        <form method="post" action={backendUrl('/login')} className="auth-form">
          <div className="field-group">
            <label htmlFor="username">Username</label>
            <input id="username" name="username" type="text" autoComplete="username" required className="field" />
          </div>
          <div className="field-group">
            <label htmlFor="password">Password</label>
            <input id="password" name="password" type="password" autoComplete="current-password" required className="field" />
          </div>
          <button type="submit" className="primary-btn large-btn w-full"><LogIn size={16} className="mr-2" />Log in</button>
        </form>
        <div className="auth-divider" />
        <div className="auth-signup">
          <p>Need a new account?</p>
          <div className="auth-actions">
            <a href={frontendUrl('/register?account_type=standard')} className="choice-link">Standard user</a>
            <a href={frontendUrl('/register?account_type=tenant')} className="primary-btn small-btn">Create tenant</a>
          </div>
        </div>
      </section>
    </div>
  )
}

function RegisterPage() {
  const [searchParams] = useSearchParams()
  const [isDark, setIsDark] = useAppTheme()
  const accountType = searchParams.get('account_type') === 'tenant' ? 'tenant' : 'standard'
  const error = searchParams.get('error')

  return (
    <div className="auth-shell">
      <ThemeToggleButton isDark={isDark} onToggle={() => setIsDark((value) => !value)} className="auth-theme-toggle" />
      <section className="auth-card auth-card-wide" aria-labelledby="register-title">
        <div className="flex items-center justify-center"><div className="brand-mark auth-brand-mark">C</div></div>
        <div className="auth-badges"><span>Create account</span><span>Secure access</span></div>
        <h1 id="register-title">Choose your access</h1>
        {error && <p className="alert error mt-4" role="alert">{error}</p>}
        <div className="auth-choice-grid">
          <a href={frontendUrl('/register?account_type=standard')} className={`choice-card ${accountType === 'standard' ? 'active' : ''}`}>
            <span className="choice-title">Standard user</span><span className="choice-copy">Starts with a personal tenant.</span>
          </a>
          <a href={frontendUrl('/register?account_type=tenant')} className={`choice-card ${accountType === 'tenant' ? 'active' : ''}`}>
            <span className="choice-title">Tenant admin</span><span className="choice-copy">Creates a new isolated tenant.</span>
          </a>
        </div>
        <form method="post" action={backendUrl('/register')} className="auth-form">
          <input type="hidden" name="account_type" value={accountType} />
          <div className="field-group">
            <label htmlFor="username">Username</label>
            <input id="username" name="username" type="text" autoComplete="username" required className="field" />
          </div>
          <div className="field-group">
            <label htmlFor="password">Password</label>
            <input id="password" name="password" type="password" autoComplete="new-password" required className="field" />
          </div>
          {accountType === 'tenant' && <div className="field-group"><label htmlFor="tenant_name">Tenant name</label><input id="tenant_name" name="tenant_name" type="text" placeholder="My tenant" className="field" /></div>}
          <button type="submit" className="primary-btn large-btn w-full">{accountType === 'tenant' ? 'Create tenant' : 'Create standard user'}</button>
        </form>
        <p className="auth-signin">Already have an account? <a href={frontendUrl('/login')}>Sign in</a></p>
      </section>
    </div>
  )
}

function DashboardPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard'],
    queryFn: fetchDashboardData,
  })

  if (isLoading) return <LoadingCard />
  if (error) return <ErrorCard message={error.message} />

  const { endpoints, devices } = data!
  const onlineCount = endpoints.filter((endpoint) => endpoint.status === 'online').length

  return (
    <div className="space-y-6">
      <div className="page-header">
        <div><p className="eyebrow">Overview</p><h1>Device-to-switch control</h1></div>
        <span className="pill live-pill">Live telemetry</span>
      </div>

      <section className="hero-panel">
        <div className="hero-copy">
          <p className="mini-label">Automation ready</p>
          <h2>Map each laptop to the correct smart switch and keep battery logic responsive.</h2>
        </div>
        <div className="hero-actions">
          <NavLink className="primary-btn" to="/mappings">Create mapping</NavLink>
          <NavLink className="secondary-btn" to="/devices">Manage switches</NavLink>
        </div>
      </section>

      <div className="stats-grid">
        <MetricCard label="Total endpoints" value={String(endpoints.length)} hint="laptops reporting" icon={MonitorSmartphone} tone="blue" />
        <MetricCard label="Online endpoints" value={String(onlineCount)} hint="seen in the last 10 minutes" icon={CheckCircle2} tone="emerald" />
        <MetricCard label="Offline endpoints" value={String(endpoints.length - onlineCount)} hint="not recently reporting" icon={CircleDashed} tone="amber" />
        <MetricCard label="Smart switches" value={String(devices.length)} hint="configured devices" icon={PlugZap} tone="violet" />
      </div>

      <section className="panel table-panel">
        <div className="panel-header"><h3>Endpoint activity</h3><NavLink to="/endpoints" className="secondary-btn">View endpoints</NavLink></div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Laptop</th><th>Battery</th><th>Power</th><th>Switch</th><th>State</th><th>Last seen</th></tr></thead>
            <tbody>
              {endpoints.map((endpoint) => (
                <tr key={endpoint.id}>
                  <td className="strong-cell">{endpoint.hostname}</td>
                  <td>{endpoint.battery}%</td>
                  <td><span className={`badge ${endpoint.charging || endpoint.ac_connected ? 'success' : 'muted'}`}>{endpoint.charging ? 'Charging' : endpoint.ac_connected ? 'On AC' : 'On battery'}</span></td>
                  <td>{endpoint.mapped_device}</td>
                  <td>{endpoint.switch_state === null ? '—' : endpoint.switch_state ? 'On' : 'Off'}</td>
                  <td>{formatTimestamp(endpoint.last_seen_at)}</td>
                </tr>
              ))}
              {!endpoints.length && <tr><td colSpan={6} className="empty-state">No endpoint telemetry has been received yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}

function DevicesPage() {
  const queryClient = useQueryClient()
  const { data: user } = useSession()
  const [manualOpen, setManualOpen] = useState(false)
  const [smartLifeOpen, setSmartLifeOpen] = useState(false)
  const [scanLocation, setScanLocation] = useState('server')
  const [discovered, setDiscovered] = useState<LanDevice[]>([])
  const [selectedLanDeviceId, setSelectedLanDeviceId] = useState('')
  const [linkedDevices, setLinkedDevices] = useState<SmartLifeDevice[]>([])
  const [qr, setQr] = useState('')
  const [smartLifeStatus, setSmartLifeStatus] = useState('')
  const [statusMessage, setStatusMessage] = useState('')
  const [smartLifeUserCode, setSmartLifeUserCode] = useState('')
  const [qrScheme, setQrScheme] = useState('smartlife')
  const [rememberUserCode, setRememberUserCode] = useState(false)
  const pollTimer = useRef<number | null>(null)

  const { data, isLoading, error } = useQuery({
    queryKey: ['devices'],
    queryFn: async () => {
      const devices = await apiFetch<Device[]>('/api/v1/devices')
      return Promise.all(devices.map(async (device) => ({
        ...device,
        channels: await apiFetch<DeviceChannel[]>(`/api/v1/devices/${device.id}/channels`),
      })))
    },
  })
  const { data: connectors = [] } = useQuery({
    queryKey: ['connectors'],
    queryFn: () => apiFetch<Connector[]>('/api/v1/connectors'),
  })

  const form = useForm<DeviceFormValues>({
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
    },
  })

  const mutation = useMutation({
    mutationFn: async (values: DeviceFormValues) => {
      const { channel_count, ...devicePayload } = values
      const device = await apiFetch<Device>('/api/v1/devices', {
        method: 'POST',
        body: JSON.stringify(devicePayload),
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
      return device
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['devices'] })
      form.reset()
      setManualOpen(false)
      setSelectedLanDeviceId('')
      setStatusMessage('Switch added.')
    },
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
    mutationFn: async ({ path, deviceId, desiredState }: { path: string; deviceId: string; desiredState: boolean }) => {
      const result = await submitLegacyAction(path)
      return { result, deviceId, desiredState }
    },
    onSuccess: ({ result }) => {
      setStatusMessage(result)
      queryClient.invalidateQueries({ queryKey: ['devices'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
  const connectorMutation = useMutation({
    mutationFn: ({ deviceId, connectorId }: { deviceId: string; connectorId: string }) => {
      const body = new FormData()
      body.set('connector_id', connectorId)
      return submitLegacyAction(`/devices/${deviceId}/connector`, body)
    },
    onSuccess: (message) => {
      setStatusMessage(message)
      queryClient.invalidateQueries({ queryKey: ['devices'] })
    },
  })
  const deleteMutation = useMutation({
    mutationFn: (deviceId: string) => submitLegacyAction(`/devices/${deviceId}/delete`),
    onSuccess: (message) => {
      setStatusMessage(message === 'Saved.' ? 'Switch deleted.' : message)
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

  useEffect(() => {
    if (user?.smartlife_user_code) {
      setSmartLifeUserCode(user.smartlife_user_code)
      setRememberUserCode(true)
    }
  }, [user?.smartlife_user_code])

  useEffect(() => {
    if (!selectedLanDeviceId) return
    const matched = linkedDevices.find((device) => device.device_id === selectedLanDeviceId)
    if (matched) {
      form.setValue('encrypted_local_key', matched.local_key)
      setStatusMessage('Smart Life key matched to the selected LAN device.')
    }
  }, [form, linkedDevices, selectedLanDeviceId])

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
        setLinkedDevices(result.devices ?? [])
        setSmartLifeStatus(`Connected. ${result.devices?.length ?? 0} local key(s) retrieved. Select the matching LAN scan result to fill its key.`)
      }
    } catch (pollError) {
      setSmartLifeStatus(pollError instanceof Error ? pollError.message : 'Could not check Smart Life sign-in.')
    }
  }

  const smartLifeMutation = useMutation({
    mutationFn: async () => {
      const userCode = smartLifeUserCode.trim()
      if (!userCode) throw new Error('Enter your Smart Life account ID / user code to continue.')
      await apiFetch<{ saved: boolean }>('/devices/smartlife/preferences', {
        method: 'POST',
        body: JSON.stringify({ user_code: userCode, remember: rememberUserCode }),
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
  if (error) return <ErrorCard message={error.message} />

  const channelCount = data?.reduce((total, device) => total + (device.channels?.length ?? 0), 0) ?? 0
  const canManageConnectors = user?.role === 'super_admin' || user?.role === 'tenant_admin' || user?.role === 'manager'

  return (
    <div className="space-y-6">
      <header className="ui-page-hero rounded-[30px] p-6 sm:p-7">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div><p className="text-[11px] font-bold uppercase tracking-[0.26em] text-blue-200">Device control</p><h1 className="mt-3 text-3xl font-black tracking-tight sm:text-4xl">Smart switches</h1></div>
          <div className="grid grid-cols-3 gap-3 text-left">
            <MetricMini label="Total" value={String(data?.length ?? 0)} />
            <MetricMini label="On" value={String(data?.filter((device) => device.current_state).length ?? 0)} />
            <MetricMini label="Channels" value={String(channelCount)} />
          </div>
        </div>
      </header>

      <section className="ui-accent-surface rounded-[28px] p-5 sm:p-6">
        <div className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div><p className="text-[11px] font-bold uppercase tracking-[0.24em] text-blue-700">Local device discovery</p><h2 className="mt-2 text-2xl font-bold tracking-tight text-slate-900">Scan a switch network</h2><p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">Scan where ChargePilot runs, or choose an online site connector for a remote LAN.</p></div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
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
          <section className="border-t border-blue-100 pt-5" aria-live="polite">
            <div className="mb-3 flex items-center justify-between"><h3 className="text-sm font-bold text-slate-900">Devices found on your network</h3><span className="badge border-slate-200 bg-white text-slate-600">{discovered.length}</span></div>
            {!discovered.length ? <p className="rounded-xl border border-dashed border-slate-300 p-4 text-sm text-slate-500">No Tuya devices were found. Make sure a switch is powered on and the selected network can reach it.</p> : <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {discovered.map((device) => <article key={device.device_id} className="rounded-xl border border-slate-200 bg-white p-3">
                <div className="flex items-start justify-between gap-3"><div className="min-w-0"><h4 className="truncate text-sm font-bold text-slate-900">{device.name}</h4><p className="mt-1 break-all text-xs leading-5 text-slate-500">{device.ip_address} · {device.device_id} · Protocol {device.protocol_version}</p></div><button type="button" className="btn-primary shrink-0 px-3 py-2 text-xs" disabled={device.already_added} onClick={() => {
                  setSelectedLanDeviceId(device.device_id)
                  form.setValue('name', device.name)
                  form.setValue('device_id', device.device_id)
                  form.setValue('ip_address', device.ip_address === 'unknown' ? '' : device.ip_address)
                  form.setValue('device_type', device.device_type || 'switch')
                  form.setValue('protocol_version', device.protocol_version || '3.5')
                  form.setValue('encrypted_local_key', '')
                  setManualOpen(true)
                }}>{device.already_added ? 'Added' : 'Use device'}</button></div>
                {device.already_added && <p className="mt-2 text-xs text-slate-500">This device is already configured.</p>}
              </article>)}
            </div>}
          </section>
        )}
        {!connectors.some((connector) => connector.is_active && connector.is_enrolled) && <p className="mt-4 rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-900">You can scan the ChargePilot server network now. To scan a remote site, <a href={backendUrl('/connectors')} className="font-semibold underline">enroll a site connector</a>.</p>}
      </section>

      <section className="rounded-[28px] border border-slate-200 bg-white/90 p-5 shadow-[0_20px_40px_rgba(15,23,42,0.04)] sm:p-6">
        <div className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div><p className="text-[11px] font-bold uppercase tracking-[0.24em] text-slate-500">Add</p><h2 className="mt-2 text-2xl font-bold tracking-tight text-slate-900">Add a switch</h2><p className="mt-2 text-sm leading-6 text-slate-500">Select a scan result or enter its local connection details.</p></div>
          <button type="button" className="btn-secondary" onClick={() => { setSelectedLanDeviceId(''); setManualOpen((open) => !open) }}>{manualOpen ? 'Close form' : 'Add switch manually'}</button>
        </div>
        {statusMessage && <p className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800" role="status">{statusMessage}</p>}
        {(mutation.isError || switchMutation.isError || connectorMutation.isError || deleteMutation.isError) && <div className="mb-4"><ErrorCard message={mutation.error?.message ?? switchMutation.error?.message ?? connectorMutation.error?.message ?? deleteMutation.error?.message ?? 'The action failed.'} /></div>}
        {manualOpen && <form className="grid gap-4 border-t border-slate-200 pt-5 md:grid-cols-2" onSubmit={form.handleSubmit((values) => mutation.mutate(values))}>
          <div><label className="label" htmlFor="device-name">Display name</label><input id="device-name" className="field" placeholder="Living room plug" {...form.register('name')} />{form.formState.errors.name && <FieldError>{form.formState.errors.name.message}</FieldError>}</div>
          <div><label className="label" htmlFor="device-id">Device ID</label><input id="device-id" className="field" {...form.register('device_id')} />{form.formState.errors.device_id && <FieldError>{form.formState.errors.device_id.message}</FieldError>}</div>
          <div><label className="label" htmlFor="device-ip">Local IP address</label><input id="device-ip" className="field" placeholder="192.168.0.50" {...form.register('ip_address')} /></div>
          <div><label className="label" htmlFor="device-type">Device type</label><input id="device-type" className="field" {...form.register('device_type')} /></div>
          <div><label className="label" htmlFor="device-protocol">Protocol version</label><input id="device-protocol" className="field" {...form.register('protocol_version')} /></div>
          <div><label className="label" htmlFor="device-key">Local key</label><button type="button" className="ml-2 text-xs font-semibold text-emerald-800 underline" onClick={() => setSmartLifeOpen(true)}>Fetch with Smart Life</button><input id="device-key" type="password" autoComplete="new-password" className="field" placeholder="Blank until entered or retrieved" {...form.register('encrypted_local_key')} />{form.formState.errors.encrypted_local_key && <FieldError>{form.formState.errors.encrypted_local_key.message}</FieldError>}<p className="mt-1.5 text-xs leading-5 text-slate-500">The key is kept blank until entered or matched from Smart Life.</p></div>
          <div><label className="label" htmlFor="channel-count">Number of channels</label><select id="channel-count" className="field" {...form.register('channel_count', { valueAsNumber: true })}>{Array.from({ length: 8 }, (_, index) => index + 1).map((count) => <option key={count} value={count}>{count} channel{count > 1 ? 's' : ''}</option>)}</select></div>
          <div className="flex items-end"><button type="submit" className="btn-primary w-full" disabled={mutation.isPending}><Plus size={16} className="mr-2" />{mutation.isPending ? 'Adding switch…' : 'Add switch'}</button></div>
        </form>}
      </section>

      <section className="rounded-[28px] border border-slate-200 bg-white/80 p-5 sm:p-6">
        <div className="mb-5 flex items-center justify-between"><div><p className="text-[11px] font-bold uppercase tracking-[0.24em] text-slate-500">Overview</p><h2 className="mt-2 text-2xl font-bold tracking-tight text-slate-900">Configured switches</h2></div><span className="badge border-slate-200 bg-slate-50 text-slate-600">Live</span></div>
        <div className="grid gap-4 lg:grid-cols-2">
          {data?.map((device) => <article key={device.id} className="switch-device-card rounded-[24px] border border-slate-200 p-4" data-state={device.current_state ? 'on' : 'off'}>
            <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
              <div className="min-w-0"><div className="flex items-center gap-3"><span className={`switch-state-light ${device.current_state ? 'is-on' : ''}`} aria-hidden="true" /><h3 className="truncate text-[22px] font-bold tracking-tight text-slate-900">{device.name}</h3><span className="switch-state-label">{device.current_state ? 'ON' : 'OFF'}</span></div>
                <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-slate-500"><span className="rounded-full bg-slate-100 px-2 py-1">{device.device_type || 'default'}</span><span className="rounded-full bg-slate-100 px-2 py-1">{device.ip_address || 'n/a'}</span><span className="rounded-full bg-blue-50 px-2 py-1 text-blue-700">{device.channels?.length ?? 0} channel{device.channels?.length === 1 ? '' : 's'}</span></div>
              </div>
            </div>
            {!!device.channels?.length && <div className="channel-panel mt-4 space-y-2">{device.channels.map((channel) => <div key={channel.id} className="switch-channel-row flex items-center justify-between gap-3 rounded-2xl border border-slate-200 px-3 py-2.5">
              <div className="flex items-center gap-3"><span className="channel-number rounded-full bg-slate-900 px-2 py-1 text-[9px] font-bold text-white">{channel.channel_index}</span><span className="text-sm font-medium text-slate-700">{channel.name}</span><span className="channel-state-label">{channel.current_state ? 'On' : 'Off'}</span></div>
              <button type="button" className="btn-secondary px-3 py-2 text-xs" disabled={switchMutation.isPending} aria-label={`Turn ${channel.current_state ? 'off' : 'on'} ${channel.name}`} onClick={() => switchMutation.mutate({ path: `/devices/${device.id}/channels/${channel.id}/turn-${channel.current_state ? 'off' : 'on'}`, deviceId: device.id, desiredState: !channel.current_state })}>{channel.current_state ? 'Turn off' : 'Turn on'}</button>
            </div>)}</div>}
            {canManageConnectors && <form className="mt-4 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-4" onSubmit={(event) => { event.preventDefault(); const body = new FormData(event.currentTarget); connectorMutation.mutate({ deviceId: device.id, connectorId: String(body.get('connector_id') ?? '') }) }}>
              <label className="text-xs font-semibold text-slate-600" htmlFor={`connector-${device.id}`}>Control on site</label>
              <select id={`connector-${device.id}`} name="connector_id" className="field min-w-44 flex-1 py-2 text-xs" defaultValue={device.connector_id ?? ''}><option value="">ChargePilot host (local setup only)</option>{connectors.filter((connector) => connector.is_active && connector.is_enrolled && connector.tenant_id === user?.tenant_id).map((connector) => <option key={connector.id} value={connector.id}>{connector.name}</option>)}</select>
              <button type="submit" className="btn-secondary px-3 py-2 text-xs" disabled={connectorMutation.isPending}>Save</button>
            </form>}
            <div className="mt-4 flex justify-end"><button type="button" className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold text-red-700 hover:bg-red-100" disabled={deleteMutation.isPending} onClick={() => { if (window.confirm('Delete this switch and all associated channels? This action cannot be undone.')) deleteMutation.mutate(device.id) }}>Delete switch</button></div>
          </article>)}
          {!data?.length && <div className="rounded-[24px] border border-dashed border-slate-300 bg-slate-50 px-6 py-12 text-center text-sm text-slate-500 lg:col-span-2">No switches configured yet. Scan your network or add a switch above to get started.</div>}
        </div>
      </section>

      {smartLifeOpen && <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-slate-950/60 p-4" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setSmartLifeOpen(false) }}>
        <section className="w-full max-w-xl overflow-hidden rounded-[28px] border border-white/70 bg-white shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="smartlife-title">
          <header className="ui-modal-heading flex items-start justify-between gap-4 px-6 py-6 text-white sm:px-8"><div><p className="text-[10px] font-bold uppercase tracking-[0.24em] text-emerald-100">Secure local key retrieval</p><h2 id="smartlife-title" className="mt-2 text-2xl font-bold">Connect Smart Life</h2><p className="mt-2 text-sm leading-6 text-emerald-50">ChargePilot retrieves local keys only. Device IP and other details come from the LAN scan.</p></div><button type="button" className="btn-secondary" onClick={() => setSmartLifeOpen(false)}>Close</button></header>
          <div className="space-y-5 p-6 sm:p-8">
            <div className="grid gap-3 sm:grid-cols-2"><div className="rounded-2xl border border-emerald-200 bg-emerald-50/80 p-3"><label className="label" htmlFor="smartlife-code">Smart Life account ID</label><input id="smartlife-code" maxLength={120} autoComplete="username" className="field mt-3" value={smartLifeUserCode} onChange={(event) => setSmartLifeUserCode(event.target.value)} /><p className="mt-2 text-[11px] leading-4 text-slate-500">Find it in Smart Life → Me → Settings → Account and Security.</p></div>
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3"><label className="label" htmlFor="smartlife-scheme">Mobile app</label><select id="smartlife-scheme" className="field mt-3" value={qrScheme} onChange={(event) => setQrScheme(event.target.value)}><option value="smartlife">Smart Life</option><option value="tuyaSmart">Tuya Smart</option></select><label className="mt-3 flex items-start gap-2 text-xs text-slate-600"><input type="checkbox" checked={rememberUserCode} onChange={(event) => setRememberUserCode(event.target.checked)} /><span>Remember this account ID on my ChargePilot account</span></label></div></div>
            <div className="flex flex-col items-center rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-5 text-center"><p className="text-sm font-semibold text-slate-800">Generate a secure sign-in QR</p><p className="mt-1 text-xs text-slate-500">Scan it in your mobile app and approve the request.</p><button type="button" className="btn-primary mt-4" disabled={smartLifeMutation.isPending} onClick={() => smartLifeMutation.mutate()}>{smartLifeMutation.isPending ? 'Preparing…' : 'Generate secure QR'}</button>{smartLifeStatus && <p className="mt-4 text-sm text-slate-600" role="status" aria-live="polite">{smartLifeStatus}</p>}{qr && <img className="mt-3 h-48 w-48 rounded-xl border border-slate-200 bg-white p-2" src={qr} alt="Smart Life sign-in QR code" />}</div>
            {!!linkedDevices.length && <div className="space-y-2" aria-live="polite">{linkedDevices.map((linked) => <div key={linked.device_id} className={`flex items-center justify-between gap-3 rounded-xl border p-3 ${selectedLanDeviceId === linked.device_id ? 'border-emerald-300 bg-emerald-50' : 'border-emerald-200 bg-white'}`}><span className="break-all text-xs font-semibold text-slate-800">{linked.device_id}</span><span className="shrink-0 text-[10px] font-semibold text-slate-600">{selectedLanDeviceId === linked.device_id ? 'Matched automatically' : 'Select matching LAN device'}</span></div>)}</div>}
          </div>
        </section>
      </div>}
    </div>
  )
}

function MappingsPage() {
  const { data: mappings, isLoading: mappingsLoading } = useQuery({
    queryKey: ['mappings'],
    queryFn: async () => apiFetch<Mapping[]>('/api/v1/mappings'),
  })
  const { data: endpoints } = useQuery({
    queryKey: ['endpoints'],
    queryFn: async () => apiFetch<Endpoint[]>('/api/v1/endpoints'),
  })
  const { data: devices } = useQuery({
    queryKey: ['devicesForMappings'],
    queryFn: async () => {
      const listed = await apiFetch<Device[]>('/api/v1/devices')
      return Promise.all(listed.map(async (device) => ({
        ...device,
        channels: await apiFetch<DeviceChannel[]>(`/api/v1/devices/${device.id}/channels`),
      })))
    },
  })

  const form = useForm({
    defaultValues: {
      endpoint_id: '',
      device_id: '',
      channel_id: '',
      on_threshold: 79,
      off_threshold: 99,
      minimum_state_change_interval: 300,
      enabled: true,
    },
  })
  const selectedDeviceId = form.watch('device_id')
  const availableChannels = devices?.find((device) => device.id === selectedDeviceId)?.channels ?? []

  const mutation = useMutation({
    mutationFn: (values: Record<string, unknown>) =>
      apiFetch<Mapping>('/api/v1/mappings', {
        method: 'POST',
        body: JSON.stringify({ ...values, channel_id: values.channel_id || null }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mappings'] })
      form.reset()
    },
  })
  const deleteMutation = useMutation({
    mutationFn: (mappingId: string) => apiFetch<void>(`/api/v1/mappings/${mappingId}`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mappings'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })

  if (mappingsLoading) return <LoadingCard />

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Automation"
        title="Laptop to switch mappings"
        description="Connect each laptop to a switch and decide how battery levels should control it."
      />

      <div className="panel p-5">
        <h3 className="mb-4 text-xl font-bold text-slate-900">Add mapping</h3>
        <form onSubmit={form.handleSubmit((values) => mutation.mutate(values))} className="grid gap-4 md:grid-cols-2">
          <div>
            <label className="label" htmlFor="mapping-endpoint">Endpoint</label>
            <select id="mapping-endpoint" required className="field" {...form.register('endpoint_id', { required: true })}>
              <option value="">Select endpoint</option>
              {endpoints?.map((ep) => <option key={ep.id} value={ep.id}>{ep.hostname}{ep.ip_address ? ` • ${ep.ip_address}` : ''}</option>)}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="mapping-device">Smart switch</label>
            <select id="mapping-device" required className="field" {...form.register('device_id', { required: true, onChange: () => form.setValue('channel_id', '') })}>
              <option value="">Select switch</option>
              {devices?.map((device) => <option key={device.id} value={device.id}>{device.name}</option>)}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="mapping-channel">Channel</label>
            <select id="mapping-channel" className="field" {...form.register('channel_id')}>
              <option value="">Default device state</option>
              {availableChannels.map((channel) => <option key={channel.id} value={channel.id}>{channel.name}</option>)}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="on-threshold">Turn on at or below (%)</label>
            <input id="on-threshold" type="number" min={0} max={100} required className="field" {...form.register('on_threshold', { valueAsNumber: true, required: true, min: 0, max: 100 })} />
          </div>
          <div>
            <label className="label" htmlFor="off-threshold">Turn off at or above (%)</label>
            <input id="off-threshold" type="number" min={0} max={100} required className="field" {...form.register('off_threshold', { valueAsNumber: true, required: true, min: 0, max: 100 })} />
          </div>
          <div>
            <label className="label" htmlFor="mapping-interval">Minimum time between changes (seconds)</label>
            <input id="mapping-interval" type="number" min={0} required className="field" {...form.register('minimum_state_change_interval', { valueAsNumber: true, required: true, min: 0 })} />
          </div>
          <div className="flex items-center gap-3 pt-8">
            <input id="mapping-enabled" type="checkbox" className="h-4 w-4 rounded border-slate-300 text-brand-600" {...form.register('enabled')} />
            <label htmlFor="mapping-enabled" className="text-sm text-slate-700">Enabled</label>
          </div>

          {mutation.isError && <p className="md:col-span-2 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{mutation.error.message}</p>}

          <div className="md:col-span-2">
            <button type="submit" className="btn-primary" disabled={mutation.isPending}>
              {mutation.isPending ? 'Saving…' : 'Add mapping'}
            </button>
          </div>
        </form>
      </div>

      {deleteMutation.isError && <ErrorCard message={deleteMutation.error.message} />}
      <section className="mapping-list-panel rounded-2xl border border-slate-200 bg-white p-5 shadow-soft sm:p-6" aria-labelledby="mapping-list-title">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-4"><div><h2 id="mapping-list-title" className="text-lg font-semibold text-slate-900">Current mappings</h2><p className="mt-1 text-sm text-slate-500">Review endpoint, switch, channel, and automation rules.</p></div><span className="rounded-full bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-700">{mappings?.length ?? 0} configured</span></div>
        <div className="mapping-list">
          {mappings?.map((mapping) => {
            const endpoint = endpoints?.find((item) => item.id === mapping.endpoint_id)
            const device = devices?.find((item) => item.id === mapping.device_id)
            const channel = device?.channels?.find((item) => item.id === mapping.channel_id)
            return <article key={mapping.id} className="mapping-card">
              <div className="mapping-card-main">
                <div className="mapping-route">
                  <div className="mapping-entity"><span className="mapping-entity-icon endpoint-icon" aria-hidden="true">PC</span><div className="min-w-0"><span className="mapping-overline">Endpoint</span><h3 className="mapping-entity-name">{endpoint?.hostname ?? 'Unknown endpoint'}</h3></div></div>
                  <span className="mapping-route-arrow" aria-hidden="true">→</span>
                  <div className="mapping-entity"><span className="mapping-entity-icon switch-icon" aria-hidden="true">⌁</span><div className="min-w-0"><span className="mapping-overline">Smart switch</span><h3 className="mapping-entity-name">{device?.name ?? 'Unknown switch'}</h3></div></div>
                </div>
                <div className="mapping-details"><span className="mapping-detail-pill">{channel?.name ?? 'Default device state'}</span><span className="mapping-detail-pill">Turn on at <strong>{mapping.on_threshold}% or below</strong></span><span className="mapping-detail-pill">Turn off at <strong>{mapping.off_threshold}% or above</strong></span><span className="mapping-detail-pill">Minimum interval <strong>{mapping.minimum_state_change_interval} sec</strong></span></div>
                <p className="mapping-id">Mapping ID <span>{mapping.id}</span></p>
              </div>
              <button type="button" className="inline-flex items-center justify-center rounded-lg border border-red-200 bg-red-50 px-3.5 py-2 text-xs font-semibold text-red-700 transition hover:bg-red-100" disabled={deleteMutation.isPending} onClick={() => {
                if (window.confirm('Delete this battery mapping?')) deleteMutation.mutate(mapping.id)
              }}>Delete mapping</button>
            </article>
          })}
          {!mappings?.length && <div className="mapping-empty-state"><span className="mapping-empty-icon" aria-hidden="true">⌁</span><h3>No mappings configured yet</h3><p>Add a mapping to connect a laptop with a smart switch and automate battery-based control.</p></div>}
        </div>
      </section>
    </div>
  )
}

function EndpointsPage() {
  const queryClient = useQueryClient()
  const { data, isLoading, error } = useQuery({
    queryKey: ['endpoints'],
    queryFn: async () => apiFetch<Endpoint[]>('/api/v1/endpoints'),
  })

  const deleteMutation = useMutation({
    mutationFn: (endpointId: string) => submitLegacyAction(`/endpoints/${endpointId}/delete`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['endpoints'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })

  if (isLoading) return <LoadingCard />
  if (error) return <ErrorCard message={error.message} />
  if (!data) return <ErrorCard message="The endpoint list returned no data." />

  return (
    <div className="space-y-6">
      <div className="page-header"><div><p className="eyebrow">Fleet</p><h1>Laptops</h1></div></div>
      {deleteMutation.isError && <ErrorCard message={deleteMutation.error.message} />}
      <section className="panel table-panel">
        <div className="panel-header"><h3>Tracked laptops</h3></div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Hostname</th><th>IP</th><th>Battery</th><th>Power</th><th>Last seen</th><th>Status</th><th className="align-right">Action</th></tr></thead>
            <tbody>
              {data?.map((endpoint) => <tr key={endpoint.id}>
                <td className="strong-cell">{endpoint.hostname}</td>
                <td>{endpoint.ip_address || 'unknown'}</td>
                <td>{endpoint.battery}%</td>
                <td><span className={`badge ${endpoint.charging || endpoint.ac_connected ? 'success' : 'muted'}`}>{endpoint.charging ? 'Charging' : endpoint.ac_connected ? 'On AC' : 'On battery'}</span></td>
                <td>{formatTimestamp(endpoint.last_seen_at)}</td>
                <td><span className={`badge ${endpoint.status === 'online' ? 'success' : 'muted'}`}>{endpoint.status}</span></td>
                <td className="align-right"><button type="button" className="danger-btn small-btn" disabled={deleteMutation.isPending} onClick={() => {
                  if (window.confirm(`Delete laptop ${endpoint.hostname}? Its mappings and event history will also be removed.`)) deleteMutation.mutate(endpoint.id)
                }}>Delete laptop</button></td>
              </tr>)}
              {!data?.length && <tr><td colSpan={7} className="empty-state">No laptops have reported telemetry yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}

function EventsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const requestedPage = Number(searchParams.get('page') || 1)
  const page = Number.isInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1
  const requestedSize = Number(searchParams.get('per_page') || 50)
  const perPage = [50, 100, 500].includes(requestedSize) ? requestedSize : 50
  const { data, isLoading, error } = useQuery({
    queryKey: ['events', page, perPage],
    queryFn: async () => apiFetch<EventPage>(`/api/v1/events/page?page=${page}&per_page=${perPage}`),
  })

  if (isLoading) return <LoadingCard />
  if (error) return <ErrorCard message={error.message} />
  if (!data) return <ErrorCard message="The event page returned no data." />

  return (
    <div className="space-y-6">
      <div className="page-header"><div><p className="eyebrow">Audit trail</p><h1>Automation Events</h1></div></div>
      <section className="panel table-panel">
        <div className="panel-header events-toolbar flex-wrap">
          <h3>Recent activity</h3>
          <label className="events-page-size flex items-center gap-2 text-sm">
            <span className="text-xs font-semibold text-slate-600">Show</span>
            <select className="events-page-size-select min-h-9 rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-sm text-slate-800" value={perPage} onChange={(event) => setSearchParams({ page: '1', per_page: event.target.value })}>
              {[50, 100, 500].map((size) => <option key={size} value={size}>{size} lines</option>)}
            </select>
          </label>
        </div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Time</th><th>Type</th><th>Laptop</th><th>Battery</th><th>Activity</th><th>Result</th></tr></thead>
            <tbody>
              {data.items.map((event) => <tr key={event.id}>
                <td>{formatTimestamp(event.created_at ?? null)}</td>
                <td className="strong-cell">{event.event_type}</td>
                <td>{event.endpoint ?? 'unknown'}</td>
                <td>{event.battery ?? 'n/a'}</td>
                <td>{event.activity ?? event.reason ?? event.event_type}</td>
                <td><span className={`badge ${event.success ? 'success' : 'muted'}`}>{event.success ? 'Success' : 'Failed'}</span></td>
              </tr>)}
              {!data.items.length && <tr><td colSpan={6} className="empty-state">No automation events have been recorded yet.</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="flex flex-col gap-3 border-t border-slate-200 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-slate-500" aria-live="polite">{data.total_events ? `Showing ${data.first_row}–${data.last_row} of ${data.total_events} events` : 'No events to display'}</p>
          <nav className="flex items-center gap-1.5" aria-label="Event log pages">
            <button type="button" className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 transition hover:border-blue-300 hover:text-blue-700 disabled:cursor-not-allowed disabled:text-slate-400" disabled={data.page <= 1} onClick={() => setSearchParams({ page: String(data.page - 1), per_page: String(perPage) })}>Previous</button>
            <span className="px-2 text-xs font-semibold text-slate-600">Page {data.page} of {data.total_pages}</span>
            <button type="button" className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 transition hover:border-blue-300 hover:text-blue-700 disabled:cursor-not-allowed disabled:text-slate-400" disabled={data.page >= data.total_pages} onClick={() => setSearchParams({ page: String(data.page + 1), per_page: String(perPage) })}>Next</button>
          </nav>
        </div>
      </section>
    </div>
  )
}

function formatTimestamp(value: string | null) {
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

function FieldError({ children }: { children: ReactNode }) {
  return <p className="mt-1.5 text-sm text-red-700" role="alert">{children}</p>
}

function MetricMini({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl border border-white/15 bg-white/10 px-3 py-2.5 backdrop-blur-sm"><p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-blue-100">{label}</p><p className="mt-1 text-xl font-bold text-white">{value}</p></div>
}

function LoadingScreen() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100">
      <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white px-5 py-3 shadow-soft">
        <CircleDashed className="animate-spin text-brand-600" size={18} />
        <span className="text-sm font-medium text-slate-700">Loading ChargePilot…</span>
      </div>
    </div>
  )
}

function LoadingCard() {
  return <div className="panel p-8 text-sm text-slate-600">Loading…</div>
}

function ErrorCard({ message }: { message: string }) {
  return <div className="panel border-red-200 bg-red-50 p-5 text-sm text-red-700">{message}</div>
}

function MetricCard({
  label,
  value,
  hint,
  icon: Icon,
  tone,
}: {
  label: string
  value: string
  hint: string
  icon: typeof BatteryCharging
  tone: 'blue' | 'emerald' | 'violet' | 'amber'
}) {
  const tones = {
    blue: 'bg-blue-50 text-blue-700',
    emerald: 'bg-emerald-50 text-emerald-700',
    violet: 'bg-violet-50 text-violet-700',
    amber: 'bg-amber-50 text-amber-700',
  }

  return (
    <div className="panel p-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">{label}</p>
          <p className="mt-3 text-3xl font-bold text-slate-900">{value}</p>
          <p className="mt-1 text-sm text-slate-500">{hint}</p>
        </div>
        <div className={`flex h-12 w-12 items-center justify-center rounded-2xl ${tones[tone]}`}>
          <Icon size={22} />
        </div>
      </div>
    </div>
  )
}

function PageHeader({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) {
  return (
    <div className="panel p-5 sm:p-6">
      <p className="text-xs font-semibold uppercase tracking-[0.22em] text-brand-600">{eyebrow}</p>
      <h2 className="mt-2 text-2xl font-bold text-slate-900">{title}</h2>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">{description}</p>
    </div>
  )
}

export default App
