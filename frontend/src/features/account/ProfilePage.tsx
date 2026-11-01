import { useMutation, useQueryClient } from '@tanstack/react-query'

import { KeyRound } from 'lucide-react'

import { useState } from 'react'

import type { FormEvent } from 'react'

import { apiFetch } from '../../shared/api'

import { useSession } from '../../shared/hooks'

import { LoadingCard, ErrorCard, PageHeader } from '../../shared/components'

import { TIME_ZONE_OPTIONS, TIME_ZONE_REGIONS } from '../../shared/config'

export function ChangePasswordSection() {
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [formError, setFormError] = useState('')
  const [successMessage, setSuccessMessage] = useState('')

  const mutation = useMutation({
    mutationFn: (values: { current_password: string; new_password: string }) =>
      apiFetch<{ message: string }>('/api/v1/auth/password', {
        method: 'PUT',
        body: JSON.stringify(values),
      }),
    onSuccess: ({ message }) => {
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      setFormError('')
      setSuccessMessage(message)
    },
  })

  function submitPasswordChange(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSuccessMessage('')
    setFormError('')
    if (newPassword !== confirmPassword) {
      setFormError('The new passwords do not match.')
      return
    }
    if (new TextEncoder().encode(newPassword).length > 72) {
      setFormError('The new password must be 72 UTF-8 bytes or fewer.')
      return
    }
    mutation.mutate({ current_password: currentPassword, new_password: newPassword })
  }

  return (
      <section className="panel account-password-section" aria-labelledby="password-form-title">
        <div className="account-password-heading">
          <span className="account-password-icon">
            <KeyRound size={18} aria-hidden="true" />
          </span>
          <div>
            <h2 id="password-form-title">Change password</h2>
            <p>Choose a new password for your ChargePilot account.</p>
          </div>
        </div>
        {successMessage && <p className="alert success" role="status">{successMessage}</p>}
        {(formError || mutation.error) && <p className="alert error" role="alert">{formError || mutation.error?.message}</p>}
        <form className="account-password-form" onSubmit={submitPasswordChange}>
          <label className="field-group" htmlFor="current-password">
            Current password
            <input
              id="current-password"
              type="password"
              autoComplete="current-password"
              required
              className="field"
              value={currentPassword}
              onChange={(event) => setCurrentPassword(event.target.value)}
            />
          </label>
          <label className="field-group" htmlFor="new-password">
            New password
            <input
              id="new-password"
              type="password"
              autoComplete="new-password"
              minLength={12}
              maxLength={72}
              required
              className="field"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
            />
            <span className="auth-helper">Use at least 12 characters.</span>
          </label>
          <label className="field-group" htmlFor="confirm-password">
            Confirm new password
            <input
              id="confirm-password"
              type="password"
              autoComplete="new-password"
              minLength={12}
              maxLength={72}
              required
              className="field"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
            />
          </label>
          <div className="account-password-actions">
            <button type="submit" className="btn-primary" disabled={mutation.isPending}>
              {mutation.isPending ? 'Saving password…' : 'Save new password'}
            </button>
          </div>
        </form>
      </section>
  )
}

export function ProfilePage() {
  const queryClient = useQueryClient()
  const { data: user, isLoading, error } = useSession()
  const [timezone, setTimezone] = useState('')
  const [statusMessage, setStatusMessage] = useState('')
  const mutation = useMutation({
    mutationFn: () => apiFetch<{ message: string }>('/api/v1/auth/profile', {
      method: 'PUT',
      body: JSON.stringify({ timezone: timezone || user?.timezone || 'UTC' }),
    }),
    onSuccess: ({ message }) => {
      setStatusMessage(message)
      queryClient.invalidateQueries({ queryKey: ['session'] })
    },
  })
  if (isLoading) return <LoadingCard />
  if (error || !user) return <ErrorCard message={error?.message ?? 'Your account could not be loaded.'} />
  const currentTimezone = timezone || user.timezone || 'UTC'
  return <div className="account-page">
    <PageHeader eyebrow="Your settings" title="Account" description="Manage your profile and sign-in preferences." />
    <section className="account-summary" aria-label="Account details">
      <div><span>Username</span><strong>{user.username}</strong></div>
      <div><span>Email</span><strong>{user.email ?? 'Not set'}</strong></div>
      <div><span>Role</span><strong>{user.role.replaceAll('_', ' ')}</strong></div>
      <div><span>Workspace</span><strong>{user.tenant_name ?? 'System'}</strong></div>
    </section>
    <section className="profile-preference panel account-timezone-section">
      <div>
        <h2>Time zone</h2>
        <p>Choose how dates and times are shown across ChargePilot.</p>
      </div>
      {statusMessage && <p className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800" role="status">{statusMessage}</p>}
      {mutation.error && <div className="mt-4"><ErrorCard message={mutation.error.message} /></div>}
      <form className="profile-preference-form" onSubmit={(event) => { event.preventDefault(); setStatusMessage(''); mutation.mutate() }}>
        <label className="profile-timezone-label" htmlFor="profile-timezone">Your time zone</label>
        <select
          id="profile-timezone"
          className="field"
          aria-label="Time zone"
          value={currentTimezone}
          onChange={(event) => setTimezone(event.target.value)}
          required
        >
          <option value="UTC">UTC — Coordinated Universal Time</option>
          {currentTimezone !== 'UTC' && !TIME_ZONE_OPTIONS.includes(currentTimezone) && (
            <option value={currentTimezone}>{currentTimezone.replaceAll('_', ' ')}</option>
          )}
          {TIME_ZONE_REGIONS.map((region) => {
            const regionZones = TIME_ZONE_OPTIONS.filter((zone) => zone.startsWith(`${region}/`))
            if (!regionZones.length) return null
            return <optgroup key={region} label={region}>
              {regionZones.map((zone) => <option key={zone} value={zone}>{zone.replaceAll('_', ' ')}</option>)}
            </optgroup>
          })}
        </select>
        <button type="submit" className="btn-primary" disabled={mutation.isPending}>{mutation.isPending ? 'Saving…' : 'Save time zone'}</button>
      </form>
    </section>
    <ChangePasswordSection />
  </div>
}
