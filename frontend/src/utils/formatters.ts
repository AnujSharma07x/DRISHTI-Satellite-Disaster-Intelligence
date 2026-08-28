export function formatNumber(num: number | null | undefined, defaultValue: string = 'N/A'): string {
  if (num === null || num === undefined || isNaN(num)) return defaultValue;
  return new Intl.NumberFormat('en-IN').format(num);
}

export function formatArea(km2: number | null | undefined, defaultValue: string = 'N/A'): string {
  if (km2 === null || km2 === undefined || isNaN(km2)) return defaultValue;
  return `${km2.toFixed(2)} km²`;
}

export function formatDistance(km: number | null | undefined, defaultValue: string = 'N/A'): string {
  if (km === null || km === undefined || isNaN(km)) return defaultValue;
  return `${km.toFixed(1)} km`;
}

export function formatPercent(value: number | null | undefined, defaultValue: string = 'N/A'): string {
  if (value === null || value === undefined || isNaN(value)) return defaultValue;
  // If value is 0-1, convert to 0-100
  const normalized = value <= 1.0 ? value * 100 : value;
  return `${normalized.toFixed(1)}%`;
}

export function formatElevation(meters: number | null | undefined, defaultValue: string = 'N/A'): string {
  if (meters === null || meters === undefined || isNaN(meters)) return defaultValue;
  return `${meters.toFixed(1)} m`;
}
