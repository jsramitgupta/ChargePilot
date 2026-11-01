import { backendUrl } from './config'

import { type ConnectorCommandStatus, type MeterCandidate, type User, type Endpoint, type Device } from './types'

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
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

export async function waitForConnectorCommands(
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

export async function setDeviceState(
  deviceId: string,
  channelId: string | null,
  desiredState: boolean,
): Promise<string> {
  const result = await apiFetch<{ status: string; command_id?: string; message?: string }>(
    `/api/v1/devices/${deviceId}/state`,
    {
      method: 'POST',
      body: JSON.stringify({ channel_id: channelId, desired_state: desiredState }),
    },
  )
  if (result.command_id) await waitForConnectorCommands([{ id: result.command_id }])
  return result.message ?? `Switch turned ${desiredState ? 'on' : 'off'}.`
}

export async function discoverMeterReadings(deviceId: string): Promise<MeterCandidate[]> {
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

export async function fetchSession(): Promise<User> {
  return apiFetch<User>('/api/v1/auth/me')
}

export async function fetchDashboardData() {
  const [endpoints, devices] = await Promise.all([
    apiFetch<Endpoint[]>('/api/v1/endpoints'),
    apiFetch<Device[]>('/api/v1/devices'),
  ])

  return { endpoints, devices }
}
