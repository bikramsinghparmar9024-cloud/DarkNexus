import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import { 
  Bot, 
  Sparkles, 
  Search, 
  Play, 
  ShieldAlert, 
  MapPin, 
  Phone, 
  Coins, 
  Tag, 
  CheckCircle2, 
  RefreshCw,
  Cpu
} from 'lucide-react';

export const AIIntelligence = () => {
  // RAG query state
  const [ragQuery, setRagQuery] = useState('Show all heroin / chitta distribution mentions near Amritsar border');
  const [ragResult, setRagResult] = useState(null);
  const [ragLoading, setRagLoading] = useState(false);

  // Live Text / Slang Analyzer state
  const [sampleText, setSampleText] = useState(
    'Chitta 10g grade-A available in Amritsar Majitha border. Cash on dead-drop or pay 0.045 BTC to bc1q8v7x2k9f2a4m8c3. Contact @amritsar_hawk or +91 9876543210'
  );
  const [analysisResult, setAnalysisResult] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);

  // Batch LangGraph state
  const [pipelineLoading, setPipelineLoading] = useState(false);
  const [pipelineResult, setPipelineResult] = useState(null);

  // Entities summary
  const [summary, setSummary] = useState(null);

  useEffect(() => {
    loadSummary();
    handleAnalyzeText();
  }, []);

  const loadSummary = async () => {
    try {
      const res = await apiClient.get('/api/ai/entities-summary');
      setSummary(res.data);
    } catch (e) {
      console.error(e);
    }
  };

  const handleRAGSearch = async (e) => {
    if (e) e.preventDefault();
    setRagLoading(true);
    try {
      const res = await apiClient.post('/api/ai/rag-query', { query: ragQuery });
      setRagResult(res.data);
    } catch (err) {
      alert('RAG Query failed: ' + (err.response?.data?.detail || err.message));
    } finally {
      setRagLoading(false);
    }
  };

  const handleAnalyzeText = async () => {
    setAnalyzing(true);
    try {
      const res = await apiClient.post('/api/ai/analyze-text', { text: sampleText });
      setAnalysisResult(res.data);
    } catch (err) {
      console.error(err);
    } finally {
      setAnalyzing(false);
    }
  };

  const handleRunLangGraph = async () => {
    setPipelineLoading(true);
    setPipelineResult(null);
    try {
      const res = await apiClient.post('/api/ai/run-pipeline');
      setPipelineResult(res.data);
      loadSummary();
    } catch (err) {
      alert('LangGraph pipeline failed: ' + (err.response?.data?.detail || err.message));
    } finally {
      setPipelineLoading(false);
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Title Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold uppercase tracking-wider text-slate-100 flex items-center gap-2">
            <Bot className="w-6 h-6 text-cyan-400" />
            <span>AI Intelligence Analyst & RAG Engine</span>
          </h2>
          <p className="text-xs text-slate-400 font-mono mt-1">
            spaCy NER &bull; Regional Punjab Slang Lexicon &bull; ChromaDB Vector RAG &bull; LangGraph Autonomous Pipeline
          </p>
        </div>

        <button
          onClick={handleRunLangGraph}
          disabled={pipelineLoading}
          className="bg-cyan-500 hover:bg-cyan-400 text-black font-bold py-2.5 px-4 rounded-lg text-xs font-mono flex items-center gap-2 transition-all glow-cyan"
        >
          {pipelineLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4 fill-current" />}
          <span>Execute LangGraph Batch Pipeline</span>
        </button>
      </div>

      {pipelineResult && (
        <div className="glass-card p-4 rounded-xl border border-emerald-500/40 bg-emerald-500/10 text-xs font-mono flex items-center justify-between">
          <div className="flex items-center gap-2 text-emerald-400">
            <CheckCircle2 className="w-4 h-4" />
            <span>Autonomous Pipeline Complete: Processed {pipelineResult.processed_records} records &bull; {pipelineResult.severe_alerts_count} severe threats flagged</span>
          </div>
          <span className="text-slate-300">Neo4j Graph Updated</span>
        </div>
      )}

      {/* RAG Investigative Search Section */}
      <div className="glass-card rounded-xl p-5 border border-[#1c2d52] space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold uppercase text-slate-200 font-mono flex items-center gap-2">
            <Search className="w-4 h-4 text-cyan-400" />
            <span>Investigative RAG Query Engine</span>
          </h3>
          <span className="text-[11px] font-mono text-cyan-400">ChromaDB Vector Retrieval</span>
        </div>

        <form onSubmit={handleRAGSearch} className="space-y-3">
          <div className="relative">
            <input
              type="text"
              required
              value={ragQuery}
              onChange={(e) => setRagQuery(e.target.value)}
              placeholder="Ask an investigative question across all scraped sources..."
              className="w-full bg-[#070b14] border border-[#1c2d52] rounded-lg px-4 py-3 text-xs text-slate-100 font-mono outline-none focus:border-cyan-500 pr-28"
            />
            <button
              type="submit"
              disabled={ragLoading}
              className="absolute right-2 top-2 bg-cyan-500 hover:bg-cyan-400 text-black font-bold px-3 py-1.5 rounded text-xs font-mono flex items-center gap-1.5"
            >
              {ragLoading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />}
              <span>Query RAG</span>
            </button>
          </div>

          {/* Quick Prompt Chips */}
          <div className="flex flex-wrap items-center gap-2 text-[11px] font-mono text-slate-400">
            <span>Quick Queries:</span>
            {[
              "Heroin supply along Amritsar-Majitha border",
              "Tramadol bulk courier delivery channels",
              "Precursor chemical acetic anhydride distributors"
            ].map((q, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => { setRagQuery(q); }}
                className="px-2 py-0.5 rounded bg-[#14203b] hover:bg-[#1c2d52] text-slate-300 border border-[#1c2d52] text-[10px]"
              >
                {q}
              </button>
            ))}
          </div>
        </form>

        {/* RAG Synthesis Result */}
        {ragResult && (
          <div className="mt-4 p-4 rounded-xl bg-[#070b14]/70 border border-cyan-500/30 space-y-3 font-mono text-xs">
            <div className="text-cyan-400 font-bold flex items-center gap-2">
              <Bot className="w-4 h-4" />
              <span>AI Synthesized Intelligence Assessment</span>
            </div>

            <div className="text-slate-200 whitespace-pre-line leading-relaxed">
              {ragResult.answer}
            </div>

            {/* Cited Sources */}
            {ragResult.sources && ragResult.sources.length > 0 && (
              <div className="mt-3 pt-3 border-t border-[#1c2d52]">
                <div className="text-[10px] text-slate-400 uppercase mb-2">Cross-Referenced Intercepts:</div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {ragResult.sources.map((src, i) => (
                    <div key={i} className="p-2 rounded bg-[#0d1527] border border-[#1c2d52] flex items-center justify-between text-[11px]">
                      <span className="text-cyan-400 truncate max-w-xs">{src.url}</span>
                      <span className="px-1.5 py-0.5 rounded bg-[#14203b] text-slate-400 text-[9px]">{src.source_type}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Interactive Slang & Entity Playground */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Input box */}
        <div className="glass-card rounded-xl p-5 border border-[#1c2d52] space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold uppercase text-slate-200 font-mono flex items-center gap-2">
              <Cpu className="w-4 h-4 text-cyan-400" />
              <span>Regional Slang & Threat Analyzer</span>
            </h3>
            <button
              onClick={handleAnalyzeText}
              disabled={analyzing}
              className="px-2.5 py-1 rounded bg-cyan-500/20 text-cyan-300 hover:bg-cyan-500/30 border border-cyan-500/40 text-[11px] font-mono flex items-center gap-1"
            >
              {analyzing ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3 fill-current" />}
              <span>Analyze</span>
            </button>
          </div>

          <p className="text-[11px] text-slate-400 font-mono">
            Test spaCy NER extraction on intercepted chats with regional terms like <em>Chitta, Bhukki, Smack, Tramadol</em>.
          </p>

          <textarea
            rows={5}
            value={sampleText}
            onChange={(e) => setSampleText(e.target.value)}
            className="w-full bg-[#070b14] border border-[#1c2d52] rounded-lg p-3 text-xs text-slate-100 font-mono outline-none focus:border-cyan-500"
          />

          {/* Extracted Entity Tags */}
          {analysisResult && (
            <div className="space-y-3 pt-2">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono uppercase text-slate-400">Assessed Threat Level:</span>
                <span className={`px-2 py-0.5 rounded text-xs font-bold font-mono ${
                  analysisResult.threat_assessment.threat_level === 'SEVERE' ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30' :
                  analysisResult.threat_assessment.threat_level === 'HIGH' ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30' :
                  'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                }`}>
                  {analysisResult.threat_assessment.threat_level} (Score: {analysisResult.threat_assessment.risk_score}/100)
                </span>
              </div>

              {/* Entity Badges */}
              <div className="flex flex-wrap gap-1.5 text-[11px] font-mono">
                {analysisResult.entities.drugs?.map((d, i) => (
                  <span key={i} className="px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30 flex items-center gap-1">
                    <Tag className="w-3 h-3" /> {d}
                  </span>
                ))}
                {analysisResult.entities.locations?.map((l, i) => (
                  <span key={i} className="px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 flex items-center gap-1">
                    <MapPin className="w-3 h-3" /> {l}
                  </span>
                ))}
                {analysisResult.entities.phones?.map((p, i) => (
                  <span key={i} className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 flex items-center gap-1">
                    <Phone className="w-3 h-3" /> {p}
                  </span>
                ))}
                {analysisResult.entities.crypto_wallets?.btc?.map((w, i) => (
                  <span key={i} className="px-2 py-0.5 rounded bg-purple-500/10 text-purple-400 border border-purple-500/30 flex items-center gap-1 truncate max-w-xs">
                    <Coins className="w-3 h-3" /> {w}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Aggregated Intelligence Breakdown */}
        <div className="glass-card rounded-xl p-5 border border-[#1c2d52] space-y-4">
          <h3 className="text-sm font-bold uppercase text-slate-200 font-mono">
            State-Wide Intelligence Hotspots
          </h3>

          <div className="space-y-3">
            <div>
              <div className="text-[11px] font-mono text-slate-400 uppercase mb-1.5">Prevalent Illicit Substances</div>
              <div className="space-y-1">
                {summary && Object.entries(summary.top_drugs).map(([drug, count]) => (
                  <div key={drug} className="flex items-center justify-between text-xs font-mono p-2 rounded bg-[#070b14] border border-[#1c2d52]">
                    <span className="text-amber-400">{drug}</span>
                    <span className="text-slate-400">{count} intercepts</span>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <div className="text-[11px] font-mono text-slate-400 uppercase mb-1.5">High-Activity Punjab Districts</div>
              <div className="space-y-1">
                {summary && Object.entries(summary.top_locations).map(([loc, count]) => (
                  <div key={loc} className="flex items-center justify-between text-xs font-mono p-2 rounded bg-[#070b14] border border-[#1c2d52]">
                    <span className="text-cyan-400">{loc}</span>
                    <span className="text-slate-400">{count} occurrences</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
