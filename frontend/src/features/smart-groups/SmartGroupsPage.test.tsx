import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { SmartGroupsPage } from './SmartGroupsPage'

const endpoint = {
  id: 'endpoint-1',
  tenant_id: 'tenant-1',
  tenant_name: 'Home',
  display_name: 'Office laptop',
  hostname: 'office-laptop',
  hardware_uuid: null,
  installation_id: 'installation-1',
  platform: 'windows' as const,
  device_class: 'laptop' as const,
  ip_address: '192.168.1.25',
  battery: 62,
  charging: true,
  ac_connected: true,
  last_seen_at: '2026-11-01T10:00:00Z',
  status: 'online' as const,
  credential_enrolled: true,
  enabled: true,
  mapped_device: '',
  switch_state: null,
  reporting_interval_minutes: 5,
}

const user = {
  id: 'user-1',
  username: 'manager',
  role: 'manager',
  is_admin: false,
  tenant_id: 'tenant-1',
  tenant_name: 'Home',
}

const catalog = [
  { id: 'os_version', name: 'Operating system version', description: 'Reports the operating system version string.', value_type: 'string' as const },
  { id: 'uptime_seconds', name: 'System uptime', description: 'Reports seconds since the operating system last started.', value_type: 'integer' as const },
]

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function renderPrefilledPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/smart-groups?endpoint_id=endpoint-1&tenant_id=tenant-1']}>
        <SmartGroupsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('single-device check workflow', () => {
  let groups: Array<Record<string, unknown>>

  beforeEach(() => {
    groups = []
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = new URL(String(input), window.location.origin).pathname
      const method = init?.method ?? 'GET'
      if (path === '/api/v1/auth/me') return jsonResponse(user)
      if (path === '/api/v1/smart-groups') {
        if (method === 'POST') {
          const payload = JSON.parse(String(init?.body))
          const group = {
            id: 'group-1',
            tenant_id: 'tenant-1',
            tenant_name: 'Home',
            name: payload.name,
            criteria: payload.criteria,
            sensor_ids: payload.sensor_ids,
            matching_endpoint_count: 1,
            matching_endpoints: [],
            recent_executions: [],
            created_at: '2026-11-01T10:00:00Z',
            updated_at: '2026-11-01T10:00:00Z',
          }
          groups = [group]
          return jsonResponse(group, 201)
        }
        return jsonResponse(groups)
      }
      if (path === '/api/v1/smart-groups/catalog') return jsonResponse(catalog)
      if (path === '/api/v1/endpoints') return jsonResponse([endpoint])
      if (path === '/api/v1/smart-groups/group-1/run') {
        return jsonResponse({ queued_endpoints: 1, queued_sensors: 1 })
      }
      return jsonResponse({ detail: `Unexpected API request: ${path}` }, 404)
    })
  })

  it('preselects the endpoint and creates then queues its approved checks', async () => {
    renderPrefilledPage()

    expect(await screen.findByText('Choose approved system checks for Office laptop.')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Group name' })).toHaveValue('Checks for Office laptop')
    expect(screen.getByRole('checkbox', { name: /Office laptop/ })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: /Operating system version/ })).toBeChecked()
    expect(screen.getByRole('button', { name: 'Create group and run checks' })).toBeEnabled()

    fireEvent.click(screen.getByRole('button', { name: 'Create group and run checks' }))

    expect(await screen.findByRole('status')).toHaveTextContent('Queued 1 check for 1 fresh device.')
    await waitFor(() => {
      expect(vi.mocked(fetch).mock.calls.some(([input, init]) =>
        String(input).includes('/api/v1/smart-groups/group-1/run') && init?.method === 'POST',
      )).toBe(true)
    })
    const createRequest = vi.mocked(fetch).mock.calls.find(([input, init]) =>
      String(input).endsWith('/api/v1/smart-groups') && init?.method === 'POST',
    )
    expect(JSON.parse(String(createRequest?.[1]?.body))).toMatchObject({
      criteria: { platforms: ['windows'], endpoint_ids: ['endpoint-1'] },
      sensor_ids: ['os_version'],
    })
  })
})
