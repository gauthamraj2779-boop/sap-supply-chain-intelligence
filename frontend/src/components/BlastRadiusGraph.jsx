import { useEffect, useRef, useState } from 'react';
import cytoscape from 'cytoscape';
import coseBilkent from 'cytoscape-cose-bilkent';
import { usePrefersReducedMotion } from '../utils/useAnimatedNumber';

cytoscape.use(coseBilkent);

// Node colors for the light editorial theme
const TYPE_COLORS = {
  Supplier:        '#b8440a',
  PurchaseOrder:   '#8b7355',
  Material:        '#6b6560',
  Plant:           '#1a5276',
  ProductionOrder: '#2e7d5e',
  SalesOrder:      '#0d6270',
  Delivery:        '#6d4c8e',
  Customer:        '#2c5f2e',
};

// Logical hop levels across the 8-hop supply chain
const TYPE_HOPS = {
  Supplier:        0,
  PurchaseOrder:   1,
  Material:        2,
  Plant:           3,
  ProductionOrder: 4,
  SalesOrder:      5,
  Delivery:        6,
  Customer:        7,
};

const LEGEND_ITEMS = [
  { label: 'Supplier',  color: '#b8440a' },
  { label: 'Material',  color: '#6b6560' },
  { label: 'Plant',     color: '#1a5276' },
  { label: 'Order',     color: '#0d6270' },
  { label: 'Customer',  color: '#2c5f2e' },
];

function buildStylesheet() {
  return [
    {
      selector: 'node',
      style: {
        'background-color': 'data(color)',
        'label': 'data(shortLabel)',
        'color': '#1a1715',
        'text-valign': 'bottom',
        'text-halign': 'center',
        'font-size': '9px',
        'font-family': '"IBM Plex Sans", system-ui, sans-serif',
        'font-weight': '500',
        'text-wrap': 'wrap',
        'text-max-width': '72px',
        'width': 'data(size)',
        'height': 'data(size)',
        'border-width': 1.5,
        'border-color': '#ccc9c1',
        'text-margin-y': 4,
        'opacity': 0, // Starts at 0 for real Cytoscape .animate() cascade
        'transition-property': 'border-width, border-color',
        'transition-duration': '200ms',
      },
    },
    {
      selector: 'node:selected, node.selected',
      style: {
        'border-width': 3.5,
        'border-color': '#0d6270',
        'opacity': 1,
      },
    },
    {
      selector: 'node.dimmed',
      style: { 'opacity': 0.2 },
    },
    {
      selector: 'edge',
      style: {
        'width': 1.5,
        'line-color': '#ccc9c1',
        'target-arrow-color': '#ccc9c1',
        'target-arrow-shape': 'vee',
        'curve-style': 'bezier',
        'label': 'data(label)',
        'font-size': '8px',
        'color': '#9b968f',
        'font-family': '"IBM Plex Mono", monospace',
        'text-rotation': 'autorotate',
        'text-background-color': '#f2f0eb',
        'text-background-opacity': 0.9,
        'text-background-padding': '2px',
        'opacity': 0, // Starts at 0 for real Cytoscape .animate() cascade
        'transition-property': 'line-color, width',
        'transition-duration': '200ms',
      },
    },
    {
      selector: 'edge.highlighted',
      style: { 'opacity': 1, 'line-color': '#0d6270', 'target-arrow-color': '#0d6270', 'width': 2 },
    },
    {
      selector: 'edge.dimmed',
      style: { 'opacity': 0.1 },
    },
  ];
}

function enrichForLightTheme(nodes) {
  return nodes.map(n => {
    const type = n.data.type || 'Material';
    const color = TYPE_COLORS[type] || '#6b6560';
    const exposure = n.data.exposure || 0;
    const size = Math.max(22, Math.min(54, 22 + (exposure / 53600000) * 32));
    const raw = n.data.label || '';
    const shortLabel = raw.split('\n')[0].split('(')[0].trim().substring(0, 16);
    const hop = TYPE_HOPS[type] ?? 0;
    return { ...n, data: { ...n.data, color, size, shortLabel, hop } };
  });
}

export default function BlastRadiusGraph({ data, onNodeSelect, selectedNodeId }) {
  const containerRef = useRef(null);
  const cyRef = useRef(null);
  const prefersReduced = usePrefersReducedMotion();
  const [nodeCount, setNodeCount] = useState(0);
  const [edgeCount, setEdgeCount] = useState(0);

  useEffect(() => {
    if (!data?.blast_radius || !containerRef.current) return;
    if (cyRef.current) { cyRef.current.destroy(); }

    const enrichedNodes = enrichForLightTheme(data.blast_radius.nodes);
    const enrichedEdges = data.blast_radius.edges.map(e => ({
      ...e, data: { ...e.data }
    }));

    const cy = cytoscape({
      container: containerRef.current,
      elements: [...enrichedNodes, ...enrichedEdges],
      style: buildStylesheet(),
      layout: {
        name: 'cose-bilkent',
        quality: 'default',
        nodeDimensionsIncludeLabels: true,
        fit: true,
        padding: 40,
        randomize: false,
        nodeRepulsion: 6000,
        idealEdgeLength: 110,
        animate: 'end',
        animationDuration: 500,
      },
      userZoomingEnabled: true,
      userPanningEnabled: true,
      boxSelectionEnabled: false,
      minZoom: 0.4,
      maxZoom: 3,
    });

    cyRef.current = cy;
    setNodeCount(cy.nodes().length);
    setEdgeCount(cy.edges().length);

    const timeouts = [];

    // Hop-by-hop draw-in cascade using real Cytoscape .animate()
    const runCascadeAnimation = () => {
      if (prefersReduced) {
        // Immediate reveal for reduced motion
        cy.nodes().style('opacity', 1);
        cy.edges().style('opacity', 0.8);
        return;
      }

      // Group nodes by hop level
      const maxHop = 7;
      for (let hop = 0; hop <= maxHop; hop++) {
        const hopNodes = cy.nodes().filter(n => n.data('hop') === hop);
        const hopEdges = cy.edges().filter(e => {
          const targetNode = e.target();
          return targetNode.data('hop') === hop;
        });

        const delay = hop * 140;

        const tid = setTimeout(() => {
          if (!cyRef.current || cy.destroyed()) return;

          hopNodes.animate(
            { style: { opacity: 1 } },
            { duration: 320, easing: 'ease-out-quad' }
          );

          hopEdges.animate(
            { style: { opacity: 0.8 } },
            { duration: 320, easing: 'ease-out-quad' }
          );
        }, delay);
        timeouts.push(tid);
      }
    };

    // Trigger cascade once layout stops
    cy.one('layoutstop', runCascadeAnimation);

    // Fallback trigger if layout completed synchronously
    const fallbackTimer = setTimeout(() => {
      if (!cy.destroyed() && cy.nodes().some(n => n.style('opacity') === '0')) {
        runCascadeAnimation();
      }
    }, 600);
    timeouts.push(fallbackTimer);

    // Node click handler: highlight neighborhood and dim rest
    cy.on('tap', 'node', (evt) => {
      const node = evt.target;
      cy.elements().removeClass('selected dimmed highlighted');
      const neighborhood = node.neighborhood().add(node);
      neighborhood.addClass('selected');
      cy.elements().not(neighborhood).addClass('dimmed');
      node.connectedEdges().addClass('highlighted');
      onNodeSelect && onNodeSelect(node.data());
    });

    // Background click handler: clear selection
    cy.on('tap', (evt) => {
      if (evt.target === cy) {
        cy.elements().removeClass('selected dimmed highlighted');
        onNodeSelect && onNodeSelect(null);
      }
    });

    return () => {
      timeouts.forEach(clearTimeout);
      cy.destroy();
      cyRef.current = null;
    };
  }, [data, prefersReduced]);

  // Sync external selectedNodeId (from inspector or table)
  useEffect(() => {
    if (!cyRef.current || !selectedNodeId) return;
    const node = cyRef.current.getElementById(selectedNodeId);
    if (!node.length) return;
    cyRef.current.elements().removeClass('selected dimmed highlighted');
    const neighborhood = node.neighborhood().add(node);
    neighborhood.addClass('selected');
    cyRef.current.elements().not(neighborhood).addClass('dimmed');
    node.connectedEdges().addClass('highlighted');
  }, [selectedNodeId]);

  const handleZoomIn  = () => cyRef.current?.zoom({ level: cyRef.current.zoom() * 1.3, renderedPosition: { x: cyRef.current.width() / 2, y: cyRef.current.height() / 2 } });
  const handleZoomOut = () => cyRef.current?.zoom({ level: cyRef.current.zoom() * 0.75, renderedPosition: { x: cyRef.current.width() / 2, y: cyRef.current.height() / 2 } });
  const handleFit     = () => cyRef.current?.fit(undefined, 30);

  return (
    <div className="graph-section">
      <div className="graph-card">
        <div className="graph-card-head">
          <span className="graph-card-label">
            {nodeCount} nodes · {edgeCount} edges — Cytoscape.js hop-by-hop traversal
          </span>
          <div className="graph-legend">
            {LEGEND_ITEMS.map(l => (
              <div key={l.label} className="gl-item">
                <div className="gl-dot" style={{ background: l.color }} />
                {l.label}
              </div>
            ))}
          </div>
        </div>
        <div className="graph-canvas-wrap">
          <div ref={containerRef} className="graph-canvas" />
          <div className="graph-zoom-controls">
            <button className="graph-zoom-btn" onClick={handleZoomIn}  title="Zoom in">+</button>
            <button className="graph-zoom-btn" onClick={handleZoomOut} title="Zoom out">−</button>
            <button className="graph-zoom-btn" onClick={handleFit}     title="Fit">⊡</button>
          </div>
        </div>
      </div>
    </div>
  );
}
