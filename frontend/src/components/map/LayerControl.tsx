import React from 'react';
import { useDisaster } from '../../context/DisasterContext';
import { TILE_LAYERS } from '../../data/constants';
import {
  Layers,
  Map as MapIcon,
  Eye,
  EyeOff,
  ShieldAlert,
  Building2,
  Navigation,
  Droplets,
  Waves,
} from 'lucide-react';

export const LayerControl: React.FC = () => {
  const { visibleLayers, toggleLayer, tileLayer, setTileLayer } = useDisaster();
  const [isOpen, setIsOpen] = React.useState(false);

  const layerItems = [
    {
      key: 'regionBoundary' as const,
      label: 'Region Boundary',
      icon: MapIcon,
      color: 'text-cyan-400',
    },
    {
      key: 'floodPolygon' as const,
      label: 'AI Flood Extent (SAR)',
      icon: Droplets,
      color: 'text-sky-400',
    },
    {
      key: 'simulationPolygon' as const,
      label: 'Simulated Inundation',
      icon: Waves,
      color: 'text-indigo-400',
    },
    {
      key: 'riskZones' as const,
      label: 'Risk Zones (Priority)',
      icon: ShieldAlert,
      color: 'text-amber-400',
    },
    {
      key: 'infrastructure' as const,
      label: 'Critical Facilities',
      icon: Building2,
      color: 'text-emerald-400',
    },
    {
      key: 'evacuationRoute' as const,
      label: 'Evacuation Corridor',
      icon: Navigation,
      color: 'text-rose-400',
    },
  ];

  return (
    <div className="absolute top-3 right-3 sm:top-4 sm:right-4 z-[1000] flex flex-col items-end">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-1.5 sm:gap-2 px-2.5 sm:px-3 py-1.5 sm:py-2 rounded-xl bg-slate-900/90 backdrop-blur-md border border-slate-700/80 text-xs font-mono text-slate-200 hover:text-white shadow-xl transition"
      >
        <Layers className="w-4 h-4 text-cyan-400 shrink-0" />
        <span className="hidden xs:inline">MAP LAYERS</span>
      </button>

      {isOpen && (
        <div className="mt-2 p-3 w-56 xs:w-64 max-w-[calc(100vw-24px)] bg-slate-900/95 backdrop-blur-xl border border-slate-700 rounded-2xl shadow-2xl space-y-3 animate-in fade-in zoom-in-95 duration-150">
          {/* Basemap Selection */}
          <div>
            <span className="text-[10px] font-mono uppercase text-slate-400 tracking-wider">
              Basemap Style
            </span>
            <div className="grid grid-cols-3 gap-1.5 mt-1.5">
              {(Object.keys(TILE_LAYERS) as Array<keyof typeof TILE_LAYERS>).map((key) => (
                <button
                  key={key}
                  onClick={() => setTileLayer(key)}
                  className={`text-[11px] py-1 px-2 rounded-lg border font-mono truncate transition ${
                    tileLayer === key
                      ? 'bg-cyan-500/20 border-cyan-500/50 text-cyan-300 font-semibold'
                      : 'bg-slate-800/60 border-slate-700/60 text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {key === 'cartoDark' ? 'Dark' : key === 'satellite' ? 'Satellite' : 'OSM'}
                </button>
              ))}
            </div>
          </div>

          <div className="border-t border-slate-800" />

          {/* Layer Toggles */}
          <div>
            <span className="text-[10px] font-mono uppercase text-slate-400 tracking-wider">
              Geospatial Layers
            </span>
            <div className="space-y-1.5 mt-1.5">
              {layerItems.map(({ key, label, icon: Icon, color }) => {
                const isVisible = visibleLayers[key];
                return (
                  <button
                    key={key}
                    onClick={() => toggleLayer(key)}
                    className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs font-medium border transition ${
                      isVisible
                        ? 'bg-slate-800/80 border-slate-700 text-slate-100'
                        : 'bg-slate-900/40 border-transparent text-slate-500 hover:bg-slate-800/40'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <Icon className={`w-3.5 h-3.5 ${isVisible ? color : 'text-slate-500'}`} />
                      <span className="text-[11px] truncate">{label}</span>
                    </div>
                    {isVisible ? (
                      <Eye className="w-3.5 h-3.5 text-cyan-400" />
                    ) : (
                      <EyeOff className="w-3.5 h-3.5 text-slate-600" />
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
