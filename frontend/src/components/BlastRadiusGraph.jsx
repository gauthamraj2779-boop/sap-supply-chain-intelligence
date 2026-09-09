import { useEffect, useRef, useState, useCallback } from 'react';
import cytoscape from 'cytoscape';
import coseBilkent from 'cytoscape-cose-bilkent';
import { enrichNodes, enrichEdges } from '../utils/graphLayout';

cytoscape.use(coseBilkent);

// Cytoscape stylesheet tuned for the light editorial theme
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
        'transition-property': 'opacity, border-width, border-color',
        'transition-duration': '200ms',
      },
    },
    {
      selector: 'node:selected, node.selected',
      style: {
        'border-width': 3,
        'border-color': '#0d6270',
      },
    },
    {
      selector: 'node.dimmed',
      style: { 'opacity': 0.25 },
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
        'opacity': 0.8,
        'transition-property': 'opacity, line-color, width',
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

// Node colors for the light theme
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

const LEGEND_ITEMS = [
  { label: 'Supplier',  color: '#b8440a' },
  { label: 'Material',  color: '#6b6560' },
  { label: 'Plant',     color: '#1a5276' },
  { label: 'Order',     color: '#0d6270' },
  { label: 'Customer',  color: '#2c5f2e' },
];

function enrichForLightTheme(nodes) {
  return nodes.map(n => {
    const type = n.data.type || 'Material';
    const color = TYPE_COLORS[type] || '#6b6560';
    const exposure = n.data.exposure || 0;
    const size = Math.max(22, Math.min(54, 22 + (exposure / 53600000) * 32));
    const raw = n.data.label || '';
    const shortLabel = raw.split('\n')[0].split('(')[0].trim().substring(0, 16);
    return { ...n, data: { ...n.data, color, size, shortLabel } };
  });
}

export default function BlastRadiusGraph({ data, onNodeSelect, selectedNodeId }) {
  const containerRef = useRef(null);
  const cyRef = useRef(null);
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
        animationDuration: 600,
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

    cy.on('tap', 'node', (evt) => {
      const node = evt.target;
      cy.elements().removeClass('selected dimmed highlighted');
      const neighborhood = node.neighborhood().add(node);
      neighborhood.addClass('selected');
      cy.elements().not(neighborhood).addClass('dimmed');
      node.connectedEdges().addClass('highlighted');
      onNodeSelect && onNodeSelect(node.data());
    });

    cy.on('tap', (evt) => {
      if (evt.target === cy) {
        cy.elements().removeClass('selected dimmed highlighted');
        onNodeSelect && onNodeSelect(null);
      }
    });

    return () => { cy.destroy(); cyRef.current = null; };
  }, [data]);

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
            {nodeCount} nodes · {edgeCount} edges — powered by Cytoscape.js
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
