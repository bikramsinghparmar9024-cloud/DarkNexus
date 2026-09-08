import React, { useEffect, useRef, useState } from 'react';
import cytoscape from 'cytoscape';
import { WhyThisLink } from './WhyThisLink';

export const NetworkGraph = ({ elements, height = "500px", onNodeSelect }) => {
  const containerRef = useRef(null);
  const cyRef = useRef(null);
  const [selectedNode, setSelectedNode] = useState(null);
  const [selectedEdge, setSelectedEdge] = useState(null);

  useEffect(() => {
    if (!containerRef.current) return;

    // Destroy existing instance
    if (cyRef.current) {
      cyRef.current.destroy();
    }

    // Correlations derived from collected records. This previously fell
    // back to a fully mapped syndicate - Tariq Lahori, Jagga Majitha and
    // a cast of Tor marketplaces - whenever no elements were supplied, so
    // an empty database rendered a complete trafficking network.
    const defaultElements = elements || { nodes: [], edges: [] };

    const cy = cytoscape({
      container: containerRef.current,
      elements: defaultElements,
      style: [
        {
          selector: 'node',
          style: {
            'label': 'data(label)',
            'color': '#0f172a',
            'font-family': 'Inter, system-ui, sans-serif',
            'font-size': '9px',
            'text-valign': 'bottom',
            'text-margin-y': 8,
            'text-wrap': 'wrap',
            'text-max-width': '100px',
            'text-halign': 'center',
            'background-color': '#06b6d4',
            'border-width': 2,
            'border-color': '#22d3ee',
            'width': 40,
            'height': 40,
            'text-background-opacity': 0.85,
            'text-background-color': '#ffffff',
            'text-background-padding': '4px',
            'text-background-shape': 'roundrectangle',
            'transition-property': 'border-width, border-color, width, height',
            'transition-duration': '0.2s'
          }
        },
        {
          selector: 'node[type = "suspect"]',
          style: {
            'background-color': '#ef4444',
            'border-color': '#f87171',
            'shape': 'hexagon',
            'width': 48,
            'height': 48,
          }
        },
        {
          selector: 'node[type = "vendor"]',
          style: {
            'background-color': '#a855f7',
            'border-color': '#c084fc',
            'shape': 'round-pentagon',
            'width': 44,
            'height': 44,
          }
        },
        {
          selector: 'node[type = "channel"]',
          style: {
            'background-color': '#3b82f6',
            'border-color': '#60a5fa',
            'shape': 'ellipse'
          }
        },
        {
          selector: 'node[type = "drug"]',
          style: {
            'background-color': '#f59e0b',
            'border-color': '#fbbf24',
            'shape': 'diamond',
            'width': 44,
            'height': 44,
          }
        },
        {
          selector: 'node[type = "onion"]',
          style: {
            'background-color': '#8b5cf6',
            'border-color': '#a78bfa',
            'shape': 'round-rectangle'
          }
        },
        {
          selector: 'node[type = "wallet"]',
          style: {
            'background-color': '#10b981',
            'border-color': '#34d399',
            'shape': 'tag'
          }
        },
        // Identity link edges (dashed, glowing)
        {
          selector: 'edge[edgeType = "identity"]',
          style: {
            'width': 3,
            'line-color': '#a855f7',
            'line-style': 'dashed',
            'line-dash-pattern': [8, 4],
            'target-arrow-color': '#a855f7',
            'target-arrow-shape': 'triangle',
            'curve-style': 'bezier',
            'label': 'data(label)',
            'font-size': '8px',
            'color': '#6d28d9',
            'font-weight': 'bold',
            'text-background-color': '#ffffff',
            'text-background-opacity': 0.9,
            'text-background-padding': '3px',
          }
        },
        // Default edge
        {
          selector: 'edge',
          style: {
            'width': (ele) => {
              const conf = ele.data('confidence') || 50;
              return Math.max(1.5, conf / 25);
            },
            'line-color': (ele) => {
              const conf = ele.data('confidence') || 50;
              if (conf >= 80) return '#22d3ee';
              if (conf >= 60) return '#3b82f6';
              if (conf >= 40) return '#64748b';
              return '#334155';
            },
            'line-opacity': (ele) => {
              const conf = ele.data('confidence') || 50;
              return Math.max(0.4, conf / 100);
            },
            'target-arrow-color': '#06b6d4',
            'target-arrow-shape': 'triangle',
            'curve-style': 'bezier',
            'label': 'data(label)',
            'font-size': '8px',
            'color': '#475569',
            'text-background-color': '#ffffff',
            'text-background-opacity': 0.9,
            'text-background-padding': '2px',
            'text-rotation': 'autorotate'
          }
        },
        {
          selector: ':selected',
          style: {
            'border-width': 4,
            'border-color': '#38bdf8',
            'line-color': '#38bdf8',
          }
        },
        {
          selector: 'node:active',
          style: {
            'overlay-opacity': 0,
          }
        },
      ],
      layout: {
        name: 'cose',
        animate: true,
        animationDuration: 800,
        padding: 50,
        nodeRepulsion: 12000,
        idealEdgeLength: 120,
        edgeElasticity: 100,
        gravity: 0.3,
        randomize: false,
      }
    });

    // Node click handler
    cy.on('tap', 'node', (evt) => {
      const nodeData = evt.target.data();
      setSelectedNode(nodeData);
      setSelectedEdge(null);
      if (onNodeSelect) onNodeSelect(nodeData);
    });

    // Edge click handler - opens "Why This Link?"
    cy.on('tap', 'edge', (evt) => {
      const edgeData = evt.target.data();
      setSelectedEdge({
        sourceId: edgeData.source,
        targetId: edgeData.target,
        sourceName: cy.$(`#${edgeData.source}`).data('label')?.split('\n')[0] || edgeData.source,
        targetName: cy.$(`#${edgeData.target}`).data('label')?.split('\n')[0] || edgeData.target,
        label: edgeData.label,
        confidence: edgeData.confidence,
      });
      setSelectedNode(null);
    });

    // Background click to deselect
    cy.on('tap', (evt) => {
      if (evt.target === cy) {
        setSelectedNode(null);
      }
    });

    cyRef.current = cy;

    return () => {
      if (cyRef.current) {
        cyRef.current.destroy();
        // Leaving the ref pointing at a destroyed instance lets the toolbar
        // callbacks below operate on it, which throws inside cytoscape.
        cyRef.current = null;
      }
    };
  }, [elements]);

  const fitGraph = () => {
    if (cyRef.current) cyRef.current.fit(undefined, 50);
  };

  const relayout = (name) => {
    if (cyRef.current) {
      cyRef.current.layout({
        name: name || 'cose',
        animate: true,
        animationDuration: 600,
        padding: 50,
        nodeRepulsion: 12000,
      }).run();
    }
  };

  return (
    <>
      <div className="relative w-full rounded-2xl overflow-hidden glass-card border border-[#1c2d52]">
        {/* Graph Control Bar */}
        <div className="absolute top-3 right-3 z-10 flex gap-2">
          <button
            onClick={fitGraph}
            className="px-2.5 py-1.5 text-[10px] font-mono rounded-lg bg-[#14203b]/90 hover:bg-cyan-500/20 text-slate-300 border border-[#1c2d52] transition-colors backdrop-blur-sm"
          >
            Center & Fit
          </button>
          <button
            onClick={() => relayout('cose')}
            className="px-2.5 py-1.5 text-[10px] font-mono rounded-lg bg-[#14203b]/90 hover:bg-cyan-500/20 text-slate-300 border border-[#1c2d52] transition-colors backdrop-blur-sm"
          >
            Physics Layout
          </button>
          <button
            onClick={() => relayout('breadthfirst')}
            className="px-2.5 py-1.5 text-[10px] font-mono rounded-lg bg-[#14203b]/90 hover:bg-cyan-500/20 text-slate-300 border border-[#1c2d52] transition-colors backdrop-blur-sm"
          >
            Hierarchy
          </button>
        </div>

        {/* Legend */}
        <div className="absolute top-3 left-3 z-10 glass-card rounded-lg p-2.5 border border-[#1c2d52] backdrop-blur-sm">
          <div className="text-[9px] font-mono text-slate-500 mb-1.5">NODE LEGEND</div>
          <div className="flex flex-wrap gap-x-3 gap-y-1">
            {[
              { color: 'bg-red-500', label: 'Suspect' },
              { color: 'bg-purple-500', label: 'Tor Vendor' },
              { color: 'bg-blue-500', label: 'Channel' },
              { color: 'bg-amber-500', label: 'Drug' },
              { color: 'bg-violet-500', label: 'Onion' },
              { color: 'bg-emerald-500', label: 'Wallet' },
            ].map(({ color, label }) => (
              <div key={label} className="flex items-center gap-1">
                <span className={`w-2 h-2 rounded-sm ${color}`} />
                <span className="text-[8px] font-mono text-slate-400">{label}</span>
              </div>
            ))}
          </div>
          <div className="text-[8px] font-mono text-cyan-400 mt-1.5 border-t border-[#1c2d52] pt-1.5">
            💡 Click any edge to see "Why This Link?"
          </div>
        </div>

        {/* Selected Node Inspector */}
        {selectedNode && (
          <div className="absolute bottom-3 left-3 z-10 max-w-sm glass-card p-3.5 rounded-xl border border-cyan-500/30 text-xs animate-fade-in-up">
            <div className="font-mono font-bold text-cyan-400">{selectedNode.label?.split('\n')[0]}</div>
            <div className="text-slate-400 mt-1">
              Type: <span className="text-slate-200 capitalize">{selectedNode.type}</span>
            </div>
            {selectedNode.threat && (
              <div className="text-slate-400">
                Threat: <span className={`font-bold ${
                  selectedNode.threat === 'SEVERE' ? 'text-rose-400' :
                  selectedNode.threat === 'HIGH' ? 'text-amber-400' : 'text-yellow-400'
                }`}>{selectedNode.threat}</span>
              </div>
            )}
          </div>
        )}

        {/* Cytoscape Container */}
        <div
          ref={containerRef}
          style={{
            width: '100%',
            height,
            background: 'var(--surface-sunken)',
            borderRadius: 10,
          }}
        />
      </div>

      {/* Why This Link? Panel */}
      {selectedEdge && (
        <WhyThisLink
          sourceId={selectedEdge.sourceId}
          targetId={selectedEdge.targetId}
          sourceName={selectedEdge.sourceName}
          targetName={selectedEdge.targetName}
          onClose={() => setSelectedEdge(null)}
        />
      )}
    </>
  );
};
