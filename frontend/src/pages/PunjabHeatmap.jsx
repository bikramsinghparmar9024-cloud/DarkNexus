import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import { 
  MapPin, 
  ShieldAlert, 
  AlertTriangle, 
  CheckCircle2, 
  Compass, 
  FileText, 
  Search, 
  Layers,
  Radio
} from 'lucide-react';

export const PunjabHeatmap = () => {
  const [hotspots, setHotspots] = useState([]);
  const [borderAlerts, setBorderAlerts] = useState([]);
  const [filterMode, setFilterMode] = useState('all'); // 'all' or 'border_only'
  const [selectedSpot, setSelectedSpot] = useState(null);

  // Search place
  const [searchPlace, setSearchPlace] = useState('Majitha');
  const [lookupResult, setLookupResult] = useState(null);
  const [lookupLoading, setLookupLoading] = useState(false);

  // Section 65B generation state.
  // These start empty on purpose. They were pre-filled with an invented FIR
  // number and badge number, which meant a court evidence certificate could be
  // generated carrying a case reference nobody had entered.
  const [certModalOpen, setCertModalOpen] = useState(false);
  const [firNumber, setFirNumber] = useState('');
  const [badgeNo, setBadgeNo] = useState('');

  // What the analyser actually resolved, keyed by district. The district grid
  // itself is a reference map and is identical on an empty database; this is
  // the only thing on the page that reflects collected intelligence.
  const [analysed, setAnalysed] = useState({});

  useEffect(() => {
    loadHotspots();
    loadBorderAlerts();
    loadAnalysedLocations();
  }, []);

  const loadAnalysedLocations = async () => {
    try {
      const res = await apiClient.get('/api/correlation/hotspots');
      const byLocation = {};
      (res.data?.hotspots || []).forEach((h) => { byLocation[h.location] = h; });
      setAnalysed(byLocation);
    } catch (e) {
      console.error(e);
    }
  };

  const loadHotspots = async () => {
    try {
      const res = await apiClient.get('/api/geo/hotspots');
      setHotspots(res.data);
      if (res.data.length > 0) setSelectedSpot(res.data[0]);
    } catch (e) {
      console.error(e);
    }
  };

  const loadBorderAlerts = async () => {
    try {
      const res = await apiClient.get('/api/geo/border-alerts');
      setBorderAlerts(res.data.alerts || []);
    } catch (e) {
      console.error(e);
    }
  };

  const handleLookup = async (e) => {
    e.preventDefault();
    setLookupLoading(true);
    try {
      const res = await apiClient.post('/api/geo/resolve', { location_name: searchPlace });
      setLookupResult(res.data);
    } catch (err) {
      alert('Location not found in Punjab DB');
    } finally {
      setLookupLoading(false);
    }
  };

  const handleDownload65B = async () => {
    try {
      const res = await apiClient.post('/api/geo/generate-section-65b', {
        investigator_name: "Harpreet Singh",
        investigator_badge: badgeNo,
        department: "Punjab State Narcotics Control Bureau, Amritsar Range",
        case_fir_number: firNumber,
        record_ids: borderAlerts.map(a => a.id)
      });
      // Open in new tab
      const blob = new Blob([res.data], { type: 'text/html' });
      const url = window.URL.createObjectURL(blob);
      window.open(url, '_blank');
    } catch (err) {
      alert('Error generating 65B certificate: ' + err.message);
    }
  };

  const displayedSpots = filterMode === 'border_only' 
    ? hotspots.filter(h => h.critical_border_zone)
    : hotspots;

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Top Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold uppercase tracking-wider text-slate-100 flex items-center gap-2">
            <Compass className="w-6 h-6 text-cyan-400" />
            <span>Punjab Narcotics Geospatial Heatmap & Indo-Pak Border Radar</span>
          </h2>
          <p className="text-xs text-slate-400 font-mono mt-1">
            Indo-Pak Border 15km Threat Corridor &bull; Transit Nexus Mapping &bull; Section 65B Court Certification
          </p>
        </div>

        <button
          onClick={() => setCertModalOpen(true)}
          className="bg-emerald-500 hover:bg-emerald-400 text-black font-bold py-2.5 px-4 rounded-lg text-xs font-mono flex items-center gap-2 transition-all glow-cyan"
        >
          <FileText className="w-4 h-4" />
          <span>Export Section 65B Evidence Certificate</span>
        </button>
      </div>

      {/* Control Bar & Filter */}
      <div className="flex flex-wrap items-center justify-between gap-4 glass-card p-4 rounded-xl border border-[#1c2d52]">
        <div className="flex items-center gap-3 text-xs font-mono">
          <span className="text-slate-400 uppercase text-[10px]">Filter View:</span>
          <button
            onClick={() => setFilterMode('all')}
            className={`px-3 py-1.5 rounded-lg border transition-all ${
              filterMode === 'all' 
                ? 'bg-cyan-500/20 text-cyan-400 border-cyan-500/40 font-bold' 
                : 'bg-[#070b14] text-slate-400 border-[#1c2d52]'
            }`}
          >
            All {hotspots.length} Districts
          </button>
          <button
            onClick={() => setFilterMode('border_only')}
            className={`px-3 py-1.5 rounded-lg border transition-all flex items-center gap-1.5 ${
              filterMode === 'border_only' 
                ? 'bg-rose-500/20 text-rose-400 border-rose-500/40 font-bold' 
                : 'bg-[#070b14] text-slate-400 border-[#1c2d52]'
            }`}
          >
            <Radio className="w-3.5 h-3.5 text-rose-400 animate-pulse" />
            <span>Critical Border Zone (&lt; 15 km)</span>
          </button>
        </div>

        {/* Quick Place Lookup */}
        <form onSubmit={handleLookup} className="flex items-center gap-2">
          <input
            type="text"
            value={searchPlace}
            onChange={(e) => setSearchPlace(e.target.value)}
            placeholder="Search Punjab district or town..."
            className="bg-[#070b14] border border-[#1c2d52] rounded-lg px-3 py-1.5 text-xs text-slate-100 font-mono outline-none focus:border-cyan-500 w-48"
          />
          <button
            type="submit"
            className="bg-[#14203b] hover:bg-[#1c2d52] text-slate-200 border border-[#1c2d52] px-3 py-1.5 rounded-lg text-xs font-mono flex items-center gap-1"
          >
            <Search className="w-3.5 h-3.5" />
            <span>Measure</span>
          </button>
        </form>
      </div>

      {lookupResult && (
        <div className={`p-3.5 rounded-xl border text-xs font-mono flex items-center justify-between ${
          lookupResult.in_critical_border_corridor 
            ? 'bg-rose-500/10 border-rose-500/30 text-rose-300' 
            : 'bg-cyan-500/10 border-cyan-500/30 text-cyan-300'
        }`}>
          <div>
            <strong>{lookupResult.location}</strong> &bull; Distance to Indo-Pak Border: <span className="font-bold">{lookupResult.distance_to_border_km} km</span>
            {/* This badge claimed drone and contraband activity at any place
                within 15 km. The measurement supports the distance, nothing
                more; the activity claim was invented. */}
            {lookupResult.in_critical_border_corridor && (
              <span className="ml-3 px-2 py-0.5 rounded bg-rose-500 text-black font-bold text-[10px]">
                WITHIN 15 KM BORDER CORRIDOR
              </span>
            )}
          </div>
          <span className="text-slate-500">Reference geography</span>
        </div>
      )}

      {/* Interactive Map Canvas Simulator */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Visual Radar */}
        <div className="lg:col-span-2 glass-card rounded-xl p-5 border border-[#1c2d52] relative overflow-hidden flex flex-col min-h-[500px]">
          <div className="flex items-center justify-between mb-4 border-b border-[#1c2d52] pb-3">
            <div className="text-xs font-mono text-slate-300 uppercase tracking-wider flex items-center gap-2">
              <Compass className="w-4 h-4 text-cyan-400" />
              <span>Geospatial Radar: Punjab State Territorial Grid</span>
            </div>
            <div className="flex items-center gap-3 text-[11px] font-mono">
              <span className="flex items-center gap-1 text-rose-400">
                <span className="w-2.5 h-2.5 rounded-full bg-rose-500"></span> &lt; 15km Border Zone
              </span>
              <span className="flex items-center gap-1 text-cyan-400">
                <span className="w-2.5 h-2.5 rounded-full bg-cyan-400"></span> Inland Distribution
              </span>
            </div>
          </div>

          {/* District Grid Cluster */}
          <div className="flex-1 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3 overflow-y-auto max-h-[420px] p-1">
            {displayedSpots.map((spot) => (
              <div
                key={spot.name}
                onClick={() => setSelectedSpot(spot)}
                className={`p-3 rounded-lg border cursor-pointer transition-all ${
                  spot.critical_border_zone
                    ? 'bg-rose-950/20 border-rose-500/40 hover:border-rose-400 hover:shadow-[0_0_15px_rgba(244,63,94,0.2)]'
                    : 'bg-[#0d1527] border-[#1c2d52] hover:border-cyan-500/40'
                } ${selectedSpot?.name === spot.name ? 'ring-2 ring-cyan-400' : ''}`}
              >
                <div className="flex items-start justify-between">
                  <span className="text-xs font-bold font-mono text-slate-100">{spot.name}</span>
                  <MapPin className={`w-3.5 h-3.5 ${spot.critical_border_zone ? 'text-rose-400' : 'text-cyan-400'}`} />
                </div>
                <div className="text-[10px] font-mono text-slate-400 mt-2">
                  Border: <span className={spot.critical_border_zone ? 'text-rose-300 font-bold' : 'text-slate-200'}>{spot.dist_to_border} km</span>
                </div>
                {/* "Critical Outpost" asserted a police post at each of these
                    places. The only thing the data supports is the distance. */}
                {spot.critical_border_zone && (
                  <div className="mt-1 text-[9px] font-mono text-rose-400/80 uppercase tracking-tight">
                    Within 15 km corridor
                  </div>
                )}
                {analysed[spot.name] ? (
                  <div className="mt-1 text-[9px] font-mono text-cyan-300 uppercase tracking-tight">
                    {analysed[spot.name].distinct_records} record{analysed[spot.name].distinct_records === 1 ? '' : 's'}
                  </div>
                ) : (
                  <div className="mt-1 text-[9px] font-mono text-slate-600 uppercase tracking-tight">
                    No records
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* This grid is a reference map of Punjab districts and renders
              identically on an empty database. Saying so prevents it being
              read as collection coverage. The line here previously claimed
              "Active BSF & State Police Coordination", which was a hardcoded
              string describing nothing. */}
          <div className="mt-3 pt-3 border-t border-[#1c2d52] flex items-center justify-between text-[11px] font-mono text-slate-500">
            <span>Reference geography &bull; 553 km Indo-Pak international border</span>
            <span>Highlighted districts carry collected records</span>
          </div>
        </div>

        {/* Right Details & Border Feed */}
        <div className="space-y-4">
          {/* Selected District Details */}
          {selectedSpot && (
            <div className="glass-card rounded-xl p-5 border border-[#1c2d52] space-y-3">
              <div className="flex items-center justify-between">
                <h4 className="text-sm font-bold font-mono text-slate-100 uppercase">{selectedSpot.name}</h4>
                <span className={`px-2 py-0.5 rounded text-[10px] font-mono ${
                  selectedSpot.critical_border_zone ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30' : 'bg-cyan-500/20 text-cyan-400'
                }`}>
                  {selectedSpot.critical_border_zone ? 'CRITICAL BORDER ZONE' : 'INLAND HUB'}
                </span>
              </div>

              <div className="text-xs font-mono space-y-1.5 text-slate-300">
                <div className="text-[10px] uppercase tracking-wider text-slate-500">Reference geography</div>
                <div>Distance to International Border: <span className="text-cyan-400 font-bold">{selectedSpot.dist_to_border} km</span></div>
                <div>GPS Coordinates: <span className="text-slate-400">{selectedSpot.lat}, {selectedSpot.lon}</span></div>

                {/* Everything below comes from the analysis pipeline. Where
                    nothing has been collected, the panel says so rather than
                    reporting a status. It previously read "ACTIVE DIGITAL
                    INTERCEPTION" - a hardcoded string, true of nowhere. */}
                <div className="pt-2 mt-2 border-t border-[#1c2d52] text-[10px] uppercase tracking-wider text-slate-500">
                  Collected intelligence
                </div>
                {analysed[selectedSpot.name] ? (
                  <>
                    <div>Records resolved here: <span className="text-slate-100 font-bold">{analysed[selectedSpot.name].distinct_records}</span></div>
                    <div>Sightings: <span className="text-slate-100">{analysed[selectedSpot.name].total_sightings}</span>
                      <span className="text-slate-500"> ({analysed[selectedSpot.name].text_mentions} text, {analysed[selectedSpot.name].gps_fixes} photo GPS)</span>
                    </div>
                    <div>Independent sources: <span className="text-slate-100">{analysed[selectedSpot.name].independent_sources.join(', ')}</span></div>
                    <div>Highest threat: <span className="text-slate-100 font-bold">{analysed[selectedSpot.name].max_threat_level}</span></div>
                    <div>Hotspot confidence: <span className="text-slate-100">{analysed[selectedSpot.name].confidence}</span>
                      {!analysed[selectedSpot.name].is_hotspot && (
                        <span className="text-slate-500"> &mdash; below the evidence threshold</span>
                      )}
                    </div>
                  </>
                ) : (
                  <div className="text-slate-500">
                    No collected record resolves to this district.
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Intercepts tied to Border */}
          <div className="glass-card rounded-xl border border-[#1c2d52] overflow-hidden">
            <div className="p-3.5 border-b border-[#1c2d52] flex items-center justify-between">
              {/* Was "Border Transit Chatter", listing anything whose text
                  contained the word "border" - three Wikipedia articles were
                  presented here as intercepted border activity. Entries now
                  come from resolved geo markers and each states its
                  disposition, because a seizure report near Attari and an
                  offer near Attari are different products. */}
              <h4 className="text-xs font-bold font-mono text-slate-200 uppercase">
                Records In Border Corridor ({borderAlerts.length})
              </h4>
              <span className="text-[10px] font-mono text-slate-500">&lt; 15 km, resolved</span>
            </div>

            <div className="divide-y divide-[#1c2d52] max-h-[290px] overflow-y-auto">
              {borderAlerts.length === 0 && (
                <div className="p-4 text-[11px] font-mono text-slate-500">
                  No collected record resolves to the border corridor.
                </div>
              )}
              {borderAlerts.map((alert) => (
                <div key={alert.id} className="p-3 hover:bg-[#14203b]/40 transition-colors text-xs font-mono">
                  <div className="flex items-center justify-between">
                    <span className={`font-bold uppercase text-[10px] px-1.5 py-0.5 rounded ${
                      alert.disposition === 'OPERATIONAL'
                        ? 'bg-rose-500/20 text-rose-400'
                        : alert.disposition === 'REPORTING'
                        ? 'bg-cyan-500/20 text-cyan-300'
                        : 'bg-slate-600/20 text-slate-400'
                    }`}>
                      {alert.disposition}
                    </span>
                    <span className="text-[10px] text-slate-400">{alert.created_at}</span>
                  </div>
                  <div className="mt-1.5 text-[10px] text-slate-400">
                    {alert.nearest_location} &bull; {alert.distance_to_border_km} km &bull; {alert.threat_level} ({alert.risk_score}/100)
                  </div>
                  <div className="mt-1 text-slate-300 line-clamp-2 text-[11px]">
                    {alert.snippet}
                  </div>
                  <div className="mt-1 text-[10px] text-slate-500 italic line-clamp-2">
                    {alert.disposition_note}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Section 65B Modal */}
      {certModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="w-full max-w-lg glass-card rounded-xl border border-[#1c2d52] p-6 space-y-4">
            <div className="flex items-center justify-between border-b border-[#1c2d52] pb-3">
              <h3 className="text-sm font-bold uppercase text-slate-100 font-mono">
                Generate Section 65B Evidence Certificate
              </h3>
              <button onClick={() => setCertModalOpen(false)} className="text-slate-400 hover:text-slate-200 text-xs">✕</button>
            </div>

            <p className="text-xs text-slate-400 font-mono">
              Generates a legal court certificate conforming to Section 65B Indian Evidence Act / Section 63 BSA 2023 with SHA-256 digital hash digest.
            </p>

            <div className="space-y-3 font-mono text-xs">
              <div>
                <label className="text-[11px] text-slate-400 block mb-1">Police Case / FIR Reference</label>
                <input
                  type="text"
                  value={firNumber}
                  onChange={(e) => setFirNumber(e.target.value)}
                  className="w-full bg-[#070b14] border border-[#1c2d52] rounded-lg px-3 py-2 text-slate-100 outline-none focus:border-cyan-500"
                />
              </div>

              <div>
                <label className="text-[11px] text-slate-400 block mb-1">Investigating Officer Badge</label>
                <input
                  type="text"
                  value={badgeNo}
                  onChange={(e) => setBadgeNo(e.target.value)}
                  className="w-full bg-[#070b14] border border-[#1c2d52] rounded-lg px-3 py-2 text-slate-100 outline-none focus:border-cyan-500"
                />
              </div>

              <div className="text-[11px] text-cyan-400">
                Will certify {borderAlerts.length} electronic records with cryptographic hashes.
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 pt-3 border-t border-[#1c2d52]">
              <button
                onClick={() => setCertModalOpen(false)}
                className="px-4 py-2 rounded-lg text-xs font-mono text-slate-400 hover:text-slate-200"
              >
                Cancel
              </button>
              <button
                onClick={handleDownload65B}
                className="px-4 py-2 rounded-lg bg-emerald-500 text-black font-bold text-xs font-mono flex items-center gap-1.5 glow-cyan"
              >
                <FileText className="w-4 h-4" />
                <span>Generate Official Certificate</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
