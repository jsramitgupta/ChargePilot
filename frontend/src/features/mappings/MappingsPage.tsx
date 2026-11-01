import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { BatteryCharging, Cable, CheckCircle2, ChevronLeft, ChevronRight, MonitorSmartphone, Pencil, PlugZap } from 'lucide-react'

import { useState } from 'react'

import { useForm, useWatch } from 'react-hook-form'

import { NavLink } from 'react-router-dom'

import { type Mapping, type Endpoint, type Device, type DeviceChannel, type MappingFormValues } from '../../shared/types'

import { apiFetch } from '../../shared/api'

import { LoadingCard, PageHeader, FieldError, ErrorCard } from '../../shared/components'

export function MappingsPage() {
  const queryClient = useQueryClient()
  const [step, setStep] = useState(1)
  const [editingMappingId, setEditingMappingId] = useState<string | null>(null)
  const [statusMessage, setStatusMessage] = useState('')
  const { data: mappings, isLoading: mappingsLoading, error: mappingsError } = useQuery<Mapping[]>({
    queryKey: ['mappings'],
    queryFn: () => apiFetch<Mapping[]>('/api/v1/mappings'),
  })
  const { data: endpoints = [], isLoading: endpointsLoading, error: endpointsError } = useQuery<Endpoint[]>({
    queryKey: ['endpoints'],
    queryFn: () => apiFetch<Endpoint[]>('/api/v1/endpoints'),
  })
  const { data: devices = [], isLoading: devicesLoading, error: devicesError } = useQuery<Device[]>({
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
      use_case: '',
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
  const useCase = useWatch({ control: form.control, name: 'use_case' })
  const turnOnEnabled = useWatch({ control: form.control, name: 'turn_on_enabled' })
  const onThreshold = useWatch({ control: form.control, name: 'on_threshold' })
  const offThreshold = useWatch({ control: form.control, name: 'off_threshold' })
  const turnOffWhenChargingEnabled = useWatch({ control: form.control, name: 'turn_off_when_charging_enabled' })
  const chargingOffThreshold = useWatch({ control: form.control, name: 'charging_off_threshold' })
  const availableChannels = devices?.find((device) => device.id === selectedDeviceId)?.channels ?? []
  const selectedEndpoint = endpoints?.find((endpoint) => endpoint.id === selectedEndpointId)
  const canShutdownSelectedEndpoint =
    selectedEndpoint?.tenant_id != null &&
    selectedEndpoint.installation_id != null &&
    ['windows', 'macos'].includes(selectedEndpoint.platform)
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
  if (mappingsError) return <ErrorCard message={mappingsError.message} />
  if (endpointsError) return <ErrorCard message={endpointsError.message} />
  if (devicesError) return <ErrorCard message={devicesError.message} />

  async function advanceStep() {
    const valid = step === 1
      ? await form.trigger('endpoint_id')
      : step === 2
        ? await form.trigger('device_id')
        : await form.trigger('use_case')
    if (!valid) return
    if (step === 1 && matchingDevices.length === 0) return
    setStatusMessage('')
    setStep((current) => Math.min(current + 1, 4))
  }

  function editMapping(mapping: Mapping) {
    mutation.reset()
    setStatusMessage('')
    setEditingMappingId(mapping.id)
    form.reset({
      endpoint_id: mapping.endpoint_id,
      device_id: mapping.device_id,
      channel_id: mapping.channel_id ?? '',
      use_case: mapping.use_case,
      turn_on_enabled: mapping.turn_on_enabled,
      on_threshold: mapping.on_threshold,
      off_threshold: mapping.off_threshold,
      turn_off_when_charging_enabled: mapping.turn_off_when_charging_enabled,
      charging_off_threshold: mapping.charging_off_threshold,
      minimum_state_change_interval: mapping.minimum_state_change_interval,
      enabled: mapping.enabled,
    })
    setStep(4)
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
        title="Automation maps"
        description="Choose the device, switch and response that should follow its battery."
      />

      <section className="mapping-builder" aria-labelledby="mapping-builder-title">
        <div className="mapping-builder-heading">
          <div>
            <h2 id="mapping-builder-title">{editingMappingId ? 'Edit mapping' : 'Create a mapping'}</h2>
            <p>{editingMappingId ? 'Review the linked device and switch, then adjust the automation rules.' : 'Choose what should be connected, then set how the battery should control it.'}</p>
          </div>
          <span className="mapping-step-count">Step {step} of 4</span>
        </div>

        <ol className="mapping-stepper" aria-label="Mapping setup">
          {[
            { number: 1, title: 'Choose device' },
            { number: 2, title: 'Choose switch' },
            { number: 3, title: 'Choose use case' },
            { number: 4, title: 'Set battery rules' },
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
              <span className="mapping-step-kicker">03 / Use case</span>
              <h3>What should happen to the switch?</h3>
              <p>Choose the switch behavior first. Battery thresholds are set in the next step.</p>
            </div>
            <div className="mapping-use-case-options" role="radiogroup" aria-label="Automation use case">
              <button
                type="button"
                role="radio"
                aria-checked={useCase === 'battery_cycle'}
                className={`mapping-use-case-option ${useCase === 'battery_cycle' ? 'is-selected' : ''}`}
                onClick={() => {
                  form.setValue('use_case', 'battery_cycle', { shouldValidate: true })
                  form.setValue('turn_on_enabled', true)
                  form.clearErrors('use_case')
                }}
              >
                <span className="mapping-use-case-icon"><BatteryCharging size={21} aria-hidden="true" /></span>
                <span className="mapping-use-case-copy">
                  <strong>Cycle switch power with battery levels</strong>
                  <small>Turn the switch on at a low battery level and off at your chosen charge target.</small>
                </span>
                <span className="mapping-use-case-indicator" aria-hidden="true" />
              </button>
              <button
                type="button"
                role="radio"
                aria-checked={useCase === 'switch_off_only'}
                className={`mapping-use-case-option ${useCase === 'switch_off_only' ? 'is-selected' : ''}`}
                onClick={() => {
                  form.setValue('use_case', 'switch_off_only', { shouldValidate: true })
                  form.setValue('turn_on_enabled', false)
                  form.clearErrors('use_case')
                }}
              >
                <span className="mapping-use-case-icon"><PlugZap size={21} aria-hidden="true" /></span>
                <span className="mapping-use-case-copy">
                  <strong>Only turn off the smart switch</strong>
                  <small>Keep automatic turn-on disabled; switch-off thresholds still apply.</small>
                </span>
                <span className="mapping-use-case-indicator" aria-hidden="true" />
              </button>
              <button
                type="button"
                role="radio"
                aria-checked={useCase === 'switch_and_shutdown'}
                className={`mapping-use-case-option ${useCase === 'switch_and_shutdown' ? 'is-selected' : ''} ${canShutdownSelectedEndpoint ? '' : 'is-unavailable'}`}
                disabled={!canShutdownSelectedEndpoint}
                aria-describedby="mapping-shutdown-support"
                onClick={() => {
                  form.setValue('use_case', 'switch_and_shutdown', { shouldValidate: true })
                  form.setValue('turn_on_enabled', false)
                  form.clearErrors('use_case')
                }}
              >
                <span className="mapping-use-case-icon"><MonitorSmartphone size={21} aria-hidden="true" /></span>
                <span className="mapping-use-case-copy">
                  <strong>Turn off the switch and the Windows or macOS device</strong>
                  <small id="mapping-shutdown-support">{canShutdownSelectedEndpoint
                    ? selectedEndpoint?.platform === 'macos'
                      ? 'The Mac asks for local confirmation. It must be awake with the agent open.'
                      : 'Windows shows a 60-second countdown that a local user can cancel.'
                    : 'Available only for enrolled, tenant-assigned Windows and macOS devices.'}</small>
                </span>
                <span className="mapping-use-case-indicator" aria-hidden="true" />
              </button>
            </div>
            {form.formState.errors.use_case && <FieldError>Select a supported use case to continue.</FieldError>}
          </div>}

          {step === 4 && <div className="mapping-step-content">
            <div className="mapping-step-copy">
              <span className="mapping-step-kicker">04 / Battery rules</span>
              <h3>{editingMappingId
                ? 'Review and adjust the battery rules'
                : useCase === 'battery_cycle'
                  ? 'Set battery thresholds'
                  : 'Set the switch-off threshold'}</h3>
              <p>{useCase === 'battery_cycle'
                ? 'Choose when the switch turns on and off. You can adjust optional behavior below.'
                : 'Choose when the switch turns off. Optional behavior is available below.'}</p>
            </div>
            <div className="mapping-rule-layout">
              <div className="mapping-rule-fields">
                {useCase === 'battery_cycle' && turnOnEnabled && <label className="mapping-rule-field" htmlFor="on-threshold"><span>Turn on at or below</span><span className="mapping-number-input"><input id="on-threshold" type="number" min={0} max={100} required {...form.register('on_threshold', { valueAsNumber: true, required: true, min: 0, max: 100 })} /><b>%</b></span></label>}
                <label className="mapping-rule-field" htmlFor="off-threshold"><span>Turn off at or above</span><span className="mapping-number-input"><input id="off-threshold" type="number" min={0} max={100} required {...form.register('off_threshold', { valueAsNumber: true, required: true, min: 0, max: 100 })} /><b>%</b></span></label>
                <details className="mapping-advanced-rules">
                  <summary>More options</summary>
                  <div className="mapping-advanced-rule-fields">
                    {useCase === 'battery_cycle' && <>
                      <label className="mapping-enable-control" htmlFor="mapping-turn-on-enabled">
                        <input id="mapping-turn-on-enabled" type="checkbox" {...form.register('turn_on_enabled')} />
                        <span><strong>Enable automatic turn-on</strong><small>Turn the switch on when battery reaches the low threshold.</small></span>
                      </label>
                      {!turnOnEnabled && <p className="mapping-advanced-note">Automatic turn-on is disabled.</p>}
                    </>}
                    <label className="mapping-enable-control" htmlFor="mapping-charging-off-enabled">
                      <input id="mapping-charging-off-enabled" type="checkbox" {...form.register('turn_off_when_charging_enabled')} />
                      <span><strong>Turn off at charge completion</strong><small>Use a separate threshold while the device is charging.</small></span>
                    </label>
                    {turnOffWhenChargingEnabled && <label className="mapping-rule-field" htmlFor="charging-off-threshold"><span>Turn off while charging at or above</span><span className="mapping-number-input"><input id="charging-off-threshold" type="number" min={0} max={100} required {...form.register('charging_off_threshold', { valueAsNumber: true, required: true, min: 0, max: 100 })} /><b>%</b></span></label>}
                    <label className="mapping-rule-field" htmlFor="mapping-interval"><span>Minimum time between changes</span><span className="mapping-number-input"><input id="mapping-interval" type="number" min={0} required {...form.register('minimum_state_change_interval', { valueAsNumber: true, required: true, min: 0 })} /><b>sec</b></span></label>
                    <label className="mapping-enable-control" htmlFor="mapping-enabled">
                      <input id="mapping-enabled" type="checkbox" {...form.register('enabled')} />
                      <span><strong>Enable automation now</strong><small>Start controlling the switch as soon as you save.</small></span>
                    </label>
                  </div>
                </details>
              </div>
              <div className="mapping-rule-preview" aria-label={`Battery response: ${useCase === 'battery_cycle' && turnOnEnabled ? `turn on at or below ${onThreshold} percent, ` : ''}turn off at or above ${offThreshold} percent${turnOffWhenChargingEnabled ? ` or while charging at or above ${chargingOffThreshold} percent` : ''}`}>
                <div className="mapping-preview-heading"><BatteryCharging size={18} /><strong>Battery response</strong></div>
                <div className="mapping-battery-track">
                  <span className="mapping-battery-fill" />
                  {useCase === 'battery_cycle' && turnOnEnabled && <span className="mapping-threshold-marker is-on" style={{ left: `${onThreshold}%` }} aria-hidden="true" />}
                  <span className="mapping-threshold-marker is-off" style={{ left: `${offThreshold}%` }} aria-hidden="true" />
                  {turnOffWhenChargingEnabled && <span className="mapping-threshold-marker is-charging" style={{ left: `${chargingOffThreshold}%` }} aria-hidden="true" />}
                </div>
                <div className="mapping-preview-scale"><span>0%</span><span>100%</span></div>
                <div className="mapping-threshold-legend" role="group" aria-label="Automation thresholds">
                  {useCase === 'battery_cycle' && turnOnEnabled && <span className="is-on"><i />Turn on at or below {onThreshold}%</span>}
                  <span className="is-off"><i />Turn off at or above {offThreshold}%</span>
                  {turnOffWhenChargingEnabled && <span className="is-charging"><i />Charging cutoff at or above {chargingOffThreshold}%</span>}
                </div>
                <p>{useCase === 'battery_cycle' && turnOnEnabled ? `On at ${onThreshold}% or below; ` : ''}Off at {offThreshold}% or above{turnOffWhenChargingEnabled ? `, or at ${chargingOffThreshold}% while charging` : ''}.</p>
                {useCase === 'battery_cycle' && turnOnEnabled && offThreshold <= onThreshold && <span className="mapping-threshold-error" role="alert">The turn-off threshold must be higher than the turn-on threshold.</span>}
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
            {step < 4 ? (
              <button type="button" className="btn-primary" onClick={() => void advanceStep()} disabled={(step === 1 && !selectedEndpointId) || (step === 2 && !tenantsMatch) || (step === 3 && !useCase)}>
                Continue <ChevronRight size={16} />
              </button>
            ) : (
              <button
                type="button"
                className="btn-primary"
                disabled={mutation.isPending || !tenantsMatch || !useCase || (turnOnEnabled && offThreshold <= onThreshold)}
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
                  <span className="mapping-use-case-label">{mapping.use_case === 'switch_off_only'
                    ? 'Switch off only'
                    : mapping.use_case === 'switch_and_shutdown'
                      ? 'Switch off + shutdown'
                      : 'Battery-managed cycle'}</span>
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
          {!mappings?.length && <div className="mapping-empty-state"><Cable size={22} aria-hidden="true" /><h3>No mappings yet</h3><p>Use the four steps above to connect a device with a switch.</p></div>}
        </div>
      </section>
    </div>
  )
}
