import { QueryClient, QueryClientProvider, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { zodResolver } from '@hookform/resolvers/zod'
import {
  BatteryCharging,
  Activity,
  Bell,
  Building2,
  Cable,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleDashed,
  CircleHelp,
  Cpu,
  List,
  KeyRound,
  LayoutGrid,
  HardDrive,
  LogIn,
  LogOut,
  Mail,
  MemoryStick,
  Menu,
  Moon,
  MonitorSmartphone,
  Network,
  Pencil,
  PlugZap,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Sun,
  Users,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { BrowserRouter, NavLink, Navigate, Outlet, Route, Routes, useNavigate, useSearchParams } from 'react-router-dom'
import { z } from 'zod'

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

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      refetchOnWindowFocus: false,
    },
  },
})

const AGENT_RELEASE_URL = 'https://github.com/jsramitgupta/ChargePilot/releases/latest'
const AGENT_RELEASE_API_URL = 'https://api.github.com/repos/jsramitgupta/ChargePilot/releases/latest'

type User = {
  id: string
  username: string
  email?: string | null
  role: string
  tenant_id?: string | null
  is_admin: boolean
  smartlife_user_code?: string | null
  timezone?: string
  tenant_name?: string | null
}

type Endpoint = {
  id: string
  tenant_id?: string | null
  tenant_name?: string | null
  display_name?: string
  hostname: string
  hardware_uuid: string | null
  installation_id?: string | null
  platform: 'windows' | 'macos' | 'android' | 'ios'
  device_class?: 'laptop' | 'desktop' | 'phone' | 'tablet' | null
  ip_address: string | null
  battery: number
  charging: boolean
  ac_connected: boolean | null
  last_seen_at: string | null
  status: 'online' | 'offline'
  credential_enrolled: boolean
  mapped_device: string
  mapped_device_tenant?: string | null
  switch_state: boolean | null
  reporting_interval_minutes: number
}

type SystemMetrics = {
  cpu_usage_percent: number | null
  gpu_usage_percent: number | null
  memory_used_bytes: number | null
  memory_total_bytes: number | null
  disks: Array<{ name: string; used_bytes: number; total_bytes: number }>
}

type EndpointReading = {
  timestamp: string
  battery_percentage: number
  charging: boolean
  ac_connected: boolean
  system_metrics: SystemMetrics | null
}

type EndpointDetails = {
  id: string
  display_name: string
  hostname: string
  platform: Endpoint['platform']
  device_class: Endpoint['device_class']
  hardware_uuid: string | null
  installation_id: string | null
  ip_address: string | null
  battery: number
  charging: boolean
  ac_connected: boolean | null
  last_seen_at: string | null
  status: 'online' | 'offline'
  agent_version: string | null
  enabled: boolean
  automation_enabled: boolean
  automation_available: boolean
  reporting_interval_minutes: number
  mappings: Array<{
    id: string
    name: string
    enabled: boolean
    on_threshold: number
    off_threshold: number
    minimum_state_change_interval: number
    switch_state: boolean
  }>
  readings: EndpointReading[]
}

type EndpointPageSize = 50 | 100
type EndpointStatusFilter = 'all' | 'online' | 'offline'

type TenantReportingSettings = {
  tenant_id: string
  tenant_name: string
  telemetry_interval_minutes: number
}

type Device = {
  id: string
  tenant_id?: string | null
  tenant_name?: string | null
  device_id: string
  name: string
  ip_address?: string | null
  device_type?: string | null
  protocol_version?: string | null
  enabled?: boolean | null
  current_state?: boolean | null
  last_state_change_at?: string | null
  last_seen_at?: string | null
  power_dp_id?: string | null
  power_multiplier?: number
  energy_dp_id?: string | null
  energy_multiplier?: number
  energy_counter_type?: 'cumulative' | 'monthly'
  meter_power_watts?: number | null
  meter_power_sample_at?: string | null
  meter_energy_month_kwh?: number | null
  meter_energy_sample_at?: string | null
  meter_month_key?: string | null
  meter_last_sample_at?: string | null
  meter_tracking_since?: string | null
  channels?: DeviceChannel[]
  connector_id?: string | null
}

type DeviceMeterSettings = {
  power_dp_id: string | null
  power_multiplier: number
  energy_dp_id: string | null
  energy_multiplier: number
  energy_counter_type: 'cumulative' | 'monthly'
}

type MeterCandidate = {
  id: string
  label: string
  sample: number
  suggested_role: 'power' | 'energy' | null
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
  tenant_name?: string | null
  is_active: boolean
  is_enrolled: boolean
  is_online: boolean
  last_seen_at?: string | null
}

type DeviceStatusRefresh = {
  commands: Array<{ id: string; device_id: string; channel_id: string | null }>
  skipped_devices: Array<{ device_id: string; reason: string }>
}

type ConnectorCommandStatus = {
  status: 'queued' | 'leased' | 'succeeded' | 'failed' | 'expired'
  result?: { error?: string; candidates?: MeterCandidate[] } | null
}

type DevicesPageData = {
  devices: Device[]
}

type AdminUser = {
  id: string
  username: string
  email?: string | null
  role: string
  tenant_id?: string | null
  tenant_name?: string | null
  created_at: string
}

type TenantInfo = {
  id: string
  name: string
  slug: string
  agent_token: string
  created_at: string
}

type AccountInvitationInfo = {
  id: string
  tenant_id: string
  tenant_name?: string | null
  username: string
  email: string
  role: string
  created_at: string
  expires_at: string
  used_at?: string | null
  revoked_at?: string | null
  is_active: boolean
}

type EndpointEnrollment = {
  id: string
  tenant_name: string
  created_at: string
  expires_at: string
  enrollment_count: number
  last_used_at?: string | null
}

type RevealedEndpointEnrollment = {
  id: string
  enrollment_code: string
  expires_at: string
}

type SmartLifeDevice = {
  device_id: string
  local_key: string
}

type Mapping = {
  id: string
  tenant_name?: string | null
  endpoint_id: string
  device_id: string
  channel_id?: string | null
  turn_on_enabled: boolean
  on_threshold: number
  off_threshold: number
  turn_off_when_charging_enabled: boolean
  charging_off_threshold: number
  minimum_state_change_interval: number
  enabled: boolean
}

type MappingFormValues = {
  endpoint_id: string
  device_id: string
  channel_id: string
  turn_on_enabled: boolean
  on_threshold: number
  off_threshold: number
  turn_off_when_charging_enabled: boolean
  charging_off_threshold: number
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

const deviceSchema = z.object({
  name: z.string().min(1, 'Display name is required'),
  device_id: z.string().min(1, 'Device ID is required'),
  ip_address: z.string().default(''),
  device_type: z.string().default('switch'),
  protocol_version: z.string().default('3.5'),
  encrypted_local_key: z.string().min(1, 'Local key is required'),
  enabled: z.boolean().default(true),
  channel_count: z.number().int().min(1).max(8),
  connector_id: z.string().default(''),
})

type DeviceFormInput = z.input<typeof deviceSchema>
type DeviceFormValues = z.output<typeof deviceSchema>

const API_BASE_URL = (
  window.CHARGEPILOT_CONFIG?.apiBaseUrl ?? import.meta.env.VITE_API_BASE_URL ?? ''
).replace(/\/+$/, '')
const FRONTEND_BASE_URL = (
  window.CHARGEPILOT_CONFIG?.frontendUrl ?? ''
).replace(/\/+$/, '') || window.location.origin

const TIME_ZONE_REGIONS = [
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
const TIME_ZONE_OPTIONS = typeof Intl.supportedValuesOf === 'function'
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

async function waitForConnectorCommands(
  commands: Array<{ id: string }>,
  timeoutMs = 45_000,
): Promise<void> {
  const pendingIds = new Set(commands.map((command) => command.id))
  const deadline = Date.now() + timeoutMs

  while (pendingIds.size) {
    const statuses = await Promise.all(
      [...pendingIds].map(async (id) => ({
        id,
        command: await apiFetch<ConnectorCommandStatus>(`/api/v1/connectors/commands/${id}`),
      })),
    )

    for (const { id, command } of statuses) {
      if (command.status === 'failed' || command.status === 'expired') {
        throw new Error(command.result?.error ?? `The site connector ${command.status} the switch command.`)
      }
      if (command.status === 'succeeded') pendingIds.delete(id)
    }

    if (!pendingIds.size) return
    if (Date.now() >= deadline) {
      throw new Error('The site connector did not complete the switch status request in time.')
    }
    await new Promise((resolve) => window.setTimeout(resolve, 2000))
  }
}

async function discoverMeterReadings(deviceId: string): Promise<MeterCandidate[]> {
  const response = await apiFetch<{ command_id?: string; candidates?: MeterCandidate[] }>(
    `/api/v1/devices/${deviceId}/meter-discovery`,
    { method: 'POST' },
  )
  if (response.candidates) return response.candidates
  if (!response.command_id) throw new Error('The switch did not return any readings.')
  await waitForConnectorCommands([{ id: response.command_id }])
  const command = await apiFetch<ConnectorCommandStatus>(
    `/api/v1/connectors/commands/${response.command_id}`,
  )
  if (!Array.isArray(command.result?.candidates)) {
    throw new Error('The site connector finished the check without returning a reading list. Update it and try again.')
  }
  return command.result.candidates
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

const ENDPOINTS_REFRESH_INTERVAL = 30_000
const OVERVIEW_ENDPOINT_LIMIT = 10

function sortEndpointsByLastSeen(endpoints: Endpoint[]) {
  return [...endpoints].sort((first, second) => {
    const firstSeen = first.last_seen_at ? Date.parse(first.last_seen_at) : Number.NEGATIVE_INFINITY
    const secondSeen = second.last_seen_at ? Date.parse(second.last_seen_at) : Number.NEGATIVE_INFINITY
    const firstTimestamp = Number.isFinite(firstSeen) ? firstSeen : Number.NEGATIVE_INFINITY
    const secondTimestamp = Number.isFinite(secondSeen) ? secondSeen : Number.NEGATIVE_INFINITY

    return secondTimestamp - firstTimestamp
      || (first.display_name || first.hostname).localeCompare(second.display_name || second.hostname)
  })
}

const PLATFORM_NAMES: Record<Endpoint['platform'], string> = {
  windows: 'Windows',
  macos: 'macOS',
  android: 'Android',
  ios: 'iOS',
}

function PlatformMark({ platform }: { platform: Endpoint['platform'] }) {
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

function EndpointIdentity({ endpoint }: { endpoint: Endpoint }) {
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
          <Route path="/verify-email" element={<VerifyEmailPage />} />
          <Route path="/accept-invitation" element={<AcceptInvitationPage />} />
          <Route element={<ProtectedLayout />}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/devices" element={<DevicesPage />} />
            <Route path="/mappings" element={<MappingsPage />} />
            <Route path="/endpoints" element={<EndpointsPage />} />
            <Route path="/events" element={<EventsPage />} />
            <Route path="/account" element={<Navigate to="/profile" replace />} />
            <Route path="/connectors" element={<ConnectorsPage />} />
            <Route path="/profile" element={<ProfilePage />} />
            <Route path="/users" element={<UsersPage />} />
            <Route path="/tenants" element={<TenantsPage />} />
            <Route path="/agent" element={<AgentSetupPage />} />
            <Route path="/support" element={<SupportPage />} />
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
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', isDark ? '#101c19' : '#eef3f0')
    window.localStorage.setItem('chargepilot-theme', isDark ? 'dark' : 'light')
  }, [isDark])

  return [isDark, setIsDark] as const
}

function ThemeToggleButton({ isDark, onToggle, className = '' }: { isDark: boolean; onToggle: () => void; className?: string }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className={`theme-toggle ${className}`}
      aria-label={isDark ? 'Use light theme' : 'Use dark theme'}
      aria-pressed={isDark}
    >
      {isDark ? <Sun size={18} aria-hidden="true" /> : <Moon size={18} aria-hidden="true" />}
    </button>
  )
}

function AppShell({ user }: { user: User }) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [isDark, setIsDark] = useAppTheme()
  const navigate = useNavigate()
  const logoutMutation = useMutation({
    mutationFn: () => apiFetch<{ status: string }>('/api/v1/auth/logout', { method: 'POST' }),
    onSuccess: () => {
      queryClient.clear()
      navigate('/login', { replace: true })
    },
  })

  useEffect(() => {
    document.body.dataset.userTimezone = user.timezone || 'UTC'
    return () => {
      delete document.body.dataset.userTimezone
    }
  }, [user.timezone])

  const navItems = [
    { to: '/', label: 'Overview', icon: LayoutGrid },
    { to: '/endpoints', label: 'Endpoints', icon: MonitorSmartphone },
    { to: '/devices', label: 'Switches', icon: PlugZap },
    { to: '/mappings', label: 'Automation maps', icon: Cable },
    { to: '/connectors', label: 'Site connectors', icon: Network },
    { to: '/events', label: 'Activity', icon: Bell },
  ]

  return (
    <div className="workspace">
      {mobileOpen && <button type="button" className="rail-scrim" aria-label="Close navigation" onClick={() => setMobileOpen(false)} />}
      <aside className={`workspace-rail ${mobileOpen ? 'is-open' : ''}`}>
        <NavLink to="/" className="rail-brand" aria-label="ChargePilot overview" onClick={() => setMobileOpen(false)}>
          <span className="rail-mark"><BatteryCharging size={21} aria-hidden="true" /></span>
          <span><strong>ChargePilot</strong><small>Energy control</small></span>
        </NavLink>
        <div className="rail-tenant"><span className="rail-tenant-dot" /><span><small>Workspace</small><strong>{user.tenant_name ?? 'System'}</strong></span></div>
        <nav id="mainNav" className="rail-nav" aria-label="Main navigation">
          <p className="rail-caption">Monitor</p>
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} end={to === '/'} onClick={() => setMobileOpen(false)} className="rail-link">
              <Icon size={17} aria-hidden="true" /><span>{label}</span>
            </NavLink>
          ))}
          <NavLink to="/agent" onClick={() => setMobileOpen(false)} className="rail-link"><Plus size={17} aria-hidden="true" /><span>Set up a device</span></NavLink>
          {(user.role === 'super_admin' || user.role === 'tenant_admin' || user.role === 'manager') && <>
            <p className="rail-caption rail-caption-spaced">Manage</p>
            <NavLink to="/users" onClick={() => setMobileOpen(false)} className="rail-link"><Users size={17} aria-hidden="true" /><span>People & invites</span></NavLink>
          </>}
          {user.role === 'super_admin' && <NavLink to="/tenants" onClick={() => setMobileOpen(false)} className="rail-link"><Building2 size={17} aria-hidden="true" /><span>Tenants</span></NavLink>}
        </nav>
        <div className="rail-footer">
          <NavLink to="/profile" className="rail-profile" aria-label="Account settings" onClick={() => setMobileOpen(false)}>
            <span className="profile-initial">{user.username.slice(0, 1).toUpperCase()}</span>
            <span className="profile-copy"><strong>Account</strong><small>{user.username}</small></span>
          </NavLink>
          <NavLink to="/support" className="rail-footer-link" onClick={() => setMobileOpen(false)}><Mail size={15} />Contact support</NavLink>
          <button type="button" className="rail-footer-link" onClick={() => logoutMutation.mutate()} disabled={logoutMutation.isPending}><LogOut size={15} />{logoutMutation.isPending ? 'Signing out…' : 'Sign out'}</button>
        </div>
      </aside>
      <div className="workspace-body">
        <header className="workspace-topbar">
          <button className="nav-toggle" type="button" aria-label={mobileOpen ? 'Close navigation' : 'Open navigation'} aria-expanded={mobileOpen} aria-controls="mainNav" onClick={() => setMobileOpen((value) => !value)}><Menu size={19} aria-hidden="true" /></button>
          <div className="topbar-context"><span className="topbar-live"><i />Control plane</span><span>Battery automation</span></div>
          <div className="topbar-actions">
            <ThemeToggleButton isDark={isDark} onToggle={() => setIsDark((value) => !value)} />
            <span className="topbar-role"><ShieldCheck size={14} aria-hidden="true" />{user.role.replaceAll('_', ' ')}</span>
          </div>
        </header>
        {logoutMutation.error && <p className="workspace-error" role="alert">{logoutMutation.error.message}</p>}
        <main className="page-shell"><Outlet /></main>
      </div>
    </div>
  )
}

function AuthBrandPanel() {
  return (
    <aside className="auth-story" aria-label="ChargePilot purpose">
      <div className="auth-story-brand"><span className="rail-mark"><BatteryCharging size={21} aria-hidden="true" /></span><strong>ChargePilot</strong></div>
      <div className="auth-story-copy">
        <span className="auth-story-kicker">Local energy, under control</span>
        <h2>Keep the battery.<br />Lose the guesswork.</h2>
        <p>Battery monitoring across your devices, paired with switches that stay on their own network.</p>
      </div>
      <div className="energy-path" aria-label="Device telemetry flows through your site connector to your switch">
        <div className="energy-node"><MonitorSmartphone size={18} /><span>Device</span></div>
        <span className="energy-wire"><i /></span>
        <div className="energy-node"><Network size={18} /><span>Site link</span></div>
        <span className="energy-wire"><i /></span>
        <div className="energy-node"><PlugZap size={18} /><span>Switch</span></div>
      </div>
      <p className="auth-story-foot">Battery rules run in ChargePilot. Device control stays local.</p>
    </aside>
  )
}

let turnstileScriptPromise: Promise<void> | null = null

function loadTurnstileScript() {
  if (window.turnstile) return Promise.resolve()
  if (turnstileScriptPromise) return turnstileScriptPromise

  turnstileScriptPromise = new Promise<void>((resolve, reject) => {
    const script = document.createElement('script')
    script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'
    script.async = true
    script.defer = true
    script.onload = () => {
      if (window.turnstile) resolve()
      else reject(new Error('Human verification could not be initialized.'))
    }
    script.onerror = () => {
      turnstileScriptPromise = null
      script.remove()
      reject(new Error('Human verification could not be loaded.'))
    }
    document.head.appendChild(script)
  })
  return turnstileScriptPromise
}

function TurnstileChallenge({
  onToken,
  action = 'registration',
}: {
  onToken: (token: string) => void
  action?: string
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const siteKey = window.CHARGEPILOT_CONFIG?.turnstileSiteKey ?? ''
  const [widgetError, setWidgetError] = useState('')

  useEffect(() => {
    if (!siteKey) return

    let disposed = false
    let widgetId: string | undefined
    void loadTurnstileScript()
      .then(() => {
        if (disposed || !containerRef.current || !window.turnstile) return
        widgetId = window.turnstile.render(containerRef.current, {
          sitekey: siteKey,
          action,
          theme: 'auto',
          callback: (token) => {
            onToken(token)
            setWidgetError('')
          },
          'expired-callback': () => onToken(''),
          'error-callback': () => {
            onToken('')
            setWidgetError('Human verification is unavailable. Refresh the page and try again.')
          },
        })
      })
      .catch(() => {
        if (!disposed) {
          onToken('')
          setWidgetError('Human verification could not be loaded. Check your connection and refresh.')
        }
      })

    return () => {
      disposed = true
      if (widgetId) window.turnstile?.remove(widgetId)
    }
  }, [action, onToken, siteKey])

  return (
    <div className="turnstile-verification">
      {siteKey
        ? <div ref={containerRef} aria-label="Human verification challenge" />
        : <p className="turnstile-status" role="alert">New account registration is currently unavailable. Human verification has not been configured.</p>}
      {widgetError && <p className="turnstile-status" role="alert">{widgetError}</p>}
    </div>
  )
}

function LoginPage() {
  const [searchParams] = useSearchParams()
  const [isDark, setIsDark] = useAppTheme()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const loginMutation = useMutation({
    mutationFn: () => apiFetch<{ user: User }>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
    onSuccess: ({ user }) => {
      queryClient.setQueryData(['session'], user)
      navigate('/', { replace: true })
    },
  })

  return (
    <div className="auth-shell">
      <ThemeToggleButton isDark={isDark} onToggle={() => setIsDark((value) => !value)} className="auth-theme-toggle" />
      <AuthBrandPanel />
      <section className="auth-card" aria-labelledby="login-title">
        <div className="flex items-center justify-center"><div className="brand-mark auth-brand-mark">C</div></div>
        <div className="auth-badges"><span>ChargePilot</span><span>Local-first control</span></div>
        <h1 id="login-title">Welcome back</h1>
        <p className="auth-subtle">Sign in to your tenant and manage your battery automation.</p>
        {searchParams.get('message') && <p className="alert success mt-5" role="status">{searchParams.get('message')}</p>}
        {searchParams.get('error') && <p className="alert error mt-4" role="alert">{searchParams.get('error')}</p>}
        <form onSubmit={(event) => { event.preventDefault(); loginMutation.mutate() }} className="auth-form">
          <div className="field-group">
            <label htmlFor="username">Username</label>
            <input id="username" name="username" type="text" autoComplete="username" required className="field" value={username} onChange={(event) => setUsername(event.target.value)} />
          </div>
          <div className="field-group">
            <label htmlFor="password">Password</label>
            <input id="password" name="password" type="password" autoComplete="current-password" required className="field" value={password} onChange={(event) => setPassword(event.target.value)} />
          </div>
          {loginMutation.error && <ErrorCard message={loginMutation.error.message} />}
          <button type="submit" className="primary-btn large-btn w-full" disabled={loginMutation.isPending}><LogIn size={16} className="mr-2" />{loginMutation.isPending ? 'Signing in…' : 'Log in'}</button>
        </form>
        <div className="auth-divider" />
        <div className="auth-signup">
          <p>Joining an existing workspace? Ask its administrator to email you an invitation.</p>
          <div className="auth-actions">
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
  const navigate = useNavigate()
  const accountType = searchParams.get('account_type') === 'tenant' ? 'tenant' : 'standard'
  const error = searchParams.get('error')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [email, setEmail] = useState('')
  const [inviteCode, setInviteCode] = useState('')
  const [tenantName, setTenantName] = useState('')
  const [challenge, setChallenge] = useState({ accountType, token: '' })
  const [challengeReset, setChallengeReset] = useState(0)
  const turnstileToken = challenge.accountType === accountType ? challenge.token : ''
  const setTurnstileToken = useCallback((token: string) => {
    setChallenge({ accountType, token })
  }, [accountType])

  const registerMutation = useMutation({
    mutationFn: () => apiFetch<{ message: string }>('/api/v1/auth/register', {
      method: 'POST',
      body: JSON.stringify({
        account_type: accountType,
        username,
        password,
        email,
        turnstile_token: turnstileToken,
        ...(accountType === 'standard' ? { invite_code: inviteCode } : { tenant_name: tenantName }),
      }),
    }),
    onError: () => {
      setChallenge({ accountType, token: '' })
      setChallengeReset((value) => value + 1)
    },
    onSuccess: () => {
      navigate('/verify-email?sent=1', { replace: true })
    },
  })

  return (
    <div className="auth-shell">
      <ThemeToggleButton isDark={isDark} onToggle={() => setIsDark((value) => !value)} className="auth-theme-toggle" />
      <AuthBrandPanel />
      <section className="auth-card auth-card-wide" aria-labelledby="register-title">
        <div className="flex items-center justify-center"><div className="brand-mark auth-brand-mark">C</div></div>
        <div className="auth-badges"><span>Create account</span><span>Secure access</span></div>
        <h1 id="register-title">Choose your access</h1>
        {error && <p className="alert error mt-4" role="alert">{error}</p>}
        <div className="auth-choice-grid">
          <a href={frontendUrl('/register?account_type=standard')} className={`choice-card ${accountType === 'standard' ? 'active' : ''}`}>
            <span className="choice-title">Standard user</span><span className="choice-copy">Join your team with a one-time invite code.</span>
          </a>
          <a href={frontendUrl('/register?account_type=tenant')} className={`choice-card ${accountType === 'tenant' ? 'active' : ''}`}>
            <span className="choice-title">Tenant admin</span><span className="choice-copy">Creates a new isolated tenant.</span>
          </a>
        </div>
        <form onSubmit={(event) => { event.preventDefault(); registerMutation.mutate() }} className="auth-form">
          <div className="field-group">
            <label htmlFor="username">Username</label>
            <input id="username" name="username" type="text" autoComplete="username" minLength={3} maxLength={80} required className="field" value={username} onChange={(event) => setUsername(event.target.value)} />
          </div>
          <div className="field-group">
            <label htmlFor="password">Password</label>
            <input id="password" name="password" type="password" autoComplete="new-password" minLength={12} maxLength={72} required className="field" value={password} onChange={(event) => setPassword(event.target.value)} />
          </div>
          <div className="field-group">
            <label htmlFor="email">Email address</label>
            <input id="email" name="email" type="email" autoComplete="email" maxLength={254} required className="field" value={email} onChange={(event) => setEmail(event.target.value)} />
            <p className="auth-helper">We’ll send a verification link that expires in 30 minutes.</p>
          </div>
          {accountType === 'tenant'
            ? <div className="field-group"><label htmlFor="tenant_name">Tenant name</label><input id="tenant_name" name="tenant_name" type="text" minLength={1} maxLength={160} placeholder="My tenant" className="field" required value={tenantName} onChange={(event) => setTenantName(event.target.value)} /></div>
            : <div className="field-group"><label htmlFor="invite_code">One-time tenant invite code</label><input id="invite_code" name="invite_code" type="text" autoComplete="off" spellCheck={false} required className="field font-mono" value={inviteCode} onChange={(event) => setInviteCode(event.target.value)} /><p className="auth-helper">Ask your tenant administrator for a code. It can be used once and expires after seven days.</p></div>}
          <div className="field-group">
            <span>Human verification</span>
            <TurnstileChallenge key={`${accountType}-${challengeReset}`} onToken={setTurnstileToken} />
          </div>
          {registerMutation.error && <ErrorCard message={registerMutation.error.message} />}
          <button type="submit" className="primary-btn large-btn w-full" disabled={registerMutation.isPending || !turnstileToken}>{registerMutation.isPending ? 'Creating account…' : accountType === 'tenant' ? 'Create tenant and admin account' : 'Create standard user account'}</button>
        </form>
        <p className="auth-signin">Already have an account? <a href={frontendUrl('/login')}>Sign in</a></p>
      </section>
    </div>
  )
}

function VerifyEmailPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const token = searchParams.get('token') ?? ''
  const sent = searchParams.get('sent') === '1'
  const [isDark, setIsDark] = useAppTheme()
  const [email, setEmail] = useState('')
  const [challenge, setChallenge] = useState('')
  const [challengeReset, setChallengeReset] = useState(0)
  const [resent, setResent] = useState(false)

  const verifyMutation = useMutation({
    mutationFn: () => apiFetch<{ user: User }>('/api/v1/auth/verify-email', {
      method: 'POST',
      body: JSON.stringify({ token }),
    }),
    onSuccess: ({ user }) => {
      queryClient.setQueryData(['session'], user)
      navigate('/', { replace: true })
    },
  })

  const resendMutation = useMutation({
    mutationFn: () => apiFetch<{ message: string }>('/api/v1/auth/resend-verification', {
      method: 'POST',
      body: JSON.stringify({ email, turnstile_token: challenge }),
    }),
    onSuccess: () => {
      setResent(true)
      setChallenge('')
      setChallengeReset((value) => value + 1)
    },
    onError: () => {
      setChallenge('')
      setChallengeReset((value) => value + 1)
    },
  })

  return (
    <div className="auth-shell">
      <ThemeToggleButton isDark={isDark} onToggle={() => setIsDark((value) => !value)} className="auth-theme-toggle" />
      <AuthBrandPanel />
      <section className="auth-card auth-card-wide" aria-labelledby="verify-email-title">
        <div className="flex items-center justify-center"><div className="brand-mark auth-brand-mark">C</div></div>
        <div className="auth-badges"><span>Account verification</span><span>Secure access</span></div>
        <h1 id="verify-email-title">Verify your email</h1>
        {sent && <p className="alert success mt-4" role="status">Your account is ready. Check your inbox for the verification link; it expires in 30 minutes.</p>}
        {token && <p className="auth-subtle">Select verify to activate your ChargePilot account.</p>}
        {token && (
          <div className="mt-5">
            {verifyMutation.error && <ErrorCard message={verifyMutation.error.message} />}
            <button type="button" className="primary-btn large-btn w-full" disabled={verifyMutation.isPending} onClick={() => verifyMutation.mutate()}>
              {verifyMutation.isPending ? 'Verifying…' : 'Verify email and sign in'}
            </button>
          </div>
        )}
        <div className="auth-divider" />
        <form onSubmit={(event) => { event.preventDefault(); resendMutation.mutate() }} className="auth-form">
          <p className="auth-subtle">{token ? 'If the link expired, request a fresh one.' : 'Need another verification link? Enter your account email.'}</p>
          <div className="field-group">
            <label htmlFor="verification-email">Email address</label>
            <input id="verification-email" name="email" type="email" autoComplete="email" maxLength={254} required className="field" value={email} onChange={(event) => setEmail(event.target.value)} />
          </div>
          <div className="field-group">
            <span>Human verification</span>
            <TurnstileChallenge key={challengeReset} onToken={setChallenge} />
          </div>
          {resendMutation.error && <ErrorCard message={resendMutation.error.message} />}
          {resent && <p className="alert success" role="status">If the account needs verification, a new email has been sent.</p>}
          <button type="submit" className="btn-secondary large-btn w-full" disabled={resendMutation.isPending || !challenge}>
            {resendMutation.isPending ? 'Sending…' : 'Resend verification email'}
          </button>
        </form>
        <p className="auth-signin"><a href={frontendUrl('/login')}>Back to sign in</a></p>
      </section>
    </div>
  )
}

function AcceptInvitationPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const [code] = useState(() => searchParams.get('code') ?? '')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [formError, setFormError] = useState('')
  useEffect(() => {
    if (code) navigate('/accept-invitation', { replace: true })
  }, [code, navigate])

  const invitationQuery = useQuery({
    queryKey: ['account-invitation', code],
    queryFn: () => apiFetch<{ username: string; email: string; role: string; tenant_name: string; expires_at: string }>(
      '/api/v1/auth/invitation-details',
      { method: 'POST', body: JSON.stringify({ code }) },
    ),
    enabled: Boolean(code),
    retry: false,
  })
  const acceptMutation = useMutation({
    mutationFn: () => apiFetch<{ user: User }>('/api/v1/auth/accept-invitation', {
      method: 'POST',
      body: JSON.stringify({ code, password }),
    }),
    onSuccess: ({ user }) => {
      queryClient.setQueryData(['session'], user)
      navigate('/', { replace: true })
    },
  })

  function submitPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFormError('')
    if (password !== confirmPassword) {
      setFormError('The passwords do not match.')
      return
    }
    if (new TextEncoder().encode(password).length > 72) {
      setFormError('The password must be 72 UTF-8 bytes or fewer.')
      return
    }
    acceptMutation.mutate()
  }

  const invite = invitationQuery.data
  const detailsError = invitationQuery.error
  const [isDark, setIsDark] = useAppTheme()

  return (
    <div className="auth-shell">
      <ThemeToggleButton isDark={isDark} onToggle={() => setIsDark((value) => !value)} className="auth-theme-toggle" />
      <AuthBrandPanel />
      <section className="auth-card auth-card-wide" aria-labelledby="invitation-title">
        <h1 id="invitation-title">Set your password</h1>
        {invitationQuery.isLoading && <p className="auth-subtle">Checking your invitation…</p>}
        {detailsError && <ErrorCard message={detailsError.message} />}
        {!code && <ErrorCard message="This invitation link is missing its one-time setup code." />}
        {invite && <>
          <p className="auth-subtle">Choose a password to activate your ChargePilot account.</p>
          <dl className="invitation-account-details">
            <div><dt>Username</dt><dd>{invite.username}</dd></div>
            <div><dt>Email</dt><dd>{invite.email}</dd></div>
            <div><dt>Workspace</dt><dd>{invite.tenant_name}</dd></div>
            <div><dt>Access</dt><dd>{invite.role.replaceAll('_', ' ')}</dd></div>
          </dl>
          <form className="auth-form" onSubmit={submitPassword}>
            <label className="field-group" htmlFor="invited-password">
              New password
              <input
                id="invited-password"
                type="password"
                autoComplete="new-password"
                minLength={12}
                maxLength={72}
                required
                className="field"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
              <span className="auth-helper">Use at least 12 characters.</span>
            </label>
            <label className="field-group" htmlFor="invited-password-confirm">
              Confirm password
              <input
                id="invited-password-confirm"
                type="password"
                autoComplete="new-password"
                minLength={12}
                maxLength={72}
                required
                className="field"
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
              />
            </label>
            {(formError || acceptMutation.error) && <ErrorCard message={formError || acceptMutation.error?.message || 'The invitation could not be accepted.'} />}
            <button type="submit" className="primary-btn large-btn w-full" disabled={acceptMutation.isPending}>
              {acceptMutation.isPending ? 'Activating account…' : 'Set password and sign in'}
            </button>
          </form>
        </>}
        <p className="auth-signin"><a href={frontendUrl('/login')}>Back to sign in</a></p>
      </section>
    </div>
  )
}

function SupportPage() {
  const { data: user } = useSession()
  const [replyEmail, setReplyEmail] = useState<string | null>(null)
  const replyAddress = replyEmail ?? user?.email ?? ''
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [sent, setSent] = useState(false)
  const supportQuery = useQuery({
    queryKey: ['support-config'],
    queryFn: () => apiFetch<{ configured: boolean; recipient: string }>('/api/v1/support/config'),
  })
  const sendMutation = useMutation({
    mutationFn: () => apiFetch<{ message: string }>('/api/v1/support/email', {
      method: 'POST',
      body: JSON.stringify({ reply_email: replyAddress, subject, body }),
    }),
    onSuccess: () => {
      setSent(true)
      setSubject('')
      setBody('')
    },
  })

  if (supportQuery.isLoading) return <LoadingCard />

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <PageHeader
        eyebrow="Help"
        title="Contact support"
        description="Send a note to the ChargePilot team. We’ll reply to the address you provide."
      />
      {supportQuery.error && <ErrorCard message={supportQuery.error.message} />}
      {supportQuery.data && !supportQuery.data.configured && (
        <section className="panel border-amber-200 bg-amber-50 p-5 text-sm text-amber-900" role="status">
          Support email is not available because the app’s SMTP settings are incomplete. Ask your administrator to configure mail delivery.
        </section>
      )}
      {supportQuery.data?.configured && (
        <section className="panel overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-slate-50 px-5 py-4 sm:px-7">
            <div>
              <h3 className="font-semibold text-slate-900">Send a support message</h3>
              <p className="mt-1 text-sm text-slate-600">Your message will go to {supportQuery.data.recipient}.</p>
            </div>
            <span className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-800">
              <Mail size={14} aria-hidden="true" /> Email ready
            </span>
          </div>
          <form
            className="space-y-5 p-5 sm:p-7"
            onSubmit={(event) => {
              event.preventDefault()
              setSent(false)
              sendMutation.mutate()
            }}
          >
            <label className="label" htmlFor="support-reply-email">
              Reply-to email
              <input
                id="support-reply-email"
                type="email"
                autoComplete="email"
                maxLength={254}
                required
                className="field"
                value={replyAddress}
                onChange={(event) => setReplyEmail(event.target.value)}
              />
            </label>
            <label className="label" htmlFor="support-subject">
              Subject
              <input
                id="support-subject"
                type="text"
                minLength={3}
                maxLength={160}
                required
                className="field"
                value={subject}
                onChange={(event) => setSubject(event.target.value)}
              />
            </label>
            <label className="label" htmlFor="support-message">
              How can we help?
              <textarea
                id="support-message"
                minLength={10}
                maxLength={5000}
                rows={8}
                required
                className="field min-h-40 resize-y"
                value={body}
                onChange={(event) => setBody(event.target.value)}
              />
            </label>
            <p className="text-xs leading-5 text-slate-500">
              Don’t include passwords, app passwords, or device local keys.
            </p>
            {sendMutation.error && <ErrorCard message={sendMutation.error.message} />}
            {sent && <p className="alert success" role="status">Your message has been sent to ChargePilot support.</p>}
            <button type="submit" className="btn-primary" disabled={sendMutation.isPending}>
              {sendMutation.isPending ? 'Sending message…' : 'Send support message'}
            </button>
          </form>
        </section>
      )}
    </div>
  )
}

function ChangePasswordSection() {
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [formError, setFormError] = useState('')
  const [successMessage, setSuccessMessage] = useState('')

  const mutation = useMutation({
    mutationFn: (values: { current_password: string; new_password: string }) =>
      apiFetch<{ message: string }>('/api/v1/auth/password', {
        method: 'PUT',
        body: JSON.stringify(values),
      }),
    onSuccess: ({ message }) => {
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      setFormError('')
      setSuccessMessage(message)
    },
  })

  function submitPasswordChange(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSuccessMessage('')
    setFormError('')
    if (newPassword !== confirmPassword) {
      setFormError('The new passwords do not match.')
      return
    }
    if (new TextEncoder().encode(newPassword).length > 72) {
      setFormError('The new password must be 72 UTF-8 bytes or fewer.')
      return
    }
    mutation.mutate({ current_password: currentPassword, new_password: newPassword })
  }

  return (
      <section className="panel account-password-section" aria-labelledby="password-form-title">
        <div className="account-password-heading">
          <span className="account-password-icon">
            <KeyRound size={18} aria-hidden="true" />
          </span>
          <div>
            <h2 id="password-form-title">Change password</h2>
            <p>Choose a new password for your ChargePilot account.</p>
          </div>
        </div>
        {successMessage && <p className="alert success" role="status">{successMessage}</p>}
        {(formError || mutation.error) && <p className="alert error" role="alert">{formError || mutation.error?.message}</p>}
        <form className="account-password-form" onSubmit={submitPasswordChange}>
          <label className="field-group" htmlFor="current-password">
            Current password
            <input
              id="current-password"
              type="password"
              autoComplete="current-password"
              required
              className="field"
              value={currentPassword}
              onChange={(event) => setCurrentPassword(event.target.value)}
            />
          </label>
          <label className="field-group" htmlFor="new-password">
            New password
            <input
              id="new-password"
              type="password"
              autoComplete="new-password"
              minLength={12}
              maxLength={72}
              required
              className="field"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
            />
            <span className="auth-helper">Use at least 12 characters.</span>
          </label>
          <label className="field-group" htmlFor="confirm-password">
            Confirm new password
            <input
              id="confirm-password"
              type="password"
              autoComplete="new-password"
              minLength={12}
              maxLength={72}
              required
              className="field"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
            />
          </label>
          <div className="account-password-actions">
            <button type="submit" className="btn-primary" disabled={mutation.isPending}>
              {mutation.isPending ? 'Saving password…' : 'Save new password'}
            </button>
          </div>
        </form>
      </section>
  )
}

function DashboardPage() {
  const [now, setNow] = useState(() => Date.now())
  const { data, isLoading, error, dataUpdatedAt, isFetching, refetch } = useQuery({
    queryKey: ['dashboard'],
    queryFn: fetchDashboardData,
    refetchInterval: ENDPOINTS_REFRESH_INTERVAL,
    refetchIntervalInBackground: false,
  })

  useEffect(() => {
    const interval = window.setInterval(() => setNow(Date.now()), 1_000)
    return () => window.clearInterval(interval)
  }, [])

  if (isLoading) return <LoadingCard />
  if (error && !data) return <ErrorCard message={error.message} />
  if (!data) return <ErrorCard message="The overview returned no data." />

  const { endpoints, devices } = data
  const onlineCount = endpoints.filter((endpoint) => endpoint.status === 'online').length
  const recentEndpoints = sortEndpointsByLastSeen(endpoints).slice(0, OVERVIEW_ENDPOINT_LIMIT)
  const currentMonth = new Date(now).toISOString().slice(0, 7)
  const powerDevices = devices.filter((device) => (
    device.meter_power_watts != null
    && device.meter_power_sample_at
    && now - Date.parse(device.meter_power_sample_at) <= 5 * 60 * 1000
  ))
  const monthEnergyDevices = devices.filter((device) => (
    device.meter_month_key === currentMonth
    && device.meter_energy_month_kwh != null
    && device.meter_energy_sample_at != null
  ))
  const totalPowerWatts = powerDevices.reduce((total, device) => total + (device.meter_power_watts ?? 0), 0)
  const totalEnergyKwh = monthEnergyDevices.reduce((total, device) => total + (device.meter_energy_month_kwh ?? 0), 0)

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

      <section className="energy-summary" aria-labelledby="energy-summary-title">
        <div className="energy-summary-heading">
          <div>
            <h2 id="energy-summary-title">Switch energy</h2>
            <p>Readings are shown only for switches with compatible meter datapoints.</p>
          </div>
          <NavLink to="/devices" className="secondary-btn">Configure switch meters</NavLink>
        </div>
        <div className="energy-summary-values">
          <div className="energy-summary-reading">
            <span>Live power</span>
            <strong>{powerDevices.length ? formatPower(totalPowerWatts) : 'No meter data'}</strong>
            <small>{powerDevices.length ? `From ${powerDevices.length} reporting switch${powerDevices.length === 1 ? '' : 'es'} · updated within 5 minutes` : 'Set up a power datapoint on a compatible switch.'}</small>
          </div>
          <div className="energy-summary-reading">
            <span>Energy this month (UTC)</span>
            <strong>{monthEnergyDevices.length ? `${totalEnergyKwh.toFixed(2)} kWh` : 'No meter data'}</strong>
            <small>{monthEnergyDevices.length ? `From ${monthEnergyDevices.length} switch meter${monthEnergyDevices.length === 1 ? '' : 's'} · cumulative meters start with their first reading` : 'Set up an energy datapoint on a compatible switch.'}</small>
          </div>
        </div>
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

function DeviceMeterPanel({
  device,
  isSaving,
  currentMonth,
  onSave,
}: {
  device: Device
  isSaving: boolean
  currentMonth: string
  onSave: (settings: DeviceMeterSettings) => void
}) {
  const [powerDpId, setPowerDpId] = useState(device.power_dp_id ?? '')
  const [powerMultiplier, setPowerMultiplier] = useState(String(device.power_multiplier ?? 1))
  const [energyDpId, setEnergyDpId] = useState(device.energy_dp_id ?? '')
  const [energyMultiplier, setEnergyMultiplier] = useState(String(device.energy_multiplier ?? 0.001))
  const [energyCounterType, setEnergyCounterType] = useState<DeviceMeterSettings['energy_counter_type']>(
    device.energy_counter_type ?? 'cumulative',
  )
  const [validationMessage, setValidationMessage] = useState('')
  const [candidates, setCandidates] = useState<MeterCandidate[]>([])
  const [isDiscovering, setIsDiscovering] = useState(false)
  const [discoveryMessage, setDiscoveryMessage] = useState('')
  const [discoveryError, setDiscoveryError] = useState('')

  const findReadings = async () => {
    setIsDiscovering(true)
    setDiscoveryError('')
    setDiscoveryMessage('')
    try {
      const found = await discoverMeterReadings(device.id)
      setCandidates(found)
      const suggestedPower = found.find((candidate) => candidate.suggested_role === 'power')
      const suggestedEnergy = found.find((candidate) => candidate.suggested_role === 'energy')
      if (suggestedPower) setPowerDpId(suggestedPower.id)
      if (suggestedEnergy) setEnergyDpId(suggestedEnergy.id)
      setDiscoveryMessage(
        found.length
          ? `Found ${found.length} live reading${found.length === 1 ? '' : 's'}. Review the suggested matches and save to start monitoring.`
          : 'The switch did not report any numeric readings. It may not support power or energy monitoring.',
      )
    } catch (error) {
      setDiscoveryError(error instanceof Error ? error.message : 'Could not read this switch.')
    } finally {
      setIsDiscovering(false)
    }
  }

  const saveSettings = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const powerScale = Number(powerMultiplier)
    const energyScale = Number(energyMultiplier)
    if ((powerDpId.trim() && (!Number.isFinite(powerScale) || powerScale <= 0))
      || (energyDpId.trim() && (!Number.isFinite(energyScale) || energyScale <= 0))) {
      setValidationMessage('Enter a positive multiplier for each configured datapoint.')
      return
    }
    setValidationMessage('')
    onSave({
      power_dp_id: powerDpId.trim() || null,
      power_multiplier: powerScale,
      energy_dp_id: energyDpId.trim() || null,
      energy_multiplier: energyScale,
      energy_counter_type: energyCounterType,
    })
  }

  const cumulativePartialMonth = device.energy_counter_type === 'cumulative'
    && device.meter_tracking_since
    && device.meter_tracking_since.slice(0, 7) === device.meter_month_key

  return (
    <section className="switch-meter-panel" aria-label={`Energy readings for ${device.name}`}>
      <div className="switch-meter-readings">
        <div>
          <span>Live power</span>
          <strong>{device.meter_power_watts == null ? '—' : formatPower(device.meter_power_watts)}</strong>
        </div>
        <div>
          <span>Energy this month (UTC)</span>
          <strong>{device.meter_energy_month_kwh == null || device.meter_energy_sample_at == null || device.meter_month_key !== currentMonth ? '—' : `${device.meter_energy_month_kwh.toFixed(2)} kWh`}</strong>
        </div>
      </div>
      <p className="switch-meter-status">
        {device.meter_power_sample_at || device.meter_energy_sample_at
          ? `Power sampled ${formatTimestamp(device.meter_power_sample_at ?? null)} · energy sampled ${formatTimestamp(device.meter_energy_sample_at ?? null)}${cumulativePartialMonth ? ` · cumulative tracking began ${formatTimestamp(device.meter_tracking_since ?? null)}` : ''}`
          : 'No meter sample yet. A configured, compatible datapoint and an online site connector are required.'}
      </p>
      <details className="switch-meter-settings">
        <summary>Set up power and energy readings</summary>
        <form className="switch-meter-form" onSubmit={saveSettings}>
          <p className="switch-meter-help">ChargePilot can check the switch and suggest its power and energy readings. This does not change the switch state.</p>
          <button type="button" className="btn-secondary switch-meter-discover" onClick={() => { void findReadings() }} disabled={isDiscovering || isSaving}>
            {isDiscovering ? 'Checking switch…' : 'Find readings from switch'}
          </button>
          {discoveryMessage && <p className="switch-meter-discovery-message" role="status">{discoveryMessage}</p>}
          {discoveryError && <p className="switch-meter-validation" role="alert">{discoveryError}</p>}
          {candidates.length > 0 && <>
            <div>
              <label htmlFor={`meter-power-reading-${device.id}`}>Which reading shows live power?</label>
              <select id={`meter-power-reading-${device.id}`} className="field" value={powerDpId} onChange={(event) => setPowerDpId(event.target.value)}>
                <option value="">Don’t monitor power</option>
                {powerDpId && !candidates.some((candidate) => candidate.id === powerDpId) && <option value={powerDpId}>Keep current power reading</option>}
                {candidates.map((candidate) => <option key={`power-${candidate.id}`} value={candidate.id}>{candidate.label} · {candidate.sample.toLocaleString()}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor={`meter-energy-reading-${device.id}`}>Which reading shows energy used?</label>
              <select id={`meter-energy-reading-${device.id}`} className="field" value={energyDpId} onChange={(event) => setEnergyDpId(event.target.value)}>
                <option value="">Don’t monitor energy</option>
                {energyDpId && !candidates.some((candidate) => candidate.id === energyDpId) && <option value={energyDpId}>Keep current energy reading</option>}
                {candidates.map((candidate) => <option key={`energy-${candidate.id}`} value={candidate.id}>{candidate.label} · {candidate.sample.toLocaleString()}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor={`meter-power-units-${device.id}`}>Power reading is in</label>
              <select id={`meter-power-units-${device.id}`} className="field" value={powerMultiplier === '1' ? 'watts' : powerMultiplier === '1000' ? 'kilowatts' : 'custom'} onChange={(event) => {
                if (event.target.value === 'watts') setPowerMultiplier('1')
                if (event.target.value === 'kilowatts') setPowerMultiplier('1000')
              }}>
                <option value="watts">Watts (W)</option>
                <option value="kilowatts">Kilowatts (kW)</option>
                <option value="custom">Custom scale</option>
              </select>
            </div>
            <div>
              <label htmlFor={`meter-energy-units-${device.id}`}>Energy reading is in</label>
              <select id={`meter-energy-units-${device.id}`} className="field" value={energyMultiplier === '1' ? 'kwh' : energyMultiplier === '0.001' ? 'wh' : 'custom'} onChange={(event) => {
                if (event.target.value === 'kwh') setEnergyMultiplier('1')
                if (event.target.value === 'wh') setEnergyMultiplier('0.001')
              }}>
                <option value="wh">Watt-hours (Wh)</option>
                <option value="kwh">Kilowatt-hours (kWh)</option>
                <option value="custom">Custom scale</option>
              </select>
            </div>
          </>}
          <div className="switch-meter-counter">
            <label htmlFor={`meter-energy-mode-${device.id}`}>How does the switch report energy?</label>
            <select id={`meter-energy-mode-${device.id}`} className="field" value={energyCounterType} onChange={(event) => setEnergyCounterType(event.target.value === 'monthly' ? 'monthly' : 'cumulative')}>
              <option value="cumulative">Total since the meter was installed</option>
              <option value="monthly">This month’s total</option>
            </select>
          </div>
          <p className="switch-meter-help switch-meter-disclaimer">A running total starts from the first reading this month, so the first monthly total may be partial. Readings update about once a minute.</p>
          <details className="switch-meter-advanced">
            <summary>Advanced setup</summary>
            <p className="switch-meter-help">Use these fields only when your switch documentation gives you its reading IDs or a custom unit scale.</p>
            <div className="switch-meter-form switch-meter-advanced-fields">
              <div>
                <label htmlFor={`meter-power-dp-${device.id}`}>Power reading ID</label>
                <input id={`meter-power-dp-${device.id}`} className="field" value={powerDpId} onChange={(event) => setPowerDpId(event.target.value)} />
              </div>
              <div>
                <label htmlFor={`meter-power-scale-${device.id}`}>Power scale to watts</label>
                <input id={`meter-power-scale-${device.id}`} className="field" type="number" min="0.000000001" step="any" value={powerMultiplier} onChange={(event) => setPowerMultiplier(event.target.value)} />
              </div>
              <div>
                <label htmlFor={`meter-energy-dp-${device.id}`}>Energy reading ID</label>
                <input id={`meter-energy-dp-${device.id}`} className="field" value={energyDpId} onChange={(event) => setEnergyDpId(event.target.value)} />
              </div>
              <div>
                <label htmlFor={`meter-energy-scale-${device.id}`}>Energy scale to kWh</label>
                <input id={`meter-energy-scale-${device.id}`} className="field" type="number" min="0.000000001" step="any" value={energyMultiplier} onChange={(event) => setEnergyMultiplier(event.target.value)} />
              </div>
            </div>
          </details>
          {validationMessage && <p className="switch-meter-validation" role="alert">{validationMessage}</p>}
          {!device.connector_id && <p className="switch-route-warning" role="status">The ChargePilot host will try to reach this switch directly. For cloud or remote networks, assign a site connector on the switch’s LAN.</p>}
          <button type="submit" className="btn-secondary px-3 py-2 text-xs" disabled={isSaving}>{isSaving ? 'Saving…' : 'Save meter setup'}</button>
        </form>
      </details>
    </section>
  )
}

function DevicesPage() {
  const queryClient = useQueryClient()
  const { data: user } = useSession()
  const [currentMonth, setCurrentMonth] = useState(() => new Date().toISOString().slice(0, 7))
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
    mutationFn: async ({ deviceId, channelId, desiredState }: { deviceId: string; channelId: string | null; desiredState: boolean }) => {
      const result = await apiFetch<{ status: string; command_id?: string; message?: string }>(`/api/v1/devices/${deviceId}/state`, {
        method: 'POST',
        body: JSON.stringify({ channel_id: channelId || null, desired_state: desiredState }),
      })
      if (result.command_id) await waitForConnectorCommands([{ id: result.command_id }])
      return result.message ?? `Switch turned ${desiredState ? 'on' : 'off'}.`
    },
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

function MappingsPage() {
  const queryClient = useQueryClient()
  const [step, setStep] = useState(1)
  const [editingMappingId, setEditingMappingId] = useState<string | null>(null)
  const [statusMessage, setStatusMessage] = useState('')
  const { data: mappings, isLoading: mappingsLoading } = useQuery<Mapping[]>({
    queryKey: ['mappings'],
    queryFn: () => apiFetch<Mapping[]>('/api/v1/mappings'),
  })
  const { data: endpoints = [], isLoading: endpointsLoading } = useQuery<Endpoint[]>({
    queryKey: ['endpoints'],
    queryFn: () => apiFetch<Endpoint[]>('/api/v1/endpoints'),
  })
  const { data: devices = [], isLoading: devicesLoading } = useQuery<Device[]>({
    queryKey: ['devicesForMappings'],
    queryFn: async () => {
      const listed = await apiFetch<Device[]>('/api/v1/devices')
      return Promise.all(listed.map(async (device) => ({
        ...device,
        channels: await apiFetch<DeviceChannel[]>(`/api/v1/devices/${device.id}/channels`),
      })))
    },
  })

  const form = useForm<MappingFormValues>({
    defaultValues: {
      endpoint_id: '',
      device_id: '',
      channel_id: '',
      turn_on_enabled: true,
      on_threshold: 79,
      off_threshold: 99,
      turn_off_when_charging_enabled: false,
      charging_off_threshold: 99,
      minimum_state_change_interval: 300,
      enabled: true,
    },
  })
  const selectedDeviceId = useWatch({ control: form.control, name: 'device_id' })
  const selectedEndpointId = useWatch({ control: form.control, name: 'endpoint_id' })
  const turnOnEnabled = useWatch({ control: form.control, name: 'turn_on_enabled' })
  const onThreshold = useWatch({ control: form.control, name: 'on_threshold' })
  const offThreshold = useWatch({ control: form.control, name: 'off_threshold' })
  const turnOffWhenChargingEnabled = useWatch({ control: form.control, name: 'turn_off_when_charging_enabled' })
  const chargingOffThreshold = useWatch({ control: form.control, name: 'charging_off_threshold' })
  const availableChannels = devices?.find((device) => device.id === selectedDeviceId)?.channels ?? []
  const selectedEndpoint = endpoints?.find((endpoint) => endpoint.id === selectedEndpointId)
  const selectedDevice = devices?.find((device) => device.id === selectedDeviceId)
  const matchingDevices = devices.filter((device) => (
    selectedEndpoint && selectedEndpoint.tenant_id === device.tenant_id
  ))
  const tenantsMatch = Boolean(
    selectedEndpoint && selectedDevice && selectedEndpoint.tenant_id === selectedDevice.tenant_id,
  )

  const mutation = useMutation({
    mutationFn: ({ mappingId, values }: { mappingId: string | null; values: MappingFormValues }) =>
      apiFetch<Mapping>(mappingId ? `/api/v1/mappings/${mappingId}` : '/api/v1/mappings', {
        method: mappingId ? 'PUT' : 'POST',
        body: JSON.stringify({ ...values, channel_id: values.channel_id || null }),
      }),
    onSuccess: (_, { mappingId }) => {
      queryClient.invalidateQueries({ queryKey: ['mappings'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      form.reset()
      setEditingMappingId(null)
      setStep(1)
      setStatusMessage(mappingId ? 'Mapping changes saved.' : 'Device and switch are now linked.')
    },
  })
  const deleteMutation = useMutation({
    mutationFn: (mappingId: string) => apiFetch<void>(`/api/v1/mappings/${mappingId}`, { method: 'DELETE' }),
    onSuccess: (_, mappingId) => {
      queryClient.invalidateQueries({ queryKey: ['mappings'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      if (editingMappingId === mappingId) cancelEditing()
    },
  })

  if (mappingsLoading || endpointsLoading || devicesLoading) return <LoadingCard />

  async function advanceStep() {
    const fieldsByStep = {
      1: ['endpoint_id'],
      2: ['device_id'],
    } as const
    const valid = await form.trigger(fieldsByStep[step as 1 | 2])
    if (!valid) return
    if (step === 1 && matchingDevices.length === 0) return
    setStatusMessage('')
    setStep((current) => Math.min(current + 1, 3))
  }

  function editMapping(mapping: Mapping) {
    mutation.reset()
    setStatusMessage('')
    setEditingMappingId(mapping.id)
    form.reset({
      endpoint_id: mapping.endpoint_id,
      device_id: mapping.device_id,
      channel_id: mapping.channel_id ?? '',
      turn_on_enabled: mapping.turn_on_enabled,
      on_threshold: mapping.on_threshold,
      off_threshold: mapping.off_threshold,
      turn_off_when_charging_enabled: mapping.turn_off_when_charging_enabled,
      charging_off_threshold: mapping.charging_off_threshold,
      minimum_state_change_interval: mapping.minimum_state_change_interval,
      enabled: mapping.enabled,
    })
    setStep(3)
    document.getElementById('mapping-builder-title')?.scrollIntoView({
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth',
      block: 'start',
    })
  }

  function cancelEditing() {
    mutation.reset()
    setEditingMappingId(null)
    setStatusMessage('')
    form.reset()
    setStep(1)
  }

  return (
    <div className="mapping-workspace">
      <PageHeader
        eyebrow="Automation"
        title="Device to switch mappings"
        description="Link a device to a switch, then set the battery levels that control it."
      />

      <section className="mapping-builder" aria-labelledby="mapping-builder-title">
        <div className="mapping-builder-heading">
          <div>
            <h2 id="mapping-builder-title">{editingMappingId ? 'Edit mapping' : 'Create a mapping'}</h2>
            <p>{editingMappingId ? 'Review the linked device and switch, then adjust the automation rules.' : 'Choose what should be connected, then set how the battery should control it.'}</p>
          </div>
          <span className="mapping-step-count">Step {step} of 3</span>
        </div>

        <ol className="mapping-stepper" aria-label="Mapping setup">
          {[
            { number: 1, title: 'Choose device' },
            { number: 2, title: 'Choose switch' },
            { number: 3, title: 'Set battery rules' },
          ].map((item) => (
            <li key={item.number} className={step === item.number ? 'is-current' : step > item.number ? 'is-complete' : ''}>
              <button
                type="button"
                aria-current={step === item.number ? 'step' : undefined}
                disabled={item.number > step}
                onClick={() => setStep(item.number)}
              >
                <span className="mapping-step-number">{step > item.number ? <CheckCircle2 size={17} /> : item.number}</span>
                <span className="mapping-step-title">{item.title}</span>
              </button>
            </li>
          ))}
        </ol>

        <div className="mapping-wizard-content">
          {step === 1 && <div className="mapping-step-content">
            <div className="mapping-step-copy">
              <span className="mapping-step-kicker">01 / Device</span>
              <h3>Which device should this switch follow?</h3>
              <p>Only devices in the same workspace can be linked to a switch.</p>
            </div>
            {!endpoints.length ? (
              <div className="mapping-empty-inline">
                <MonitorSmartphone size={22} />
                <div><strong>No devices reporting yet</strong><p>Enroll a device and send its first reading before creating a mapping.</p></div>
                <NavLink to="/endpoints" className="btn-secondary">View devices</NavLink>
              </div>
            ) : <div className="mapping-choice-grid">
              {endpoints.map((endpoint) => (
                <button
                  key={endpoint.id}
                  type="button"
                  className={`mapping-choice-card ${selectedEndpointId === endpoint.id ? 'is-selected' : ''}`}
                  aria-pressed={selectedEndpointId === endpoint.id}
                  onClick={() => {
                    form.setValue('endpoint_id', endpoint.id, { shouldValidate: true })
                    form.clearErrors('endpoint_id')
                    if (selectedDevice && selectedDevice.tenant_id !== endpoint.tenant_id) {
                      form.setValue('device_id', '')
                      form.setValue('channel_id', '')
                    }
                  }}
                >
                  <span className={`mapping-choice-status ${endpoint.status === 'online' ? 'is-online' : ''}`} />
                  <MonitorSmartphone size={19} aria-hidden="true" />
                  <span className="mapping-choice-copy"><strong>{endpoint.display_name || endpoint.hostname}</strong><small>{endpoint.tenant_name ?? 'Unassigned tenant'}{endpoint.ip_address ? ` · ${endpoint.ip_address}` : ''}</small></span>
                  <span className={`mapping-choice-battery ${endpoint.battery <= 25 ? 'is-low' : ''}`}>{endpoint.battery}%</span>
                </button>
              ))}
            </div>}
            {form.formState.errors.endpoint_id && <FieldError>Select a device to continue.</FieldError>}
            {selectedEndpoint && matchingDevices.length === 0 && (
              <div className="mapping-guidance" role="status">
                <span>No switches are assigned to <strong>{selectedEndpoint.tenant_name ?? 'this tenant'}</strong> yet.</span>
                <NavLink to="/devices">Set up a switch</NavLink>
              </div>
            )}
          </div>}

          {step === 2 && <div className="mapping-step-content">
            <div className="mapping-step-copy">
              <span className="mapping-step-kicker">02 / Switch</span>
              <h3>Choose the switch and output</h3>
              <p>{selectedEndpoint ? `Available switches for ${selectedEndpoint.hostname}.` : 'Return to step 1 and choose a device first.'}</p>
            </div>
            {!matchingDevices.length ? (
              <div className="mapping-empty-inline">
                <PlugZap size={22} />
                <div><strong>No matching switch is ready</strong><p>Add a switch to the same workspace as the selected device.</p></div>
                <NavLink to="/devices" className="btn-secondary">Set up a switch</NavLink>
              </div>
            ) : <div className="mapping-switch-options">
              {matchingDevices.map((device) => (
                <button
                  key={device.id}
                  type="button"
                  className={`mapping-switch-option ${selectedDeviceId === device.id ? 'is-selected' : ''}`}
                  aria-pressed={selectedDeviceId === device.id}
                  onClick={() => {
                    form.setValue('device_id', device.id, { shouldValidate: true })
                    form.setValue('channel_id', '')
                    form.clearErrors('device_id')
                  }}
                >
                  <span className={`switch-state-light ${device.current_state ? 'is-on' : ''}`} aria-hidden="true" />
                  <PlugZap size={19} aria-hidden="true" />
                  <span className="mapping-choice-copy"><strong>{device.name}</strong><small>{device.tenant_name ?? 'Unassigned tenant'}{device.ip_address ? ` · ${device.ip_address}` : ''}</small></span>
                  <span className="mapping-switch-state">{device.current_state ? 'On' : 'Off'}</span>
                </button>
              ))}
            </div>}
            {selectedDevice && <div className="mapping-channel-picker">
              <label className="label" htmlFor="mapping-channel">Switch output</label>
              <select id="mapping-channel" className="field" {...form.register('channel_id')}>
                <option value="">Whole switch</option>
                {availableChannels.map((channel) => <option key={channel.id} value={channel.id}>{channel.name}</option>)}
              </select>
              <p>Choose an individual output for multi-channel switches.</p>
            </div>}
            {form.formState.errors.device_id && <FieldError>Select a switch to continue.</FieldError>}
          </div>}

          {step === 3 && <div className="mapping-step-content">
            <div className="mapping-step-copy">
              <span className="mapping-step-kicker">03 / Battery rules</span>
              <h3>{editingMappingId ? 'Review and adjust the battery rules' : 'Set when the switch should change'}</h3>
              <p>These values are only applied when you save. Separate thresholds prevent rapid toggling around one battery level.</p>
            </div>
            <div className="mapping-rule-layout">
              <div className="mapping-rule-fields">
                <label className="mapping-enable-control" htmlFor="mapping-turn-on-enabled">
                  <input id="mapping-turn-on-enabled" type="checkbox" {...form.register('turn_on_enabled')} />
                  <span><strong>Enable automatic turn-on</strong><small>Turn the switch on when battery reaches the selected low threshold.</small></span>
                </label>
                <label className="mapping-rule-field" htmlFor="on-threshold"><span>Turn on at or below</span><span className="mapping-number-input"><input id="on-threshold" type="number" min={0} max={100} required={turnOnEnabled} disabled={!turnOnEnabled} {...form.register('on_threshold', { valueAsNumber: true, required: turnOnEnabled, min: 0, max: 100 })} /><b>%</b></span></label>
                <label className="mapping-enable-control" htmlFor="mapping-charging-off-enabled">
                  <input id="mapping-charging-off-enabled" type="checkbox" {...form.register('turn_off_when_charging_enabled')} />
                  <span><strong>Turn off at charge completion</strong><small>When the device is charging, turn the switch off at its separate battery threshold.</small></span>
                </label>
                <label className="mapping-rule-field" htmlFor="charging-off-threshold"><span>Turn off while charging at or above</span><span className="mapping-number-input"><input id="charging-off-threshold" type="number" min={0} max={100} required={turnOffWhenChargingEnabled} disabled={!turnOffWhenChargingEnabled} {...form.register('charging_off_threshold', { valueAsNumber: true, required: turnOffWhenChargingEnabled, min: 0, max: 100 })} /><b>%</b></span></label>
                <label className="mapping-rule-field" htmlFor="off-threshold"><span>Turn off at or above</span><span className="mapping-number-input"><input id="off-threshold" type="number" min={0} max={100} required {...form.register('off_threshold', { valueAsNumber: true, required: true, min: 0, max: 100 })} /><b>%</b></span></label>
                <label className="mapping-rule-field" htmlFor="mapping-interval"><span>Minimum time between changes</span><span className="mapping-number-input"><input id="mapping-interval" type="number" min={0} required {...form.register('minimum_state_change_interval', { valueAsNumber: true, required: true, min: 0 })} /><b>sec</b></span></label>
                <label className="mapping-enable-control" htmlFor="mapping-enabled">
                  <input id="mapping-enabled" type="checkbox" {...form.register('enabled')} />
                  <span><strong>Enable automation now</strong><small>This device will control the switch as soon as the mapping is saved.</small></span>
                </label>
              </div>
              <div className="mapping-rule-preview" aria-label={`Battery automation preview: ${turnOnEnabled ? `turn on at or below ${onThreshold} percent` : 'automatic turn-on disabled'}, turn off at or above ${offThreshold} percent${turnOffWhenChargingEnabled ? ` or while charging at or above ${chargingOffThreshold} percent` : ''}`}>
                <div className="mapping-preview-heading"><BatteryCharging size={18} /><strong>Battery response</strong></div>
                <div className="mapping-battery-track">
                  <span className="mapping-battery-fill" />
                  {turnOnEnabled && <span className="mapping-threshold-marker is-on" style={{ left: `${onThreshold}%` }} aria-hidden="true" />}
                  <span className="mapping-threshold-marker is-off" style={{ left: `${offThreshold}%` }} aria-hidden="true" />
                  {turnOffWhenChargingEnabled && <span className="mapping-threshold-marker is-charging" style={{ left: `${chargingOffThreshold}%` }} aria-hidden="true" />}
                </div>
                <div className="mapping-preview-scale"><span>0%</span><span>100%</span></div>
                <div className="mapping-threshold-legend" role="group" aria-label="Automation thresholds">
                  {turnOnEnabled && <span className="is-on"><i />Turn on at or below {onThreshold}%</span>}
                  <span className="is-off"><i />Turn off at or above {offThreshold}%</span>
                  {turnOffWhenChargingEnabled && <span className="is-charging"><i />Charging cutoff at or above {chargingOffThreshold}%</span>}
                </div>
                <p>{turnOnEnabled ? `On when battery falls to ${onThreshold}% or below. ` : 'Automatic turn-on is disabled. '}{turnOffWhenChargingEnabled ? `Off at ${chargingOffThreshold}% or above while charging. ` : ''}Off at {offThreshold}% or above.</p>
                {turnOnEnabled && offThreshold <= onThreshold && <span className="mapping-threshold-error" role="alert">The turn-off threshold must be higher than the turn-on threshold.</span>}
              </div>
            </div>
            <div className="mapping-review-route">
              <span className="mapping-review-endpoint"><MonitorSmartphone size={16} />{selectedEndpoint?.hostname ?? 'No device selected'}</span>
              <ChevronRight size={17} aria-hidden="true" />
              <span className="mapping-review-device"><PlugZap size={16} />{selectedDevice?.name ?? 'Switch not selected'}{form.getValues('channel_id') ? ` · ${availableChannels.find((channel) => channel.id === form.getValues('channel_id'))?.name ?? 'Channel'}` : ''}</span>
            </div>
          </div>}

          {mutation.isError && <ErrorCard message={mutation.error.message} />}
          {statusMessage && <p className="mapping-success-message" role="status"><CheckCircle2 size={17} />{statusMessage}</p>}
          <div className="mapping-wizard-footer">
            <div className="mapping-footer-navigation">
              {step > 1 ? <button type="button" className="btn-secondary" onClick={() => setStep((current) => current - 1)}><ChevronLeft size={16} />Back</button> : <span />}
              {editingMappingId && <button type="button" className="mapping-cancel-edit" onClick={cancelEditing}>Cancel edit</button>}
            </div>
            {step < 3 ? (
              <button type="button" className="btn-primary" onClick={() => void advanceStep()} disabled={(step === 1 && !selectedEndpointId) || (step === 2 && !tenantsMatch)}>
                Continue <ChevronRight size={16} />
              </button>
            ) : (
              <button
                type="button"
                className="btn-primary"
                disabled={mutation.isPending || !tenantsMatch || (turnOnEnabled && offThreshold <= onThreshold)}
                onClick={() => void form.handleSubmit((values) => mutation.mutate({ mappingId: editingMappingId, values }))()}
              >
                {mutation.isPending ? 'Saving…' : editingMappingId ? 'Save changes' : 'Create mapping'}
              </button>
            )}
          </div>
        </div>
      </section>

      {deleteMutation.isError && <ErrorCard message={deleteMutation.error.message} />}
      <section className="mapping-list-panel" aria-labelledby="mapping-list-title">
        <div className="mapping-list-heading">
          <div><h2 id="mapping-list-title">Current mappings</h2><p>Battery rules connecting devices to switches.</p></div>
          <span className="mapping-total">{mappings?.length ?? 0}<small>configured</small></span>
        </div>
        <div className="mapping-list">
          {mappings?.map((mapping) => {
            const endpoint = endpoints?.find((item) => item.id === mapping.endpoint_id)
            const device = devices?.find((item) => item.id === mapping.device_id)
            const channel = device?.channels?.find((item) => item.id === mapping.channel_id)
            return <article key={mapping.id} className="mapping-card">
              <div className="mapping-card-main">
                <div className="mapping-route">
                  <div className="mapping-entity">
                    <span className="mapping-entity-icon endpoint-icon"><MonitorSmartphone size={18} aria-hidden="true" /></span>
                    <div className="min-w-0"><span className="mapping-overline">Device</span><h3 className="mapping-entity-name">{endpoint?.hostname ?? 'Unknown device'}</h3><small>{endpoint?.tenant_name ?? 'Unassigned workspace'}</small></div>
                  </div>
                  <ChevronRight className="mapping-route-arrow" size={19} aria-hidden="true" />
                  <div className="mapping-entity">
                    <span className="mapping-entity-icon switch-icon"><PlugZap size={18} aria-hidden="true" /></span>
                    <div className="min-w-0"><span className="mapping-overline">Switch</span><h3 className="mapping-entity-name">{device?.name ?? 'Unknown switch'}</h3><small>{channel?.name ?? 'Whole switch'}</small></div>
                  </div>
                </div>
                <div className="mapping-rules">
                  <div className="mapping-rule-summary"><span>Turn on</span><strong>{mapping.turn_on_enabled ? `${mapping.on_threshold}%` : 'Off'}</strong><small>{mapping.turn_on_enabled ? 'or below' : 'automatic'}</small></div>
                  <div className="mapping-rule-summary"><span>Turn off</span><strong>{mapping.off_threshold}%</strong><small>or above</small></div>
                  {mapping.turn_off_when_charging_enabled && <div className="mapping-rule-summary"><span>Charging cutoff</span><strong>{mapping.charging_off_threshold}%</strong><small>or above while charging</small></div>}
                  <div className="mapping-rule-summary"><span>Cooldown</span><strong>{mapping.minimum_state_change_interval}s</strong><small>between changes</small></div>
                  <span className={`mapping-enabled-state ${mapping.enabled ? 'is-enabled' : ''}`}>{mapping.enabled ? 'Automation on' : 'Paused'}</span>
                  <span className="mapping-tenant-label">{mapping.tenant_name ?? 'Unassigned tenant'}</span>
                </div>
                <details className="mapping-id"><summary>Mapping details</summary><code>{mapping.id}</code></details>
              </div>
              <div className="mapping-card-actions">
                <button type="button" className="mapping-edit-button" onClick={() => editMapping(mapping)}><Pencil size={14} aria-hidden="true" />Edit</button>
                <button type="button" className="mapping-delete-button" disabled={deleteMutation.isPending} onClick={() => {
                  if (window.confirm('Delete this battery mapping?')) deleteMutation.mutate(mapping.id)
                }}>Delete</button>
              </div>
            </article>
          })}
          {!mappings?.length && <div className="mapping-empty-state"><Cable size={22} aria-hidden="true" /><h3>No mappings yet</h3><p>Use the three steps above to connect a device with a switch.</p></div>}
        </div>
      </section>
    </div>
  )
}

function EndpointsPage() {
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

function trapDialogFocus(event: ReactKeyboardEvent<HTMLElement>) {
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

function EndpointDetailsPanel({
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
  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [onClose])

  const latestReading = details?.readings.at(-1)
  const metrics = latestReading?.system_metrics
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
          {details.mappings.map((mapping) => <li key={mapping.id} className="flex items-center justify-between gap-3 rounded-lg border border-[var(--line)] px-3 py-3">
            <div><p className="font-medium text-[var(--ink)]">{mapping.name}</p><p className="mt-1 text-xs text-[var(--muted)]">{mapping.enabled ? 'Mapping active' : 'Mapping paused'} · Switch {mapping.switch_state ? 'on' : 'off'}</p></div>
            <span className="shrink-0 text-right text-xs text-[var(--muted)]">On ≤ {mapping.on_threshold}%<br />Off ≥ {mapping.off_threshold}%</span>
          </li>)}
        </ul> : <p className="text-sm text-[var(--muted)]">No switch mappings are assigned to this device.</p>}
      </section>

      <section aria-labelledby="report-history-title">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <h3 id="report-history-title" className="font-semibold text-[var(--ink)]">Recent reports</h3>
          <span className="text-xs text-[var(--muted)]">Up to 100 reports · retained for 30 days</span>
        </div>
        {details.readings.length ? <div className="max-h-72 overflow-auto rounded-lg border border-[var(--line)]">
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

function DeviceMetricCard({
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
            <thead><tr><th>Time</th><th>Type</th><th>Device</th><th>Battery</th><th>Activity</th><th>Result</th></tr></thead>
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

function ConnectorsPage() {
  const queryClient = useQueryClient()
  const { data: user } = useSession()
  const [deploymentMethod, setDeploymentMethod] = useState<'docker' | 'python'>('docker')
  const [name, setName] = useState('')
  const [tenantId, setTenantId] = useState('')
  const [enrollmentCode, setEnrollmentCode] = useState('')
  const [copyStatus, setCopyStatus] = useState('')

  const connectorsQuery = useQuery({
    queryKey: ['connectors'],
    queryFn: () => apiFetch<Connector[]>('/api/v1/connectors'),
  })
  const tenantsQuery = useQuery({
    queryKey: ['admin-tenants'],
    queryFn: () => apiFetch<TenantInfo[]>('/api/v1/admin/tenants'),
    enabled: user?.role === 'super_admin',
  })
  const createMutation = useMutation({
    mutationFn: () => apiFetch<{ enrollment_code: string }>('/api/v1/connectors/enrollment-codes', {
      method: 'POST',
      body: JSON.stringify({ name, tenant_id: tenantId || undefined }),
    }),
    onSuccess: ({ enrollment_code }) => {
      setEnrollmentCode(enrollment_code)
      setName('')
      setTenantId('')
      queryClient.invalidateQueries({ queryKey: ['connectors'] })
    },
  })
  const revokeMutation = useMutation({
    mutationFn: (connectorId: string) => apiFetch<{ status: string }>(`/api/v1/connectors/${connectorId}/revoke`, { method: 'POST' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['connectors'] }),
  })
  const deleteMutation = useMutation({
    mutationFn: (connectorId: string) => apiFetch<void>(`/api/v1/connectors/${connectorId}`, { method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['connectors'] }),
  })

  if (connectorsQuery.isLoading || tenantsQuery.isLoading) return <LoadingCard />
  if (connectorsQuery.error) return <ErrorCard message={connectorsQuery.error.message} />
  if (tenantsQuery.error) return <ErrorCard message={tenantsQuery.error.message} />
  const connectors = connectorsQuery.data ?? []
  const tenants = tenantsQuery.data ?? []
  const actionError = createMutation.error ?? revokeMutation.error ?? deleteMutation.error
  const canManageConnectors = user?.role === 'super_admin' || user?.role === 'tenant_admin' || user?.role === 'manager'
  const connectorServerUrl = (API_BASE_URL || window.location.origin).replace(/\/+$/, '')
  const pythonInstallCommand = `curl -fsSL ${connectorServerUrl}/connectors/install.sh | sh`
  const composeYaml = `services:
  chargepilot-connector:
    image: endusercompute/chargepilot-connector:sha-922f4aac9cef35276eef7814620f38d674720f73
    container_name: chargepilot-connector
    network_mode: host
    restart: unless-stopped
    read_only: true
    tmpfs:
      - /tmp:rw,noexec,nosuid,size=16m
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
    environment:
      CHARGEPILOT_CONNECTOR_SERVER_URL: ${connectorServerUrl}
      CHARGEPILOT_CONNECTOR_ENROLLMENT_CODE: \${CHARGEPILOT_CONNECTOR_ENROLLMENT_CODE:-}
      CHARGEPILOT_CONNECTOR_CONFIG: /data/connector-config.json
    volumes:
      - connector-data:/data

volumes:
  connector-data:`

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Remote device networks" title="Site connectors" description="Connect a computer on the same local network as your Tuya switches. It securely polls ChargePilot over HTTPS and performs discovery and control on site." />
      {actionError && <ErrorCard message={actionError.message} />}
      <section className="connector-deploy-guide" aria-labelledby="connector-deploy-title">
        <div className="connector-deploy-heading">
          <div>
            <h2 id="connector-deploy-title">Choose how to run your site connector</h2>
            <p>One small service on the switch's LAN keeps discovery and control local.</p>
          </div>
          <div className="connector-network-path" aria-label="Connector network path">
            <span>Tuya LAN</span><ChevronRight size={15} aria-hidden="true" /><span>Connector</span><ChevronRight size={15} aria-hidden="true" /><span>HTTPS</span>
          </div>
        </div>
        <p className="connector-prerequisite"><ShieldCheck size={16} aria-hidden="true" /><span>Use an always-on computer on the same network as your switches. It needs outbound HTTPS and local Tuya traffic; no inbound Internet port is required.</span></p>
        <div className="connector-method-options" role="group" aria-label="Connector deployment method">
          <button type="button" className={`connector-method-option ${deploymentMethod === 'docker' ? 'is-selected' : ''}`} aria-pressed={deploymentMethod === 'docker'} onClick={() => setDeploymentMethod('docker')}>
            <span className="connector-method-name">Docker Compose</span><span>Linux server, NAS, or Raspberry Pi</span>
          </button>
          <button type="button" className={`connector-method-option ${deploymentMethod === 'python' ? 'is-selected' : ''}`} aria-pressed={deploymentMethod === 'python'} onClick={() => setDeploymentMethod('python')}>
            <span className="connector-method-name">Python process</span><span>Linux or macOS terminal</span>
          </button>
        </div>
        <div className="connector-deploy-steps" aria-live="polite">
          <article className="connector-deploy-step">
            <span className="connector-step-number">1</span>
            <div><h3>Prepare the connector host</h3><p>Use an always-on computer on the switch LAN. Python installs directly from ChargePilot; Docker pulls the published image.</p><a href={backendUrl('/connectors/download')} className="connector-download-link">Download source package (optional)</a></div>
          </article>
          <article className="connector-deploy-step">
            <span className="connector-step-number">2</span>
            <div><h3>Create its one-time code</h3><p>Name this network and generate a code below. It expires after 15 minutes and can be used once.</p>{canManageConnectors && <a href="#connector-enrollment-form" className="connector-step-link">Create enrollment code</a>}</div>
          </article>
          <article className="connector-deploy-step">
            <span className="connector-step-number">3</span>
            <div>
              <h3>{deploymentMethod === 'docker' ? 'Start the published Docker image' : 'Install and start Python'}</h3>
              {deploymentMethod === 'docker' ? <>
                <p>Save this as <code>docker-compose.yml</code>. It uses the published image and this ChargePilot API URL, and Docker creates persistent storage automatically.</p>
                <pre className="connector-command"><code>{composeYaml}</code></pre>
                <button type="button" className="btn-secondary mt-2" onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(composeYaml)
                    setCopyStatus('Compose YAML copied.')
                  } catch {
                    setCopyStatus('Copy was blocked. Select the YAML and copy it manually.')
                  }
                }}>Copy Compose YAML</button>
                <p className="mt-1 text-xs text-slate-500" role="status">{copyStatus}</p>
                <p className="connector-step-note">Run this in Bash beside the Compose file: <code>read -rsp 'One-time ChargePilot code: ' CHARGEPILOT_CONNECTOR_ENROLLMENT_CODE &amp;&amp; echo &amp;&amp; export CHARGEPILOT_CONNECTOR_ENROLLMENT_CODE &amp;&amp; docker compose up -d &amp;&amp; unset CHARGEPILOT_CONNECTOR_ENROLLMENT_CODE</code>. The code is not added to shell history, but remains visible in Docker metadata until enrollment completes and the container is recreated without it. The saved credential remains in the Docker-managed volume. Allow local Tuya traffic (UDP 6666, 6667, 7000; TCP 6668).</p>
              </> : <>
                <p>On Linux or macOS, install Python 3.12+, <code>curl</code>, and <code>unzip</code>. Run this command on the switch LAN and enter only the one-time enrollment code when prompted. Windows users can download the source package for manual Python setup.</p>
                <pre className="connector-command"><code>{pythonInstallCommand}</code></pre>
                <button type="button" className="btn-secondary mt-2" onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(pythonInstallCommand)
                    setCopyStatus('Python install command copied.')
                  } catch {
                    setCopyStatus('Copy was blocked. Select the command and copy it manually.')
                  }
                }}>Copy install command</button>
                <p className="mt-1 text-xs text-slate-500" role="status">{copyStatus}</p>
                <p className="connector-step-note">This runs the installer provided by your ChargePilot server; use it only if you trust that server. It stores the credential in your user configuration directory. Allow local Tuya traffic (UDP 6666, 6667, 7000; TCP 6668). Keep the process running or configure your OS service manager.</p>
              </>}
            </div>
          </article>
        </div>
        <p className="connector-finish-note">When it reports online here, use the Switches page to scan this LAN and assign discovered switches to the connector.</p>
      </section>
      {enrollmentCode && (
        <section className="rounded-2xl border border-amber-300 bg-amber-50 p-5" aria-labelledby="enrollment-code-title">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div><h2 id="enrollment-code-title" className="text-lg font-bold text-amber-950">One-time enrollment code</h2><p className="mt-1 text-sm text-amber-900">Use it on the connector computer within 15 minutes. It is shown only once; do not share or commit it.</p></div>
            <button type="button" className="btn-secondary" onClick={async () => {
              try {
                await navigator.clipboard.writeText(enrollmentCode)
                setCopyStatus('Enrollment code copied.')
              } catch {
                setCopyStatus('Copy was blocked. Select the code and copy it manually.')
              }
            }}>Copy code</button>
          </div>
          <output className="mt-4 block select-all break-all rounded-lg border border-amber-200 bg-white px-4 py-4 font-mono text-lg font-semibold tracking-wider text-slate-900">{enrollmentCode}</output>
          <p className="mt-2 min-h-4 text-xs text-amber-900" role="status">{copyStatus}</p>
        </section>
      )}
      <div className="grid gap-5 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
        {canManageConnectors && <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-bold text-slate-900" id="connector-enrollment-form">Create enrollment code</h2>
          <p className="mt-1 text-sm text-slate-600">Choose a name that identifies the physical switch network.</p>
          <form className="mt-4 space-y-3" onSubmit={(event) => { event.preventDefault(); createMutation.mutate() }}>
            <label className="label" htmlFor="connector-name">Name<input id="connector-name" required maxLength={160} className="field" value={name} onChange={(event) => setName(event.target.value)} placeholder="Main office LAN" /></label>
            {user?.role === 'super_admin' && <label className="label" htmlFor="connector-tenant">Tenant<select id="connector-tenant" required className="field" value={tenantId} onChange={(event) => setTenantId(event.target.value)}><option value="">Select a tenant</option>{tenants.map((tenant) => <option key={tenant.id} value={tenant.id}>{tenant.name}</option>)}</select></label>}
            <button type="submit" className="btn-primary" disabled={createMutation.isPending}>{createMutation.isPending ? 'Creating code…' : 'Create one-time code'}</button>
          </form>
        </section>}
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-baseline justify-between gap-3"><h2 className="text-lg font-bold text-slate-900">Connectors</h2><span className="text-sm text-slate-500">{connectors.length}</span></div>
          <div className="mt-4 divide-y divide-slate-100">
            {connectors.map((connector) => {
              const status = !connector.is_active ? 'Revoked' : !connector.is_enrolled ? 'Awaiting enrollment' : connector.is_online ? 'Online' : 'Offline'
              const statusColor = !connector.is_active ? 'text-red-700' : connector.is_online ? 'text-emerald-700' : 'text-amber-700'
              return <article key={connector.id} className="flex flex-col gap-3 py-4 first:pt-0 sm:flex-row sm:items-center sm:justify-between">
                <div><h3 className="font-semibold text-slate-900">{connector.name}</h3><p className="mt-1 text-sm"><span className={statusColor}>{status}</span><span className="text-slate-500"> · Last contact {formatTimestamp(connector.last_seen_at ?? null)}</span></p></div>
                {canManageConnectors && (connector.is_active
                  ? <button type="button" className="btn-secondary border-red-200 text-red-700 hover:bg-red-50" disabled={revokeMutation.isPending} onClick={() => { if (window.confirm('Revoke this connector and unassign its switches?')) revokeMutation.mutate(connector.id) }}>Revoke</button>
                  : <button type="button" className="btn-secondary border-red-200 text-red-700 hover:bg-red-50" disabled={deleteMutation.isPending} onClick={() => { if (window.confirm('Permanently delete this revoked connector and its command history?')) deleteMutation.mutate(connector.id) }}>Delete</button>)}
              </article>
            })}
            {!connectors.length && <p className="py-6 text-sm text-slate-500">No connectors yet. Add one for a remote switch network.</p>}
          </div>
        </section>
      </div>
    </div>
  )
}

function ProfilePage() {
  const queryClient = useQueryClient()
  const { data: user, isLoading, error } = useSession()
  const [timezone, setTimezone] = useState('')
  const [statusMessage, setStatusMessage] = useState('')
  const mutation = useMutation({
    mutationFn: () => apiFetch<{ message: string }>('/api/v1/auth/profile', {
      method: 'PUT',
      body: JSON.stringify({ timezone: timezone || user?.timezone || 'UTC' }),
    }),
    onSuccess: ({ message }) => {
      setStatusMessage(message)
      queryClient.invalidateQueries({ queryKey: ['session'] })
    },
  })
  if (isLoading) return <LoadingCard />
  if (error || !user) return <ErrorCard message={error?.message ?? 'Your account could not be loaded.'} />
  const currentTimezone = timezone || user.timezone || 'UTC'
  return <div className="account-page">
    <PageHeader eyebrow="Your settings" title="Account" description="Manage your profile and sign-in preferences." />
    <section className="account-summary" aria-label="Account details">
      <div><span>Username</span><strong>{user.username}</strong></div>
      <div><span>Email</span><strong>{user.email ?? 'Not set'}</strong></div>
      <div><span>Role</span><strong>{user.role.replaceAll('_', ' ')}</strong></div>
      <div><span>Workspace</span><strong>{user.tenant_name ?? 'System'}</strong></div>
    </section>
    <section className="profile-preference panel account-timezone-section">
      <div>
        <h2>Time zone</h2>
        <p>Choose how dates and times are shown across ChargePilot.</p>
      </div>
      {statusMessage && <p className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800" role="status">{statusMessage}</p>}
      {mutation.error && <div className="mt-4"><ErrorCard message={mutation.error.message} /></div>}
      <form className="profile-preference-form" onSubmit={(event) => { event.preventDefault(); setStatusMessage(''); mutation.mutate() }}>
        <label className="profile-timezone-label" htmlFor="profile-timezone">Your time zone</label>
        <select
          id="profile-timezone"
          className="field"
          aria-label="Time zone"
          value={currentTimezone}
          onChange={(event) => setTimezone(event.target.value)}
          required
        >
          <option value="UTC">UTC — Coordinated Universal Time</option>
          {currentTimezone !== 'UTC' && !TIME_ZONE_OPTIONS.includes(currentTimezone) && (
            <option value={currentTimezone}>{currentTimezone.replaceAll('_', ' ')}</option>
          )}
          {TIME_ZONE_REGIONS.map((region) => {
            const regionZones = TIME_ZONE_OPTIONS.filter((zone) => zone.startsWith(`${region}/`))
            if (!regionZones.length) return null
            return <optgroup key={region} label={region}>
              {regionZones.map((zone) => <option key={zone} value={zone}>{zone.replaceAll('_', ' ')}</option>)}
            </optgroup>
          })}
        </select>
        <button type="submit" className="btn-primary" disabled={mutation.isPending}>{mutation.isPending ? 'Saving…' : 'Save time zone'}</button>
      </form>
    </section>
    <ChangePasswordSection />
  </div>
}

function UsersPage() {
  const queryClient = useQueryClient()
  const { data: currentUser, isLoading: sessionLoading } = useSession()
  const usersQuery = useQuery({ queryKey: ['admin-users'], queryFn: () => apiFetch<AdminUser[]>('/api/v1/admin/users') })
  const tenantsQuery = useQuery({ queryKey: ['admin-tenants'], queryFn: () => apiFetch<TenantInfo[]>('/api/v1/admin/tenants'), enabled: currentUser?.role === 'super_admin' })
  const invitationsQuery = useQuery({ queryKey: ['account-invitations'], queryFn: () => apiFetch<AccountInvitationInfo[]>('/api/v1/admin/account-invitations') })
  const [statusMessage, setStatusMessage] = useState('')
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteUsername, setInviteUsername] = useState('')
  const [inviteRole, setInviteRole] = useState('tenant_admin')
  const [inviteTenantId, setInviteTenantId] = useState('')
  const actionMutation = useMutation({
    mutationFn: async ({ method, path, body }: { method: 'PATCH' | 'DELETE'; path: string; body?: Record<string, unknown> }) =>
      apiFetch<{ message?: string } | undefined>(path, {
        method,
        ...(body ? { body: JSON.stringify(body) } : {}),
      }),
    onSuccess: (_, variables) => {
      setStatusMessage(variables.method === 'DELETE' ? 'Account removed.' : 'Access updated.')
      queryClient.invalidateQueries({ queryKey: ['admin-users'] })
    },
  })
  const inviteMutation = useMutation({
    mutationFn: (body: { email: string; username: string; role: string; tenant_id?: string }) => apiFetch<AccountInvitationInfo>('/api/v1/admin/account-invitations', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
    onSuccess: (invitation) => {
      setStatusMessage(`Invitation sent to ${invitation.email}.`)
      setInviteEmail('')
      setInviteUsername('')
      queryClient.invalidateQueries({ queryKey: ['account-invitations'] })
    },
  })
  const revokeInviteMutation = useMutation({
    mutationFn: (invitationId: string) => apiFetch<void>(`/api/v1/admin/account-invitations/${invitationId}`, { method: 'DELETE' }),
    onSuccess: () => {
      setStatusMessage('Invitation revoked.')
      queryClient.invalidateQueries({ queryKey: ['account-invitations'] })
    },
  })
  const isSuperAdmin = currentUser?.role === 'super_admin'
  if (sessionLoading || usersQuery.isLoading || tenantsQuery.isLoading || invitationsQuery.isLoading) return <LoadingCard />
  if (usersQuery.error) return <ErrorCard message={usersQuery.error.message} />
  if (tenantsQuery.error) return <ErrorCard message={tenantsQuery.error.message} />
  if (invitationsQuery.error) return <ErrorCard message={invitationsQuery.error.message} />
  const tenants = tenantsQuery.data ?? []
  const roles = ['tenant_admin', 'manager', 'standard_user', 'viewer']
  const submitRoleChange = (event: FormEvent<HTMLFormElement>, account: AdminUser) => {
    event.preventDefault()
    const body = Object.fromEntries(new FormData(event.currentTarget).entries())
    actionMutation.mutate({ path: `/api/v1/admin/users/${account.id}`, method: 'PATCH', body })
  }
  const invitations = invitationsQuery.data ?? []
  const statusOf = (invitation: AccountInvitationInfo) => invitation.used_at
    ? 'Accepted'
    : invitation.revoked_at
      ? 'Revoked'
      : invitation.is_active
        ? 'Waiting for response'
        : 'Expired'
  const submitInvitation = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setStatusMessage('')
    inviteMutation.mutate({
      email: inviteEmail,
      username: inviteUsername,
      role: inviteRole,
      ...(isSuperAdmin ? { tenant_id: inviteTenantId } : {}),
    })
  }
  return (
    <div className="people-page">
      <PageHeader eyebrow="Administration" title="People & invites" description="Invite teammates, manage access, and keep track of who belongs to this workspace." />
      {statusMessage && <p className="alert success" role="status">{statusMessage}</p>}
      {(actionMutation.error || inviteMutation.error || revokeInviteMutation.error) && (
        <ErrorCard message={actionMutation.error?.message ?? inviteMutation.error?.message ?? revokeInviteMutation.error?.message ?? 'The request failed.'} />
      )}

      <section className="panel people-invite-section" aria-labelledby="invite-heading">
        <div className="people-section-heading">
          <div>
            <h2 id="invite-heading">Invite someone</h2>
            <p>We’ll email a private setup link and one-time code. They choose their password before signing in.</p>
          </div>
          <span className="people-heading-icon"><Mail size={19} aria-hidden="true" /></span>
        </div>
        <form className="people-invite-form" onSubmit={submitInvitation}>
          <label className="field-group" htmlFor="invite-username">
            Username
            <input
              id="invite-username"
              autoComplete="off"
              minLength={3}
              maxLength={80}
              required
              className="field"
              value={inviteUsername}
              onChange={(event) => setInviteUsername(event.target.value)}
            />
          </label>
          <label className="field-group" htmlFor="invite-email">
            Email address
            <input
              id="invite-email"
              type="email"
              autoComplete="email"
              maxLength={254}
              required
              className="field"
              value={inviteEmail}
              onChange={(event) => setInviteEmail(event.target.value)}
            />
          </label>
          <label className="field-group" htmlFor="invite-role">
            Access level
            <select id="invite-role" className="field" value={inviteRole} onChange={(event) => setInviteRole(event.target.value)}>
              {roles.map((role) => <option key={role} value={role}>{role.replaceAll('_', ' ')}</option>)}
            </select>
          </label>
          {isSuperAdmin && (
            <label className="field-group" htmlFor="invite-tenant">
              Workspace
              <select id="invite-tenant" className="field" required value={inviteTenantId} onChange={(event) => setInviteTenantId(event.target.value)}>
                <option value="">Select a workspace</option>
                {tenants.map((tenant) => <option key={tenant.id} value={tenant.id}>{tenant.name}</option>)}
              </select>
            </label>
          )}
          <div className="people-invite-submit">
            <p>The link expires in seven days and can only be used once.</p>
            <button type="submit" className="btn-primary" disabled={inviteMutation.isPending || (isSuperAdmin && !inviteTenantId)}>
              {inviteMutation.isPending ? 'Sending invitation…' : 'Send invitation'}
            </button>
          </div>
        </form>
      </section>

      <section className="panel people-invitations-section" aria-labelledby="invitations-heading">
        <div className="people-section-heading">
          <div>
            <h2 id="invitations-heading">Invitations</h2>
            <p>Track who has been invited and revoke links that are no longer needed.</p>
          </div>
          <span className="people-count">{invitations.length}</span>
        </div>
        {invitations.length ? (
          <div className="people-invitation-list">
            {invitations.map((invitation) => (
              <article className="people-invitation-row" key={invitation.id}>
                <div className="people-invitation-person">
                  <span className="people-invitation-avatar" aria-hidden="true">{invitation.username.slice(0, 1).toUpperCase()}</span>
                  <div>
                    <strong>{invitation.username}</strong>
                    <span>{invitation.email}</span>
                  </div>
                </div>
                <div className="people-invitation-meta">
                  <span className={`people-invitation-status ${invitation.is_active ? 'is-pending' : invitation.used_at ? 'is-accepted' : ''}`}>
                    {statusOf(invitation)}
                  </span>
                  <span>{invitation.role.replaceAll('_', ' ')}</span>
                  <span>{invitation.tenant_name ?? currentUser?.tenant_name ?? 'Workspace'}</span>
                  <span>{invitation.is_active ? `Expires ${formatTimestamp(invitation.expires_at)}` : `Sent ${formatTimestamp(invitation.created_at)}`}</span>
                </div>
                {invitation.is_active && (
                  <button
                    type="button"
                    className="people-revoke-button"
                    disabled={revokeInviteMutation.isPending}
                    onClick={() => revokeInviteMutation.mutate(invitation.id)}
                  >
                    Revoke
                  </button>
                )}
              </article>
            ))}
          </div>
        ) : (
          <div className="people-empty-state">
            <p>No invitations yet.</p>
            <span>Send an invitation above to give someone access to this workspace.</span>
          </div>
        )}
      </section>

      <section className="panel people-accounts-section" aria-labelledby="accounts-heading">
        <div className="people-section-heading">
          <div>
            <h2 id="accounts-heading">Accounts</h2>
            <p>Manage roles and remove access for people already in ChargePilot.</p>
          </div>
          <span className="people-count">{usersQuery.data?.length ?? 0}</span>
        </div>
        <div className="people-table-wrap">
          <table className="people-table">
            <thead>
              <tr>
                <th scope="col">Person</th>
                <th scope="col">Access</th>
                {isSuperAdmin && <th scope="col">Workspace</th>}
                <th scope="col">Joined</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {(usersQuery.data ?? []).map((account) => (
                <tr key={account.id}>
                  <td>
                    <div className="people-account-person">
                      <strong>{account.username}</strong>
                      <span>{account.email ?? 'Email not set'}</span>
                    </div>
                  </td>
                  <td>
                    {account.role === 'super_admin' ? 'Super Admin' : (
                      <form className="people-role-form" onSubmit={(event) => submitRoleChange(event, account)}>
                        <select name="role" aria-label={`Access level for ${account.username}`} defaultValue={account.role} className="field">
                          {roles.map((role) => <option key={role} value={role}>{role.replaceAll('_', ' ')}</option>)}
                        </select>
                        {isSuperAdmin && (
                          <select name="tenant_id" aria-label={`Workspace for ${account.username}`} defaultValue={account.tenant_id ?? ''} required className="field">
                            <option value="">Select workspace</option>
                            {tenants.map((tenant) => <option key={tenant.id} value={tenant.id}>{tenant.name}</option>)}
                          </select>
                        )}
                        <button type="submit" className="btn-secondary" disabled={actionMutation.isPending}>Save access</button>
                      </form>
                    )}
                  </td>
                  {isSuperAdmin && <td>{account.tenant_name ?? 'Unassigned'}</td>}
                  <td>{formatTimestamp(account.created_at)}</td>
                  <td>
                    {account.id !== currentUser?.id && account.role !== 'super_admin' ? (
                      <button
                        type="button"
                        className="people-revoke-button"
                        disabled={actionMutation.isPending}
                        onClick={() => {
                          if (window.confirm(`Remove ${account.username}'s account?`)) {
                            actionMutation.mutate({ path: `/api/v1/admin/users/${account.id}`, method: 'DELETE' })
                          }
                        }}
                      >
                        Remove
                      </button>
                    ) : <span className="people-current-account">You</span>}
                  </td>
                </tr>
              ))}
              {!usersQuery.data?.length && (
                <tr><td colSpan={isSuperAdmin ? 5 : 4} className="people-no-accounts">No accounts found.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}

function TenantsPage() {
  const queryClient = useQueryClient()
  const tenantsQuery = useQuery({ queryKey: ['admin-tenants'], queryFn: () => apiFetch<TenantInfo[]>('/api/v1/admin/tenants') })
  const [statusMessage, setStatusMessage] = useState('')
  const actionMutation = useMutation({
    mutationFn: async ({ path, method, body }: { path: string; method: 'POST' | 'DELETE'; body?: Record<string, unknown> }) =>
      apiFetch<{ message?: string } | undefined>(path, {
        method,
        ...(body ? { body: JSON.stringify(body) } : {}),
      }),
    onSuccess: (_, variables) => {
      setStatusMessage(variables.method === 'DELETE' ? 'Tenant deleted.' : variables.path.includes('rotate-agent-token') ? 'Agent token rotated.' : 'Tenant created.')
      queryClient.invalidateQueries({ queryKey: ['admin-tenants'] })
    },
  })
  if (tenantsQuery.isLoading) return <LoadingCard />
  if (tenantsQuery.error) return <ErrorCard message={tenantsQuery.error.message} />
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const tenantName = String(new FormData(event.currentTarget).get('tenant_name') ?? '')
    actionMutation.mutate({ path: '/api/v1/admin/tenants', method: 'POST', body: { name: tenantName } })
  }
  return <div className="space-y-6">
    <PageHeader eyebrow="Super Admin" title="Tenants" description="Create and manage isolated customer environments and their agent credentials." />
    {statusMessage && <p className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800" role="status">{statusMessage}</p>}
    {actionMutation.error && <ErrorCard message={actionMutation.error.message} />}
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="text-lg font-bold text-slate-900">Create a tenant</h2>
      <form className="mt-4 flex flex-col gap-3 sm:flex-row" onSubmit={submit}><label className="label min-w-0 flex-1" htmlFor="tenant-name">Tenant name<input id="tenant-name" name="tenant_name" required maxLength={160} className="field" /></label><button type="submit" className="btn-primary self-end" disabled={actionMutation.isPending}>Create tenant</button></form>
    </section>
    <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-200 px-5 py-4"><h2 className="font-bold text-slate-900">Tenant directory</h2></div>
      <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-left text-sm">
        <thead className="bg-slate-50 text-xs text-slate-500"><tr><th className="px-4 py-3">Name</th><th className="px-4 py-3">Slug</th><th className="px-4 py-3">Agent token</th><th className="px-4 py-3">Created</th><th className="px-4 py-3">Actions</th></tr></thead>
        <tbody className="divide-y divide-slate-100">{(tenantsQuery.data ?? []).map((tenant) => <tr key={tenant.id}>
          <td className="px-4 py-3 font-semibold text-slate-900">{tenant.name}</td><td className="px-4 py-3 text-slate-600">{tenant.slug}</td><td className="px-4 py-3"><code className="break-all font-mono text-xs">{tenant.agent_token}</code></td><td className="px-4 py-3 text-slate-500">{formatTimestamp(tenant.created_at)}</td>
          <td className="space-y-2 px-4 py-3"><button type="button" className="btn-secondary px-3 py-2" onClick={() => actionMutation.mutate({ path: `/api/v1/admin/tenants/${tenant.id}/rotate-agent-token`, method: 'POST' })}>Rotate token</button><button type="button" className="btn-secondary border-red-200 px-3 py-2 text-red-700" onClick={() => { if (window.confirm('Delete this tenant and all of its tenant data?')) actionMutation.mutate({ path: `/api/v1/admin/tenants/${tenant.id}`, method: 'DELETE' }) }}>Delete</button></td>
        </tr>)}
        {!tenantsQuery.data?.length && <tr><td colSpan={5} className="px-4 py-8 text-center text-slate-500">No tenants have been created yet.</td></tr>}</tbody>
      </table></div>
    </section>
  </div>
}

function AgentSetupPage() {
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const [installGuideOpen, setInstallGuideOpen] = useState(false)
  const installGuideTriggerRef = useRef<HTMLButtonElement | null>(null)
  const tenantId = searchParams.get('tenant_id') ?? ''
  const { data: user } = useSession()
  const isSuperAdmin = user?.role === 'super_admin'
  const canManageEnrollments = isSuperAdmin || user?.role === 'tenant_admin' || user?.role === 'manager'
  const tenantsQuery = useQuery({
    queryKey: ['admin-tenants'],
    queryFn: () => apiFetch<TenantInfo[]>('/api/v1/admin/tenants'),
    enabled: isSuperAdmin,
  })
  const releaseAssetsQuery = useQuery({
    queryKey: ['latest-agent-release-assets'],
    queryFn: async () => {
      const response = await fetch(AGENT_RELEASE_API_URL, {
        headers: { Accept: 'application/vnd.github+json' },
      })
      if (!response.ok) throw new Error(`Could not load the latest agent release (GitHub returned ${response.status}).`)
      const payload: unknown = await response.json()
      if (typeof payload !== 'object' || payload === null) throw new Error('GitHub returned an invalid agent release.')
      const release = payload as { tag_name?: unknown; assets?: unknown }
      if (typeof release.tag_name !== 'string' || !Array.isArray(release.assets)) {
        throw new Error('GitHub returned an incomplete agent release.')
      }
      const assets = release.assets.flatMap((asset) => {
        if (typeof asset !== 'object' || asset === null || !('name' in asset) || !('browser_download_url' in asset)) return []
        const { name, browser_download_url } = asset
        if (typeof name !== 'string' || typeof browser_download_url !== 'string') return []
        const url = new URL(browser_download_url)
        if (url.protocol !== 'https:' || url.hostname !== 'github.com') return []
        return [{ name, url: url.toString() }]
      })
      return { tag: release.tag_name, assets }
    },
    staleTime: 60 * 60 * 1000,
  })
  const reportingSettingsQuery = useQuery({
    queryKey: ['tenant-reporting-settings', isSuperAdmin ? tenantId : user?.tenant_id],
    queryFn: () => apiFetch<TenantReportingSettings>(
      `/api/v1/admin/tenant-settings${isSuperAdmin ? `?tenant_id=${encodeURIComponent(tenantId)}` : ''}`,
    ),
    enabled: Boolean(canManageEnrollments && (!isSuperAdmin || tenantId)),
  })
  const [reportingScheduleDirty, setReportingScheduleDirty] = useState(false)
  const updateReportingSettingsMutation = useMutation({
    mutationFn: (telemetryIntervalMinutes: number) =>
      apiFetch<TenantReportingSettings>('/api/v1/admin/tenant-settings', {
        method: 'PUT',
        body: JSON.stringify({
          telemetry_interval_minutes: telemetryIntervalMinutes,
          ...(isSuperAdmin ? { tenant_id: tenantId } : {}),
        }),
      }),
    onSuccess: (settings) => {
      queryClient.setQueryData(['tenant-reporting-settings', isSuperAdmin ? tenantId : user?.tenant_id], settings)
      queryClient.invalidateQueries({ queryKey: ['endpoints'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      setReportingScheduleDirty(false)
    },
  })
  const [copyStatus, setCopyStatus] = useState('')
  const [revealedEnrollment, setRevealedEnrollment] = useState<RevealedEndpointEnrollment | null>(null)
  const [clockNow, setClockNow] = useState(Date.now)
  useEffect(() => {
    const timer = window.setInterval(() => setClockNow(Date.now()), 10_000)
    return () => window.clearInterval(timer)
  }, [])
  useEffect(() => {
    if (!revealedEnrollment) return
    const enrollmentId = revealedEnrollment.id
    const delay = Math.max(0, Date.parse(revealedEnrollment.expires_at) - Date.now())
    const timer = window.setTimeout(() => {
      setRevealedEnrollment((current) => current?.id === enrollmentId ? null : current)
    }, delay)
    return () => window.clearTimeout(timer)
  }, [revealedEnrollment])
  const tokenQuery = useQuery({
    queryKey: ['endpoint-enrollments'],
    queryFn: () => apiFetch<EndpointEnrollment[]>('/api/v1/admin/endpoint-enrollments'),
    enabled: Boolean(canManageEnrollments),
    refetchInterval: 30_000,
  })
  const createEnrollmentMutation = useMutation({
    mutationFn: () => apiFetch<{ id: string; enrollment_code: string; expires_at: string }>('/api/v1/admin/endpoint-enrollments', {
      method: 'POST',
      body: JSON.stringify(tenantId ? { tenant_id: tenantId } : {}),
    }),
    onSuccess: ({ id, enrollment_code, expires_at }) => {
      setRevealedEnrollment({ id, enrollment_code, expires_at })
      setCopyStatus('')
      void queryClient.invalidateQueries({ queryKey: ['endpoint-enrollments'] })
    },
  })
  const revealEnrollmentMutation = useMutation({
    mutationFn: (enrollmentId: string) =>
      apiFetch<RevealedEndpointEnrollment>(`/api/v1/admin/endpoint-enrollments/${enrollmentId}/token`),
    onSuccess: (enrollment) => {
      setRevealedEnrollment(enrollment)
      setCopyStatus('')
    },
  })
  const revokeEnrollmentMutation = useMutation({
    mutationFn: (enrollmentId: string) =>
      apiFetch<void>(`/api/v1/admin/endpoint-enrollments/${enrollmentId}`, { method: 'DELETE' }),
    onSuccess: (_, enrollmentId) => {
      setRevealedEnrollment((current) => current?.id === enrollmentId ? null : current)
      void queryClient.invalidateQueries({ queryKey: ['endpoint-enrollments'] })
    },
  })
  const activeEnrollments = (tokenQuery.data ?? []).filter((token) => Date.parse(token.expires_at) > clockNow)
  const tokenLimitReached = activeEnrollments.length >= 5
  const revealedEnrollmentIsListed = activeEnrollments.some((token) => token.id === revealedEnrollment?.id)
  const copyText = async (text: string, copiedMessage: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopyStatus(copiedMessage)
    } catch {
      setCopyStatus('Copy was blocked. Select the text and copy it manually.')
    }
  }
  const agentPackages = [
    { platform: 'Windows', format: '.EXE', description: 'Windows service and enrollment window', matches: (name: string) => name.toLowerCase() === 'chargepilotagent.exe' },
    { platform: 'macOS', format: '.DMG', description: 'Menu-bar app for macOS', matches: (name: string) => name.toLowerCase().endsWith('.dmg') },
    { platform: 'iPhone and iPad', format: '.IPA', description: 'iOS app package for provisioned devices', matches: (name: string) => name.toLowerCase().endsWith('.ipa') },
    { platform: 'Android', format: '.APK', description: 'Android app package', matches: (name: string) => name.toLowerCase().endsWith('.apk') },
  ]
  return <div className="space-y-6">
    <header className="setup-page-header">
      <div>
        <p className="page-context">Endpoint setup</p>
        <h1>Enroll a device</h1>
        <p>Create one private token for your workspace, then use it to enroll devices across supported platforms.</p>
      </div>
      <button type="button" className="secondary-btn" onClick={(event) => {
        installGuideTriggerRef.current = event.currentTarget
        setInstallGuideOpen(true)
      }}>
        <CircleHelp size={16} aria-hidden="true" />Install instructions
      </button>
    </header>
    {isSuperAdmin && <section className="panel max-w-3xl p-5 sm:p-6">
      <h2 className="text-lg font-bold text-slate-900">Choose a workspace</h2>
      <p className="mt-1 text-sm text-slate-600">Every device enrolled with this token will belong to the selected workspace.</p>
      {tenantsQuery.error && <div className="mt-3"><ErrorCard message={tenantsQuery.error.message} /></div>}
      <label className="label mt-4" htmlFor="enrollment-tenant">Workspace
        <select id="enrollment-tenant" className="field mt-1" value={tenantId} onChange={(event) => {
          setRevealedEnrollment(null)
          setSearchParams(event.target.value ? { tenant_id: event.target.value } : {})
        }}>
          <option value="">Select a workspace</option>
          {(tenantsQuery.data ?? []).map((tenant) => <option key={tenant.id} value={tenant.id}>{tenant.name}</option>)}
        </select>
      </label>
    </section>}
    {canManageEnrollments && <section className="panel max-w-3xl p-5 sm:p-6" aria-labelledby="reporting-schedule-title">
      <div className="flex items-start gap-3">
        <div className="rounded-lg bg-[var(--surface-muted)] p-2 text-[var(--leaf)]"><Activity size={18} aria-hidden="true" /></div>
        <div>
          <h2 id="reporting-schedule-title" className="text-lg font-bold text-[var(--ink)]">Workspace reporting schedule</h2>
          <p className="mt-1 max-w-xl text-sm leading-6 text-[var(--muted)]">Set how often supported agents should send a battery and system-health report. The backend applies the new target when each agent next checks in.</p>
        </div>
      </div>
      {reportingSettingsQuery.error && <div className="mt-4"><ErrorCard message={reportingSettingsQuery.error.message} /></div>}
      {updateReportingSettingsMutation.error && <div className="mt-4"><ErrorCard message={updateReportingSettingsMutation.error.message} /></div>}
      {isSuperAdmin && !tenantId
        ? <p className="mt-4 text-sm text-[var(--muted)]">Select a workspace above to review its reporting target.</p>
        : reportingSettingsQuery.isLoading
          ? <p className="mt-4 text-sm text-[var(--muted)]">Loading reporting schedule…</p>
          : reportingSettingsQuery.data && <form className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end" onSubmit={(event) => {
            event.preventDefault()
            const interval = Number(new FormData(event.currentTarget).get('telemetry_interval_minutes'))
            updateReportingSettingsMutation.mutate(interval)
          }}>
            <label className="field-group min-w-0 flex-1" htmlFor="reporting-interval">
              <span>Send a report every</span>
              <select
                id="reporting-interval"
                name="telemetry_interval_minutes"
                className="field"
                key={`${reportingSettingsQuery.data.tenant_id}-${reportingSettingsQuery.data.telemetry_interval_minutes}`}
                defaultValue={reportingSettingsQuery.data.telemetry_interval_minutes}
                onChange={() => setReportingScheduleDirty(true)}
              >
                {[5, 10, 15, 30, 60, 120, 360, 720, 1440].map((minutes) => <option key={minutes} value={minutes}>{minutes < 60 ? `${minutes} minutes` : minutes % 60 === 0 ? `${minutes / 60} hour${minutes === 60 ? '' : 's'}` : `${minutes} minutes`}</option>)}
              </select>
            </label>
            <button type="submit" className="btn-primary" disabled={updateReportingSettingsMutation.isPending || !reportingScheduleDirty}>
              {updateReportingSettingsMutation.isPending ? 'Saving schedule…' : 'Save schedule'}
            </button>
          </form>}
      <p className="mt-3 text-xs leading-5 text-[var(--muted)]">Windows and macOS follow the target after a successful report. Android background work has a 15-minute operating-system minimum. iOS reports when opened or triggered by Shortcuts; iOS does not allow ChargePilot to guarantee a recurring background interval. Mobile reports can be delayed.</p>
      {updateReportingSettingsMutation.isSuccess && <p className="mt-3 text-sm text-[var(--leaf)]" role="status">Schedule saved. Enrolled agents will adopt it after their next accepted report.</p>}
    </section>}
    {createEnrollmentMutation.error && <ErrorCard message={createEnrollmentMutation.error.message} />}
    {revealEnrollmentMutation.error && <ErrorCard message={revealEnrollmentMutation.error.message} />}
    {revokeEnrollmentMutation.error && <ErrorCard message={revokeEnrollmentMutation.error.message} />}
    {revealedEnrollment && !revealedEnrollmentIsListed && Date.parse(revealedEnrollment.expires_at) > clockNow && <div className="panel max-w-3xl border-l-4 border-[var(--copper)] p-4 sm:p-5">
      <p className="text-sm font-semibold text-[var(--ink)]">Enrollment token · expires {formatTimestamp(revealedEnrollment.expires_at)}</p>
      <code className="mt-3 block break-all rounded-lg border border-[var(--line)] bg-[var(--surface-muted)] p-3 font-mono text-sm text-[var(--ink)]">{revealedEnrollment.enrollment_code}</code>
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" className="btn-secondary" onClick={() => void copyText(revealedEnrollment.enrollment_code, 'Enrollment token copied.')}>Copy token</button>
        <button type="button" className="btn-secondary" onClick={() => setRevealedEnrollment(null)}>Hide token</button>
        <button type="button" className="danger-btn small-btn" disabled={revokeEnrollmentMutation.isPending} onClick={() => revokeEnrollmentMutation.mutate(revealedEnrollment.id)}>Revoke</button>
      </div>
      <p className="mt-2 min-h-5 text-xs text-[var(--muted)]" role="status">{copyStatus}</p>
    </div>}
    {canManageEnrollments && <section className="panel max-w-3xl p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900">Enrollment token</h2>
          <p className="mt-2 max-w-xl text-sm leading-6 text-slate-600">Create a token for any enabled platform. Reveal or hide it during its 24-hour lifetime, or revoke it at any time.</p>
          <p className="mt-2 text-sm font-semibold text-[var(--ink)]" aria-live="polite">
            Active tokens: {tokenQuery.isLoading ? 'Loading…' : `${activeEnrollments.length} of 5`}
          </p>
        </div>
        <button
          type="button"
          className="btn-primary"
          disabled={createEnrollmentMutation.isPending || tokenQuery.isLoading || tokenQuery.isError || tokenLimitReached || (isSuperAdmin && !tenantId)}
          onClick={() => createEnrollmentMutation.mutate()}
        >
          {createEnrollmentMutation.isPending ? 'Creating token…' : 'Create enrollment token'}
        </button>
      </div>
      {isSuperAdmin && !tenantId && <p className="mt-3 text-sm text-amber-800">Select a workspace before creating a token.</p>}
      {tokenLimitReached && <p className="mt-3 text-sm text-[var(--muted)]">Revoke a token or wait for one to expire before creating another.</p>}
      {tokenQuery.error && <div className="mt-4"><ErrorCard message={tokenQuery.error.message} /></div>}
      {tokenQuery.isLoading && <p className="mt-4 text-sm text-[var(--muted)]">Loading enrollment tokens…</p>}
      {!tokenQuery.isLoading && tokenQuery.data && <div className="mt-6 border-t border-[var(--line)] pt-5">
        <h3 className="font-semibold text-[var(--ink)]">Your active tokens</h3>
        {activeEnrollments.length ? <ul className="mt-3 divide-y divide-[var(--line)]">
          {activeEnrollments.map((token) => {
            const revealed = revealedEnrollment?.id === token.id
            const revealPending = revealEnrollmentMutation.isPending && revealEnrollmentMutation.variables === token.id
            return <li key={token.id} className="py-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-medium text-[var(--ink)]">Expires {formatTimestamp(token.expires_at)}</p>
                  <p className="mt-1 text-xs text-[var(--muted)]">Created {formatTimestamp(token.created_at)} · {token.enrollment_count} device{token.enrollment_count === 1 ? '' : 's'} enrolled · {token.tenant_name}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    className="btn-secondary"
                    disabled={revealEnrollmentMutation.isPending || Date.parse(token.expires_at) <= clockNow}
                    aria-expanded={revealed}
                    onClick={() => {
                      if (revealed) {
                        setRevealedEnrollment(null)
                        setCopyStatus('')
                      } else {
                        setRevealedEnrollment(null)
                        revealEnrollmentMutation.mutate(token.id)
                      }
                    }}
                  >
                    {revealed ? 'Hide token' : revealPending ? 'Loading…' : 'Show token'}
                  </button>
                  <button type="button" className="danger-btn small-btn" disabled={revokeEnrollmentMutation.isPending} onClick={() => revokeEnrollmentMutation.mutate(token.id)}>Revoke</button>
                </div>
              </div>
              {revealed && revealedEnrollment && Date.parse(revealedEnrollment.expires_at) > clockNow && <div className="mt-3 rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] p-3 sm:p-4">
                <p className="text-xs font-medium text-[var(--muted)]">This token is available until it expires.</p>
                <code className="mt-2 block break-all rounded-lg border border-[var(--line)] bg-[var(--surface)] p-3 font-mono text-sm text-[var(--ink)]">{revealedEnrollment.enrollment_code}</code>
                <button type="button" className="btn-secondary mt-3" onClick={() => void copyText(revealedEnrollment.enrollment_code, 'Enrollment token copied.')}>Copy token</button>
                <p className="mt-2 min-h-5 text-xs text-[var(--muted)]" role="status">{copyStatus}</p>
              </div>}
            </li>
          })}
        </ul> : <p className="mt-2 text-sm text-[var(--muted)]">No active tokens. Expired and revoked tokens are hidden.</p>}
      </div>}
    </section>}
    <section className="agent-package-section" aria-labelledby="agent-package-title">
      <div className="agent-package-heading">
        <div>
          <h2 id="agent-package-title">Install a ChargePilot agent</h2>
          <p>Choose the installer for the device you want to enroll.</p>
        </div>
        {releaseAssetsQuery.data && <a href={AGENT_RELEASE_URL} target="_blank" rel="noreferrer">Release {releaseAssetsQuery.data.tag}</a>}
      </div>
      {releaseAssetsQuery.isLoading && <p className="agent-package-message">Loading the latest agent packages…</p>}
      {releaseAssetsQuery.error && <div className="agent-package-error" role="alert">
        <p>{releaseAssetsQuery.error.message}</p>
        <a href={AGENT_RELEASE_URL} target="_blank" rel="noreferrer">Open the latest agent release</a>
      </div>}
      {releaseAssetsQuery.data && <div className="agent-package-grid">
        {agentPackages.map((agentPackage) => {
          const asset = releaseAssetsQuery.data.assets.find((candidate) => agentPackage.matches(candidate.name))
          return <article className="agent-package-card" key={agentPackage.format}>
            <div className="agent-package-format" aria-hidden="true">{agentPackage.format}</div>
            <h3>{agentPackage.platform}</h3>
            <p>{agentPackage.description}</p>
            {asset
              ? <a className="btn-secondary" href={asset.url} download>{`Download ${agentPackage.format}`}</a>
              : <a className="btn-secondary" href={AGENT_RELEASE_URL} target="_blank" rel="noreferrer">Check release assets</a>}
            {asset && <span className="agent-package-filename">{asset.name}</span>}
          </article>
        })}
      </div>}
      {!canManageEnrollments && <p className="agent-enrollment-note">An administrator must create an enrollment token for this workspace.</p>}
      <p className="agent-enrollment-note">After the first report, review devices on the <NavLink to="/endpoints">Endpoints</NavLink> page.</p>
    </section>
    {installGuideOpen && <AgentInstallInstructions onClose={() => {
      setInstallGuideOpen(false)
      window.requestAnimationFrame(() => installGuideTriggerRef.current?.focus())
    }} />}
  </div>
}

function formatPower(watts: number) {
  return watts >= 1000
    ? `${(watts / 1000).toFixed(2)} kW`
    : `${watts.toFixed(1)} W`
}

function formatPercent(value: number | null | undefined) {
  return value === null || value === undefined || !Number.isFinite(value)
    ? 'Not reported'
    : `${Math.round(value)}%`
}

function formatBytes(value: number) {
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

function formatTimestampWithSeconds(value: string | null) {
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

function RelativeTimestamp({ value, now }: { value: string | null; now: number }) {
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

function FieldError({ children }: { children: ReactNode }) {
  return <p className="mt-1.5 text-sm text-red-700" role="alert">{children}</p>
}

function MetricMini({ label, value }: { label: string; value: string }) {
  return <div className="switch-metric"><p>{label}</p><strong>{value}</strong></div>
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
  return <div className="alert error" role="alert">{message}</div>
}

function LiveRefreshControl({
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

function MetricCard({
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

function AgentInstallInstructions({ onClose }: { onClose: () => void }) {
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
      <p className="install-guide-note">Release signing varies by platform and release. Review the latest release notes before installing. iOS Shortcuts and mobile background reports are best-effort and do not guarantee exact reporting times.</p>
      <div className="install-guide-footer">
        <a href={AGENT_RELEASE_URL} target="_blank" rel="noreferrer">Review release notes and signing details</a>
        <button type="button" className="btn-primary" onClick={onClose}>Done</button>
      </div>
    </section>
  </div>
}

function PageHeader({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) {
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

export default App
