import React from 'react';
import { useDisaster } from '../../context/DisasterContext';
import { formatArea, formatNumber, formatPercent } from '../../utils/formatters';
import { Satellite, ShieldCheck, Activity, Cpu, Database } from 'lucide-react';

export const FloodAnalysisPanel: React.FC = () => {
  const { floodPrediction, inferenceMetadata, selectedRegion } = useDisaster();

  return (
    <div className="p-4 bg-slate-900/80 backdrop-blur-md rounded-2xl border border-slate-800 shadow-xl space-y-4">
      {/* Panel Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-sky-500/10 text-sky-400 border border-sky-500/20">
            <Satellite className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-xs font-bold font-mono tracking-wider text-slate-100 uppercase">
              AI Flood Telemetry
            </h3>
            <p className="text-[10px] text-slate-400">
              Sentinel-1 SAR Change Detection
            </p>
          </div>
        </div>

        <span className="text-[10px] px-2 py-0.5 rounded font-mono font-bold bg-sky-500/15 border border-sky-500/30 text-sky-400">
          {floodPrediction?.status?.toUpperCase() || 'COMPLETED'}
        </span>
      </div>

      {/* Grid of Key AI Metrics */}
      <div className="grid grid-cols-2 gap-2.5">
        <div className="p-2.5 rounded-xl bg-slate-800/50 border border-slate-700/50">
          <span className="text-[10px] text-slate-400 font-medium uppercase tracking-wider block mb-1">
            Detected Flood Area
          </span>
          <span className="text-lg font-bold font-mono text-sky-300">
            {formatArea(floodPrediction?.flood_area)}
          </span>
        </div>

        <div className="p-2.5 rounded-xl bg-slate-800/50 border border-slate-700/50">
          <span className="text-[10px] text-slate-400 font-medium uppercase tracking-wider block mb-1">
            Model Confidence
          </span>
          <span className="text-lg font-bold font-mono text-emerald-300">
            {formatPercent(floodPrediction?.confidence)}
          </span>
        </div>

        <div className="p-2.5 rounded-xl bg-slate-800/50 border border-slate-700/50">
          <span className="text-[10px] text-slate-400 font-medium uppercase tracking-wider block mb-1">
            Flooded Pixels
          </span>
          <span className="text-sm font-bold font-mono text-slate-200">
            {formatNumber(inferenceMetadata?.flooded_pixels)}
          </span>
          <span className="text-[10px] text-slate-500 block mt-0.5 font-mono">
            of {formatNumber(inferenceMetadata?.valid_pixels)} valid
          </span>
        </div>

        <div className="p-2.5 rounded-xl bg-slate-800/50 border border-slate-700/50">
          <span className="text-[10px] text-slate-400 font-medium uppercase tracking-wider block mb-1">
            SAR Drop Threshold
          </span>
          <span className="text-sm font-bold font-mono text-slate-200">
            {inferenceMetadata?.drop_threshold_db ? `${inferenceMetadata.drop_threshold_db.toFixed(1)} dB` : 'N/A'}
          </span>
          <span className="text-[10px] text-slate-500 block mt-0.5 font-mono">
            Backscatter delta
          </span>
        </div>
      </div>

      {/* Model Spec Footer */}
      <div className="p-2.5 rounded-xl bg-slate-950/60 border border-slate-800 text-[11px] text-slate-400 space-y-1 font-mono">
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1.5 text-slate-400">
            <Cpu className="w-3 h-3 text-cyan-400" /> Model Architecture:
          </span>
          <span className="text-slate-200 truncate max-w-[140px]">
            {floodPrediction?.model_version || 'LightUNet-SAR'}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1.5 text-slate-400">
            <Database className="w-3 h-3 text-cyan-400" /> Region Reference:
          </span>
          <span className="text-slate-200">
            {selectedRegion?.name || 'Assam Morigaon'}
          </span>
        </div>
      </div>
    </div>
  );
};
