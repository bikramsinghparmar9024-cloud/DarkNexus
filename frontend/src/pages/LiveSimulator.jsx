import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import {
  Radio,
  Send,
  Zap,
  ShieldAlert,
  AlertTriangle,
  CheckCircle2,
  FileCheck,
  Compass,
  Cpu,
  Share2,
  RefreshCw,
  Clock,
  Sparkles
} from 'lucide-react';

export const LiveSimulator = () => {
  const [scenarios, setScenarios] = useState([]);
  const [loadingScenarios, setLoadingScenarios] = useState(true);

  // Form input state
  const [sourceType, setSourceType] = useState('TELEGRAM');
  const [rawText, setRawText] = useState('Veere khemkaran border te drone drop ho gya, 5kg chitta chakko. GPS location send kar reha behind tubewell. Jaldi khata clear karo.');
  const [author, setAuthor] = useState('@pak_pb_transit');
  const [sourceUrl, setSourceUrl] = useState('https://t.me/s/border_transit_alert/481');

  // Pipeline execution state
  const [processing, setProcessing] = useState(false);
  const [result, setResult] = useState(null);
  const [liveLog, setLiveLog] = useState([]);

  useEffect(() => {
    loadScenarios();
  }, []);

  const loadScenarios = async () => {
    try {
      const res = await apiClient.get('/api/simulator/scenarios');
      setScenarios(res.data);
    } catch (e) {
      console.error('Failed to load scenarios:', e);
    } finally {
      setLoadingScenarios(false);
    }
  };

  const selectScenario = (sc) => {
    setSourceType(sc.source_type);
    setRawText(sc.raw_text);
    setAuthor(sc.author);
    setSourceUrl(sc.source_url);
    setResult(null);
    setLiveLog([`Preset loaded: ${sc.title} (${sc.location})`]);
  };

  const handleRunPipeline = async (e) => {
    if (e) e.preventDefault();
    if (!rawText.trim()) return;

    setProcessing(true);
    setResult(null);
    setLiveLog([
      'Intercept received at Tactical Ingestion Gateway...',
      'Executing Punjabi/Gurmukhi Slang Normalization Engine...',
      'Running spaCy NER for Narcotic Substances & Contact Identifiers...',
      'Calculating Geospatial Proximity to 553km Indo-Pak International Border...',
      'Generating Cryptographic SHA-256 Digest for Section 65B Court Prosecution...'
    ]);

    try {
      const res = await apiClient.post('/api/simulator/ingest', {
        source_type: sourceType,
        text: rawText,
        author: author,
        source_url: sourceUrl
      });

      setResult(res.data);
      setLiveLog((prev) => [
        ...prev,
        `✓ Threat Classified: ${res.data.threat_level}`,
        `✓ Border Alert: ${res.data.border_danger_zone ? 'CRITICAL (< 15KM CORRIDOR)' : 'Inland Hub'}`,
        `✓ SHA-256 Digest Sealed: ${res.data.sha256_hash.slice(0, 24)}...`,
        `✓ Dispatched via WebSocket to Punjab Police Command Center.`
      ]);
    } catch (err) {
      console.error(err);
      setLiveLog((prev) => [...prev, '❌ Pipeline Error: Could not process intercept.']);
    } finally {
      setProcessing(false);
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Top Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="p-1.5 rounded-lg bg-red-500/10 text-red-400 border border-red-500/20">
              <Radio className="w-5 h-5 animate-pulse" />
            </span>
            <h2 className="text-xl font-bold uppercase tracking-wider text-slate-100 font-mono">
              Tactical Live Wiretap & Ingestion Simulator
            </h2>
          </div>
          <p className="text-xs text-slate-400 font-mono mt-1">
            Simulate real-time multi-source chatter, regional slang normalization, Indo-Pak border radar triggers, and Section 65B legal court evidence hashing.
          </p>
        </div>

        <div className="flex items-center gap-2 text-xs font-mono text-cyan-400 bg-cyan-950/40 border border-cyan-800/40 px-3 py-1.5 rounded-lg">
          <Sparkles className="w-3.5 h-3.5" />
          <span>Evaluation Demo Ready</span>
        </div>
      </div>

      {/* 1-Click Operational Presets */}
      <div>
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 font-mono mb-3 flex items-center gap-2">
          <Zap className="w-4 h-4 text-amber-400" />
          <span>1-Click Preset Operational Scenarios (Punjab Police Focus)</span>
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          {scenarios.map((sc) => (
            <button
              key={sc.id}
              onClick={() => selectScenario(sc)}
              className="text-left glass-card p-3 rounded-xl border border-[#1c2d52] hover:border-cyan-500/50 hover:bg-[#14203b] transition-all group relative overflow-hidden"
            >
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 font-bold">
                  {sc.badge}
                </span>
                <span className="text-[10px] text-slate-500 font-mono">{sc.source_type}</span>
              </div>
              <h4 className="text-xs font-bold text-slate-200 group-hover:text-cyan-300 transition-colors line-clamp-1">
                {sc.title}
              </h4>
              <p className="text-[11px] text-slate-400 mt-1 line-clamp-2">{sc.description}</p>
              <div className="mt-2 text-[10px] text-amber-400/80 font-mono flex items-center gap-1">
                <Compass className="w-3 h-3" />
                <span>{sc.location}</span>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Simulator Form & Results Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Ingestion Console Form */}
        <div className="lg:col-span-6 space-y-4">
          <div className="glass-card p-5 rounded-2xl border border-[#1c2d52] space-y-4">
            <h3 className="text-sm font-bold uppercase tracking-wider text-slate-200 font-mono flex items-center gap-2">
              <Send className="w-4 h-4 text-cyan-400" />
              <span>Intercept Injection Console</span>
            </h3>

            <form onSubmit={handleRunPipeline} className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[11px] font-mono text-slate-400 block mb-1">Source Pipeline</label>
                  <select
                    value={sourceType}
                    onChange={(e) => setSourceType(e.target.value)}
                    className="w-full bg-[#0d1527] border border-[#1c2d52] rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-400 font-mono"
                  >
                    <option value="TELEGRAM">Telegram (MTProto / Preview)</option>
                    <option value="DARK_WEB">Dark Web (.onion Tor SOCKS5h)</option>
                    <option value="SURFACE_WEB">Surface Web (Playwright Stealth)</option>
                  </select>
                </div>

                <div>
                  <label className="text-[11px] font-mono text-slate-400 block mb-1">Target / Author Handle</label>
                  <input
                    type="text"
                    value={author}
                    onChange={(e) => setAuthor(e.target.value)}
                    className="w-full bg-[#0d1527] border border-[#1c2d52] rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-400 font-mono"
                    placeholder="@handle or vendor"
                  />
                </div>
              </div>

              <div>
                <label className="text-[11px] font-mono text-slate-400 block mb-1">
                  Raw Intercept Content (Punjabi / Hindi / Romanized Slang)
                </label>
                <textarea
                  rows={4}
                  value={rawText}
                  onChange={(e) => setRawText(e.target.value)}
                  className="w-full bg-[#0d1527] border border-[#1c2d52] rounded-lg p-3 text-xs text-slate-200 focus:outline-none focus:border-cyan-400 font-mono leading-relaxed"
                  placeholder="Paste intercepted message or marketplace listing..."
                />
              </div>

              <div>
                <label className="text-[11px] font-mono text-slate-400 block mb-1">Source URL / Channel Link</label>
                <input
                  type="text"
                  value={sourceUrl}
                  onChange={(e) => setSourceUrl(e.target.value)}
                  className="w-full bg-[#0d1527] border border-[#1c2d52] rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-400 font-mono text-slate-400"
                />
              </div>

              <button
                type="submit"
                disabled={processing}
                className={`w-full py-2.5 rounded-xl font-mono text-xs font-bold uppercase tracking-wider flex items-center justify-center gap-2 transition-all ${
                  processing
                    ? 'bg-cyan-600/50 text-cyan-200 cursor-not-allowed'
                    : 'bg-cyan-500 hover:bg-cyan-400 text-slate-950 shadow-lg shadow-cyan-500/20'
                }`}
              >
                {processing ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    <span>Executing AI Pipeline...</span>
                  </>
                ) : (
                  <>
                    <Zap className="w-4 h-4" />
                    <span>Trigger Full AI Triage & Hash Seal</span>
                  </>
                )}
              </button>
            </form>
          </div>

          {/* Real-Time Pipeline Progress Log */}
          <div className="glass-card p-4 rounded-xl border border-[#1c2d52] bg-[#090e1c]/80 font-mono text-xs">
            <div className="flex items-center gap-2 text-slate-400 font-bold uppercase text-[10px] mb-2">
              <Clock className="w-3.5 h-3.5 text-cyan-400" />
              <span>Live Execution Log</span>
            </div>
            <div className="space-y-1 text-[11px] text-slate-300 max-h-36 overflow-y-auto">
              {liveLog.length === 0 && <span className="text-slate-500">Ready for intercept injection.</span>}
              {liveLog.map((log, idx) => (
                <div key={idx} className="flex items-center gap-2">
                  <span className="text-cyan-500 font-bold">›</span>
                  <span>{log}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Intelligence Decomposition & Results */}
        <div className="lg:col-span-6 space-y-4">
          {result ? (
            <div className="space-y-4 animate-fadeIn">
              {/* Threat Status Banner */}
              <div
                className={`p-4 rounded-2xl border flex items-center justify-between ${
                  result.threat_level === 'SEVERE'
                    ? 'bg-red-500/10 border-red-500/30 text-red-400'
                    : result.threat_level === 'HIGH'
                    ? 'bg-amber-500/10 border-amber-500/30 text-amber-400'
                    : 'bg-blue-500/10 border-blue-500/30 text-blue-400'
                }`}
              >
                <div className="flex items-center gap-3">
                  <ShieldAlert className="w-6 h-6" />
                  <div>
                    <h4 className="font-bold text-sm uppercase font-mono">
                      Threat Assessment: {result.threat_level}
                    </h4>
                    <p className="text-xs opacity-80 font-mono">
                      {result.border_danger_zone
                        ? 'CRITICAL WARNING: Indo-Pak Border Corridor (< 15km Zone)'
                        : 'Inland Distribution Network Incident'}
                    </p>
                  </div>
                </div>
                <span className="text-xs font-mono font-bold px-2.5 py-1 rounded bg-black/40 border border-white/10">
                  ID #{result.record_id}
                </span>
              </div>

              {/* Agent Pipeline Visualization */}
              {result.agent_pipeline && (
                <div className="glass-card p-4 rounded-xl border border-[#1c2d52] space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold uppercase text-slate-300 font-mono flex items-center gap-1.5">
                      <Cpu className="w-3.5 h-3.5 text-cyan-400" />
                      <span>Multi-Agent Intelligence Pipeline</span>
                    </span>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                      {result.agent_pipeline.filter(a => a.status === 'COMPLETE').length}/{result.agent_pipeline.length} Stages Complete
                    </span>
                  </div>
                  <div className="flex items-center gap-1 overflow-x-auto pb-1">
                    {result.agent_pipeline.map((agent, i) => {
                      const isComplete = agent.status === 'COMPLETE';
                      const isLast = i === result.agent_pipeline.length - 1;
                      return (
                        <React.Fragment key={i}>
                          <div className={`flex-shrink-0 p-2.5 rounded-xl border text-center min-w-[140px] transition-all ${
                            isComplete
                              ? 'bg-emerald-500/5 border-emerald-500/30'
                              : 'bg-amber-500/5 border-amber-500/30 animate-pulse'
                          }`}>
                            <div className="flex items-center justify-center gap-1.5 mb-1">
                              {isComplete ? (
                                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                              ) : (
                                <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                              )}
                              <span className={`text-[10px] font-mono font-bold ${isComplete ? 'text-emerald-300' : 'text-amber-300'}`}>
                                {agent.agent}
                              </span>
                            </div>
                            <p className="text-[8px] font-mono text-slate-400 leading-tight">{agent.stage}</p>
                            <p className="text-[8px] font-mono text-slate-500 mt-1 leading-tight truncate">{agent.output_summary}</p>
                          </div>
                          {!isLast && (
                            <div className="flex-shrink-0 text-cyan-500/50">
                              <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M6 4l4 4-4 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                            </div>
                          )}
                        </React.Fragment>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Stage 1: Slang Normalization Breakdown */}
              <div className="glass-card p-4 rounded-xl border border-[#1c2d52] space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold uppercase text-slate-300 font-mono flex items-center gap-1.5">
                    <Cpu className="w-3.5 h-3.5 text-cyan-400" />
                    <span>Stage 1: Regional Punjabi Slang Normalizer</span>
                  </span>
                  <span className="text-[10px] font-mono text-cyan-400">
                    {result.pipeline_stages.stage_1_slang.detected_slang_count} dialect terms translated
                  </span>
                </div>
                <div className="p-3 bg-[#0d1527] rounded-lg text-xs font-mono text-slate-200 border border-[#1c2d52] leading-relaxed">
                  {result.pipeline_stages.stage_1_slang.normalized_text}
                </div>
              </div>

              {/* Stage 2 & 4: Entities & Geospatial Grid */}
              <div className="grid grid-cols-2 gap-3">
                <div className="glass-card p-3 rounded-xl border border-[#1c2d52] space-y-1.5">
                  <span className="text-[11px] font-bold uppercase text-slate-400 font-mono flex items-center gap-1">
                    <Compass className="w-3.5 h-3.5 text-amber-400" />
                    <span>Geospatial Radar</span>
                  </span>
                  <p className="text-xs font-bold text-slate-200 font-mono">
                    {result.pipeline_stages.stage_4_geospatial.location || 'Punjab Territory'}
                  </p>
                  <p className="text-[10px] font-mono text-slate-400">
                    Distance to Border:{' '}
                    <span className="text-amber-400 font-bold">
                      {result.pipeline_stages.stage_4_geospatial.distance_to_border_km !== undefined
                        ? `${result.pipeline_stages.stage_4_geospatial.distance_to_border_km} km`
                        : 'N/A'}
                    </span>
                  </p>
                </div>

                <div className="glass-card p-3 rounded-xl border border-[#1c2d52] space-y-1.5">
                  <span className="text-[11px] font-bold uppercase text-slate-400 font-mono flex items-center gap-1">
                    <Share2 className="w-3.5 h-3.5 text-emerald-400" />
                    <span>Modus Operandi</span>
                  </span>
                  <div className="flex flex-wrap gap-1">
                    {result.pipeline_stages.stage_3_threat.modus_operandi?.length > 0 ? (
                      result.pipeline_stages.stage_3_threat.modus_operandi.map((m, i) => (
                        <span key={i} className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-300 font-mono">
                          {m}
                        </span>
                      ))
                    ) : (
                      <span className="text-[11px] text-slate-500 font-mono">Standard Trafficking</span>
                    )}
                  </div>
                </div>
              </div>

              {/* Stage 5: Section 65B Digital Evidence Digest */}
              <div className="glass-card p-4 rounded-xl border border-cyan-500/30 bg-cyan-950/10 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold uppercase text-cyan-300 font-mono flex items-center gap-1.5">
                    <FileCheck className="w-4 h-4 text-cyan-400" />
                    <span>Section 65B Indian Evidence Act Certificate</span>
                  </span>
                  <span className="text-[10px] px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-300 font-mono font-bold">
                    TAMPER-EVIDENT
                  </span>
                </div>
                <div className="font-mono text-[11px] text-slate-300 space-y-1">
                  <div>
                    <span className="text-slate-400">SHA-256 Hash: </span>
                    <span className="text-cyan-400 break-all">{result.sha256_hash}</span>
                  </div>
                  <div>
                    <span className="text-slate-400">Investigator: </span>
                    <span>Inspector PB-CID-8821 (Border Special Task Force)</span>
                  </div>
                  <div>
                    <span className="text-slate-400">Statute: </span>
                    <span>Section 65B IEA, 1872 / Section 63 BSA, 2023 (Admissible in Court)</span>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="glass-card p-12 rounded-2xl border border-[#1c2d52] text-center space-y-3">
              <Cpu className="w-10 h-10 text-slate-600 mx-auto" />
              <h4 className="text-sm font-bold text-slate-400 uppercase font-mono">Awaiting Live Intercept</h4>
              <p className="text-xs text-slate-500 max-w-sm mx-auto font-mono">
                Select a preset scenario above or type custom Romanized Punjabi chatter, then click "Trigger Full AI Triage".
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
