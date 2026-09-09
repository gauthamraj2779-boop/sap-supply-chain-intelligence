import React, { useState, useEffect, useRef } from 'react';
import { Sparkles, MessageSquare, Zap, ShieldCheck, Database, ArrowRight, Layers } from 'lucide-react';

import ChatSidebar from './components/ChatSidebar';
import ChatHeader from './components/ChatHeader';
import ChatInput from './components/ChatInput';
import ThinkingBlock from './components/ThinkingBlock';
import InteractiveResponseCanvas from './components/InteractiveResponseCanvas';
import InspectorPage from './components/InspectorPage';

import { analyseQuestion, checkHealth } from './utils/api';

const HERO_PROMPT_CARDS = [
  {
    icon: Zap,
    title: 'Apex Microelectronics (+14d)',
    badge: 'Flagship Demo',
    query: 'Supplier Apex Microelectronics is delayed by 14 days. What is our financial risk and how do we avoid it?',
    color: 'rose',
  },
  {
    icon: ShieldCheck,
    title: 'MCU-32 Sole-Source Risk',
    badge: 'Vulnerability Test',
    query: 'What if we lose our sole source for MCU-32 microcontrollers for 21 days?',
    color: 'amber',
  },
  {
    icon: Database,
    title: 'Plant 1010 Downtime (+7d)',
    badge: 'Cross-Plant Flow',
    query: 'Show me all customers affected if Plant 1010 goes offline for 7 days.',
    color: 'cyan',
  },
  {
    icon: Sparkles,
    title: 'Toshiro Metals (+7d)',
    badge: 'Buffer Absorption',
    query: 'How exposed are we if Toshiro Metals is 7 days late?',
    color: 'emerald',
  },
];

export default function App() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [scenarios, setScenarios] = useState([]);
  const [activeScenarioId, setActiveScenarioId] = useState(null);
  const [currentQuery, setCurrentQuery] = useState('');
  const [activeReport, setActiveReport] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [thinkingStep, setThinkingStep] = useState(0);
  const [elapsedTime, setElapsedTime] = useState(0);
  const [showInspector, setShowInspector] = useState(false);
  const [systemHealth, setSystemHealth] = useState(null);

  const timerRef = useRef(null);
  const stepIntervalRef = useRef(null);
  const messagesEndRef = useRef(null);

  // Poll health on mount
  useEffect(() => {
    checkHealth()
      .then((h) => setSystemHealth(h))
      .catch((e) => console.warn('Health check failed:', e));
  }, []);

  const scrollToBottom = () => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  };

  const handleRunQuery = async (queryText) => {
    if (!queryText.trim() || isLoading) return;

    setCurrentQuery(queryText);
    setIsLoading(true);
    setThinkingStep(0);
    setElapsedTime(0);

    const startTime = Date.now();
    timerRef.current = setInterval(() => {
      setElapsedTime((Date.now() - startTime) / 1000);
    }, 100);

    // Animate reasoning steps
    stepIntervalRef.current = setInterval(() => {
      setThinkingStep((prev) => (prev < 5 ? prev + 1 : prev));
    }, 600);

    try {
      const resp = await analyseQuestion(queryText);
      clearInterval(timerRef.current);
      clearInterval(stepIntervalRef.current);
      setThinkingStep(5);

      const finalElapsed = (Date.now() - startTime) / 1000;
      setElapsedTime(finalElapsed);
      setIsLoading(false);

      const reportData = resp.report || resp;
      setActiveReport(reportData);

      // Save to history
      const newScenario = {
        id: `sc-${Date.now()}`,
        query: queryText,
        title: queryText.slice(0, 40) + (queryText.length > 40 ? '...' : ''),
        exposure: reportData.financial_summary?.total_exposure
          ? `$${(reportData.financial_summary.total_exposure / 1e6).toFixed(1)}M`
          : '$0',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        data: reportData,
        elapsed: finalElapsed,
      };

      setScenarios((prev) => [newScenario, ...prev]);
      setActiveScenarioId(newScenario.id);

      setTimeout(scrollToBottom, 100);
    } catch (err) {
      clearInterval(timerRef.current);
      clearInterval(stepIntervalRef.current);
      setIsLoading(false);
      alert('Error running simulation: ' + (err.message || String(err)));
    }
  };

  const handleSelectScenario = (id) => {
    const sc = scenarios.find((s) => s.id === id);
    if (sc) {
      setActiveScenarioId(sc.id);
      setCurrentQuery(sc.query);
      setActiveReport(sc.data);
      setElapsedTime(sc.elapsed || 2.4);
    }
  };

  const handleSelectPreset = (preset) => {
    handleRunQuery(preset.query);
  };

  const handleNewScenario = () => {
    setActiveScenarioId(null);
    setCurrentQuery('');
    setActiveReport(null);
    setIsLoading(false);
    setElapsedTime(0);
  };

  const handleClearScenarios = () => {
    setScenarios([]);
    handleNewScenario();
  };

  return (
    <div className="chat-app-root">
      <ChatSidebar
        isOpen={sidebarOpen}
        onToggle={() => setSidebarOpen(!sidebarOpen)}
        scenarios={scenarios}
        activeScenarioId={activeScenarioId}
        onSelectScenario={handleSelectScenario}
        onNewScenario={handleNewScenario}
        onClearScenarios={handleClearScenarios}
        onSelectPreset={handleSelectPreset}
        systemHealth={systemHealth}
        onOpenInspector={() => setShowInspector(true)}
      />

      <div className={`chat-main-container ${sidebarOpen ? 'sidebar-expanded' : 'sidebar-collapsed'}`}>
        <ChatHeader
          sidebarOpen={sidebarOpen}
          onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
          currentScenario={scenarios.find((s) => s.id === activeScenarioId)}
          onReset={handleNewScenario}
          onOpenInspector={() => setShowInspector(true)}
          systemHealth={systemHealth}
        />

        <main className="chat-content-scroll">
          {/* Landing state when no query has been run */}
          {!activeReport && !isLoading ? (
            <div className="chat-hero-landing">
              <div className="hero-badge-pill">
                <Sparkles size={14} className="text-violet" />
                <span>Next-Gen Supply Chain Intelligence</span>
              </div>

              <h1 className="hero-main-title">
                What SAP disruption would you like to stress-test?
              </h1>

              <p className="hero-main-subtitle">
                Ask multi-hop questions across suppliers, purchase orders, materials, plants, and customer deliveries.
                Get deterministic financial exposure down to the dollar with autonomous avoidance plans.
              </p>

              <div className="hero-prompt-grid">
                {HERO_PROMPT_CARDS.map((card, idx) => {
                  const Icon = card.icon;
                  return (
                    <button
                      key={idx}
                      className={`hero-card-btn card-${card.color}`}
                      onClick={() => handleRunQuery(card.query)}
                    >
                      <div className="hero-card-top">
                        <div className="hero-card-icon-box">
                          <Icon size={16} />
                        </div>
                        <span className="hero-card-badge">{card.badge}</span>
                      </div>
                      <h3 className="hero-card-title">{card.title}</h3>
                      <p className="hero-card-query truncate">{card.query}</p>
                      <div className="hero-card-arrow">
                        <span>Run Simulation</span>
                        <ArrowRight size={13} />
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="chat-messages-thread">
              {/* User message */}
              {currentQuery && (
                <div className="message-row user-row">
                  <div className="user-bubble">
                    <p className="user-query-text">{currentQuery}</p>
                  </div>
                </div>
              )}

              {/* Assistant message container */}
              <div className="message-row assistant-row">
                <div className="assistant-avatar">
                  <Sparkles size={18} className="text-violet" />
                </div>

                <div className="assistant-content-container">
                  {/* OpenAI o1 / Deep Research style thinking block */}
                  <ThinkingBlock
                    isLoading={isLoading}
                    activeStepIndex={thinkingStep}
                    elapsedSeconds={elapsedTime}
                    isCompleted={!isLoading && !!activeReport}
                  />

                  {/* Interactive Response Canvas */}
                  {!isLoading && activeReport && (
                    <InteractiveResponseCanvas
                      data={activeReport}
                      onFollowUp={(query) => handleRunQuery(query)}
                      onOpenInspector={() => setShowInspector(true)}
                    />
                  )}
                </div>
              </div>

              <div ref={messagesEndRef} />
            </div>
          )}
        </main>

        {/* Sticky floating bottom query bar */}
        <ChatInput
          onSubmit={handleRunQuery}
          isLoading={isLoading}
          onCancel={() => setIsLoading(false)}
          initialQuery=""
        />
      </div>

      {/* Modal Inspector for SAP DDIC Catalog */}
      {showInspector && (
        <div className="modal-backdrop" onClick={() => setShowInspector(false)}>
          <div className="modal-surface" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>SAP Data Dictionary (DDIC) Catalog</h3>
              <button className="close-modal-btn" onClick={() => setShowInspector(false)}>✕</button>
            </div>
            <div className="modal-body">
              <InspectorPage onClose={() => setShowInspector(false)} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
