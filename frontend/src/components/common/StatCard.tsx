import React from 'react';
import { LucideIcon } from 'lucide-react';

interface StatCardProps {
  title: string;
  value: string | number;
  unit?: string;
  subtext?: string;
  icon: LucideIcon;
  variant?: 'cyan' | 'blue' | 'rose' | 'amber' | 'emerald' | 'slate';
  delta?: string;
  deltaType?: 'increase' | 'decrease' | 'neutral';
}

export const StatCard: React.FC<StatCardProps> = ({
  title,
  value,
  unit,
  subtext,
  icon: Icon,
  variant = 'cyan',
  delta,
  deltaType = 'neutral',
}) => {
  const variantStyles = {
    cyan: {
      border: 'border-cyan-500/20 hover:border-cyan-500/40',
      iconBg: 'bg-cyan-500/10 text-cyan-400',
      glow: 'hover:shadow-[0_0_15px_rgba(6,182,212,0.15)]',
      valueColor: 'text-cyan-100',
    },
    blue: {
      border: 'border-blue-500/20 hover:border-blue-500/40',
      iconBg: 'bg-blue-500/10 text-blue-400',
      glow: 'hover:shadow-[0_0_15px_rgba(59,130,246,0.15)]',
      valueColor: 'text-blue-100',
    },
    rose: {
      border: 'border-rose-500/20 hover:border-rose-500/40',
      iconBg: 'bg-rose-500/10 text-rose-400',
      glow: 'hover:shadow-[0_0_15px_rgba(244,63,94,0.15)]',
      valueColor: 'text-rose-100',
    },
    amber: {
      border: 'border-amber-500/20 hover:border-amber-500/40',
      iconBg: 'bg-amber-500/10 text-amber-400',
      glow: 'hover:shadow-[0_0_15px_rgba(245,158,11,0.15)]',
      valueColor: 'text-amber-100',
    },
    emerald: {
      border: 'border-emerald-500/20 hover:border-emerald-500/40',
      iconBg: 'bg-emerald-500/10 text-emerald-400',
      glow: 'hover:shadow-[0_0_15px_rgba(16,185,129,0.15)]',
      valueColor: 'text-emerald-100',
    },
    slate: {
      border: 'border-slate-700/60 hover:border-slate-600',
      iconBg: 'bg-slate-800 text-slate-300',
      glow: '',
      valueColor: 'text-slate-100',
    },
  }[variant];

  return (
    <div
      className={`relative p-3.5 bg-slate-900/80 backdrop-blur-md rounded-xl border ${variantStyles.border} ${variantStyles.glow} transition-all duration-200`}
    >
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <span className="text-[11px] font-medium tracking-wider text-slate-400 uppercase">
          {title}
        </span>
        <div className={`p-1.5 rounded-lg ${variantStyles.iconBg}`}>
          <Icon className="w-4 h-4" />
        </div>
      </div>

      <div className="flex items-baseline gap-1.5">
        <span className={`text-xl font-bold font-mono ${variantStyles.valueColor}`}>
          {value}
        </span>
        {unit && <span className="text-xs text-slate-400 font-mono">{unit}</span>}
      </div>

      {(subtext || delta) && (
        <div className="flex items-center justify-between mt-1 text-[11px] text-slate-400">
          {subtext && <span className="truncate">{subtext}</span>}
          {delta && (
            <span
              className={`font-mono text-[10px] px-1 rounded ${
                deltaType === 'increase'
                  ? 'text-rose-400 bg-rose-500/10'
                  : deltaType === 'decrease'
                  ? 'text-emerald-400 bg-emerald-500/10'
                  : 'text-slate-400'
              }`}
            >
              {delta}
            </span>
          )}
        </div>
      )}
    </div>
  );
};
