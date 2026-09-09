import { useEffect, useRef, useState, useMemo } from 'react';
import cytoscape from 'cytoscape';
import { usePrefersReducedMotion } from '../utils/useAnimatedNumber';
import { NODE_COLORS, SEVERITY_COLORS, buildStylesheet, buildLayout } from '../utils/graphLayout';

/**
 * Interactive blast radius over the live graph.
 *
 * Two things are computed from the data rather than authored:
 *  - Node size scales against the largest exposure in *this* report, so the
 *    picture stays meaningful whether the answer is $95M or $50K.
 *  - The hop-by-hop reveal is driven by real breadth-first distance from the
 *    delayed supplier, so the cascade you watch is the cascade the traversal
 *    actually walked.
 */
export default function BlastRadiusGraph({
  data,
  onNodeSelect,
  selectedNodeId,
  isActive = true,
}) {
  const containerRef = useRef(null);
  const cyRef = useRef(null);
  const [counts, setCounts] = useState({ nodes: 0, edges: 0 });
  const prefersReduced = usePrefersReducedMotion();

  const elements = useMemo(() => {
    const nodes = data?.blast_radius?.nodes ?? [];
    const edges = data?.blast_radius?.edges ?? [];
    if (nodes.length === 0) return { sized: [], edges: [], types: [], root: null, maxHop: 0 };

    const root = nodes.find((n) => n.data.type === 'Supplier')?.data.id ?? nodes[0].data.id;

    // Breadth-first distance from the supplier: the true hop number of every
    // node, used both to order the reveal and to explain the picture.
    const adjacency = new Map(nodes.map((n) => [n.data.id, []]));
    edges.forEach((e) => {
      adjacency.get(e.data.source)?.push(e.data.target);
      adjacency.get(e.data.target)?.push(e.data.source);
    });
    const hop = new Map([[root, 0]]);
    const queue = [root];
    while (queue.length) {
      const id = queue.shift();
      for (const next of adjacency.get(id) ?? []) {
        if (!hop.has(next)) {
          hop.set(next, hop.get(id) + 1);
          queue.push(next);
        }
      }
    }

    const maxExposure = Math.max(1, ...nodes.map((n) => n.data.exposure || 0));
    const sized = nodes.map((n) => {
      const type = n.data.type || 'Material';
      // Square-root scaling: area tracks exposure, so a 10x figure does not
      // produce a node 10x wider that swamps the canvas.
      const ratio = Math.sqrt((n.data.exposure || 0) / maxExposure);
      return {
        data: {
          ...n.data,
          color: NODE_COLORS[type] || NODE_COLORS.default,
          borderColor: SEVERITY_COLORS[n.data.severity] || SEVERITY_COLORS.none,
          size: Math.round(22 + ratio * 34),
          shortLabel: String(n.data.label || '').slice(0, 20),
          hopOrder: hop.get(n.data.id) ?? 0,
        },
      };
    });

    const withHops = edges.map((e) => ({
      data: {
        ...e.data,
        // An edge appears with the later of the two nodes it connects.
        hopOrder: Math.max(hop.get(e.data.source) ?? 0, hop.get(e.data.target) ?? 0),
      },
    }));

    return {
      sized,
      edges: withHops,
      root,
      maxHop: Math.max(0, ...hop.values()),
      types: [...new Set(nodes.map((n) => n.data.type))],
    };
  }, [data]);

  useEffect(() => {
    if (!containerRef.current || elements.sized.length === 0) return;
    if (cyRef.current) cyRef.current.destroy();

    const cy = cytoscape({
      container: containerRef.current,
      elements: [...elements.sized, ...elements.edges],
      style: buildStylesheet(),
      // No `layout` here on purpose: a layout passed to the constructor runs
      // before the container is measured and before styles resolve, which
      // collapses every node into a single cluster.
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

  // Hop-by-hop reveal, replayed whenever the panel becomes active.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !isActive || elements.sized.length === 0) return;

    if (prefersReduced) {
      cy.elements().style('opacity', 1);
      return;
    }

    const timeouts = [];
    cy.elements().style('opacity', 0);

    const byHop = new Map();
    cy.elements().forEach((el) => {
      const h = el.data('hopOrder') ?? 0;
      if (!byHop.has(h)) byHop.set(h, []);
      byHop.get(h).push(el);
    });

    [...byHop.keys()].sort((a, b) => a - b).forEach((h, index) => {
      timeouts.push(
        setTimeout(() => {
          if (!cyRef.current || cyRef.current.destroyed()) return;
          cy.collection(byHop.get(h)).animate(
            { style: { opacity: 1 } },
            { duration: 300, easing: 'ease-out' },
          );
        }, index * 160),
      );
    });

    return () => timeouts.forEach(clearTimeout);
  }, [elements, isActive, prefersReduced]);

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
            {counts.nodes} nodes · {counts.edges} edges · {elements.maxHop} hops deep —
            node size scales with exposure
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
            <button className="graph-zoom-btn" onClick={() => cyRef.current?.fit(undefined, 36)} title="Fit">⊡</button>
          </div>
        </div>
      </div>
    </div>
  );
}
