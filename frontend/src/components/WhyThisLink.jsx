import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import {
  X, Shield, ShieldCheck, ShieldAlert, ShieldQuestion,
  Fingerprint, AtSign, Wallet, MessageCircle, Globe, Clock,
  CheckCircle2, XCircle, AlertTriangle, ExternalLink,
  ChevronRight, Lock, Eye, Sparkles, Link2, FileSearch,
  ThumbsUp, ThumbsDown, HelpCircle
} from 'lucide-react';

// Signal type icons
const SIGNAL_ICONS = {
  pgp_fingerprint: Fingerprint,
  alias_overlap: AtSign,
  payment_handle: Wallet,
  communication_id: MessageCircle,
  surface_web_corroboration: Globe,
  timing_correlation: Clock,
};

// Confidence level colors
const CONFIDENCE_COLORS = {
  VERY_HIGH: { bg: 'bg-emerald-500', text: 'text-emerald-400', border: 'border-emerald-500/40', glow: 'shadow-[0_0_20px_rgba(16,185,129,0.3)]' },
  HIGH: { bg: 'bg-cyan-500', text: 'text-cyan-400', border: 'border-cyan-500/40', glow: 'shadow-[0_0_20px_rgba(6,182,212,0.3)]' },
  MODERATE: { bg: 'bg-amber-500', text: 'text-amber-400', border: 'border-amber-500/40', glow: 'shadow-[0_0_20px_rgba(245,158,11,0.3)]' },
  LOW: { bg: 'bg-orange-500', text: 'text-orange-400', border: 'border-orange-500/40', glow: '' },
  SPECULATIVE: { bg: 'bg-slate-500', text: 'text-slate-400', border: 'border-slate-500/40', glow: '' },
};

// Intelligence state styles
const STATE_STYLES = {
  LEAD: { bg: 'bg-amber-500/15', text: 'text-amber-300', border: 'border-amber-500/40', icon: ShieldQuestion, label: 'LEAD' },
  CORROBORATED: { bg: 'bg-cyan-500/15', text: 'text-cyan-300', border: 'border-cyan-500/40', icon: Shield, label: 'CORROBORATED' },
  VERIFIED: { bg: 'bg-emerald-500/15', text: 'text-emerald-300', border: 'border-emerald-500/40', icon: ShieldCheck, label: 'VERIFIED' },
  REJECTED: { bg: 'bg-rose-500/15', text: 'text-rose-300', border: 'border-rose-500/40', icon: ShieldAlert, label: 'REJECTED' },
  PENDING: { bg: 'bg-slate-500/15', text: 'text-slate-300', border: 'border-slate-500/40', icon: ShieldQuestion, label: 'PENDING REVIEW' },
};

// Source type reliability badge
const SOURCE_TYPE_BADGE = {
  DARK_WEB: { color: 'text-purple-400', bg: 'bg-purple-500/10', border: 'border-purple-500/30' },
  TELEGRAM: { color: 'text-blue-400', bg: 'bg-blue-500/10', border: 'border-blue-500/30' },
  SURFACE_WEB: { color: 'text-emerald-400', bg: 'bg-emerald-500/10', border: 'border-emerald-500/30' },
  BLOCKCHAIN: { color: 'text-amber-400', bg: 'bg-amber-500/10', border: 'border-amber-500/30' },
  FORENSIC: { color: 'text-cyan-400', bg: 'bg-cyan-500/10', border: 'border-cyan-500/30' },
};

export const WhyThisLink = ({ sourceId, targetId, sourceName, targetName, onClose }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [verifying, setVerifying] = useState(false);
  const [verificationResult, setVerificationResult] = useState(null);

  useEffect(() => {
    if (!sourceId || !targetId) return;
    fetchExplanation();
  }, [sourceId, targetId]);

  const fetchExplanation = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.post('/api/entity-resolution/explain-link', {
        source_entity_id: sourceId,
        target_entity_id: targetId,
      });
      setData(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load link explanation');
    } finally {
      setLoading(false);
    }
  };

  const handleVerify = async (action) => {
    setVerifying(true);
    try {
      // No badge is sent. The reviewer is taken from the authenticated token
      // server-side: a badge number supplied by the browser is an unverified
      // claim about who performed the review, and that is the one field that
      // must not be assertable by the client.
      const res = await apiClient.post('/api/verification/verify-relationship', {
        source_entity_id: sourceId,
        target_entity_id: targetId,
        action: action,
        notes: action === 'VERIFY' ? 'Analyst confirmed relationship' : action === 'REJECT' ? 'Insufficient evidence' : 'Needs more data',
      });
      setVerificationResult(res.data.verification);
    } catch (err) {
      console.error('Verification failed:', err);
    } finally {
      setVerifying(false);
    }
  };

  if (!sourceId || !targetId) return null;

  const confidenceColors = data ? (CONFIDENCE_COLORS[data.confidence?.level] || CONFIDENCE_COLORS.SPECULATIVE) : CONFIDENCE_COLORS.SPECULATIVE;
  const stateStyle = data ? (STATE_STYLES[verificationResult?.state || data.intelligence_state] || STATE_STYLES.PENDING) : STATE_STYLES.PENDING;
  const StateIcon = stateStyle.icon;

  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />

      {/* Slide-over Panel */}
      <div
        className="relative w-full max-w-xl h-full bg-[#0a1020] border-l border-cyan-500/30 shadow-[-20px_0_60px_rgba(6,182,212,0.1)] overflow-y-auto animate-slide-in-right"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 z-10 bg-[#0a1020]/95 backdrop-blur-md border-b border-[#1c2d52] p-5">
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center">
                <FileSearch className="w-5 h-5 text-cyan-400" />
              </div>
              <div>
                <h2 className="text-sm font-bold text-slate-100 uppercase tracking-wider flex items-center gap-2">
                  Why This Link?
                  <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
                </h2>
                <p className="text-[11px] text-slate-400 mt-0.5">Evidence-backed relationship analysis</p>
              </div>
            </div>
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 border border-transparent hover:border-rose-500/30 transition-all"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Entity Names */}
          <div className="mt-4 flex items-center gap-3 text-xs">
            <span className="px-2.5 py-1 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 font-mono font-bold truncate max-w-[180px]">
              {sourceName || sourceId}
            </span>
            <Link2 className="w-4 h-4 text-cyan-400 flex-shrink-0" />
            <span className="px-2.5 py-1 rounded-lg bg-purple-500/10 border border-purple-500/30 text-purple-300 font-mono font-bold truncate max-w-[180px]">
              {targetName || targetId}
            </span>
          </div>
        </div>

        {/* Content */}
        <div className="p-5 space-y-5">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-16 space-y-4">
              <div className="w-12 h-12 rounded-xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center animate-pulse">
                <FileSearch className="w-6 h-6 text-cyan-400 animate-spin" />
              </div>
              <span className="text-xs font-mono text-cyan-400 tracking-wider">ANALYZING RELATIONSHIP...</span>
            </div>
          ) : error ? (
            <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-xs text-rose-300">
              <p className="font-bold">Analysis Error</p>
              <p className="mt-1">{error}</p>
            </div>
          ) : data ? (
            <div className="space-y-5 stagger-children">

              {/* ─── Confidence Gauge ─────────────────────────────── */}
              <div className={`p-4 rounded-2xl bg-[#0c1326] border ${confidenceColors.border} ${confidenceColors.glow}`}>
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs font-bold text-slate-300 uppercase tracking-wider">Confidence Score</span>
                  <span className={`text-2xl font-black ${confidenceColors.text} font-mono`}>
                    {data.confidence?.score}%
                  </span>
                </div>

                {/* Gauge bar */}
                <div className="w-full h-3 bg-[#070b14] rounded-full overflow-hidden border border-[#162547] mb-2">
                  <div
                    className={`h-full rounded-full ${confidenceColors.bg} animate-gauge-fill transition-all`}
                    style={{ width: `${data.confidence?.score || 0}%` }}
                  />
                </div>

                <div className="flex items-center justify-between text-[10px] font-mono">
                  <span className={`px-2 py-0.5 rounded-full ${confidenceColors.text} ${stateStyle.bg} border ${stateStyle.border} font-bold`}>
                    {data.confidence?.label}
                  </span>
                  <span className="text-slate-400">{data.confidence?.meaning}</span>
                </div>
              </div>

              {/* ─── Intelligence State ───────────────────────────── */}
              <div className={`p-3.5 rounded-xl ${stateStyle.bg} border ${stateStyle.border} flex items-center justify-between`}>
                <div className="flex items-center gap-2.5">
                  <StateIcon className={`w-5 h-5 ${stateStyle.text}`} />
                  <div>
                    <span className={`text-xs font-bold ${stateStyle.text} uppercase tracking-wider`}>
                      {verificationResult?.state || data.intelligence_state}
                    </span>
                    <p className="text-[10px] text-slate-400 mt-0.5">
                      {data.intelligence_state === 'CORROBORATED'
                        ? `${data.independent_source_count} independent sources agree`
                        : data.intelligence_state === 'VERIFIED'
                        ? 'Analyst-verified relationship'
                        : 'AI-detected lead — analyst verification pending'}
                    </p>
                  </div>
                </div>
                <span className="text-[10px] font-mono text-slate-500">
                  {data.matched_signal_count}/{data.total_signal_count} signals
                </span>
              </div>

              {/* ─── Signal Breakdown ─────────────────────────────── */}
              <div className="space-y-2">
                <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
                  <Fingerprint className="w-3.5 h-3.5 text-cyan-400" />
                  Signal Breakdown
                </h3>
                <div className="space-y-2">
                  {data.signal_breakdown?.map((sig, i) => {
                    const SigIcon = SIGNAL_ICONS[sig.signal_type] || HelpCircle;
                    return (
                      <div
                        key={i}
                        className={`p-3 rounded-xl border transition-all ${
                          sig.matched
                            ? 'bg-emerald-500/5 border-emerald-500/30'
                            : 'bg-[#0e172e] border-[#1c2d52] opacity-50'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2.5">
                            {sig.matched ? (
                              <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                            ) : (
                              <XCircle className="w-4 h-4 text-slate-500 flex-shrink-0" />
                            )}
                            <SigIcon className={`w-3.5 h-3.5 ${sig.matched ? 'text-cyan-400' : 'text-slate-500'}`} />
                            <span className={`text-xs font-semibold ${sig.matched ? 'text-slate-200' : 'text-slate-500'}`}>
                              {sig.description}
                            </span>
                          </div>
                          <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded ${
                            sig.matched ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30' : 'bg-slate-500/10 text-slate-500'
                          }`}>
                            {sig.contribution}
                          </span>
                        </div>
                        {sig.matched && sig.value && (
                          <div className="mt-2 ml-9 text-[10px] font-mono text-slate-400 bg-[#070b14] px-2.5 py-1.5 rounded-lg border border-[#162547] break-all">
                            {typeof sig.value === 'object' ? JSON.stringify(sig.value) : String(sig.value)}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* ─── Evidence Cards ───────────────────────────────── */}
              {data.evidence_cards?.length > 0 && (
                <div className="space-y-2">
                  <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
                    <Eye className="w-3.5 h-3.5 text-cyan-400" />
                    Supporting Evidence ({data.evidence_cards.length} sources)
                  </h3>
                  <div className="space-y-2">
                    {data.evidence_cards.map((ev, i) => {
                      const badge = SOURCE_TYPE_BADGE[ev.source_type] || SOURCE_TYPE_BADGE.SURFACE_WEB;
                      return (
                        <div key={i} className="p-3.5 rounded-xl bg-[#0e172e] border border-[#1c2d52] hover:border-cyan-500/30 transition-all space-y-2">
                          <div className="flex items-center justify-between gap-2">
                            <span className={`text-[9px] font-mono font-bold px-2 py-0.5 rounded border ${badge.bg} ${badge.color} ${badge.border}`}>
                              {ev.source_type}
                            </span>
                            <span className="text-[9px] font-mono text-slate-500">{ev.source_id}</span>
                          </div>
                          <p className="text-[11px] text-slate-300 leading-relaxed">{ev.snippet}</p>
                          <div className="flex items-center justify-between text-[9px] font-mono text-slate-500">
                            <span className="truncate max-w-[200px]">{ev.url}</span>
                            <div className="flex items-center gap-1">
                              <Clock className="w-2.5 h-2.5" />
                              <span>{ev.timestamp?.split('T')[0]}</span>
                            </div>
                          </div>
                          {ev.reliability && (
                            <div className="text-[9px] font-mono text-slate-500">
                              Reliability: <span className={`font-bold ${
                                ev.reliability.rating === 'HIGH' ? 'text-emerald-400' :
                                ev.reliability.rating === 'MEDIUM' ? 'text-amber-400' : 'text-slate-400'
                              }`}>{ev.reliability.rating}</span>
                              <span className="mx-1">—</span>
                              {ev.reliability.note}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* ─── Contradictions ───────────────────────────────── */}
              {data.contradictions?.length > 0 && (
                <div className="space-y-2">
                  <h3 className="text-xs font-bold text-amber-400 uppercase tracking-wider flex items-center gap-2">
                    <AlertTriangle className="w-3.5 h-3.5" />
                    Contradictions ({data.contradictions.length})
                  </h3>
                  {data.contradictions.map((c, i) => (
                    <div key={i} className="p-3 rounded-xl bg-amber-500/5 border border-amber-500/30 text-xs text-amber-300">
                      <span className="font-bold">{c.severity}:</span> {c.note}
                    </div>
                  ))}
                </div>
              )}

              {/* ─── Corroboration Assessment ────────────────────── */}
              {data.corroboration && (
                <div className="p-4 rounded-xl bg-[#0c1326] border border-[#1c2d52] space-y-3">
                  <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
                    <Shield className="w-3.5 h-3.5 text-cyan-400" />
                    Corroboration Assessment
                  </h3>
                  <div className="grid grid-cols-2 gap-2 text-[10px] font-mono">
                    <div className="p-2 rounded-lg bg-[#070b14] border border-[#162547]">
                      <div className="text-slate-500">Level</div>
                      <div className="text-cyan-400 font-bold">{data.corroboration.corroboration_level}</div>
                    </div>
                    <div className="p-2 rounded-lg bg-[#070b14] border border-[#162547]">
                      <div className="text-slate-500">Evidence Strength</div>
                      <div className="text-emerald-400 font-bold">{data.corroboration.evidence_strength}%</div>
                    </div>
                    <div className="p-2 rounded-lg bg-[#070b14] border border-[#162547]">
                      <div className="text-slate-500">Independent Sources</div>
                      <div className="text-slate-200 font-bold">{data.corroboration.independent_source_count}</div>
                    </div>
                    <div className="p-2 rounded-lg bg-[#070b14] border border-[#162547]">
                      <div className="text-slate-500">Temporal</div>
                      <div className="text-slate-200 font-bold">{data.corroboration.temporal_analysis?.span || 'N/A'}</div>
                    </div>
                  </div>
                </div>
              )}

              {/* ─── Analyst Verification Actions ────────────────── */}
              <div className="p-4 rounded-xl bg-[#0c1326] border border-cyan-500/20 space-y-3">
                <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider">
                  Analyst Verification
                </h3>
                {verificationResult ? (
                  <div className={`p-3 rounded-xl ${STATE_STYLES[verificationResult.state]?.bg || 'bg-slate-500/10'} border ${STATE_STYLES[verificationResult.state]?.border || 'border-slate-500/30'}`}>
                    <div className="flex items-center gap-2">
                      {verificationResult.state === 'VERIFIED' && <ShieldCheck className="w-4 h-4 text-emerald-400" />}
                      {verificationResult.state === 'REJECTED' && <ShieldAlert className="w-4 h-4 text-rose-400" />}
                      <span className={`text-xs font-bold ${STATE_STYLES[verificationResult.state]?.text || 'text-slate-300'}`}>
                        {verificationResult.message}
                      </span>
                    </div>
                    <p className="text-[10px] font-mono text-slate-400 mt-1">
                      Reviewed by {verificationResult.reviewed_by} • {verificationResult.timestamp}
                    </p>
                    {/* Whether the judgement actually reached the graph. It
                        previously lived only in server memory, so a rejected
                        edge kept being drawn and the decision was lost on the
                        next restart. */}
                    {verificationResult.persisted?.status === 'SUCCESS' ? (
                      <p className="text-[10px] font-mono text-slate-400 mt-1">
                        Saved to {verificationResult.persisted.edges_updated} graph edge
                        {verificationResult.persisted.edges_updated === 1 ? '' : 's'}
                        {verificationResult.persisted.hidden_from_default_view
                          ? ' — now hidden from the default graph view'
                          : ''}
                      </p>
                    ) : (
                      <p className="text-[10px] font-mono text-amber-400/80 mt-1">
                        Recorded against the relationship, but no matching graph
                        edge was found to update.
                      </p>
                    )}
                  </div>
                ) : (
                  <div className="flex gap-2">
                    <button
                      onClick={() => handleVerify('VERIFY')}
                      disabled={verifying}
                      className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-emerald-500/15 border border-emerald-500/40 text-emerald-300 text-xs font-bold hover:bg-emerald-500/25 transition-all disabled:opacity-50"
                    >
                      <ThumbsUp className="w-3.5 h-3.5" />
                      Verify
                    </button>
                    <button
                      onClick={() => handleVerify('REJECT')}
                      disabled={verifying}
                      className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-rose-500/15 border border-rose-500/40 text-rose-300 text-xs font-bold hover:bg-rose-500/25 transition-all disabled:opacity-50"
                    >
                      <ThumbsDown className="w-3.5 h-3.5" />
                      Reject
                    </button>
                    <button
                      onClick={() => handleVerify('REQUEST_MORE')}
                      disabled={verifying}
                      className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-amber-500/15 border border-amber-500/40 text-amber-300 text-xs font-bold hover:bg-amber-500/25 transition-all disabled:opacity-50"
                    >
                      <HelpCircle className="w-3.5 h-3.5" />
                      Need More
                    </button>
                  </div>
                )}
              </div>

              {/* ─── Metadata Footer ─────────────────────────────── */}
              <div className="text-[9px] font-mono text-slate-500 p-3 rounded-xl bg-[#070b14] border border-[#162547] space-y-1">
                <div>Inferential Hops: {data.inferential_hops}</div>
                <div>A confidence score is an analytical confidence measure, not a probability of guilt.</div>
                <div>AI findings are investigative leads until appropriately corroborated and verified.</div>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
};
