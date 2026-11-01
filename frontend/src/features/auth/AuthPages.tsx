import { useMutation, useQuery } from '@tanstack/react-query'

import { BatteryCharging, LogIn, MonitorSmartphone, Network, PlugZap } from 'lucide-react'

import { useCallback, useEffect, useRef, useState } from 'react'

import type { FormEvent } from 'react'

import { useNavigate, useSearchParams } from 'react-router-dom'

import { ErrorCard } from '../../shared/components'

import { ThemeToggleButton } from '../../app/theme'

import { useAppTheme } from '../../app/useAppTheme'

import { apiFetch } from '../../shared/api'

import { type User } from '../../shared/types'

import { queryClient } from '../../app/queryClient'

import { frontendUrl } from '../../shared/config'

let turnstileScriptPromise: Promise<void> | null = null

export function AuthBrandPanel() {
  return (
    <aside className="auth-story" aria-label="ChargePilot purpose">
      <div className="auth-story-brand"><span className="rail-mark"><BatteryCharging size={21} aria-hidden="true" /></span><strong>ChargePilot</strong></div>
      <div className="auth-story-copy">
        <span className="auth-story-kicker">Local energy, under control</span>
        <h2>Keep the battery.<br />Lose the guesswork.</h2>
        <p>Battery monitoring across your devices, paired with switches that stay on their own network.</p>
      </div>
      <div className="energy-path" aria-label="Device telemetry flows through your site connector to your switch">
        <div className="energy-node"><MonitorSmartphone size={18} /><span>Device</span></div>
        <span className="energy-wire"><i /></span>
        <div className="energy-node"><Network size={18} /><span>Site link</span></div>
        <span className="energy-wire"><i /></span>
        <div className="energy-node"><PlugZap size={18} /><span>Switch</span></div>
      </div>
      <p className="auth-story-foot">Battery rules run in ChargePilot. Device control stays local.</p>
    </aside>
  )
}

function loadTurnstileScript() {
  if (window.turnstile) return Promise.resolve()
  if (turnstileScriptPromise) return turnstileScriptPromise

  turnstileScriptPromise = new Promise<void>((resolve, reject) => {
    const script = document.createElement('script')
    script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'
    script.async = true
    script.defer = true
    script.onload = () => {
      if (window.turnstile) resolve()
      else reject(new Error('Human verification could not be initialized.'))
    }
    script.onerror = () => {
      turnstileScriptPromise = null
      script.remove()
      reject(new Error('Human verification could not be loaded.'))
    }
    document.head.appendChild(script)
  })
  return turnstileScriptPromise
}

export function TurnstileChallenge({
  onToken,
  action = 'registration',
}: {
  onToken: (token: string) => void
  action?: string
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const siteKey = window.CHARGEPILOT_CONFIG?.turnstileSiteKey ?? ''
  const [widgetError, setWidgetError] = useState('')

  useEffect(() => {
    if (!siteKey) return

    let disposed = false
    let widgetId: string | undefined
    void loadTurnstileScript()
      .then(() => {
        if (disposed || !containerRef.current || !window.turnstile) return
        widgetId = window.turnstile.render(containerRef.current, {
          sitekey: siteKey,
          action,
          theme: 'auto',
          callback: (token) => {
            onToken(token)
            setWidgetError('')
          },
          'expired-callback': () => onToken(''),
          'error-callback': () => {
            onToken('')
            setWidgetError('Human verification is unavailable. Refresh the page and try again.')
          },
        })
      })
      .catch(() => {
        if (!disposed) {
          onToken('')
          setWidgetError('Human verification could not be loaded. Check your connection and refresh.')
        }
      })

    return () => {
      disposed = true
      if (widgetId) window.turnstile?.remove(widgetId)
    }
  }, [action, onToken, siteKey])

  return (
    <div className="turnstile-verification">
      {siteKey
        ? <div ref={containerRef} aria-label="Human verification challenge" />
        : <p className="turnstile-status" role="alert">New account registration is currently unavailable. Human verification has not been configured.</p>}
      {widgetError && <p className="turnstile-status" role="alert">{widgetError}</p>}
    </div>
  )
}

export function LoginPage() {
  const [searchParams] = useSearchParams()
  const [isDark, setIsDark] = useAppTheme()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const loginMutation = useMutation({
    mutationFn: () => apiFetch<{ user: User }>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
    onSuccess: ({ user }) => {
      queryClient.setQueryData(['session'], user)
      navigate('/', { replace: true })
    },
  })

  return (
    <div className="auth-shell">
      <ThemeToggleButton isDark={isDark} onToggle={() => setIsDark((value) => !value)} className="auth-theme-toggle" />
      <AuthBrandPanel />
      <section className="auth-card" aria-labelledby="login-title">
        <div className="flex items-center justify-center"><div className="brand-mark auth-brand-mark">C</div></div>
        <div className="auth-badges"><span>ChargePilot</span><span>Local-first control</span></div>
        <h1 id="login-title">Welcome back</h1>
        <p className="auth-subtle">Sign in to your tenant and manage your battery automation.</p>
        {searchParams.get('message') && <p className="alert success mt-5" role="status">{searchParams.get('message')}</p>}
        {searchParams.get('error') && <p className="alert error mt-4" role="alert">{searchParams.get('error')}</p>}
        <form onSubmit={(event) => { event.preventDefault(); loginMutation.mutate() }} className="auth-form">
          <div className="field-group">
            <label htmlFor="username">Username</label>
            <input id="username" name="username" type="text" autoComplete="username" required className="field" value={username} onChange={(event) => setUsername(event.target.value)} />
          </div>
          <div className="field-group">
            <label htmlFor="password">Password</label>
            <input id="password" name="password" type="password" autoComplete="current-password" required className="field" value={password} onChange={(event) => setPassword(event.target.value)} />
          </div>
          {loginMutation.error && <ErrorCard message={loginMutation.error.message} />}
          <button type="submit" className="primary-btn large-btn w-full" disabled={loginMutation.isPending}><LogIn size={16} className="mr-2" />{loginMutation.isPending ? 'Signing in…' : 'Log in'}</button>
        </form>
        <div className="auth-divider" />
        <div className="auth-signup">
          <p>Joining an existing workspace? Ask its administrator to email you an invitation.</p>
          <div className="auth-actions">
            <a href={frontendUrl('/register?account_type=tenant')} className="primary-btn small-btn">Create tenant</a>
          </div>
        </div>
      </section>
    </div>
  )
}

export function RegisterPage() {
  const [searchParams] = useSearchParams()
  const [isDark, setIsDark] = useAppTheme()
  const navigate = useNavigate()
  const accountType = searchParams.get('account_type') === 'tenant' ? 'tenant' : 'standard'
  const error = searchParams.get('error')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [email, setEmail] = useState('')
  const [inviteCode, setInviteCode] = useState('')
  const [tenantName, setTenantName] = useState('')
  const [challenge, setChallenge] = useState({ accountType, token: '' })
  const [challengeReset, setChallengeReset] = useState(0)
  const turnstileToken = challenge.accountType === accountType ? challenge.token : ''
  const setTurnstileToken = useCallback((token: string) => {
    setChallenge({ accountType, token })
  }, [accountType])

  const registerMutation = useMutation({
    mutationFn: () => apiFetch<{ message: string }>('/api/v1/auth/register', {
      method: 'POST',
      body: JSON.stringify({
        account_type: accountType,
        username,
        password,
        email,
        turnstile_token: turnstileToken,
        ...(accountType === 'standard' ? { invite_code: inviteCode } : { tenant_name: tenantName }),
      }),
    }),
    onError: () => {
      setChallenge({ accountType, token: '' })
      setChallengeReset((value) => value + 1)
    },
    onSuccess: () => {
      navigate('/verify-email?sent=1', { replace: true })
    },
  })

  return (
    <div className="auth-shell">
      <ThemeToggleButton isDark={isDark} onToggle={() => setIsDark((value) => !value)} className="auth-theme-toggle" />
      <AuthBrandPanel />
      <section className="auth-card auth-card-wide" aria-labelledby="register-title">
        <div className="flex items-center justify-center"><div className="brand-mark auth-brand-mark">C</div></div>
        <div className="auth-badges"><span>Create account</span><span>Secure access</span></div>
        <h1 id="register-title">Choose your access</h1>
        {error && <p className="alert error mt-4" role="alert">{error}</p>}
        <div className="auth-choice-grid">
          <a href={frontendUrl('/register?account_type=standard')} className={`choice-card ${accountType === 'standard' ? 'active' : ''}`}>
            <span className="choice-title">Standard user</span><span className="choice-copy">Join your team with a one-time invite code.</span>
          </a>
          <a href={frontendUrl('/register?account_type=tenant')} className={`choice-card ${accountType === 'tenant' ? 'active' : ''}`}>
            <span className="choice-title">Tenant admin</span><span className="choice-copy">Creates a new isolated tenant.</span>
          </a>
        </div>
        <form onSubmit={(event) => { event.preventDefault(); registerMutation.mutate() }} className="auth-form">
          <div className="field-group">
            <label htmlFor="username">Username</label>
            <input id="username" name="username" type="text" autoComplete="username" minLength={3} maxLength={80} required className="field" value={username} onChange={(event) => setUsername(event.target.value)} />
          </div>
          <div className="field-group">
            <label htmlFor="password">Password</label>
            <input id="password" name="password" type="password" autoComplete="new-password" minLength={12} maxLength={72} required className="field" value={password} onChange={(event) => setPassword(event.target.value)} />
          </div>
          <div className="field-group">
            <label htmlFor="email">Email address</label>
            <input id="email" name="email" type="email" autoComplete="email" maxLength={254} required className="field" value={email} onChange={(event) => setEmail(event.target.value)} />
            <p className="auth-helper">We’ll send a verification link that expires in 30 minutes.</p>
          </div>
          {accountType === 'tenant'
            ? <div className="field-group"><label htmlFor="tenant_name">Tenant name</label><input id="tenant_name" name="tenant_name" type="text" minLength={1} maxLength={160} placeholder="My tenant" className="field" required value={tenantName} onChange={(event) => setTenantName(event.target.value)} /></div>
            : <div className="field-group"><label htmlFor="invite_code">One-time tenant invite code</label><input id="invite_code" name="invite_code" type="text" autoComplete="off" spellCheck={false} required className="field font-mono" value={inviteCode} onChange={(event) => setInviteCode(event.target.value)} /><p className="auth-helper">Ask your tenant administrator for a code. It can be used once and expires after seven days.</p></div>}
          <div className="field-group">
            <span>Human verification</span>
            <TurnstileChallenge key={`${accountType}-${challengeReset}`} onToken={setTurnstileToken} />
          </div>
          {registerMutation.error && <ErrorCard message={registerMutation.error.message} />}
          <button type="submit" className="primary-btn large-btn w-full" disabled={registerMutation.isPending || !turnstileToken}>{registerMutation.isPending ? 'Creating account…' : accountType === 'tenant' ? 'Create tenant and admin account' : 'Create standard user account'}</button>
        </form>
        <p className="auth-signin">Already have an account? <a href={frontendUrl('/login')}>Sign in</a></p>
      </section>
    </div>
  )
}

export function VerifyEmailPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const token = searchParams.get('token') ?? ''
  const sent = searchParams.get('sent') === '1'
  const [isDark, setIsDark] = useAppTheme()
  const [email, setEmail] = useState('')
  const [challenge, setChallenge] = useState('')
  const [challengeReset, setChallengeReset] = useState(0)
  const [resent, setResent] = useState(false)

  const verifyMutation = useMutation({
    mutationFn: () => apiFetch<{ user: User }>('/api/v1/auth/verify-email', {
      method: 'POST',
      body: JSON.stringify({ token }),
    }),
    onSuccess: ({ user }) => {
      queryClient.setQueryData(['session'], user)
      navigate('/', { replace: true })
    },
  })

  const resendMutation = useMutation({
    mutationFn: () => apiFetch<{ message: string }>('/api/v1/auth/resend-verification', {
      method: 'POST',
      body: JSON.stringify({ email, turnstile_token: challenge }),
    }),
    onSuccess: () => {
      setResent(true)
      setChallenge('')
      setChallengeReset((value) => value + 1)
    },
    onError: () => {
      setChallenge('')
      setChallengeReset((value) => value + 1)
    },
  })

  return (
    <div className="auth-shell">
      <ThemeToggleButton isDark={isDark} onToggle={() => setIsDark((value) => !value)} className="auth-theme-toggle" />
      <AuthBrandPanel />
      <section className="auth-card auth-card-wide" aria-labelledby="verify-email-title">
        <div className="flex items-center justify-center"><div className="brand-mark auth-brand-mark">C</div></div>
        <div className="auth-badges"><span>Account verification</span><span>Secure access</span></div>
        <h1 id="verify-email-title">Verify your email</h1>
        {sent && <p className="alert success mt-4" role="status">Your account is ready. Check your inbox for the verification link; it expires in 30 minutes.</p>}
        {token && <p className="auth-subtle">Select verify to activate your ChargePilot account.</p>}
        {token && (
          <div className="mt-5">
            {verifyMutation.error && <ErrorCard message={verifyMutation.error.message} />}
            <button type="button" className="primary-btn large-btn w-full" disabled={verifyMutation.isPending} onClick={() => verifyMutation.mutate()}>
              {verifyMutation.isPending ? 'Verifying…' : 'Verify email and sign in'}
            </button>
          </div>
        )}
        <div className="auth-divider" />
        <form onSubmit={(event) => { event.preventDefault(); resendMutation.mutate() }} className="auth-form">
          <p className="auth-subtle">{token ? 'If the link expired, request a fresh one.' : 'Need another verification link? Enter your account email.'}</p>
          <div className="field-group">
            <label htmlFor="verification-email">Email address</label>
            <input id="verification-email" name="email" type="email" autoComplete="email" maxLength={254} required className="field" value={email} onChange={(event) => setEmail(event.target.value)} />
          </div>
          <div className="field-group">
            <span>Human verification</span>
            <TurnstileChallenge key={challengeReset} onToken={setChallenge} />
          </div>
          {resendMutation.error && <ErrorCard message={resendMutation.error.message} />}
          {resent && <p className="alert success" role="status">If the account needs verification, a new email has been sent.</p>}
          <button type="submit" className="btn-secondary large-btn w-full" disabled={resendMutation.isPending || !challenge}>
            {resendMutation.isPending ? 'Sending…' : 'Resend verification email'}
          </button>
        </form>
        <p className="auth-signin"><a href={frontendUrl('/login')}>Back to sign in</a></p>
      </section>
    </div>
  )
}

export function AcceptInvitationPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const [code] = useState(() => searchParams.get('code') ?? '')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [formError, setFormError] = useState('')
  useEffect(() => {
    if (code) navigate('/accept-invitation', { replace: true })
  }, [code, navigate])

  const invitationQuery = useQuery({
    queryKey: ['account-invitation', code],
    queryFn: () => apiFetch<{ username: string; email: string; role: string; tenant_name: string; expires_at: string }>(
      '/api/v1/auth/invitation-details',
      { method: 'POST', body: JSON.stringify({ code }) },
    ),
    enabled: Boolean(code),
    retry: false,
  })
  const acceptMutation = useMutation({
    mutationFn: () => apiFetch<{ user: User }>('/api/v1/auth/accept-invitation', {
      method: 'POST',
      body: JSON.stringify({ code, password }),
    }),
    onSuccess: ({ user }) => {
      queryClient.setQueryData(['session'], user)
      navigate('/', { replace: true })
    },
  })

  function submitPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFormError('')
    if (password !== confirmPassword) {
      setFormError('The passwords do not match.')
      return
    }
    if (new TextEncoder().encode(password).length > 72) {
      setFormError('The password must be 72 UTF-8 bytes or fewer.')
      return
    }
    acceptMutation.mutate()
  }

  const invite = invitationQuery.data
  const detailsError = invitationQuery.error
  const [isDark, setIsDark] = useAppTheme()

  return (
    <div className="auth-shell">
      <ThemeToggleButton isDark={isDark} onToggle={() => setIsDark((value) => !value)} className="auth-theme-toggle" />
      <AuthBrandPanel />
      <section className="auth-card auth-card-wide" aria-labelledby="invitation-title">
        <h1 id="invitation-title">Set your password</h1>
        {invitationQuery.isLoading && <p className="auth-subtle">Checking your invitation…</p>}
        {detailsError && <ErrorCard message={detailsError.message} />}
        {!code && <ErrorCard message="This invitation link is missing its one-time setup code." />}
        {invite && <>
          <p className="auth-subtle">Choose a password to activate your ChargePilot account.</p>
          <dl className="invitation-account-details">
            <div><dt>Username</dt><dd>{invite.username}</dd></div>
            <div><dt>Email</dt><dd>{invite.email}</dd></div>
            <div><dt>Workspace</dt><dd>{invite.tenant_name}</dd></div>
            <div><dt>Access</dt><dd>{invite.role.replaceAll('_', ' ')}</dd></div>
          </dl>
          <form className="auth-form" onSubmit={submitPassword}>
            <label className="field-group" htmlFor="invited-password">
              New password
              <input
                id="invited-password"
                type="password"
                autoComplete="new-password"
                minLength={12}
                maxLength={72}
                required
                className="field"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
              <span className="auth-helper">Use at least 12 characters.</span>
            </label>
            <label className="field-group" htmlFor="invited-password-confirm">
              Confirm password
              <input
                id="invited-password-confirm"
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
            {(formError || acceptMutation.error) && <ErrorCard message={formError || acceptMutation.error?.message || 'The invitation could not be accepted.'} />}
            <button type="submit" className="primary-btn large-btn w-full" disabled={acceptMutation.isPending}>
              {acceptMutation.isPending ? 'Activating account…' : 'Set password and sign in'}
            </button>
          </form>
        </>}
        <p className="auth-signin"><a href={frontendUrl('/login')}>Back to sign in</a></p>
      </section>
    </div>
  )
}
