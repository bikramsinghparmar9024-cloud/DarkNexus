import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import {
  Database, Shield, ShieldCheck, ShieldAlert, Lock, Eye, Search,
  Hash, Clock, ExternalLink, FileText, AlertTriangle, CheckCircle2,
  XCircle, RefreshCw, Fingerprint, Layers, ChevronRight, Copy, 
  Archive, FileSearch, Cpu, Upload, Camera, MapPin, Loader2
} from 'lucide-react';
// ─── Source type styles ──────────────────────────────────────────
const SOURCE_BADGE = {
  DARK_WEB: { bg: 'bg-purple-500/10', text: 'text-purple-400', border: 'border-purple-500/30' },
  TELEGRAM: { bg: 'bg-blue-500/10', text: 'text-blue-400', border: 'border-blue-500/30' },
  SURFACE_WEB: { bg: 'bg-emerald-500/10', text: 'text-emerald-400', border: 'border-emerald-500/30' },
};

const STATE_BADGE = {
  LEAD: { bg: 'bg-amber-500/15', text: 'text-amber-300', border: 'border-amber-500/40', label: 'LEAD' },
  CORROBORATED: { bg: 'bg-cyan-500/15', text: 'text-cyan-300', border: 'border-cyan-500/40', label: 'CORROBORATED' },
  VERIFIED: { bg: 'bg-emerald-500/15', text: 'text-emerald-300', border: 'border-emerald-500/40', label: 'VERIFIED' },
  REJECTED: { bg: 'bg-rose-500/15', text: 'text-rose-300', border: 'border-rose-500/40', label: 'REJECTED' },
};

const getSourceBadge = (type) => SOURCE_BADGE[type] || SOURCE_BADGE.SURFACE_WEB;
const getStateBadge = (state) => STATE_BADGE[state] || STATE_BADGE.LEAD;

export const EvidenceVault = () => {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isOffline, setIsOffline] = useState(false);
  const [selectedRecord, setSelectedRecord] = useState(null);
  const [recordDetail, setRecordDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [integrityResult, setIntegrityResult] = useState(null);
  const [verifying, setVerifying] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterState, setFilterState] = useState('ALL');
  const [copiedHash, setCopiedHash] = useState(false);

  // Manual image submission. Photographs seized from a handset are often the
  // only intelligence in a case that was never posted anywhere, so there has
  // to be a way in that is not a crawler.
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const [uploadError, setUploadError] = useState(null);
  const [caseRef, setCaseRef] = useState('');

  const submitImage = async (fileList) => {
    const file = fileList && fileList[0];
    if (!file) return;

    setUploading(true);
    setUploadError(null);
    setUploadResult(null);
    try {
      const form = new FormData();
      form.append('file', file);
      if (caseRef.trim()) form.append('case_reference', caseRef.trim());

      const res = await apiClient.post('/api/media/upload', form);
      setUploadResult(res.data);
      fetchRecords();
    } catch (err) {
      setUploadError(
        err.response?.data?.detail || 'Could not analyse this image.');
    } finally {
      setUploading(false);
    }
  };

  // ─── Fetch vault records ───────────────────────────────────────
  useEffect(() => {
    fetchRecords();
  }, []);

  const fetchRecords = async () => {
    setLoading(true);
    try {
      const res = await apiClient.get('/api/vault/browse/all', { timeout: 3000 });
      setRecords(res.data.records || []);
      setIsOffline(false);
    } catch (e) {
      console.error('EvidenceVault: failed to fetch records:', e.message);
      setRecords([]);
    } finally {
      setLoading(false);
    }
  };

  // ─── Fetch single record detail ────────────────────────────────
  const fetchRecordDetail = async (recordId) => {
    setDetailLoading(true);
    setIntegrityResult(null);
    try {
      const res = await apiClient.get(`/api/vault/${recordId}`, { timeout: 3000 });
      setRecordDetail(res.data.vault_record);
    } catch (e) {
      setRecordDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  // ─── Verify integrity ─────────────────────────────────────────
  const handleVerifyIntegrity = async (recordId) => {
    setVerifying(true);
    try {
      const res = await apiClient.get(`/api/vault/${recordId}/verify-integrity`, { timeout: 3000 });
      setIntegrityResult(res.data);
    } catch (e) {
      console.error('Integrity verification failed:', e.message);
      setIntegrityResult(null);
    } finally {
      setVerifying(false);
    }
  };

  const handleSelectRecord = (record) => {
    setSelectedRecord(record);
    fetchRecordDetail(record.id);
  };

  const copyHash = (hash) => {
    navigator.clipboard.writeText(hash);
    setCopiedHash(true);
    setTimeout(() => setCopiedHash(false), 2000);
  };

  // ─── Filters ───────────────────────────────────────────────────
  const filteredRecords = records.filter(r => {
    const matchesSearch = !searchQuery ||
      r.snippet?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.author?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.source_url?.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesState = filterState === 'ALL' || r.intelligence_state === filterState;
    return matchesSearch && matchesState;
  });

  if (loading) {
    return (
      <div className="p-6 space-y-6 max-w-7xl mx-auto">
        <div className="glass-card rounded-xl p-5 border-l-4 border-purple-500">
          <div className="skeleton h-6 w-64 mb-2" />
          <div className="skeleton h-3 w-96" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="glass-card rounded-xl p-5 space-y-3">
              <div className="skeleton h-3 w-24" />
              <div className="skeleton h-5 w-full" />
              <div className="skeleton h-3 w-48" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* ─── Header ─────────────────────────────────────────────── */}
      <div className="glass-card rounded-xl p-5 border-l-4 border-purple-500 animate-fade-in-up">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
              <Database className="w-5 h-5 text-purple-400" />
              Evidence Vault — Read-Only Repository
            </h2>
            <p className="text-xs text-slate-400 mt-1 font-mono">
              Immutable Evidence Artifacts • SHA-256 Chain of Custody • Section 65B IEA Compliant • AI Analysis Layer (Separate)
            </p>
          </div>
          <div className="flex items-center gap-3">
            {isOffline && (
              <span className="text-[9px] font-mono px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30">DEMO</span>
            )}
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-purple-500/10 border border-purple-500/30">
              <Lock className="w-3.5 h-3.5 text-purple-400" />
              <span className="text-[10px] font-mono text-purple-300 font-bold">READ-ONLY</span>
            </div>
          </div>
        </div>
      </div>


      {/* ─── Submit an image for forensic extraction ────────────── */}
      <div className="glass-card rounded-xl p-5 border border-[#1c2d52]">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <Camera className="w-4 h-4 text-cyan-400" />
              Submit image evidence
            </h3>
            <p className="text-[11px] text-slate-400 mt-1 font-mono">
              SHA-256 over the original bytes · EXIF · camera signature · GPS resolved
              to a district and distance to border · OCR of text in the frame
            </p>
          </div>

          <div className="flex items-center gap-2">
            <input
              type="text"
              value={caseRef}
              onChange={(e) => setCaseRef(e.target.value)}
              placeholder="Case / FIR reference (optional)"
              className="bg-[#070b14] border border-[#1c2d52] rounded-lg px-3 py-2 text-xs text-slate-100 font-mono outline-none focus:border-cyan-500 w-56"
            />
            <label className={`btn btn-primary text-xs ${uploading ? 'opacity-60' : ''}`}>
              {uploading
                ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                : <Upload className="w-3.5 h-3.5" />}
              <span>{uploading ? 'Analysing…' : 'Choose image'}</span>
              <input
                type="file"
                accept="image/*"
                disabled={uploading}
                onChange={(e) => { submitImage(e.target.files); e.target.value = ''; }}
                className="hidden"
              />
            </label>
          </div>
        </div>

        {uploadError && (
          <div className="mt-3 p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-[11px] font-mono text-rose-300">
            {uploadError}
          </div>
        )}

        {uploadResult && (
          <div className="mt-4 space-y-3">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-[11px] font-mono">
              <div className="p-2.5 rounded-lg bg-[#070b14] border border-[#162547]">
                <div className="text-slate-500">Camera</div>
                <div className="text-slate-200">
                  {uploadResult.forensics.device_signature || '—'}
                </div>
              </div>
              <div className="p-2.5 rounded-lg bg-[#070b14] border border-[#162547]">
                <div className="text-slate-500">Taken</div>
                <div className="text-slate-200">
                  {uploadResult.forensics.capture_timestamp || '—'}
                </div>
              </div>
              <div className="p-2.5 rounded-lg bg-[#070b14] border border-[#162547]">
                <div className="text-slate-500">Location</div>
                <div className={uploadResult.forensics.in_border_corridor
                  ? 'text-rose-300 font-bold' : 'text-slate-200'}>
                  {uploadResult.forensics.location || '—'}
                  {uploadResult.forensics.distance_to_border_km != null && (
                    <span className="text-slate-500">
                      {' '}· {uploadResult.forensics.distance_to_border_km} km to border
                    </span>
                  )}
                </div>
              </div>
              <div className="p-2.5 rounded-lg bg-[#070b14] border border-[#162547]">
                <div className="text-slate-500">Text found</div>
                {/* "none" would be a claim about the photograph. When the OCR
                    engine is missing, nothing was read at all - a different
                    statement, and the one an operator can act on. */}
                <div className={uploadResult.forensics.ocr_available === false
                  ? 'text-amber-400' : 'text-slate-200'}>
                  {uploadResult.forensics.ocr_available === false
                    ? 'OCR unavailable'
                    : (uploadResult.forensics.ocr_char_count
                        ? `${uploadResult.forensics.ocr_char_count} characters`
                        : 'none')}
                </div>
              </div>
            </div>

            {uploadResult.forensics.in_border_corridor && (
              <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-[11px] font-mono text-rose-300 flex items-center gap-2">
                <MapPin className="w-3.5 h-3.5" />
                GPS places this photograph inside the 15 km border corridor.
              </div>
            )}

            {uploadResult.forensics.ocr_text && (
              <div className="p-3 rounded-lg bg-[#070b14] border border-[#162547]">
                <div className="text-[10px] font-mono uppercase tracking-wider text-slate-500 mb-1">
                  Text read from the image
                </div>
                <p className="text-[11px] font-mono text-slate-300 whitespace-pre-wrap">
                  {uploadResult.forensics.ocr_text.slice(0, 600)}
                </p>
              </div>
            )}

            {/* What the file did NOT carry, said plainly. Blank fields alone
                would read as an extraction failure, when a stripped image is
                the normal case for anything forwarded through a chat app. */}
            {uploadResult.notes?.length > 0 && (
              <ul className="space-y-1">
                {uploadResult.notes.map((note, i) => (
                  <li key={i} className="text-[11px] font-mono text-slate-500">— {note}</li>
                ))}
              </ul>
            )}

            <div className="text-[10px] font-mono text-slate-500 break-all">
              record {uploadResult.record_id} · {uploadResult.filename} ·
              {' '}{uploadResult.size_bytes} bytes · sha256 {uploadResult.sha256}
            </div>
          </div>
        )}
      </div>

      {/* ─── Stats Row ──────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 stagger-children">
        {[
          { label: 'Total Artifacts', value: records.length, color: 'purple', icon: Archive },
          { label: 'Verified', value: records.filter(r => r.intelligence_state === 'VERIFIED').length, color: 'emerald', icon: ShieldCheck },
          { label: 'Corroborated', value: records.filter(r => r.intelligence_state === 'CORROBORATED').length, color: 'cyan', icon: Shield },
          { label: 'Pending Leads', value: records.filter(r => r.intelligence_state === 'LEAD').length, color: 'amber', icon: AlertTriangle },
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

      {/* ─── Search & Filter ────────────────────────────────────── */}
      <div className="flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search evidence by content, author, URL..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-[#0d1527] border border-[#1c2d52] text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-purple-500/50 font-mono"
          />
        </div>
        <div className="flex gap-1.5">
          {['ALL', 'LEAD', 'CORROBORATED', 'VERIFIED'].map(state => (
            <button
              key={state}
              onClick={() => setFilterState(state)}
              className={`px-3 py-2 rounded-xl text-[10px] font-mono font-bold border transition-all ${
                filterState === state
                  ? 'bg-purple-500/15 text-purple-300 border-purple-500/40'
                  : 'bg-[#14203b] text-slate-400 border-[#1c2d52] hover:text-slate-200'
              }`}
            >
              {state}
            </button>
          ))}
        </div>
      </div>

      {/* ─── Main Content ───────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">

        {/* ── Left: Record List ── */}
        <div className="lg:col-span-2 space-y-3 max-h-[700px] overflow-y-auto pr-1">
          {filteredRecords.map((record) => {
            const srcBadge = getSourceBadge(record.source_type);
            const stBadge = getStateBadge(record.intelligence_state);
            const isSelected = selectedRecord?.id === record.id;
            return (
              <div
                key={record.id}
                onClick={() => handleSelectRecord(record)}
                className={`glass-card rounded-xl p-4 border cursor-pointer transition-all ${
                  isSelected
                    ? 'border-purple-500/50 bg-purple-500/5 ring-1 ring-purple-500/30 shadow-[0_0_20px_rgba(168,85,247,0.1)]'
                    : 'border-[#1c2d52] hover:border-purple-500/30'
                }`}
              >
                <div className="flex items-center justify-between gap-2 mb-2">
                  <div className="flex items-center gap-2">
                    <span className={`text-[9px] font-mono font-bold px-2 py-0.5 rounded border ${srcBadge.bg} ${srcBadge.text} ${srcBadge.border}`}>
                      {record.source_type}
                    </span>
                    <span className={`text-[9px] font-mono font-bold px-2 py-0.5 rounded border ${stBadge.bg} ${stBadge.text} ${stBadge.border}`}>
                      {stBadge.label}
                    </span>
                  </div>
                  <span className={`text-[9px] font-mono font-bold px-2 py-0.5 rounded border ${
                    record.threat_level === 'SEVERE' ? 'bg-rose-500/20 text-rose-400 border-rose-500/30' :
                    record.threat_level === 'HIGH' ? 'bg-amber-500/20 text-amber-400 border-amber-500/30' :
                    'bg-yellow-500/20 text-yellow-300 border-yellow-500/30'
                  }`}>{record.threat_level}</span>
                </div>

                <p className="text-xs text-slate-300 leading-relaxed line-clamp-2 mb-2">{record.snippet}</p>

                <div className="flex items-center justify-between text-[9px] font-mono text-slate-500">
                  <span className="flex items-center gap-1">
                    <Hash className="w-2.5 h-2.5 text-purple-400" />
                    <span className="truncate max-w-[120px]">{record.sha256_hash?.slice(0, 16)}...</span>
                  </span>
                  <span className="flex items-center gap-1">
                    <Clock className="w-2.5 h-2.5" />
                    {record.acquisition_timestamp?.split('T')[0]}
                  </span>
                </div>

                <div className="text-[9px] font-mono text-slate-500 mt-1 flex items-center gap-1">
                  <ExternalLink className="w-2.5 h-2.5" />
                  <span className="truncate">{record.source_url}</span>
                </div>
              </div>
            );
          })}

          {filteredRecords.length === 0 && (
            <div className="p-8 text-center glass-card rounded-xl border border-[#1c2d52]">
              <Database className="w-8 h-8 text-slate-600 mx-auto mb-3" />
              <p className="text-xs text-slate-500 font-mono">No evidence records match your filters.</p>
            </div>
          )}
        </div>

        {/* ── Right: Record Detail ── */}
        <div className="lg:col-span-3 space-y-4">
          {detailLoading ? (
            <div className="glass-card rounded-xl p-8 border border-[#1c2d52] space-y-4">
              <div className="skeleton h-6 w-48" />
              <div className="skeleton h-4 w-full" />
              <div className="skeleton h-4 w-3/4" />
              <div className="skeleton h-32 w-full" />
            </div>
          ) : recordDetail ? (
            <div className="space-y-4 animate-fade-in-up">
              {/* Original Evidence Banner */}
              <div className="glass-card rounded-xl p-5 border border-purple-500/30 bg-gradient-to-r from-purple-950/20 to-[#0d1527] space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-purple-500/10 border border-purple-500/30 flex items-center justify-center">
                      <Lock className="w-5 h-5 text-purple-400" />
                    </div>
                    <div>
                      <h3 className="text-sm font-bold text-slate-100 uppercase tracking-wider">Original Evidence Artifact</h3>
                      <p className="text-[10px] text-slate-400 font-mono">Record #{recordDetail.id} • Immutable • Read-Only</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[9px] font-mono px-2 py-0.5 rounded bg-purple-500/15 text-purple-300 border border-purple-500/40 font-bold">
                      {recordDetail.immutable ? '🔒 IMMUTABLE' : 'MUTABLE'}
                    </span>
                  </div>
                </div>

                {/* Cleaned content */}
                <div>
                  <div className="text-[10px] uppercase font-mono text-slate-400 mb-1.5">Cleaned Text Extract</div>
                  <div className="p-3 rounded-lg bg-[#070b14] border border-[#162547] text-xs text-slate-200 font-mono leading-relaxed">
                    {recordDetail.cleaned_content}
                  </div>
                </div>

                {/* Raw content (collapsible) */}
                <details className="group">
                  <summary className="text-[10px] uppercase font-mono text-slate-500 cursor-pointer hover:text-slate-300 transition-colors flex items-center gap-1">
                    <ChevronRight className="w-3 h-3 group-open:rotate-90 transition-transform" />
                    View Raw Original Content
                  </summary>
                  <div className="mt-2 p-3 rounded-lg bg-[#070b14] border border-[#162547] text-[10px] text-slate-400 font-mono leading-relaxed overflow-x-auto max-h-40 overflow-y-auto">
                    {recordDetail.original_content}
                  </div>
                </details>
              </div>

              {/* Provenance Chain */}
              <div className="glass-card rounded-xl p-5 border border-[#1c2d52] space-y-3">
                <h4 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
                  <Layers className="w-4 h-4 text-cyan-400" />
                  Provenance & Chain of Custody
                </h4>
                <div className="grid grid-cols-2 gap-2 text-[10px] font-mono">
                  {[
                    { label: 'Source Type', value: recordDetail.provenance?.source_type, color: 'text-purple-400' },
                    { label: 'Acquisition Method', value: recordDetail.provenance?.acquisition_method, color: 'text-cyan-400' },
                    { label: 'Author / Handle', value: recordDetail.provenance?.author_or_handle, color: 'text-rose-400' },
                    { label: 'Collector', value: recordDetail.provenance?.collector_identity, color: 'text-emerald-400' },
                    { label: 'Source URL', value: recordDetail.provenance?.source_url, color: 'text-blue-400', span: true },
                    { label: 'Acquired At', value: recordDetail.provenance?.acquisition_timestamp, color: 'text-slate-300' },
                  ].map((item, i) => (
                    <div key={i} className={`p-2.5 rounded-lg bg-[#070b14] border border-[#162547] ${item.span ? 'col-span-2' : ''}`}>
                      <div className="text-slate-500 mb-0.5">{item.label}</div>
                      <div className={`${item.color} font-bold break-all`}>{item.value || 'N/A'}</div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Integrity & SHA-256 */}
              <div className="glass-card rounded-xl p-5 border border-[#1c2d52] space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
                    <Hash className="w-4 h-4 text-cyan-400" />
                    Cryptographic Integrity
                  </h4>
                  <button
                    onClick={() => handleVerifyIntegrity(recordDetail.id)}
                    disabled={verifying}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-[10px] font-mono font-bold hover:bg-emerald-500/20 transition-all disabled:opacity-50"
                  >
                    {verifying ? <RefreshCw className="w-3 h-3 animate-spin" /> : <ShieldCheck className="w-3 h-3" />}
                    Verify Integrity
                  </button>
                </div>

                <div className="p-3 rounded-lg bg-[#070b14] border border-[#162547] text-[10px] font-mono space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500">Algorithm:</span>
                    <span className="text-slate-300">{recordDetail.integrity?.hash_algorithm}</span>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-slate-500">SHA-256:</span>
                    <div className="flex items-center gap-1.5">
                      <span className="text-cyan-400 break-all text-[9px]">{recordDetail.integrity?.sha256_hash}</span>
                      <button
                        onClick={() => copyHash(recordDetail.integrity?.sha256_hash)}
                        className="p-1 rounded hover:bg-cyan-500/20 text-slate-400 hover:text-cyan-400 transition-colors flex-shrink-0"
                      >
                        {copiedHash ? <CheckCircle2 className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                      </button>
                    </div>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500">Computed At:</span>
                    <span className="text-slate-300">{recordDetail.integrity?.hash_computed_at}</span>
                  </div>
                </div>

                {/* Integrity verification result */}
                {integrityResult && (
                  <div className={`p-4 rounded-xl border animate-fade-in-up ${
                    integrityResult.integrity_verified
                      ? 'bg-emerald-500/10 border-emerald-500/30'
                      : 'bg-rose-500/10 border-rose-500/30'
                  }`}>
                    <div className="flex items-center gap-2 mb-2">
                      {integrityResult.integrity_verified ? (
                        <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                      ) : (
                        <XCircle className="w-5 h-5 text-rose-400" />
                      )}
                      <span className={`text-sm font-bold font-mono ${integrityResult.integrity_verified ? 'text-emerald-300' : 'text-rose-300'}`}>
                        {integrityResult.integrity_verified ? 'INTEGRITY CONFIRMED' : 'INTEGRITY FAILURE'}
                      </span>
                    </div>
                    <p className="text-[10px] font-mono text-slate-400 leading-relaxed">
                      {integrityResult.verdict}
                    </p>
                    <div className="mt-2 grid grid-cols-2 gap-2 text-[9px] font-mono">
                      <div className="p-2 rounded bg-[#070b14] border border-[#162547]">
                        <div className="text-slate-500">Stored Hash</div>
                        <div className="text-cyan-400 break-all">{integrityResult.stored_hash?.slice(0, 32)}...</div>
                      </div>
                      <div className="p-2 rounded bg-[#070b14] border border-[#162547]">
                        <div className="text-slate-500">Recomputed Hash</div>
                        <div className="text-cyan-400 break-all">{integrityResult.recomputed_hash?.slice(0, 32)}...</div>
                      </div>
                    </div>
                    <div className="text-[9px] font-mono text-slate-500 mt-2">
                      Verified at: {integrityResult.verification_timestamp}
                    </div>
                  </div>
                )}
              </div>

              {/* AI Analysis Layer (Separated) */}
              {recordDetail.ai_analysis_layer && (
                <div className="glass-card rounded-xl p-5 border border-amber-500/30 bg-amber-950/5 space-y-3">
                  <div className="flex items-center gap-2">
                    <Cpu className="w-4 h-4 text-amber-400" />
                    <h4 className="text-xs font-bold text-amber-300 uppercase tracking-wider">AI Analysis Layer</h4>
                    <span className="text-[8px] font-mono px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30">DERIVED — NOT ORIGINAL EVIDENCE</span>
                  </div>
                  <p className="text-[10px] text-amber-400/70 font-mono italic">
                    {recordDetail.ai_analysis_layer.note}
                  </p>
                  <div className="space-y-2 text-[10px] font-mono">
                    {recordDetail.ai_analysis_layer.threat_classification && (
                      <div className="p-2 rounded bg-[#070b14] border border-[#162547]">
                        <span className="text-slate-500">Threat Classification: </span>
                        <span className="text-rose-400 font-bold">{recordDetail.ai_analysis_layer.threat_classification}</span>
                      </div>
                    )}
                    {recordDetail.ai_analysis_layer.geo_resolution && (
                      <div className="p-2 rounded bg-[#070b14] border border-[#162547]">
                        <span className="text-slate-500">Geo Resolution: </span>
                        <span className="text-cyan-400">{recordDetail.ai_analysis_layer.geo_resolution}</span>
                      </div>
                    )}
                    {recordDetail.ai_analysis_layer.extracted_entities && (
                      <div>
                        <div className="text-slate-500 mb-1">Extracted Entities:</div>
                        <div className="flex flex-wrap gap-1">
                          {recordDetail.ai_analysis_layer.extracted_entities.map((ent, i) => (
                            <span key={i} className="px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 text-[9px]">{ent}</span>
                          ))}
                        </div>
                      </div>
                    )}
                    {recordDetail.ai_analysis_layer.detected_slang && (
                      <div>
                        <div className="text-slate-500 mb-1">Detected Slang Translations:</div>
                        <div className="flex flex-wrap gap-1">
                          {recordDetail.ai_analysis_layer.detected_slang.map((s, i) => (
                            <span key={i} className="px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20 text-[9px]">{s}</span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="glass-card rounded-xl p-12 border border-[#1c2d52] text-center space-y-3">
              <Database className="w-10 h-10 text-slate-600 mx-auto" />
              <h4 className="text-sm font-bold text-slate-400 uppercase font-mono">Select an Evidence Record</h4>
              <p className="text-xs text-slate-500 font-mono max-w-sm mx-auto">
                Click any evidence artifact from the list to view original content, provenance chain, integrity verification, and AI analysis.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
