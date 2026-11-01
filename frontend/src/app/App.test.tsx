import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'
import { queryClient } from './queryClient'
import { apiFetch, fetchSession } from '../shared/api'
import type { User } from '../shared/types'

vi.mock('../shared/api', () => ({
  apiFetch: vi.fn(),
  fetchSession: vi.fn(),
}))

vi.mock('../features/overview/DashboardPage', () => ({
  DashboardPage: () => <h1>Overview page</h1>,
}))
vi.mock('../features/devices/DevicesPage', () => ({
  DevicesPage: () => <h1>Switches page</h1>,
}))
vi.mock('../features/mappings/MappingsPage', () => ({
  MappingsPage: () => <h1>Automation maps page</h1>,
}))
vi.mock('../features/smart-groups/SmartGroupsPage', () => ({
  SmartGroupsPage: () => <h1>Smart Groups page</h1>,
}))
vi.mock('../features/endpoints/EndpointsPage', () => ({
  EndpointsPage: () => <h1>Endpoints page</h1>,
}))
vi.mock('../features/events/EventsPage', () => ({
  EventsPage: () => <h1>Activity page</h1>,
}))
vi.mock('../features/connectors/ConnectorsPage', () => ({
  ConnectorsPage: () => <h1>Site connectors page</h1>,
}))
vi.mock('../features/account/ProfilePage', () => ({
  ProfilePage: () => <h1>Profile page</h1>,
}))
vi.mock('../features/account/UserManagementPage', () => ({
  UsersPage: () => <h1>People &amp; invites page</h1>,
}))
vi.mock('../features/account/TenantManagementPage', () => ({
  TenantsPage: () => <h1>Tenants page</h1>,
}))
vi.mock('../features/account/AgentSetupPage', () => ({
  AgentSetupPage: () => <h1>Device setup page</h1>,
}))
vi.mock('../features/support/SupportPage', () => ({
  SupportPage: () => <h1>Support page</h1>,
}))

const superAdmin: User = {
  id: 'user-1',
  username: 'operator',
  role: 'super_admin',
  is_admin: true,
  tenant_id: null,
  tenant_name: null,
  timezone: 'UTC',
}

function renderAtPath(path: string) {
  window.history.replaceState({}, '', path)
  return render(<App />)
}

describe('application routes and shell', () => {
  beforeEach(() => {
    queryClient.clear()
    vi.mocked(fetchSession).mockResolvedValue(superAdmin)
  })

  afterEach(() => {
    queryClient.clear()
  })

  it('renders the public login route and accessible credential fields', async () => {
    renderAtPath('/login')

    expect(await screen.findByRole('heading', { name: 'Welcome back' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Username' })).toBeInTheDocument()
    expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password')
  })

  it.each([
    ['/register', 'Choose your access'],
    ['/verify-email', 'Verify your email'],
    ['/accept-invitation', 'Set your password'],
  ])('renders public authentication route %s', async (path, heading) => {
    renderAtPath(path)

    expect(await screen.findByRole('heading', { name: heading })).toBeInTheDocument()
  })

  it('surfaces sign-in errors without leaving the login route', async () => {
    vi.mocked(apiFetch).mockRejectedValueOnce(new Error('Invalid credentials'))
    renderAtPath('/login')
    fireEvent.change(screen.getByRole('textbox', { name: 'Username' }), { target: { value: 'operator' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'wrong-password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Log in' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid credentials')
    expect(window.location.pathname).toBe('/login')
  })

  it('redirects protected pages to login when the session is unavailable', async () => {
    vi.mocked(fetchSession).mockRejectedValue(new Error('Not authenticated'))
    renderAtPath('/devices')

    expect(await screen.findByRole('heading', { name: 'Welcome back' })).toBeInTheDocument()
    await waitFor(() => expect(window.location.pathname).toBe('/login'))
  })

  it.each([
    ['/', 'Overview page', 'Overview'],
    ['/endpoints', 'Endpoints page', 'Endpoints'],
    ['/devices', 'Switches page', 'Switches'],
    ['/mappings', 'Automation maps page', 'Automation maps'],
    ['/smart-groups', 'Smart Groups page', 'Smart Groups & Sensors'],
    ['/connectors', 'Site connectors page', 'Site connectors'],
    ['/events', 'Activity page', 'Activity'],
    ['/profile', 'Profile page', 'Account settings'],
    ['/users', 'People & invites page', 'People & invites'],
    ['/tenants', 'Tenants page', 'Tenants'],
    ['/agent', 'Device setup page', 'Set up a device'],
    ['/support', 'Support page', 'Contact support'],
  ])('renders %s through its registered route', async (path, heading, navigationLabel) => {
    renderAtPath(path)

    expect(await screen.findByRole('heading', { name: heading })).toBeInTheDocument()
    if (path !== '/support') {
      expect(screen.getByRole('link', { name: navigationLabel })).toHaveAttribute('aria-current', 'page')
    }
  })

  it('redirects the legacy account route to profile', async () => {
    renderAtPath('/account')

    expect(await screen.findByRole('heading', { name: 'Profile page' })).toBeInTheDocument()
    expect(window.location.pathname).toBe('/profile')
  })

  it('shows management links according to the signed-in role', async () => {
    const firstRender = renderAtPath('/')
    expect(await screen.findByRole('link', { name: 'Tenants' })).toBeInTheDocument()

    firstRender.unmount()
    queryClient.clear()
    vi.mocked(fetchSession).mockResolvedValue({ ...superAdmin, role: 'manager' })
    renderAtPath('/devices')
    expect(await screen.findByRole('link', { name: 'People & invites' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Tenants' })).not.toBeInTheDocument()
  })

  it('toggles theme from the authenticated shell and persists the preference', async () => {
    renderAtPath('/')

    const toggle = await screen.findByRole('button', { name: 'Use dark theme' })
    fireEvent.click(toggle)

    expect(screen.getByRole('button', { name: 'Use light theme' })).toHaveAttribute('aria-pressed', 'true')
    await waitFor(() => expect(window.localStorage.getItem('chargepilot-theme')).toBe('dark'))
    expect(document.body).toHaveClass('theme-dark')
  })
})
