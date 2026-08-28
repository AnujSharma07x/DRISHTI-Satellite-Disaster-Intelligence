import React from 'react';
import { useDisaster } from '../../context/DisasterContext';
import { Badge } from '../common/Badge';
import { formatNumber } from '../../utils/formatters';
import { AlertCircle, Navigation, MapPin } from 'lucide-react';

export const PriorityZoneList: React.FC = () => {
  const { priorityZones, selectedZoneId, setSelectedZoneId } = useDisaster();

  return (
    <div className="p-4 bg-slate-900/80 backdrop-blur-md rounded-2xl border border-slate-800 shadow-xl space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-bold font-mono tracking-wider text-slate-200 uppercase flex items-center gap-1.5">
          <AlertCircle className="w-3.5 h-3.5 text-rose-400" />
          Ranked Priority Zones
        </h4>
        <span className="text-[10px] text-slate-500 font-mono">
          {priorityZones.length} Sectors Scored
        </span>
      </div>

      <div className="space-y-2 max-h-56 overflow-y-auto pr-1 select-none">
        {priorityZones.map((zone) => {
          const isSelected = selectedZoneId === zone.zone_id;

          return (
            <div
              key={zone.zone_id}
              onClick={() => setSelectedZoneId(zone.zone_id)}
              className={`p-2.5 rounded-xl border cursor-pointer transition-all duration-150 flex items-center justify-between gap-2 ${
                isSelected
                  ? 'bg-slate-800 border-cyan-500/60 shadow-[0_0_12px_rgba(6,182,212,0.2)]'
                  : 'bg-slate-950/60 border-slate-800 hover:border-slate-700 hover:bg-slate-800/40'
              }`}
            >
              <div className="flex items-center gap-2.5">
                <div
                  className={`w-6 h-6 rounded-lg font-mono font-bold text-xs flex items-center justify-center ${
                    zone.rank === 1
                      ? 'bg-rose-500/20 text-rose-400 border border-rose-500/40'
                      : zone.rank === 2
                      ? 'bg-orange-500/20 text-orange-400 border border-orange-500/40'
                      : 'bg-slate-800 text-slate-400 border border-slate-700'
                  }`}
                >
                  #{zone.rank}
                </div>

                <div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-bold text-slate-200 truncate max-w-[130px]">
                      {zone.zone_name}
                    </span>
                  </div>
                  <span className="text-[10px] text-slate-400 font-mono">
                    Pop: {formatNumber(zone.population_affected)}
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <Badge level={zone.risk_level} size="sm" />
                <span className="text-xs font-mono font-extrabold text-slate-200">
                  {zone.risk_score}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
