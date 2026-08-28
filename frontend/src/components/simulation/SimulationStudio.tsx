import React, { useState } from 'react';
import { useDisaster } from '../../context/DisasterContext';
import { Waves, Play, Sparkles, Sliders, RefreshCw } from 'lucide-react';

export const SimulationStudio: React.FC = () => {
  const { activeScenario, isSimulating, runScenarioSimulation } = useDisaster();
  const [sliderLevel, setSliderLevel] = useState<number>(activeScenario?.flood_level || 3.0);

  const presets = [2.5, 3.0, 3.5];

  const handleRun = () => {
    runScenarioSimulation(sliderLevel);
  };

  const handlePreset = (level: number) => {
    setSliderLevel(level);
    runScenarioSimulation(level);
  };

  return (
    <div className="p-4 bg-slate-900/80 backdrop-blur-md rounded-2xl border border-slate-800 shadow-xl space-y-4">
      {/* Studio Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
            <Waves className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-xs font-bold font-mono tracking-wider text-slate-100 uppercase">
              Digital Twin Simulation Studio
            </h3>
            <p className="text-[10px] text-slate-400">
              What-If Inundation Scenario Modeling
            </p>
          </div>
        </div>

        <span className="text-[10px] px-2 py-0.5 rounded font-mono font-bold bg-indigo-500/15 border border-indigo-500/30 text-indigo-300">
          {activeScenario?.status?.toUpperCase() || 'IDLE'}
        </span>
      </div>

      {/* Slider Control */}
      <div className="space-y-2 p-3 bg-slate-950/60 rounded-xl border border-slate-800">
        <div className="flex items-center justify-between text-xs">
          <span className="text-slate-400 flex items-center gap-1.5 font-medium">
            <Sliders className="w-3.5 h-3.5 text-indigo-400" /> Simulated Flood Level:
          </span>
          <span className="font-mono text-base font-extrabold text-indigo-300 bg-indigo-500/10 px-2 py-0.5 rounded border border-indigo-500/30">
            {sliderLevel.toFixed(1)} m
          </span>
        </div>

        <input
          type="range"
          min="0.0"
          max="5.0"
          step="0.1"
          value={sliderLevel}
          disabled={isSimulating}
          onChange={(e) => setSliderLevel(parseFloat(e.target.value))}
          className="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-indigo-500 disabled:opacity-50"
        />

        <div className="flex items-center justify-between text-[10px] font-mono text-slate-500">
          <span>0.0m (Baseline)</span>
          <span>2.5m</span>
          <span>5.0m (Max Severity)</span>
        </div>
      </div>

      {/* Quick Preset Buttons & Run Action */}
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] font-medium text-slate-400">Quick Scenarios:</span>
          <div className="flex items-center gap-1.5">
            {presets.map((level) => (
              <button
                key={level}
                disabled={isSimulating}
                onClick={() => handlePreset(level)}
                className={`text-xs px-2.5 py-1 rounded-lg font-mono border transition ${
                  activeScenario?.flood_level === level
                    ? 'bg-indigo-500/25 border-indigo-500 text-indigo-200 font-bold shadow-[0_0_10px_rgba(99,102,241,0.25)]'
                    : 'bg-slate-800/80 border-slate-700 text-slate-300 hover:text-white hover:bg-slate-700'
                }`}
              >
                {level.toFixed(1)}m
              </button>
            ))}
          </div>
        </div>

        <button
          onClick={handleRun}
          disabled={isSimulating}
          className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl font-mono text-xs font-bold tracking-wider uppercase text-white bg-gradient-to-r from-indigo-600 to-blue-600 hover:from-indigo-500 hover:to-blue-500 border border-indigo-400/40 shadow-[0_0_20px_rgba(79,70,229,0.35)] transition-all duration-200 disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {isSimulating ? (
            <>
              <RefreshCw className="w-4 h-4 animate-spin" />
              <span>Simulating PostGIS Overlay...</span>
            </>
          ) : (
            <>
              <Play className="w-4 h-4 fill-white" />
              <span>Run Scenario Simulation</span>
            </>
          )}
        </button>
      </div>
    </div>
  );
};
