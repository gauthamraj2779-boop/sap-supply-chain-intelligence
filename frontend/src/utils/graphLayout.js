/** Cytoscape styling for the blast radius graph. */

export const NODE_COLORS = {
  Supplier:        '#b8440a',
  PurchaseOrder:   '#8b7355',
  Material:        '#6b6560',
  Plant:           '#1a5276',
  ProductionOrder: '#2e7d5e',
  SalesOrder:      '#0d6270',
  Delivery:        '#6d4c8e',
  Customer:        '#2c5f2e',
  default:         '#6b6560',
};

/** Border colour encodes severity, so shape and colour carry different facts. */
export const SEVERITY_COLORS = {
  none:     '#ccc9c1',
  low:      '#c9b458',
  medium:   '#d18f34',
  high:     '#c2591f',
  critical: '#a02020',
};

/**
 * Layered left-to-right layout rooted at the delayed supplier.
 *
 * The blast radius is a cascade, so the picture should read as one: hop depth
 * becomes horizontal distance from the supplier. A force-directed layout hides
 * exactly the structure this view exists to show. `breadthfirst` lays out
 * top-down, so positions are transposed to run left-to-right, which suits a
 * wide canvas and keeps the supplier at the left edge where the eye starts.
 */
export function buildLayout(rootId) {
  return {
    name: 'breadthfirst',
    directed: true,
    roots: rootId ? [rootId] : undefined,
    padding: 30,
    spacingFactor: 1.1,
    avoidOverlap: true,
    nodeDimensionsIncludeLabels: true,
    fit: true,
    animate: true,
    animationDuration: 500,
    transform: (node, pos) => ({ x: pos.y, y: pos.x }),
  };
}

export function buildStylesheet() {
  return [
    {
      selector: 'node',
      style: {
        'background-color': 'data(color)',
        label: 'data(shortLabel)',
        color: '#1a1715',
        'text-valign': 'bottom',
        'text-halign': 'center',
        'font-size': '9px',
        'font-family': '"IBM Plex Sans", system-ui, sans-serif',
        'font-weight': '500',
        'text-wrap': 'wrap',
        'text-max-width': '78px',
        width: 'data(size)',
        height: 'data(size)',
        'border-width': 2,
        'border-color': 'data(borderColor)',
        'text-margin-y': 4,
        'transition-property': 'opacity, border-width',
        'transition-duration': '200ms',
      },
    },
    {
      selector: 'node:selected, node.selected',
      style: { 'border-width': 4, 'border-color': '#0d6270' },
    },
    { selector: 'node.dimmed', style: { opacity: 0.22 } },
    {
      selector: 'edge',
      style: {
        width: 1.5,
        'line-color': '#ccc9c1',
        'target-arrow-color': '#ccc9c1',
        'target-arrow-shape': 'vee',
        'curve-style': 'bezier',
        label: 'data(label)',
        'font-size': '8px',
        color: '#9b968f',
        'font-family': '"IBM Plex Mono", monospace',
        'text-rotation': 'autorotate',
        'text-background-color': '#f2f0eb',
        'text-background-opacity': 0.9,
        'text-background-padding': '2px',
        opacity: 0.8,
        'transition-property': 'opacity, line-color, width',
        'transition-duration': '200ms',
      },
    },
    {
      selector: 'edge[severity = "critical"]',
      style: { 'line-color': '#c98080', 'target-arrow-color': '#c98080' },
    },
    {
      selector: 'edge.highlighted',
      style: {
        opacity: 1,
        'line-color': '#0d6270',
        'target-arrow-color': '#0d6270',
        width: 2.5,
      },
    },
    { selector: 'edge.dimmed', style: { opacity: 0.08 } },
  ];
}
