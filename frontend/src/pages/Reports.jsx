import React, { useState } from 'react';
import {
  FileText, Download, Loader2, ScrollText, CheckSquare, Square, Scale,
} from 'lucide-react';
import { useApi, useMutation } from '../hooks/useApi';
import { useAuth } from '../auth/AuthContext';
import {
  PageHeader, SectionCard, AsyncBoundary, EmptyState, RiskBadge, SourceBadge,
  Mono, ErrorState,
} from '../components/ui';
import { API_BASE_URL } from '../api/client';

/*
 * Evidence dossiers.
 *
 * The previous page held DEMO_REPORTS and DEMO_AUDIT_LOG and made no request
 * of any kind, so it listed reports that had never been generated. A dossier
 * is now built from records the investigator selects, by the endpoint that
 * actually produces the PDF.
 */

// Resolved once in api/client.js. Repeating the fallback here is how
// this file kept pointing at 127.0.0.1 after the shared client was
// fixed for same-origin deployment.
const API_BASE = API_BASE_URL;

export const Reports = () => {
  const { user } = useAuth();
  const records = useApi('/api/data', { params: { limit: 100 } });
  const generate = useMutation('post');

  const [selected, setSelected] = useState(() => new Set());
  const [notes, setNotes] = useState('');
  const [caseNumber, setCaseNumber] = useState('');
  const [generated, setGenerated] = useState([]);

  const list = Array.isArray(records.data) ? records.data : [];

  const toggle = (id) => setSelected((prev) => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });

  const toggleAll = () => setSelected((prev) =>
    prev.size === list.length ? new Set() : new Set(list.map((r) => r.id)));

  const buildDossier = async () => {
    if (!selected.size) return;
    try {
      const data = await generate.run('/api/evidence/generate-dossier', {
        investigator_badge: user?.badge_number || user?.username || 'UNKNOWN',
        record_ids: Array.from(selected),
        case_notes: [caseNumber && `Case: ${caseNumber}`, notes].filter(Boolean).join('\n'),
      });
      setGenerated((prev) => [{ ...data, at: new Date(), count: selected.size }, ...prev]);
      setSelected(new Set());
      setNotes('');
    } catch {
      // Surfaced through generate.error.
    }
  };

  return (
    <div className="flex-1 min-w-0 scroll-area">
      <div className="p-5 space-y-4 max-w-[1400px]">
        <PageHeader
          breadcrumb="Evidence / Reports"
          title="Evidence Dossiers"
          description="Compile selected records into a court-ready package with their hashes intact."
        />

        <div className="card p-3 flex items-start gap-2.5">
          <Scale className="w-4 h-4 shrink-0 mt-0.5" style={{ color: 'var(--accent)' }} />
          <p className="text-[12px] leading-relaxed" style={{ color: 'var(--text-muted)' }}>
            Each record carries the SHA-256 computed when it was collected. The dossier
            reproduces those hashes so the exported package can be checked against the
            evidence vault, supporting a Section 65B certificate.
          </p>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
          <div className="xl:col-span-2">
            <SectionCard
              title="Select records"
              bodyClass=""
              action={
                <button onClick={toggleAll} className="btn btn-ghost text-[12px]"
                        disabled={!list.length}>
                  {selected.size === list.length && list.length ? 'Clear all' : 'Select all'}
                </button>
              }
            >
              <AsyncBoundary
                loading={records.loading}
                error={records.error}
                onRetry={records.reload}
                skeletonRows={6}
                isEmpty={list.length === 0}
                empty={
                  <EmptyState
                    icon={FileText}
                    title="No records available to compile"
                    description="A dossier is built from collected intelligence. Add a source and collect before generating one."
                  />
                }
              >
                <table className="data-table">
                  <thead>
                    <tr>
                      <th className="w-8" /><th>Collected</th><th>Source</th>
                      <th>Content</th><th>Risk</th><th>Hash</th>
                    </tr>
                  </thead>
                  <tbody>
                    {list.map((r) => {
                      const isOn = selected.has(r.id);
                      return (
                        <tr key={r.id} onClick={() => toggle(r.id)}
                            className={`cursor-pointer ${isOn ? 'is-selected' : ''}`}>
                          <td>
                            {isOn
                              ? <CheckSquare className="w-4 h-4" style={{ color: 'var(--accent)' }} />
                              : <Square className="w-4 h-4" style={{ color: 'var(--text-muted)' }} />}
                          </td>
                          <td className="whitespace-nowrap text-[12px]"
                              style={{ color: 'var(--text-muted)' }}>{r.created_at}</td>
                          <td><SourceBadge type={r.source_type} /></td>
                          <td className="max-w-[300px]">
                            <span className="truncate block" style={{ color: 'var(--text-primary)' }}>
                              {r.cleaned_text?.slice(0, 120) || '—'}
                            </span>
                          </td>
                          <td><RiskBadge level={r.threat_level} /></td>
                          <td><Mono>{r.sha256_hash?.slice(0, 12)}…</Mono></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </AsyncBoundary>
            </SectionCard>
          </div>

          <div className="space-y-4">
            <SectionCard title="Compile dossier">
              <div className="space-y-3">
                <div>
                  <label className="label block mb-1">Case / FIR number</label>
                  <input className="input" value={caseNumber} placeholder="Optional"
                         onChange={(e) => setCaseNumber(e.target.value)} />
                </div>
                <div>
                  <label className="label block mb-1">Investigator notes</label>
                  <textarea className="input" rows={4} value={notes}
                            placeholder="Context an officer reading this package would need."
                            onChange={(e) => setNotes(e.target.value)} />
                </div>

                <div className="rounded-lg px-3 py-2 text-[12px]"
                     style={{ background: 'var(--surface-sunken)', color: 'var(--text-secondary)' }}>
                  {selected.size === 0
                    ? 'No records selected.'
                    : `${selected.size} record${selected.size === 1 ? '' : 's'} selected.`}
                  {user?.badge_number && (
                    <div className="mt-1" style={{ color: 'var(--text-muted)' }}>
                      Signed by <span className="mono">{user.badge_number}</span>
                    </div>
                  )}
                </div>

                {generate.error && <ErrorState error={generate.error} compact />}

                <button onClick={buildDossier} className="btn btn-primary w-full justify-center"
                        disabled={!selected.size || generate.busy}>
                  {generate.busy
                    ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    : <FileText className="w-3.5 h-3.5" />}
                  Generate dossier
                </button>
              </div>
            </SectionCard>

            <SectionCard title="Generated this session">
              {generated.length === 0 ? (
                <p className="text-[13px]" style={{ color: 'var(--text-muted)' }}>
                  Dossiers you generate appear here with a download link. The list is
                  not persisted — the files themselves live in the reports directory
                  on the server.
                </p>
              ) : (
                <div className="space-y-2">
                  {generated.map((g, i) => (
                    <div key={i} className="flex items-center justify-between gap-2 rounded-lg p-2.5"
                         style={{ background: 'var(--surface-sunken)', border: '1px solid var(--border)' }}>
                      <div className="min-w-0">
                        <Mono className="block truncate">{g.report_id || 'dossier'}</Mono>
                        <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                          {g.count} record(s) · {g.at.toLocaleTimeString()}
                        </span>
                      </div>
                      {g.report_id && (
                        <a className="btn btn-secondary shrink-0"
                           href={`${API_BASE}/api/evidence/download/${g.report_id}`}
                           target="_blank" rel="noreferrer">
                          <Download className="w-3.5 h-3.5" /> PDF
                        </a>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </SectionCard>

            <div className="card p-3 flex items-start gap-2.5">
              <ScrollText className="w-4 h-4 shrink-0 mt-0.5" style={{ color: 'var(--text-muted)' }} />
              <p className="text-[11px] leading-relaxed" style={{ color: 'var(--text-muted)' }}>
                Dossier generation is recorded in the audit log against your badge.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
