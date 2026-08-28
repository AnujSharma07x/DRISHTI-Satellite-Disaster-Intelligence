import React from 'react';
import { useDisaster } from '../../context/DisasterContext';
import { StatCard } from '../common/StatCard';
import { formatArea, formatNumber } from '../../utils/formatters';
import { Users, Building, Route, Hospital, Droplet } from 'lucide-react';

export const ImpactAssessment: React.FC = () => {
  const { activeScenario } = useDisaster();

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-bold font-mono tracking-wider text-slate-300 uppercase flex items-center gap-1.5">
          <Droplet className="w-3.5 h-3.5 text-indigo-400" />
          Scenario Impact Metrics
        </h3>
        <span className="text-[11px] font-mono text-slate-400">
          Level: {activeScenario?.flood_level ? `${activeScenario.flood_level.toFixed(1)}m` : 'N/A'}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2.5">
        {/* Flooded Area */}
        <StatCard
          title="Inundated Area"
          value={formatArea(activeScenario?.flooded_area)}
          icon={Droplet}
          variant="blue"
          subtext="Total submerged land"
        />

        {/* Population Affected */}
        <StatCard
          title="Exposed Population"
          value={formatNumber(activeScenario?.population_affected)}
          icon={Users}
          variant="rose"
          subtext="Inhabitants in flood zone"
        />

        {/* Roads Cut - IMPORTANT: Segment count, NOT km */}
        <StatCard
          title="Roads Cut Off"
          value={formatNumber(activeScenario?.roads_affected_count)}
          unit="segments"
          icon={Route}
          variant="amber"
          subtext="Intersected segments"
        />

        {/* Hospitals Affected */}
        <StatCard
          title="Hospitals Affected"
          value={formatNumber(activeScenario?.hospitals_affected)}
          icon={Hospital}
          variant="cyan"
          subtext="Critical medical centres"
        />
      </div>
    </div>
  );
};
