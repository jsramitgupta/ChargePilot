import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ChevronRight, Pencil, ShieldCheck } from 'lucide-react'

import { useState } from 'react'

import { useSession } from '../../shared/hooks'

import { apiFetch } from '../../shared/api'

import { type Connector, type TenantInfo } from '../../shared/types'

import { LoadingCard, ErrorCard, PageHeader } from '../../shared/components'

import { API_BASE_URL } from '../../shared/config'

import { formatTimestamp } from '../../shared/lib'

export function ConnectorsPage() {
  const queryClient = useQueryClient()
  const { data: user } = useSession()
  const [name, setName] = useState('')
  const [editingConnectorId, setEditingConnectorId] = useState<string | null>(null)
  const [editedConnectorName, setEditedConnectorName] = useState('')
  const [tenantId, setTenantId] = useState('')
  const [enrollmentCode, setEnrollmentCode] = useState('')
  const [copyStatus, setCopyStatus] = useState('')
  const [deploymentMode, setDeploymentMode] = useState<'docker' | 'windows'>('docker')

  const connectorsQuery = useQuery({
    queryKey: ['connectors'],
    queryFn: () => apiFetch<Connector[]>('/api/v1/connectors'),
  })
  const tenantsQuery = useQuery({
    queryKey: ['admin-tenants'],
    queryFn: () => apiFetch<TenantInfo[]>('/api/v1/admin/tenants'),
    enabled: user?.role === 'super_admin',
  })
  const createMutation = useMutation({
    mutationFn: () => apiFetch<{ enrollment_code: string }>('/api/v1/connectors/enrollment-codes', {
      method: 'POST',
      body: JSON.stringify({ name, tenant_id: tenantId || undefined }),
    }),
    onSuccess: ({ enrollment_code }) => {
      setEnrollmentCode(enrollment_code)
      setName('')
      setTenantId('')
      queryClient.invalidateQueries({ queryKey: ['connectors'] })
    },
  })
  const renameMutation = useMutation({
    mutationFn: ({ connectorId, name }: { connectorId: string; name: string }) =>
      apiFetch<{ id: string; name: string }>(`/api/v1/connectors/${connectorId}`, {
        method: 'PATCH',
        body: JSON.stringify({ name }),
      }),
    onSuccess: () => {
      setEditingConnectorId(null)
      setEditedConnectorName('')
      queryClient.invalidateQueries({ queryKey: ['connectors'] })
    },
  })
  const revokeMutation = useMutation({
    mutationFn: (connectorId: string) => apiFetch<{ status: string }>(`/api/v1/connectors/${connectorId}/revoke`, { method: 'POST' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['connectors'] }),
  })
  const deleteMutation = useMutation({
    mutationFn: (connectorId: string) => apiFetch<void>(`/api/v1/connectors/${connectorId}`, { method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['connectors'] }),
  })

  if (connectorsQuery.isLoading || tenantsQuery.isLoading) return <LoadingCard />
  if (connectorsQuery.error) return <ErrorCard message={connectorsQuery.error.message} />
  if (tenantsQuery.error) return <ErrorCard message={tenantsQuery.error.message} />
  const connectors = connectorsQuery.data ?? []
  const tenants = tenantsQuery.data ?? []
  const actionError = createMutation.error ?? renameMutation.error ?? revokeMutation.error ?? deleteMutation.error
  const canManageConnectors = user?.role === 'super_admin' || user?.role === 'tenant_admin' || user?.role === 'manager'
  const connectorServerUrl = (API_BASE_URL || window.location.origin).replace(/\/+$/, '')
  const windowsInstallCommand = `.\\ChargePilotConnector.exe install --server-url "${connectorServerUrl}"`
  const onlineCount = connectors.filter((connector) => connector.is_active && connector.is_enrolled && connector.is_online).length
  const waitingCount = connectors.filter((connector) => connector.is_active && !connector.is_enrolled).length
  const offlineCount = connectors.filter((connector) => connector.is_active && connector.is_enrolled && !connector.is_online).length
  const composeYaml = `services:
  chargepilot-connector:
    image: endusercompute/chargepilot-connector:sha-f9c01a016d3a2e706c8a50a12c3aa5ae73da38b2
    container_name: chargepilot-connector
    network_mode: host
    restart: unless-stopped
    read_only: true
    tmpfs:
      - /tmp:rw,noexec,nosuid,size=16m
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
    environment:
      CHARGEPILOT_CONNECTOR_SERVER_URL: ${connectorServerUrl}
      CHARGEPILOT_CONNECTOR_ENROLLMENT_CODE: \${CHARGEPILOT_CONNECTOR_ENROLLMENT_CODE:-}
      CHARGEPILOT_CONNECTOR_CONFIG: /data/connector-config.json
    volumes:
      - connector-data:/data

volumes:
  connector-data:`

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Remote device networks" title="Site connectors" description="Run one connector on each switch network. It keeps Tuya discovery and control on site, using outbound WebSocket notifications and HTTPS for durable commands." />
      <section className="connector-readiness" aria-label="Connector setup overview">
        <p><strong>Before you start</strong> Choose an always-on computer on the switch LAN. It needs outbound HTTPS and local Tuya access; no inbound Internet port is required.</p>
        <ul>
          <li><span className="connector-readiness-dot is-online" aria-hidden="true" />{onlineCount} online</li>
          <li><span className="connector-readiness-dot is-waiting" aria-hidden="true" />{waitingCount} awaiting enrollment</li>
          <li><span className="connector-readiness-dot is-offline" aria-hidden="true" />{offlineCount} offline</li>
        </ul>
      </section>
      {actionError && <ErrorCard message={actionError.message} />}
      <section className="connector-deploy-guide" aria-labelledby="connector-deploy-title">
        <div className="connector-deploy-heading">
          <div>
            <h2 id="connector-deploy-title">Run a site connector</h2>
            <p>Choose Docker Compose for Linux hosts or a Windows executable installed as a service.</p>
          </div>
          <div className="connector-network-path" aria-label="Connector network path">
            <span>Tuya LAN</span><ChevronRight size={15} aria-hidden="true" /><span>Connector</span><ChevronRight size={15} aria-hidden="true" /><span>HTTPS</span>
          </div>
        </div>
        <p className="connector-prerequisite"><ShieldCheck size={16} aria-hidden="true" /><span>The host must stay powered on, reach ChargePilot over HTTPS, and reach switches on the local network using Tuya traffic (UDP 6666, 6667, 7000; TCP 6668).</span></p>
        <div className="mb-4 flex flex-wrap gap-2">
          <button type="button" aria-pressed={deploymentMode === 'docker'} className={deploymentMode === 'docker' ? 'btn-primary' : 'btn-secondary'} onClick={() => setDeploymentMode('docker')}>Docker Compose</button>
          <button type="button" aria-pressed={deploymentMode === 'windows'} className={deploymentMode === 'windows' ? 'btn-primary' : 'btn-secondary'} onClick={() => setDeploymentMode('windows')}>Windows executable</button>
        </div>
        {deploymentMode === 'docker' ? <div className="connector-deploy-steps" aria-live="polite">
          <article className="connector-deploy-step">
            <span className="connector-step-number">1</span>
            <div><h3>Prepare the connector host</h3><p>Use an always-on Linux computer, NAS, or Raspberry Pi on the switch LAN with Docker Compose installed.</p></div>
          </article>
          <article className="connector-deploy-step">
            <span className="connector-step-number">2</span>
            <div><h3>Create a one-time code</h3><p>Name the connector for this switch network. The code appears once, expires in 15 minutes, and can enroll only one connector.</p>{canManageConnectors && <a href="#connector-enrollment-form" className="connector-step-link">Go to connector setup</a>}</div>
          </article>
          <article className="connector-deploy-step">
            <span className="connector-step-number">3</span>
            <div>
              <h3>Start the published Docker image</h3>
              <p>Save as <code>docker-compose.yml</code> on the connector host. This uses the published image, connects to this ChargePilot server, and creates persistent Docker storage.</p>
              <p>For a private image, sign in with <code>docker login</code> using an account with read access before the first pull. Keep the registry token out of this file; it is separate from the one-time enrollment code.</p>
              <p><a href="https://docs-chargepilot.endusercompute.in/guides/private-connector-image-access">Read the private connector image access guide</a>.</p>
              <pre className="connector-command"><code>{composeYaml}</code></pre>
              <button type="button" className="btn-secondary mt-2" onClick={async () => {
                try {
                  await navigator.clipboard.writeText(composeYaml)
                  setCopyStatus('Compose YAML copied.')
                } catch {
                  setCopyStatus('Copy was blocked. Select the YAML and copy it manually.')
                }
              }}>Copy Compose YAML</button>
              <p className="mt-1 text-xs text-slate-500" role="status">{copyStatus}</p>
              <p className="connector-step-note">Run this in Bash beside the Compose file: <code>read -rsp 'One-time ChargePilot code: ' CHARGEPILOT_CONNECTOR_ENROLLMENT_CODE &amp;&amp; echo &amp;&amp; export CHARGEPILOT_CONNECTOR_ENROLLMENT_CODE &amp;&amp; docker compose up -d &amp;&amp; unset CHARGEPILOT_CONNECTOR_ENROLLMENT_CODE</code>. The code is not added to shell history, but remains visible in Docker metadata until enrollment completes and the container is recreated without it. The saved credential remains in the Docker-managed volume. Allow local Tuya traffic (UDP 6666, 6667, 7000; TCP 6668).</p>
            </div>
          </article>
        </div> : <div className="connector-deploy-steps" aria-live="polite">
          <article className="connector-deploy-step">
            <span className="connector-step-number">1</span>
            <div>
              <h3>Download the Windows executable</h3>
              <p>Use an always-on Windows computer connected to the switch LAN. Download the self-contained connector; no separate Python installation is required.</p>
              <a className="connector-step-link" href={`${connectorServerUrl}/connectors/ChargePilotConnector.exe`}>Download ChargePilotConnector.exe</a>
              <p className="connector-step-note">The current build is not code-signed. Windows SmartScreen may show an unknown-publisher warning; only continue if you trust this ChargePilot deployment.</p>
            </div>
          </article>
          <article className="connector-deploy-step">
            <span className="connector-step-number">2</span>
            <div>
              <h3>Install and enroll the Windows service</h3>
              <p>Open PowerShell as Administrator in the download folder and run the command below. The installer prompts for the one-time code without placing it in shell history or process arguments.</p>
              <pre className="connector-command"><code>{windowsInstallCommand}</code></pre>
              <button type="button" className="btn-secondary mt-2" onClick={async () => {
                try {
                  await navigator.clipboard.writeText(windowsInstallCommand)
                  setCopyStatus('Windows install command copied.')
                } catch {
                  setCopyStatus('Copy was blocked. Select the command and copy it manually.')
                }
              }}>Copy install command</button>
              <p className="mt-1 text-xs text-slate-500" role="status">{copyStatus}</p>
              <p className="connector-step-note">The service starts automatically at boot as the restricted LocalService account. Its connector credential is stored under <code>%ProgramData%\ChargePilot</code>, accessible to SYSTEM, Administrators, and the service identity. Rotating logs are stored under <code>%ProgramData%\ChargePilot\logs</code>. Windows must allow outbound HTTPS/WSS plus local Tuya traffic (UDP 6666, 6667, 7000; TCP 6668).</p>
            </div>
          </article>
          <article className="connector-deploy-step">
            <span className="connector-step-number">3</span>
            <div>
              <h3>Check, update, or remove the service</h3>
              <p>Use an elevated PowerShell window to check the service with <code>.\ChargePilotConnector.exe status</code>; the executable also supports <code>start</code>, <code>stop</code>, and <code>uninstall</code>.</p>
              <p>To update, stop the service, replace <code>%ProgramFiles%\ChargePilot\Connector\ChargePilotConnector.exe</code> with a newly downloaded build, then start it again. Before removing a connector permanently, revoke it on this page; uninstall removes the local credential but does not revoke the server-side connector.</p>
            </div>
          </article>
        </div>}
        <p className="connector-finish-note">Setup is complete when this page shows the connector online. Then open <strong>Switches</strong> to scan this LAN and assign the discovered switches to it.</p>
      </section>
      {enrollmentCode && (
        <section className="rounded-2xl border border-amber-300 bg-amber-50 p-5" aria-labelledby="enrollment-code-title">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div><h2 id="enrollment-code-title" className="text-lg font-bold text-amber-950">One-time enrollment code</h2><p className="mt-1 text-sm text-amber-900">Use it on the connector computer within 15 minutes. It is shown only once; do not share or commit it.</p></div>
            <button type="button" className="btn-secondary" onClick={async () => {
              try {
                await navigator.clipboard.writeText(enrollmentCode)
                setCopyStatus('Enrollment code copied.')
              } catch {
                setCopyStatus('Copy was blocked. Select the code and copy it manually.')
              }
            }}>Copy code</button>
          </div>
          <output className="mt-4 block select-all break-all rounded-lg border border-amber-200 bg-white px-4 py-4 font-mono text-lg font-semibold tracking-wider text-slate-900">{enrollmentCode}</output>
          <p className="mt-2 min-h-4 text-xs text-amber-900" role="status">{copyStatus}</p>
        </section>
      )}
      <div className="grid gap-5 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
        {canManageConnectors && <section className="connector-create-panel" aria-labelledby="connector-enrollment-form">
          <h2 className="text-lg font-bold text-[var(--ink)]" id="connector-enrollment-form">Add a site connector</h2>
          <p className="mt-1 text-sm text-[var(--muted)]">Give this connector a location-based name, then enter its one-time code on the computer that will run it.</p>
          <form className="mt-4 space-y-3" onSubmit={(event) => { event.preventDefault(); createMutation.mutate() }}>
            <label className="label" htmlFor="connector-name">Connector name<input id="connector-name" required maxLength={160} className="field" value={name} onChange={(event) => setName(event.target.value)} placeholder="Warehouse switch network" /></label>
            {user?.role === 'super_admin' && <label className="label" htmlFor="connector-tenant">Workspace<select id="connector-tenant" required className="field" value={tenantId} onChange={(event) => setTenantId(event.target.value)}><option value="">Select a workspace</option>{tenants.map((tenant) => <option key={tenant.id} value={tenant.id}>{tenant.name}</option>)}</select></label>}
            <button type="submit" className="btn-primary" disabled={createMutation.isPending}>{createMutation.isPending ? 'Creating code…' : 'Create connector and code'}</button>
          </form>
        </section>}
        <section className="connector-inventory" aria-labelledby="connector-inventory-title">
          <div className="connector-inventory-heading"><div><h2 id="connector-inventory-title">Your connectors</h2><p>Rename a connector to match its site; device assignments and credentials stay the same.</p></div><span>{connectors.length}</span></div>
          <div className="site-connector-list">
            {connectors.map((connector) => {
              const status = !connector.is_active ? 'Revoked' : !connector.is_enrolled ? 'Awaiting enrollment' : connector.is_online ? 'Online' : 'Offline'
              return <article key={connector.id} className="site-connector-row">
                <div className="site-connector-info">
                  {editingConnectorId === connector.id
                    ? <form className="site-connector-rename" onSubmit={(event) => { event.preventDefault(); renameMutation.mutate({ connectorId: connector.id, name: editedConnectorName.trim() }) }}>
                      <label className="sr-only" htmlFor={`connector-rename-${connector.id}`}>Name for {connector.name}</label>
                      <input id={`connector-rename-${connector.id}`} className="field" autoFocus maxLength={160} required value={editedConnectorName} onChange={(event) => setEditedConnectorName(event.target.value)} />
                      <button type="submit" className="btn-primary" disabled={renameMutation.isPending}>{renameMutation.isPending ? 'Saving…' : 'Save name'}</button>
                      <button type="button" className="btn-secondary" disabled={renameMutation.isPending} onClick={() => { setEditingConnectorId(null); setEditedConnectorName('') }}>Cancel</button>
                    </form>
                    : <div className="site-connector-title">
                      <h3>{connector.name}</h3>
                      {canManageConnectors && <button type="button" className="connector-edit-name" aria-label={`Edit ${connector.name} name`} onClick={() => { setEditingConnectorId(connector.id); setEditedConnectorName(connector.name) }}><Pencil size={14} aria-hidden="true" /><span>Edit name</span></button>}
                    </div>}
                  <p className="site-connector-status"><span className={`connector-status-pill ${!connector.is_active ? 'is-revoked' : connector.is_online ? 'is-online' : connector.is_enrolled ? 'is-offline' : 'is-waiting'}`}>{status}</span><span>Last contact {formatTimestamp(connector.last_seen_at ?? null)}</span>{user?.role === 'super_admin' && connector.tenant_name && <span>Workspace: {connector.tenant_name}</span>}</p>
                </div>
                {canManageConnectors && <div className="site-connector-actions">{connector.is_active
                  ? <button type="button" className="btn-secondary connector-revoke-button" disabled={revokeMutation.isPending} onClick={() => { if (window.confirm('Revoke this connector and unassign its switches?')) revokeMutation.mutate(connector.id) }}>Revoke connector</button>
                  : <button type="button" className="btn-secondary connector-revoke-button" disabled={deleteMutation.isPending} onClick={() => { if (window.confirm('Permanently delete this revoked connector and its command history?')) deleteMutation.mutate(connector.id) }}>Delete connector</button>}</div>}
              </article>
            })}
            {!connectors.length && <p className="connector-empty-state">No connectors yet. Add one after choosing the computer that will stay on the switch network.</p>}
          </div>
        </section>
      </div>
    </div>
  )
}
