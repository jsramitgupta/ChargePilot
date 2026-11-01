import { useMutation, useQuery } from '@tanstack/react-query'

import { Mail } from 'lucide-react'

import { useState } from 'react'

import { useSession } from '../../shared/hooks'

import { apiFetch } from '../../shared/api'

import { LoadingCard, PageHeader, ErrorCard } from '../../shared/components'

export function SupportPage() {
  const { data: user } = useSession()
  const [replyEmail, setReplyEmail] = useState<string | null>(null)
  const replyAddress = replyEmail ?? user?.email ?? ''
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [sent, setSent] = useState(false)
  const supportQuery = useQuery({
    queryKey: ['support-config'],
    queryFn: () => apiFetch<{ configured: boolean; recipient: string }>('/api/v1/support/config'),
  })
  const sendMutation = useMutation({
    mutationFn: () => apiFetch<{ message: string }>('/api/v1/support/email', {
      method: 'POST',
      body: JSON.stringify({ reply_email: replyAddress, subject, body }),
    }),
    onSuccess: () => {
      setSent(true)
      setSubject('')
      setBody('')
    },
  })

  if (supportQuery.isLoading) return <LoadingCard />

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <PageHeader
        eyebrow="Help"
        title="Contact support"
        description="Send a note to the ChargePilot team. We’ll reply to the address you provide."
      />
      {supportQuery.error && <ErrorCard message={supportQuery.error.message} />}
      {supportQuery.data && !supportQuery.data.configured && (
        <section className="panel border-amber-200 bg-amber-50 p-5 text-sm text-amber-900" role="status">
          Support email is not available because the app’s SMTP settings are incomplete. Ask your administrator to configure mail delivery.
        </section>
      )}
      {supportQuery.data?.configured && (
        <section className="panel overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-slate-50 px-5 py-4 sm:px-7">
            <div>
              <h3 className="font-semibold text-slate-900">Send a support message</h3>
              <p className="mt-1 text-sm text-slate-600">Your message will go to {supportQuery.data.recipient}.</p>
            </div>
            <span className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-800">
              <Mail size={14} aria-hidden="true" /> Email ready
            </span>
          </div>
          <form
            className="space-y-5 p-5 sm:p-7"
            onSubmit={(event) => {
              event.preventDefault()
              setSent(false)
              sendMutation.mutate()
            }}
          >
            <label className="label" htmlFor="support-reply-email">
              Reply-to email
              <input
                id="support-reply-email"
                type="email"
                autoComplete="email"
                maxLength={254}
                required
                className="field"
                value={replyAddress}
                onChange={(event) => setReplyEmail(event.target.value)}
              />
            </label>
            <label className="label" htmlFor="support-subject">
              Subject
              <input
                id="support-subject"
                type="text"
                minLength={3}
                maxLength={160}
                required
                className="field"
                value={subject}
                onChange={(event) => setSubject(event.target.value)}
              />
            </label>
            <label className="label" htmlFor="support-message">
              How can we help?
              <textarea
                id="support-message"
                minLength={10}
                maxLength={5000}
                rows={8}
                required
                className="field min-h-40 resize-y"
                value={body}
                onChange={(event) => setBody(event.target.value)}
              />
            </label>
            <p className="text-xs leading-5 text-slate-500">
              Don’t include passwords, app passwords, or device local keys.
            </p>
            {sendMutation.error && <ErrorCard message={sendMutation.error.message} />}
            {sent && <p className="alert success" role="status">Your message has been sent to ChargePilot support.</p>}
            <button type="submit" className="btn-primary" disabled={sendMutation.isPending}>
              {sendMutation.isPending ? 'Sending message…' : 'Send support message'}
            </button>
          </form>
        </section>
      )}
    </div>
  )
}
