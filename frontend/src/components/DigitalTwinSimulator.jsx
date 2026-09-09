import React, { useState, useMemo } from 'react';
import {
  Sliders, AlertTriangle, ShieldCheck, TrendingUp, Zap, Clock,
  ArrowRight, RefreshCw, Cpu, Activity, DollarSign, Layers
} from 'lucide-react';
import { formatMoney, formatQty } from '../utils/format';

export default function DigitalTwinSimulator({
  baseSupplier = 'Apex Microelectronics',
  initialDelay = 14,
  onApplyDelay,
}) {
  const [delayDays, setDelayDays] = useState(initialDelay);
  const [airFreightActive, setAirFreightActive] = useState(false);
  const [safetyBufferDeploy, setSafetyBufferDeploy] = useState(false);

  // Dynamic real-time calculation based on delay days
  const simulation = useMemo(() => {
    // Current stock covers 6 days at Plant 1010
    const stockCoverageDays = 6;
    const effectiveDelay = Math.max(0, delayDays - (airFreightActive ? 8 : 0));
    const shortfallDays = Math.max(0, effectiveDelay - (stockCoverageDays + (safetyBufferDeploy ? 4 : 0)));

    let threatLevel = 'SAFE';
    let defcon = 'DEFCON 4';
    let color = 'emerald';
    let summary = 'Stock buffer fully absorbs supplier variance. Zero customer impact.';

    // Base short units: 200 units/day consumption
    const dailyConsumption = 200;
    const shortUnits = shortfallDays > 0 ? shortfallDays * dailyConsumption + 850 : 0;

    // Stranded PO: ~$36K/day of delay
    const strandedPO = delayDays > 0 ? Math.min(504000, delayDays * 36000) : 0;

    // Plant idle cost: $180,000/day after stock runs out
    const plantHaltCost = shortfallDays * 180000 * 2; // 2 affected plants

    // Revenue at risk & penalties
    let revenueAtRisk = 0;
    let penaltyExposure = 0;
    let affectedCustomers = 0;
    let affectedDeliveries = 0;

    if (shortfallDays === 0) {
      threatLevel = 'SAFE';
      defcon = 'BUFFER SECURE';
      color = 'emerald';
      summary = 'Current on-hand inventory at Plant 1010 and 1020 completely absorbs this delay. 0 deliveries breached.';
    } else if (shortfallDays <= 3) {
      threatLevel = 'MODERATE';
      defcon = 'PLANT RISK';
      color = 'amber';
      revenueAtRisk = 12500000;
      penaltyExposure = 850000;
      affectedCustomers = 2;
      affectedDeliveries = 2;
      summary = 'Plant 1010 faces material starvation on Day 7. Internal production queue halted; customer buffer shrinking.';
    } else if (shortfallDays <= 8) {
      threatLevel = 'CRITICAL';
      defcon = 'SLA BREACH';
      color = 'rose';
      revenueAtRisk = 99500000;
      penaltyExposure = 7270000;
      affectedCustomers = 5;
      affectedDeliveries = 7;
      summary = 'Severe cascade! Boeing Commercial and Airbus SAS delivery milestones breached. Contractual penalty clauses triggered.';
    } else {
      threatLevel = 'CATASTROPHIC';
      defcon = 'SYSTEMIC FAILURE';
      color = 'purple';
      revenueAtRisk = 185000000;
      penaltyExposure = 18400000;
      affectedCustomers = 6;
      affectedDeliveries = 10;
      summary = 'Global assembly lines paralyzed across Europe & US. Multiple Tier-1 aerospace commitments breached.';
    }

    const totalExposure = strandedPO + plantHaltCost + revenueAtRisk + penaltyExposure;

    return {
      effectiveDelay,
      shortfallDays,
      shortUnits,
      threatLevel,
      defcon,
      color,
      summary,
      strandedPO,
      plantHaltCost,
      revenueAtRisk,
      penaltyExposure,
      totalExposure,
      affectedCustomers,
      affectedDeliveries,
    };
  }, [delayDays, airFreightActive, safetyBufferDeploy]);

  return (
    <div className="digital-twin-wrapper">
      <div className="twin-header-bar">
        <div className="twin-title-left">
          <div className="twin-live-dot" />
          <Activity size={18} className="text-cyan" />
          <div>
            <h3 className="twin-heading">Supply Chain Digital Twin — Stress-Test Simulator</h3>
            <p className="twin-subheading">
              Drag the delay slider to test systemic breaking points across SAP plants, BOMs, and customer SLAs in real time.
            </p>
          </div>
        </div>

        <div className={`threat-defcon-badge badge-${simulation.color}`}>
          <span className="defcon-pulse" />
          <span className="defcon-title">{simulation.defcon}</span>
          <span className="defcon-level">{simulation.threatLevel}</span>
        </div>
      </div>

      {/* Main Interactive Control Deck */}
      <div className="twin-control-deck">
        <div className="twin-slider-box">
          <div className="slider-label-row">
            <span className="sl-title">
              <Clock size={15} />
              <span>Simulated Supplier Disruption Delay:</span>
            </span>
            <span className="sl-value-pill">
              <strong>+{delayDays} Days</strong> ({delayDays === 0 ? 'On Time' : `${delayDays * 24} hours`})
            </span>
          </div>

          <input
            type="range"
            min="0"
            max="30"
            step="1"
            value={delayDays}
            onChange={(e) => setDelayDays(parseInt(e.target.value, 10))}
            className="twin-range-slider"
          />

          <div className="slider-milestones">
            <span className={delayDays === 0 ? 'active' : ''}>Day 0<br /><small>Normal</small></span>
            <span className={delayDays >= 6 ? 'active breached' : ''}>Day 6<br /><small>Stock Depleted</small></span>
            <span className={delayDays >= 10 ? 'active breached' : ''}>Day 10<br /><small>Airbus Breach</small></span>
            <span className={delayDays >= 14 ? 'active breached' : ''}>Day 14<br /><small>Boeing Breach</small></span>
            <span className={delayDays >= 25 ? 'active breached' : ''}>Day 30<br /><small>Catastrophic</small></span>
          </div>
        </div>

        {/* Live Interventions Toggles */}
        <div className="twin-toggles-grid">
          <button
            className={`twin-toggle-card ${airFreightActive ? 'active-emerald' : ''}`}
            onClick={() => setAirFreightActive(!airFreightActive)}
          >
            <div className="tt-top">
              <Zap size={16} />
              <span className="tt-status">{airFreightActive ? 'ACTIVATED' : 'OFFLINE'}</span>
            </div>
            <span className="tt-name">Simulate Air-Freight Dispatch</span>
            <span className="tt-desc">Reduces transit delay by 8 days (Cost: $45K, saves $81M)</span>
          </button>

          <button
            className={`twin-toggle-card ${safetyBufferDeploy ? 'active-cyan' : ''}`}
            onClick={() => setSafetyBufferDeploy(!safetyBufferDeploy)}
          >
            <div className="tt-top">
              <Layers size={16} />
              <span className="tt-status">{safetyBufferDeploy ? 'DEPLOYED' : 'STANDBY'}</span>
            </div>
            <span className="tt-name">Cross-Plant Buffer Rebalance</span>
            <span className="tt-desc">Draws 1,000 units from Plant 1020 buffer (+4 days coverage)</span>
          </button>
        </div>
      </div>

      {/* Real-time Dynamic Financial Ticker & Domino Metrics */}
      <div className="twin-metrics-strip">
        <div className="twin-metric-cell">
          <span className="tm-label">Live Financial Exposure</span>
          <span className={`tm-value text-${simulation.color}`}>
            {formatMoney(simulation.totalExposure)}
          </span>
          <span className="tm-hint">Real-time aggregate loss</span>
        </div>

        <div className="twin-metric-cell">
          <span className="tm-label">Stock Shortfall</span>
          <span className="tm-value text-amber">
            {simulation.shortUnits > 0 ? `${formatQty(simulation.shortUnits)} EA` : '0 EA (Buffer OK)'}
          </span>
          <span className="tm-hint">{simulation.shortfallDays} days of stockout</span>
        </div>

        <div className="twin-metric-cell">
          <span className="tm-label">Plant Downtime Cost</span>
          <span className="tm-value">
            {formatMoney(simulation.plantHaltCost)}
          </span>
          <span className="tm-hint">Idle labor &amp; tooling</span>
        </div>

        <div className="twin-metric-cell">
          <span className="tm-label">Delivery SLA Breaches</span>
          <span className="tm-value text-rose">
            {simulation.affectedDeliveries} Deliveries
          </span>
          <span className="tm-hint">{simulation.affectedCustomers} enterprise customers</span>
        </div>
      </div>

      <div className="twin-summary-footer">
        <div className="ts-text">
          <strong>Live Simulation Diagnostic: </strong>
          <span>{simulation.summary}</span>
        </div>
        {onApplyDelay && (
          <button
            className="twin-apply-btn"
            onClick={() => onApplyDelay(delayDays)}
          >
            <span>Lock &amp; Run Multi-Hop Agent Analysis</span>
            <ArrowRight size={14} />
          </button>
        )}
      </div>
    </div>
  );
}
