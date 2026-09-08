import React, { useState, useEffect, useCallback } from 'react';
import { apiClient } from '../api/client';
import { WhyThisLink } from '../components/WhyThisLink';
import {
  Fingerprint, Search, Users, Link2, ShieldCheck, ShieldQuestion,
  AlertTriangle, ChevronRight, Eye, Sparkles, RefreshCw, Filter,
  AtSign, Wallet, MessageCircle, Globe, Clock, CheckCircle2, XCircle,
  Zap, TrendingUp, ArrowRight, ExternalLink, Database
} from 'lucide-react';

// ─── Visual helpers ──────────────────────────────────────────────
const TYPE_STYLES = {
  suspect: { bg: 'bg-rose-500/10', border: 'border-rose-500/30', text: 'text-rose-400', icon: '◆', shape: 'rounded-lg' },
  vendor: { bg: 'bg-purple-500/10', border: 'border-purple-500/30', text: 'text-purple-400', icon: '⬠', shape: 'rounded-lg' },
  channel: { bg: 'bg-blue-500/10', border: 'border-blue-500/30', text: 'text-blue-400', icon: '●', shape: 'rounded-full' },
  marketplace: { bg: 'bg-violet-500/10', border: 'border-violet-500/30', text: 'text-violet-400', icon: '◼', shape: 'rounded-lg' },
  wallet: { bg: 'bg-amber-500/10', border: 'border-amber-500/30', text: 'text-amber-400', icon: '⬡', shape: 'rounded-lg' },
};

const CONFIDENCE_STYLES = {
  VERY_HIGH: { bg: 'bg-emerald-500', text: 'text-emerald-400', barBg: 'from-emerald-500 to-green-400' },
  HIGH: { bg: 'bg-cyan-500', text: 'text-cyan-400', barBg: 'from-cyan-500 to-blue-400' },
  MODERATE: { bg: 'bg-amber-500', text: 'text-amber-400', barBg: 'from-amber-500 to-orange-400' },
  LOW: { bg: 'bg-orange-500', text: 'text-orange-400', barBg: 'from-orange-500 to-red-400' },
  SPECULATIVE: { bg: 'bg-slate-500', text: 'text-slate-400', barBg: 'from-slate-500 to-slate-600' },
};

const getTypeStyle = (type) => TYPE_STYLES[type] || TYPE_STYLES.suspect;
const getConfStyle = (level) => CONFIDENCE_STYLES[level] || CONFIDENCE_STYLES.SPECULATIVE;

export const EntityExplorer = () => {
  const [entities, setEntities] = useState([]);
  const [relationships, setRelationships] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState('ALL');
  const [selectedEntity, setSelectedEntity] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [candidatesLoading, setCandidatesLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('entities'); // 'entities' | 'relationships'
  const [explainLink, setExplainLink] = useState(null);
  const [isOffline, setIsOffline] = useState(false);

  // ─── Fetch data ────────────────────────────────────────────────
  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [entRes, relRes] = await Promise.all([
        apiClient.get('/api/entity-resolution/entities', { timeout: 3000 }),
        apiClient.get('/api/entity-resolution/relationships', { timeout: 3000 }),
      ]);
      setEntities(entRes.data.entities || []);
      setRelationships(relRes.data.relationships || []);
      setIsOffline(false);
    } catch (e) {
      console.error('EntityExplorer: failed to fetch data:', e.message);
      setEntities([]);
      setRelationships([]);
    } finally {
      setLoading(false);
    }
  };

  // ─── Fetch candidates for selected entity ─────────────────────
  const fetchCandidates = async (entityId) => {
    setCandidatesLoading(true);
    try {
      const res = await apiClient.get(`/api/entity-resolution/candidates/${entityId}`, { timeout: 3000 });
      setCandidates(res.data.candidates || []);
    } catch (e) {
      setCandidates([]);
    } finally {
      setCandidatesLoading(false);
    }
  };

  const handleSelectEntity = (entity) => {
    setSelectedEntity(entity);
    fetchCandidates(entity.id);
  };

  // ─── Filters ───────────────────────────────────────────────────
  const entityTypes = ['ALL', ...new Set(entities.map(e => e.type))];

  const filteredEntities = entities.filter(e => {
    const matchesSearch = e.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      e.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (e.aliases || []).some(a => a.toLowerCase().includes(searchQuery.toLowerCase()));
    const matchesType = typeFilter === 'ALL' || e.type === typeFilter;
    return matchesSearch && matchesType;
  });

  const filteredRelationships = relationships.filter(r => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return r.source_entity.name.toLowerCase().includes(q) ||
      r.target_entity.name.toLowerCase().includes(q);
  });

  // ─── Loading skeleton ─────────────────────────────────────────
  if (loading) {
    return (
      <div className="p-6 space-y-6 max-w-7xl mx-auto">
        <div className="glass-card rounded-xl p-5 border-l-4 border-cyan-500">
          <div className="skeleton h-6 w-64 mb-2" />
          <div className="skeleton h-3 w-96" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3, 4, 5, 6].map(i => (
            <div key={i} className="glass-card rounded-xl p-5 space-y-3">
              <div className="skeleton h-3 w-20" />
              <div className="skeleton h-5 w-40" />
              <div className="skeleton h-3 w-32" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* ─── Header Banner ──────────────────────────────────────── */}
      <div className="glass-card rounded-xl p-5 border-l-4 border-cyan-500 animate-fade-in-up">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
              <Fingerprint className="w-5 h-5 text-cyan-400" />
              Entity Resolution & Identity Correlation
            </h2>
            <p className="text-xs text-slate-400 mt-1 font-mono">
              Cross-Platform Identity Matching • Confidence Scoring • Signal Decomposition • Evidence Provenance
            </p>
          </div>
          <div className="flex items-center gap-3">
            {isOffline && (
              <span className="text-[9px] font-mono px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30">DEMO MODE</span>
            )}
            <button
              onClick={fetchData}
              className="p-2 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 hover:bg-cyan-500/20 transition-all"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* ─── Stats Row ──────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 stagger-children">
        {[
          { label: 'Known Entities', value: entities.length, color: 'cyan', icon: Users },
          { label: 'Relationships', value: relationships.length, color: 'purple', icon: Link2 },
          { label: 'High Confidence', value: relationships.filter(r => r.confidence >= 75).length, color: 'emerald', icon: ShieldCheck },
          { label: 'Contradictions', value: relationships.reduce((sum, r) => sum + (r.contradictions_count || 0), 0), color: 'amber', icon: AlertTriangle },
        ].map((stat, i) => (
          <div key={i} className="glass-card glass-card-hover rounded-xl p-4 border border-[#1c2d52]">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] uppercase font-mono tracking-wider text-slate-400">{stat.label}</span>
              <stat.icon className={`w-4 h-4 text-${stat.color}-400`} />
            </div>
            <div className={`text-xl font-bold font-mono text-${stat.color}-400 animate-count-pop`}>{stat.value}</div>
          </div>
        ))}
      </div>

      {/* ─── Tab Switcher ───────────────────────────────────────── */}
      <div className="flex items-center gap-1 p-1 rounded-xl bg-[#0d1527] border border-[#1c2d52] w-fit">
        {[
          { key: 'entities', label: 'Entity Browser', icon: Users },
          { key: 'relationships', label: 'Relationship Map', icon: Link2 },
        ].map(tab => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold font-mono transition-all ${
              activeTab === tab.key
                ? 'bg-cyan-500/15 text-cyan-300 border border-cyan-500/40 shadow-[0_0_15px_rgba(6,182,212,0.15)]'
                : 'text-slate-400 hover:text-slate-200 border border-transparent'
            }`}
          >
            <tab.icon className="w-3.5 h-3.5" />
            {tab.label}
          </button>
        ))}
      </div>

      {/* ─── Search & Filter Bar ────────────────────────────────── */}
      <div className="flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search entities, aliases, IDs..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-[#0d1527] border border-[#1c2d52] text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500/50 font-mono"
          />
        </div>
        {activeTab === 'entities' && (
          <div className="flex gap-1.5">
            {entityTypes.map(type => (
              <button
                key={type}
                onClick={() => setTypeFilter(type)}
                className={`px-3 py-2 rounded-xl text-[10px] font-mono font-bold border transition-all capitalize ${
                  typeFilter === type
                    ? 'bg-cyan-500/15 text-cyan-300 border-cyan-500/40'
                    : 'bg-[#14203b] text-slate-400 border-[#1c2d52] hover:text-slate-200'
                }`}
              >
                {type === 'ALL' ? 'All Types' : type}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* ─── Main Content ───────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* ── Left: Entity/Relationship List ── */}
        <div className="lg:col-span-2 space-y-4">
          {activeTab === 'entities' ? (
            /* ── ENTITY GRID ── */
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 stagger-children">
              {filteredEntities.map((entity) => {
                const style = getTypeStyle(entity.type);
                const isSelected = selectedEntity?.id === entity.id;
                return (
                  <div
                    key={entity.id}
                    onClick={() => handleSelectEntity(entity)}
                    className={`glass-card rounded-xl p-4 border cursor-pointer transition-all hover:shadow-[0_0_20px_rgba(6,182,212,0.1)] ${
                      isSelected
                        ? 'border-cyan-500/50 bg-cyan-500/5 ring-1 ring-cyan-500/30'
                        : 'border-[#1c2d52] hover:border-cyan-500/30'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <div className="flex items-center gap-2">
                        <span className={`w-8 h-8 ${style.shape} ${style.bg} border ${style.border} flex items-center justify-center text-sm ${style.text}`}>
                          {style.icon}
                        </span>
                        <div>
                          <div className="text-xs font-bold text-slate-100">{entity.name}</div>
                          <div className="text-[10px] font-mono text-slate-500 capitalize">{entity.type}</div>
                        </div>
                      </div>
                      {entity.threat_level && (
                        <span className={`text-[9px] font-mono font-bold px-2 py-0.5 rounded border ${
                          entity.threat_level === 'SEVERE' ? 'bg-rose-500/20 text-rose-400 border-rose-500/30' :
                          entity.threat_level === 'HIGH' ? 'bg-amber-500/20 text-amber-400 border-amber-500/30' :
                          'bg-yellow-500/20 text-yellow-300 border-yellow-500/30'
                        }`}>{entity.threat_level}</span>
                      )}
                    </div>

                    {entity.platform && (
                      <div className="text-[10px] font-mono text-slate-400 mb-1.5 flex items-center gap-1">
                        <Globe className="w-3 h-3 text-slate-500" />
                        {entity.platform}
                      </div>
                    )}

                    {entity.aliases && entity.aliases.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-2">
                        {entity.aliases.map((alias, i) => (
                          <span key={i} className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-[#14203b] text-slate-400 border border-[#1c2d52]">
                            {alias}
                          </span>
                        ))}
                      </div>
                    )}

                    <div className="mt-2 text-[9px] font-mono text-slate-500 truncate">
                      ID: {entity.id}
                    </div>
                  </div>
                );
              })}

              {filteredEntities.length === 0 && (
                <div className="col-span-full p-8 text-center glass-card rounded-xl border border-[#1c2d52]">
                  <Search className="w-8 h-8 text-slate-600 mx-auto mb-3" />
                  <p className="text-xs text-slate-500 font-mono">No entities match your search criteria.</p>
                </div>
              )}
            </div>
          ) : (
            /* ── RELATIONSHIP TABLE ── */
            <div className="glass-card rounded-xl border border-[#1c2d52] overflow-hidden">
              <div className="p-4 border-b border-[#1c2d52] flex items-center justify-between">
                <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
                  <Link2 className="w-4 h-4 text-cyan-400" />
                  All Known Relationships
                </h3>
                <span className="text-xs font-mono text-cyan-400">{filteredRelationships.length} Links</span>
              </div>
              <div className="divide-y divide-[#1c2d52] max-h-[600px] overflow-y-auto">
                {filteredRelationships.map((rel, i) => {
                  const confStyle = getConfStyle(rel.confidence_level);
                  const srcStyle = getTypeStyle(rel.source_entity.type);
                  const tgtStyle = getTypeStyle(rel.target_entity.type);
                  return (
                    <div
                      key={i}
                      onClick={() => setExplainLink({
                        sourceId: rel.source_entity.id,
                        targetId: rel.target_entity.id,
                        sourceName: rel.source_entity.name,
                        targetName: rel.target_entity.name,
                      })}
                      className="p-4 hover:bg-[#14203b]/40 transition-all cursor-pointer group"
                    >
                      <div className="flex items-center gap-3 mb-2">
                        {/* Source */}
                        <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded border ${srcStyle.bg} ${srcStyle.text} ${srcStyle.border} truncate max-w-[160px]`}>
                          {rel.source_entity.name}
                        </span>
                        <ArrowRight className="w-3.5 h-3.5 text-cyan-400 flex-shrink-0 group-hover:text-cyan-300 transition-colors" />
                        {/* Target */}
                        <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded border ${tgtStyle.bg} ${tgtStyle.text} ${tgtStyle.border} truncate max-w-[160px]`}>
                          {rel.target_entity.name}
                        </span>
                      </div>

                      <div className="flex items-center gap-4">
                        {/* Confidence bar */}
                        <div className="flex-1">
                          <div className="w-full h-2 bg-[#070b14] rounded-full overflow-hidden border border-[#162547]">
                            <div
                              className={`h-full rounded-full bg-gradient-to-r ${confStyle.barBg} animate-gauge-fill`}
                              style={{ width: `${rel.confidence}%` }}
                            />
                          </div>
                        </div>
                        <span className={`text-xs font-bold font-mono ${confStyle.text} min-w-[40px] text-right`}>
                          {rel.confidence}%
                        </span>
                        <span className={`text-[9px] font-mono px-2 py-0.5 rounded ${confStyle.text} bg-[#14203b] border border-[#1c2d52]`}>
                          {rel.confidence_level}
                        </span>
                      </div>

                      <div className="flex items-center gap-4 mt-2 text-[9px] font-mono text-slate-500">
                        <span className="flex items-center gap-1">
                          <CheckCircle2 className="w-2.5 h-2.5 text-emerald-400" />
                          {rel.matched_signals} signals
                        </span>
                        <span className="flex items-center gap-1">
                          <Eye className="w-2.5 h-2.5 text-cyan-400" />
                          {rel.evidence_count} evidence
                        </span>
                        {rel.contradictions_count > 0 && (
                          <span className="flex items-center gap-1 text-amber-400">
                            <AlertTriangle className="w-2.5 h-2.5" />
                            {rel.contradictions_count} contradictions
                          </span>
                        )}
                        <span className="ml-auto text-cyan-400 opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1">
                          <Sparkles className="w-2.5 h-2.5" />
                          Click to explain
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* ── Right: Selected Entity Detail / Candidates ── */}
        <div className="space-y-4">
          {selectedEntity ? (
            <>
              {/* Entity Detail Card */}
              <div className="glass-card rounded-xl p-5 border border-cyan-500/30 bg-gradient-to-b from-[#0d1629] to-[#0a1020] space-y-3 animate-fade-in-up">
                <div className="flex items-center gap-3">
                  <div className={`w-12 h-12 ${getTypeStyle(selectedEntity.type).shape} ${getTypeStyle(selectedEntity.type).bg} border ${getTypeStyle(selectedEntity.type).border} flex items-center justify-center text-xl ${getTypeStyle(selectedEntity.type).text}`}>
                    {getTypeStyle(selectedEntity.type).icon}
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-slate-100">{selectedEntity.name}</h3>
                    <span className="text-[10px] font-mono text-slate-400 capitalize">{selectedEntity.type} • {selectedEntity.platform}</span>
                  </div>
                </div>

                <div className="text-[10px] font-mono text-slate-500 bg-[#070b14] p-2.5 rounded-lg border border-[#162547]">
                  ID: <span className="text-cyan-400">{selectedEntity.id}</span>
                </div>

                {selectedEntity.aliases?.length > 0 && (
                  <div>
                    <div className="text-[10px] uppercase font-mono text-slate-400 mb-1.5">Known Aliases</div>
                    <div className="flex flex-wrap gap-1.5">
                      {selectedEntity.aliases.map((alias, i) => (
                        <span key={i} className="text-[10px] font-mono px-2 py-0.5 rounded bg-purple-500/10 text-purple-300 border border-purple-500/30">
                          <AtSign className="w-2.5 h-2.5 inline mr-0.5" />{alias}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Candidate Matches */}
              <div className="glass-card rounded-xl p-5 border border-[#1c2d52] space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
                    <Fingerprint className="w-4 h-4 text-cyan-400" />
                    Identity Candidates
                  </h3>
                  <span className="text-[10px] font-mono text-cyan-400">
                    {candidatesLoading ? 'Loading...' : `${candidates.length} Matches`}
                  </span>
                </div>

                {candidatesLoading ? (
                  <div className="space-y-2">
                    {[1, 2].map(i => <div key={i} className="skeleton h-16 rounded-xl" />)}
                  </div>
                ) : candidates.length > 0 ? (
                  <div className="space-y-2">
                    {candidates.map((cand, i) => {
                      const candStyle = getTypeStyle(cand.type);
                      return (
                        <div
                          key={i}
                          onClick={() => setExplainLink({
                            sourceId: selectedEntity.id,
                            targetId: cand.entity_id,
                            sourceName: selectedEntity.name,
                            targetName: cand.name,
                          })}
                          className="p-3 rounded-xl bg-[#0e172e] border border-[#1c2d52] hover:border-cyan-500/30 transition-all cursor-pointer space-y-2"
                        >
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              <span className={`w-6 h-6 ${candStyle.shape} ${candStyle.bg} border ${candStyle.border} flex items-center justify-center text-xs ${candStyle.text}`}>
                                {candStyle.icon}
                              </span>
                              <span className="text-xs font-bold text-slate-200">{cand.name}</span>
                            </div>
                            <span className={`text-xs font-bold font-mono ${cand.confidence >= 75 ? 'text-emerald-400' : cand.confidence >= 50 ? 'text-amber-400' : 'text-slate-400'}`}>
                              {cand.confidence}%
                            </span>
                          </div>

                          <div className="w-full h-1.5 bg-[#070b14] rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full bg-gradient-to-r ${cand.confidence >= 75 ? 'from-emerald-500 to-green-400' : cand.confidence >= 50 ? 'from-amber-500 to-orange-400' : 'from-slate-500 to-slate-600'}`}
                              style={{ width: `${cand.confidence}%` }}
                            />
                          </div>

                          <div className="text-[9px] font-mono text-slate-500">
                            {cand.matched_signals} signals matched • {cand.reason}
                          </div>

                          <div className="text-[9px] font-mono text-cyan-400 flex items-center gap-1">
                            <Sparkles className="w-2.5 h-2.5" />
                            Click to view full explanation
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="p-4 text-center text-xs text-slate-500 font-mono rounded-xl bg-[#0e172e] border border-dashed border-[#1c2d52]">
                    No candidate identity matches found for this entity.
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="glass-card rounded-xl p-8 border border-[#1c2d52] text-center space-y-3">
              <Fingerprint className="w-10 h-10 text-slate-600 mx-auto" />
              <h4 className="text-sm font-bold text-slate-400 uppercase font-mono">Select an Entity</h4>
              <p className="text-xs text-slate-500 font-mono max-w-xs mx-auto">
                Click any entity card to view identity candidates, signal breakdowns, and cross-platform correlation evidence.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* ─── Why This Link? Panel ───────────────────────────────── */}
      {explainLink && (
        <WhyThisLink
          sourceId={explainLink.sourceId}
          targetId={explainLink.targetId}
          sourceName={explainLink.sourceName}
          targetName={explainLink.targetName}
          onClose={() => setExplainLink(null)}
        />
      )}
    </div>
  );
};
