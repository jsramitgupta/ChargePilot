import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { Activity, CircleHelp } from 'lucide-react'

import { useEffect, useRef, useState } from 'react'

import { NavLink, useSearchParams } from 'react-router-dom'

import { apiFetch } from '../../shared/api'

import { useSession } from '../../shared/hooks'

import { ErrorCard, AgentInstallInstructions } from '../../shared/components'

import type { TenantInfo, AgentReleaseAssets, TenantReportingSettings, RevealedEndpointEnrollment, EndpointEnrollment } from '../../shared/types'

import { formatTimestamp } from '../../shared/lib'

export function AgentSetupPage() {
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const [installGuideOpen, setInstallGuideOpen] = useState(false)
  const installGuideTriggerRef = useRef<HTMLButtonElement | null>(null)
  const tenantId = searchParams.get('tenant_id') ?? ''
  const { data: user } = useSession()
  const isSuperAdmin = user?.role === 'super_admin'
  const canManageEnrollments = isSuperAdmin || user?.role === 'tenant_admin' || user?.role === 'manager'
  const tenantsQuery = useQuery({
    queryKey: ['admin-tenants'],
    queryFn: () => apiFetch<TenantInfo[]>('/api/v1/admin/tenants'),
    enabled: isSuperAdmin,
  })
  const releaseAssetsQuery = useQuery({
    queryKey: ['latest-agent-release-assets'],
    queryFn: () => apiFetch<AgentReleaseAssets>('/api/v1/agent/releases/latest'),
    staleTime: 60 * 60 * 1000,
  })
  const reportingSettingsQuery = useQuery({
    queryKey: ['tenant-reporting-settings', isSuperAdmin ? tenantId : user?.tenant_id],
    queryFn: () => apiFetch<TenantReportingSettings>(
      `/api/v1/admin/tenant-settings${isSuperAdmin ? `?tenant_id=${encodeURIComponent(tenantId)}` : ''}`,
    ),
    enabled: Boolean(canManageEnrollments && (!isSuperAdmin || tenantId)),
  })
  const [reportingScheduleDirty, setReportingScheduleDirty] = useState(false)
  const updateReportingSettingsMutation = useMutation({
    mutationFn: (telemetryIntervalMinutes: number) =>
      apiFetch<TenantReportingSettings>('/api/v1/admin/tenant-settings', {
        method: 'PUT',
        body: JSON.stringify({
          telemetry_interval_minutes: telemetryIntervalMinutes,
          ...(isSuperAdmin ? { tenant_id: tenantId } : {}),
        }),
      }),
    onSuccess: (settings) => {
      queryClient.setQueryData(['tenant-reporting-settings', isSuperAdmin ? tenantId : user?.tenant_id], settings)
      queryClient.invalidateQueries({ queryKey: ['endpoints'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      setReportingScheduleDirty(false)
    },
  })
  const [copyStatus, setCopyStatus] = useState('')
  const [revealedEnrollment, setRevealedEnrollment] = useState<RevealedEndpointEnrollment | null>(null)
  const [clockNow, setClockNow] = useState(Date.now)
  useEffect(() => {
    const timer = window.setInterval(() => setClockNow(Date.now()), 10_000)
    return () => window.clearInterval(timer)
  }, [])
  useEffect(() => {
    if (!revealedEnrollment) return
    const enrollmentId = revealedEnrollment.id
    const delay = Math.max(0, Date.parse(revealedEnrollment.expires_at) - Date.now())
    const timer = window.setTimeout(() => {
      setRevealedEnrollment((current) => current?.id === enrollmentId ? null : current)
    }, delay)
    return () => window.clearTimeout(timer)
  }, [revealedEnrollment])
  const tokenQuery = useQuery({
    queryKey: ['endpoint-enrollments'],
    queryFn: () => apiFetch<EndpointEnrollment[]>('/api/v1/admin/endpoint-enrollments'),
    enabled: Boolean(canManageEnrollments),
    refetchInterval: 30_000,
  })
  const createEnrollmentMutation = useMutation({
    mutationFn: () => apiFetch<{ id: string; enrollment_code: string; expires_at: string }>('/api/v1/admin/endpoint-enrollments', {
      method: 'POST',
      body: JSON.stringify(tenantId ? { tenant_id: tenantId } : {}),
    }),
    onSuccess: ({ id, enrollment_code, expires_at }) => {
      setRevealedEnrollment({ id, enrollment_code, expires_at })
      setCopyStatus('')
      void queryClient.invalidateQueries({ queryKey: ['endpoint-enrollments'] })
    },
  })
  const revealEnrollmentMutation = useMutation({
    mutationFn: (enrollmentId: string) =>
      apiFetch<RevealedEndpointEnrollment>(`/api/v1/admin/endpoint-enrollments/${enrollmentId}/token`),
    onSuccess: (enrollment) => {
      setRevealedEnrollment(enrollment)
      setCopyStatus('')
    },
  })
  const revokeEnrollmentMutation = useMutation({
    mutationFn: (enrollmentId: string) =>
      apiFetch<void>(`/api/v1/admin/endpoint-enrollments/${enrollmentId}`, { method: 'DELETE' }),
    onSuccess: (_, enrollmentId) => {
      setRevealedEnrollment((current) => current?.id === enrollmentId ? null : current)
      void queryClient.invalidateQueries({ queryKey: ['endpoint-enrollments'] })
    },
  })
  const activeEnrollments = (tokenQuery.data ?? []).filter((token) => Date.parse(token.expires_at) > clockNow)
  const tokenLimitReached = activeEnrollments.length >= 5
  const revealedEnrollmentIsListed = activeEnrollments.some((token) => token.id === revealedEnrollment?.id)
  const copyText = async (text: string, copiedMessage: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopyStatus(copiedMessage)
    } catch {
      setCopyStatus('Copy was blocked. Select the text and copy it manually.')
    }
  }
  const agentPackages = [
    { platform: 'Windows', format: '.EXE', description: 'Windows service and enrollment window', matches: (name: string) => name.toLowerCase() === 'chargepilotagent.exe' },
    { platform: 'macOS', format: '.DMG', description: 'Menu-bar app for macOS', matches: (name: string) => name.toLowerCase().endsWith('.dmg') },
    { platform: 'iPhone and iPad', format: '.IPA', description: 'iOS app package for provisioned devices', matches: (name: string) => name.toLowerCase().endsWith('.ipa') },
    { platform: 'Android', format: '.APK', description: 'Android app package', matches: (name: string) => name.toLowerCase().endsWith('.apk') },
  ]
  return <div className="space-y-6">
    <header className="setup-page-header">
      <div>
        <p className="page-context">Endpoint setup</p>
        <h1>Enroll a device</h1>
        <p>Create one private token for your workspace, then use it to enroll devices across supported platforms.</p>
      </div>
      <button type="button" className="secondary-btn" onClick={(event) => {
        installGuideTriggerRef.current = event.currentTarget
        setInstallGuideOpen(true)
      }}>
        <CircleHelp size={16} aria-hidden="true" />Install instructions
      </button>
    </header>
    {isSuperAdmin && <section className="panel max-w-3xl p-5 sm:p-6">
      <h2 className="text-lg font-bold text-slate-900">Choose a workspace</h2>
      <p className="mt-1 text-sm text-slate-600">Every device enrolled with this token will belong to the selected workspace.</p>
      {tenantsQuery.error && <div className="mt-3"><ErrorCard message={tenantsQuery.error.message} /></div>}
      <label className="label mt-4" htmlFor="enrollment-tenant">Workspace
        <select id="enrollment-tenant" className="field mt-1" value={tenantId} onChange={(event) => {
          setRevealedEnrollment(null)
          setSearchParams(event.target.value ? { tenant_id: event.target.value } : {})
        }}>
          <option value="">Select a workspace</option>
          {(tenantsQuery.data ?? []).map((tenant) => <option key={tenant.id} value={tenant.id}>{tenant.name}</option>)}
        </select>
      </label>
    </section>}
    {canManageEnrollments && <section className="panel max-w-3xl p-5 sm:p-6" aria-labelledby="reporting-schedule-title">
      <div className="flex items-start gap-3">
        <div className="rounded-lg bg-[var(--surface-muted)] p-2 text-[var(--leaf)]"><Activity size={18} aria-hidden="true" /></div>
        <div>
          <h2 id="reporting-schedule-title" className="text-lg font-bold text-[var(--ink)]">Workspace reporting schedule</h2>
          <p className="mt-1 max-w-xl text-sm leading-6 text-[var(--muted)]">Set how often supported agents should send a battery and system-health report. The backend applies the new target when each agent next checks in.</p>
        </div>
      </div>
      {reportingSettingsQuery.error && <div className="mt-4"><ErrorCard message={reportingSettingsQuery.error.message} /></div>}
      {updateReportingSettingsMutation.error && <div className="mt-4"><ErrorCard message={updateReportingSettingsMutation.error.message} /></div>}
      {isSuperAdmin && !tenantId
        ? <p className="mt-4 text-sm text-[var(--muted)]">Select a workspace above to review its reporting target.</p>
        : reportingSettingsQuery.isLoading
          ? <p className="mt-4 text-sm text-[var(--muted)]">Loading reporting schedule…</p>
          : reportingSettingsQuery.data && <form className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end" onSubmit={(event) => {
            event.preventDefault()
            const interval = Number(new FormData(event.currentTarget).get('telemetry_interval_minutes'))
            updateReportingSettingsMutation.mutate(interval)
          }}>
            <label className="field-group min-w-0 flex-1" htmlFor="reporting-interval">
              <span>Send a report every</span>
              <select
                id="reporting-interval"
                name="telemetry_interval_minutes"
                className="field"
                key={`${reportingSettingsQuery.data.tenant_id}-${reportingSettingsQuery.data.telemetry_interval_minutes}`}
                defaultValue={reportingSettingsQuery.data.telemetry_interval_minutes}
                onChange={() => setReportingScheduleDirty(true)}
              >
                {[5, 10, 15, 30, 60, 120, 360, 720, 1440].map((minutes) => <option key={minutes} value={minutes}>{minutes < 60 ? `${minutes} minutes` : minutes % 60 === 0 ? `${minutes / 60} hour${minutes === 60 ? '' : 's'}` : `${minutes} minutes`}</option>)}
              </select>
            </label>
            <button type="submit" className="btn-primary" disabled={updateReportingSettingsMutation.isPending || !reportingScheduleDirty}>
              {updateReportingSettingsMutation.isPending ? 'Saving schedule…' : 'Save schedule'}
            </button>
          </form>}
      <p className="mt-3 text-xs leading-5 text-[var(--muted)]">Windows and macOS follow the target after a successful report. Android background work has a 15-minute operating-system minimum. iOS reports when opened or triggered by Shortcuts; iOS does not allow ChargePilot to guarantee a recurring background interval. Mobile reports can be delayed.</p>
      {updateReportingSettingsMutation.isSuccess && <p className="mt-3 text-sm text-[var(--leaf)]" role="status">Schedule saved. Enrolled agents will adopt it after their next accepted report.</p>}
    </section>}
    {createEnrollmentMutation.error && <ErrorCard message={createEnrollmentMutation.error.message} />}
    {revealEnrollmentMutation.error && <ErrorCard message={revealEnrollmentMutation.error.message} />}
    {revokeEnrollmentMutation.error && <ErrorCard message={revokeEnrollmentMutation.error.message} />}
    {revealedEnrollment && !revealedEnrollmentIsListed && Date.parse(revealedEnrollment.expires_at) > clockNow && <div className="panel max-w-3xl border-l-4 border-[var(--copper)] p-4 sm:p-5">
      <p className="text-sm font-semibold text-[var(--ink)]">Enrollment token · expires {formatTimestamp(revealedEnrollment.expires_at)}</p>
      <code className="mt-3 block break-all rounded-lg border border-[var(--line)] bg-[var(--surface-muted)] p-3 font-mono text-sm text-[var(--ink)]">{revealedEnrollment.enrollment_code}</code>
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" className="btn-secondary" onClick={() => void copyText(revealedEnrollment.enrollment_code, 'Enrollment token copied.')}>Copy token</button>
        <button type="button" className="btn-secondary" onClick={() => setRevealedEnrollment(null)}>Hide token</button>
        <button type="button" className="danger-btn small-btn" disabled={revokeEnrollmentMutation.isPending} onClick={() => revokeEnrollmentMutation.mutate(revealedEnrollment.id)}>Revoke</button>
      </div>
      <p className="mt-2 min-h-5 text-xs text-[var(--muted)]" role="status">{copyStatus}</p>
    </div>}
    {canManageEnrollments && <section className="panel max-w-3xl p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900">Enrollment token</h2>
          <p className="mt-2 max-w-xl text-sm leading-6 text-slate-600">Create a token for any enabled platform. Reveal or hide it during its 24-hour lifetime, or revoke it at any time.</p>
          <p className="mt-2 text-sm font-semibold text-[var(--ink)]" aria-live="polite">
            Active tokens: {tokenQuery.isLoading ? 'Loading…' : `${activeEnrollments.length} of 5`}
          </p>
        </div>
        <button
          type="button"
          className="btn-primary"
          disabled={createEnrollmentMutation.isPending || tokenQuery.isLoading || tokenQuery.isError || tokenLimitReached || (isSuperAdmin && !tenantId)}
          onClick={() => createEnrollmentMutation.mutate()}
        >
          {createEnrollmentMutation.isPending ? 'Creating token…' : 'Create enrollment token'}
        </button>
      </div>
      {isSuperAdmin && !tenantId && <p className="mt-3 text-sm text-amber-800">Select a workspace before creating a token.</p>}
      {tokenLimitReached && <p className="mt-3 text-sm text-[var(--muted)]">Revoke a token or wait for one to expire before creating another.</p>}
      {tokenQuery.error && <div className="mt-4"><ErrorCard message={tokenQuery.error.message} /></div>}
      {tokenQuery.isLoading && <p className="mt-4 text-sm text-[var(--muted)]">Loading enrollment tokens…</p>}
      {!tokenQuery.isLoading && tokenQuery.data && <div className="mt-6 border-t border-[var(--line)] pt-5">
        <h3 className="font-semibold text-[var(--ink)]">Your active tokens</h3>
        {activeEnrollments.length ? <ul className="mt-3 divide-y divide-[var(--line)]">
          {activeEnrollments.map((token) => {
            const revealed = revealedEnrollment?.id === token.id
            const revealPending = revealEnrollmentMutation.isPending && revealEnrollmentMutation.variables === token.id
            return <li key={token.id} className="py-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-medium text-[var(--ink)]">Expires {formatTimestamp(token.expires_at)}</p>
                  <p className="mt-1 text-xs text-[var(--muted)]">Created {formatTimestamp(token.created_at)} · {token.enrollment_count} device{token.enrollment_count === 1 ? '' : 's'} enrolled · {token.tenant_name}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    className="btn-secondary"
                    disabled={revealEnrollmentMutation.isPending || Date.parse(token.expires_at) <= clockNow}
                    aria-expanded={revealed}
                    onClick={() => {
                      if (revealed) {
                        setRevealedEnrollment(null)
                        setCopyStatus('')
                      } else {
                        setRevealedEnrollment(null)
                        revealEnrollmentMutation.mutate(token.id)
                      }
                    }}
                  >
                    {revealed ? 'Hide token' : revealPending ? 'Loading…' : 'Show token'}
                  </button>
                  <button type="button" className="danger-btn small-btn" disabled={revokeEnrollmentMutation.isPending} onClick={() => revokeEnrollmentMutation.mutate(token.id)}>Revoke</button>
                </div>
              </div>
              {revealed && revealedEnrollment && Date.parse(revealedEnrollment.expires_at) > clockNow && <div className="mt-3 rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] p-3 sm:p-4">
                <p className="text-xs font-medium text-[var(--muted)]">This token is available until it expires.</p>
                <code className="mt-2 block break-all rounded-lg border border-[var(--line)] bg-[var(--surface)] p-3 font-mono text-sm text-[var(--ink)]">{revealedEnrollment.enrollment_code}</code>
                <button type="button" className="btn-secondary mt-3" onClick={() => void copyText(revealedEnrollment.enrollment_code, 'Enrollment token copied.')}>Copy token</button>
                <p className="mt-2 min-h-5 text-xs text-[var(--muted)]" role="status">{copyStatus}</p>
              </div>}
            </li>
          })}
        </ul> : <p className="mt-2 text-sm text-[var(--muted)]">No active tokens. Expired and revoked tokens are hidden.</p>}
      </div>}
    </section>}
    <section className="agent-package-section" aria-labelledby="agent-package-title">
      <div className="agent-package-heading">
        <div>
          <h2 id="agent-package-title">Install a ChargePilot agent</h2>
          <p>Choose the installer for the device you want to enroll.</p>
        </div>
        {releaseAssetsQuery.data && <span>Release {releaseAssetsQuery.data.tag}</span>}
      </div>
      {releaseAssetsQuery.isLoading && <p className="agent-package-message">Loading the latest agent packages…</p>}
      {releaseAssetsQuery.error && <div className="agent-package-error" role="alert">
        <p>{releaseAssetsQuery.error.message}</p>
        <button type="button" className="agent-release-retry" disabled={releaseAssetsQuery.isFetching} onClick={() => { void releaseAssetsQuery.refetch() }}>
          {releaseAssetsQuery.isFetching ? 'Retrying…' : 'Retry package lookup'}
        </button>
      </div>}
      {releaseAssetsQuery.data && <div className="agent-package-grid">
        {agentPackages.map((agentPackage) => {
          const asset = releaseAssetsQuery.data.assets.find((candidate) => agentPackage.matches(candidate.name))
          return <article className="agent-package-card" key={agentPackage.format}>
            <div className="agent-package-format" aria-hidden="true">{agentPackage.format}</div>
            <h3>{agentPackage.platform}</h3>
            <p>{agentPackage.description}</p>
            {asset
              ? <a className="btn-secondary" href={asset.url} download>{`Download ${agentPackage.format}`}</a>
              : <span className="agent-package-message">Not available in this release.</span>}
            {asset && <span className="agent-package-filename">{asset.name}</span>}
          </article>
        })}
      </div>}
      {!canManageEnrollments && <p className="agent-enrollment-note">An administrator must create an enrollment token for this workspace.</p>}
      <p className="agent-enrollment-note">After the first report, review devices on the <NavLink to="/endpoints">Endpoints</NavLink> page.</p>
    </section>
    {installGuideOpen && <AgentInstallInstructions onClose={() => {
      setInstallGuideOpen(false)
      window.requestAnimationFrame(() => installGuideTriggerRef.current?.focus())
    }} />}
  </div>
}
