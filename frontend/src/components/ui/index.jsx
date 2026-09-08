import React from 'react';
import {
  AlertCircle, AlertTriangle, Inbox, Loader2, RefreshCw, ShieldOff,
  TrendingUp, TrendingDown, WifiOff, X,
} from 'lucide-react';

/*
 * Shared interface primitives.
 *
 * The states below exist because the previous pages had exactly one: on any
 * failure they rendered fabricated demo data, so an outage, an expired session
 * and an empty database were indistinguishable on screen. Each of those is now
 * a distinct, honest state.
 */

// ── Risk and status ──────────────────────────────────────────────────

const RISK_STYLES = {
  SEVERE: { bg: 'var(--risk-high-bg)', color: 'var(--risk-high-text)', border: 'var(--risk-high-border)', label: 'Severe' },
  HIGH: { bg: 'var(--risk-high-bg)', color: 'var(--risk-high-text)', border: 'var(--risk-high-border)', label: 'High' },
  MEDIUM: { bg: 'var(--risk-medium-bg)', color: 'var(--risk-medium-text)', border: 'var(--risk-medium-border)', label: 'Medium' },
  LOW: { bg: 'var(--risk-low-bg)', color: 'var(--risk-low-text)', border: 'var(--risk-low-border)', label: 'Low' },
  UNREVIEWED: { bg: 'var(--risk-none-bg)', color: 'var(--risk-none-text)', border: 'var(--risk-none-border)', label: 'Unreviewed' },
};

export const RiskBadge = ({ level, className = '' }) => {
  const key = (level || 'UNREVIEWED').toUpperCase();
  const style = RISK_STYLES[key] || RISK_STYLES.UNREVIEWED;
  return (
    <span
      className={`pill ${className}`}
      style={{ background: style.bg, color: style.color, borderColor: style.border }}
    >
      {style.label}
    </span>
  );
};

const STATUS_COLORS = {
  ACTIVE: 'var(--status-active)',
  OPERATIONAL: 'var(--status-active)',
  RUNNING: 'var(--status-progress)',
  PENDING: 'var(--status-progress)',
  DEGRADED: 'var(--status-degraded)',
  PAUSED: 'var(--status-degraded)',
  BLOCKED: 'var(--status-degraded)',
  FAILED: 'var(--risk-high-text)',
  CLOSED: 'var(--status-closed)',
};

export const StatusDot = ({ status, label }) => {
  const color = STATUS_COLORS[(status || '').toUpperCase()] || 'var(--status-closed)';
  return (
    <span className="inline-flex items-center gap-2 text-[13px]" style={{ color: 'var(--text-secondary)' }}>
      <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: color }} />
      {label || status}
    </span>
  );
};

// ── Metric card ──────────────────────────────────────────────────────

export const StatCard = ({ icon: Icon, label, value, delta, deltaLabel, tone = 'accent', loading }) => {
  const tones = {
    accent: { bg: 'var(--accent-soft)', color: 'var(--accent)' },
    danger: { bg: 'var(--risk-high-bg)', color: 'var(--risk-high-text)' },
    success: { bg: 'var(--risk-low-bg)', color: 'var(--risk-low-text)' },
    warning: { bg: 'var(--risk-medium-bg)', color: 'var(--risk-medium-text)' },
  };
  const t = tones[tone] || tones.accent;
  const Trend = delta > 0 ? TrendingUp : TrendingDown;

  return (
    <div className="card p-4 flex items-start gap-3.5">
      {Icon && (
        <div className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0"
             style={{ background: t.bg, color: t.color }}>
          <Icon className="w-5 h-5" />
        </div>
      )}
      <div className="min-w-0 flex-1">
        <div className="label">{label}</div>
        {loading ? (
          <div className="h-7 w-16 rounded mt-1.5 animate-pulse" style={{ background: 'var(--surface-hover)' }} />
        ) : (
          <div className="text-[26px] font-semibold leading-tight mt-0.5"
               style={{ color: 'var(--text-primary)' }}>
            {value ?? '—'}
          </div>
        )}
        {!loading && delta !== undefined && delta !== null && (
          <div className="flex items-center gap-1 text-[11px] mt-0.5"
               style={{ color: delta >= 0 ? 'var(--status-active)' : 'var(--risk-high-text)' }}>
            <Trend className="w-3 h-3" />
            <span>{Math.abs(delta)}%</span>
            {deltaLabel && <span style={{ color: 'var(--text-muted)' }}>{deltaLabel}</span>}
          </div>
        )}
      </div>
    </div>
  );
};

// ── Page furniture ───────────────────────────────────────────────────

export const PageHeader = ({ title, description, breadcrumb, actions }) => (
  <div className="flex items-start justify-between gap-4 flex-wrap">
    <div>
      {breadcrumb && (
        <div className="text-[12px] mb-1" style={{ color: 'var(--text-muted)' }}>
          {breadcrumb}
        </div>
      )}
      <h1 className="text-[22px] font-semibold" style={{ color: 'var(--text-primary)' }}>{title}</h1>
      {description && (
        <p className="text-[13px] mt-0.5" style={{ color: 'var(--text-secondary)' }}>{description}</p>
      )}
    </div>
    {actions && <div className="flex items-center gap-2">{actions}</div>}
  </div>
);

export const SectionCard = ({ title, action, children, className = '', bodyClass = 'p-4' }) => (
  <div className={`card-flush ${className}`}>
    {(title || action) && (
      <div className="flex items-center justify-between px-4 py-3"
           style={{ borderBottom: '1px solid var(--border)' }}>
        <h2 className="section-title">{title}</h2>
        {action}
      </div>
    )}
    <div className={bodyClass}>{children}</div>
  </div>
);

// ── The four honest states ───────────────────────────────────────────

export const LoadingState = ({ label = 'Loading…', rows = 0 }) => {
  if (rows > 0) {
    return (
      <div className="space-y-2 p-4">
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="h-9 rounded animate-pulse" style={{ background: 'var(--surface-hover)' }} />
        ))}
      </div>
    );
  }
  return (
    <div className="flex flex-col items-center justify-center py-14 gap-2.5">
      <Loader2 className="w-5 h-5 animate-spin" style={{ color: 'var(--accent)' }} />
      <p className="text-[13px]" style={{ color: 'var(--text-muted)' }}>{label}</p>
    </div>
  );
};

/**
 * Nothing collected yet. Distinct from an error: the system is working, there
 * is simply nothing to show. Says what to do about it.
 */
export const EmptyState = ({ icon: Icon = Inbox, title, description, action }) => (
  <div className="flex flex-col items-center justify-center py-14 px-6 text-center">
    <div className="w-11 h-11 rounded-full flex items-center justify-center mb-3"
         style={{ background: 'var(--surface-hover)', color: 'var(--text-muted)' }}>
      <Icon className="w-5 h-5" />
    </div>
    <p className="text-[14px] font-medium" style={{ color: 'var(--text-primary)' }}>{title}</p>
    {description && (
      <p className="text-[13px] mt-1 max-w-md leading-relaxed" style={{ color: 'var(--text-muted)' }}>
        {description}
      </p>
    )}
    {action && <div className="mt-4">{action}</div>}
  </div>
);

/**
 * A request failed. Names the failure and offers a retry, rather than
 * silently substituting invented data.
 */
export const ErrorState = ({ error, onRetry, compact }) => {
  const kind = error?.kind || 'error';
  const icons = {
    offline: WifiOff,
    timeout: RefreshCw,
    forbidden: ShieldOff,
    unauthenticated: ShieldOff,
    server_error: AlertTriangle,
  };
  const Icon = icons[kind] || AlertCircle;

  const isPermission = kind === 'forbidden' || kind === 'unauthenticated';
  const tone = isPermission
    ? { bg: 'var(--risk-medium-bg)', color: 'var(--risk-medium-text)', border: 'var(--risk-medium-border)' }
    : { bg: 'var(--risk-high-bg)', color: 'var(--risk-high-text)', border: 'var(--risk-high-border)' };

  if (compact) {
    return (
      <div className="flex items-center gap-2 rounded-lg px-3 py-2 text-[12px]"
           style={{ background: tone.bg, color: tone.color, border: `1px solid ${tone.border}` }}>
        <Icon className="w-3.5 h-3.5 shrink-0" />
        <span className="flex-1">{error?.message || 'Request failed.'}</span>
        {onRetry && <button onClick={onRetry} className="underline font-medium">Retry</button>}
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center py-12 px-6 text-center">
      <div className="w-11 h-11 rounded-full flex items-center justify-center mb-3"
           style={{ background: tone.bg, color: tone.color }}>
        <Icon className="w-5 h-5" />
      </div>
      <p className="text-[14px] font-medium" style={{ color: 'var(--text-primary)' }}>
        {isPermission ? 'Access denied' : 'Could not load this data'}
      </p>
      <p className="text-[13px] mt-1 max-w-md leading-relaxed" style={{ color: 'var(--text-muted)' }}>
        {error?.message || 'The request failed.'}
      </p>
      {onRetry && (
        <button onClick={onRetry} className="btn btn-secondary mt-4">
          <RefreshCw className="w-3.5 h-3.5" /> Try again
        </button>
      )}
    </div>
  );
};

/**
 * Renders the correct state for an async resource, so pages do not each
 * reinvent the decision and quietly get it wrong.
 */
export const AsyncBoundary = ({ loading, error, isEmpty, onRetry, empty, skeletonRows, children }) => {
  if (loading) return <LoadingState rows={skeletonRows} />;
  if (error) return <ErrorState error={error} onRetry={onRetry} />;
  if (isEmpty) return empty || <EmptyState title="Nothing to show yet" />;
  return children;
};

// ── Right-hand detail panel ──────────────────────────────────────────

export const DetailPanel = ({ open, onClose, title, subtitle, badge, tabs, activeTab, onTabChange, footer, children }) => {
  if (!open) return null;
  return (
    <aside
      className="w-[380px] shrink-0 flex flex-col animate-slide-in"
      style={{
        background: 'var(--surface-card)',
        borderLeft: '1px solid var(--border)',
        boxShadow: 'var(--shadow-panel)',
      }}
    >
      <div className="px-4 py-3 flex items-start justify-between gap-3"
           style={{ borderBottom: '1px solid var(--border)' }}>
        <div className="min-w-0">
          {subtitle && <div className="label">{subtitle}</div>}
          <div className="flex items-center gap-2 flex-wrap">
            <h2 className="text-[15px] font-semibold truncate" style={{ color: 'var(--text-primary)' }}>
              {title}
            </h2>
            {badge}
          </div>
        </div>
        <button onClick={onClose} className="btn btn-ghost p-1.5" aria-label="Close panel">
          <X className="w-4 h-4" />
        </button>
      </div>

      {tabs && (
        <div className="flex px-2 gap-1" style={{ borderBottom: '1px solid var(--border)' }}>
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => onTabChange?.(tab.id)}
              className="px-3 py-2 text-[13px] font-medium border-b-2 -mb-px transition"
              style={{
                borderColor: activeTab === tab.id ? 'var(--accent)' : 'transparent',
                color: activeTab === tab.id ? 'var(--accent)' : 'var(--text-muted)',
              }}
            >
              {tab.label}
              {tab.count !== undefined && (
                <span className="ml-1" style={{ color: 'var(--text-muted)' }}>({tab.count})</span>
              )}
            </button>
          ))}
        </div>
      )}

      <div className="flex-1 scroll-area p-4 space-y-4">{children}</div>
      {footer && <div className="p-3" style={{ borderTop: '1px solid var(--border)' }}>{footer}</div>}
    </aside>
  );
};

export const Field = ({ label, value, mono, children }) => (
  <div className="grid grid-cols-[110px_1fr] gap-2 items-start">
    <div className="text-[12px] pt-0.5" style={{ color: 'var(--text-muted)' }}>{label}</div>
    <div className={`text-[13px] break-words ${mono ? 'mono' : ''}`} style={{ color: 'var(--text-primary)' }}>
      {children ?? (value === null || value === undefined || value === '' ? '—' : value)}
    </div>
  </div>
);

export const Mono = ({ children, className = '' }) => (
  <span className={`mono text-[12px] ${className}`} style={{ color: 'var(--text-secondary)' }}>
    {children}
  </span>
);

/** A qualitative confidence marker; never shown as a bare number. */
export const ConfidenceBadge = ({ level }) => {
  const map = {
    HIGH: RISK_STYLES.LOW,
    VERY_HIGH: RISK_STYLES.LOW,
    MODERATE: RISK_STYLES.MEDIUM,
    LOW: RISK_STYLES.MEDIUM,
    SPECULATIVE: RISK_STYLES.UNREVIEWED,
    INSUFFICIENT: RISK_STYLES.UNREVIEWED,
  };
  const style = map[(level || '').toUpperCase()] || RISK_STYLES.UNREVIEWED;
  return (
    <span className="pill" style={{ background: style.bg, color: style.color, borderColor: style.border }}>
      {(level || 'unknown').replace(/_/g, ' ').toLowerCase()}
    </span>
  );
};

export const SourceBadge = ({ type }) => {
  const map = {
    TELEGRAM: { label: 'Telegram', color: '#0ea5e9' },
    DARK_WEB: { label: 'Dark Web', color: '#7c3aed' },
    SURFACE_WEB: { label: 'Surface Web', color: '#0d9488' },
    MEDIA_GPS: { label: 'Media GPS', color: '#ea580c' },
  };
  const s = map[(type || '').toUpperCase()] || { label: type || 'Unknown', color: 'var(--text-muted)' };
  return (
    <span className="inline-flex items-center gap-1.5 text-[12px]" style={{ color: 'var(--text-secondary)' }}>
      <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: s.color }} />
      {s.label}
    </span>
  );
};
