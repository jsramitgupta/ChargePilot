import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { MappingsPage } from './MappingsPage'
import type { Device, Endpoint } from '../../shared/types'

const endpoint: Endpoint = {
  id: 'endpoint-1',
  tenant_id: 'tenant-1',
  tenant_name: 'Home',
  display_name: 'MacBook Air',
  hostname: 'macbook-air',
  hardware_uuid: null,
  installation_id: 'install-1',
  platform: 'macos',
  ip_address: '192.168.1.25',
  battery: 62,
  charging: true,
  ac_connected: true,
  last_seen_at: '2026-11-01T00:00:00Z',
  status: 'online',
  credential_enrolled: true,
  enabled: true,
  mapped_device: '',
  switch_state: null,
  reporting_interval_minutes: 5,
}

const device: Device = {
  id: 'switch-1',
  tenant_id: 'tenant-1',
  tenant_name: 'Home',
  device_id: 'tuya-device-1',
  name: 'Desk switch',
  ip_address: '192.168.1.30',
  current_state: true,
  channels: [],
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function renderMappingsPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <MappingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('mapping wizard', () => {
  beforeEach(() => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = new URL(String(input), window.location.origin).pathname
      if (path === '/api/v1/mappings') return jsonResponse([])
      if (path === '/api/v1/endpoints') return jsonResponse([endpoint])
      if (path === '/api/v1/devices') return jsonResponse([device])
      if (path === `/api/v1/devices/${device.id}/channels`) return jsonResponse([])
      return jsonResponse({ detail: `Unexpected API request: ${path}` }, 404)
    })
  })

  it('shows a loading state while its data is pending', () => {
    vi.mocked(fetch).mockImplementation(() => new Promise<Response>(() => undefined))
    renderMappingsPage()
    expect(screen.getByText('Loading…')).toBeInTheDocument()
  })

  it('reports mapping data failures explicitly', async () => {
    vi.mocked(fetch).mockImplementation(async (input) => {
      const path = new URL(String(input), window.location.origin).pathname
      if (path === '/api/v1/mappings') return jsonResponse({ detail: 'Mapping service unavailable' }, 503)
      if (path === '/api/v1/endpoints') return jsonResponse([endpoint])
      if (path === '/api/v1/devices') return jsonResponse([device])
      if (path === `/api/v1/devices/${device.id}/channels`) return jsonResponse([])
      return jsonResponse({ detail: `Unexpected API request: ${path}` }, 404)
    })
    renderMappingsPage()
    expect(await screen.findByRole('alert')).toHaveTextContent('Mapping service unavailable')
  })

  it('keeps the wizard moving through a tenant-matched device and switch', async () => {
    renderMappingsPage()

    expect(await screen.findByRole('heading', { name: 'Which device should this switch follow?' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /MacBook Air/ }))
    fireEvent.click(screen.getByRole('button', { name: /Continue/ }))

    expect(await screen.findByRole('heading', { name: 'Choose the switch and output' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Desk switch/ }))
    fireEvent.click(screen.getByRole('button', { name: /Continue/ }))

    expect(await screen.findByRole('heading', { name: 'What should happen to the switch?' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('radio', { name: /Cycle switch power with battery levels/ }))
    fireEvent.click(screen.getByRole('button', { name: /Continue/ }))

    expect(await screen.findByRole('heading', { name: 'Set battery thresholds' })).toBeInTheDocument()
    expect(screen.getByRole('spinbutton', { name: /Turn off at or above/ })).toHaveValue(99)
  })
})
