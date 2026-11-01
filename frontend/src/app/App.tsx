import { QueryClientProvider, useMutation } from '@tanstack/react-query'

import { BatteryCharging, Bell, Building2, Cable, Cpu, LayoutGrid, LogOut, Mail, Menu, MonitorSmartphone, Network, PlugZap, Plus, ShieldCheck, Users } from 'lucide-react'

import { useEffect, useState } from 'react'

import { BrowserRouter, NavLink, Navigate, Outlet, Route, Routes, useNavigate } from 'react-router-dom'

import { queryClient } from './queryClient'

import { LoginPage, RegisterPage, VerifyEmailPage, AcceptInvitationPage } from '../features/auth/AuthPages'

import { DashboardPage } from '../features/overview/DashboardPage'

import { DevicesPage } from '../features/devices/DevicesPage'

import { MappingsPage } from '../features/mappings/MappingsPage'

import { SmartGroupsPage } from '../features/smart-groups/SmartGroupsPage'

import { EndpointsPage } from '../features/endpoints/EndpointsPage'

import { EventsPage } from '../features/events/EventsPage'

import { ConnectorsPage } from '../features/connectors/ConnectorsPage'

import { ProfilePage } from '../features/account/ProfilePage'

import { UsersPage } from '../features/account/UserManagementPage'

import { TenantsPage } from '../features/account/TenantManagementPage'

import { AgentSetupPage } from '../features/account/AgentSetupPage'

import { SupportPage } from '../features/support/SupportPage'

import { useSession } from '../shared/hooks'

import { LoadingScreen } from '../shared/components'

import { type User } from '../shared/types'

import { apiFetch } from '../shared/api'

import { ThemeToggleButton } from './theme'

import { useAppTheme } from './useAppTheme'

export function App() {
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
            <Route path="/smart-groups" element={<SmartGroupsPage />} />
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
    { to: '/smart-groups', label: 'Smart Groups & Sensors', icon: Cpu },
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

export default App
