import { QueryClient, QueryClientProvider, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { zodResolver } from '@hookform/resolvers/zod'
import {
  BatteryCharging,
  Bell,
  Building2,
  Cable,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleDashed,
  List,
  KeyRound,
  LayoutGrid,
  LogIn,
  LogOut,
  Menu,
  Moon,
  MonitorSmartphone,
  Network,
  PlugZap,
  Plus,
  Search,
  ShieldCheck,
  Sun,
  Users,
} from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { BrowserRouter, NavLink, Navigate, Outlet, Route, Routes, useNavigate, useSearchParams } from 'react-router-dom'
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
  tenant_name?: string | null
}

type Endpoint = {
  id: string
  tenant_id?: string | null
  tenant_name?: string | null
  hostname: string
  hardware_uuid: string | null
  ip_address: string | null
  battery: number
  charging: boolean
  ac_connected: boolean
  last_seen_at: string | null
  status: 'online' | 'offline'
  mapped_device: string
  mapped_device_tenant?: string | null
  switch_state: boolean | null
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
  last_seen_at?: string | null
}

type DeviceStatusRefresh = {
  commands: Array<{ id: string; device_id: string; channel_id: string | null }>
  skipped_devices: Array<{ device_id: string; reason: string }>
}

type ConnectorCommandStatus = {
  status: 'queued' | 'leased' | 'succeeded' | 'failed' | 'expired'
  result?: { error?: string } | null
}

type DevicesPageData = {
  devices: Device[]
  skippedDevices: DeviceStatusRefresh['skipped_devices']
}

type AdminUser = {
  id: string
  username: string
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

type TenantInviteInfo = {
  id: string
  tenant_id: string
  tenant_name?: string | null
  created_at: string
  expires_at: string
  used_at?: string | null
  is_active: boolean
}

type AgentSetup = {
  token: string
  global_token?: string | null
  token_scope: string
  install_command: string
  is_super_admin: boolean
  can_rotate_tenant_token: boolean
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
            <Route path="/account" element={<SuperAdminAccountPage />} />
            <Route path="/connectors" element={<ConnectorsPage />} />
            <Route path="/profile" element={<ProfilePage />} />
            <Route path="/users" element={<UsersPage />} />
            <Route path="/tenants" element={<TenantsPage />} />
            <Route path="/agent" element={<AgentSetupPage />} />
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
    { to: '/endpoints', label: 'Laptops', icon: MonitorSmartphone },
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
          <NavLink to="/agent" onClick={() => setMobileOpen(false)} className="rail-link"><Plus size={17} aria-hidden="true" /><span>Set up a laptop</span></NavLink>
          {(user.role === 'super_admin' || user.role === 'tenant_admin' || user.role === 'manager') && <>
            <p className="rail-caption rail-caption-spaced">Manage</p>
            <NavLink to="/users" onClick={() => setMobileOpen(false)} className="rail-link"><Users size={17} aria-hidden="true" /><span>People & invites</span></NavLink>
          </>}
          {user.role === 'super_admin' && <NavLink to="/tenants" onClick={() => setMobileOpen(false)} className="rail-link"><Building2 size={17} aria-hidden="true" /><span>Tenants</span></NavLink>}
        </nav>
        <div className="rail-footer">
          <NavLink to="/profile" className="rail-profile" onClick={() => setMobileOpen(false)}>
            <span className="profile-initial">{user.username.slice(0, 1).toUpperCase()}</span>
            <span className="profile-copy"><strong>{user.username}</strong><small>{user.role.replaceAll('_', ' ')}</small></span>
          </NavLink>
          {user.role === 'super_admin' && <NavLink to="/account" className="rail-footer-link" onClick={() => setMobileOpen(false)}><KeyRound size={15} />Account security</NavLink>}
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
        <p>Reliable laptop monitoring, paired with switches that stay on their own network.</p>
      </div>
      <div className="energy-path" aria-label="Laptop telemetry flows through your site connector to your switch">
        <div className="energy-node"><MonitorSmartphone size={18} /><span>Laptop</span></div>
        <span className="energy-wire"><i /></span>
        <div className="energy-node"><Network size={18} /><span>Site link</span></div>
        <span className="energy-wire"><i /></span>
        <div className="energy-node"><PlugZap size={18} /><span>Switch</span></div>
      </div>
      <p className="auth-story-foot">Battery rules run in ChargePilot. Device control stays local.</p>
    </aside>
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
  const navigate = useNavigate()
  const accountType = searchParams.get('account_type') === 'tenant' ? 'tenant' : 'standard'
  const error = searchParams.get('error')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [inviteCode, setInviteCode] = useState('')
  const [tenantName, setTenantName] = useState('')
  const registerMutation = useMutation({
    mutationFn: () => apiFetch<{ user: User }>('/api/v1/auth/register', {
      method: 'POST',
      body: JSON.stringify({
        account_type: accountType,
        username,
        password,
        ...(accountType === 'standard' ? { invite_code: inviteCode } : { tenant_name: tenantName }),
      }),
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
          {accountType === 'tenant'
            ? <div className="field-group"><label htmlFor="tenant_name">Tenant name</label><input id="tenant_name" name="tenant_name" type="text" minLength={1} maxLength={160} placeholder="My tenant" className="field" required value={tenantName} onChange={(event) => setTenantName(event.target.value)} /></div>
            : <div className="field-group"><label htmlFor="invite_code">One-time tenant invite code</label><input id="invite_code" name="invite_code" type="text" autoComplete="off" spellCheck={false} required className="field font-mono" value={inviteCode} onChange={(event) => setInviteCode(event.target.value)} /><p className="mt-1 text-xs text-slate-500">Ask your tenant administrator for a code. It can be used once and expires after seven days.</p></div>}
          {registerMutation.error && <ErrorCard message={registerMutation.error.message} />}
          <button type="submit" className="primary-btn large-btn w-full" disabled={registerMutation.isPending}>{registerMutation.isPending ? 'Creating account…' : accountType === 'tenant' ? 'Create tenant and admin account' : 'Create standard user account'}</button>
        </form>
        <p className="auth-signin">Already have an account? <a href={frontendUrl('/login')}>Sign in</a></p>
      </section>
    </div>
  )
}

function SuperAdminAccountPage() {
  const { data: user, isLoading, error } = useSession()
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

  if (isLoading) return <LoadingCard />
  if (error || !user) return <ErrorCard message="Your session could not be verified. Sign in again to continue." />
  if (user.role !== 'super_admin') return <Navigate to="/" replace />

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Account security"
        title="Change password"
        description="Update the password used to sign in to the super admin account."
      />
      <section className="panel max-w-2xl p-5 sm:p-6" aria-labelledby="password-form-title">
        <div className="mb-5 flex items-start gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-blue-700">
            <KeyRound size={18} aria-hidden="true" />
          </span>
          <div>
            <h2 id="password-form-title" className="text-lg font-semibold text-slate-900">Super admin password</h2>
            <p className="mt-1 text-sm leading-6 text-slate-600">Use at least 12 characters. Your current session stays active after the change.</p>
          </div>
        </div>
        {successMessage && <p className="alert success mb-4" role="status">{successMessage}</p>}
        {(formError || mutation.error) && (
          <p className="alert error mb-4" role="alert">{formError || mutation.error?.message}</p>
        )}
        <form className="space-y-4" onSubmit={submitPasswordChange}>
          <div className="field-group">
            <label htmlFor="current-password">Current password</label>
            <input
              id="current-password"
              type="password"
              autoComplete="current-password"
              required
              className="field"
              value={currentPassword}
              onChange={(event) => setCurrentPassword(event.target.value)}
            />
          </div>
          <div className="field-group">
            <label htmlFor="new-password">New password</label>
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
          </div>
          <div className="field-group">
            <label htmlFor="confirm-password">Confirm new password</label>
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
          </div>
          <div className="flex justify-end border-t border-slate-200 pt-4">
            <button type="submit" className="btn-primary" disabled={mutation.isPending}>
              {mutation.isPending ? 'Changing password…' : 'Change password'}
            </button>
          </div>
        </form>
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
            <thead><tr><th>Laptop</th><th>Tenant</th><th>Battery</th><th>Power</th><th>Switch</th><th>Switch tenant</th><th>State</th><th>Last seen</th></tr></thead>
            <tbody>
              {endpoints.map((endpoint) => (
                <tr key={endpoint.id}>
                  <td className="strong-cell">{endpoint.hostname}</td>
                  <td>{endpoint.tenant_name ?? 'Unassigned'}</td>
                  <td>{endpoint.battery}%</td>
                  <td><span className={`badge ${endpoint.charging || endpoint.ac_connected ? 'success' : 'muted'}`}>{endpoint.charging ? 'Charging' : endpoint.ac_connected ? 'On AC' : 'On battery'}</span></td>
                  <td>{endpoint.mapped_device}</td>
                  <td>{endpoint.mapped_device_tenant ?? '—'}</td>
                  <td>{endpoint.switch_state === null ? '—' : endpoint.switch_state ? 'On' : 'Off'}</td>
                  <td>{formatTimestamp(endpoint.last_seen_at)}</td>
                </tr>
              ))}
              {!endpoints.length && <tr><td colSpan={8} className="empty-state">No endpoint telemetry has been received yet.</td></tr>}
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
  const [switchView, setSwitchView] = useState<'cards' | 'list'>('cards')
  const [switchFilter, setSwitchFilter] = useState<'all' | 'on' | 'off' | 'unassigned'>('all')
  const [switchSearch, setSwitchSearch] = useState('')
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

  const { data, isLoading, error } = useQuery<DevicesPageData>({
    queryKey: ['devices'],
    queryFn: async () => {
      const refresh = await apiFetch<DeviceStatusRefresh>('/api/v1/devices/status/refresh', {
        method: 'POST',
      })
      await waitForConnectorCommands(refresh.commands, 30_000)
      const devices = await apiFetch<Device[]>('/api/v1/devices')
      return {
        devices: await Promise.all(devices.map(async (device) => ({
          ...device,
          channels: await apiFetch<DeviceChannel[]>(`/api/v1/devices/${device.id}/channels`),
        }))),
        skippedDevices: refresh.skipped_devices,
      }
    },
    refetchInterval: 5 * 60 * 1000,
    refetchIntervalInBackground: false,
  })
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

  const mutation = useMutation({
    mutationFn: async (values: DeviceFormValues) => {
      const { channel_count, connector_id, ...devicePayload } = values
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
  if (error && !data) return <ErrorCard message={error.message} />

  const channelCount = data?.devices.reduce((total, device) => total + (device.channels?.length ?? 0), 0) ?? 0
  const canManageConnectors = user?.role === 'super_admin' || user?.role === 'tenant_admin' || user?.role === 'manager'
  const setupConnectors = connectors.filter((connector) => (
    connector.is_active && connector.is_enrolled && connector.tenant_id === user?.tenant_id
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
    <div className="space-y-6">
      <header className="ui-page-hero rounded-[30px] p-6 sm:p-7">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div><p className="text-[11px] font-bold uppercase tracking-[0.26em] text-blue-200">Device control</p><h1 className="mt-3 text-3xl font-black tracking-tight sm:text-4xl">Smart switches</h1></div>
          <div className="grid grid-cols-3 gap-3 text-left">
            <MetricMini label="Total" value={String(data?.devices.length ?? 0)} />
            <MetricMini label="On" value={String(data?.devices.filter((device) => device.current_state).length ?? 0)} />
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
                form.setValue('connector_id', onlineSetupConnectors.length === 1 ? onlineSetupConnectors[0].id : '')
                setManualOpen(true)
                  }}>{device.already_added ? 'Added' : 'Use device'}</button></div>
                    {device.already_added && <p className="mt-2 text-xs text-slate-500">This device is already configured.</p>}
                  </article>)}
            </div>}
          </section>
        )}
        {!connectors.some((connector) => connector.is_active && connector.is_enrolled) && <p className="mt-4 rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-900">You can scan the ChargePilot server network now. To scan a remote site, <NavLink to="/connectors" className="font-semibold underline">enroll a site connector</NavLink>.</p>}
      </section>

      <section className="rounded-[28px] border border-slate-200 bg-white/90 p-5 shadow-[0_20px_40px_rgba(15,23,42,0.04)] sm:p-6">
        <div className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div><p className="text-[11px] font-bold uppercase tracking-[0.24em] text-slate-500">Add</p><h2 className="mt-2 text-2xl font-bold tracking-tight text-slate-900">Add a switch</h2><p className="mt-2 text-sm leading-6 text-slate-500">Select a scan result or enter its local connection details.</p></div>
          <button type="button" className="btn-secondary" onClick={() => {
            setSelectedLanDeviceId('')
            setManualOpen((open) => {
              if (!open) form.setValue('connector_id', onlineSetupConnectors.length === 1 ? onlineSetupConnectors[0].id : '')
              return !open
            })
          }}>{manualOpen ? 'Close setup' : 'Add switch manually'}</button>
        </div>
        {statusMessage && <p className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800" role="status">{statusMessage}</p>}
        {(mutation.isError || switchMutation.isError || connectorMutation.isError || deleteMutation.isError) && <div className="mb-4"><ErrorCard message={mutation.error?.message ?? switchMutation.error?.message ?? connectorMutation.error?.message ?? deleteMutation.error?.message ?? 'The action failed.'} /></div>}
        {manualOpen && <form className="grid gap-4 border-t border-slate-200 pt-5 md:grid-cols-2" onSubmit={form.handleSubmit((values) => mutation.mutate(values))}>
          <div className="md:col-span-2"><p className="switch-setup-step"><span>1</span> Identify the switch</p></div>
          <div><label className="label" htmlFor="device-name">Display name</label><input id="device-name" className="field" placeholder="Living room plug" {...form.register('name')} />{form.formState.errors.name && <FieldError>{form.formState.errors.name.message}</FieldError>}</div>
          <div><label className="label" htmlFor="device-id">Device ID</label><input id="device-id" className="field" {...form.register('device_id')} />{form.formState.errors.device_id && <FieldError>{form.formState.errors.device_id.message}</FieldError>}</div>
          <div><label className="label" htmlFor="device-ip">Local IP address</label><input id="device-ip" className="field" placeholder="192.168.0.50" {...form.register('ip_address')} /></div>
          <div><label className="label" htmlFor="device-type">Device type</label><input id="device-type" className="field" {...form.register('device_type')} /></div>
          <div><label className="label" htmlFor="device-protocol">Protocol version</label><input id="device-protocol" className="field" {...form.register('protocol_version')} /></div>
          <div className="md:col-span-2"><p className="switch-setup-step"><span>2</span> Add local access details</p></div>
          <div><label className="label" htmlFor="device-key">Local key</label><button type="button" className="ml-2 text-xs font-semibold text-brand-600 underline" onClick={() => setSmartLifeOpen(true)}>Fetch with Smart Life</button><input id="device-key" type="password" autoComplete="new-password" className="field" placeholder="Blank until entered or retrieved" {...form.register('encrypted_local_key')} />{form.formState.errors.encrypted_local_key && <FieldError>{form.formState.errors.encrypted_local_key.message}</FieldError>}<p className="mt-1.5 text-xs leading-5 text-slate-500">The key is kept blank until entered or matched from Smart Life.</p></div>
          <div><label className="label" htmlFor="channel-count">Number of channels</label><select id="channel-count" className="field" {...form.register('channel_count', { valueAsNumber: true })}>{Array.from({ length: 8 }, (_, index) => index + 1).map((count) => <option key={count} value={count}>{count} channel{count > 1 ? 's' : ''}</option>)}</select></div>
          <div className="md:col-span-2"><p className="switch-setup-step"><span>3</span> Choose where commands run</p></div>
          <div className="md:col-span-2">
            <label className="label" htmlFor="new-device-connector">Control this switch through</label>
            <select id="new-device-connector" className="field" {...form.register('connector_id')}>
              <option value="">ChargePilot host · local network only</option>
              {setupConnectors.map((connector) => <option key={connector.id} value={connector.id}>{connector.name} · {connector.is_online ? 'online' : 'offline'}</option>)}
            </select>
            {setupConnectors.length ? (
              <p className="switch-route-help">Choose the site connector that shares this switch’s LAN. An offline connector can be assigned, but won’t control the switch until it reconnects.</p>
            ) : (
              <p className="switch-route-warning">No enrolled connector is available for this tenant. The ChargePilot host option works only when the API host can reach the switch directly. <NavLink to="/connectors">Set up a site connector</NavLink>.</p>
            )}
          </div>
          <div className="md:col-span-2 flex justify-end"><button type="submit" className="btn-primary" disabled={mutation.isPending}><Plus size={16} className="mr-2" />{mutation.isPending ? 'Adding switch…' : 'Save switch setup'}</button></div>
        </form>}
      </section>

      <section className="switch-inventory" aria-labelledby="switch-inventory-title">
        <div className="switch-inventory-heading">
          <div><p className="switch-section-caption">Your device inventory</p><h2 id="switch-inventory-title">Configured switches</h2><p>Check live state, connection route, and channel controls.</p></div>
          <span className="switch-inventory-count">{filteredDevices.length}<small>showing</small></span>
        </div>
        {error && <div className="mb-4"><ErrorCard message={`Could not refresh switch status: ${error.message}`} /></div>}
        {!!data?.skippedDevices.length && <p className="switch-inventory-alert" role="status">{data.skippedDevices.length} switch{data.skippedDevices.length === 1 ? '' : 'es'} could not return live status. Check each switch’s assigned site connector and its heartbeat.</p>}
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
              {!!device.channels?.length ? <div className="channel-panel">{device.channels.map((channel) => <div key={channel.id} className="switch-channel-row">
                <div className="switch-channel-name"><span className="channel-number">{channel.channel_index}</span><span>{channel.name}</span><span className={`channel-state-label ${channel.current_state ? 'is-on' : ''}`}>{channel.current_state ? 'On' : 'Off'}</span></div>
                <button type="button" className="btn-secondary px-3 py-2 text-xs" disabled={switchMutation.isPending} aria-label={`Turn ${channel.current_state ? 'off' : 'on'} ${channel.name}`} onClick={() => switchMutation.mutate({ deviceId: device.id, channelId: channel.id, desiredState: !channel.current_state })}>{channel.current_state ? 'Turn off' : 'Turn on'}</button>
              </div>)}</div> : <div className="switch-card-actions">
                <span className="channel-state-label">Whole switch</span>
                <button type="button" className="btn-secondary px-3 py-2 text-xs" disabled={switchMutation.isPending} onClick={() => switchMutation.mutate({ deviceId: device.id, channelId: '', desiredState: !device.current_state })}>{device.current_state ? 'Turn off' : 'Turn on'}</button>
              </div>}
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
  const queryClient = useQueryClient()
  const [step, setStep] = useState(1)
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
  const selectedDeviceId = useWatch({ control: form.control, name: 'device_id' })
  const selectedEndpointId = useWatch({ control: form.control, name: 'endpoint_id' })
  const onThreshold = useWatch({ control: form.control, name: 'on_threshold' })
  const offThreshold = useWatch({ control: form.control, name: 'off_threshold' })
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
    mutationFn: (values: Record<string, unknown>) =>
      apiFetch<Mapping>('/api/v1/mappings', {
        method: 'POST',
        body: JSON.stringify({ ...values, channel_id: values.channel_id || null }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mappings'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      form.reset()
      setStep(1)
      setStatusMessage('Laptop and switch are now linked.')
    },
  })
  const deleteMutation = useMutation({
    mutationFn: (mappingId: string) => apiFetch<void>(`/api/v1/mappings/${mappingId}`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mappings'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
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
    setStep((current) => Math.min(current + 1, 3))
  }

  return (
    <div className="mapping-workspace">
      <PageHeader
        eyebrow="Automation"
        title="Laptop to switch mappings"
        description="Link a laptop to a switch, then set the battery levels that control it."
      />

      <section className="mapping-builder" aria-labelledby="mapping-builder-title">
        <div className="mapping-builder-heading">
          <div>
            <h2 id="mapping-builder-title">Create a mapping</h2>
            <p>Choose what should be connected, then set how the battery should control it.</p>
          </div>
          <span className="mapping-step-count">Step {step} of 3</span>
        </div>

        <ol className="mapping-stepper" aria-label="Mapping setup">
          {[
            { number: 1, title: 'Choose laptop' },
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
                <span>{item.title}</span>
              </button>
            </li>
          ))}
        </ol>

        <form onSubmit={form.handleSubmit((values) => mutation.mutate(values))}>
          {step === 1 && <div className="mapping-step-content">
            <div className="mapping-step-copy">
              <span className="mapping-step-kicker">01 / Laptop</span>
              <h3>Which laptop should this switch follow?</h3>
              <p>Only laptops in the same tenant can be linked to a switch.</p>
            </div>
            {!endpoints.length ? (
              <div className="mapping-empty-inline">
                <MonitorSmartphone size={22} />
                <div><strong>No laptops registered</strong><p>Register a laptop and send its first telemetry before creating a mapping.</p></div>
                <NavLink to="/endpoints" className="btn-secondary">View laptops</NavLink>
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
                  <span className="mapping-choice-copy"><strong>{endpoint.hostname}</strong><small>{endpoint.tenant_name ?? 'Unassigned tenant'}{endpoint.ip_address ? ` · ${endpoint.ip_address}` : ''}</small></span>
                  <span className={`mapping-choice-battery ${endpoint.battery <= 25 ? 'is-low' : ''}`}>{endpoint.battery}%</span>
                </button>
              ))}
            </div>}
            {form.formState.errors.endpoint_id && <FieldError>Select a laptop to continue.</FieldError>}
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
              <p>{selectedEndpoint ? `Available switches for ${selectedEndpoint.hostname}.` : 'Return to step 1 and choose a laptop first.'}</p>
            </div>
            {!matchingDevices.length ? (
              <div className="mapping-empty-inline">
                <PlugZap size={22} />
                <div><strong>No matching switch is ready</strong><p>Add a switch to the same tenant as the selected laptop.</p></div>
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
              <h3>When should the switch change?</h3>
              <p>Separate thresholds create hysteresis and prevent rapid toggling around one battery level.</p>
            </div>
            <div className="mapping-rule-layout">
              <div className="mapping-rule-fields">
                <label className="mapping-rule-field" htmlFor="on-threshold"><span>Turn on at or below</span><span className="mapping-number-input"><input id="on-threshold" type="number" min={0} max={100} required {...form.register('on_threshold', { valueAsNumber: true, required: true, min: 0, max: 100 })} /><b>%</b></span></label>
                <label className="mapping-rule-field" htmlFor="off-threshold"><span>Turn off at or above</span><span className="mapping-number-input"><input id="off-threshold" type="number" min={0} max={100} required {...form.register('off_threshold', { valueAsNumber: true, required: true, min: 0, max: 100 })} /><b>%</b></span></label>
                <label className="mapping-rule-field" htmlFor="mapping-interval"><span>Minimum time between changes</span><span className="mapping-number-input"><input id="mapping-interval" type="number" min={0} required {...form.register('minimum_state_change_interval', { valueAsNumber: true, required: true, min: 0 })} /><b>sec</b></span></label>
                <label className="mapping-enable-control" htmlFor="mapping-enabled">
                  <input id="mapping-enabled" type="checkbox" {...form.register('enabled')} />
                  <span><strong>Enable automation now</strong><small>The laptop will control this switch as soon as the mapping is saved.</small></span>
                </label>
              </div>
              <div className="mapping-rule-preview" aria-label={`Switch turns on at ${onThreshold} percent and off at ${offThreshold} percent`}>
                <div className="mapping-preview-heading"><BatteryCharging size={18} /><strong>Battery response</strong></div>
                <div className="mapping-battery-track">
                  <span className="mapping-battery-fill" />
                  <span className="mapping-threshold-marker is-on" style={{ left: `${onThreshold}%` }}><i />On · {onThreshold}%</span>
                  <span className="mapping-threshold-marker is-off" style={{ left: `${offThreshold}%` }}><i />Off · {offThreshold}%</span>
                </div>
                <div className="mapping-preview-scale"><span>0%</span><span>100%</span></div>
                <p>On when battery falls to {onThreshold}% · Off when it reaches {offThreshold}%</p>
                {offThreshold <= onThreshold && <span className="mapping-threshold-error" role="alert">The turn-off threshold must be higher than the turn-on threshold.</span>}
              </div>
            </div>
            <div className="mapping-review-route">
              <span className="mapping-review-endpoint"><MonitorSmartphone size={16} />{selectedEndpoint?.hostname ?? 'Laptop not selected'}</span>
              <ChevronRight size={17} aria-hidden="true" />
              <span className="mapping-review-device"><PlugZap size={16} />{selectedDevice?.name ?? 'Switch not selected'}{form.getValues('channel_id') ? ` · ${availableChannels.find((channel) => channel.id === form.getValues('channel_id'))?.name ?? 'Channel'}` : ''}</span>
            </div>
          </div>}

          {mutation.isError && <ErrorCard message={mutation.error.message} />}
          {statusMessage && <p className="mapping-success-message" role="status"><CheckCircle2 size={17} />{statusMessage}</p>}
          <div className="mapping-wizard-footer">
            {step > 1 ? <button type="button" className="btn-secondary" onClick={() => setStep((current) => current - 1)}><ChevronLeft size={16} />Back</button> : <span />}
            {step < 3 ? (
              <button type="button" className="btn-primary" onClick={() => void advanceStep()} disabled={(step === 1 && !selectedEndpointId) || (step === 2 && !tenantsMatch)}>
                Continue <ChevronRight size={16} />
              </button>
            ) : (
              <button type="submit" className="btn-primary" disabled={mutation.isPending || !tenantsMatch || offThreshold <= onThreshold}>
                {mutation.isPending ? 'Saving mapping…' : 'Save mapping'}
              </button>
            )}
          </div>
        </form>
      </section>

      {deleteMutation.isError && <ErrorCard message={deleteMutation.error.message} />}
      <section className="mapping-list-panel" aria-labelledby="mapping-list-title">
        <div className="mapping-list-heading">
          <div><h2 id="mapping-list-title">Current mappings</h2><p>Battery rules currently connecting laptops to switches.</p></div>
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
                    <div className="min-w-0"><span className="mapping-overline">Laptop</span><h3 className="mapping-entity-name">{endpoint?.hostname ?? 'Unknown laptop'}</h3><small>{endpoint?.tenant_name ?? 'Unassigned tenant'}</small></div>
                  </div>
                  <ChevronRight className="mapping-route-arrow" size={19} aria-hidden="true" />
                  <div className="mapping-entity">
                    <span className="mapping-entity-icon switch-icon"><PlugZap size={18} aria-hidden="true" /></span>
                    <div className="min-w-0"><span className="mapping-overline">Switch</span><h3 className="mapping-entity-name">{device?.name ?? 'Unknown switch'}</h3><small>{channel?.name ?? 'Whole switch'}</small></div>
                  </div>
                </div>
                <div className="mapping-rules">
                  <div className="mapping-rule-summary"><span>Turn on</span><strong>{mapping.on_threshold}%</strong><small>or below</small></div>
                  <div className="mapping-rule-summary"><span>Turn off</span><strong>{mapping.off_threshold}%</strong><small>or above</small></div>
                  <div className="mapping-rule-summary"><span>Cooldown</span><strong>{mapping.minimum_state_change_interval}s</strong><small>between changes</small></div>
                  <span className={`mapping-enabled-state ${mapping.enabled ? 'is-enabled' : ''}`}>{mapping.enabled ? 'Automation on' : 'Paused'}</span>
                  <span className="mapping-tenant-label">{mapping.tenant_name ?? 'Unassigned tenant'}</span>
                </div>
                <details className="mapping-id"><summary>Mapping details</summary><code>{mapping.id}</code></details>
              </div>
              <button type="button" className="mapping-delete-button" disabled={deleteMutation.isPending} onClick={() => {
                if (window.confirm('Delete this battery mapping?')) deleteMutation.mutate(mapping.id)
              }}>Delete</button>
            </article>
          })}
          {!mappings?.length && <div className="mapping-empty-state"><Cable size={22} aria-hidden="true" /><h3>No mappings yet</h3><p>Use the three steps above to connect a laptop with a switch.</p></div>}
        </div>
      </section>
    </div>
  )
}

function EndpointsPage() {
  const queryClient = useQueryClient()
  const { data: user } = useSession()
  const [assignedTenantId, setAssignedTenantId] = useState('')
  const tenantsQuery = useQuery({
    queryKey: ['admin-tenants'],
    queryFn: () => apiFetch<TenantInfo[]>('/api/v1/admin/tenants'),
    enabled: user?.role === 'super_admin',
  })
  const [statusMessage, setStatusMessage] = useState('')
  const { data, isLoading, error } = useQuery({
    queryKey: ['endpoints'],
    queryFn: async () => apiFetch<Endpoint[]>('/api/v1/endpoints'),
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

  const deleteMutation = useMutation({
    mutationFn: (endpointId: string) => apiFetch<void>(`/api/v1/endpoints/${endpointId}`, { method: 'DELETE' }),
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
      {statusMessage && <p className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800" role="status">{statusMessage} <NavLink to={assignedTenantId ? `/agent?tenant_id=${assignedTenantId}` : '/agent'} className="font-semibold underline">Open tenant agent setup</NavLink></p>}
      {assignTenantMutation.error && <ErrorCard message={assignTenantMutation.error.message} />}
      {deleteMutation.isError && <ErrorCard message={deleteMutation.error.message} />}
      <section className="panel table-panel">
        <div className="panel-header"><h3>Tracked laptops</h3></div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Hostname</th><th>Tenant</th><th>Hardware UUID</th><th>IP</th><th>Battery</th><th>Power</th><th>Last seen</th><th>Status</th><th className="align-right">Action</th></tr></thead>
            <tbody>
              {data?.map((endpoint) => <tr key={endpoint.id}>
                <td className="strong-cell">{endpoint.hostname}</td>
                <td>{endpoint.tenant_id ? endpoint.tenant_name ?? 'Unknown tenant' : user?.role === 'super_admin' ? <div className="flex min-w-56 flex-col gap-2"><span className="badge muted w-fit">Unassigned</span><form className="flex items-center gap-2" onSubmit={(event) => {
                  event.preventDefault()
                  const tenantId = String(new FormData(event.currentTarget).get('tenant_id') ?? '')
                  if (tenantId) assignTenantMutation.mutate({ endpointId: endpoint.id, tenantId })
                }}>
                  <select name="tenant_id" aria-label={`Tenant for ${endpoint.hostname}`} required className="field min-w-32 py-2"><option value="">Unassigned</option>{(tenantsQuery.data ?? []).map((tenant) => <option key={tenant.id} value={tenant.id}>{tenant.name}</option>)}</select>
                  <button type="submit" className="btn-secondary px-3 py-2" disabled={assignTenantMutation.isPending}>Assign</button>
                </form></div> : 'Unassigned'}</td>
                <td className="font-mono text-xs" title={endpoint.hardware_uuid || undefined}>{endpoint.hardware_uuid || 'Pending agent update'}</td>
                <td>{endpoint.ip_address || 'unknown'}</td>
                <td>{endpoint.battery}%</td>
                <td><span className={`badge ${endpoint.charging || endpoint.ac_connected ? 'success' : 'muted'}`}>{endpoint.charging ? 'Charging' : endpoint.ac_connected ? 'On AC' : 'On battery'}</span></td>
                <td>{formatTimestamp(endpoint.last_seen_at)}</td>
                <td><span className={`badge ${endpoint.status === 'online' ? 'success' : 'muted'}`}>{endpoint.status}</span></td>
                <td className="align-right"><button type="button" className="danger-btn small-btn" disabled={deleteMutation.isPending} onClick={() => {
                  if (window.confirm(`Delete laptop ${endpoint.hostname}? Its mappings and event history will also be removed.`)) deleteMutation.mutate(endpoint.id)
                }}>Delete laptop</button></td>
              </tr>)}
              {!data?.length && <tr><td colSpan={9} className="empty-state">No laptops have reported telemetry yet.</td></tr>}
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

function ConnectorsPage() {
  const queryClient = useQueryClient()
  const { data: user } = useSession()
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

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Remote device networks" title="Site connectors" description="Connect a computer on the same local network as your Tuya switches. It securely polls ChargePilot over HTTPS and performs discovery and control on site." />
      {actionError && <ErrorCard message={actionError.message} />}
      {enrollmentCode && (
        <section className="rounded-2xl border border-amber-300 bg-amber-50 p-5" aria-labelledby="enrollment-code-title">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div><h2 id="enrollment-code-title" className="text-lg font-bold text-amber-950">One-time enrollment code</h2><p className="mt-1 text-sm text-amber-900">Enter it on the connector computer within 15 minutes. This code is shown only once.</p></div>
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
          <h2 className="text-lg font-bold text-slate-900">Add a connector</h2>
          <p className="mt-1 text-sm text-slate-600">Download the package, then create a single-use enrollment code.</p>
          <a href={backendUrl('/connectors/download')} className="mt-4 inline-flex rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-sm font-semibold text-blue-700 hover:bg-blue-100">Download connector package</a>
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
  return <div className="mx-auto max-w-3xl space-y-5">
    <PageHeader eyebrow="Account" title={user.username} description="Manage the display settings for your ChargePilot account." />
    <section className="grid gap-4 sm:grid-cols-2">
      <MetricMini label="Role" value={user.role.replaceAll('_', ' ')} />
      <MetricMini label="Tenant" value={user.tenant_name ?? 'Personal tenant'} />
    </section>
    <section className="profile-preference panel">
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
  </div>
}

function UsersPage() {
  const queryClient = useQueryClient()
  const { data: currentUser, isLoading: sessionLoading } = useSession()
  const usersQuery = useQuery({ queryKey: ['admin-users'], queryFn: () => apiFetch<AdminUser[]>('/api/v1/admin/users') })
  const tenantsQuery = useQuery({ queryKey: ['admin-tenants'], queryFn: () => apiFetch<TenantInfo[]>('/api/v1/admin/tenants'), enabled: currentUser?.role === 'super_admin' })
  const invitesQuery = useQuery({ queryKey: ['admin-invites'], queryFn: () => apiFetch<TenantInviteInfo[]>('/api/v1/admin/invites') })
  const [statusMessage, setStatusMessage] = useState('')
  const [inviteCode, setInviteCode] = useState('')
  const [inviteTenantId, setInviteTenantId] = useState('')
  const actionMutation = useMutation({
    mutationFn: async ({ method, path, body }: { method: 'POST' | 'PATCH' | 'DELETE'; path: string; body?: Record<string, unknown> }) =>
      apiFetch<{ message?: string } | undefined>(path, {
        method,
        ...(body ? { body: JSON.stringify(body) } : {}),
      }),
    onSuccess: (_, variables) => {
      setStatusMessage(variables.method === 'DELETE' ? 'User deleted.' : variables.method === 'PATCH' ? 'User updated.' : 'User created.')
      queryClient.invalidateQueries({ queryKey: ['admin-users'] })
    },
  })
  const inviteMutation = useMutation({
    mutationFn: () => apiFetch<{ id: string; code: string }>('/api/v1/admin/invites', {
      method: 'POST',
      body: JSON.stringify(isSuperAdmin ? { tenant_id: inviteTenantId } : {}),
    }),
    onSuccess: ({ code }) => {
      setInviteCode(code)
      queryClient.invalidateQueries({ queryKey: ['admin-invites'] })
    },
  })
  const revokeInviteMutation = useMutation({
    mutationFn: (inviteId: string) => apiFetch<void>(`/api/v1/admin/invites/${inviteId}`, { method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin-invites'] }),
  })
  const isSuperAdmin = currentUser?.role === 'super_admin'
  if (sessionLoading || usersQuery.isLoading || tenantsQuery.isLoading || invitesQuery.isLoading) return <LoadingCard />
  if (usersQuery.error) return <ErrorCard message={usersQuery.error.message} />
  if (tenantsQuery.error) return <ErrorCard message={tenantsQuery.error.message} />
  if (invitesQuery.error) return <ErrorCard message={invitesQuery.error.message} />
  const tenants = tenantsQuery.data ?? []
  const roles = ['tenant_admin', 'manager', 'standard_user', 'viewer']
  const submit = (event: FormEvent<HTMLFormElement>, path: string, method: 'POST' | 'PATCH' = 'POST') => {
    event.preventDefault()
    const body = Object.fromEntries(new FormData(event.currentTarget).entries())
    actionMutation.mutate({ path: path === '/users' ? '/api/v1/admin/users' : path, method, body })
  }
  return <div className="space-y-6">
    <PageHeader eyebrow="Administration" title="User accounts" description="Add people to your tenant and control which ChargePilot tasks they can access." />
    {statusMessage && <p className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800" role="status">{statusMessage}</p>}
    {(actionMutation.error || inviteMutation.error || revokeInviteMutation.error) && <ErrorCard message={actionMutation.error?.message ?? inviteMutation.error?.message ?? revokeInviteMutation.error?.message ?? 'The request failed.'} />}
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="text-lg font-bold text-slate-900">Invite a standard user</h2>
      <p className="mt-1 max-w-2xl text-sm text-slate-600">Create a one-use code for someone joining this tenant. It expires in seven days and is shown only once.</p>
      {inviteCode && <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-4">
        <p className="text-sm font-semibold text-emerald-900">Copy this code and share it with the new user.</p>
        <output className="mt-2 block select-all break-all font-mono text-sm text-emerald-950">{inviteCode}</output>
        <button type="button" className="btn-secondary mt-3" onClick={async () => {
          try {
            await navigator.clipboard.writeText(inviteCode)
            setStatusMessage('Invite code copied.')
          } catch {
            setStatusMessage('Copy was blocked. Select the code and copy it manually.')
          }
        }}>Copy invite code</button>
      </div>}
      <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end">
        {isSuperAdmin && <label className="label min-w-0 flex-1" htmlFor="invite-tenant">Tenant<select id="invite-tenant" className="field" required value={inviteTenantId} onChange={(event) => setInviteTenantId(event.target.value)}><option value="">Select a tenant</option>{tenants.map((tenant) => <option key={tenant.id} value={tenant.id}>{tenant.name}</option>)}</select></label>}
        <button type="button" className="btn-primary" disabled={inviteMutation.isPending || (isSuperAdmin && !inviteTenantId)} onClick={() => { setInviteCode(''); inviteMutation.mutate() }}>{inviteMutation.isPending ? 'Creating code…' : 'Create one-time invite'}</button>
      </div>
      {!!invitesQuery.data?.length && <div className="mt-4 divide-y divide-slate-100 border-t border-slate-200">
        {invitesQuery.data.map((invite) => <div key={invite.id} className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm">
          <div><span className="font-semibold">{invite.tenant_name ?? currentUser?.tenant_name ?? 'Tenant'}</span><span className="ml-2 text-slate-500">{invite.used_at ? 'Used' : invite.is_active ? `Expires ${formatTimestamp(invite.expires_at)}` : 'Expired'}</span></div>
          {invite.is_active && <button type="button" className="text-sm font-semibold text-red-700 underline" onClick={() => revokeInviteMutation.mutate(invite.id)}>Revoke</button>}
        </div>)}
      </div>}
    </section>
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="text-lg font-bold text-slate-900">Create a user</h2>
      <form className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4" onSubmit={(event) => submit(event, '/users')}>
        <label className="label" htmlFor="new-user-name">Username<input id="new-user-name" name="username" minLength={3} maxLength={80} required className="field" /></label>
        <label className="label" htmlFor="new-user-password">Password<input id="new-user-password" name="password" minLength={12} maxLength={72} required type="password" autoComplete="new-password" className="field" /></label>
        <label className="label" htmlFor="new-user-role">Role<select id="new-user-role" name="role" className="field">{roles.map((role) => <option key={role} value={role}>{role.replaceAll('_', ' ')}</option>)}</select></label>
        {isSuperAdmin && <label className="label" htmlFor="new-user-tenant">Tenant<select id="new-user-tenant" name="tenant_id" required className="field"><option value="">Select a tenant</option>{tenants.map((tenant) => <option key={tenant.id} value={tenant.id}>{tenant.name}</option>)}</select></label>}
        <button type="submit" className="btn-primary sm:col-span-2 xl:col-span-4" disabled={actionMutation.isPending}>Create user</button>
      </form>
    </section>
    <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-200 px-5 py-4"><h2 className="font-bold text-slate-900">Accounts</h2></div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[680px] text-left text-sm">
          <thead className="bg-slate-50 text-xs text-slate-500"><tr><th className="px-4 py-3">Username</th><th className="px-4 py-3">Role</th>{isSuperAdmin && <th className="px-4 py-3">Tenant</th>}<th className="px-4 py-3">Created</th><th className="px-4 py-3">Actions</th></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {(usersQuery.data ?? []).map((account) => <tr key={account.id}>
              <td className="px-4 py-3 font-semibold text-slate-900">{account.username}</td>
              <td className="px-4 py-3">{account.role === 'super_admin' ? 'Super Admin' : <form className="flex flex-wrap gap-2" onSubmit={(event) => submit(event, `/api/v1/admin/users/${account.id}`, 'PATCH')}><select name="role" aria-label={`Role for ${account.username}`} defaultValue={account.role} className="field min-w-32 py-2">{roles.map((role) => <option key={role} value={role}>{role.replaceAll('_', ' ')}</option>)}</select>{isSuperAdmin && <select name="tenant_id" aria-label={`Tenant for ${account.username}`} defaultValue={account.tenant_id ?? ''} required className="field min-w-36 py-2"><option value="">Select tenant</option>{tenants.map((tenant) => <option key={tenant.id} value={tenant.id}>{tenant.name}</option>)}</select>}<button type="submit" className="btn-secondary px-3 py-2">Save</button></form>}</td>
              {isSuperAdmin && <td className="px-4 py-3">{account.tenant_name ?? 'Unassigned'}</td>}
              <td className="px-4 py-3 text-slate-500">{formatTimestamp(account.created_at)}</td>
              <td className="px-4 py-3">{account.id !== currentUser?.id && account.role !== 'super_admin' ? <button type="button" className="btn-secondary border-red-200 px-3 py-2 text-red-700" onClick={() => { if (window.confirm('Delete this user?')) actionMutation.mutate({ path: `/api/v1/admin/users/${account.id}`, method: 'DELETE' }) }}>Delete</button> : <span className="text-xs text-slate-400">Current</span>}</td>
            </tr>)}
            {!usersQuery.data?.length && <tr><td colSpan={isSuperAdmin ? 5 : 4} className="px-4 py-8 text-center text-slate-500">No users found.</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  </div>
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
  const tenantId = searchParams.get('tenant_id') ?? ''
  const { data: user } = useSession()
  const tenantsQuery = useQuery({
    queryKey: ['admin-tenants'],
    queryFn: () => apiFetch<TenantInfo[]>('/api/v1/admin/tenants'),
    enabled: user?.role === 'super_admin',
  })
  const setupQuery = useQuery({
    queryKey: ['agent-setup', tenantId],
    queryFn: () => apiFetch<AgentSetup>(`/api/v1/agent/setup${tenantId ? `?tenant_id=${encodeURIComponent(tenantId)}` : ''}`),
  })
  const [statusMessage, setStatusMessage] = useState('')
  const [copyStatus, setCopyStatus] = useState('')
  const mutation = useMutation({
    mutationFn: async ({ path, body }: { path: string; body: Record<string, unknown> }) =>
      apiFetch<{ message: string }>(path, { method: 'PUT', body: JSON.stringify(body) }),
    onSuccess: ({ message }) => {
      setStatusMessage(message)
      return queryClient.invalidateQueries({ queryKey: ['agent-setup'] })
    },
  })
  const data = setupQuery.data
  if (setupQuery.isLoading) return <LoadingCard />
  if (setupQuery.error) return <ErrorCard message={setupQuery.error.message} />
  return <div className="space-y-6">
    <PageHeader eyebrow="Endpoint setup" title="Install the laptop agent" description="Download the Windows scripts, extract them, and run the command on each laptop you want ChargePilot to monitor." />
    {statusMessage && <p className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800" role="status">{statusMessage}</p>}
    {mutation.error && <ErrorCard message={mutation.error.message} />}
    {data?.is_super_admin && <section className="rounded-2xl border border-blue-200 bg-blue-50 p-5">
      <h2 className="font-bold text-slate-900">Choose endpoint tenant</h2>
      <p className="mt-1 text-sm text-slate-600">Use the tenant-specific agent token for laptops assigned to a tenant. The global token only registers unassigned endpoints.</p>
      {tenantsQuery.error && <div className="mt-3"><ErrorCard message={tenantsQuery.error.message} /></div>}
      <label className="label mt-4" htmlFor="agent-tenant">Agent token scope
        <select id="agent-tenant" className="field" value={tenantId} onChange={(event) => {
          const value = event.target.value
          setSearchParams(value ? { tenant_id: value } : {})
        }}>
          <option value="">System-wide unassigned endpoints</option>
          {(tenantsQuery.data ?? []).map((tenant) => <option key={tenant.id} value={tenant.id}>{tenant.name}</option>)}
        </select>
      </label>
    </section>}
    {data?.is_super_admin && <section className="rounded-2xl border border-blue-200 bg-blue-50 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="font-bold text-slate-900">Global agent token</h2><p className="mt-1 text-sm text-slate-600">This token registers unassigned endpoints. Use tenant-specific tokens for assigned laptops. Regenerating stops agents using the previous value.</p></div><button type="button" className="btn-secondary" onClick={() => { if (window.confirm('Regenerate the global agent token? Existing agents using it will stop authenticating.')) mutation.mutate({ path: '/api/v1/admin/global-agent-token', body: { action: 'regenerate' } }) }}>Regenerate token</button></div>
      <form className="mt-4 flex flex-col gap-3 sm:flex-row" onSubmit={(event) => { event.preventDefault(); mutation.mutate({ path: '/api/v1/admin/global-agent-token', body: { action: 'save', token: String(new FormData(event.currentTarget).get('token') ?? '') } }) }}><input name="token" defaultValue={data?.global_token ?? ''} required minLength={16} maxLength={512} autoComplete="off" spellCheck={false} className="field min-w-0 flex-1 font-mono" aria-label="Global agent token" /><button type="submit" className="btn-primary">Save token</button></form>
    </section>}
    <section className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
      <div className="grid lg:grid-cols-[0.9fr_1.1fr]">
        <div className="ui-modal-heading p-6 text-white sm:p-8"><h2 className="text-2xl font-bold">Get the Windows scripts</h2><p className="mt-2 text-sm leading-6 text-slate-300">The ZIP contains the telemetry agent and scheduled-task installer. Your token is not embedded in the archive.</p><a href={backendUrl('/agent/download')} className="mt-6 inline-flex items-center justify-center rounded-xl bg-blue-500 px-4 py-3 text-sm font-bold text-white hover:bg-blue-400">Download agent scripts</a><p className="mt-3 text-xs text-slate-400">ZIP archive · PowerShell · Windows 10/11</p></div>
        <div className="p-6 sm:p-8"><h2 className="text-2xl font-bold tracking-tight text-slate-900">Run the setup command</h2><p className="mt-2 text-sm leading-6 text-slate-600">Extract the ZIP, open PowerShell in that folder, and run this command.</p><div className="mt-5 break-all rounded-xl border border-slate-200 bg-slate-50 p-4"><code className="font-mono text-sm text-slate-800">{data?.install_command}</code></div><button type="button" className="btn-secondary mt-3" onClick={async () => {
          try {
            await navigator.clipboard.writeText(data?.install_command ?? '')
            setCopyStatus('Install command copied.')
          } catch {
            setCopyStatus('Copy was blocked. Select the command and copy it manually.')
          }
        }}>Copy command</button><p className="mt-2 min-h-4 text-xs text-slate-500" role="status">{copyStatus}</p><div className="mt-6 border-t border-slate-200 pt-5"><p className="text-xs font-bold text-slate-500">{data?.token_scope}</p><p className="mt-1 text-xs text-slate-500">Keep this private. Regenerating it stops agents using the previous token.</p><code className="mt-3 block break-all rounded-xl border border-slate-200 bg-slate-50 px-3 py-3 font-mono text-sm text-slate-800">{data?.token}</code>{data?.can_rotate_tenant_token && <button type="button" className="btn-secondary mt-3" onClick={() => { if (window.confirm('Regenerate this tenant token? Agents using the old token will stop authenticating.')) mutation.mutate({ path: '/api/v1/admin/tenant-agent-token', body: {} }) }}>Regenerate tenant token</button>}</div></div>
      </div>
    </section>
    <p className="text-sm text-slate-500">After the first report, the laptop appears on the <NavLink to="/endpoints" className="font-semibold text-blue-700 underline">Endpoints</NavLink> page.</p>
  </div>
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
