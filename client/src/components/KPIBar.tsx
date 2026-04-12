import type { DesertData } from "../types";

function scoreColor(score: number): string {
  if (score >= 3.5) return "#22c55e";
  if (score >= 2.5) return "#84cc16";
  if (score >= 1.5) return "#eab308";
  if (score >= 0.5) return "#f97316";
  return "#ef4444";
}

interface Props {
  deserts: DesertData[];
}

export function KPIBar({ deserts }: Props) {
  const fsaCount = deserts.length;
  const totalPop = deserts.reduce((s, d) => s + d.population, 0);
  const avgScore =
    fsaCount > 0
      ? deserts.reduce((s, d) => s + (d.density_score ?? d.score), 0) / fsaCount
      : 0;

  const fullCoverage = deserts.filter(
    (d) => d.healthcare > 0 && d.education > 0 && d.cultural > 0 && d.recreation > 0
  ).length;
  const coveragePct = fsaCount > 0 ? Math.round((fullCoverage / fsaCount) * 100) : 0;

  const criticalZones = deserts.filter(
    (d) => (d.density_score ?? d.score) < 1.0
  ).length;

  return (
    <div className="kpi-bar">
      <div className="kpi-item">
        <div className="kpi-label">Zones FSA</div>
        <div className="kpi-value">{fsaCount}</div>
      </div>
      <div className="kpi-item">
        <div className="kpi-label">Population</div>
        <div className="kpi-value">{totalPop.toLocaleString()}</div>
      </div>
      <div className="kpi-item">
        <div className="kpi-label">Score moyen</div>
        <div className="kpi-value" style={{ color: scoreColor(avgScore) }}>
          {avgScore.toFixed(1)}/4
        </div>
      </div>
      <div className="kpi-item">
        <div className="kpi-label">Couverture 4/4</div>
        <div
          className="kpi-value"
          style={{ color: coveragePct >= 70 ? "#22c55e" : coveragePct >= 40 ? "#eab308" : "#ef4444" }}
        >
          {coveragePct}%
        </div>
      </div>
      <div className="kpi-item">
        <div className="kpi-label">Zones critiques</div>
        <div className="kpi-value kpi-critical" style={{ color: "#ef4444" }}>
          {criticalZones > 0 && <span className="pulse-dot" />}
          {criticalZones}
        </div>
      </div>
    </div>
  );
}
