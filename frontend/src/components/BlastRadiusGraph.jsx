import { useEffect, useRef, useState } from 'react';
import cytoscape from 'cytoscape';
import { usePrefersReducedMotion } from '../utils/useAnimatedNumber';

// Exact 10 nodes matching the reference mockup and screenshot
const GRAPH_NODES = [
  { id: 'sup-apex',   label: 'Apex Microelectronics', type: 'Supplier',        color: '#b8440a', size: 22, hopOrder: 0, x: 80,  y: 75,  valign: 'top',    halign: 'center', marginY: -8 },
  { id: 'po-4500',    label: 'PO #4500-12',           type: 'PurchaseOrder',   color: '#595e60', size: 14, hopOrder: 1, x: 215, y: 135, valign: 'top',    halign: 'right',  marginY: -6 },
  { id: 'mat-mcu32',  label: 'MCU-32',                type: 'Material',        color: '#a6833b', size: 16, hopOrder: 2, x: 230, y: 225, valign: 'bottom', halign: 'center', marginY: 6 },
  { id: 'pl-1010',    label: 'Plant 1010, Hamburg',   type: 'Plant',           color: '#2f3e4e', size: 18, hopOrder: 3, x: 360, y: 75,  valign: 'top',    halign: 'center', marginY: -8 },
  { id: 'prod-9001',  label: 'Prod. order #9001',     type: 'ProductionOrder', color: '#595e60', size: 15, hopOrder: 4, x: 495, y: 140, valign: 'bottom', halign: 'center', marginY: 6 },
  { id: 'so-4502',    label: 'Sales order #4502',     type: 'SalesOrder',      color: '#595e60', size: 15, hopOrder: 5, x: 625, y: 75,  valign: 'top',    halign: 'center', marginY: -8 },
  { id: 'cus-boeing', label: 'Boeing',                type: 'Customer',        color: '#2c5f2e', size: 18, hopOrder: 6, x: 760, y: 75,  valign: 'top',    halign: 'center', marginY: -8 },
  { id: 'so-4508',    label: 'Sales order #4508',     type: 'SalesOrder',      color: '#595e60', size: 15, hopOrder: 5, x: 635, y: 225, valign: 'bottom', halign: 'center', marginY: 6 },
  { id: 'cus-airbus', label: 'Airbus',                type: 'Customer',        color: '#2c5f2e', size: 18, hopOrder: 6, x: 760, y: 165, valign: 'bottom', halign: 'center', marginY: 6 },
  { id: 'gap',        label: 'gap',                   type: 'Supplier',        color: '#b8440a', size: 12, hopOrder: 7, x: 810, y: 125, valign: 'top',    halign: 'center', marginY: -7 },
];

// Straight edge connections matching screenshot topology
const GRAPH_EDGES = [
  { id: 'e1',  source: 'sup-apex',   target: 'po-4500',    hopOrder: 1 },
  { id: 'e2',  source: 'po-4500',    target: 'mat-mcu32',  hopOrder: 2 },
  { id: 'e3',  source: 'mat-mcu32',  target: 'pl-1010',    hopOrder: 3 },
  { id: 'e4',  source: 'pl-1010',    target: 'prod-9001',  hopOrder: 4 },
  { id: 'e5',  source: 'prod-9001',  target: 'so-4502',    hopOrder: 5 },
  { id: 'e6',  source: 'so-4502',    target: 'cus-boeing', hopOrder: 6 },
  { id: 'e7',  source: 'prod-9001',  target: 'so-4508',    hopOrder: 5 },
  { id: 'e8',  source: 'so-4508',    target: 'cus-airbus', hopOrder: 6 },
  { id: 'e9',  source: 'cus-boeing', target: 'gap',        hopOrder: 7 },
  { id: 'e10', source: 'cus-airbus', target: 'gap',        hopOrder: 7 },
];

const LEGEND_ITEMS = [
  { label: 'Supplier',  color: '#b8440a' },
  { label: 'Material',  color: '#a6833b' },
  { label: 'Plant',     color: '#2f3e4e' },
  { label: 'Order',     color: '#595e60' },
  { label: 'Customer',  color: '#2c5f2e' },
];

function buildStylesheet() {
  return [
    {
      selector: 'node',
      style: {
        'background-color': 'data(color)',
        'label': 'data(label)',
        'color': '#4a4640',
        'text-valign': 'data(valign)',
        'text-halign': 'data(halign)',
        'text-margin-y': 'data(marginY)',
        'font-size': '10px',
        'font-family': '"IBM Plex Sans", system-ui, sans-serif',
        'font-weight': 400,
        'width': 'data(size)',
        'height': 'data(size)',
        'border-width': 1.5,
        'border-color': '#ccc9c1',
        'opacity': 0, // Starts at 0 for Cytoscape .animate() reveal
        'transition-property': 'border-width, border-color, opacity',
        'transition-duration': '220ms',
      },
    },
    {
      selector: 'node:selected, node.selected',
      style: {
        'border-width': 3,
        'border-color': '#0d6270',
        'opacity': 1,
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
        'curve-style': 'straight',
        'opacity': 0, // Starts at 0 for Cytoscape .animate() reveal
        'transition-property': 'line-color, opacity, width',
        'transition-duration': '220ms',
      },
    },
    {
      selector: 'edge.highlighted',
      style: { 'opacity': 1, 'line-color': '#0d6270', 'width': 2 },
    },
    {
      selector: 'edge.dimmed',
      style: { 'opacity': 0.1 },
    },
  ];
}

export default function BlastRadiusGraph({ onSelectNode, selectedNodeId = 'sup-apex', isActive = true }) {
  const containerRef = useRef(null);
  const cyRef = useRef(null);
  const prefersReduced = usePrefersReducedMotion();

  // Initialize Cytoscape instance once
  useEffect(() => {
    if (!containerRef.current) return;
    if (cyRef.current) cyRef.current.destroy();

    const elements = [
      ...GRAPH_NODES.map(n => ({
        data: {
          id: n.id,
          label: n.label,
          color: n.color,
          size: n.size,
          hopOrder: n.hopOrder,
          valign: n.valign,
          halign: n.halign,
          marginY: n.marginY,
        },
        position: { x: n.x, y: n.y },
      })),
      ...GRAPH_EDGES.map(e => ({
        data: {
          id: e.id,
          source: e.source,
          target: e.target,
          hopOrder: e.hopOrder,
        },
      })),
    ];

    const cy = cytoscape({
      container: containerRef.current,
      elements,
      style: buildStylesheet(),
      layout: {
        name: 'preset',
        fit: true,
        padding: 30,
      },
      userZoomingEnabled: true,
      userPanningEnabled: true,
      boxSelectionEnabled: false,
      minZoom: 0.5,
      maxZoom: 2.5,
    });

    cyRef.current = cy;

    // Node click handler
    cy.on('tap', 'node', (evt) => {
      const node = evt.target;
      cy.elements().removeClass('selected dimmed highlighted');
      const neighborhood = node.neighborhood().add(node);
      neighborhood.addClass('selected');
      cy.elements().not(neighborhood).addClass('dimmed');
      node.connectedEdges().addClass('highlighted');
      onSelectNode && onSelectNode(node.id());
    });

    // Background click handler: select default supplier
    cy.on('tap', (evt) => {
      if (evt.target === cy) {
        cy.elements().removeClass('selected dimmed highlighted');
        const defaultNode = cy.getElementById('sup-apex');
        if (defaultNode.length) {
          const neighborhood = defaultNode.neighborhood().add(defaultNode);
          neighborhood.addClass('selected');
          cy.elements().not(neighborhood).addClass('dimmed');
          defaultNode.connectedEdges().addClass('highlighted');
        }
        onSelectNode && onSelectNode('sup-apex');
      }
    });

    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, []);

  // Hop-by-hop draw-in cascade: replays whenever the panel is active (per notes)
  useEffect(() => {
    if (!cyRef.current || !isActive) return;

    const cy = cyRef.current;
    const timeouts = [];

    // Ensure fit is applied properly
    cy.fit(undefined, 30);

    if (prefersReduced) {
      cy.elements().style('opacity', 1);
      return;
    }

    // Start everything hidden
    cy.elements().style('opacity', 0);

    // Group elements by hopOrder
    const byHop = {};
    cy.elements().forEach(el => {
      const hop = el.data('hopOrder') ?? 0;
      if (!byHop[hop]) byHop[hop] = [];
      byHop[hop].push(el);
    });

    // Animate hop by hop
    Object.entries(byHop).forEach(([hop, elements]) => {
      const tid = setTimeout(() => {
        if (!cyRef.current || cyRef.current.destroyed()) return;
        cy.collection(elements).animate(
          { style: { opacity: 1 } },
          { duration: 300, easing: 'ease-out' }
        );
      }, Number(hop) * 140);
      timeouts.push(tid);
    });

    return () => {
      timeouts.forEach(clearTimeout);
    };
  }, [isActive, prefersReduced]);

  // Synchronize selection with selectedNodeId
  useEffect(() => {
    if (!cyRef.current || !selectedNodeId) return;
    const cy = cyRef.current;
    const node = cy.getElementById(selectedNodeId);
    if (!node.length) return;

    cy.elements().removeClass('selected dimmed highlighted');
    const neighborhood = node.neighborhood().add(node);
    neighborhood.addClass('selected');
    cy.elements().not(neighborhood).addClass('dimmed');
    node.connectedEdges().addClass('highlighted');
  }, [selectedNodeId]);

  const handleZoomIn  = () => cyRef.current?.zoom({ level: cyRef.current.zoom() * 1.25, renderedPosition: { x: cyRef.current.width() / 2, y: cyRef.current.height() / 2 } });
  const handleZoomOut = () => cyRef.current?.zoom({ level: cyRef.current.zoom() * 0.8, renderedPosition: { x: cyRef.current.width() / 2, y: cyRef.current.height() / 2 } });
  const handleFit     = () => cyRef.current?.fit(undefined, 30);

  return (
    <div className="graph-section">
      <div className="graph-card">
        <div className="graph-card-head">
          <span className="graph-card-label">
            12 nodes · 11 edges · rendered with Cytoscape in the live build
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
        <div className="graph-canvas-wrap" style={{ height: 260 }}>
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
