import { useState } from 'react'

import type { FormEvent } from 'react'

import type { Device, DeviceMeterSettings, MeterUnitScale, MeterCandidate } from '../../shared/types'

import { meterScaleParts, meterMultiplier, formatPower, formatTimestamp } from '../../shared/lib'

import { discoverMeterReadings } from '../../shared/api'

export function DeviceMeterPanel({
  device,
  isSaving,
  currentMonth,
  now,
  onSave,
}: {
  device: Device
  isSaving: boolean
  currentMonth: string
  now: number
  onSave: (settings: DeviceMeterSettings) => void
}) {
  const powerUnits: MeterUnitScale[] = [
    { unit: 'watts', multiplier: 1 },
    { unit: 'kilowatts', multiplier: 1000 },
  ]
  const energyUnits: MeterUnitScale[] = [
    { unit: 'wh', multiplier: 0.001 },
    { unit: 'kwh', multiplier: 1 },
  ]
  const initialPowerScale = meterScaleParts(device.power_multiplier ?? 1, powerUnits)
  const initialEnergyScale = meterScaleParts(device.energy_multiplier ?? 0.001, energyUnits)
  const [powerDpId, setPowerDpId] = useState(device.power_dp_id ?? '')
  const [powerMultiplier, setPowerMultiplier] = useState(String(device.power_multiplier ?? 1))
  const [powerUnit, setPowerUnit] = useState(initialPowerScale.unit)
  const [powerDecimalPlaces, setPowerDecimalPlaces] = useState(initialPowerScale.decimalPlaces)
  const [powerCustomBaseScale, setPowerCustomBaseScale] = useState(initialPowerScale.customBaseScale)
  const [energyDpId, setEnergyDpId] = useState(device.energy_dp_id ?? '')
  const [energyMultiplier, setEnergyMultiplier] = useState(String(device.energy_multiplier ?? 0.001))
  const [energyUnit, setEnergyUnit] = useState(initialEnergyScale.unit)
  const [energyDecimalPlaces, setEnergyDecimalPlaces] = useState(initialEnergyScale.decimalPlaces)
  const [energyCustomBaseScale, setEnergyCustomBaseScale] = useState(initialEnergyScale.customBaseScale)
  const [energyCounterType, setEnergyCounterType] = useState<DeviceMeterSettings['energy_counter_type']>(
    device.energy_counter_type ?? 'cumulative',
  )
  const [validationMessage, setValidationMessage] = useState('')
  const [candidates, setCandidates] = useState<MeterCandidate[]>([])
  const [isDiscovering, setIsDiscovering] = useState(false)
  const [discoveryMessage, setDiscoveryMessage] = useState('')
  const [discoveryError, setDiscoveryError] = useState('')

  const updatePowerUnit = (unit: string) => {
    const baseScale = Number(powerMultiplier) * (10 ** Number(powerDecimalPlaces))
    const customBaseScale = Number.isFinite(baseScale) && baseScale > 0
      ? String(baseScale)
      : powerCustomBaseScale
    if (unit === 'custom' && customBaseScale !== powerCustomBaseScale) {
      setPowerCustomBaseScale(customBaseScale)
    }
    setPowerUnit(unit)
    setPowerMultiplier(String(meterMultiplier(
      unit,
      powerDecimalPlaces,
      unit === 'custom' ? customBaseScale : powerCustomBaseScale,
      powerUnits,
    )))
  }

  const updatePowerDecimalPlaces = (decimalPlaces: string) => {
    setPowerDecimalPlaces(decimalPlaces)
    setPowerMultiplier(String(meterMultiplier(powerUnit, decimalPlaces, powerCustomBaseScale, powerUnits)))
  }

  const updateEnergyUnit = (unit: string) => {
    const baseScale = Number(energyMultiplier) * (10 ** Number(energyDecimalPlaces))
    const customBaseScale = Number.isFinite(baseScale) && baseScale > 0
      ? String(baseScale)
      : energyCustomBaseScale
    if (unit === 'custom' && customBaseScale !== energyCustomBaseScale) {
      setEnergyCustomBaseScale(customBaseScale)
    }
    setEnergyUnit(unit)
    setEnergyMultiplier(String(meterMultiplier(
      unit,
      energyDecimalPlaces,
      unit === 'custom' ? customBaseScale : energyCustomBaseScale,
      energyUnits,
    )))
  }

  const updateEnergyDecimalPlaces = (decimalPlaces: string) => {
    setEnergyDecimalPlaces(decimalPlaces)
    setEnergyMultiplier(String(meterMultiplier(energyUnit, decimalPlaces, energyCustomBaseScale, energyUnits)))
  }

  const updatePowerCustomBaseScale = (value: string) => {
    setPowerUnit('custom')
    setPowerCustomBaseScale(value)
    const baseScale = Number(value)
    setPowerMultiplier(Number.isFinite(baseScale) && baseScale > 0
      ? String(baseScale * (10 ** -Number(powerDecimalPlaces)))
      : value)
  }

  const updateEnergyCustomBaseScale = (value: string) => {
    setEnergyUnit('custom')
    setEnergyCustomBaseScale(value)
    const baseScale = Number(value)
    setEnergyMultiplier(Number.isFinite(baseScale) && baseScale > 0
      ? String(baseScale * (10 ** -Number(energyDecimalPlaces)))
      : value)
  }

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
  const powerAge = device.meter_power_sample_at
    ? now - Date.parse(device.meter_power_sample_at)
    : Number.POSITIVE_INFINITY
  const hasCurrentPower = device.meter_power_watts != null
    && powerAge >= 0
    && powerAge <= 5 * 60 * 1000
  const powerReading = hasCurrentPower && device.meter_power_watts != null
    ? formatPower(device.meter_power_watts)
    : device.power_dp_id ? 'Waiting for a fresh reading' : 'Not configured'
  const hasCurrentMonthEnergy = device.meter_energy_month_kwh != null
    && device.meter_energy_sample_at != null
    && device.meter_month_key === currentMonth
  const energyReading = hasCurrentMonthEnergy && device.meter_energy_month_kwh != null
    ? `${device.meter_energy_month_kwh.toFixed(2)} kWh`
    : device.energy_dp_id ? 'No current-month reading' : 'Not configured'
  const powerRawExample = candidates.find((candidate) => candidate.id === powerDpId)?.sample ?? 591
  const energyRawExample = candidates.find((candidate) => candidate.id === energyDpId)?.sample ?? 591

  return (
    <section className="switch-meter-panel" aria-label={`Energy readings for ${device.name}`}>
      <div className="switch-meter-readings">
        <div>
          <span>Live power</span>
          <strong>{powerReading}</strong>
        </div>
        <div>
          <span>Energy this month (UTC)</span>
          <strong>{energyReading}</strong>
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
          </>}
          <div>
            <label htmlFor={`meter-power-units-${device.id}`}>Power reading is in</label>
            <select id={`meter-power-units-${device.id}`} className="field" value={powerUnit} onChange={(event) => updatePowerUnit(event.target.value)}>
              <option value="watts">Watts (W)</option>
              <option value="kilowatts">Kilowatts (kW)</option>
              <option value="custom">Custom scale</option>
            </select>
          </div>
          <div>
            <label htmlFor={`meter-energy-units-${device.id}`}>Energy reading is in</label>
            <select id={`meter-energy-units-${device.id}`} className="field" value={energyUnit} onChange={(event) => updateEnergyUnit(event.target.value)}>
              <option value="wh">Watt-hours (Wh)</option>
              <option value="kwh">Kilowatt-hours (kWh)</option>
              <option value="custom">Custom scale</option>
            </select>
          </div>
          <div>
            <label htmlFor={`meter-power-decimals-${device.id}`}>Decimal places in the power reading</label>
            <select id={`meter-power-decimals-${device.id}`} className="field" value={powerDecimalPlaces} onChange={(event) => updatePowerDecimalPlaces(event.target.value)}>
              <option value="0">None ({powerRawExample.toLocaleString()} stays unchanged)</option>
              {Array.from({ length: 6 }, (_, index) => index + 1).map((places) => (
                <option key={places} value={places}>{places} ({`${powerRawExample.toLocaleString()} becomes ${(powerRawExample / (10 ** places)).toFixed(places)}`})</option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor={`meter-energy-decimals-${device.id}`}>Decimal places in the energy reading</label>
            <select id={`meter-energy-decimals-${device.id}`} className="field" value={energyDecimalPlaces} onChange={(event) => updateEnergyDecimalPlaces(event.target.value)}>
              <option value="0">None ({energyRawExample.toLocaleString()} stays unchanged)</option>
              {Array.from({ length: 6 }, (_, index) => index + 1).map((places) => (
                <option key={places} value={places}>{places} ({`${energyRawExample.toLocaleString()} becomes ${(energyRawExample / (10 ** places)).toFixed(places)}`})</option>
              ))}
            </select>
          </div>
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
            <p className="switch-meter-help">Use these fields when your switch documentation gives you its reading IDs or a custom base scale. Decimal places are applied after this scale.</p>
            <div className="switch-meter-form switch-meter-advanced-fields">
              <div>
                <label htmlFor={`meter-power-dp-${device.id}`}>Power reading ID</label>
                <input id={`meter-power-dp-${device.id}`} className="field" value={powerDpId} onChange={(event) => setPowerDpId(event.target.value)} />
              </div>
              <div>
                <label htmlFor={`meter-power-scale-${device.id}`}>Power base scale to watts</label>
                <input id={`meter-power-scale-${device.id}`} className="field" type="number" min="0.000000001" step="any" value={powerUnit === 'custom' ? powerCustomBaseScale : String(powerUnits.find((unit) => unit.unit === powerUnit)?.multiplier ?? '')} onChange={(event) => updatePowerCustomBaseScale(event.target.value)} />
              </div>
              <div>
                <label htmlFor={`meter-energy-dp-${device.id}`}>Energy reading ID</label>
                <input id={`meter-energy-dp-${device.id}`} className="field" value={energyDpId} onChange={(event) => setEnergyDpId(event.target.value)} />
              </div>
              <div>
                <label htmlFor={`meter-energy-scale-${device.id}`}>Energy base scale to kWh</label>
                <input id={`meter-energy-scale-${device.id}`} className="field" type="number" min="0.000000001" step="any" value={energyUnit === 'custom' ? energyCustomBaseScale : String(energyUnits.find((unit) => unit.unit === energyUnit)?.multiplier ?? '')} onChange={(event) => updateEnergyCustomBaseScale(event.target.value)} />
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
