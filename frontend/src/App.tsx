import React, { useState } from 'react';
import { DisasterProvider } from './context/DisasterContext';
import { Header } from './components/common/Header';
import { DisasterMap } from './components/map/DisasterMap';
import { FloodAnalysisPanel } from './components/flood/FloodAnalysisPanel';
import { SimulationStudio } from './components/simulation/SimulationStudio';
import { ImpactAssessment } from './components/simulation/ImpactAssessment';
import { RiskOverview } from './components/risk/RiskOverview';
import { ExplainabilityRadar } from './components/risk/ExplainabilityRadar';
import { PriorityZoneList } from './components/risk/PriorityZoneList';
import { EvacuationPanel } from './components/routing/EvacuationPanel';
import {
  Activity,
  Waves,
  ShieldAlert,
  Navigation,
  Satellite,
  ChevronRight,
  ChevronLeft,
  X,
} from 'lucide-react';

const DashboardContent: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'overview' | 'simulation' | 'risk' | 'routing'>('overview');
  const [isSidebarOpen, setIsSidebarOpen] = useState<boolean>(true);

  return (
    <div className="flex flex-col h-screen w-screen bg-[#0B0F17] text-slate-100 overflow-hidden font-sans">
      {/* Top Navbar */}
      <Header />

      {/* Main Command Center Split View */}
      <div className="relative flex-1 flex overflow-hidden">
        {/* Left / Center Map Canvas */}
        <div className="flex-1 relative h-full">
          <DisasterMap />

          {/* Quick tab switcher overlay on map (mobile / quick access) */}
          <div className="absolute top-3 left-3 sm:top-4 sm:left-4 z-[1000] flex items-center gap-0.5 sm:gap-0 p-1 rounded-xl bg-slate-900/90 backdrop-blur-md border border-slate-800 shadow-2xl overflow-x-auto no-scrollbar max-w-[calc(100vw-72px)] sm:max-w-none">
            <button
              onClick={() => setActiveTab('overview')}
              className={`flex items-center justify-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-mono transition shrink-0 ${
                activeTab === 'overview'
                  ? 'bg-cyan-500/20 text-cyan-300 font-bold border border-cyan-500/40 shadow-[0_0_10px_rgba(6,182,212,0.2)]'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Satellite className="w-3.5 h-3.5 shrink-0" />
              <span className="hidden xs:inline sm:inline">Overview</span>
            </button>
            <button
              onClick={() => setActiveTab('simulation')}
              className={`flex items-center justify-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-mono transition shrink-0 ${
                activeTab === 'simulation'
                  ? 'bg-indigo-500/20 text-indigo-300 font-bold border border-indigo-500/40 shadow-[0_0_10px_rgba(99,102,241,0.2)]'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Waves className="w-3.5 h-3.5 shrink-0" />
              <span className="hidden xs:inline sm:inline">Digital Twin</span>
            </button>
            <button
              onClick={() => setActiveTab('risk')}
              className={`flex items-center justify-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-mono transition shrink-0 ${
                activeTab === 'risk'
                  ? 'bg-rose-500/20 text-rose-300 font-bold border border-rose-500/40 shadow-[0_0_10px_rgba(244,63,94,0.2)]'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <ShieldAlert className="w-3.5 h-3.5 shrink-0" />
              <span className="hidden xs:inline sm:inline">Risk Engine</span>
            </button>
            <button
              onClick={() => setActiveTab('routing')}
              className={`flex items-center justify-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-mono transition shrink-0 ${
                activeTab === 'routing'
                  ? 'bg-emerald-500/20 text-emerald-300 font-bold border border-emerald-500/40 shadow-[0_0_10px_rgba(16,185,129,0.2)]'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Navigation className="w-3.5 h-3.5 shrink-0" />
              <span className="hidden xs:inline sm:inline">Evacuation</span>
            </button>
          </div>

          {/* Toggle Sidebar Collapse Button */}
          <button
            onClick={() => setIsSidebarOpen(!isSidebarOpen)}
            className={`absolute top-1/2 right-0 -translate-y-1/2 z-[1000] p-1.5 rounded-l-xl bg-slate-900/90 backdrop-blur-md border-y border-l border-slate-700 text-slate-300 hover:text-white shadow-2xl transition ${
              isSidebarOpen ? 'hidden md:block' : 'block'
            }`}
            title={isSidebarOpen ? 'Collapse Telemetry' : 'Expand Telemetry'}
          >
            {isSidebarOpen ? (
              <ChevronRight className="w-4 h-4" />
            ) : (
              <ChevronLeft className="w-4 h-4" />
            )}
          </button>
        </div>

        {/* Mobile backdrop behind the drawer sidebar */}
        {isSidebarOpen && (
          <div
            onClick={() => setIsSidebarOpen(false)}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-10 md:hidden"
            aria-hidden="true"
          />
        )}

        {/* Right Telemetry & Control Sidebar */}
        {isSidebarOpen && (
          <aside className="fixed md:relative inset-y-0 right-0 top-16 md:top-0 w-full xs:w-[85%] sm:w-96 md:w-[380px] lg:w-[420px] xl:w-[450px] h-[calc(100%-4rem)] md:h-full bg-slate-950/95 border-l border-slate-800/80 flex flex-col z-20 shrink-0 shadow-2xl animate-in slide-in-from-right duration-200">
            {/* Sidebar Tab Header */}
            <div className="p-2 sm:p-3 border-b border-slate-800/80 flex items-center gap-1 bg-slate-900/50">
              <button
                onClick={() => setIsSidebarOpen(false)}
                className="md:hidden shrink-0 p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
                title="Close panel"
              >
                <X className="w-4 h-4" />
              </button>
              <div className="grid grid-cols-4 gap-1 flex-1">
              <button
                onClick={() => setActiveTab('overview')}
                className={`py-1.5 text-[10px] sm:text-[11px] font-mono rounded-lg transition text-center truncate ${
                  activeTab === 'overview'
                    ? 'bg-cyan-500/20 text-cyan-300 font-bold border border-cyan-500/30'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Overview
              </button>
              <button
                onClick={() => setActiveTab('simulation')}
                className={`py-1.5 text-[10px] sm:text-[11px] font-mono rounded-lg transition text-center truncate ${
                  activeTab === 'simulation'
                    ? 'bg-indigo-500/20 text-indigo-300 font-bold border border-indigo-500/30'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Simulation
              </button>
              <button
                onClick={() => setActiveTab('risk')}
                className={`py-1.5 text-[10px] sm:text-[11px] font-mono rounded-lg transition text-center truncate ${
                  activeTab === 'risk'
                    ? 'bg-rose-500/20 text-rose-300 font-bold border border-rose-500/30'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Risk Engine
              </button>
              <button
                onClick={() => setActiveTab('routing')}
                className={`py-1.5 text-[10px] sm:text-[11px] font-mono rounded-lg transition text-center truncate ${
                  activeTab === 'routing'
                    ? 'bg-emerald-500/20 text-emerald-300 font-bold border border-emerald-500/30'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Evacuation
              </button>
              </div>
            </div>

            {/* Scrollable Sidebar Panels */}
            <div className="flex-1 p-3 sm:p-4 overflow-y-auto space-y-4 pr-2.5 sm:pr-3.5 scrollbar-thin scrollbar-thumb-slate-800 scrollbar-track-transparent">
              {activeTab === 'overview' && (
                <>
                  <ImpactAssessment />
                  <FloodAnalysisPanel />
                  <RiskOverview />
                  <EvacuationPanel />
                </>
              )}

              {activeTab === 'simulation' && (
                <>
                  <SimulationStudio />
                  <ImpactAssessment />
                  <FloodAnalysisPanel />
                </>
              )}

              {activeTab === 'risk' && (
                <>
                  <RiskOverview />
                  <ExplainabilityRadar />
                  <PriorityZoneList />
                </>
              )}

              {activeTab === 'routing' && (
                <>
                  <EvacuationPanel />
                  <PriorityZoneList />
                  <RiskOverview />
                </>
              )}
            </div>
          </aside>
        )}
      </div>
    </div>
  );
};

export const App: React.FC = () => {
  return (
    <DisasterProvider>
      <DashboardContent />
    </DisasterProvider>
  );
};

export default App;
