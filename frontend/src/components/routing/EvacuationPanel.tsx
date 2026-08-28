import React from 'react';
import { useDisaster } from '../../context/DisasterContext';
import { formatDistance } from '../../utils/formatters';
import {
  Navigation,
  Building2,
  Clock,
  Route,
  AlertTriangle,
  CheckCircle2,
} from 'lucide-react';

export const EvacuationPanel: React.FC = () => {
  const { activeRoute, selectedZoneId } = useDisaster();

  if (!activeRoute) return null;

  return (
    <div className="p-4 bg-slate-900/80 backdrop-blur-md rounded-2xl border border-slate-800 shadow-xl space-y-3.5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <Navigation className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-xs font-bold font-mono tracking-wider text-slate-100 uppercase">
              Emergency Response Plan
            </h3>
            <p className="text-[10px] text-slate-400">
              Flood-Aware Shortest Path Routing
            </p>
          </div>
        </div>

        <span
          className={`text-[10px] px-2 py-0.5 rounded font-mono font-bold border ${
            activeRoute.used_flooded_road
              ? 'bg-rose-500/15 border-rose-500/30 text-rose-400'
              : 'bg-emerald-500/15 border-emerald-500/30 text-emerald-400'
          }`}
        >
          {activeRoute.used_flooded_road ? 'HAZARD CAUTION' : 'CLEAR CORRIDOR'}
        </span>
      </div>

      {/* Target Facility Card */}
      <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800 space-y-1.5">
        <div className="flex items-center justify-between text-xs">
          <span className="text-slate-400 flex items-center gap-1.5">
            <Building2 className="w-3.5 h-3.5 text-cyan-400" />
            Recommended Safe Haven:
          </span>
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 uppercase">
            {activeRoute.recommended_facility_type?.replace('_', ' ') || 'Relief Camp'}
          </span>
        </div>
        <h4 className="text-sm font-bold text-slate-100 truncate">
          {activeRoute.recommended_facility_name || 'District Civil Emergency Hub'}
        </h4>
      </div>

      {/* Route Telemetry KPIs */}
      <div className="grid grid-cols-2 gap-2.5">
        <div className="p-2.5 rounded-xl bg-slate-800/50 border border-slate-700/50">
          <span className="text-[10px] text-slate-400 font-medium uppercase tracking-wider block mb-0.5 flex items-center gap-1">
            <Route className="w-3 h-3 text-cyan-400" /> Road Distance
          </span>
          <span className="text-base font-bold font-mono text-slate-100">
            {formatDistance(activeRoute.estimated_distance_km)}
          </span>
        </div>

        <div className="p-2.5 rounded-xl bg-slate-800/50 border border-slate-700/50">
          <span className="text-[10px] text-slate-400 font-medium uppercase tracking-wider block mb-0.5 flex items-center gap-1">
            <Clock className="w-3 h-3 text-cyan-400" /> Est. Transit Time
          </span>
          <span className="text-base font-bold font-mono text-slate-100">
            {activeRoute.estimated_time_minutes ? `${activeRoute.estimated_time_minutes.toFixed(0)} min` : '15 min'}
          </span>
        </div>
      </div>

      {/* Warning banner if flooded segments were traversed as last resort */}
      {activeRoute.used_flooded_road ? (
        <div className="p-2.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
          <div className="space-y-0.5">
            <span className="font-bold font-mono text-[11px] block">
              WARNING: SUBMERGED CORRIDOR DETECTED
            </span>
            <p className="text-[11px] text-rose-300/90 leading-tight">
              No completely dry road exists. Recommended path navigates shallowest flood fringe as emergency fallback.
            </p>
          </div>
        </div>
      ) : (
        <div className="p-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          <span className="text-[11px]">
            {activeRoute.note || 'Active elevated corridor. Safe for high-clearance emergency dispatch.'}
          </span>
        </div>
      )}
    </div>
  );
};
