export function getGraphLayoutOptions() {
  return {
    name: 'cose-bilkent',
    quality: 'default',
    nodeDimensionsIncludeLabels: true,
    refresh: 30,
    fit: true,
    padding: 40,
    randomize: false,
    nodeRepulsion: 8000,
    idealEdgeLength: 120,
    edgeElasticity: 0.45,
    nestingFactor: 0.1,
    gravity: 0.25,
    numIter: 2500,
    tile: true,
    animate: 'end',
    animationDuration: 800,
    tilingPaddingVertical: 10,
    tilingPaddingHorizontal: 10,
    gravityRangeCompound: 1.5,
    gravityCompound: 1.0,
    gravityRange: 3.8,
  };
}

export const NODE_TYPE_CONFIG = {
  Supplier:        { color: '#ef4444', icon: '🏭', layer: 0 },
  PurchaseOrder:   { color: '#f97316', icon: '📄', layer: 1 },
  Material:        { color: '#eab308', icon: '🔩', layer: 2 },
  Plant:           { color: '#3b82f6', icon: '🏗️', layer: 3 },
  ProductionOrder: { color: '#8b5cf6', icon: '⚙️', layer: 4 },
  SalesOrder:      { color: '#06b6d4', icon: '🛒', layer: 5 },
  Delivery:        { color: '#ec4899', icon: '🚚', layer: 6 },
  Customer:        { color: '#10b981', icon: '🏢', layer: 7 },
};

export const SEVERITY_COLORS = {
  critical: '#ef4444',
  high:     '#f97316',
  medium:   '#eab308',
  low:      '#22c55e',
  none:     '#6b7280',
};

export function buildCytoscapeStylesheet() {
  return [
    {
      selector: 'node',
      style: {
        'background-color': 'data(color)',
        'label': 'data(label)',
        'color': '#ffffff',
        'text-valign': 'center',
        'text-halign': 'center',
        'font-size': '10px',
        'font-family': 'Inter, system-ui, sans-serif',
        'font-weight': '600',
        'text-wrap': 'wrap',
        'text-max-width': '80px',
        'width': 'data(size)',
        'height': 'data(size)',
        'border-width': 2,
        'border-color': '#ffffff33',
        'text-outline-color': '#00000088',
        'text-outline-width': 1,
        'transition-property': 'background-color, border-color, border-width, opacity, width, height',
        'transition-duration': '300ms',
      },
    },
    {
      selector: 'node:selected',
      style: {
        'border-width': 4,
        'border-color': '#ffffff',
        'box-shadow': '0 0 20px rgba(255,255,255,0.5)',
      },
    },
    {
      selector: 'node.highlighted',
      style: {
        'border-width': 3,
        'border-color': '#facc15',
        'opacity': 1,
      },
    },
    {
      selector: 'node.dimmed',
      style: { 'opacity': 0.25 },
    },
    {
      selector: 'node.animating',
      style: {
        'border-color': '#facc15',
        'border-width': 4,
      },
    },
    {
      selector: 'edge',
      style: {
        'width': 2,
        'line-color': 'data(edgeColor)',
        'target-arrow-color': 'data(edgeColor)',
        'target-arrow-shape': 'triangle',
        'curve-style': 'bezier',
        'label': 'data(label)',
        'font-size': '8px',
        'color': '#94a3b8',
        'font-family': 'Inter, system-ui, sans-serif',
        'text-rotation': 'autorotate',
        'text-background-color': '#0f172a',
        'text-background-opacity': 0.8,
        'text-background-padding': '2px',
        'opacity': 0.7,
        'transition-property': 'opacity, line-color, width',
        'transition-duration': '300ms',
      },
    },
    {
      selector: 'edge.highlighted',
      style: { 'opacity': 1, 'width': 3 },
    },
    {
      selector: 'edge.dimmed',
      style: { 'opacity': 0.1 },
    },
  ];
}

export function enrichNodes(nodes) {
  return nodes.map(node => {
    const type = node.data.type || 'Material';
    const config = NODE_TYPE_CONFIG[type] || NODE_TYPE_CONFIG.Material;
    const exposure = node.data.exposure || 0;
    const size = Math.max(40, Math.min(90, 40 + (exposure / 53600000) * 50));
    return {
      ...node,
      data: {
        ...node.data,
        color: config.color,
        size,
        icon: config.icon,
      },
    };
  });
}

export function enrichEdges(edges) {
  return edges.map(edge => ({
    ...edge,
    data: {
      ...edge.data,
      edgeColor: SEVERITY_COLORS[edge.data.severity] || SEVERITY_COLORS.none,
    },
  }));
}
