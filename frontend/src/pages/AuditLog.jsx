import React from 'react';
import { ScrollText, ShieldCheck } from 'lucide-react';
import { useApi } from '../hooks/useApi';
import { PageHeader, SectionCard, AsyncBoundary, EmptyState, Mono } from '../components/ui';

/*
 * Chain-of-custody audit trail.
 *
 * Entries were anonymous until authentication was applied: the logger accepted
 * a user id that no caller ever passed. Actions are now attributed to the
 * signed-in officer, which is the difference between "record 47 was accessed"
 * and something that stands up in court.
 */

export const AuditLog = () => {
  const { data, error, loading, reload } = useApi('/api/evidence/audit-trail', {
    params: { limit: 200 },
  });
  const events = Array.isArray(data) ? data : [];

  return (
    <div className="flex-1 min-w-0 scroll-area">
      <div className="p-5 space-y-4 max-w-[1200px]">
        <PageHeader
          breadcrumb="Evidence / Audit"
          title="Audit Log"
          description="Every action taken against evidence, attributed to the officer who took it."
        />

        <div className="card p-3 flex items-start gap-2.5">
          <ShieldCheck className="w-4 h-4 shrink-0 mt-0.5" style={{ color: 'var(--status-active)' }} />
          <p className="text-[12px] leading-relaxed" style={{ color: 'var(--text-muted)' }}>
            Vault access, media downloads, dossier exports and surveillance changes
            are recorded here with the acting officer and originating address.
          </p>
        </div>

        <SectionCard bodyClass="">
          <AsyncBoundary
            loading={loading}
            error={error}
            onRetry={reload}
            skeletonRows={8}
            isEmpty={events.length === 0}
            empty={
              <EmptyState
                icon={ScrollText}
                title="No audit events recorded yet"
                description="Actions are logged as they happen. An empty trail means nothing has been done in this deployment yet."
              />
            }
          >
            <table className="data-table">
              <thead>
                <tr>
                  <th>Time</th><th>Action</th><th>Resource</th>
                  <th>Officer</th><th>Address</th><th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {events.map((e) => (
                  <tr key={e.id}>
                    <td className="whitespace-nowrap text-[12px]" style={{ color: 'var(--text-muted)' }}>
                      {e.timestamp ? new Date(e.timestamp).toLocaleString() : '—'}
                    </td>
                    <td><Mono>{e.action}</Mono></td>
                    <td><Mono>{e.resource || '—'}</Mono></td>
                    <td className="text-[12px]">{e.user_id ? `user ${e.user_id}` : 'system'}</td>
                    <td><Mono>{e.ip_address || '—'}</Mono></td>
                    <td className="max-w-[380px] text-[12px]">
                      <span className="truncate block">{e.details || '—'}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </AsyncBoundary>
        </SectionCard>
      </div>
    </div>
  );
};
