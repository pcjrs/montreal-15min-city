import { useMemo } from "react";
import type { DesertData } from "../types";

interface Props {
  deserts: DesertData[];
  onSelectBorough?: (borough: string) => void;
}

const CATEGORIES = [
  { key: "healthcare", label: "Sante", icon: "\u{1F3E5}" },
  { key: "education", label: "Education", icon: "\u{1F393}" },
  { key: "cultural", label: "Culture", icon: "\u{1F3AD}" },
  { key: "recreation", label: "Loisirs", icon: "\u26BD" },
] as const;

const CATEGORY_COLORS: Record<string, string> = {
  healthcare: "#ef4444",
  education: "#3b82f6",
  cultural: "#a855f7",
  recreation: "#22c55e",
};

function scoreColor(score: number): string {
  if (score >= 3.5) return "#22c55e";
  if (score >= 2.5) return "#84cc16";
  if (score >= 1.5) return "#eab308";
  if (score >= 0.5) return "#f97316";
  return "#ef4444";
}

function getMissing(d: DesertData): string[] {
  const missing: string[] = [];
  if (d.healthcare === 0) missing.push("sante");
  if (d.education === 0) missing.push("edu");
  if (d.cultural === 0) missing.push("culture");
  if (d.recreation === 0) missing.push("loisirs");
  return missing;
}

export function StatsView({ deserts, onSelectBorough }: Props) {
  // Triage queue — worst zones
  const triageZones = useMemo(() => {
    return deserts
      .filter((d) => (d.density_score ?? d.score) < 1.5)
      .sort((a, b) => (a.density_score ?? a.score) - (b.density_score ?? b.score))
      .slice(0, 15);
  }, [deserts]);

  const categoryStats = useMemo(() => {
    return CATEGORIES.map(({ key, label, icon }) => {
      let totalAdequacy = 0;
      let belowHalf = 0;
      for (const d of deserts) {
        const detail = d.category_details?.find((cd) => cd.category === key);
        const ratio = detail ? detail.adequacy_ratio : 0;
        totalAdequacy += ratio;
        if (ratio < 0.5) belowHalf++;
      }
      const avgPct = deserts.length > 0 ? Math.round((totalAdequacy / deserts.length) * 100) : 0;
      return { key, label, icon, avgPct, belowHalf };
    });
  }, [deserts]);

  const histogram = useMemo(() => {
    const buckets = Array.from({ length: 9 }, (_, i) => ({
      min: i * 0.5,
      max: (i + 1) * 0.5,
      label: `${(i * 0.5).toFixed(1)}`,
      count: 0,
    }));
    for (const d of deserts) {
      const s = d.density_score ?? d.score;
      const idx = Math.min(8, Math.floor(s / 0.5));
      buckets[idx].count++;
    }
    const maxCount = Math.max(1, ...buckets.map((b) => b.count));
    return { buckets, maxCount };
  }, [deserts]);

  const boroughTable = useMemo(() => {
    const grouped: Record<string, { scores: number[]; pop: number; fsas: number; underserved: number }> = {};
    for (const d of deserts) {
      if (!grouped[d.borough]) grouped[d.borough] = { scores: [], pop: 0, fsas: 0, underserved: 0 };
      const g = grouped[d.borough];
      const s = d.density_score ?? d.score;
      g.scores.push(s);
      g.pop += d.population;
      g.fsas++;
      if (s < 2.5) g.underserved++;
    }
    return Object.entries(grouped)
      .map(([borough, g]) => ({
        borough,
        avgScore: g.scores.reduce((a, b) => a + b, 0) / g.scores.length,
        population: g.pop,
        fsaCount: g.fsas,
        underserved: g.underserved,
      }))
      .sort((a, b) => b.avgScore - a.avgScore);
  }, [deserts]);

  return (
    <div className="stats-view">
      {/* Triage Queue */}
      {triageZones.length > 0 && (
        <>
          <h3>{"\u{1F6A8}"} Triage — Zones critiques</h3>
          <div className="triage-queue">
            {triageZones.map((d) => {
              const s = d.density_score ?? d.score;
              const missing = getMissing(d);
              return (
                <div key={d.postal_code} className="triage-row">
                  <span className="triage-code" style={{ color: scoreColor(s) }}>
                    {d.postal_code}
                  </span>
                  <div className="triage-bar-track">
                    <div
                      className="triage-bar-fill"
                      style={{
                        width: `${(s / 4) * 100}%`,
                        backgroundColor: scoreColor(s),
                      }}
                    />
                  </div>
                  <span className="triage-score" style={{ color: scoreColor(s) }}>
                    {s.toFixed(1)}
                  </span>
                  <span className="triage-missing">
                    {missing.length > 0 ? `manque: ${missing.join(", ")}` : "faible densite"}
                  </span>
                  {onSelectBorough && (
                    <button
                      className="triage-btn"
                      onClick={() => onSelectBorough(d.borough)}
                    >
                      Voir
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}

      <h3>{"\u{1F4CA}"} Couverture par categorie</h3>
      <div className="stats-categories">
        {categoryStats.map((cat) => (
          <div key={cat.key} className="stats-cat-row">
            <div className="stats-cat-label">
              <span>{cat.icon}</span> <strong>{cat.label}</strong>
            </div>
            <div className="stats-cat-info">
              {cat.avgPct}% couverture moyenne &mdash; {cat.belowHalf} zones &lt; 50%
            </div>
            <div className="stats-bar-track">
              <div
                className="stats-bar-fill"
                style={{
                  width: `${cat.avgPct}%`,
                  backgroundColor: CATEGORY_COLORS[cat.key],
                }}
              />
            </div>
          </div>
        ))}
      </div>

      <h3>Distribution des scores</h3>
      <div className="histogram">
        {histogram.buckets.map((b) => (
          <div key={b.label} className="histogram-col">
            <div className="histogram-bar-container">
              <div
                className="histogram-bar"
                style={{
                  height: `${(b.count / histogram.maxCount) * 100}%`,
                  backgroundColor: scoreColor(b.min + 0.25),
                }}
              />
            </div>
            <div className="histogram-count">{b.count}</div>
            <div className="histogram-label">{b.label}</div>
          </div>
        ))}
      </div>

      <h3>Arrondissements</h3>
      <div className="borough-table-container">
        <table className="borough-table">
          <thead>
            <tr>
              <th>Arrondissement</th>
              <th>Score</th>
              <th>Population</th>
              <th>FSAs</th>
              <th>Sous-desservi</th>
            </tr>
          </thead>
          <tbody>
            {boroughTable.map((row) => (
              <tr
                key={row.borough}
                style={{ cursor: onSelectBorough ? "pointer" : undefined }}
                onClick={() => onSelectBorough?.(row.borough)}
              >
                <td className="borough-name">{row.borough}</td>
                <td>
                  <span className="score-pill" style={{ color: scoreColor(row.avgScore) }}>
                    {row.avgScore.toFixed(1)}
                  </span>
                </td>
                <td>{row.population.toLocaleString()}</td>
                <td>{row.fsaCount}</td>
                <td>
                  {row.underserved > 0 ? (
                    <span style={{ color: "#ef4444" }}>{row.underserved}</span>
                  ) : (
                    <span style={{ color: "#22c55e" }}>0</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
