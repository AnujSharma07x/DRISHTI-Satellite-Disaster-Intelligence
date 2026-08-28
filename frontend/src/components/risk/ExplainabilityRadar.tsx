import React from 'react';
import { useDisaster } from '../../context/DisasterContext';
import { RISK_WEIGHTS, RISK_CAPS } from '../../data/constants';
import { Shield, Droplet, Users, Building2, Route } from 'lucide-react';

export const ExplainabilityRadar: React.FC = () => {
  const { activeScenario } = useDisaster();

  // Compute components based on Engineer 4's exact locked formula in risk/risk_engine.py:
  // flood_severity = clamp(100 * flood_level / 5.0)
  // population_exposure = clamp(100 * pop / 50000)
  // infrastructure_importance = clamp(100 * hospitals / 5)
  // accessibility = clamp(100 * roads_count / 30)
  const floodLevel = activeScenario?.flood_level || 3.0;
  const pop = activeScenario?.population_affected || 12500;
  const hospitals = activeScenario?.hospitals_affected || 3;
  const roadsCount = activeScenario?.roads_affected_count || 18;

  const severityScore = Math.min(100, Math.round((floodLevel / RISK_CAPS.flood_level_m) * 100));
  const popScore = Math.min(100, Math.round((pop / RISK_CAPS.population_affected) * 100));
  const infraScore = Math.min(100, Math.round((hospitals / RISK_CAPS.hospitals_affected) * 100));
  const accessScore = Math.min(100, Math.round((roadsCount / 25) * 100));

  const factors = [
    {
      name: 'Flood Severity',
      weight: '30%',
      score: severityScore,
      icon: Droplet,
      color: 'bg-sky-500',
      textColor: 'text-sky-400',
      description: `${floodLevel.toFixed(1)}m elevation depth`,
    },
    {
      name: 'Population Exposure',
      weight: '30%',
      score: popScore,
      icon: Users,
      color: 'bg-rose-500',
      textColor: 'text-rose-400',
      description: `${pop.toLocaleString()} people in danger zone`,
    },
    {
      name: 'Critical Infrastructure',
      weight: '25%',
      score: infraScore,
      icon: Building2,
      color: 'bg-amber-500',
      textColor: 'text-amber-400',
      description: `${hospitals} hospitals compromised`,
    },
    {
      name: 'Road Accessibility',
      weight: '15%',
      score: accessScore,
      icon: Route,
      color: 'bg-emerald-500',
      textColor: 'text-emerald-400',
      description: `${roadsCount} road segments severed`,
    },
  ];

  return (
    <div className="p-4 bg-slate-900/80 backdrop-blur-md rounded-2xl border border-slate-800 shadow-xl space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-bold font-mono tracking-wider text-slate-200 uppercase flex items-center gap-1.5">
          <Shield className="w-3.5 h-3.5 text-cyan-400" />
          4-Factor Explainability Breakdown
        </h4>
        <span className="text-[10px] text-slate-500 font-mono">Weighted Model</span>
      </div>

      <div className="space-y-2.5">
        {factors.map(({ name, weight, score, icon: Icon, color, textColor, description }) => (
          <div key={name} className="space-y-1">
            <div className="flex items-center justify-between text-xs">
              <span className="flex items-center gap-1.5 font-medium text-slate-300">
                <Icon className={`w-3.5 h-3.5 ${textColor}`} /> {name}
                <span className="text-[10px] text-slate-500 font-mono">({weight})</span>
              </span>
              <span className="font-mono text-xs font-bold text-slate-200">{score}/100</span>
            </div>

            <div className="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${color}`}
                style={{ width: `${score}%` }}
              />
            </div>

            <span className="text-[10px] text-slate-500 font-mono block truncate">
              {description}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};
