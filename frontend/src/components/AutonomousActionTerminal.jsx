import React, { useState } from 'react';
import {
  FileCheck, Download, Send, CheckCircle2, Clock, Calendar, AlertCircle,
  FileText, Copy, Printer, Check, ArrowRight, ShieldCheck, Zap, Layers, RefreshCw
} from 'lucide-react';
import { formatMoney, formatQty } from '../utils/format';

export default function AutonomousActionTerminal({
  data,
  onClose,
}) {
  const [activeTab, setActiveTab] = useState('po');
  const [poTransmitted, setPoTransmitted] = useState(false);
  const [poLoading, setPoLoading] = useState(false);
  const [co02Committed, setCo02Committed] = useState(false);
  const [copiedLetter, setCopiedLetter] = useState(false);

  const supplier = data?.supplier || { name: 'Apex Microelectronics', lifnr: '0000001000' };
  const totalExposure = data?.financial_summary?.total_exposure || 111174000;
  const residualExposure = data?.financial_summary?.residual_exposure || 13498056;

  const handleTransmitPO = () => {
    setPoLoading(true);
    setTimeout(() => {
      setPoLoading(false);
      setPoTransmitted(true);
    }, 1200);
  };

  const handleCopyNotice = (text) => {
    navigator.clipboard.writeText(text);
    setCopiedLetter(true);
    setTimeout(() => setCopiedLetter(false), 2000);
  };

  const BOEING_LETTER = `CONFIDENTIAL & PRIVILEGED
Date: September 9, 2026
To: Director of Supply Chain & Aircraft Programs, Boeing Commercial Airplanes
From: Global Supply Chain Intelligence Operations
Subject: PROACTIVE RESOLUTION NOTICE — Delivery Schedule 0080001 (Line 10)

Dear Boeing Procurement Leadership,

We are writing to provide proactive operational notification regarding Purchase Order commitment #4500012 for sub-assembly components utilized in Boeing Commercial line deliveries.

A primary tier-1 component supplier (Apex Microelectronics) recently declared a 14-day production variance. Pursuant to our Automated Supply Chain Immune Protocol, our system has autonomously executed immediate mitigation:

1. ALTERNATE RE-SOURCING: An expedited replacement contract has been committed to certified secondary supplier Nova Components GmbH (Hamburg) for 2,850 units of MCU-32.
2. PRODUCTION SCHEDULE ALIGNMENT: Plant 1010 production queues have been dynamic re-sequenced.
3. SCHEDULE IMPACT: Final aircraft assembly delivery is protected with a net schedule variance of under 48 hours, fully absorbed by existing factory buffer.

Contractual milestone penalties under Master Service Agreement Section 14.2 are hereby preserved with zero systemic disruption to Boeing final assembly lines.

Sincerely,
Vice President, Enterprise Global Procurement`;

  return (
    <div className="action-terminal-wrapper">
      <div className="terminal-header-bar">
        <div className="terminal-title-box">
          <div className="terminal-badge">
            <Zap size={14} className="text-emerald" />
            <span>AUTONOMOUS REMEDIATION TERMINAL</span>
          </div>
          <h2 className="terminal-title">SAP Autonomous Action Execution Suite</h2>
          <p className="terminal-subtitle">
            Do not just alert — execute. Approve verified SAP transactions, defer production queues, and generate executive dossiers with zero manual SAP GUI data entry.
          </p>
        </div>

        {onClose && (
          <button className="terminal-close-btn" onClick={onClose}>
            ✕
          </button>
        )}
      </div>

      {/* Terminal Navigation Bar */}
      <div className="terminal-nav-bar">
        <button
          className={`term-nav-btn ${activeTab === 'po' ? 'active' : ''}`}
          onClick={() => setActiveTab('po')}
        >
          <FileCheck size={16} />
          <span>1. Execute SAP PO (ME21N)</span>
          {poTransmitted && <span className="pill-success">TRANSMITTED</span>}
        </button>

        <button
          className={`term-nav-btn ${activeTab === 'co02' ? 'active' : ''}`}
          onClick={() => setActiveTab('co02')}
        >
          <Calendar size={16} />
          <span>2. Re-sequence Production (CO02)</span>
          {co02Committed && <span className="pill-success">COMMITTED</span>}
        </button>

        <button
          className={`term-nav-btn ${activeTab === 'customer' ? 'active' : ''}`}
          onClick={() => setActiveTab('customer')}
        >
          <Send size={16} />
          <span>3. Customer Mitigation Notices</span>
        </button>

        <button
          className={`term-nav-btn ${activeTab === 'cfo' ? 'active' : ''}`}
          onClick={() => setActiveTab('cfo')}
        >
          <FileText size={16} />
          <span>4. CFO 1-Page Board Dossier</span>
        </button>
      </div>

      {/* TERMINAL TAB CONTENT */}
      <div className="terminal-body-area">
        {/* TAB 1: SAP PO ME21N */}
        {activeTab === 'po' && (
          <div className="terminal-pane">
            <div className="pane-summary-banner banner-emerald">
              <div>
                <strong>Autonomous Action: </strong>
                Re-source 2,850 units of MCU-32 from Nova Components GmbH (Hamburg).
              </div>
              <div className="text-right">
                <span className="text-sm">Cost: <strong>$9,682</strong></span>
                <span className="text-sm ml-4">Mitigates: <strong className="text-emerald">$81,630,000</strong></span>
              </div>
            </div>

            {/* Official SAP PO Document Voucher */}
            <div className="sap-po-voucher">
              <div className="voucher-header">
                <div>
                  <span className="sap-logo-text">SAP S/4HANA</span>
                  <h4 className="voucher-title">STANDARD PURCHASE ORDER (ME21N)</h4>
                  <span className="voucher-doc-type">Document Type: NB · Org: 1000 · Group: 001</span>
                </div>
                <div className="voucher-status-box">
                  {poTransmitted ? (
                    <div className="po-status-badge transmitted">
                      <CheckCircle2 size={16} />
                      <span>POSTED: PO #4500098421</span>
                    </div>
                  ) : (
                    <div className="po-status-badge draft">
                      <Clock size={16} />
                      <span>PENDING TRANSMISSION</span>
                    </div>
                  )}
                </div>
              </div>

              <div className="voucher-meta-grid">
                <div className="vm-cell">
                  <span className="vm-label">Vendor Master (LFA1)</span>
                  <span className="vm-val font-mono">0000001010</span>
                  <span className="vm-sub">Nova Components GmbH, Hamburg DE</span>
                </div>
                <div className="vm-cell">
                  <span className="vm-label">Target Plant (WERKS)</span>
                  <span className="vm-val font-mono">1010</span>
                  <span className="vm-sub">Munich Advanced Production</span>
                </div>
                <div className="vm-cell">
                  <span className="vm-label">Storage Location (LGORT)</span>
                  <span className="vm-val font-mono">0001</span>
                  <span className="vm-sub">Raw Assembly Components</span>
                </div>
                <div className="vm-cell">
                  <span className="vm-label">Required Delivery (EINDT)</span>
                  <span className="vm-val font-mono">2026-09-22</span>
                  <span className="vm-sub">Express Road Freight</span>
                </div>
              </div>

              {/* Line items table */}
              <table className="voucher-table">
                <thead>
                  <tr>
                    <th>Item</th>
                    <th>Material (MATNR)</th>
                    <th>Description (MAKTX)</th>
                    <th>Order Qty</th>
                    <th>Net Price</th>
                    <th>Net Value</th>
                    <th>Tax</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td className="font-mono">00010</td>
                    <td className="font-mono text-cyan">MCU-32</td>
                    <td>Automotive Microcontroller 32-bit High Reliability</td>
                    <td className="font-mono">2,850 EA</td>
                    <td className="font-mono">$3.40 / EA</td>
                    <td className="font-mono font-bold">$9,682.00</td>
                    <td className="font-mono">V1 (19%)</td>
                  </tr>
                </tbody>
              </table>

              <div className="voucher-footer">
                <div className="vf-bapi">
                  <span className="bapi-tag">BAPI Payload</span>
                  <code>BAPI_PO_CREATE1 (VENDOR=0000001010, MATNR=MCU-32, MENGE=2850, NETPR=3.40, WERKS=1010)</code>
                </div>

                <div className="vf-actions">
                  <button
                    className="btn-download-xml"
                    onClick={() => alert('Downloaded EDI 850 XML Payload: PO_4500098421.xml')}
                  >
                    <Download size={14} />
                    <span>Download EDI 850 XML</span>
                  </button>

                  <button
                    disabled={poTransmitted || poLoading}
                    className={`btn-transmit-po ${poTransmitted ? 'transmitted' : ''}`}
                    onClick={handleTransmitPO}
                  >
                    {poLoading ? (
                      <>
                        <RefreshCw size={14} className="animate-spin" />
                        <span>Transmitting RFC to S/4HANA...</span>
                      </>
                    ) : poTransmitted ? (
                      <>
                        <CheckCircle2 size={14} />
                        <span>Transmitted &amp; Confirmed in SAP</span>
                      </>
                    ) : (
                      <>
                        <Send size={14} />
                        <span>1-Click Approve &amp; Transmit to SAP S/4HANA</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: PRODUCTION RE-SEQUENCING (CO02) */}
        {activeTab === 'co02' && (
          <div className="terminal-pane">
            <div className="pane-summary-banner banner-cyan">
              <div>
                <strong>Autonomous Action: </strong>
                Defer Production Order 000009005 (PSU-220) by 4 days to prioritize critical customer orders.
              </div>
              <div>
                <span className="text-sm">Cost: <strong>$0</strong></span>
                <span className="text-sm ml-4">Mitigates: <strong className="text-cyan">$16,045,944</strong></span>
              </div>
            </div>

            <div className="gantt-reschedule-card">
              <div className="gantt-head">
                <h4 className="gantt-title">Production Floor Slack &amp; Queue Shift (SAP PP · CO02)</h4>
                <span className="gantt-order font-mono">ORDER #000009005 · PLANT 1010</span>
              </div>

              {/* Visual Gantt Comparison */}
              <div className="gantt-visual-box">
                <div className="gantt-timeline-header">
                  <span>Day 0</span>
                  <span>Day 4</span>
                  <span>Day 8</span>
                  <span>Day 12</span>
                  <span>Day 16</span>
                  <span>Day 20</span>
                </div>

                <div className="gantt-row">
                  <div className="gantt-label">Original Slot:</div>
                  <div className="gantt-bar-track">
                    <div className="gantt-bar bar-original" style={{ left: '25%', width: '30%' }}>
                      <span>Sep 12 - Sep 18 (Conflicts with Shortfall)</span>
                    </div>
                  </div>
                </div>

                <div className="gantt-row">
                  <div className="gantt-label text-emerald">Optimized Slot:</div>
                  <div className="gantt-bar-track">
                    <div className="gantt-bar bar-optimized" style={{ left: '45%', width: '30%' }}>
                      <span>Sep 16 - Sep 22 (Post Nova Arrival)</span>
                    </div>
                  </div>
                </div>
              </div>

              <div className="gantt-details-grid">
                <div className="gd-cell">
                  <span className="gd-label">Identified Float Slack</span>
                  <span className="gd-val text-emerald">5.2 Days</span>
                  <span className="gd-sub">Finish date still precedes delivery SLA</span>
                </div>
                <div className="gd-cell">
                  <span className="gd-label">Factory Setup Cost</span>
                  <span className="gd-val">$0.00</span>
                  <span className="gd-sub">No tooling change required</span>
                </div>
                <div className="gd-cell">
                  <span className="gd-label">Capacity Utilization</span>
                  <span className="gd-val text-cyan">94.2%</span>
                  <span className="gd-sub">Line balanced with zero idle overtime</span>
                </div>
              </div>

              <div className="gantt-footer">
                <button
                  disabled={co02Committed}
                  className={`btn-commit-co02 ${co02Committed ? 'committed' : ''}`}
                  onClick={() => setCo02Committed(true)}
                >
                  {co02Committed ? (
                    <>
                      <CheckCircle2 size={16} />
                      <span>Committed to SAP PP (BAPI_PRODORD_CHANGE Confirmed)</span>
                    </>
                  ) : (
                    <>
                      <Check size={16} />
                      <span>Commit Re-Schedule to SAP Production Planning (CO02)</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* TAB 3: CUSTOMER BREACH MITIGATION NOTICE */}
        {activeTab === 'customer' && (
          <div className="terminal-pane">
            <div className="pane-summary-banner banner-rose">
              <div>
                <strong>Autonomous Communication: </strong>
                Auto-drafted force majeure mitigation letter for Boeing Commercial Airplanes ($31.2M Order, $2.5M Penalty).
              </div>
              <button
                className="btn-copy-letter"
                onClick={() => handleCopyNotice(BOEING_LETTER)}
              >
                {copiedLetter ? <Check size={14} /> : <Copy size={14} />}
                <span>{copiedLetter ? 'Copied to Clipboard!' : 'Copy Letter'}</span>
              </button>
            </div>

            <div className="customer-letter-preview">
              <pre className="letter-text-box">{BOEING_LETTER}</pre>
            </div>
          </div>
        )}

        {/* TAB 4: CFO 1-PAGE EXECUTIVE DOSSIER */}
        {activeTab === 'cfo' && (
          <div className="terminal-pane">
            <div className="cfo-print-dossier" id="cfo-dossier">
              <div className="cfo-header-strip">
                <div>
                  <h3 className="cfo-title">BOARD OF DIRECTORS &amp; CFO CRISIS ACTION BRIEF</h3>
                  <span className="cfo-subtitle">SAP Supply Chain Immune System · Incident Response Report</span>
                </div>
                <button className="btn-print-dossier" onClick={() => window.print()}>
                  <Printer size={15} />
                  <span>Print 1-Page PDF</span>
                </button>
              </div>

              <div className="cfo-stats-row">
                <div className="cfo-stat-box box-risk">
                  <span className="cs-label">Baseline Unmitigated Risk</span>
                  <span className="cs-val text-rose">{formatMoney(totalExposure)}</span>
                  <span className="cs-sub">5 Customers · 7 Deliveries</span>
                </div>
                <div className="cfo-stat-box box-savings">
                  <span className="cs-label">Total Risk Mitigated</span>
                  <span className="cs-val text-emerald">{formatMoney(totalExposure - residualExposure)}</span>
                  <span className="cs-sub">87.9% Risk Eliminated</span>
                </div>
                <div className="cfo-stat-box">
                  <span className="cs-label">Total Execution Spend</span>
                  <span className="cs-val text-cyan">$9,682</span>
                  <span className="cs-sub">ROI: 10,088x</span>
                </div>
                <div className="cfo-stat-box">
                  <span className="cs-label">Net Residual Exposure</span>
                  <span className="cs-val text-amber">{formatMoney(residualExposure)}</span>
                  <span className="cs-sub">Confined to buffer adjustments</span>
                </div>
              </div>

              <div className="cfo-section-title">EXECUTIVE SUMMARY &amp; AUDIT LINEAGE</div>
              <p className="cfo-narrative-para">
                On September 9, 2026, an autonomous monitoring agent identified an unannounced 14-day schedule slippage at tier-1 semiconductor vendor <strong>Apex Microelectronics (LFA1: 0000001000)</strong>. Left unaddressed, component depletion on Day 6 would have cascaded into Plant 1010/1020 line halts and breached contract delivery milestones for <strong>Boeing Commercial ($31.2M)</strong> and <strong>Airbus SAS ($18.7M)</strong>, creating an unmitigated <strong>$111,174,000 USD</strong> financial liability.
              </p>

              <div className="cfo-table-box">
                <table className="cfo-table">
                  <thead>
                    <tr>
                      <th>Disruption Metric</th>
                      <th>SAP Source Table</th>
                      <th>Gross Exposure</th>
                      <th>Mitigation Action</th>
                      <th>Residual Risk</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>Stranded PO Value</td>
                      <td className="font-mono">EKPO.NETWR</td>
                      <td>$504,000</td>
                      <td>Transfer commitments to Nova</td>
                      <td className="text-emerald">$0</td>
                    </tr>
                    <tr>
                      <td>Plant Idle Downtime</td>
                      <td className="font-mono">AFKO.GLTRP / MARD</td>
                      <td>$3,900,000</td>
                      <td>CO02 Production Re-sequencing</td>
                      <td className="text-emerald">$0</td>
                    </tr>
                    <tr>
                      <td>Revenue at Risk</td>
                      <td className="font-mono">VBAP.NETWR</td>
                      <td>$99,500,000</td>
                      <td>Re-source 2,850 MCU-32 ($9.7K)</td>
                      <td className="text-amber">$8,200,000</td>
                    </tr>
                    <tr>
                      <td>Late Delivery Penalties</td>
                      <td className="font-mono">LIKP / LIPS</td>
                      <td>$7,270,000</td>
                      <td>Force Majeure Waiver Notice</td>
                      <td className="text-amber">$5,298,056</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <div className="cfo-signoff-row">
                <div className="cfo-sign-cell">
                  <span>Prepared By: AI-Powered SAP Knowledge Graph Engine</span>
                  <span className="font-mono text-xs">SHACL Governed · 100% Deterministic Core</span>
                </div>
                <div className="cfo-sign-cell text-right">
                  <span>Approved for Board Presentation: Chief Procurement Officer</span>
                  <span className="font-mono text-xs">Status: READY FOR SIGNATURE</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
