import React from 'react';
import { Link } from 'react-router-dom';
import {
  Radar, AlertTriangle, Target, Coins, Activity, MapPin, Users,
  ArrowRight, Inbox, ShieldCheck,
} from 'lucide-react';
import { useApi } from '../hooks/useApi';
import { useAuth } from '../auth/AuthContext';
import {
  StatCard, SectionCard, PageHeader, AsyncBoundary, EmptyState, ErrorState,
  RiskBadge, StatusDot, SourceBadge, Mono, ConfidenceBadge,
} from '../components/ui';

/*
 * Operational overview.
 *
 * Every figure on this page comes from the database. The previous version fell
 * back to invented totals (147 records, 23 alerts, a fabricated network graph)
 * whenever a request failed, so an empty system and a working one looked the
 * same. Where there is nothing to show, this page says so.
 */

const relativeTime = (iso) => {
  if (!iso) return '—';
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return iso;
  const mins = Math.round((Date.now() - then.getTime()) / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return then.toLocaleDateString();
};

export const Overview = () => {
  const { user } = useAuth();
  const stats = useApi('/api/dashboard/stats');
  const activity = useApi('/api/dashboard/activity');
  const judgements = useApi('/api/correlation/key-judgements');
  const surveillance = useApi('/api/targets/surveillance-status');

  const s = stats.data;
  const pipelines = s?.pipelines || {};

  const greeting = (() => {
    const h = new Date().getHours();
    if (h < 12) return 'Good morning';
    if (h < 17) return 'Good afternoon';
    return 'Good evening';
  })();

  return (
    <div className="flex-1 min-w-0 scroll-area">
      <div className="p-5 space-y-4 max-w-[1500px]">
        <PageHeader
          title={`${greeting}${user?.username ? `, ${user.username}` : ''}`}
          description="Operational status across collection, analysis and evidence."
          actions={
            <div className="text-right text-[12px]" style={{ color: 'var(--text-muted)' }}>
              {new Date().toLocaleDateString(undefined, {
                weekday: 'short', day: 'numeric', month: 'short', year: 'numeric',
              })}
              <div className="mono">{new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</div>
            </div>
          }
        />

        {stats.error && <ErrorState error={stats.error} onRetry={stats.reload} compact />}

        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
          <StatCard icon={Radar} label="Intelligence Records"
                    value={s?.total_intelligence_records} loading={stats.loading} />
          <StatCard icon={AlertTriangle} label="High / Severe Alerts" tone="danger"
                    value={s?.threat_alerts} loading={stats.loading} />
          <StatCard icon={Target} label="Sources Watched" tone="success"
                    value={s?.active_targets} loading={stats.loading} />
          <StatCard icon={Coins} label="Wallets Tracked" tone="warning"
                    value={s?.crypto_wallets_tracked} loading={stats.loading} />
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
          <div className="xl:col-span-2 space-y-4">
            <SectionCard
              title="Recent Intelligence"
              bodyClass=""
              action={<Link to="/intelligence" className="link text-[12px] flex items-center gap-1">
                View all <ArrowRight className="w-3 h-3" />
              </Link>}
            >
              <AsyncBoundary
                loading={activity.loading}
                error={activity.error}
                onRetry={activity.reload}
                skeletonRows={5}
                isEmpty={Array.isArray(activity.data) && activity.data.length === 0}
                empty={
                  <EmptyState
                    icon={Inbox}
                    title="No intelligence collected yet"
                    description="Add a source under Sources and the scheduler will begin collecting from it. Records appear here as they arrive."
                    action={<Link to="/targets" className="btn btn-primary">Add a source</Link>}
                  />
                }
              >
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Time</th><th>Source</th><th>Summary</th><th>Risk</th><th>Hash</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(activity.data || []).map((row) => (
                      <tr key={row.id}>
                        <td className="whitespace-nowrap" style={{ color: 'var(--text-muted)' }}>
                          {row.created_at}
                        </td>
                        <td><SourceBadge type={row.source_type} /></td>
                        <td className="max-w-[380px]">
                          <div className="truncate-2" style={{ color: 'var(--text-primary)' }}>
                            {row.snippet || '—'}
                          </div>
                          {row.url && <Mono className="block truncate">{row.url}</Mono>}
                        </td>
                        <td><RiskBadge level={row.threat_level} /></td>
                        <td><Mono>{row.sha256}</Mono></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </AsyncBoundary>
            </SectionCard>

            <SectionCard title="Key Judgements"
                         action={<Link to="/network" className="link text-[12px]">Network analysis</Link>}>
              <AsyncBoundary
                loading={judgements.loading}
                error={judgements.error}
                onRetry={judgements.reload}
                isEmpty={!judgements.data?.key_judgements?.length}
                empty={
                  <EmptyState
                    icon={Users}
                    title="Not enough data to draw conclusions"
                    description="Correlation needs several records from independent sources before it will assert a pattern. Findings appear here once that threshold is met."
                  />
                }
              >
                <div className="space-y-2.5">
                  {(judgements.data?.key_judgements || []).map((j, i) => (
                    <div key={i} className="rounded-lg p-3"
                         style={{ background: 'var(--surface-sunken)', border: '1px solid var(--border)' }}>
                      <div className="flex items-start justify-between gap-3">
                        <p className="text-[13px] font-medium" style={{ color: 'var(--text-primary)' }}>
                          {j.judgement}
                        </p>
                        <ConfidenceBadge level={j.confidence} />
                      </div>
                      <p className="text-[12px] mt-1.5 leading-relaxed" style={{ color: 'var(--text-muted)' }}>
                        {j.evidence}
                      </p>
                    </div>
                  ))}
                </div>
              </AsyncBoundary>
            </SectionCard>
          </div>

          <div className="space-y-4">
            <SectionCard title="Collection Pipelines">
              {stats.loading ? (
                <div className="space-y-2">
                  {[0, 1, 2].map((i) => (
                    <div key={i} className="h-8 rounded animate-pulse" style={{ background: 'var(--surface-hover)' }} />
                  ))}
                </div>
              ) : (
                <div className="space-y-2.5">
                  {Object.entries(pipelines).map(([key, p]) => (
                    <div key={key} className="flex items-center justify-between">
                      <StatusDot status={p.status} label={p.label || key} />
                      <span className="text-[13px] font-medium" style={{ color: 'var(--text-primary)' }}>
                        {p.records}
                      </span>
                    </div>
                  ))}
                  {s?.proxies && (
                    <div className="pt-2.5 flex items-center justify-between"
                         style={{ borderTop: '1px solid var(--border)' }}>
                      <span className="text-[13px]" style={{ color: 'var(--text-secondary)' }}>
                        Proxy pool
                      </span>
                      <span className="text-[13px] mono" style={{ color: 'var(--text-muted)' }}>
                        {s.proxies.alive_proxies ?? 0} alive
                      </span>
                    </div>
                  )}
                </div>
              )}
            </SectionCard>

            <SectionCard title="Surveillance"
                         action={<Link to="/targets" className="link text-[12px]">Manage</Link>}>
              <AsyncBoundary
                loading={surveillance.loading}
                error={surveillance.error}
                onRetry={surveillance.reload}
                isEmpty={false}
              >
                <div className="space-y-2.5 text-[13px]">
                  <div className="flex items-center justify-between">
                    <StatusDot
                      status={surveillance.data?.scheduler_running ? 'ACTIVE' : 'PAUSED'}
                      label={surveillance.data?.scheduler_running ? 'Scheduler running' : 'Scheduler stopped'}
                    />
                  </div>
                  {[
                    ['Sources active', surveillance.data?.targets_active],
                    ['Sources paused', surveillance.data?.targets_paused],
                    ['Failing', surveillance.data?.targets_failing],
                    ['Due now', surveillance.data?.targets_due_now],
                  ].map(([label, value]) => (
                    <div key={label} className="flex items-center justify-between">
                      <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
                      <span className="font-medium" style={{ color: 'var(--text-primary)' }}>{value ?? 0}</span>
                    </div>
                  ))}
                </div>
              </AsyncBoundary>
            </SectionCard>

            <SectionCard title="Quick Actions">
              <div className="grid grid-cols-2 gap-2">
                {[
                  { to: '/targets', icon: Target, label: 'Add source' },
                  { to: '/intelligence', icon: Radar, label: 'Search intel' },
                  { to: '/simulator', icon: Activity, label: 'Triage text' },
                  { to: '/geospatial', icon: MapPin, label: 'Hotspots' },
                ].map(({ to, icon: Icon, label }) => (
                  <Link
                    key={to}
                    to={to}
                    className="flex flex-col items-center gap-1.5 rounded-lg py-3 transition"
                    style={{ background: 'var(--surface-sunken)', border: '1px solid var(--border)' }}
                  >
                    <Icon className="w-4 h-4" style={{ color: 'var(--accent)' }} />
                    <span className="text-[12px]" style={{ color: 'var(--text-secondary)' }}>{label}</span>
                  </Link>
                ))}
              </div>
            </SectionCard>

            <div className="card p-3 flex items-start gap-2.5">
              <ShieldCheck className="w-4 h-4 shrink-0 mt-0.5" style={{ color: 'var(--status-active)' }} />
              <p className="text-[11px] leading-relaxed" style={{ color: 'var(--text-muted)' }}>
                Every record is SHA-256 hashed on collection and access is logged
                against your badge for chain of custody.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
