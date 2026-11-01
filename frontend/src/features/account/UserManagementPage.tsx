import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { Mail } from 'lucide-react'

import { useState } from 'react'

import type { FormEvent } from 'react'

import { apiFetch } from '../../shared/api'

import { useSession } from '../../shared/hooks'

import { LoadingCard, ErrorCard, PageHeader } from '../../shared/components'

import type { AdminUser, TenantInfo, AccountInvitationInfo } from '../../shared/types'

import { formatTimestamp } from '../../shared/lib'

export function UsersPage() {
  const queryClient = useQueryClient()
  const { data: currentUser, isLoading: sessionLoading } = useSession()
  const usersQuery = useQuery({ queryKey: ['admin-users'], queryFn: () => apiFetch<AdminUser[]>('/api/v1/admin/users') })
  const tenantsQuery = useQuery({ queryKey: ['admin-tenants'], queryFn: () => apiFetch<TenantInfo[]>('/api/v1/admin/tenants'), enabled: currentUser?.role === 'super_admin' })
  const invitationsQuery = useQuery({ queryKey: ['account-invitations'], queryFn: () => apiFetch<AccountInvitationInfo[]>('/api/v1/admin/account-invitations') })
  const [statusMessage, setStatusMessage] = useState('')
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteUsername, setInviteUsername] = useState('')
  const [inviteRole, setInviteRole] = useState('tenant_admin')
  const [inviteTenantId, setInviteTenantId] = useState('')
  const actionMutation = useMutation({
    mutationFn: async ({ method, path, body }: { method: 'PATCH' | 'DELETE'; path: string; body?: Record<string, unknown> }) =>
      apiFetch<{ message?: string } | undefined>(path, {
        method,
        ...(body ? { body: JSON.stringify(body) } : {}),
      }),
    onSuccess: (_, variables) => {
      setStatusMessage(variables.method === 'DELETE' ? 'Account removed.' : 'Access updated.')
      queryClient.invalidateQueries({ queryKey: ['admin-users'] })
    },
  })
  const inviteMutation = useMutation({
    mutationFn: (body: { email: string; username: string; role: string; tenant_id?: string }) => apiFetch<AccountInvitationInfo>('/api/v1/admin/account-invitations', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
    onSuccess: (invitation) => {
      setStatusMessage(`Invitation sent to ${invitation.email}.`)
      setInviteEmail('')
      setInviteUsername('')
      queryClient.invalidateQueries({ queryKey: ['account-invitations'] })
    },
  })
  const deleteInvitationMutation = useMutation({
    mutationFn: (invitationId: string) => apiFetch<void>(`/api/v1/admin/account-invitations/${invitationId}`, { method: 'DELETE' }),
    onSuccess: () => {
      setStatusMessage('Invitation deleted.')
      queryClient.invalidateQueries({ queryKey: ['account-invitations'] })
    },
  })
  const isSuperAdmin = currentUser?.role === 'super_admin'
  if (sessionLoading || usersQuery.isLoading || tenantsQuery.isLoading || invitationsQuery.isLoading) return <LoadingCard />
  if (usersQuery.error) return <ErrorCard message={usersQuery.error.message} />
  if (tenantsQuery.error) return <ErrorCard message={tenantsQuery.error.message} />
  if (invitationsQuery.error) return <ErrorCard message={invitationsQuery.error.message} />
  const tenants = tenantsQuery.data ?? []
  const roles = ['tenant_admin', 'manager', 'standard_user', 'viewer']
  const submitRoleChange = (event: FormEvent<HTMLFormElement>, account: AdminUser) => {
    event.preventDefault()
    const body = Object.fromEntries(new FormData(event.currentTarget).entries())
    actionMutation.mutate({ path: `/api/v1/admin/users/${account.id}`, method: 'PATCH', body })
  }
  const invitations = invitationsQuery.data ?? []
  const statusOf = (invitation: AccountInvitationInfo) => invitation.used_at
    ? 'Accepted'
    : invitation.revoked_at
      ? 'Revoked'
      : invitation.is_active
        ? 'Waiting for response'
        : 'Expired'
  const submitInvitation = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setStatusMessage('')
    inviteMutation.mutate({
      email: inviteEmail,
      username: inviteUsername,
      role: inviteRole,
      ...(isSuperAdmin ? { tenant_id: inviteTenantId } : {}),
    })
  }
  return (
    <div className="people-page">
      <PageHeader eyebrow="Administration" title="People & invites" description="Invite teammates, manage access, and keep track of who belongs to this workspace." />
      {statusMessage && <p className="alert success" role="status">{statusMessage}</p>}
      {(actionMutation.error || inviteMutation.error || deleteInvitationMutation.error) && (
        <ErrorCard message={actionMutation.error?.message ?? inviteMutation.error?.message ?? deleteInvitationMutation.error?.message ?? 'The request failed.'} />
      )}

      <section className="panel people-invite-section" aria-labelledby="invite-heading">
        <div className="people-section-heading">
          <div>
            <h2 id="invite-heading">Invite someone</h2>
            <p>We’ll email a private setup link and one-time code. They choose their password before signing in.</p>
          </div>
          <span className="people-heading-icon"><Mail size={19} aria-hidden="true" /></span>
        </div>
        <form className="people-invite-form" onSubmit={submitInvitation}>
          <label className="field-group" htmlFor="invite-username">
            Username
            <input
              id="invite-username"
              autoComplete="off"
              minLength={3}
              maxLength={80}
              required
              className="field"
              value={inviteUsername}
              onChange={(event) => setInviteUsername(event.target.value)}
            />
          </label>
          <label className="field-group" htmlFor="invite-email">
            Email address
            <input
              id="invite-email"
              type="email"
              autoComplete="email"
              maxLength={254}
              required
              className="field"
              value={inviteEmail}
              onChange={(event) => setInviteEmail(event.target.value)}
            />
          </label>
          <label className="field-group" htmlFor="invite-role">
            Access level
            <select id="invite-role" className="field" value={inviteRole} onChange={(event) => setInviteRole(event.target.value)}>
              {roles.map((role) => <option key={role} value={role}>{role.replaceAll('_', ' ')}</option>)}
            </select>
          </label>
          {isSuperAdmin && (
            <label className="field-group" htmlFor="invite-tenant">
              Workspace
              <select id="invite-tenant" className="field" required value={inviteTenantId} onChange={(event) => setInviteTenantId(event.target.value)}>
                <option value="">Select a workspace</option>
                {tenants.map((tenant) => <option key={tenant.id} value={tenant.id}>{tenant.name}</option>)}
              </select>
            </label>
          )}
          <div className="people-invite-submit">
            <p>The link expires in seven days and can only be used once.</p>
            <button type="submit" className="btn-primary" disabled={inviteMutation.isPending || (isSuperAdmin && !inviteTenantId)}>
              {inviteMutation.isPending ? 'Sending invitation…' : 'Send invitation'}
            </button>
          </div>
        </form>
      </section>

      <section className="panel people-invitations-section" aria-labelledby="invitations-heading">
        <div className="people-section-heading">
          <div>
            <h2 id="invitations-heading">Invitations</h2>
            <p>Review invitation history and remove records that are no longer needed.</p>
          </div>
          <span className="people-count">{invitations.length}</span>
        </div>
        {invitations.length ? (
          <div className="people-invitation-list">
            {invitations.map((invitation) => (
              <article className="people-invitation-row" key={invitation.id}>
                <div className="people-invitation-person">
                  <span className="people-invitation-avatar" aria-hidden="true">{invitation.username.slice(0, 1).toUpperCase()}</span>
                  <div>
                    <strong>{invitation.username}</strong>
                    <span>{invitation.email}</span>
                  </div>
                </div>
                <div className="people-invitation-meta">
                  <span className={`people-invitation-status ${invitation.is_active ? 'is-pending' : invitation.used_at ? 'is-accepted' : ''}`}>
                    {statusOf(invitation)}
                  </span>
                  <span>{invitation.role.replaceAll('_', ' ')}</span>
                  <span>{invitation.tenant_name ?? currentUser?.tenant_name ?? 'Workspace'}</span>
                  <span>{invitation.is_active ? `Expires ${formatTimestamp(invitation.expires_at)}` : `Sent ${formatTimestamp(invitation.created_at)}`}</span>
                </div>
                <button
                  type="button"
                  className="people-delete-invitation-button"
                  aria-label={`Delete invitation for ${invitation.username}`}
                  disabled={deleteInvitationMutation.isPending}
                  onClick={() => {
                    if (window.confirm('Delete this invitation record? Pending setup links will stop working. Accepted accounts are not affected.')) {
                      deleteInvitationMutation.mutate(invitation.id)
                    }
                  }}
                >
                  Delete
                </button>
              </article>
            ))}
          </div>
        ) : (
          <div className="people-empty-state">
            <p>No invitations yet.</p>
            <span>Send an invitation above to give someone access to this workspace.</span>
          </div>
        )}
      </section>

      <section className="panel people-accounts-section" aria-labelledby="accounts-heading">
        <div className="people-section-heading">
          <div>
            <h2 id="accounts-heading">Accounts</h2>
            <p>Manage roles and remove access for people already in ChargePilot.</p>
          </div>
          <span className="people-count">{usersQuery.data?.length ?? 0}</span>
        </div>
        <div className="people-table-wrap">
          <table className="people-table">
            <thead>
              <tr>
                <th scope="col">Person</th>
                <th scope="col">Access</th>
                {isSuperAdmin && <th scope="col">Workspace</th>}
                <th scope="col">Joined</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {(usersQuery.data ?? []).map((account) => (
                <tr key={account.id}>
                  <td>
                    <div className="people-account-person">
                      <strong>{account.username}</strong>
                      <span>{account.email ?? 'Email not set'}</span>
                    </div>
                  </td>
                  <td>
                    {account.role === 'super_admin' ? 'Super Admin' : (
                      <form className="people-role-form" onSubmit={(event) => submitRoleChange(event, account)}>
                        <select name="role" aria-label={`Access level for ${account.username}`} defaultValue={account.role} className="field">
                          {roles.map((role) => <option key={role} value={role}>{role.replaceAll('_', ' ')}</option>)}
                        </select>
                        {isSuperAdmin && (
                          <select name="tenant_id" aria-label={`Workspace for ${account.username}`} defaultValue={account.tenant_id ?? ''} required className="field">
                            <option value="">Select workspace</option>
                            {tenants.map((tenant) => <option key={tenant.id} value={tenant.id}>{tenant.name}</option>)}
                          </select>
                        )}
                        <button type="submit" className="btn-secondary" disabled={actionMutation.isPending}>Save access</button>
                      </form>
                    )}
                  </td>
                  {isSuperAdmin && <td>{account.tenant_name ?? 'Unassigned'}</td>}
                  <td>{formatTimestamp(account.created_at)}</td>
                  <td>
                    {account.id !== currentUser?.id && account.role !== 'super_admin' ? (
                      <button
                        type="button"
                        className="people-revoke-button"
                        disabled={actionMutation.isPending}
                        onClick={() => {
                          if (window.confirm(`Remove ${account.username}'s account?`)) {
                            actionMutation.mutate({ path: `/api/v1/admin/users/${account.id}`, method: 'DELETE' })
                          }
                        }}
                      >
                        Remove
                      </button>
                    ) : <span className="people-current-account">You</span>}
                  </td>
                </tr>
              ))}
              {!usersQuery.data?.length && (
                <tr><td colSpan={isSuperAdmin ? 5 : 4} className="people-no-accounts">No accounts found.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
