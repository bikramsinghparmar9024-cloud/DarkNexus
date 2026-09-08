import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import {
  ShieldCheck, ShieldAlert, ShieldQuestion, Shield, Search, Filter,
  CheckCircle2, XCircle, Clock, AlertTriangle, ChevronRight, Eye,
  RefreshCw, FileText, Fingerprint, ThumbsUp, ThumbsDown, HelpCircle,
  ArrowRight, Zap, Hash, Activity, User
} from 'lucide-react';

// ─── State machine styles ────────────────────────────────────────
const STATE_CONFIG = {
  LEAD: {
    bg: 'bg-amber-500/10', border: 'border-amber-500/30', text: 'text-amber-400',
    gradientFrom: 'from-amber-500', gradientTo: 'to-orange-500',
    icon: ShieldQuestion, label: 'LEAD', description: 'AI-detected intelligence lead. Awaiting corroboration.',
    dotColor: 'bg-amber-400',
  },
  CORROBORATED: {
    bg: 'bg-cyan-500/10', border: 'border-cyan-500/30', text: 'text-cyan-400',
    gradientFrom: 'from-cyan-500', gradientTo: 'to-blue-500',
    icon: Shield, label: 'CORROBORATED', description: 'Multiple independent sources confirm this intelligence.',
    dotColor: 'bg-cyan-400',
  },
  VERIFIED: {
    bg: 'bg-emerald-500/10', border: 'border-emerald-500/30', text: 'text-emerald-400',
    gradientFrom: 'from-emerald-500', gradientTo: 'to-green-500',
    icon: ShieldCheck, label: 'VERIFIED', description: 'Analyst-verified. Eligible for approved investigative outputs.',
    dotColor: 'bg-emerald-400',
  },
  REJECTED: {
    bg: 'bg-rose-500/10', border: 'border-rose-500/30', text: 'text-rose-400',
    gradientFrom: 'from-rose-500', gradientTo: 'to-red-500',
    icon: ShieldAlert, label: 'REJECTED', description: 'Rejected by investigator. Excluded from approved outputs.',
    dotColor: 'bg-rose-400',
  },
};

const SOURCE_BADGE = {
  DARK_WEB: { bg: 'bg-purple-500/10', text: 'text-purple-400', border: 'border-purple-500/30' },
  TELEGRAM: { bg: 'bg-blue-500/10', text: 'text-blue-400', border: 'border-blue-500/30' },
  SURFACE_WEB: { bg: 'bg-emerald-500/10', text: 'text-emerald-400', border: 'border-emerald-500/30' },
};

const getStateConfig = (state) => STATE_CONFIG[state] || STATE_CONFIG.LEAD;
const getSourceBadge = (type) => SOURCE_BADGE[type] || SOURCE_BADGE.SURFACE_WEB;

export const IntelVerification = () => {
  const [findings, setFindings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isOffline, setIsOffline] = useState(false);
  const [filterState, setFilterState] = useState('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [actionLoading, setActionLoading] = useState(null);
  const [actionResults, setActionResults] = useState({});
  const [auditLog, setAuditLog] = useState([]);

  // ─── Fetch findings ────────────────────────────────────────────
  useEffect(() => {
    fetchFindings();
  }, []);

  const fetchFindings = async () => {
    setLoading(true);
    try {
      const res = await apiClient.get('/api/verification/findings', { timeout: 3000 });
      setFindings(res.data.findings || []);
      setIsOffline(false);
    } catch (e) {
      console.error('IntelVerification: failed to fetch findings:', e.message);
      setFindings([]);
    } finally {
      setLoading(false);
    }
  };

  // ─── Verification actions ─────────────────────────────────────
  const handleVerify = async (recordId) => {
    setActionLoading(recordId);
    try {
      const res = await apiClient.post(`/api/verification/verify/${recordId}`, {
        investigator_badge: 'PB-CID-8821',
        notes: 'Verified by investigator during review session.'
      }, { timeout: 3000 });
      setFindings(prev => prev.map(f => f.id === recordId ? { ...f, intelligence_state: 'VERIFIED', verified_by: 'PB-CID-8821', verified_at: new Date().toISOString() } : f));
      setActionResults(prev => ({ ...prev, [recordId]: { action: 'VERIFIED', message: res.data?.message || 'Finding verified successfully' } }));
      addAuditEntry('VERIFY_FINDING', recordId, 'Investigator PB-CID-8821 verified finding.');
    } catch (e) {
      // Offline fallback
      setFindings(prev => prev.map(f => f.id === recordId ? { ...f, intelligence_state: 'VERIFIED', verified_by: 'PB-CID-8821', verified_at: new Date().toISOString() } : f));
      setActionResults(prev => ({ ...prev, [recordId]: { action: 'VERIFIED', message: 'Finding verified (offline mode)' } }));
      addAuditEntry('VERIFY_FINDING', recordId, 'Investigator PB-CID-8821 verified finding (offline).');
    } finally {
      setActionLoading(null);
    }
  };

  const handleReject = async (recordId) => {
    setActionLoading(recordId);
    try {
      await apiClient.post(`/api/verification/reject/${recordId}`, {
        investigator_badge: 'PB-CID-8821',
        reason: 'Insufficient corroboration — alias match only.'
      }, { timeout: 3000 });
      setFindings(prev => prev.map(f => f.id === recordId ? { ...f, intelligence_state: 'REJECTED' } : f));
      setActionResults(prev => ({ ...prev, [recordId]: { action: 'REJECTED', message: 'Finding rejected' } }));
      addAuditEntry('REJECT_FINDING', recordId, 'Investigator PB-CID-8821 rejected finding.');
    } catch (e) {
      setFindings(prev => prev.map(f => f.id === recordId ? { ...f, intelligence_state: 'REJECTED' } : f));
      setActionResults(prev => ({ ...prev, [recordId]: { action: 'REJECTED', message: 'Finding rejected (offline)' } }));
      addAuditEntry('REJECT_FINDING', recordId, 'Investigator PB-CID-8821 rejected finding (offline).');
    } finally {
      setActionLoading(null);
    }
  };

  const handleRequestCorroboration = async (recordId) => {
    setActionLoading(recordId);
    try {
      await apiClient.post(`/api/verification/request-corroboration/${recordId}`, {
        investigator_badge: 'PB-CID-8821',
        additional_signals_needed: 'Requires independent surface-web or forensic corroboration.'
      }, { timeout: 3000 });
      setFindings(prev => prev.map(f => f.id === recordId ? { ...f, intelligence_state: 'LEAD' } : f));
      setActionResults(prev => ({ ...prev, [recordId]: { action: 'LEAD', message: 'Corroboration requested — returned to LEAD state' } }));
      addAuditEntry('REQUEST_CORROBORATION', recordId, 'Investigator PB-CID-8821 requested further corroboration.');
    } catch (e) {
      setFindings(prev => prev.map(f => f.id === recordId ? { ...f, intelligence_state: 'LEAD' } : f));
      setActionResults(prev => ({ ...prev, [recordId]: { action: 'LEAD', message: 'Corroboration requested (offline)' } }));
      addAuditEntry('REQUEST_CORROBORATION', recordId, 'Further corroboration requested (offline).');
    } finally {
      setActionLoading(null);
    }
  };

  const addAuditEntry = (action, recordId, details) => {
    setAuditLog(prev => [{
      id: Date.now(),
      action,
      resource: `record_${recordId}`,
      user: 'admin_punjab (PB-CID-8821)',
      timestamp: new Date().toLocaleString('en-IN', { hour12: false }),
      details,
    }, ...prev]);
  };

  // ─── Filters ───────────────────────────────────────────────────
  const filteredFindings = findings.filter(f => {
    const matchesSearch = !searchQuery ||
      f.snippet?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      f.author?.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesState = filterState === 'ALL' || f.intelligence_state === filterState;
    return matchesSearch && matchesState;
  });

  // ─── Stats ─────────────────────────────────────────────────────
  const stateCounts = {
    LEAD: findings.filter(f => f.intelligence_state === 'LEAD').length,
    CORROBORATED: findings.filter(f => f.intelligence_state === 'CORROBORATED').length,
    VERIFIED: findings.filter(f => f.intelligence_state === 'VERIFIED').length,
    REJECTED: findings.filter(f => f.intelligence_state === 'REJECTED').length,
  };

  if (loading) {
    return (
      <div className="p-6 space-y-6 max-w-7xl mx-auto">
        <div className="glass-card rounded-xl p-5 border-l-4 border-emerald-500">
          <div className="skeleton h-6 w-64 mb-2" />
          <div className="skeleton h-3 w-96" />
        </div>
        <div className="grid grid-cols-4 gap-4">
          {[1, 2, 3, 4].map(i => <div key={i} className="glass-card rounded-xl p-5"><div className="skeleton h-8 w-12" /></div>)}
        </div>
        {[1, 2, 3].map(i => <div key={i} className="glass-card rounded-xl p-5"><div className="skeleton h-24 w-full" /></div>)}
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* ─── Header ─────────────────────────────────────────────── */}
      <div className="glass-card rounded-xl p-5 border-l-4 border-emerald-500 animate-fade-in-up">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
              <ShieldCheck className="w-5 h-5 text-emerald-400" />
              Intelligence Verification & State Machine
            </h2>
            <p className="text-xs text-slate-400 mt-1 font-mono">
              LEAD → CORROBORATED → VERIFIED Pipeline • Analyst Review • Audited Chain of Custody
            </p>
          </div>
          <div className="flex items-center gap-3">
            {isOffline && (
              <span className="text-[9px] font-mono px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30">DEMO</span>
            )}
            <button
              onClick={fetchFindings}
              className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/20 transition-all"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* ─── State Machine Visual Pipeline ───────────────────────── */}
      <div className="glass-card rounded-2xl p-6 border border-[#1c2d52] bg-gradient-to-r from-[#0d1629] to-[#0a1020]">
        <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider mb-5 flex items-center gap-2">
          <Activity className="w-4 h-4 text-cyan-400" />
          Intelligence State Pipeline
        </h3>
        <div className="flex items-center justify-between gap-2">
          {['LEAD', 'CORROBORATED', 'VERIFIED'].map((state, idx) => {
            const cfg = getStateConfig(state);
            const Icon = cfg.icon;
            const isLast = idx === 2;
            return (
              <React.Fragment key={state}>
                <button
                  onClick={() => setFilterState(filterState === state ? 'ALL' : state)}
                  className={`flex-1 p-4 rounded-2xl border-2 transition-all cursor-pointer group relative overflow-hidden ${
                    filterState === state
                      ? `${cfg.bg} ${cfg.border} shadow-[0_0_25px_rgba(6,182,212,0.15)]`
                      : 'border-[#1c2d52] hover:border-[#2a3f6e] bg-[#0e172e]/60'
                  }`}
                >
                  {/* Background glow */}
                  <div className={`absolute inset-0 bg-gradient-to-br ${cfg.gradientFrom} ${cfg.gradientTo} opacity-[0.03] group-hover:opacity-[0.06] transition-opacity`} />

                  <div className="relative z-10">
                    <div className="flex items-center justify-between mb-2">
                      <Icon className={`w-6 h-6 ${cfg.text}`} />
                      <span className={`text-2xl font-black font-mono ${cfg.text}`}>
                        {stateCounts[state]}
                      </span>
                    </div>
                    <div className={`text-xs font-bold font-mono ${cfg.text} uppercase tracking-wider`}>{cfg.label}</div>
                    <p className="text-[9px] text-slate-500 mt-1 font-mono leading-relaxed">{cfg.description}</p>
                  </div>
                </button>

                {!isLast && (
                  <div className="flex-shrink-0 flex flex-col items-center gap-0.5">
                    <ArrowRight className="w-5 h-5 text-cyan-500/40" />
                    <span className="text-[7px] font-mono text-slate-600 uppercase">promote</span>
                  </div>
                )}
              </React.Fragment>
            );
          })}
        </div>

        {/* Rejected count */}
        {stateCounts.REJECTED > 0 && (
          <div className="mt-3 flex items-center justify-end">
            <button
              onClick={() => setFilterState(filterState === 'REJECTED' ? 'ALL' : 'REJECTED')}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-[10px] font-mono font-bold transition-all ${
                filterState === 'REJECTED'
                  ? 'bg-rose-500/15 text-rose-400 border border-rose-500/40'
                  : 'text-rose-400/60 hover:text-rose-400 border border-transparent'
              }`}
            >
              <ShieldAlert className="w-3 h-3" />
              {stateCounts.REJECTED} Rejected
            </button>
          </div>
        )}
      </div>

      {/* ─── Search & Filter ────────────────────────────────────── */}
      <div className="flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search findings by content, author..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-[#0d1527] border border-[#1c2d52] text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500/50 font-mono"
          />
        </div>
        <div className="flex gap-1.5">
          {['ALL', 'LEAD', 'CORROBORATED', 'VERIFIED', 'REJECTED'].map(state => {
            const cfg = state !== 'ALL' ? getStateConfig(state) : null;
            return (
              <button
                key={state}
                onClick={() => setFilterState(state)}
                className={`px-3 py-2 rounded-xl text-[10px] font-mono font-bold border transition-all ${
                  filterState === state
                    ? `${cfg?.bg || 'bg-cyan-500/15'} ${cfg?.text || 'text-cyan-300'} ${cfg?.border || 'border-cyan-500/40'}`
                    : 'bg-[#14203b] text-slate-400 border-[#1c2d52] hover:text-slate-200'
                }`}
              >
                {state}
              </button>
            );
          })}
        </div>
      </div>

      {/* ─── Findings Cards ─────────────────────────────────────── */}
      <div className="space-y-4">
        {filteredFindings.map((finding) => {
          const stateCfg = getStateConfig(finding.intelligence_state);
          const StateIcon = stateCfg.icon;
          const srcBadge = getSourceBadge(finding.source_type);
          const actionResult = actionResults[finding.id];
          const isProcessing = actionLoading === finding.id;

          return (
            <div
              key={finding.id}
              className="glass-card rounded-xl border border-[#1c2d52] overflow-hidden hover:border-[#2a3f6e] transition-all animate-fade-in-up"
            >
              {/* Top state indicator bar */}
              <div className={`h-1 bg-gradient-to-r ${stateCfg.gradientFrom} ${stateCfg.gradientTo}`} />

              <div className="p-5">
                <div className="flex flex-col lg:flex-row lg:items-start gap-4">
                  {/* Main content */}
                  <div className="flex-1 space-y-3">
                    {/* Badges row */}
                    <div className="flex items-center flex-wrap gap-2">
                      <span className={`text-[9px] font-mono font-bold px-2.5 py-1 rounded-lg border flex items-center gap-1.5 ${stateCfg.bg} ${stateCfg.text} ${stateCfg.border}`}>
                        <StateIcon className="w-3 h-3" />
                        {stateCfg.label}
                      </span>
                      <span className={`text-[9px] font-mono font-bold px-2 py-0.5 rounded border ${srcBadge.bg} ${srcBadge.text} ${srcBadge.border}`}>
                        {finding.source_type}
                      </span>
                      <span className={`text-[9px] font-mono font-bold px-2 py-0.5 rounded border ${
                        finding.threat_level === 'SEVERE' ? 'bg-rose-500/20 text-rose-400 border-rose-500/30' :
                        finding.threat_level === 'HIGH' ? 'bg-amber-500/20 text-amber-400 border-amber-500/30' :
                        'bg-yellow-500/20 text-yellow-300 border-yellow-500/30'
                      }`}>{finding.threat_level}</span>
                      <span className="text-[9px] font-mono text-slate-500">ID #{finding.id}</span>
                    </div>

                    {/* Snippet */}
                    <p className="text-xs text-slate-300 leading-relaxed">{finding.snippet}</p>

                    {/* Metadata */}
                    <div className="flex items-center flex-wrap gap-4 text-[9px] font-mono text-slate-500">
                      <span className="flex items-center gap-1">
                        <User className="w-2.5 h-2.5" />
                        {finding.author}
                      </span>
                      <span className="flex items-center gap-1 truncate max-w-[200px]">
                        <Eye className="w-2.5 h-2.5" />
                        {finding.source_url}
                      </span>
                      <span className="flex items-center gap-1">
                        <Clock className="w-2.5 h-2.5" />
                        {finding.created_at?.split('T')[0]}
                      </span>
                      <span className="flex items-center gap-1">
                        <Hash className="w-2.5 h-2.5 text-purple-400" />
                        <span className="truncate max-w-[100px]">{finding.sha256_hash?.slice(0, 16)}...</span>
                      </span>
                    </div>

                    {/* Verified by info */}
                    {finding.verified_by && (
                      <div className="flex items-center gap-2 p-2 rounded-lg bg-emerald-500/5 border border-emerald-500/20 text-[10px] font-mono">
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                        <span className="text-emerald-300">Verified by <strong>{finding.verified_by}</strong></span>
                        <span className="text-slate-500">at {finding.verified_at?.split('T')[0]}</span>
                      </div>
                    )}

                    {/* Action result feedback */}
                    {actionResult && (
                      <div className={`flex items-center gap-2 p-2.5 rounded-lg text-[10px] font-mono animate-fade-in-up ${
                        actionResult.action === 'VERIFIED' ? 'bg-emerald-500/10 border border-emerald-500/30 text-emerald-300' :
                        actionResult.action === 'REJECTED' ? 'bg-rose-500/10 border border-rose-500/30 text-rose-300' :
                        'bg-amber-500/10 border border-amber-500/30 text-amber-300'
                      }`}>
                        {actionResult.action === 'VERIFIED' && <CheckCircle2 className="w-3.5 h-3.5" />}
                        {actionResult.action === 'REJECTED' && <XCircle className="w-3.5 h-3.5" />}
                        {actionResult.action === 'LEAD' && <HelpCircle className="w-3.5 h-3.5" />}
                        {actionResult.message}
                      </div>
                    )}
                  </div>

                  {/* Action buttons (right side) */}
                  {finding.intelligence_state !== 'VERIFIED' && finding.intelligence_state !== 'REJECTED' && (
                    <div className="flex lg:flex-col gap-2 flex-shrink-0">
                      <button
                        onClick={() => handleVerify(finding.id)}
                        disabled={isProcessing}
                        className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-[10px] font-bold font-mono hover:bg-emerald-500/20 transition-all disabled:opacity-50 whitespace-nowrap"
                      >
                        {isProcessing ? <RefreshCw className="w-3 h-3 animate-spin" /> : <ThumbsUp className="w-3 h-3" />}
                        Verify
                      </button>
                      <button
                        onClick={() => handleReject(finding.id)}
                        disabled={isProcessing}
                        className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-[10px] font-bold font-mono hover:bg-rose-500/20 transition-all disabled:opacity-50 whitespace-nowrap"
                      >
                        <ThumbsDown className="w-3 h-3" />
                        Reject
                      </button>
                      <button
                        onClick={() => handleRequestCorroboration(finding.id)}
                        disabled={isProcessing}
                        className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-[10px] font-bold font-mono hover:bg-amber-500/20 transition-all disabled:opacity-50 whitespace-nowrap"
                      >
                        <HelpCircle className="w-3 h-3" />
                        Need More
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}

        {filteredFindings.length === 0 && (
          <div className="p-12 text-center glass-card rounded-xl border border-[#1c2d52]">
            <ShieldCheck className="w-10 h-10 text-slate-600 mx-auto mb-3" />
            <h4 className="text-sm font-bold text-slate-400 uppercase font-mono">No Findings</h4>
            <p className="text-xs text-slate-500 font-mono mt-1">No intelligence findings match the current filter.</p>
          </div>
        )}
      </div>

      {/* ─── Session Audit Log ──────────────────────────────────── */}
      {auditLog.length > 0 && (
        <div className="glass-card rounded-xl border border-[#1c2d52] overflow-hidden animate-fade-in-up">
          <div className="p-4 border-b border-[#1c2d52] flex items-center justify-between">
            <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
              <FileText className="w-4 h-4 text-cyan-400" />
              Session Verification Audit Trail
            </h3>
            <span className="text-xs font-mono text-slate-400">{auditLog.length} Actions</span>
          </div>
          <div className="divide-y divide-[#1c2d52] max-h-[250px] overflow-y-auto">
            {auditLog.map((entry) => (
              <div key={entry.id} className="p-3 hover:bg-[#14203b]/40 transition-colors text-xs">
                <div className="flex items-center gap-3">
                  <span className={`text-[9px] font-mono font-bold px-2 py-0.5 rounded border ${
                    entry.action.includes('VERIFY') ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30' :
                    entry.action.includes('REJECT') ? 'bg-rose-500/10 text-rose-300 border-rose-500/30' :
                    'bg-amber-500/10 text-amber-300 border-amber-500/30'
                  }`}>{entry.action}</span>
                  <span className="font-mono text-cyan-400 text-[10px]">{entry.resource}</span>
                  <span className="font-mono text-slate-500 text-[10px]">{entry.user}</span>
                  <span className="font-mono text-slate-500 text-[10px] ml-auto">{entry.timestamp}</span>
                </div>
                <p className="mt-1 text-slate-400 text-[10px] font-mono">{entry.details}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
