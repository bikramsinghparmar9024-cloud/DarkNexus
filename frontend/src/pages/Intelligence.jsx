import React, { useState, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Search, Filter, Inbox, Image as ImageIcon, MapPin, Hash, Link2,
  Fingerprint, Coins, Phone, AtSign, AlertTriangle,
} from 'lucide-react';
import { useApi } from '../hooks/useApi';
import {
  PageHeader, SectionCard, AsyncBoundary, EmptyState, RiskBadge, SourceBadge,
  DetailPanel, Field, Mono, ConfidenceBadge,
} from '../components/ui';

/*
 * Unified intelligence feed.
 *
 * This replaces three separate pages - Surface Web, Dark Web and Telegram -
 * none of which called the backend. They rendered constants, and the Surface
 * Web "Crawl" button ran a two-second timer and added a random number to a
 * counter.
 *
 * One feed with a source filter is also closer to how the records are actually
 * used: an investigator looks for a wallet or a handle, not for "things that
 * arrived over Telegram".
 */

const SOURCE_FILTERS = [
  { id: '', label: 'All' },
  { id: 'TELEGRAM', label: 'Telegram' },
  { id: 'DARK_WEB', label: 'Dark Web' },
  { id: 'SURFACE_WEB', label: 'Surface Web' },
];

const RISK_FILTERS = ['', 'SEVERE', 'HIGH', 'MEDIUM', 'LOW'];

const analysisOf = (record) => record?.metadata?.analysis || {};

/*
 * A record typed into the Live Triage console reads identically to one a
 * scraper collected, which is how synthetic preset text ended up looking like
 * intelligence. Anything not collected automatically is labelled here.
 */
const OriginBadge = ({ method }) => {
  if (!method || method === 'AUTOMATED_COLLECTION') return null;
  const injected = method === 'MANUAL_IMPORT';
  return (
    <span
      className="pill"
      title={injected
        ? 'Entered by hand through the Live Triage console, not collected from a source'
        : 'Collected before provenance was recorded; origin unverified'}
      style={{
        background: 'var(--risk-medium-bg)',
        color: 'var(--risk-medium-text)',
        borderColor: 'var(--risk-medium-border)',
      }}
    >
      {injected ? 'injected' : 'origin unknown'}
    </span>
  );
};

export const Intelligence = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [sourceType, setSourceType] = useState('');
  const [threatLevel, setThreatLevel] = useState('');
  const [search, setSearch] = useState(searchParams.get('q') || '');
  const [submitted, setSubmitted] = useState(searchParams.get('q') || '');
  const [selectedId, setSelectedId] = useState(null);
  const [tab, setTab] = useState('overview');

  const params = useMemo(() => ({
    source_type: sourceType || undefined,
    threat_level: threatLevel || undefined,
    search: submitted || undefined,
    limit: 100,
  }), [sourceType, threatLevel, submitted]);

  const { data, error, loading, reload } = useApi('/api/data', { params });
  const records = Array.isArray(data) ? data : [];
  const selected = records.find((r) => r.id === selectedId) || null;
  const media = useApi(`/api/media/record/${selectedId}`, { skip: !selectedId });

  const applySearch = (e) => {
    e.preventDefault();
    setSubmitted(search.trim());
    setSearchParams(search.trim() ? { q: search.trim() } : {});
  };

  const counts = useMemo(() => {
    const out = {};
    records.forEach((r) => { out[r.source_type] = (out[r.source_type] || 0) + 1; });
    return out;
  }, [records]);

  const analysis = analysisOf(selected);
  const entities = analysis.entities || {};
  const threat = analysis.threat || {};
  const wallets = [
    ...(entities.crypto_wallets?.btc || []),
    ...(entities.crypto_wallets?.eth || []),
  ];

  return (
    <>
      <div className="flex-1 min-w-0 scroll-area">
        <div className="p-5 space-y-4">
          <PageHeader
            breadcrumb="Collection / Intelligence"
            title="Intelligence"
            description="Records collected from every monitored source, with the analysis applied to each."
          />

          <SectionCard bodyClass="p-3">
            <form onSubmit={applySearch} className="flex flex-wrap items-center gap-2">
              <div className="relative flex-1 min-w-[220px]">
                <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none"
                        style={{ color: 'var(--text-muted)' }} />
                <input
                  className="input pl-8"
                  placeholder="Search text, handles, wallets…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </div>

              <select className="input w-auto" value={threatLevel}
                      onChange={(e) => setThreatLevel(e.target.value)}>
                {RISK_FILTERS.map((r) => (
                  <option key={r} value={r}>{r ? `Risk: ${r}` : 'All risk levels'}</option>
                ))}
              </select>

              <button type="submit" className="btn btn-primary">
                <Filter className="w-3.5 h-3.5" /> Apply
              </button>
            </form>

            <div className="flex items-center gap-1.5 mt-3 flex-wrap">
              {SOURCE_FILTERS.map((f) => {
                const active = sourceType === f.id;
                const count = f.id ? counts[f.id] : records.length;
                return (
                  <button
                    key={f.id || 'all'}
                    onClick={() => setSourceType(f.id)}
                    className="pill transition"
                    style={{
                      background: active ? 'var(--accent-soft)' : 'var(--surface-sunken)',
                      color: active ? 'var(--accent)' : 'var(--text-secondary)',
                      borderColor: active ? 'var(--accent-border)' : 'var(--border)',
                    }}
                  >
                    {f.label}
                    {count !== undefined && <span style={{ opacity: 0.7 }}>{count}</span>}
                  </button>
                );
              })}
            </div>
          </SectionCard>

          <SectionCard bodyClass="">
            <AsyncBoundary
              loading={loading}
              error={error}
              onRetry={reload}
              skeletonRows={8}
              isEmpty={records.length === 0}
              empty={
                <EmptyState
                  icon={Inbox}
                  title={submitted ? 'No records match this search' : 'No intelligence collected yet'}
                  description={
                    submitted
                      ? 'Try broader wording, or clear the filters. Only collected records are searched — this does not query the internet.'
                      : 'Add a source under Sources and the scheduler will begin collecting. Records appear here as they arrive.'
                  }
                />
              }
            >
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Collected</th><th>Source</th><th>Author</th>
                    <th>Content</th><th>Risk</th><th>Hash</th>
                  </tr>
                </thead>
                <tbody>
                  {records.map((r) => (
                    <tr
                      key={r.id}
                      onClick={() => { setSelectedId(r.id); setTab('overview'); }}
                      className={`cursor-pointer ${selectedId === r.id ? 'is-selected' : ''}`}
                    >
                      <td className="whitespace-nowrap" style={{ color: 'var(--text-muted)' }}>
                        {r.created_at || '—'}
                      </td>
                      <td><SourceBadge type={r.source_type} /></td>
                      <td className="mono text-[12px]">
                        <div className="flex items-center gap-1.5">
                          <span>{r.author || '—'}</span>
                          <OriginBadge method={r.acquisition_method} />
                        </div>
                      </td>
                      <td className="max-w-[420px]">
                        <div className="truncate-2" style={{ color: 'var(--text-primary)' }}>
                          {r.cleaned_text?.slice(0, 200) || '—'}
                        </div>
                      </td>
                      <td><RiskBadge level={r.threat_level} /></td>
                      <td><Mono>{r.sha256_hash?.slice(0, 12)}…</Mono></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </AsyncBoundary>
          </SectionCard>
        </div>
      </div>

      <DetailPanel
        open={Boolean(selected)}
        onClose={() => setSelectedId(null)}
        subtitle={selected ? `Record ${selected.id}` : ''}
        title={selected?.author || selected?.source_type || ''}
        badge={selected && <RiskBadge level={selected.threat_level} />}
        activeTab={tab}
        onTabChange={setTab}
        tabs={[
          { id: 'overview', label: 'Overview' },
          { id: 'entities', label: 'Entities' },
          { id: 'media', label: 'Media', count: media.data?.count },
        ]}
      >
        {tab === 'overview' && selected && (
          <>
            <div className="space-y-2">
              <Field label="Source"><SourceBadge type={selected.source_type} /></Field>
              <Field label="Collected" value={selected.created_at} />
              <Field label="Origin">
                {selected.acquisition_method === 'AUTOMATED_COLLECTION'
                  ? 'Collected automatically from a monitored source'
                  : selected.acquisition_method === 'MANUAL_IMPORT'
                    ? 'Entered by hand through Live Triage — not collected'
                    : 'Unknown (predates provenance tracking)'}
              </Field>
              <Field label="Author" value={selected.author} mono />
              <Field label="Link">
                {selected.source_url ? (
                  <a href={selected.source_url} target="_blank" rel="noreferrer"
                     className="link inline-flex items-center gap-1 break-all">
                    <Link2 className="w-3 h-3 shrink-0" />
                    <span className="mono text-[12px]">{selected.source_url}</span>
                  </a>
                ) : '—'}
              </Field>
              <Field label="SHA-256"><Mono>{selected.sha256_hash}</Mono></Field>
            </div>

            {threat.score_explanation && (
              <div className="rounded-lg p-3"
                   style={{ background: 'var(--surface-sunken)', border: '1px solid var(--border)' }}>
                <div className="label mb-1.5">Why this risk level</div>
                <p className="text-[12px] leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                  {threat.score_explanation}
                </p>
                {threat.rule_threat_level && threat.rule_threat_level !== threat.threat_level && (
                  <p className="text-[12px] mt-2 leading-relaxed" style={{ color: 'var(--text-muted)' }}>
                    Keyword score alone gave <strong>{threat.rule_threat_level}</strong>.
                    {threat.semantic_adjustment?.reason
                      ? ` Adjusted because ${threat.semantic_adjustment.reason}.`
                      : ''}
                  </p>
                )}
                {threat.suppressed_reason && (
                  <p className="text-[12px] mt-2 leading-relaxed" style={{ color: 'var(--risk-medium-text)' }}>
                    {threat.suppressed_reason}
                  </p>
                )}
              </div>
            )}

            <div>
              <div className="label mb-1.5">Content</div>
              <div className="rounded-lg p-3 text-[12px] leading-relaxed whitespace-pre-wrap max-h-72 scroll-area"
                   style={{ background: 'var(--surface-sunken)', border: '1px solid var(--border)', color: 'var(--text-secondary)' }}>
                {selected.cleaned_text || '—'}
              </div>
            </div>
          </>
        )}

        {tab === 'entities' && (
          <div className="space-y-3">
            {[
              { icon: AlertTriangle, label: 'Substances', items: entities.drugs },
              { icon: MapPin, label: 'Locations', items: entities.locations },
              { icon: AtSign, label: 'Handles', items: entities.handles },
              { icon: Phone, label: 'Phone numbers', items: entities.phones },
              { icon: Coins, label: 'Wallets (verified)', items: wallets, mono: true },
              { icon: Fingerprint, label: 'PGP fingerprints', items: entities.pgp_fingerprints, mono: true },
              { icon: Hash, label: 'UPI identifiers', items: entities.upi_ids, mono: true },
            ].map(({ icon: Icon, label, items, mono }) => (
              <div key={label}>
                <div className="label flex items-center gap-1.5 mb-1.5">
                  <Icon className="w-3 h-3" /> {label}
                </div>
                {items?.length ? (
                  <div className="flex flex-wrap gap-1.5">
                    {items.map((item, i) => (
                      <span key={i} className={`pill ${mono ? 'mono' : ''}`}
                            style={{ background: 'var(--surface-sunken)', color: 'var(--text-secondary)', borderColor: 'var(--border)' }}>
                        {String(item)}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="text-[12px]" style={{ color: 'var(--text-muted)' }}>None found</p>
                )}
              </div>
            ))}

            {entities.crypto_wallets_unverified?.length > 0 && (
              <div className="rounded-lg p-3"
                   style={{ background: 'var(--risk-medium-bg)', border: '1px solid var(--risk-medium-border)' }}>
                <div className="label mb-1" style={{ color: 'var(--risk-medium-text)' }}>
                  Unverified wallet strings
                </div>
                <p className="text-[11px] leading-relaxed mb-2" style={{ color: 'var(--risk-medium-text)' }}>
                  These look like addresses but failed checksum validation — likely
                  mistyped or misread. Not traced or cited as fact.
                </p>
                {entities.crypto_wallets_unverified.map((w, i) => (
                  <Mono key={i} className="block break-all">{w.address}</Mono>
                ))}
              </div>
            )}
          </div>
        )}

        {tab === 'media' && (
          <AsyncBoundary
            loading={media.loading}
            error={media.error}
            onRetry={media.reload}
            isEmpty={!media.data?.artifacts?.length}
            empty={<EmptyState icon={ImageIcon} title="No media recovered"
                               description="No images or video were attached to this record." />}
          >
            <div className="space-y-3">
              {(media.data?.artifacts || []).map((m) => (
                <div key={m.id} className="rounded-lg p-3"
                     style={{ background: 'var(--surface-sunken)', border: '1px solid var(--border)' }}>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[12px] font-medium" style={{ color: 'var(--text-primary)' }}>
                      {m.media_type} · {m.dimensions?.width}×{m.dimensions?.height}
                    </span>
                    {m.in_border_corridor && <RiskBadge level="SEVERE" />}
                  </div>
                  <div className="space-y-1.5">
                    <Field label="Device" value={m.forensics?.device_signature} />
                    <Field label="Captured" value={m.forensics?.capture_timestamp} />
                    {m.geo && (
                      <Field label="GPS">
                        <span>
                          {m.geo.nearest_known_location} · {m.geo.distance_to_border_km} km to border
                        </span>
                      </Field>
                    )}
                    <Field label="SHA-256"><Mono>{m.sha256_hash?.slice(0, 24)}…</Mono></Field>
                  </div>
                  {m.ocr_text && (
                    <div className="mt-2 text-[11px] p-2 rounded whitespace-pre-wrap"
                         style={{ background: 'var(--surface-card)', color: 'var(--text-muted)' }}>
                      {m.ocr_text.slice(0, 300)}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </AsyncBoundary>
        )}
      </DetailPanel>
    </>
  );
};
