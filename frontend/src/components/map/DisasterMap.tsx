import React, { useEffect, useMemo } from 'react';
import {
  MapContainer,
  TileLayer,
  GeoJSON,
  Marker,
  Popup,
  Polyline,
  useMap,
} from 'react-leaflet';
import L from 'leaflet';

import { useDisaster } from '../../context/DisasterContext';
import { LayerControl } from './LayerControl';
import { getBoundsFromGeoJSON, normalizeGeoJSON } from '../../utils/geoUtils';
import { normalizeRiskLevel, getRiskColor } from '../../utils/riskNormalizer';
import { formatArea, formatNumber } from '../../utils/formatters';

// Custom Map Bounds Controller
const MapBoundsController: React.FC<{ geojson: any }> = ({ geojson }) => {
  const map = useMap();

  useEffect(() => {
    if (!geojson) return;

    try {
      const bounds = getBoundsFromGeoJSON(geojson);

      if (bounds && bounds.isValid()) {
        map.fitBounds(bounds, {
          padding: [40, 40],
          maxZoom: 14,
          animate: true,
        });
      }
    } catch {
      // Ignore boundary errors
    }
  }, [geojson, map]);

  return null;
};

// Custom SVG Icons for facilities
function createFacilityIcon(
  type: string,
  isAccessible: boolean = true
) {
  const color = !isAccessible
    ? '#EF4444'
    : type === 'hospital'
    ? '#06B6D4'
    : type === 'relief_centre'
    ? '#10B981'
    : type === 'fire_station'
    ? '#F59E0B'
    : '#3B82F6';

  const svg = `
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      width="32"
      height="32"
    >
      <defs>
        <filter
          id="shadow"
          x="-20%"
          y="-20%"
          width="140%"
          height="140%"
        >
          <feDropShadow
            dx="0"
            dy="2"
            stdDeviation="3"
            flood-color="#000000"
            flood-opacity="0.6"
          />
        </filter>
      </defs>

      <circle
        cx="12"
        cy="12"
        r="11"
        fill="#0F172A"
        stroke="${color}"
        stroke-width="2"
        filter="url(#shadow)"
      />

      <circle
        cx="12"
        cy="12"
        r="8"
        fill="${color}"
        fill-opacity="0.25"
      />

      <circle
        cx="12"
        cy="12"
        r="4"
        fill="${color}"
      />
    </svg>
  `;

  return L.divIcon({
    html: svg,
    className: 'custom-facility-marker',
    iconSize: [32, 32],
    iconAnchor: [16, 16],
    popupAnchor: [0, -16],
  });
}

export const DisasterMap: React.FC = () => {
  const {
    selectedRegion,
    floodPrediction,
    activeScenario,
    riskZones,
    facilities,
    activeRoute,
    visibleLayers,
    selectedZoneId,
    setSelectedZoneId,
  } = useDisaster();

  // --------------------------------------------------
  // Normalize GeoJSON layers
  // --------------------------------------------------

  const regionGeoJSON = useMemo(
    () => normalizeGeoJSON(selectedRegion?.geometry),
    [selectedRegion]
  );

  const floodGeoJSON = useMemo(
    () => normalizeGeoJSON(floodPrediction?.geometry),
    [floodPrediction]
  );

  const simulationGeoJSON = useMemo(
    () => normalizeGeoJSON(activeScenario?.result_geometry),
    [activeScenario]
  );

  // Focus bounds:
  // Simulation -> Flood Prediction -> Region
  const focusGeometry = useMemo(() => {
    return (
      simulationGeoJSON ||
      floodGeoJSON ||
      regionGeoJSON
    );
  }, [
    simulationGeoJSON,
    floodGeoJSON,
    regionGeoJSON,
  ]);

  // Initial map center
  const defaultCenter: [number, number] = [
    26.28,
    92.32,
  ];
  // Dark OSM map styling
const darkMapStyle = `
  .dark-osm-tiles {
    filter:
      invert(90%)
      hue-rotate(180deg)
      brightness(75%)
      contrast(105%)
      saturate(70%);
  }
`;

  return (
    <div className="relative w-full h-full bg-[#0B0F17] overflow-hidden">
     <style>{darkMapStyle}</style>
      <MapContainer
        center={defaultCenter}
        zoom={12}
        zoomControl={false}
        className="w-full h-full z-0"
      >

        {/* ==================================================
            DARK BASE MAP
            ================================================== */}

        <TileLayer
  url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
  attribution='&copy; OpenStreetMap contributors'
  maxZoom={19}
  className="dark-osm-tiles"
/>

        {/* Auto fit bounds */}
        <MapBoundsController
          geojson={focusGeometry}
        />

        {/* ==================================================
            1. STUDY REGION BOUNDARY
            ================================================== */}

        {visibleLayers.regionBoundary &&
          regionGeoJSON && (
            <GeoJSON
              key={`region-${selectedRegion?.id}`}
              data={regionGeoJSON}
              style={{
                color: '#00E5FF',
                weight: 2,
                dashArray: '6, 6',
                fillOpacity: 0.03,
                fillColor: '#00E5FF',
              }}
            />
          )}

        {/* ==================================================
            2. AI FLOOD DETECTION POLYGON
            ================================================== */}

        {visibleLayers.floodPolygon &&
          floodGeoJSON && (
            <GeoJSON
              key={`flood-sar-${floodPrediction?.region_id}-${floodPrediction?.flood_area}`}
              data={floodGeoJSON}
              style={{
                color: '#38BDF8',
                weight: 2,
                fillColor: '#0284C7',
                fillOpacity: 0.45,
              }}
              onEachFeature={(_feature, layer) => {
                const confidence =
                  floodPrediction?.confidence != null
                    ? (floodPrediction.confidence * 100).toFixed(1)
                    : '99.5';

                layer.bindPopup(`
                  <div class="p-2.5 font-sans text-slate-100 bg-slate-900 rounded-lg border border-sky-500/40">

                    <div class="flex items-center gap-1.5 text-xs font-bold text-sky-400 uppercase tracking-wider mb-1">
                      <span class="w-2 h-2 rounded-full bg-sky-400 animate-ping"></span>
                      AI Satellite Flood Extent
                    </div>

                    <div class="text-xs space-y-1 mt-1 text-slate-300">

                      <div>
                        <b>Model:</b>
                        ${floodPrediction?.model_version || 'U-Net SAR'}
                      </div>

                      <div>
                        <b>Confidence:</b>
                        ${confidence}%
                      </div>

                      <div>
                        <b>Inundated Area:</b>
                        ${formatArea(floodPrediction?.flood_area)}
                      </div>

                      <div>
                        <b>Status:</b>
                        ${floodPrediction?.status || 'completed'}
                      </div>

                    </div>
                  </div>
                `);
              }}
            />
          )}

        {/* ==================================================
            3. DIGITAL TWIN SIMULATED INUNDATION
            ================================================== */}

        {visibleLayers.simulationPolygon &&
          simulationGeoJSON && (
            <GeoJSON
              key={`sim-poly-${activeScenario?.scenario_id}-${activeScenario?.flood_level}`}
              data={simulationGeoJSON}
              style={{
                color: '#818CF8',
                weight: 2,
                fillColor: '#4F46E5',
                fillOpacity: 0.4,
              }}
              onEachFeature={(_feature, layer) => {
                layer.bindPopup(`
                  <div class="p-2.5 font-sans text-slate-100 bg-slate-900 rounded-lg border border-indigo-500/40">

                    <div class="text-xs font-bold text-indigo-400 uppercase tracking-wider mb-1">
                      Digital Twin Inundation Scenario
                    </div>

                    <div class="text-xs space-y-1 mt-1 text-slate-300">

                      <div>
                        <b>Water Level:</b>
                        ${activeScenario?.flood_level?.toFixed(1) ?? 'N/A'} m
                      </div>

                      <div>
                        <b>Flooded Area:</b>
                        ${formatArea(activeScenario?.flooded_area)}
                      </div>

                      <div>
                        <b>Pop. Affected:</b>
                        ${formatNumber(activeScenario?.population_affected)}
                      </div>

                      <div>
                        <b>Roads Cut:</b>
                        ${formatNumber(activeScenario?.roads_affected_count)} segments
                      </div>

                    </div>
                  </div>
                `);
              }}
            />
          )}

        {/* ==================================================
            4. RISK ZONES
            ================================================== */}

        {visibleLayers.riskZones &&
          riskZones.map((zone) => {
            const normalized = normalizeRiskLevel(
              zone.risk_level
            );

            const colors = getRiskColor(normalized);

            const isSelected =
              selectedZoneId === zone.id;

            return (
              <GeoJSON
                key={`risk-zone-${zone.id}-${isSelected}`}
                data={normalizeGeoJSON(zone.geometry)}
                style={{
                  color: isSelected
                    ? '#FFFFFF'
                    : colors.hex,

                  weight: isSelected ? 3 : 2,

                  dashArray: isSelected
                    ? '4, 4'
                    : undefined,

                  fillColor: colors.hex,

                  fillOpacity: isSelected
                    ? 0.5
                    : 0.3,
                }}
                eventHandlers={{
                  click: () =>
                    setSelectedZoneId(zone.id),
                }}
                onEachFeature={(_feature, layer) => {
                  const riskScore =
                    (zone.risk_score || 0.85) *
                    (
                      zone.risk_score &&
                      zone.risk_score <= 1.0
                        ? 100
                        : 1
                    );

                  layer.bindPopup(`
                    <div
                      class="p-2.5 font-sans text-slate-100 bg-slate-900 rounded-lg border"
                      style="border-color: ${colors.hex}"
                    >

                      <div class="flex items-center justify-between gap-2 mb-1">

                        <span
                          class="text-xs font-bold tracking-wider uppercase font-mono"
                          style="color: ${colors.hex}"
                        >
                          ZONE ${zone.id}
                        </span>

                        <span
                          class="text-[10px] px-1.5 py-0.5 rounded font-mono font-bold"
                          style="
                            background-color: ${colors.hex}33;
                            color: ${colors.hex};
                          "
                        >
                          ${normalized}
                        </span>

                      </div>

                      <div class="text-xs space-y-1 text-slate-300 mt-1.5">

                        <div>
                          <b>Risk Score:</b>
                          ${riskScore.toFixed(0)} / 100
                        </div>

                        <div>
                          <b>Exposed Pop:</b>
                          ${formatNumber(
                            zone.population_exposed || 12000
                          )}
                        </div>

                        <div>
                          <b>Key Driver:</b>
                          ${
                            zone.primary_reason ||
                            'High Vulnerability Sector'
                          }
                        </div>

                      </div>

                    </div>
                  `);
                }}
              />
            );
          })}

        {/* ==================================================
            5. CRITICAL INFRASTRUCTURE
            ================================================== */}

        {visibleLayers.infrastructure &&
          facilities.map((fac) => {

            const lat =
              fac.latitude ??
              (
                fac.geometry?.coordinates
                  ? fac.geometry.coordinates[1]
                  : null
              );

            const lng =
              fac.longitude ??
              (
                fac.geometry?.coordinates
                  ? fac.geometry.coordinates[0]
                  : null
              );

            if (
              lat === null ||
              lat === undefined ||
              lng === null ||
              lng === undefined
            ) {
              return null;
            }

            return (
              <Marker
                key={fac.id}
                position={[lat, lng]}
                icon={createFacilityIcon(
                  fac.type,
                  fac.is_accessible
                )}
              >

                <Popup>

                  <div className="p-2 text-slate-100 bg-slate-900 rounded border border-slate-700">

                    <div className="text-xs font-bold text-cyan-300">
                      {fac.name}
                    </div>

                    <div className="text-[11px] text-slate-400 capitalize mt-0.5">
                      Type: {fac.type.replace('_', ' ')}
                    </div>

                    <div className="mt-1">

                      <span
                        className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${
                          fac.is_accessible
                            ? 'bg-emerald-500/20 text-emerald-300'
                            : 'bg-rose-500/20 text-rose-300'
                        }`}
                      >
                        {fac.is_accessible
                          ? 'ACCESSIBLE'
                          : 'FLOOD BLOCKED'}
                      </span>

                    </div>

                  </div>

                </Popup>

              </Marker>
            );
          })}

        {/* ==================================================
            6. EVACUATION ROUTE
            ================================================== */}

        {visibleLayers.evacuationRoute &&
          activeRoute?.route_geometry?.coordinates &&
          activeRoute.route_geometry.coordinates.length > 0 && (

            <Polyline
              positions={activeRoute.route_geometry.coordinates.map(
                ([lng, lat]: [number, number]) => [
                  lat,
                  lng,
                ]
              )}

              pathOptions={{
                color:
                  activeRoute.used_flooded_road
                    ? '#EF4444'
                    : '#10B981',

                weight: 4,

                opacity: 0.9,

                dashArray:
                  activeRoute.used_flooded_road
                    ? '8, 6'
                    : undefined,
              }}
            >

              <Popup>

                <div className="p-2 text-slate-100 bg-slate-900 rounded border border-emerald-500/40">

                  <div className="text-xs font-bold text-emerald-400">
                    Emergency Evacuation Corridor
                  </div>

                  <div className="text-xs text-slate-300 mt-1 space-y-0.5">

                    <div>
                      <b>Destination:</b>{' '}
                      {activeRoute.recommended_facility_name}
                    </div>

                    <div>
                      <b>Distance:</b>{' '}
                      {activeRoute.estimated_distance_km} km
                    </div>

                    <div>
                      <b>Est. Time:</b>{' '}
                      {activeRoute.estimated_time_minutes} min
                    </div>

                    {activeRoute.used_flooded_road && (
                      <div className="text-rose-400 font-bold mt-1">
                        ⚠️ WARNING: Route crosses flooded road segments
                      </div>
                    )}

                  </div>

                </div>

              </Popup>

            </Polyline>
          )}

      </MapContainer>

      {/* ==================================================
          FLOATING HUD LAYER CONTROLLER
          ================================================== */}

      <LayerControl />

      {/* ==================================================
          MAP LEGEND
          ================================================== */}

      <div className="absolute bottom-4 left-4 z-[1000] p-3 bg-slate-900/90 backdrop-blur-md border border-slate-800 rounded-xl text-xs space-y-1.5 shadow-xl select-none hidden sm:block">

        <div className="text-[10px] font-mono text-slate-400 uppercase tracking-wider mb-1">
          Map Legend
        </div>

        <div className="flex items-center gap-2 text-slate-300 text-[11px]">
          <span className="w-3.5 h-3.5 rounded bg-sky-500/40 border border-sky-400" />
          <span>AI Flood Extent (Sentinel-1)</span>
        </div>

        <div className="flex items-center gap-2 text-slate-300 text-[11px]">
          <span className="w-3.5 h-3.5 rounded bg-indigo-500/40 border border-indigo-400" />
          <span>Simulated Inundation</span>
        </div>

        <div className="flex items-center gap-2 text-slate-300 text-[11px]">
          <span className="w-3.5 h-3.5 rounded bg-rose-500/40 border border-rose-400" />
          <span>High/Critical Risk Zone</span>
        </div>

        <div className="flex items-center gap-2 text-slate-300 text-[11px]">
          <span className="w-4 h-1 rounded bg-emerald-400" />
          <span>Safe Evacuation Route</span>
        </div>

      </div>

    </div>
  );
};