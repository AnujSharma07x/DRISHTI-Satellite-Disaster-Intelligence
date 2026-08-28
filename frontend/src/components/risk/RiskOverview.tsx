import React from 'react';
import { useDisaster } from '../../context/DisasterContext';
import { Badge } from '../common/Badge';
import { normalizeRiskLevel, getRiskColor } from '../../utils/riskNormalizer';
import { ShieldAlert, Activity } from 'lucide-react';

export const RiskOverview: React.FC = () => {
  const { priorityZones, activeScenario } = useDisaster();

  // Compute average or top priority risk score
  const topZone = priorityZones[0];
  const avgScore = topZone ? topZone.risk_score : 78;
  const normalizedLevel = topZone ? topZone.risk_level : normalizeRiskLevel('CRITICAL');
  const colors = getRiskColor(normalizedLevel);

  return (
    <div className="p-4 bg-slate-900/80 backdrop-blur-md rounded-2xl border border-slate-800 shadow-xl space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-rose-500/10 text-rose-400 border border-rose-500/20">
            <ShieldAlert className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-xs font-bold font-mono tracking-wider text-slate-100 uppercase">
              District Risk Engine
            </h3>
            <p className="text-[10px] text-slate-400">
              Explainable 4-Factor Assessment
            </p>
          </div>
        </div>

        <Badge level={normalizedLevel} />
      </div>

      {/* Gauge and Score Bar */}
      <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800 space-y-2">
        <div className="flex items-baseline justify-between">
          <span className="text-xs text-slate-400 font-medium">Composite Risk Score</span>
          <div className="flex items-baseline gap-1">
            <span
              className="text-2xl font-black font-mono tracking-tight"
              style={{ color: colors.hex }}
            >
              {avgScore}
            </span>
            <span className="text-xs text-slate-500 font-mono">/ 100</span>
          </div>
        </div>

        {/* Progress Bar */}
        <div className="w-full h-2.5 bg-slate-800 rounded-full overflow-hidden p-0.5">
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{
              width: `${Math.min(100, Math.max(0, avgScore))}%`,
              backgroundColor: colors.hex,
            }}
          />
        </div>

        <div className="flex justify-between text-[9px] font-mono text-slate-500">
          <span>0 (Low)</span>
          <span>40 (Moderate)</span>
          <span>60 (High)</span>
          <span>80+ (Critical)</span>
        </div>
      </div>
    </div>
  );
};
