import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { useState } from 'react'

import type { FormEvent } from 'react'

import { apiFetch } from '../../shared/api'

import { LoadingCard, ErrorCard, PageHeader } from '../../shared/components'

import type { TenantInfo } from '../../shared/types'

import { formatTimestamp } from '../../shared/lib'

export function TenantsPage() {
  const queryClient = useQueryClient()
  const tenantsQuery = useQuery({ queryKey: ['admin-tenants'], queryFn: () => apiFetch<TenantInfo[]>('/api/v1/admin/tenants') })
  const [statusMessage, setStatusMessage] = useState('')
  const actionMutation = useMutation({
    mutationFn: async ({ path, method, body }: { path: string; method: 'POST' | 'DELETE'; body?: Record<string, unknown> }) =>
      apiFetch<{ message?: string } | undefined>(path, {
        method,
        ...(body ? { body: JSON.stringify(body) } : {}),
      }),
    onSuccess: (_, variables) => {
      setStatusMessage(variables.method === 'DELETE' ? 'Tenant deleted.' : variables.path.includes('rotate-agent-token') ? 'Agent token rotated.' : 'Tenant created.')
      queryClient.invalidateQueries({ queryKey: ['admin-tenants'] })
    },
  })
  if (tenantsQuery.isLoading) return <LoadingCard />
  if (tenantsQuery.error) return <ErrorCard message={tenantsQuery.error.message} />
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const tenantName = String(new FormData(event.currentTarget).get('tenant_name') ?? '')
    actionMutation.mutate({ path: '/api/v1/admin/tenants', method: 'POST', body: { name: tenantName } })
  }
  return <div className="space-y-6">
    <PageHeader eyebrow="Super Admin" title="Tenants" description="Create and manage isolated customer environments and their agent credentials." />
    {statusMessage && <p className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800" role="status">{statusMessage}</p>}
    {actionMutation.error && <ErrorCard message={actionMutation.error.message} />}
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="text-lg font-bold text-slate-900">Create a tenant</h2>
      <form className="mt-4 flex flex-col gap-3 sm:flex-row" onSubmit={submit}><label className="label min-w-0 flex-1" htmlFor="tenant-name">Tenant name<input id="tenant-name" name="tenant_name" required maxLength={160} className="field" /></label><button type="submit" className="btn-primary self-end" disabled={actionMutation.isPending}>Create tenant</button></form>
    </section>
    <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-200 px-5 py-4"><h2 className="font-bold text-slate-900">Tenant directory</h2></div>
      <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-left text-sm">
        <thead className="bg-slate-50 text-xs text-slate-500"><tr><th className="px-4 py-3">Name</th><th className="px-4 py-3">Slug</th><th className="px-4 py-3">Agent token</th><th className="px-4 py-3">Created</th><th className="px-4 py-3">Actions</th></tr></thead>
        <tbody className="divide-y divide-slate-100">{(tenantsQuery.data ?? []).map((tenant) => <tr key={tenant.id}>
          <td className="px-4 py-3 font-semibold text-slate-900">{tenant.name}</td><td className="px-4 py-3 text-slate-600">{tenant.slug}</td><td className="px-4 py-3"><code className="break-all font-mono text-xs">{tenant.agent_token}</code></td><td className="px-4 py-3 text-slate-500">{formatTimestamp(tenant.created_at)}</td>
          <td className="space-y-2 px-4 py-3"><button type="button" className="btn-secondary px-3 py-2" onClick={() => actionMutation.mutate({ path: `/api/v1/admin/tenants/${tenant.id}/rotate-agent-token`, method: 'POST' })}>Rotate token</button><button type="button" className="btn-secondary border-red-200 px-3 py-2 text-red-700" onClick={() => { if (window.confirm('Delete this tenant and all of its tenant data?')) actionMutation.mutate({ path: `/api/v1/admin/tenants/${tenant.id}`, method: 'DELETE' }) }}>Delete</button></td>
        </tr>)}
        {!tenantsQuery.data?.length && <tr><td colSpan={5} className="px-4 py-8 text-center text-slate-500">No tenants have been created yet.</td></tr>}</tbody>
      </table></div>
    </section>
  </div>
}
