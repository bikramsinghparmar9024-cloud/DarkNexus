import React, { useState } from 'react';
import {
  Plus, Play, Pause, Trash2, Target, RefreshCw, AlertTriangle, Loader2,
} from 'lucide-react';
import { useApi, useMutation } from '../hooks/useApi';
import {
  PageHeader, SectionCard, AsyncBoundary, EmptyState, StatusDot, Mono,
  ErrorState, StatCard,
} from '../components/ui';

/*
 * Surveillance sources.
 *
 * This replaces the Surface Web page, whose "Crawl" button ran a two-second
 * timer and then added a random number between one and five to a counter. The
 * real endpoints existed and went unused; there was also no way to register a
 * source at all, because /api/targets did not exist.
 *
 * Everything here drives the scheduler: adding a source puts it under
 * collection, pausing it stops collection, and the failure counts are what the
 * scheduler actually recorded.
 */

const SOURCE_TYPES = [
  { id: 'TELEGRAM', label: 'Telegram channel', placeholder: 't.me/channel_name' },
  { id: 'SURFACE_WEB', label: 'Website', placeholder: 'https://example.com/listings' },
  { id: 'DARK_WEB', label: 'Onion service', placeholder: 'http://….onion' },
];

const INTERVALS = [
  { value: 5, label: 'Every 5 minutes' },
  { value: 15, label: 'Every 15 minutes' },
  { value: 60, label: 'Hourly' },
  { value: 360, label: 'Every 6 hours' },
  { value: 1440, label: 'Daily' },
];

export const Sources = () => {
  const targets = useApi('/api/targets');
  const status = useApi('/api/targets/surveillance-status');
  const post = useMutation('post');
  const patch = useMutation('patch');
  const del = useMutation('delete');

  const [showForm, setShowForm] = useState(false);
  const [identifier, setIdentifier] = useState('');
  const [sourceType, setSourceType] = useState('TELEGRAM');
  const [interval, setInterval] = useState(60);
  const [formError, setFormError] = useState(null);
  const [runningNow, setRunningNow] = useState(false);
  const [actionError, setActionError] = useState(null);
  const [removingId, setRemovingId] = useState(null);

  const refresh = () => { targets.reload(); status.reload(); };

  const addSource = async (e) => {
    e.preventDefault();
    setFormError(null);
    try {
      await post.run('/api/targets', {
        identifier: identifier.trim(),
        source_type: sourceType,
        scan_interval_minutes: Number(interval),
      });
      setIdentifier('');
      setShowForm(false);
      refresh();
    } catch (err) {
      setFormError(err.described?.message || 'Could not add this source.');
    }
  };

  // Both handlers used to swallow every error with .catch(() => {}). A failed
  // request then looked exactly like a button that does nothing: no row
  // change, no message, nothing in the interface at all.
  const toggle = async (target) => {
    setActionError(null);
    try {
      await patch.run(`/api/targets/${target.id}`, {
        status: target.status === 'ACTIVE' ? 'PAUSED' : 'ACTIVE',
      });
    } catch (err) {
      setActionError(err.described?.message || 'Could not change this source.');
    }
    refresh();
  };

  const remove = async (target) => {
    // Removing a source is not reversible from this screen, so it is
    // confirmed. Collected records survive - that is worth saying here rather
    // than only in the footnote.
    const ok = window.confirm(
      `Remove "${target.identifier}" from surveillance?

` +
      'Future collection stops. Records already collected from it are kept.');
    if (!ok) return;

    setActionError(null);
    setRemovingId(target.id);
    try {
      await del.run(`/api/targets/${target.id}`);
    } catch (err) {
      setActionError(err.described?.message
        || `Could not remove "${target.identifier}".`);
    } finally {
      setRemovingId(null);
    }
    refresh();
  };

  const collectNow = async () => {
    setRunningNow(true);
    try {
      await post.run('/api/targets/run-surveillance-now');
      refresh();
    } finally {
      setRunningNow(false);
    }
  };

  const list = targets.data?.targets || [];
  const placeholder = SOURCE_TYPES.find((t) => t.id === sourceType)?.placeholder;

  return (
    <div className="flex-1 min-w-0 scroll-area">
      <div className="p-5 space-y-4 max-w-[1400px]">
        <PageHeader
          breadcrumb="Collection / Sources"
          title="Surveillance Sources"
          description="Sources revisited automatically by the collection scheduler."
          actions={
            <>
              <button onClick={collectNow} className="btn btn-secondary" disabled={runningNow}>
                {runningNow ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
                Collect now
              </button>
              <button onClick={() => setShowForm((v) => !v)} className="btn btn-primary">
                <Plus className="w-3.5 h-3.5" /> Add source
              </button>
            </>
          }
        />

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <StatCard icon={Target} label="Active" value={status.data?.targets_active}
                    loading={status.loading} tone="success" />
          <StatCard icon={Pause} label="Paused" value={status.data?.targets_paused}
                    loading={status.loading} />
          <StatCard icon={AlertTriangle} label="Failing" value={status.data?.targets_failing}
                    loading={status.loading} tone="danger" />
          <StatCard icon={RefreshCw} label="Due now" value={status.data?.targets_due_now}
                    loading={status.loading} tone="warning" />
        </div>

        {showForm && (
          <SectionCard title="Add a source">
            <form onSubmit={addSource} className="space-y-3">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div>
                  <label className="label block mb-1">Type</label>
                  <select className="input" value={sourceType}
                          onChange={(e) => setSourceType(e.target.value)}>
                    {SOURCE_TYPES.map((t) => (
                      <option key={t.id} value={t.id}>{t.label}</option>
                    ))}
                  </select>
                </div>
                <div className="md:col-span-2">
                  <label className="label block mb-1">Identifier</label>
                  <input className="input" placeholder={placeholder} value={identifier}
                         onChange={(e) => setIdentifier(e.target.value)} />
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div>
                  <label className="label block mb-1">Check every</label>
                  <select className="input" value={interval}
                          onChange={(e) => setInterval(e.target.value)}>
                    {INTERVALS.map((i) => (
                      <option key={i.value} value={i.value}>{i.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              {sourceType === 'DARK_WEB' && (
                <p className="text-[12px]" style={{ color: 'var(--risk-medium-text)' }}>
                  Onion collection needs a running Tor daemon. Without it this
                  source will fail every attempt and be paused automatically.
                </p>
              )}
              {formError && <ErrorState error={{ message: formError }} compact />}

              <div className="flex gap-2">
                <button type="submit" className="btn btn-primary" disabled={!identifier.trim() || post.busy}>
                  {post.busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
                  Add and begin collecting
                </button>
                <button type="button" className="btn btn-ghost" onClick={() => setShowForm(false)}>
                  Cancel
                </button>
              </div>
            </form>
          </SectionCard>
        )}

        {actionError && (
          <ErrorState error={{ message: actionError }} compact />
        )}

        <SectionCard bodyClass="">
          <AsyncBoundary
            loading={targets.loading}
            error={targets.error}
            onRetry={targets.reload}
            skeletonRows={5}
            isEmpty={list.length === 0}
            empty={
              <EmptyState
                icon={Target}
                title="No sources under surveillance"
                description="Add a Telegram channel or a website and the scheduler will revisit it on the interval you choose, filing whatever it finds as intelligence."
                action={<button onClick={() => setShowForm(true)} className="btn btn-primary">
                  <Plus className="w-3.5 h-3.5" /> Add the first source
                </button>}
              />
            }
          >
            <table className="data-table">
              <thead>
                <tr>
                  <th>Status</th><th>Identifier</th><th>Type</th><th>Interval</th>
                  <th>Collected</th><th>Last checked</th><th>Last error</th><th />
                </tr>
              </thead>
              <tbody>
                {list.map((t) => (
                  <tr key={t.id}>
                    <td><StatusDot status={t.status} label={t.status} /></td>
                    <td><Mono>{t.identifier}</Mono></td>
                    <td className="text-[12px]">{t.source_type.replace('_', ' ').toLowerCase()}</td>
                    <td className="text-[12px]">{t.scan_interval_minutes}m</td>
                    <td className="font-medium" style={{ color: 'var(--text-primary)' }}>
                      {t.records_in_db ?? t.total_records_collected ?? 0}
                    </td>
                    <td className="text-[12px] whitespace-nowrap">
                      {t.last_scraped_at ? new Date(t.last_scraped_at).toLocaleString() : 'never'}
                    </td>
                    <td className="max-w-[220px]">
                      {t.last_error ? (
                        <span className="text-[12px] truncate block" style={{ color: 'var(--risk-high-text)' }}>
                          {t.last_error}
                        </span>
                      ) : (
                        <span className="text-[12px]" style={{ color: 'var(--text-muted)' }}>—</span>
                      )}
                      {t.consecutive_failures > 0 && (
                        <span className="text-[11px]" style={{ color: 'var(--risk-medium-text)' }}>
                          {t.consecutive_failures} consecutive failure(s)
                        </span>
                      )}
                    </td>
                    <td className="whitespace-nowrap text-right">
                      <button onClick={() => toggle(t)} className="btn btn-ghost p-1.5"
                              title={t.status === 'ACTIVE' ? 'Pause' : 'Resume'}>
                        {t.status === 'ACTIVE' ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
                      </button>
                      <button onClick={() => remove(t)} className="btn btn-ghost p-1.5"
                              disabled={removingId === t.id}
                              title="Remove from surveillance (collected records are kept)">
                        {removingId === t.id
                          ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          : <Trash2 className="w-3.5 h-3.5" />}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </AsyncBoundary>
        </SectionCard>

        <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
          Removing a source stops future collection. Records already gathered from
          it are retained — evidence does not disappear because you stopped watching.
        </p>
      </div>
    </div>
  );
};
