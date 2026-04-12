import { useMemo } from "react";
import { MapContainer, TileLayer, CircleMarker, Popup, Tooltip, useMap, useMapEvents } from "react-leaflet";
import type { Facility, TransitStop, DesertData, FSA, BoroughScore } from "../types";

const MONTREAL_CENTER: [number, number] = [45.5017, -73.5673];

export type MapCategory = "global" | "healthcare" | "education" | "cultural" | "recreation" | "transport";

const CATEGORY_COLORS: Record<string, string> = {
  healthcare: "#ef4444",
  education: "#3b82f6",
  cultural: "#a855f7",
  recreation: "#22c55e",
};

function densityScoreColor(score: number): string {
  if (score >= 3.5) return "#22c55e";
  if (score >= 2.5) return "#84cc16";
  if (score >= 1.5) return "#eab308";
  if (score >= 0.5) return "#f97316";
  return "#ef4444";
}

function categoryScoreColor(ratio: number): string {
  if (ratio >= 0.9) return "#22c55e";
  if (ratio >= 0.7) return "#84cc16";
  if (ratio >= 0.5) return "#eab308";
  if (ratio >= 0.25) return "#f97316";
  return "#ef4444";
}

function headwayColor(headway: number | null): string {
  if (headway === null) return "#6b7280";
  if (headway < 5) return "#22c55e";
  if (headway < 10) return "#84cc16";
  if (headway < 15) return "#eab308";
  if (headway < 25) return "#f97316";
  return "#ef4444";
}

function transportScore(d: DesertData): number {
  // Normalize: 10+ stops and <10 min headway = good
  const stopScore = Math.min(1, d.stop_count / 10);
  const headwayScore = d.avg_headway != null ? Math.max(0, 1 - d.avg_headway / 30) : 0;
  return stopScore * 0.5 + headwayScore * 0.5;
}

function getFsaColor(d: DesertData, category: MapCategory): string {
  if (category === "global") {
    return densityScoreColor(d.density_score ?? d.score);
  }
  if (category === "transport") {
    return categoryScoreColor(transportScore(d));
  }
  const detail = d.category_details?.find((cd) => cd.category === category);
  return categoryScoreColor(detail ? detail.adequacy_ratio : 0);
}

function FlyToBorough({ fsas, borough }: { fsas: FSA[]; borough: string | null }) {
  const map = useMap();
  useMemo(() => {
    if (!borough) return;
    const boroughFsas = fsas.filter((f) => f.borough === borough);
    if (boroughFsas.length === 0) return;
    const lats = boroughFsas.map((f) => f.latitude);
    const lons = boroughFsas.map((f) => f.longitude);
    const bounds: [[number, number], [number, number]] = [
      [Math.min(...lats) - 0.005, Math.min(...lons) - 0.008],
      [Math.max(...lats) + 0.005, Math.max(...lons) + 0.008],
    ];
    map.fitBounds(bounds, { padding: [20, 20] });
  }, [borough, fsas, map]);
  return null;
}

function MapClickHandler({ onClick }: { onClick?: (lat: number, lon: number) => void }) {
  useMapEvents({
    click(e) {
      if (onClick) {
        onClick(e.latlng.lat, e.latlng.lng);
      }
    },
  });
  return null;
}

interface Props {
  facilities: Facility[];
  stops: TransitStop[];
  deserts: DesertData[];
  fsas: FSA[];
  selectedBorough: string | null;
  boroughScore: BoroughScore | null;
  onMapClick?: (lat: number, lon: number) => void;
  onFsaClick?: (borough: string) => void;
  category: MapCategory;
  showFacilities: boolean;
  showStops: boolean;
}

export function MapView({
  facilities,
  stops,
  deserts,
  fsas,
  selectedBorough,
  boroughScore,
  onMapClick,
  onFsaClick,
  category,
  showFacilities,
  showStops,
}: Props) {
  // Filter facilities by selected category
  const filteredFacilities = useMemo(() => {
    if (!showFacilities) return [];
    if (category === "global" || category === "transport") return facilities;
    return facilities.filter((f) => f.category === category);
  }, [facilities, category, showFacilities]);

  const filteredStops = useMemo(() => {
    if (!showStops) return [];
    if (category === "transport") return stops; // show all when transport selected
    if (category !== "global") return []; // hide stops when specific facility category
    return stops;
  }, [stops, category, showStops]);

  return (
    <MapContainer center={MONTREAL_CENTER} zoom={11} zoomControl={true}>
      <TileLayer
        attribution='&copy; <a href="https://carto.com/">CARTO</a>'
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
      />
      <FlyToBorough fsas={fsas} borough={selectedBorough} />
      <MapClickHandler onClick={onMapClick} />

      {/* FSA zone circles colored by selected category */}
      {deserts.map((d) => {
        const color = getFsaColor(d, category);
        return (
          <CircleMarker
            key={`desert-${d.postal_code}`}
            center={[d.latitude, d.longitude]}
            radius={Math.max(8, Math.sqrt(d.population) / 8)}
            pathOptions={{
              color,
              fillColor: color,
              fillOpacity: 0.35,
              weight: 1.5,
            }}
            eventHandlers={{
              click: (e) => {
                e.originalEvent.stopPropagation();
                onFsaClick?.(d.borough);
              },
            }}
          >
            <Tooltip
              direction="center"
              permanent
              className="fsa-label"
            >
              {d.postal_code}
            </Tooltip>
            <Popup>
              <strong>{d.postal_code}</strong> &mdash; {d.borough}<br />
              Density Score: <strong>{(d.density_score ?? d.score).toFixed(1)}/4</strong><br />
              Population: {d.population.toLocaleString()}<br />
              Stops nearby: {d.stop_count}<br />
              Healthcare: {d.healthcare} | Education: {d.education}<br />
              Cultural: {d.cultural} | Recreation: {d.recreation}
              {d.category_details && (
                <>
                  <br /><br />
                  {d.category_details.map((cd) => (
                    <span key={cd.category}>
                      {cd.category}: {cd.actual}/{cd.expected} needed ({Math.round(cd.adequacy_ratio * 100)}%)<br />
                    </span>
                  ))}
                </>
              )}
            </Popup>
          </CircleMarker>
        );
      })}

      {/* Transit stops */}
      {filteredStops.map((s) => (
        <CircleMarker
          key={`stop-${s.stop_id}-${s.agency}`}
          center={[s.stop_lat, s.stop_lon]}
          radius={3}
          pathOptions={{
            color: headwayColor(s.avg_headway_min),
            fillColor: headwayColor(s.avg_headway_min),
            fillOpacity: 0.7,
            weight: 0.5,
          }}
        >
          <Popup>
            <strong>{s.stop_name}</strong><br />
            Agency: {s.agency}<br />
            Headway: {s.avg_headway_min ? `${s.avg_headway_min.toFixed(1)} min` : "N/A"}<br />
            Wheelchair: {s.wheelchair_boarding === 1 ? "Yes" : "No"}
          </Popup>
        </CircleMarker>
      ))}

      {/* Facilities */}
      {filteredFacilities.map((f, i) => (
        <CircleMarker
          key={`fac-${i}`}
          center={[f.lat, f.lon]}
          radius={5}
          pathOptions={{
            color: CATEGORY_COLORS[f.category] ?? "#6b7280",
            fillColor: CATEGORY_COLORS[f.category] ?? "#6b7280",
            fillOpacity: 0.9,
            weight: 1,
          }}
        >
          <Popup>
            <strong>{f.facility_name}</strong><br />
            {f.category} &mdash; {f.facility_type}
          </Popup>
        </CircleMarker>
      ))}

      {/* Highlight borough FSA scores when selected */}
      {boroughScore?.fsa_scores.map((s) => {
        const ds = s.density_score ?? s.score;
        const color = densityScoreColor(ds);
        return (
          <CircleMarker
            key={`bscore-${s.postal_code}`}
            center={[s.latitude, s.longitude]}
            radius={14}
            pathOptions={{
              color,
              fillColor: color,
              fillOpacity: 0.4,
              weight: 2.5,
            }}
          >
            <Popup>
              <strong>{s.postal_code}</strong> &mdash; {s.fsa_name}<br />
              Density Score: <strong style={{ color }}>{ds.toFixed(1)}/4</strong><br />
              Population: {s.population.toLocaleString()}<br />
              Stops: {s.stop_count} | Headway: {s.avg_headway_min ?? "N/A"} min<br />
              Wheelchair: {s.wheelchair_pct}%<br />
              {s.category_details && s.category_details.map((cd) => (
                <span key={cd.category}>
                  {cd.category}: {cd.actual}/{cd.expected} needed ({Math.round(cd.adequacy_ratio * 100)}%)<br />
                </span>
              ))}
              {s.missing.length > 0 && <>Missing: <strong>{s.missing.join(", ")}</strong></>}
            </Popup>
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
}
