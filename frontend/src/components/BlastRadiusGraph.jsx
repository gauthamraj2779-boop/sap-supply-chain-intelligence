import { useEffect, useRef, useState, useMemo } from 'react';
import cytoscape from 'cytoscape';
import { NODE_COLORS, SEVERITY_COLORS, buildStylesheet, buildLayout } from '../utils/graphLayout';

/**
 * Interactive blast radius. Node size is scaled against the largest exposure in
 * *this* report rather than a fixed constant, so the visual stays meaningful
 * whether the answer is $95M or $50K. The legend lists only the node types the
 * traversal actually reached.
 */
export default function BlastRadiusGraph({ data, onNodeSelect, selectedNodeId }) {
  const containerRef = useRef(null);
  const cyRef = useRef(null);
  const [counts, setCounts] = useState({ nodes: 0, edges: 0 });

  const elements = useMemo(() => {
    const nodes = data?.blast_radius?.nodes ?? [];
    const edges = data?.blast_radius?.edges ?? [];
    const maxExposure = Math.max(1, ...nodes.map((n) => n.data.exposure || 0));

    const sized = nodes.map((n) => {
      const type = n.data.type || 'Material';
      const exposure = n.data.exposure || 0;
      // Square-root scaling: area tracks exposure, so a 10x figure does not
      // produce a node 10x wider that swamps the canvas.
      const ratio = Math.sqrt(exposure / maxExposure);
      return {
        data: {
          ...n.data,
          color: NODE_COLORS[type] || NODE_COLORS.default,
          borderColor: SEVERITY_COLORS[n.data.severity] || SEVERITY_COLORS.none,
          size: Math.round(22 + ratio * 34),
          shortLabel: String(n.data.label || '').slice(0, 20),
        },
      };
    });

    const root = nodes.find((n) => n.data.type === 'Supplier')?.data.id;
    return { sized, edges, root, types: [...new Set(nodes.map((n) => n.data.type))] };
  }, [data]);

  useEffect(() => {
    if (!containerRef.current || elements.sized.length === 0) return;
    if (cyRef.current) cyRef.current.destroy();

    const cy = cytoscape({
      container: containerRef.current,
      elements: [...elements.sized, ...elements.edges],
      style: buildStylesheet(),
      // No `layout` here on purpose. A layout passed to the constructor runs
      // before the container is measured and before styles resolve, which
      // collapses every node into a single cluster. It is run explicitly below,
      // once the element is laid out by the browser.
      userZoomingEnabled: true,
      userPanningEnabled: true,
      boxSelectionEnabled: false,
      minZoom: 0.3,
      maxZoom: 3,
    });

    cyRef.current = cy;
    setCounts({ nodes: cy.nodes().length, edges: cy.edges().length });

    cy.one('layoutstop', () => cy.fit(undefined, 36));

    const raf = requestAnimationFrame(() => {
      cy.resize();
      cy.layout(buildLayout(elements.root)).run();
    });

    // Keep the graph framed when the pane or window is resized.
    const ro = new ResizeObserver(() => {
      if (!cyRef.current) return;
      cy.resize();
      cy.fit(undefined, 36);
    });
    ro.observe(containerRef.current);

    cy.on('tap', 'node', (evt) => {
      const node = evt.target;
      cy.elements().removeClass('selected dimmed highlighted');
      const hood = node.neighborhood().add(node);
      hood.addClass('selected');
      cy.elements().not(hood).addClass('dimmed');
      node.connectedEdges().addClass('highlighted');
      onNodeSelect?.(node.data());
    });

    cy.on('tap', (evt) => {
      if (evt.target === cy) {
        cy.elements().removeClass('selected dimmed highlighted');
        onNodeSelect?.(null);
      }
    });

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      cy.destroy();
      cyRef.current = null;
    };
  }, [elements, onNodeSelect]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !selectedNodeId) return;
    const node = cy.getElementById(selectedNodeId);
    if (!node.length) return;
    cy.elements().removeClass('selected dimmed highlighted');
    const hood = node.neighborhood().add(node);
    hood.addClass('selected');
    cy.elements().not(hood).addClass('dimmed');
    node.connectedEdges().addClass('highlighted');
  }, [selectedNodeId]);

  const zoomBy = (factor) => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.zoom({
      level: cy.zoom() * factor,
      renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 },
    });
  };

  if (elements.sized.length === 0) {
    return (
      <div className="graph-section">
        <div className="graph-card">
          <div className="graph-empty">
            No downstream nodes were reached — this delay does not propagate.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="graph-section">
      <div className="graph-card">
        <div className="graph-card-head">
          <span className="graph-card-label">
            {counts.nodes} nodes · {counts.edges} edges — node size scales with exposure
          </span>
          <div className="graph-legend">
            {elements.types.map((t) => (
              <div key={t} className="gl-item">
                <div
                  className="gl-dot"
                  style={{ background: NODE_COLORS[t] || NODE_COLORS.default }}
                />
                {t}
              </div>
            ))}
          </div>
        </div>
        <div className="graph-canvas-wrap">
          <div ref={containerRef} className="graph-canvas" />
          <div className="graph-zoom-controls">
            <button className="graph-zoom-btn" onClick={() => zoomBy(1.3)} title="Zoom in">+</button>
            <button className="graph-zoom-btn" onClick={() => zoomBy(0.75)} title="Zoom out">−</button>
            <button className="graph-zoom-btn" onClick={() => cyRef.current?.fit(undefined, 30)} title="Fit">⊡</button>
          </div>
        </div>
      </div>
    </div>
  );
}
