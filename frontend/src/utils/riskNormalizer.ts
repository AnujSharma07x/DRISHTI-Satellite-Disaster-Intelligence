import { NormalizedRiskLevel } from '../types/risk';

export function normalizeRiskLevel(rawLevel: string | null | undefined): NormalizedRiskLevel {
  if (!rawLevel) return 'MODERATE';
  const clean = rawLevel.trim().toUpperCase().replace(/[\s-]+/g, '_');
  
  if (clean === 'CRITICAL') return 'CRITICAL';
  if (clean === 'VERY_HIGH' || clean === 'VERYHIGH' || clean === 'SEVERE') return 'VERY_HIGH';
  if (clean === 'HIGH') return 'HIGH';
  if (clean === 'MODERATE' || clean === 'MEDIUM' || clean === 'MED') return 'MODERATE';
  if (clean === 'LOW') return 'LOW';
  
  return 'MODERATE';
}

export function getRiskColor(level: NormalizedRiskLevel): {
  bg: string;
  text: string;
  border: string;
  fill: string;
  glow: string;
  hex: string;
} {
  switch (level) {
    case 'CRITICAL':
      return {
        bg: 'bg-rose-500/15',
        text: 'text-rose-400',
        border: 'border-rose-500/40',
        fill: '#F43F5E',
        glow: 'shadow-[0_0_12px_rgba(244,63,94,0.4)]',
        hex: '#F43F5E',
      };
    case 'VERY_HIGH':
      return {
        bg: 'bg-red-500/15',
        text: 'text-red-400',
        border: 'border-red-500/40',
        fill: '#EF4444',
        glow: 'shadow-[0_0_12px_rgba(239,68,68,0.4)]',
        hex: '#EF4444',
      };
    case 'HIGH':
      return {
        bg: 'bg-orange-500/15',
        text: 'text-orange-400',
        border: 'border-orange-500/40',
        fill: '#F97316',
        glow: 'shadow-[0_0_12px_rgba(249,115,22,0.3)]',
        hex: '#F97316',
      };
    case 'MODERATE':
      return {
        bg: 'bg-amber-500/15',
        text: 'text-amber-400',
        border: 'border-amber-500/40',
        fill: '#F59E0B',
        glow: 'shadow-[0_0_12px_rgba(245,158,11,0.3)]',
        hex: '#F59E0B',
      };
    case 'LOW':
    default:
      return {
        bg: 'bg-emerald-500/15',
        text: 'text-emerald-400',
        border: 'border-emerald-500/40',
        fill: '#10B981',
        glow: 'shadow-[0_0_12px_rgba(16,185,129,0.3)]',
        hex: '#10B981',
      };
  }
}
