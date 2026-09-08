import React, { useEffect, useRef, useState } from 'react';
import { apiClient, describeApiError } from '../api/client';
import { Share2, RefreshCw, ZoomIn, ZoomOut, Maximize } from 'lucide-react';



export const NetworkMap = () => {
  const cyRef = useRef(null);
  const containerRef = useRef(null);
  const [layout, setLayout] = useState('cose');
  const [selectedNode, setSelectedNode] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [nodeCount, setNodeCount] = useState(null);
  // Where the entity was actually found. Selecting a node used to show its
  // label and type only, so an investigator could see that a substance was in
  // the graph but had to leave it to find out where the word appeared.
  const [nodeDetail, setNodeDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const loadNodeDetail = async (nodeKey) => {
    setDetailLoading(true);
    setNodeDetail(null);
    try {
      const res = await apiClient.get(
        `/api/dashboard/network-graph/node/${encodeURIComponent(nodeKey)}`);
      setNodeDetail(res.data);
    } catch (err) {
      setNodeDetail({ error: describeApiError(err).message });
    } finally {
      setDetailLoading(false);
    }
  };

  useEffect(() => {
    let cy = null;
    // The import and construction below are asynchronous, so the effect can be
    // torn down before `cy` is ever assigned. Without this flag the cleanup
    // finds null, destroys nothing, and the instance created moments later
    // animates its layout against a container React has already replaced -
    // which is where cytoscape's "cannot read properties of null" came from.
    let cancelled = false;

    const initGraph = async () => {
      const cytoscape = (await import('cytoscape')).default;
      if (cancelled || !containerRef.current) return;

      // The graph shows correlations actually derived from collected records.
      // It previously fell back to a hardcoded syndicate - Tariq Lahori and
      // company - whenever the request failed, so an empty or unreachable
      // system displayed a fully mapped trafficking network.
      let elements = [];
      try {
        const res = await apiClient.get('/api/dashboard/network-graph');
        if (res.data?.nodes && res.data?.edges) {
          elements = [...res.data.nodes, ...res.data.edges];
        }
        setLoadError(null);
        setNodeCount(res.data?.nodes?.length ?? 0);
      } catch (e) {
        setLoadError(describeApiError(e));
        setNodeCount(0);
      }

      const typeColors = {
        suspect: '#f43f5e',
        telegram: '#3b82f6',
        darkweb: '#a855f7',
        crypto: '#f59e0b',
      };

      cy = cytoscape({
        container: containerRef.current,
        elements,
        style: [
          {
            selector: 'node',
            style: {
              'label': 'data(label)',
              'font-size': '10px',
              'font-family': 'JetBrains Mono, monospace',
              'color': '#0f172a',
              'text-outline-color': '#ffffff',
              'text-outline-width': 2,
              'text-valign': 'bottom',
              'text-margin-y': 6,
              'width': 36,
              'height': 36,
              'border-width': 2,
              'border-color': '#1c2d52',
              'background-color': (ele) => typeColors[ele.data('type')] || '#06b6d4',
              'background-opacity': 0.8,
            }
          },
          {
            selector: 'node[type="suspect"]',
            style: {
              'shape': 'diamond',
              'width': 40,
              'height': 40,
              'border-color': '#f43f5e',
              'border-width': 3,
            }
          },
          {
            selector: 'node[type="crypto"]',
            style: { 'shape': 'hexagon' }
          },
          {
            selector: 'edge',
            style: {
              'width': 1.5,
              'line-color': '#1c2d52',
              'target-arrow-color': '#06b6d4',
              'target-arrow-shape': 'triangle',
              'curve-style': 'bezier',
              'opacity': 0.6,
              'label': 'data(label)',
              'font-size': '8px',
              'font-family': 'JetBrains Mono, monospace',
              'color': '#475569',
              'text-rotation': 'autorotate',
              'text-margin-y': -8,
            }
          },
          {
            selector: ':selected',
            style: {
              'border-color': '#06b6d4',
              'border-width': 4,
              'background-opacity': 1,
            }
          }
        ],
        layout: { name: layout, animate: true, animationDuration: 500, nodeRepulsion: () => 8000, idealEdgeLength: () => 100 },
        minZoom: 0.3,
        maxZoom: 3,
      });

      cy.on('tap', 'node', (evt) => {
        const node = evt.target;
        setSelectedNode({ id: node.id(), label: node.data('label'), type: node.data('type'), risk: node.data('risk') });
        loadNodeDetail(node.id());
      });

      cy.on('tap', (evt) => {
        if (evt.target === cy) {
          setSelectedNode(null);
          setNodeDetail(null);
        }
      });

      if (cancelled) {
        cy.destroy();
        return;
      }
      cyRef.current = cy;
    };

    initGraph();
    return () => {
      cancelled = true;
      if (cy) cy.destroy();
      cyRef.current = null;
    };
  }, [layout]);

  const changeLayout = (name) => setLayout(name);

  return (
    <div className="p-6 space-y-4 max-w-7xl mx-auto">
      {/* Banner */}
      <div className="glass-card rounded-xl p-5 border-l-4 border-cyan-500 animate-fade-in-up">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
              <Share2 className="w-5 h-5 text-cyan-400" />
              Trafficking Network Analysis
            </h2>
            <p className="text-xs text-slate-400 mt-1 font-mono">Interactive Graph &bull; Suspects &bull; Channels &bull; Marketplaces &bull; Crypto Wallets</p>
          </div>
          <div className="flex items-center gap-2">
            {['cose', 'breadthfirst', 'circle', 'grid'].map(l => (
              <button key={l} onClick={() => changeLayout(l)}
                className={`px-2.5 py-1 rounded-lg text-[10px] font-mono font-bold border transition-all ${layout === l ? 'bg-cyan-500/15 text-cyan-300 border-cyan-500/40' : 'bg-[#14203b] text-slate-400 border-[#1c2d52] hover:text-slate-200'}`}>
                {l.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 flex-wrap text-[10px] font-mono">
        {[
          { label: 'Suspect', color: 'bg-rose-500', shape: '◆' },
          { label: 'Telegram', color: 'bg-blue-500', shape: '●' },
          { label: 'Dark Web', color: 'bg-purple-500', shape: '●' },
          { label: 'Crypto Wallet', color: 'bg-amber-500', shape: '⬡' },
        ].map(item => (
          <span key={item.label} className="flex items-center gap-1.5 text-slate-400">
            <span className={`w-3 h-3 rounded-sm ${item.color}`} />
            {item.shape} {item.label}
          </span>
        ))}
      </div>

      {/* Graph Container */}
      <div className="glass-card rounded-xl border border-[#1c2d52] overflow-hidden relative">
        <div
          ref={containerRef}
          style={{ width: '100%', height: '560px', background: 'var(--surface-sunken)' }}
        />

        {/* An empty canvas looks broken. Say why it is empty instead - the
            graph holds correlations derived from collected records, so it
            stays blank until records arrive that share something. */}
        {nodeCount === 0 && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none px-6">
            <div className="text-center max-w-md pointer-events-auto">
              {loadError ? (
                <>
                  <p className="text-[14px] font-medium" style={{ color: 'var(--text-primary)' }}>
                    Could not load the network
                  </p>
                  <p className="text-[13px] mt-1" style={{ color: 'var(--text-muted)' }}>
                    {loadError.message}
                  </p>
                </>
              ) : (
                <>
                  <p className="text-[14px] font-medium" style={{ color: 'var(--text-primary)' }}>
                    No correlations to map yet
                  </p>
                  <p className="text-[13px] mt-1.5 leading-relaxed" style={{ color: 'var(--text-muted)' }}>
                    The graph links actors, substances and wallets that appear
                    together in collected records. It stays empty until records
                    arrive carrying an author or an extracted entity - a page
                    with neither, such as an ordinary website, produces no nodes.
                  </p>
                  <p className="text-[12px] mt-3" style={{ color: 'var(--text-muted)' }}>
                    Records collected before the graph existed are not in it.
                    Run <span className="mono">POST /api/ai/run-pipeline</span> to
                    re-analyse them and populate it.
                  </p>
                </>
              )}
            </div>
          </div>
        )}

        {/* Selected node, with the passages it was found in */}
        {selectedNode && (
          <div className="absolute bottom-4 left-4 glass-card rounded-xl p-4 border border-cyan-500/30 max-w-md max-h-[60%] overflow-y-auto animate-modal-in">
            <div className="text-xs font-bold text-slate-100 mb-1">{selectedNode.label}</div>
            <div className="text-[10px] font-mono text-slate-400 space-y-0.5">
              <div>Type: <span className="text-cyan-400">{selectedNode.type}</span></div>
              {selectedNode.risk && <div>Risk: <span className="text-rose-400 font-bold">{selectedNode.risk}/100</span></div>}
              {nodeDetail?.node && (
                <div>Seen in <span className="text-slate-200">{nodeDetail.evidence_count}</span> record
                  {nodeDetail.evidence_count === 1 ? '' : 's'} · {nodeDetail.connections?.length} connection
                  {nodeDetail.connections?.length === 1 ? '' : 's'}
                </div>
              )}
            </div>

            {detailLoading && (
              <div className="mt-3 text-[10px] font-mono text-slate-500">Loading evidence…</div>
            )}

            {nodeDetail?.error && (
              <div className="mt-3 text-[10px] font-mono text-amber-400/80">{nodeDetail.error}</div>
            )}

            {nodeDetail?.evidence?.length > 0 && (
              <div className="mt-3 space-y-2 border-t border-[#1c2d52] pt-3">
                <div className="text-[10px] font-mono uppercase tracking-wider text-slate-500">
                  Found in
                </div>
                {nodeDetail.evidence.map((ev) => (
                  <div key={ev.record_id} className="text-[10px] font-mono space-y-1">
                    <div className="text-slate-400">
                      record {ev.record_id} · {ev.source_type} · {ev.threat_level}
                    </div>
                    <a href={ev.source_url} target="_blank" rel="noreferrer"
                       className="text-cyan-400 hover:underline break-all block">
                      {ev.source_url}
                    </a>
                    <p className="text-slate-300 leading-relaxed">
                      {ev.snippet}
                    </p>
                    {/* Said plainly, because an excerpt from the top of a
                        document is not evidence of where the term appeared. */}
                    <div className="text-slate-500">
                      {ev.is_excerpt_around_match
                        ? `matched "${ev.matched_term}" at character ${ev.found_at}`
                        : 'term not located in the stored text — showing the start of the document'}
                    </div>
                    <div className="text-slate-600 break-all">sha256 {ev.sha256}</div>
                  </div>
                ))}
              </div>
            )}

            {nodeDetail && !detailLoading && nodeDetail.evidence_count === 0 && (
              <div className="mt-3 text-[10px] font-mono text-slate-500">
                No collected record is linked to this node.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
