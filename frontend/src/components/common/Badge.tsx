import React from 'react';
import { NormalizedRiskLevel } from '../../types/risk';
import { getRiskColor } from '../../utils/riskNormalizer';

interface BadgeProps {
  level?: NormalizedRiskLevel | string;
  variant?: 'risk' | 'status' | 'neutral';
  children?: React.ReactNode;
  className?: string;
  size?: 'sm' | 'md' | 'lg';
}

export const Badge: React.FC<BadgeProps> = ({
  level,
  variant = 'risk',
  children,
  className = '',
  size = 'md',
}) => {
  const sizeClasses = {
    sm: 'text-[10px] px-1.5 py-0.5',
    md: 'text-xs px-2.5 py-1',
    lg: 'text-sm px-3 py-1.5',
  }[size];

  if (variant === 'risk' && level) {
    const colors = getRiskColor(level as NormalizedRiskLevel);
    return (
      <span
        className={`inline-flex items-center gap-1.5 font-mono font-semibold rounded border uppercase tracking-wider ${colors.bg} ${colors.text} ${colors.border} ${sizeClasses} ${className}`}
      >
        <span
          className="w-1.5 h-1.5 rounded-full"
          style={{ backgroundColor: colors.fill }}
        />
        {children || level}
      </span>
    );
  }

  return (
    <span
      className={`inline-flex items-center font-mono font-medium rounded border border-slate-700 bg-slate-800/60 text-slate-300 ${sizeClasses} ${className}`}
    >
      {children}
    </span>
  );
};
