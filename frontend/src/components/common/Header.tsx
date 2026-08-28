import React from 'react';
import { useDisaster } from '../../context/DisasterContext';
import {
  Satellite,
  Radio,
  Wifi,
  WifiOff,
  AlertTriangle,
  RefreshCw,
  MapPin,
  Layers,
} from 'lucide-react';

export const Header: React.FC = () => {
  const {
    isLiveMode,
    isBackendHealthy,
    setLiveMode,
    regions,
    selectedRegion,
    setSelectedRegionId,
    activeScenario,
    refreshData,
    isLoading,
  } = useDisaster();

  return (
    <header className="h-16 px-2.5 sm:px-4 bg-slate-900/90 backdrop-blur-md border-b border-slate-800 flex items-center justify-between gap-2 z-30 shrink-0 select-none overflow-hidden">
      {/* Brand & Project Identity */}
      <div className="flex items-center gap-2 sm:gap-3 min-w-0 shrink">
        <div className="relative flex items-center justify-center w-9 h-9 sm:w-10 sm:h-10 rounded-xl bg-gradient-to-tr from-cyan-600 to-blue-600 shadow-[0_0_20px_rgba(6,182,212,0.35)] border border-cyan-400/30 shrink-0">
          <Satellite className="w-4.5 h-4.5 sm:w-5 sm:h-5 text-cyan-100 animate-pulse" />
          <span className="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-cyan-400 animate-ping" />
        </div>

        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="text-base sm:text-lg font-extrabold tracking-wider bg-gradient-to-r from-cyan-400 via-blue-200 to-white bg-clip-text text-transparent font-mono">
              DRISHTI
            </h1>
            <span className="hidden sm:inline text-[10px] px-1.5 py-0.5 rounded bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 font-mono tracking-widest uppercase shrink-0">
              v0.2.0 • SIH 26206
            </span>
          </div>
          <p className="hidden md:flex text-[11px] text-slate-400 tracking-wide font-medium items-center gap-1.5 truncate">
            <span>Satellite Disaster Intelligence</span>
            <span className="text-slate-600">•</span>
            <span className="text-cyan-400/80">Flood Response Command Center</span>
          </p>
        </div>
      </div>

      {/* Center Hazard Banner */}
      <div className="hidden lg:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-rose-500/10 border border-rose-500/30 shrink-0">
        <AlertTriangle className="w-4 h-4 text-rose-400 animate-bounce" />
        <div className="text-xs">
          <span className="font-bold text-rose-300 font-mono">
            ELEVATION WARNING:
          </span>{' '}
          <span className="text-slate-300">
            {activeScenario?.flood_level ? `${activeScenario.flood_level.toFixed(1)}m Inundation Scenario Active` : 'Monitoring Basin'}
          </span>
        </div>
      </div>

      {/* Controls & Mode Switcher */}
      <div className="flex items-center gap-1.5 sm:gap-3 shrink-0">
        {/* Region Selector */}
        <div className="flex items-center gap-1.5 sm:gap-2 px-1.5 sm:px-2.5 py-1.5 rounded-lg bg-slate-800/80 border border-slate-700/60 max-w-[92px] xs:max-w-[130px] sm:max-w-none">
          <MapPin className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
          <select
            value={selectedRegion?.id || ''}
            onChange={(e) => setSelectedRegionId(e.target.value)}
            className="bg-transparent text-xs text-slate-200 focus:outline-none cursor-pointer font-medium pr-1 min-w-0 w-full truncate"
          >
            {regions.map((reg) => (
              <option key={reg.id} value={reg.id} className="bg-slate-900 text-slate-200">
                {reg.name} {reg.state ? `(${reg.state})` : ''}
              </option>
            ))}
          </select>
        </div>

        {/* Live / Demo Mode Switcher */}
        <button
          onClick={() => setLiveMode(!isLiveMode)}
          className={`flex items-center gap-1.5 sm:gap-2 px-2 sm:px-3 py-1.5 rounded-lg border text-xs font-mono font-medium transition-all duration-200 shrink-0 ${
            isLiveMode
              ? 'bg-emerald-500/10 border-emerald-500/40 text-emerald-300 shadow-[0_0_12px_rgba(16,185,129,0.2)]'
              : 'bg-amber-500/10 border-amber-500/40 text-amber-300 shadow-[0_0_12px_rgba(245,158,11,0.2)]'
          }`}
          title="Click to toggle between FastAPI live backend and Offline Demo mode"
        >
          {isLiveMode ? (
            <>
              <Radio className="w-3.5 h-3.5 text-emerald-400 animate-pulse shrink-0" />
              <span className="hidden sm:inline">LIVE API</span>
            </>
          ) : (
            <>
              <Layers className="w-3.5 h-3.5 text-amber-400 shrink-0" />
              <span className="hidden sm:inline">DEMO MODE</span>
            </>
          )}
        </button>

        {/* Refresh button */}
        <button
          onClick={refreshData}
          disabled={isLoading}
          className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 transition shrink-0"
          title="Refresh backend telemetry"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
        </button>
      </div>
    </header>
  );
};
