import { useQuery } from '@tanstack/react-query'

import { useSearchParams } from 'react-router-dom'

import { apiFetch } from '../../shared/api'

import { type EventPage } from '../../shared/types'

import { LoadingCard, ErrorCard } from '../../shared/components'

import { formatTimestamp } from '../../shared/lib'

export function EventsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const requestedPage = Number(searchParams.get('page') || 1)
  const page = Number.isInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1
  const requestedSize = Number(searchParams.get('per_page') || 50)
  const perPage = [50, 100, 500].includes(requestedSize) ? requestedSize : 50
  const { data, isLoading, error } = useQuery({
    queryKey: ['events', page, perPage],
    queryFn: async () => apiFetch<EventPage>(`/api/v1/events/page?page=${page}&per_page=${perPage}`),
  })

  if (isLoading) return <LoadingCard />
  if (error) return <ErrorCard message={error.message} />
  if (!data) return <ErrorCard message="The event page returned no data." />

  return (
    <div className="space-y-6">
      <div className="page-header"><div><p className="eyebrow">Audit trail</p><h1>Automation Events</h1></div></div>
      <section className="panel table-panel">
        <div className="panel-header events-toolbar flex-wrap">
          <h3>Recent activity</h3>
          <label className="events-page-size flex items-center gap-2 text-sm">
            <span className="text-xs font-semibold text-slate-600">Show</span>
            <select className="events-page-size-select min-h-9 rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-sm text-slate-800" value={perPage} onChange={(event) => setSearchParams({ page: '1', per_page: event.target.value })}>
              {[50, 100, 500].map((size) => <option key={size} value={size}>{size} lines</option>)}
            </select>
          </label>
        </div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Time</th><th>Type</th><th>Device</th><th>Battery</th><th>Activity</th><th>Result</th></tr></thead>
            <tbody>
              {data.items.map((event) => <tr key={event.id}>
                <td>{formatTimestamp(event.created_at ?? null)}</td>
                <td className="strong-cell">{event.event_type}</td>
                <td>{event.endpoint ?? 'unknown'}</td>
                <td>{event.battery ?? 'n/a'}</td>
                <td>{event.activity ?? event.reason ?? event.event_type}</td>
                <td><span className={`badge ${event.success ? 'success' : 'muted'}`}>{event.success ? 'Success' : 'Failed'}</span></td>
              </tr>)}
              {!data.items.length && <tr><td colSpan={6} className="empty-state">No automation events have been recorded yet.</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="flex flex-col gap-3 border-t border-slate-200 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-slate-500" aria-live="polite">{data.total_events ? `Showing ${data.first_row}–${data.last_row} of ${data.total_events} events` : 'No events to display'}</p>
          <nav className="flex items-center gap-1.5" aria-label="Event log pages">
            <button type="button" className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 transition hover:border-blue-300 hover:text-blue-700 disabled:cursor-not-allowed disabled:text-slate-400" disabled={data.page <= 1} onClick={() => setSearchParams({ page: String(data.page - 1), per_page: String(perPage) })}>Previous</button>
            <span className="px-2 text-xs font-semibold text-slate-600">Page {data.page} of {data.total_pages}</span>
            <button type="button" className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 transition hover:border-blue-300 hover:text-blue-700 disabled:cursor-not-allowed disabled:text-slate-400" disabled={data.page >= data.total_pages} onClick={() => setSearchParams({ page: String(data.page + 1), per_page: String(perPage) })}>Next</button>
          </nav>
        </div>
      </section>
    </div>
  )
}
