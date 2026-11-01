import { z } from 'zod'

export type User = {
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

export type Endpoint = {
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
  enabled: boolean
  mapped_device: string
  mapped_device_tenant?: string | null
  switch_state: boolean | null
  reporting_interval_minutes: number
}

export type SystemMetrics = {
  cpu_usage_percent: number | null
  gpu_usage_percent: number | null
  memory_used_bytes: number | null
  memory_total_bytes: number | null
  disks: Array<{ name: string; used_bytes: number; total_bytes: number }>
}

export type EndpointReading = {
  timestamp: string
  battery_percentage: number
  charging: boolean
  ac_connected: boolean
  system_metrics: SystemMetrics | null
}

export type EndpointDetails = {
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
    use_case: 'battery_cycle' | 'switch_off_only' | 'switch_and_shutdown'
    on_threshold: number
    off_threshold: number
    minimum_state_change_interval: number
    switch_state: boolean
    power_dp_id: string | null
    energy_dp_id: string | null
    meter_power_watts: number | null
    meter_power_sample_at: string | null
    meter_energy_month_kwh: number | null
    meter_energy_sample_at: string | null
    meter_month_key: string | null
  }>
  readings: EndpointReading[]
}

export type AgentReleaseAssets = {
  tag: string
  assets: Array<{ name: string; url: string }>
}

export type EndpointPageSize = 50 | 100

export type EndpointStatusFilter = 'all' | 'online' | 'offline'

export type TenantReportingSettings = {
  tenant_id: string
  tenant_name: string
  telemetry_interval_minutes: number
}

export type SensorDefinition = {
  id: string
  name: string
  description: string
  value_type: 'string' | 'integer'
}

export type SmartGroupCriteria = {
  platforms: Array<'windows' | 'macos'>
  endpoint_ids?: string[] | null
  name_contains?: string | null
  battery_min?: number | null
  battery_max?: number | null
  charging?: boolean | null
}

export type SensorExecution = {
  id: string
  sensor_id: string
  sensor_name: string
  endpoint_id: string
  endpoint_name: string
  platform: 'windows' | 'macos'
  status: 'queued' | 'claimed' | 'completed' | 'failed' | 'cancelled' | 'expired'
  result: { value: string | number } | null
  error: string | null
  created_at: string | null
  completed_at: string | null
}

export type SmartGroup = {
  id: string
  tenant_id: string
  tenant_name: string
  name: string
  criteria: SmartGroupCriteria
  sensor_ids: string[]
  matching_endpoint_count: number
  matching_endpoints: Array<{
    id: string
    name: string
    platform: 'windows' | 'macos'
    battery_percentage: number
    last_seen_at: string | null
  }>
  recent_executions: SensorExecution[]
  created_at: string
  updated_at: string
}

export type SmartGroupTenant = { id: string; name: string }

export type Device = {
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

export type DeviceMeterSettings = {
  power_dp_id: string | null
  power_multiplier: number
  energy_dp_id: string | null
  energy_multiplier: number
  energy_counter_type: 'cumulative' | 'monthly'
}

export type MeterCandidate = {
  id: string
  label: string
  sample: number
  suggested_role: 'power' | 'energy' | null
}

export type MeterUnitScale = {
  unit: string
  multiplier: number
}

export type MeterScaleParts = {
  unit: string
  decimalPlaces: string
  customBaseScale: string
}

export type DeviceChannel = {
  id: string
  device_id: string
  channel_index: number
  name: string
  dp_id?: string | null
  enabled: boolean
  current_state: boolean
}

export type LanDevice = {
  name: string
  device_id: string
  ip_address: string
  protocol_version: string
  device_type: string
  already_added: boolean
}

export type Connector = {
  id: string
  name: string
  tenant_id: string | null
  tenant_name?: string | null
  is_active: boolean
  is_enrolled: boolean
  is_online: boolean
  last_seen_at?: string | null
}

export type DeviceStatusRefresh = {
  commands: Array<{ id: string; device_id: string; channel_id: string | null }>
  skipped_devices: Array<{ device_id: string; reason: string }>
}

export type ConnectorCommandStatus = {
  status: 'queued' | 'leased' | 'succeeded' | 'failed' | 'expired'
  result?: { error?: string; candidates?: MeterCandidate[] } | null
}

export type DevicesPageData = {
  devices: Device[]
}

export type AdminUser = {
  id: string
  username: string
  email?: string | null
  role: string
  tenant_id?: string | null
  tenant_name?: string | null
  created_at: string
}

export type TenantInfo = {
  id: string
  name: string
  slug: string
  agent_token: string
  created_at: string
}

export type AccountInvitationInfo = {
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

export type EndpointEnrollment = {
  id: string
  tenant_name: string
  created_at: string
  expires_at: string
  enrollment_count: number
  last_used_at?: string | null
}

export type RevealedEndpointEnrollment = {
  id: string
  enrollment_code: string
  expires_at: string
}

export type SmartLifeDevice = {
  device_id: string
  local_key: string
}

export type Mapping = {
  id: string
  tenant_name?: string | null
  endpoint_id: string
  device_id: string
  channel_id?: string | null
  use_case: 'battery_cycle' | 'switch_off_only' | 'switch_and_shutdown'
  turn_on_enabled: boolean
  on_threshold: number
  off_threshold: number
  turn_off_when_charging_enabled: boolean
  charging_off_threshold: number
  minimum_state_change_interval: number
  enabled: boolean
}

export type MappingFormValues = {
  endpoint_id: string
  device_id: string
  channel_id: string
  use_case: 'battery_cycle' | 'switch_off_only' | 'switch_and_shutdown' | ''
  turn_on_enabled: boolean
  on_threshold: number
  off_threshold: number
  turn_off_when_charging_enabled: boolean
  charging_off_threshold: number
  minimum_state_change_interval: number
  enabled: boolean
}

export type EventItem = {
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

export type EventPage = {
  items: EventItem[]
  page: number
  per_page: number
  total_events: number
  total_pages: number
  first_row: number
  last_row: number
}

export const deviceSchema = z.object({
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

export type DeviceFormInput = z.input<typeof deviceSchema>

export type DeviceFormValues = z.output<typeof deviceSchema>
