import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { EndpointDetails } from '../../shared/types'

import { EndpointDetailsPanel } from './EndpointDetails'

const details: EndpointDetails = {
  id: 'endpoint-1',
  tenant_id: 'tenant-1',
  display_name: 'Office laptop',
  hostname: 'office-laptop',
  platform: 'windows',
  device_class: 'laptop',
  hardware_uuid: null,
  installation_id: 'installation-1',
  ip_address: '192.168.1.25',
  battery: 62,
  charging: true,
  ac_connected: true,
  last_seen_at: '2026-11-01T10:00:00Z',
  status: 'online',
  agent_version: '0.1.9',
  enabled: true,
  automation_enabled: true,
  automation_available: true,
  reporting_interval_minutes: 5,
  mappings: [{
    id: 'mapping-1',
    name: 'Desk switch',
    device_id: 'switch-1',
    channel_id: 'channel-1',
    channel_name: 'Outlet 2',
    switch_enabled: true,
    enabled: true,
    use_case: 'battery_cycle',
    on_threshold: 79,
    off_threshold: 99,
    minimum_state_change_interval: 300,
    switch_state: true,
    power_dp_id: null,
    energy_dp_id: null,
    meter_power_watts: null,
    meter_power_sample_at: null,
    meter_energy_month_kwh: null,
    meter_energy_sample_at: null,
    meter_month_key: null,
  }],
  readings: [],
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function renderDetails() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <EndpointDetailsPanel
          details={details}
          isLoading={false}
          error={null}
          canRunChecks
          onClose={() => undefined}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('endpoint actions', () => {
  beforeEach(() => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({
      status: 'succeeded',
      message: 'Switch turned off.',
    }))
  })

  it('links a selected enrolled device to a prefilled approved-check workflow', () => {
    renderDetails()

    expect(screen.getByRole('link', { name: 'Choose checks' })).toHaveAttribute(
      'href',
      '/smart-groups?endpoint_id=endpoint-1&tenant_id=tenant-1',
    )
    expect(screen.getByText(/pasted PowerShell or Python code is not sent or executed/)).toBeInTheDocument()
  })

  it('controls the mapped channel through the existing device-state API', async () => {
    renderDetails()

    fireEvent.click(screen.getByRole('button', { name: 'Turn off' }))

    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalled())

    const request = vi.mocked(fetch).mock.calls.find(([input]) =>
      String(input).includes('/api/v1/devices/switch-1/state'),
    )
    expect(request).toBeDefined()
    expect(request?.[1]?.method).toBe('POST')
    expect(JSON.parse(String(request?.[1]?.body))).toEqual({
      channel_id: 'channel-1',
      desired_state: false,
    })
    expect(await screen.findByRole('status')).toHaveTextContent('Switch turned off.')
  })
})
