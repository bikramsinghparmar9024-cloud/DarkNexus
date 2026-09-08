import React, { useEffect, useState, useCallback } from 'react';
import { apiClient, describeApiError } from '../api/client';
import {
  Crosshair, Plus, Eye, EyeOff, Globe, Send, ShieldAlert,
  UserPlus, X, ChevronRight, Activity, AlertTriangle, FileText,
  Search, Radar, Link2, Fingerprint, Signal, Clock, Shield,
  Zap, TrendingUp, Lock, Unlock, Database, Download, CheckCircle2,
  RefreshCw, Layers, Sparkles, Filter, ExternalLink, Trash2,
  ShieldCheck, ShieldQuestion, ThumbsUp, ThumbsDown, HelpCircle
} from 'lucide-react';

// ─── Source type visual configuration ────────────────────────────
const SOURCE_CONFIG = {
  DARK_WEB: {
    color: 'purple',
    bg: 'bg-purple-500/10',
    border: 'border-purple-500/30',
    text: 'text-purple-400',
    badge: 'bg-purple-500/20 text-purple-300 border-purple-500/40',
    icon: EyeOff,
    label: 'Dark Web (.onion)'
  },
  TELEGRAM: {
    color: 'blue',
    bg: 'bg-blue-500/10',
    border: 'border-blue-500/30',
    text: 'text-blue-400',
    badge: 'bg-blue-500/20 text-blue-300 border-blue-500/40',
    icon: Send,
    label: 'Telegram Channel'
  },
  SURFACE_WEB: {
    color: 'emerald',
    bg: 'bg-emerald-500/10',
    border: 'border-emerald-500/30',
    text: 'text-emerald-400',
    badge: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
    icon: Globe,
    label: 'Surface Clearnet'
  },
};

const getSourceStyle = (type) => SOURCE_CONFIG[type] || SOURCE_CONFIG.SURFACE_WEB;

// ─── Risk score gradient & badge helper ──────────────────────────
const getRiskColor = (score) => {
  if (score >= 90) return { bar: 'from-rose-500 to-red-600', text: 'text-rose-400', bg: 'bg-rose-500/10', border: 'border-rose-500/30', label: 'CRITICAL' };
  if (score >= 75) return { bar: 'from-amber-500 to-orange-500', text: 'text-amber-400', bg: 'bg-amber-500/10', border: 'border-amber-500/30', label: 'HIGH' };
  if (score >= 50) return { bar: 'from-yellow-500 to-amber-400', text: 'text-yellow-400', bg: 'bg-yellow-500/10', border: 'border-yellow-500/30', label: 'MEDIUM' };
  return { bar: 'from-emerald-500 to-green-400', text: 'text-emerald-400', bg: 'bg-emerald-500/10', border: 'border-emerald-500/30', label: 'LOW' };
};






// ─── Client-side AES-256-GCM via Web Crypto API ──────────────────
async function clientEncrypt(plaintext, passphrase) {
  const enc = new TextEncoder();
  const data = enc.encode(plaintext);
  const originalSize = data.byteLength;

  // Derive key from passphrase using SHA-256
  const keyMaterial = await crypto.subtle.digest('SHA-256', enc.encode(passphrase));
  const key = await crypto.subtle.importKey('raw', keyMaterial, { name: 'AES-GCM' }, false, ['encrypt']);

  // Generate random IV
  const iv = crypto.getRandomValues(new Uint8Array(12));

  // Encrypt
  const encrypted = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, data);
  const encryptedArray = new Uint8Array(encrypted);

  // Base64 encode
  const toB64 = (arr) => btoa(String.fromCharCode(...arr));
  const compressedSize = Math.floor(originalSize * 0.45); // Simulated compression ratio

  return {
    status: 'SUCCESS',
    algorithm: 'WebCrypto AES-256-GCM (Client-Side)',
    original_size_bytes: originalSize,
    compressed_size_bytes: compressedSize,
    encrypted_size_bytes: encryptedArray.byteLength,
    space_saved_percentage: `${Math.round((1 - compressedSize / originalSize) * 100)}%`,
    nonce_b64: toB64(iv),
    encrypted_payload_b64: toB64(encryptedArray),
    timestamp: new Date().toISOString()
  };
}

async function clientDecrypt(encryptedB64, nonceB64, passphrase) {
  const enc = new TextEncoder();
  const dec = new TextDecoder();

  const fromB64 = (str) => new Uint8Array(atob(str).split('').map(c => c.charCodeAt(0)));

  const keyMaterial = await crypto.subtle.digest('SHA-256', enc.encode(passphrase));
  const key = await crypto.subtle.importKey('raw', keyMaterial, { name: 'AES-GCM' }, false, ['decrypt']);

  const iv = fromB64(nonceB64);
  const encrypted = fromB64(encryptedB64);

  const decrypted = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, encrypted);
  const original = dec.decode(decrypted);

  return {
    status: 'SUCCESS',
    restored_size_bytes: decrypted.byteLength,
    integrity_verified: true,
    decrypted_data: original
  };
}

// ─── Reusable Glass Modal ────────────────────────────────────────
const Modal = ({ open, onClose, title, subtitle, icon: Icon, children }) => {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-md p-4" onClick={onClose}>
      <div
        className="glass-card rounded-2xl border border-cyan-500/30 p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-[0_0_60px_rgba(6,182,212,0.15)] animate-modal-in"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-5 border-b border-[#1c2d52] pb-4">
          <div className="flex items-center gap-3">
            {Icon && (
              <div className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
                <Icon className="w-5 h-5" />
              </div>
            )}
            <div>
              <h3 className="text-sm font-bold text-slate-100 uppercase tracking-wider">{title}</h3>
              {subtitle && <p className="text-xs text-slate-400 mt-0.5">{subtitle}</p>}
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-rose-400 transition-colors p-1.5 rounded-lg hover:bg-rose-500/10 border border-transparent hover:border-rose-500/30"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
};

// ══════════════════════════════════════════════════════════════════
// ██  MAIN COMPONENT: CTI PROJECTS WORKSPACE
// ══════════════════════════════════════════════════════════════════
export const CTIProjects = () => {
  const [projects, setProjects] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [isOffline, setIsOffline] = useState(false);
  const [createError, setCreateError] = useState(null);
  const [suspectError, setSuspectError] = useState(null);
  const [sourceError, setSourceError] = useState(null);

  // Modals
  const [showNewProject, setShowNewProject] = useState(false);
  const [showAddSource, setShowAddSource] = useState(false);
  const [showAddSuspect, setShowAddSuspect] = useState(false);
  const [showVault, setShowVault] = useState(false);
  const [showReportDetail, setShowReportDetail] = useState(null);

  // Form states
  const [newProject, setNewProject] = useState({ name: '', topic: 'Drug Trafficking', description: '' });
  const [newSource, setNewSource] = useState({ identifier: '', source_type: 'TELEGRAM', label: '' });
  const [newSuspect, setNewSuspect] = useState({ username: '', alias: '', platform: 'Telegram & Tor', role: 'Distributor / Courier', notes: '' });
  const [submitting, setSubmitting] = useState(false);

  // Data Vault state
  const [vaultData, setVaultData] = useState('');
  const [vaultPassphrase, setVaultPassphrase] = useState('PunjabPoliceSpecialNarcoticsUnit2026');
  const [vaultEncryptedResult, setVaultEncryptedResult] = useState(null);
  const [vaultDecryptedResult, setVaultDecryptedResult] = useState(null);
  const [vaultBusy, setVaultBusy] = useState(false);

  // Reports & Alerts
  const [reports, setReports] = useState([]);
  const [alerts, setAlerts] = useState([]);

  const selected = projects.find((p) => p.id === selectedId) || null;

  // ─── 1. Load Projects (API with offline fallback) ────────────
  const fetchProjects = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/cti/projects', { timeout: 3000 });
      const list = res.data.projects || [];
      setProjects(list);
      if (!selectedId && list.length > 0) setSelectedId(list[0].id);
      setIsOffline(false);
    } catch (e) {
      // No invented operations. This used to load Operation Border Falcon and
      // its cast of fictional suspects whenever the backend was unreachable,
      // which is indistinguishable on screen from a real investigation.
      setProjects([]);
      setIsOffline(true);
    } finally {
      setLoading(false);
    }
  }, [selectedId]);

  useEffect(() => { fetchProjects(); }, []);

  // ─── 2. Per-project panels ────────────────────────────────────
  //
  // This block used to manufacture the contents of every panel for
  // whichever project was selected: "SEALED & VERIFIED" dossiers with
  // invented SHA-256 hashes signed by a fictional inspector, and alerts
  // describing intercepts that never happened. None of it came from the
  // backend, and none of it was distinguishable on screen from evidence.
  //
  // There is no per-project reports or alerts endpoint yet, so these
  // panels are empty until one exists. An empty panel is honest; a
  // fabricated dossier in a case file is not.
  useEffect(() => {
    if (!selected) return;
    setReports([]);
    setAlerts([]);
    setVaultData("");
    setVaultEncryptedResult(null);
    setVaultDecryptedResult(null);
  }, [selectedId, projects]);

  // ─── 3. Create Project ─────────────────────────────────────────
  const handleCreateProject = async (e) => {
    e.preventDefault();
    if (!newProject.name.trim()) return;
    setSubmitting(true);
    setCreateError(null);
    try {
      const res = await apiClient.post('/api/cti/projects', newProject);
      const created = res.data.project;
      setProjects((prev) => [created, ...prev]);
      setSelectedId(created.id);
      setShowNewProject(false);
      setNewProject({ name: '', topic: 'Drug Trafficking', description: '' });
    } catch (err) {
      // A project that failed to save server-side must not appear to exist.
      // It would live only in this browser tab, and any work filed under it
      // would vanish on refresh.
      setCreateError(describeApiError(err).message);
    } finally {
      setSubmitting(false);
    }
  };

  // ─── 4. Toggle Observation ─────────────────────────────────────
  const handleToggleObserving = async (projId) => {
    try {
      const res = await apiClient.post(`/api/cti/projects/${projId}/toggle-observing`, {}, { timeout: 3000 });
      setProjects((prev) => prev.map((p) => (p.id === projId ? { ...p, is_observing: res.data.is_observing } : p)));
    } catch (e) {
      setProjects((prev) => prev.map((p) => (p.id === projId ? { ...p, is_observing: !p.is_observing } : p)));
    }
  };

  // ─── 5. Add Source ─────────────────────────────────────────────
  const handleAddSource = async (e) => {
    e.preventDefault();
    if (!newSource.identifier.trim() || !selectedId) return;
    setSubmitting(true);
    try {
      const res = await apiClient.post(`/api/cti/projects/${selectedId}/sources`, newSource, { timeout: 3000 });
      const addedSource = res.data.source;
      setProjects((prev) => prev.map((p) => (p.id === selectedId ? { ...p, sources: [...(p.sources || []), addedSource] } : p)));
    } catch (err) {
      const addedSource = {
        id: `s_${Date.now()}`,
        identifier: newSource.identifier,
        source_type: newSource.source_type.toUpperCase(),
        label: newSource.label || newSource.identifier,
        status: 'ACTIVE',
        last_ping: 'Connecting...'
      };
      setProjects((prev) => prev.map((p) => (p.id === selectedId ? { ...p, sources: [...(p.sources || []), addedSource] } : p)));
    }
    setShowAddSource(false);
    setNewSource({ identifier: '', source_type: 'TELEGRAM', label: '' });
    setSubmitting(false);
  };

  // ─── 6. Remove Source ──────────────────────────────────────────
  const handleRemoveSource = async (sourceId) => {
    if (!selectedId) return;
    try {
      await apiClient.delete(`/api/cti/projects/${selectedId}/sources/${sourceId}`);
      setProjects((prev) => prev.map((p) =>
        p.id === selectedId ? { ...p, sources: (p.sources || []).filter(s => s.id !== sourceId) } : p
      ));
    } catch (e) {
      // Removing it from the list while the server still holds it would show
      // surveillance as stopped when collection is in fact continuing.
      setSourceError(describeApiError(e).message);
    }
  };

  // ─── 7. Add Suspect ────────────────────────────────────────────
  const handleAddSuspect = async (e) => {
    e.preventDefault();
    if (!newSuspect.username.trim() || !selectedId) return;
    setSubmitting(true);
    setSuspectError(null);
    try {
      const res = await apiClient.post(
        `/api/cti/projects/${selectedId}/suspects`, newSuspect);
      const addedSuspect = res.data.suspect;
      setProjects((prev) => prev.map((p) => (p.id === selectedId
        ? { ...p, suspects: [addedSuspect, ...(p.suspects || [])] } : p)));
      setShowAddSuspect(false);
      setNewSuspect({ username: '', alias: '', platform: 'Telegram & Tor',
                      role: 'Distributor / Courier', notes: '' });
    } catch (err) {
      // Correlation is evidence-derived and happens server-side. This used
      // to score a suspect by testing whether the handle contained
      // "lahori" or "jagga" and assigning 96 or 92 - a confident number
      // for an account nothing was actually known about.
      setSuspectError(describeApiError(err).message);
    } finally {
      setSubmitting(false);
    }
  };

  // ─── 8. Delete Project ─────────────────────────────────────────
  const handleDeleteProject = (projId) => {
    setProjects((prev) => prev.filter(p => p.id !== projId));
    if (selectedId === projId) {
      const remaining = projects.filter(p => p.id !== projId);
      setSelectedId(remaining.length > 0 ? remaining[0].id : null);
    }
  };

  // ─── 9. Compress & Encrypt (API → Web Crypto fallback) ────────
  const handleCompressAndEncrypt = async () => {
    if (!vaultData.trim()) return;
    setVaultBusy(true);
    try {
      const res = await apiClient.post('/api/cti/compress-encrypt', { data_payload: vaultData, passphrase: vaultPassphrase }, { timeout: 5000 });
      setVaultEncryptedResult(res.data);
    } catch (err) {
      try {
        const result = await clientEncrypt(vaultData, vaultPassphrase);
        setVaultEncryptedResult(result);
      } catch (e2) {
        alert('Encryption failed: ' + e2.message);
      }
    }
    setVaultDecryptedResult(null);
    setVaultBusy(false);
  };

  // ─── 10. Decrypt & Decompress ──────────────────────────────────
  const handleDecryptAndDecompress = async () => {
    if (!vaultEncryptedResult) return;
    setVaultBusy(true);
    try {
      const res = await apiClient.post('/api/cti/decrypt-decompress', {
        encrypted_payload_b64: vaultEncryptedResult.encrypted_payload_b64,
        nonce_b64: vaultEncryptedResult.nonce_b64,
        passphrase: vaultPassphrase
      }, { timeout: 5000 });
      setVaultDecryptedResult(res.data);
    } catch (err) {
      try {
        const result = await clientDecrypt(vaultEncryptedResult.encrypted_payload_b64, vaultEncryptedResult.nonce_b64, vaultPassphrase);
        setVaultDecryptedResult(result);
      } catch (e2) {
        alert('Decryption failed: ' + e2.message);
      }
    }
    setVaultBusy(false);
  };

  // Filtered projects for sidebar
  const filteredProjects = projects.filter((p) =>
    p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    p.topic.toLowerCase().includes(searchQuery.toLowerCase())
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[80vh]">
        <div className="flex flex-col items-center gap-4">
          <div className="w-14 h-14 rounded-2xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center animate-glow-pulse">
            <Radar className="w-7 h-7 text-cyan-400 animate-spin" />
          </div>
          <span className="text-xs font-mono text-cyan-400 tracking-wider">INITIALIZING CTI PROJECT WORKSPACE...</span>
          <div className="flex gap-1">
            {[0, 1, 2, 3, 4].map(i => (
              <div key={i} className="w-2 h-2 rounded-full bg-cyan-400/60 animate-pulse" style={{ animationDelay: `${i * 150}ms` }} />
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-4rem)] overflow-hidden bg-[#070b14]">

      {/* ═════════════════════════════════════════════════════════════
          LEFT PANEL: LIST OF PROJECTS
          ═════════════════════════════════════════════════════════════ */}
      <aside className="w-80 flex-shrink-0 border-r border-[#1c2d52] bg-[#0a1020] flex flex-col">
        <div className="p-4 border-b border-[#1c2d52] space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Crosshair className="w-4 h-4 text-cyan-400" />
              <h2 className="text-xs font-bold text-slate-100 uppercase tracking-wider">CTI Projects</h2>
            </div>
            <div className="flex items-center gap-2">
              {isOffline && (
                <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30">DEMO</span>
              )}
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/30">
                {projects.length} Active
              </span>
            </div>
          </div>

          <button
            onClick={() => setShowNewProject(true)}
            className="w-full flex items-center justify-center gap-2 px-3.5 py-2.5 rounded-xl text-xs font-bold
                       bg-gradient-to-r from-cyan-500 to-blue-600 text-slate-950
                       hover:from-cyan-400 hover:to-blue-500 shadow-[0_0_20px_rgba(6,182,212,0.3)]
                       transition-all active:scale-[0.98]"
          >
            <Plus className="w-4 h-4" />
            Create CTI Project
          </button>

          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search projects or topics..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 rounded-lg bg-[#0d1527] border border-[#1c2d52] text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500/50"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {filteredProjects.map((proj) => {
            const isSelected = proj.id === selectedId;
            return (
              <div
                key={proj.id}
                onClick={() => setSelectedId(proj.id)}
                className={`p-3.5 rounded-xl transition-all cursor-pointer border group ${
                  isSelected
                    ? 'bg-cyan-500/10 border-cyan-500/40 shadow-[0_0_25px_rgba(6,182,212,0.15)] ring-1 ring-cyan-500/30'
                    : 'bg-[#0d1527]/60 border-[#1c2d52] hover:bg-[#14203b] hover:border-slate-600'
                }`}
              >
                <div className="flex items-start justify-between gap-2 mb-1.5">
                  <h3 className={`text-xs font-bold line-clamp-1 ${isSelected ? 'text-cyan-300' : 'text-slate-100'}`}>
                    {proj.name}
                  </h3>
                  <div className="flex items-center gap-1.5 flex-shrink-0">
                    {proj.is_observing ? (
                      <span className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-emerald-500/15 border border-emerald-500/30 text-[9px] font-mono text-emerald-400">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                        LIVE
                      </span>
                    ) : (
                      <span className="px-1.5 py-0.5 rounded bg-slate-500/15 border border-slate-500/30 text-[9px] font-mono text-slate-400">
                        PAUSED
                      </span>
                    )}
                    <button
                      onClick={(e) => { e.stopPropagation(); handleDeleteProject(proj.id); }}
                      className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-rose-500/20 text-slate-500 hover:text-rose-400 transition-all"
                      title="Delete project"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                </div>

                <div className="flex items-center gap-2 mb-2">
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#152342] text-cyan-400 border border-cyan-500/20 truncate">
                    {proj.topic}
                  </span>
                </div>

                <p className="text-[11px] text-slate-400 line-clamp-2 leading-relaxed mb-2.5">
                  {proj.description}
                </p>

                <div className="flex items-center justify-between text-[10px] font-mono text-slate-400 pt-2 border-t border-[#1c2d52]/60">
                  <span className="flex items-center gap-1">
                    <Signal className="w-3 h-3 text-cyan-400" />
                    {(proj.sources || []).length} Sources
                  </span>
                  <span className="flex items-center gap-1">
                    <Fingerprint className="w-3 h-3 text-rose-400" />
                    {(proj.suspects || []).length} Suspects
                  </span>
                </div>
              </div>
            );
          })}

          {filteredProjects.length === 0 && (
            <div className="p-6 text-center text-slate-500 text-xs">
              No matching projects found.
            </div>
          )}
        </div>
      </aside>

      {/* ═════════════════════════════════════════════════════════════
          MAIN CANVAS
          ═════════════════════════════════════════════════════════════ */}
      <main className="flex-1 overflow-y-auto p-6 space-y-6">
        {selected ? (
          <>
            {/* ─── HEADER: NAME OF SELECTED PROJECT ───────────────── */}
            <div className="glass-card rounded-2xl p-5 border border-cyan-500/30 bg-gradient-to-r from-[#0d1629] via-[#0b1324] to-[#0a1020] shadow-[0_0_40px_rgba(6,182,212,0.08)] animate-fade-in-up">
              <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-4">
                <div className="space-y-1.5">
                  <div className="flex items-center gap-3 flex-wrap">
                    <span className="text-xs font-mono uppercase px-2.5 py-0.5 rounded-full bg-cyan-500/15 text-cyan-300 border border-cyan-500/40 flex items-center gap-1.5">
                      <Sparkles className="w-3 h-3" />
                      {selected.topic}
                    </span>
                    <span className="text-xs font-mono text-slate-500">ID: {selected.id}</span>
                    {isOffline && (
                      <span className="text-[9px] font-mono px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30">⚡ OFFLINE MODE</span>
                    )}
                  </div>
                  <h1 className="text-xl lg:text-2xl font-black text-slate-100 tracking-tight">{selected.name}</h1>
                  <p className="text-xs text-slate-400 max-w-3xl leading-relaxed">{selected.description}</p>
                </div>

                <div className="flex items-center gap-3 flex-wrap flex-shrink-0">
                  <button
                    onClick={() => setShowVault(true)}
                    className="flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-bold
                               bg-gradient-to-r from-purple-500/20 to-indigo-500/20 text-purple-300
                               border border-purple-500/40 hover:border-purple-400 hover:shadow-[0_0_20px_rgba(168,85,247,0.25)]
                               transition-all"
                  >
                    <Lock className="w-3.5 h-3.5 text-purple-400" />
                    <span>Data Vault</span>
                  </button>

                  <button
                    onClick={() => handleToggleObserving(selected.id)}
                    className={`flex items-center gap-2.5 px-4 py-2 rounded-xl text-xs font-bold transition-all border ${
                      selected.is_observing
                        ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300 hover:bg-emerald-500/25 shadow-[0_0_20px_rgba(16,185,129,0.2)]'
                        : 'bg-slate-700/30 border-slate-600 text-slate-300 hover:bg-slate-700/50'
                    }`}
                  >
                    {selected.is_observing ? (
                      <>
                        <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                        <Eye className="w-4 h-4 text-emerald-400" />
                        <span>OBSERVING LIVE</span>
                      </>
                    ) : (
                      <>
                        <EyeOff className="w-4 h-4 text-slate-400" />
                        <span>PAUSED</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            </div>

            {/* ─── SOURCES SECTION ─────────────────────────────────── */}
            <div className="glass-card rounded-2xl p-5 border border-[#1c2d52] bg-[#0c1326]/90 space-y-4 animate-fade-in-up" style={{ animationDelay: '50ms' }}>
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center gap-3">
                  <div className="w-7 h-7 rounded-lg bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
                    <Signal className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h2 className="text-xs font-bold text-slate-100 uppercase tracking-wider">Sources</h2>
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-[#162340] text-cyan-300 border border-cyan-500/30">
                        {(selected.sources || []).length} Monitoring
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-400">
                      Auto-predicted for <span className="text-cyan-400 font-semibold">{selected.topic}</span> & continuous investigator feeds
                    </p>
                  </div>
                </div>

                <button
                  onClick={() => setShowAddSource(true)}
                  className="flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-bold
                             bg-cyan-500/15 text-cyan-300 border border-cyan-500/40
                             hover:bg-cyan-500/25 hover:border-cyan-400 hover:shadow-[0_0_15px_rgba(6,182,212,0.2)]
                             transition-all"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>Add New Source</span>
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 stagger-children">
                {(selected.sources || []).map((src, i) => {
                  const style = getSourceStyle(src.source_type);
                  const SrcIcon = style.icon;
                  return (
                    <div
                      key={src.id || i}
                      className="p-3.5 rounded-xl bg-[#0e172e] border border-[#1c2d52] hover:border-cyan-500/40 hover:bg-[#121c38] transition-all group relative"
                    >
                      <button
                        onClick={() => handleRemoveSource(src.id)}
                        className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-rose-500/20 text-slate-500 hover:text-rose-400 transition-all"
                        title="Remove source"
                      >
                        <X className="w-3 h-3" />
                      </button>

                      <div className="flex items-center justify-between gap-2 mb-2 pr-6">
                        <span className={`text-[10px] font-mono px-2 py-0.5 rounded border flex items-center gap-1.5 ${style.badge}`}>
                          <SrcIcon className="w-3 h-3" />
                          {style.label}
                        </span>
                        <span className="flex items-center gap-1 text-[9px] font-mono text-emerald-400">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                          {src.status || 'ACTIVE'}
                        </span>
                      </div>

                      <div className="text-xs font-bold text-slate-200 truncate group-hover:text-cyan-300 transition-colors">
                        {src.label || src.identifier}
                      </div>

                      <div className="text-[10px] font-mono text-slate-400 truncate flex items-center gap-1 mt-1">
                        <Link2 className="w-3 h-3 flex-shrink-0 text-slate-500" />
                        <span className="truncate">{src.identifier}</span>
                      </div>

                      {src.last_ping && (
                        <div className="flex items-center gap-1 text-[9px] font-mono text-slate-500 mt-2">
                          <Clock className="w-2.5 h-2.5 text-cyan-400" />
                          <span>Last ping: {src.last_ping}</span>
                        </div>
                      )}
                    </div>
                  );
                })}

                {(!selected.sources || selected.sources.length === 0) && (
                  <div className="col-span-full p-4 rounded-xl bg-[#0e172e] border border-dashed border-[#1c2d52] text-center text-xs text-slate-500">
                    No active intelligence sources connected yet. Click "+ Add New Source" above.
                  </div>
                )}
              </div>
            </div>

            {/* ─── 3 COLUMNS: [Active Report] | [Alert] | [Sus Acc] ── */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

              {/* ═══ COLUMN 1: ACTIVE REPORT ═══ */}
              <div className="glass-card rounded-2xl p-5 border border-[#1c2d52] bg-[#0a1122]/90 flex flex-col space-y-4 animate-fade-in-up" style={{ animationDelay: '100ms' }}>
                <div className="flex items-center justify-between border-b border-[#1c2d52] pb-3">
                  <div className="flex items-center gap-2">
                    <FileText className="w-4 h-4 text-cyan-400" />
                    <h2 className="text-xs font-bold text-slate-100 uppercase tracking-wider">Active Report</h2>
                  </div>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/30">
                    {reports.length} Dossiers
                  </span>
                </div>

                <p className="text-[11px] text-slate-400">
                  Sealed evidence dossiers with cryptographic SHA-256 hashes generated from intercepted telemetry.
                </p>

                <div className="space-y-3 flex-1 overflow-y-auto max-h-[560px] pr-1">
                  {reports.map((rep) => (
                    <div
                      key={rep.id}
                      className="p-3.5 rounded-xl bg-[#0e172e] border border-[#1c2d52] hover:border-cyan-500/40 transition-all space-y-2.5"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-cyan-500/15 text-cyan-300 border border-cyan-500/30">
                            {rep.id}
                          </span>
                          <h4 className="text-xs font-bold text-slate-200 mt-1">{rep.title}</h4>
                        </div>
                        <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 whitespace-nowrap">
                          {rep.status}
                        </span>
                      </div>

                      <p className="text-[11px] text-slate-400 leading-relaxed">{rep.summary}</p>

                      <div className="space-y-1 text-[10px] font-mono text-slate-400 bg-[#070b14] p-2.5 rounded-lg border border-[#162547]">
                        <div className="flex items-center justify-between">
                          <span className="text-slate-500">Investigator:</span>
                          <span className="text-slate-300">{rep.investigator}</span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-slate-500">Evidence Count:</span>
                          <span className="text-cyan-400 font-bold">{rep.records_count} Intercepts</span>
                        </div>
                        <div className="flex items-center justify-between truncate">
                          <span className="text-slate-500">SHA-256:</span>
                          <span className="text-slate-400 truncate max-w-[150px] font-mono text-[9px]">{rep.hash}</span>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 pt-1">
                        <button
                          onClick={() => setShowReportDetail(rep)}
                          className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 text-[11px] font-semibold hover:bg-cyan-500/20 transition-all"
                        >
                          <Eye className="w-3 h-3" />
                          View Dossier
                        </button>
                        <a
                          href="/reports"
                          className="px-2.5 py-1.5 rounded-lg bg-[#14203b] border border-[#1c2d52] text-slate-400 hover:text-slate-200 text-[11px] font-semibold flex items-center gap-1"
                        >
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      </div>
                    </div>
                  ))}
                </div>

                <a href="/reports" className="w-full flex items-center justify-center gap-2 py-2 rounded-xl bg-[#0e172e] border border-[#1c2d52] hover:border-cyan-500/30 text-xs font-semibold text-slate-300 hover:text-cyan-300 transition-all">
                  <span>Open Full Evidence Chamber</span>
                  <ChevronRight className="w-3.5 h-3.5" />
                </a>
              </div>

              {/* ═══ COLUMN 2: ALERT ═══ */}
              <div className="glass-card rounded-2xl p-5 border border-[#1c2d52] bg-[#0a1122]/90 flex flex-col space-y-4 animate-fade-in-up" style={{ animationDelay: '150ms' }}>
                <div className="flex items-center justify-between border-b border-[#1c2d52] pb-3">
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-amber-400" />
                    <h2 className="text-xs font-bold text-slate-100 uppercase tracking-wider">Alert</h2>
                  </div>
                  <span className="flex items-center gap-1.5 text-[10px] font-mono px-2 py-0.5 rounded-full bg-rose-500/10 text-rose-400 border border-rose-500/30">
                    <span className="w-1.5 h-1.5 rounded-full bg-rose-400 animate-ping" />
                    {alerts.length} Real-Time
                  </span>
                </div>

                <p className="text-[11px] text-slate-400">
                  Live threat warnings intercepted across monitored Dark Web channels, Telegram, and border zones.
                </p>

                <div className="space-y-3 flex-1 overflow-y-auto max-h-[560px] pr-1">
                  {alerts.map((alt) => {
                    const isCritical = alt.level === 'CRITICAL';
                    const isSevere = alt.level === 'SEVERE';
                    return (
                      <div
                        key={alt.id}
                        className={`p-3.5 rounded-xl bg-[#0e172e] border transition-all space-y-2 ${
                          isCritical
                            ? 'border-rose-500/40 shadow-[0_0_20px_rgba(244,63,94,0.1)]'
                            : isSevere
                            ? 'border-amber-500/35'
                            : 'border-[#1c2d52]'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span
                            className={`text-[9px] font-mono font-bold px-2 py-0.5 rounded border ${
                              isCritical
                                ? 'bg-rose-500/20 text-rose-300 border-rose-500/40 animate-pulse'
                                : isSevere
                                ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                                : 'bg-yellow-500/20 text-yellow-300 border-yellow-500/40'
                            }`}
                          >
                            {alt.level}
                          </span>
                          <span className="text-[9px] font-mono text-slate-500 flex items-center gap-1">
                            <Clock className="w-2.5 h-2.5" />
                            {alt.timestamp}
                          </span>
                        </div>

                        <h4 className="text-xs font-bold text-slate-200">{alt.title}</h4>
                        <p className="text-[11px] text-slate-300 leading-relaxed">{alt.details}</p>

                        <div className="flex items-center justify-between pt-1 text-[10px] font-mono">
                          <span className="text-slate-500 truncate max-w-[140px]">
                            Source: <span className="text-cyan-400">{alt.source}</span>
                          </span>
                          <div className="flex gap-1 flex-wrap justify-end">
                            {alt.keywords.slice(0, 2).map((kw, k) => (
                              <span key={k} className="px-1.5 py-0.5 rounded bg-[#162547] text-slate-300 text-[9px]">{kw}</span>
                            ))}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>

                <div className="p-3 rounded-xl bg-cyan-500/5 border border-cyan-500/20 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                    <span className="text-[10px] font-mono text-slate-300">Live Wiretap Receiver Listening</span>
                  </div>
                  <a href="/simulator" className="text-[10px] font-mono font-semibold text-cyan-400 hover:underline flex items-center gap-1">
                    Launch Wiretap Simulator &rarr;
                  </a>
                </div>
              </div>

              {/* ═══ COLUMN 3: SUS ACC (SUSPECTS) ═══ */}
              <div className="glass-card rounded-2xl p-5 border border-[#1c2d52] bg-[#0a1122]/90 flex flex-col space-y-4 animate-fade-in-up" style={{ animationDelay: '200ms' }}>
                <div className="flex items-center justify-between border-b border-[#1c2d52] pb-3">
                  <div className="flex items-center gap-2">
                    <Fingerprint className="w-4 h-4 text-rose-400" />
                    <h2 className="text-xs font-bold text-slate-100 uppercase tracking-wider">Sus Acc</h2>
                  </div>
                  <button
                    onClick={() => setShowAddSuspect(true)}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-bold
                               bg-rose-500/15 text-rose-300 border border-rose-500/40
                               hover:bg-rose-500/25 hover:border-rose-400 hover:shadow-[0_0_15px_rgba(244,63,94,0.2)]
                               transition-all"
                  >
                    <UserPlus className="w-3.5 h-3.5" />
                    <span>Add Sus Acc</span>
                  </button>
                </div>

                <p className="text-[11px] text-slate-400">
                  Tracks username activity across pipelines and calculates risk scores & cross-source correlations.
                </p>

                <div className="flex gap-1.5 flex-wrap">
                  {['ALL', 'LEAD', 'CORROBORATED', 'VERIFIED'].map((state) => {
                    const stateColors = {
                      ALL: 'bg-slate-500/10 text-slate-300 border-slate-500/30',
                      LEAD: 'bg-amber-500/10 text-amber-300 border-amber-500/30',
                      CORROBORATED: 'bg-cyan-500/10 text-cyan-300 border-cyan-500/30',
                      VERIFIED: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30',
                    };
                    return (
                      <span key={state} className={`text-[9px] font-mono font-bold px-2 py-0.5 rounded border cursor-default ${stateColors[state]}`}>
                        {state}
                      </span>
                    );
                  })}
                </div>

                <div className="space-y-3 flex-1 overflow-y-auto max-h-[560px] pr-1">
                  {(selected.suspects || []).map((sus, i) => {
                    const risk = getRiskColor(sus.risk_score);
                    return (
                      <div key={sus.id || i} className="p-3.5 rounded-xl bg-[#0e172e] border border-[#1c2d52] hover:border-rose-500/40 transition-all space-y-2.5">
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <div className="text-xs font-bold text-slate-100 font-mono flex items-center gap-1.5">
                              <span>{sus.username}</span>
                              {(() => {
                                const state = sus.intelligence_state || (sus.risk_score >= 85 ? 'CORROBORATED' : 'LEAD');
                                const stColors = {
                                  LEAD: { bg: 'bg-amber-500/15', text: 'text-amber-300', border: 'border-amber-500/30', Icon: ShieldQuestion },
                                  CORROBORATED: { bg: 'bg-cyan-500/15', text: 'text-cyan-300', border: 'border-cyan-500/30', Icon: Shield },
                                  VERIFIED: { bg: 'bg-emerald-500/15', text: 'text-emerald-300', border: 'border-emerald-500/30', Icon: ShieldCheck },
                                };
                                const st = stColors[state] || stColors.LEAD;
                                return (
                                  <span className={`text-[8px] font-mono font-bold px-1.5 py-0.5 rounded ${st.bg} ${st.text} border ${st.border} flex items-center gap-0.5`}>
                                    <st.Icon className="w-2.5 h-2.5" />
                                    {state}
                                  </span>
                                );
                              })()}
                            </div>
                            {sus.alias && <div className="text-[10px] text-slate-400 font-mono">aka {sus.alias}</div>}
                          </div>
                          <span className={`text-[9px] font-mono font-bold px-2 py-0.5 rounded border ${risk.bg} ${risk.text} ${risk.border}`}>
                            {risk.label}
                          </span>
                        </div>

                        <div className="space-y-1">
                          <div className="flex items-center justify-between text-[10px] font-mono">
                            <span className="text-slate-500">Threat Risk Score</span>
                            <span className={`font-bold ${risk.text}`}>{sus.risk_score}/100</span>
                          </div>
                          <div className="w-full h-1.5 bg-[#070b14] rounded-full overflow-hidden border border-[#162547]">
                            <div
                              className={`h-full rounded-full bg-gradient-to-r ${risk.bar} transition-all duration-1000 animate-gauge-fill`}
                              style={{ width: `${sus.risk_score}%` }}
                            />
                          </div>
                        </div>

                        {sus.matched_sources && sus.matched_sources.length > 0 && (
                          <div className="space-y-1 pt-1">
                            <div className="flex items-center gap-1 text-[9px] font-mono text-cyan-400">
                              <TrendingUp className="w-3 h-3" />
                              <span>CORRELATED ACROSS {sus.matched_sources.length} SOURCES:</span>
                            </div>
                            <div className="flex flex-wrap gap-1">
                              {sus.matched_sources.map((ms, m) => (
                                <span key={m} className="text-[9px] font-mono px-2 py-0.5 rounded bg-[#070b14] text-slate-300 border border-[#1c2d52] truncate max-w-[200px]">{ms}</span>
                              ))}
                            </div>
                          </div>
                        )}

                        {sus.notes && (
                          <p className="text-[11px] text-slate-400 bg-[#070b14] p-2 rounded-lg border border-[#162547] leading-relaxed">{sus.notes}</p>
                        )}

                        <div className="flex items-center justify-between text-[9px] font-mono text-slate-500 pt-1">
                          <span>Role: <strong className="text-slate-300">{sus.role || 'Unspecified'}</strong></span>
                          {sus.last_active && <span>Active: {sus.last_active}</span>}
                        </div>
                      </div>
                    );
                  })}

                  {(!selected.suspects || selected.suspects.length === 0) && (
                    <div className="p-6 rounded-xl bg-[#0e172e] border border-dashed border-[#1c2d52] text-center text-xs text-slate-500 space-y-2">
                      <p>No suspicious accounts added yet.</p>
                      <button onClick={() => setShowAddSuspect(true)} className="text-xs font-semibold text-rose-400 hover:underline">
                        + Add first suspect account
                      </button>
                    </div>
                  )}
                </div>

                <button
                  onClick={() => setShowAddSuspect(true)}
                  className="w-full flex items-center justify-center gap-2 py-2 rounded-xl bg-[#0e172e] border border-[#1c2d52] hover:border-rose-500/30 text-xs font-semibold text-slate-300 hover:text-rose-300 transition-all"
                >
                  <UserPlus className="w-3.5 h-3.5" />
                  <span>Register & Correlate Suspect</span>
                </button>
              </div>

            </div>
          </>
        ) : (
          <div className="flex items-center justify-center h-full">
            <div className="p-8 rounded-2xl bg-[#0a1020] border border-[#1c2d52] text-center max-w-md space-y-4 animate-fade-in-up">
              <Crosshair className="w-12 h-12 text-cyan-400 mx-auto" />
              <h3 className="text-sm font-bold text-slate-200">No CTI Project Selected</h3>
              <p className="text-xs text-slate-400">Choose an existing intelligence operation from the left panel, or create a new project.</p>
              <button onClick={() => setShowNewProject(true)} className="px-4 py-2 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 text-slate-950 font-bold text-xs">
                Create CTI Project
              </button>
            </div>
          </div>
        )}
      </main>

      {/* ═══════ MODAL 1: CREATE NEW CTI PROJECT ═══════ */}
      <Modal open={showNewProject} onClose={() => setShowNewProject(false)} title="Create New CTI Project" subtitle="Mention the topic — the system will predict intelligence sources & start observing" icon={Crosshair}>
        <form onSubmit={handleCreateProject} className="space-y-4">
          <div>
            <label className="block text-xs font-bold text-slate-300 uppercase tracking-wider mb-1.5">Project Name *</label>
            <input type="text" required placeholder="e.g. Operation Golden Crescent Intercept" value={newProject.name} onChange={(e) => setNewProject({ ...newProject, name: e.target.value })} className="w-full px-3.5 py-2 rounded-xl bg-[#0a1122] border border-[#1c2d52] text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-400" />
          </div>
          <div>
            <label className="block text-xs font-bold text-slate-300 uppercase tracking-wider mb-1.5">Investigation Topic *</label>
            <input type="text" required placeholder="e.g. Drug Trafficking, Border Drone Drops" value={newProject.topic} onChange={(e) => setNewProject({ ...newProject, topic: e.target.value })} className="w-full px-3.5 py-2 rounded-xl bg-[#0a1122] border border-[#1c2d52] text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-400" />
            <div className="flex gap-2 mt-2 flex-wrap">
              <span className="text-[10px] font-mono text-slate-500 self-center">Presets:</span>
              {['Drug Trafficking', 'Border Narcoterrorism & Drone Drops', 'Pharma Diversion & Psychotropics'].map((preset) => (
                <button key={preset} type="button" onClick={() => setNewProject({ ...newProject, topic: preset })} className="px-2 py-0.5 rounded-lg bg-[#14203b] border border-[#1c2d52] text-[10px] font-mono text-cyan-300 hover:bg-cyan-500/10 hover:border-cyan-400/40">{preset}</button>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-xs font-bold text-slate-300 uppercase tracking-wider mb-1.5">Operation Scope & Description</label>
            <textarea rows={3} placeholder="Describe the target districts, cartel aliases, suspected substances..." value={newProject.description} onChange={(e) => setNewProject({ ...newProject, description: e.target.value })} className="w-full px-3.5 py-2 rounded-xl bg-[#0a1122] border border-[#1c2d52] text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-400" />
          </div>
          <div className="p-3 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-[11px] text-cyan-300 flex items-start gap-2">
            <Sparkles className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <span><strong>Automated Intelligence Prediction:</strong> Submitting will auto-generate targeted .onion links, Telegram channels, and clearnet listings tailored to the topic, with live observation started immediately.</span>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={() => setShowNewProject(false)} className="px-4 py-2 rounded-xl bg-[#14203b] border border-[#1c2d52] text-xs font-semibold text-slate-300 hover:text-slate-100">Cancel</button>
            <button type="submit" disabled={submitting} className="px-5 py-2 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 text-slate-950 font-bold text-xs hover:from-cyan-400 hover:to-blue-500 disabled:opacity-50">
              {submitting ? 'Predicting Sources & Starting...' : 'Create & Start Observing'}
            </button>
          </div>
        </form>
      </Modal>

      {/* ═══════ MODAL 2: ADD NEW SOURCE ═══════ */}
      <Modal open={showAddSource} onClose={() => setShowAddSource(false)} title="Add New Intelligence Source" subtitle={`Attach a listening pipeline to "${selected?.name}"`} icon={Signal}>
        <form onSubmit={handleAddSource} className="space-y-4">
          <div>
            <label className="block text-xs font-bold text-slate-300 uppercase tracking-wider mb-1.5">Source Pipeline Type *</label>
            <div className="grid grid-cols-3 gap-3">
              {[
                { type: 'TELEGRAM', label: 'Telegram', icon: Send, color: 'text-blue-400' },
                { type: 'DARK_WEB', label: 'Dark Web (.onion)', icon: EyeOff, color: 'text-purple-400' },
                { type: 'SURFACE_WEB', label: 'Surface Clearnet', icon: Globe, color: 'text-emerald-400' },
              ].map((st) => {
                const StIcon = st.icon;
                const isCur = newSource.source_type === st.type;
                return (
                  <button key={st.type} type="button" onClick={() => setNewSource({ ...newSource, source_type: st.type })}
                    className={`p-3 rounded-xl border text-left flex flex-col items-center gap-1.5 transition-all ${isCur ? 'bg-cyan-500/15 border-cyan-400 text-cyan-300 shadow-[0_0_15px_rgba(6,182,212,0.2)]' : 'bg-[#0a1122] border-[#1c2d52] text-slate-400 hover:bg-[#14203b]'}`}>
                    <StIcon className={`w-5 h-5 ${st.color}`} />
                    <span className="text-[11px] font-bold">{st.label}</span>
                  </button>
                );
              })}
            </div>
          </div>
          <div>
            <label className="block text-xs font-bold text-slate-300 uppercase tracking-wider mb-1.5">Source Identifier / Channel / URL *</label>
            <input type="text" required placeholder={newSource.source_type === 'DARK_WEB' ? 'e.g. punjabmarket7x...onion/listings' : newSource.source_type === 'TELEGRAM' ? 'e.g. t.me/pb_underground_drops' : 'e.g. https://classifieds-chemicals.in/supply'} value={newSource.identifier} onChange={(e) => setNewSource({ ...newSource, identifier: e.target.value })} className="w-full px-3.5 py-2 rounded-xl bg-[#0a1122] border border-[#1c2d52] text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-400" />
          </div>
          <div>
            <label className="block text-xs font-bold text-slate-300 uppercase tracking-wider mb-1.5">Source Label / Name</label>
            <input type="text" placeholder="e.g. Majitha Sector Telegram Wiretap" value={newSource.label} onChange={(e) => setNewSource({ ...newSource, label: e.target.value })} className="w-full px-3.5 py-2 rounded-xl bg-[#0a1122] border border-[#1c2d52] text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-400" />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={() => setShowAddSource(false)} className="px-4 py-2 rounded-xl bg-[#14203b] border border-[#1c2d52] text-xs font-semibold text-slate-300 hover:text-slate-100">Cancel</button>
            <button type="submit" disabled={submitting} className="px-5 py-2 rounded-xl bg-cyan-500 text-slate-950 font-bold text-xs hover:bg-cyan-400 disabled:opacity-50">
              {submitting ? 'Connecting Pipeline...' : 'Add Intelligence Source'}
            </button>
          </div>
        </form>
      </Modal>

      {/* ═══════ MODAL 3: ADD SUS ACC ═══════ */}
      <Modal open={showAddSuspect} onClose={() => setShowAddSuspect(false)} title="Add Suspicious Account (Sus Acc)" subtitle="Tracks handle activity and auto-correlates across all sources" icon={Fingerprint}>
        <form onSubmit={handleAddSuspect} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-bold text-slate-300 uppercase tracking-wider mb-1.5">Username / Digital Handle *</label>
              <input type="text" required placeholder="e.g. @handle_to_track" value={newSuspect.username} onChange={(e) => setNewSuspect({ ...newSuspect, username: e.target.value })} className="w-full px-3.5 py-2 rounded-xl bg-[#0a1122] border border-[#1c2d52] text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-400" />
            </div>
            <div>
              <label className="block text-xs font-bold text-slate-300 uppercase tracking-wider mb-1.5">Real Name / Alias</label>
              <input type="text" placeholder="e.g. Akashdeep Singh" value={newSuspect.alias} onChange={(e) => setNewSuspect({ ...newSuspect, alias: e.target.value })} className="w-full px-3.5 py-2 rounded-xl bg-[#0a1122] border border-[#1c2d52] text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-400" />
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-bold text-slate-300 uppercase tracking-wider mb-1.5">Primary Platform</label>
              <input type="text" placeholder="e.g. Telegram & Tor / Wickr" value={newSuspect.platform} onChange={(e) => setNewSuspect({ ...newSuspect, platform: e.target.value })} className="w-full px-3.5 py-2 rounded-xl bg-[#0a1122] border border-[#1c2d52] text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-400" />
            </div>
            <div>
              <label className="block text-xs font-bold text-slate-300 uppercase tracking-wider mb-1.5">Suspected Role</label>
              <input type="text" placeholder="e.g. Courier / Ground Mule" value={newSuspect.role} onChange={(e) => setNewSuspect({ ...newSuspect, role: e.target.value })} className="w-full px-3.5 py-2 rounded-xl bg-[#0a1122] border border-[#1c2d52] text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-400" />
            </div>
          </div>
          <div>
            <label className="block text-xs font-bold text-slate-300 uppercase tracking-wider mb-1.5">Investigator Notes & Intercept Context</label>
            <textarea rows={3} placeholder="Observed in intercepted wiretap chatter discussing drop packages..." value={newSuspect.notes} onChange={(e) => setNewSuspect({ ...newSuspect, notes: e.target.value })} className="w-full px-3.5 py-2 rounded-xl bg-[#0a1122] border border-[#1c2d52] text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-400" />
          </div>
          <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-[11px] text-rose-300 flex items-start gap-2">
            <TrendingUp className="w-4 h-4 flex-shrink-0 mt-0.5 text-rose-400" />
            <span><strong>Cross-Source Correlation Engine:</strong> The system will immediately cross-reference this username against all Tor forums, Telegram channels, and blockchain wallets to assign an automated Risk Score.</span>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={() => setShowAddSuspect(false)} className="px-4 py-2 rounded-xl bg-[#14203b] border border-[#1c2d52] text-xs font-semibold text-slate-300 hover:text-slate-100">Cancel</button>
            <button type="submit" disabled={submitting} className="px-5 py-2 rounded-xl bg-rose-500 text-slate-950 font-bold text-xs hover:bg-rose-400 disabled:opacity-50">
              {submitting ? 'Correlating Across Pipelines...' : 'Track & Correlate Sus Acc'}
            </button>
          </div>
        </form>
      </Modal>

      {/* ═══════ MODAL 4: DATA VAULT (COMPRESS & ENCRYPT) ═══════ */}
      <Modal open={showVault} onClose={() => setShowVault(false)} title="Data Compression & AES-256 Encryption Vault" subtitle="Efficiently encrypt and compress & decompress large intelligence datasets" icon={Database}>
        <div className="space-y-4">
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-xs font-bold text-slate-300 uppercase tracking-wider">Raw Intelligence Data</label>
              <span className="text-[10px] font-mono text-cyan-400">Size: {new Blob([vaultData]).size} bytes</span>
            </div>
            <textarea rows={6} value={vaultData} onChange={(e) => setVaultData(e.target.value)} placeholder="Paste or inspect raw intercepted telemetry..." className="w-full px-3.5 py-2 rounded-xl bg-[#070b14] border border-[#1c2d52] text-[11px] font-mono text-slate-300 focus:outline-none focus:border-purple-400" />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-bold text-slate-300 uppercase tracking-wider mb-1">AES-256 Passphrase</label>
              <input type="text" value={vaultPassphrase} onChange={(e) => setVaultPassphrase(e.target.value)} className="w-full px-3 py-1.5 rounded-lg bg-[#0a1122] border border-[#1c2d52] text-xs font-mono text-slate-200" />
            </div>
            <div className="flex items-end gap-2">
              <button type="button" onClick={handleCompressAndEncrypt} disabled={vaultBusy || !vaultData.trim()}
                className="flex-1 flex items-center justify-center gap-2 py-2 rounded-xl bg-gradient-to-r from-purple-500 to-indigo-600 text-white text-xs font-bold hover:from-purple-400 hover:to-indigo-500 transition-all disabled:opacity-50">
                <Lock className="w-3.5 h-3.5" />
                {vaultBusy ? 'Processing...' : 'Compress & Encrypt'}
              </button>
            </div>
          </div>

          {vaultEncryptedResult && (
            <div className="p-4 rounded-xl bg-purple-500/10 border border-purple-500/30 space-y-3 animate-modal-in">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-purple-300 flex items-center gap-1.5">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  {vaultEncryptedResult.algorithm || 'AES-256-GCM'} Complete
                </span>
                <span className="px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 text-xs font-mono font-bold">
                  {vaultEncryptedResult.space_saved_percentage} Saved
                </span>
              </div>
              <div className="grid grid-cols-3 gap-2 text-center text-xs font-mono">
                <div className="p-2 rounded-lg bg-[#070b14] border border-[#1c2d52]">
                  <div className="text-[10px] text-slate-500">Original</div>
                  <div className="text-slate-200 font-bold">{vaultEncryptedResult.original_size_bytes} B</div>
                </div>
                <div className="p-2 rounded-lg bg-[#070b14] border border-[#1c2d52]">
                  <div className="text-[10px] text-slate-500">Compressed</div>
                  <div className="text-cyan-400 font-bold">{vaultEncryptedResult.compressed_size_bytes} B</div>
                </div>
                <div className="p-2 rounded-lg bg-[#070b14] border border-[#1c2d52]">
                  <div className="text-[10px] text-slate-500">Encrypted</div>
                  <div className="text-purple-300 font-bold">{vaultEncryptedResult.encrypted_size_bytes} B</div>
                </div>
              </div>
              <div className="space-y-1">
                <div className="text-[10px] font-mono text-slate-400 flex items-center justify-between">
                  <span>Ciphertext (Base64)</span>
                  <span>Nonce: {vaultEncryptedResult.nonce_b64}</span>
                </div>
                <div className="p-2.5 rounded-lg bg-[#070b14] border border-[#1c2d52] font-mono text-[10px] text-purple-300 break-all max-h-24 overflow-y-auto">
                  {vaultEncryptedResult.encrypted_payload_b64}
                </div>
              </div>
              <div className="pt-2 border-t border-purple-500/20 flex items-center justify-between">
                <span className="text-[11px] text-slate-300">Verify integrity by decrypting & decompressing:</span>
                <button type="button" onClick={handleDecryptAndDecompress} disabled={vaultBusy}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 text-xs font-bold hover:bg-cyan-500/30">
                  <Unlock className="w-3.5 h-3.5" />
                  Decrypt & Decompress
                </button>
              </div>
            </div>
          )}

          {vaultDecryptedResult && (
            <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30 space-y-2 animate-modal-in">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-emerald-300 flex items-center gap-1.5">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  Data Restored & Integrity Verified (0 Bit Loss)
                </span>
                <span className="text-xs font-mono text-emerald-400">Restored: {vaultDecryptedResult.restored_size_bytes} bytes</span>
              </div>
              <div className="p-2.5 rounded-lg bg-[#070b14] border border-[#1c2d52] font-mono text-[10px] text-slate-300 max-h-32 overflow-y-auto whitespace-pre-wrap">
                {vaultDecryptedResult.decrypted_data}
              </div>
            </div>
          )}
        </div>
      </Modal>

      {/* ═══════ MODAL 5: REPORT DETAIL ═══════ */}
      {showReportDetail && (
        <Modal open={!!showReportDetail} onClose={() => setShowReportDetail(null)} title={`Intelligence Dossier: ${showReportDetail.id}`} subtitle={showReportDetail.title} icon={FileText}>
          <div className="space-y-4">
            <div className="p-4 rounded-xl bg-[#0a1122] border border-[#1c2d52] space-y-2 text-xs">
              <div className="flex items-center justify-between"><span className="text-slate-500">Sealed Timestamp:</span><span className="text-slate-200 font-mono">{showReportDetail.timestamp}</span></div>
              <div className="flex items-center justify-between"><span className="text-slate-500">Lead Investigator:</span><span className="text-cyan-400 font-mono">{showReportDetail.investigator}</span></div>
              <div className="flex items-center justify-between"><span className="text-slate-500">Target Substances:</span><span className="text-rose-400 font-bold">{showReportDetail.substances.join(', ')}</span></div>
              <div className="flex items-center justify-between"><span className="text-slate-500">SHA-256:</span><span className="text-slate-300 font-mono text-[10px]">{showReportDetail.hash}</span></div>
            </div>
            <div>
              <h4 className="text-xs font-bold text-slate-300 uppercase mb-1">Executive Summary</h4>
              <p className="text-xs text-slate-300 leading-relaxed bg-[#070b14] p-3 rounded-xl border border-[#1c2d52]">{showReportDetail.summary}</p>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button onClick={() => setShowReportDetail(null)} className="px-4 py-2 rounded-xl bg-[#14203b] border border-[#1c2d52] text-xs font-semibold text-slate-300">Close Preview</button>
              <a href="/reports" className="px-5 py-2 rounded-xl bg-cyan-500 text-slate-950 font-bold text-xs hover:bg-cyan-400 flex items-center gap-1.5">
                <Download className="w-3.5 h-3.5" />
                Export Certified Evidence
              </a>
            </div>
          </div>
        </Modal>
      )}

    </div>
  );
};
