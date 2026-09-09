import React, { useState, useEffect } from 'react';
import {
  ChevronDown, ChevronUp, CheckCircle2, Loader2, Sparkles,
  Search, GitBranch, DollarSign, ShieldAlert, CheckCheck, FileEdit
} from 'lucide-react';

const REASONING_STEPS = [
  {
    id: 'entity',
    icon: Search,
    title: 'Resolving SAP Master Data Entities',
    detail: 'Mapping natural language tokens to LFA1 (Vendor: 0000001000) and MARA (Materials).',
  },
  {
    id: 'traversal',
    icon: GitBranch,
    title: '8-Hop Graph Traversal Across Business Objects',
    detail: 'Traversing LFA1 → EKKO/EKPO → EKET → MARD → AFKO/RESB → VBAP → LIKP.',
  },
  {
    id: 'finance',
    icon: DollarSign,
    title: 'Deterministic Financial Exposure Quantification',
    detail: 'Pricing stranded PO lines, daily plant idle costs, revenue at risk, and contract penalties.',
  },
  {
    id: 'avoidance',
    icon: ShieldAlert,
    title: 'Discovering Preventive Avoidance & Re-sourcing Paths',
    detail: 'Evaluating EINA/EINE alternate vendors, plant safety buffers, and order re-sequencing.',
  },
  {
    id: 'governance',
    icon: CheckCheck,
    title: 'SHACL Shape Validation & Confidence Gate',
    detail: 'Verifying 101 RDF nodes conform to W3C supply chain ontology with 0 hallucinations.',
  },
  {
    id: 'narrative',
    icon: FileEdit,
    title: 'DeepSeek-V4-Pro Executive Brief Synthesis',
    detail: 'Generating CFO-level narrative briefing locked to deterministic numbers.',
  },
];

export default function ThinkingBlock({
  isLoading = false,
  activeStepIndex = 0,
  elapsedSeconds = 0,
  isCompleted = false,
}) {
  const [isOpen, setIsOpen] = useState(true);

  // Once completed, user can still toggle it open or closed
  const currentStep = REASONING_STEPS[Math.min(activeStepIndex, REASONING_STEPS.length - 1)];

  return (
    <div className={`thinking-block ${isCompleted ? 'completed' : 'active'}`}>
      <div className="thinking-header" onClick={() => setIsOpen(!isOpen)}>
        <div className="thinking-header-left">
          {isLoading ? (
            <div className="thinking-spinner-badge">
              <Loader2 size={14} className="animate-spin text-cyan" />
            </div>
          ) : (
            <div className="thinking-success-badge">
              <Sparkles size={14} className="text-violet" />
            </div>
          )}
          <div className="thinking-title-box">
            <span className="thinking-title">
              {isLoading
                ? `Reasoning across 8 hops... (${elapsedSeconds.toFixed(1)}s)`
                : `Completed reasoning & graph traversal (${elapsedSeconds.toFixed(1)}s)`}
            </span>
            <span className="thinking-current-step">
              {isLoading ? currentStep.title : '6 validation & computation steps verified'}
            </span>
          </div>
        </div>

        <button className="thinking-toggle-btn">
          {isOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>
      </div>

      {isOpen && (
        <div className="thinking-content">
          <div className="thinking-steps-list">
            {REASONING_STEPS.map((step, idx) => {
              const Icon = step.icon;
              const isDone = isCompleted || idx < activeStepIndex;
              const isCurrent = isLoading && idx === activeStepIndex;
              const isPending = !isCompleted && idx > activeStepIndex;

              return (
                <div
                  key={step.id}
                  className={`thinking-step ${
                    isDone ? 'step-done' : isCurrent ? 'step-current' : 'step-pending'
                  }`}
                >
                  <div className="step-indicator">
                    {isDone ? (
                      <CheckCircle2 size={15} className="text-emerald" />
                    ) : isCurrent ? (
                      <div className="step-pulse-dot" />
                    ) : (
                      <div className="step-idle-dot" />
                    )}
                  </div>
                  <div className="step-body">
                    <div className="step-title-row">
                      <Icon size={13} className="step-icon" />
                      <span className="step-title">{step.title}</span>
                    </div>
                    <p className="step-detail">{step.detail}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
