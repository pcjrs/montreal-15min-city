import { useState, useEffect, useRef } from "react";
import type { BoroughScore, CategoryDetail } from "../types";

const CATEGORY_COLORS: Record<string, string> = {
  healthcare: "#ef4444",
  education: "#3b82f6",
  cultural: "#a855f7",
  recreation: "#22c55e",
};

function scoreLabel(score: number): string {
  if (score >= 3.5) return "Well-Served";
  if (score >= 2.5) return "Adequate";
  if (score >= 1.5) return "Underserved";
  if (score >= 0.5) return "Poorly Served";
  return "Service Desert";
}

function scoreColor(score: number): string {
  if (score >= 3.5) return "#22c55e";
  if (score >= 2.5) return "#84cc16";
  if (score >= 1.5) return "#eab308";
  if (score >= 0.5) return "#f97316";
  return "#ef4444";
}

function AdequacyBar({ detail }: { detail: CategoryDetail }) {
  const pct = Math.round(detail.adequacy_ratio * 100);
  const color = CATEGORY_COLORS[detail.category] ?? "#6b7280";

  return (
    <div className="adequacy-row">
      <span className="adequacy-label">{detail.category}</span>
      <div className="adequacy-bar-track">
        <div
          className="adequacy-bar-fill"
          style={{ width: `${Math.min(100, pct)}%`, backgroundColor: color }}
        />
      </div>
      <span className="adequacy-stat">
        {detail.actual}/{detail.expected} ({pct}%)
      </span>
    </div>
  );
}

interface Props {
  score: BoroughScore;
  loading: boolean;
  onAskAgent?: (query: string) => void;
}

export function ScoreCard({ score, loading, onAskAgent }: Props) {
  const [priority, setPriority] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [displayScore, setDisplayScore] = useState(0);
  const prevBoroughRef = useRef<string | null>(null);

  const avgDensity = score.average_score;

  // Animate score count-up when borough changes
  useEffect(() => {
    if (loading) return;
    if (prevBoroughRef.current === score.borough && displayScore === avgDensity) return;
    prevBoroughRef.current = score.borough;

    const start = 0;
    const end = avgDensity;
    const duration = 400;
    const startTime = performance.now();

    function tick(now: number) {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      // ease-out
      const eased = 1 - (1 - progress) * (1 - progress);
      setDisplayScore(start + (end - start) * eased);
      if (progress < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }, [avgDensity, score.borough, loading]);

  if (loading) {
    return (
      <div className="score-card">
        <div className="step-indicator">
          <div className="step-dots">
            <div className="step-dot" />
            <div className="step-dot" />
            <div className="step-dot" />
          </div>
          <span>Calcul du score...</span>
        </div>
      </div>
    );
  }

  const color = scoreColor(avgDensity);
  const label = scoreLabel(avgDensity);

  const aggregated = ["healthcare", "education", "cultural", "recreation"].map((cat) => {
    let totalActual = 0;
    let totalExpected = 0;
    for (const fsa of score.fsa_scores) {
      const detail = fsa.category_details?.find((d) => d.category === cat);
      if (detail) {
        totalActual += detail.actual;
        totalExpected += detail.expected;
      }
    }
    const ratio = totalExpected > 0 ? Math.min(1, totalActual / totalExpected) : 1;
    return {
      category: cat,
      actual: totalActual,
      expected: totalExpected,
      adequacy_ratio: ratio,
      score: 0,
      present: totalActual > 0,
      count: totalActual,
    } as CategoryDetail;
  });

  const visibleUnderserved = showAll
    ? score.underserved_fsas
    : score.underserved_fsas.slice(0, 3);

  return (
    <div className="score-card">
      <h2>{score.borough}</h2>
      <div style={{ color }}>
        <span className="score-big">{displayScore.toFixed(1)}</span>
        <span className="score-label"> / 4</span>
      </div>
      <div className="score-badge" style={{ color }}>{label}</div>

      {/* Priority chips */}
      <div className="priority-chips">
        {["P1", "P2", "P3"].map((p) => (
          <button
            key={p}
            className={`priority-chip ${priority === p ? `active-${p.toLowerCase()}` : ""}`}
            onClick={() => setPriority(priority === p ? null : p)}
          >
            {p}
          </button>
        ))}
      </div>

      <div className="adequacy-section">
        {aggregated.map((d) => (
          <AdequacyBar key={d.category} detail={d} />
        ))}
      </div>

      <div className="stats">
        <div className="stat">
          <div className="stat-value">{score.total_population.toLocaleString()}</div>
          Population
        </div>
        <div className="stat">
          <div className="stat-value">{score.fsa_count}</div>
          FSA zones
        </div>
        <div className="stat">
          <div className="stat-value">{score.underserved_fsas.length}</div>
          Underserved
        </div>
        <div className="stat">
          <div className="stat-value">{score.underserved_population.toLocaleString()}</div>
          Pop. at risk
        </div>
      </div>

      {score.underserved_fsas.length > 0 && (
        <div className="underserved">
          <strong>Gaps:</strong>
          {visibleUnderserved.map((fsa) => (
            <div key={fsa.postal_code} className="underserved-item">
              <span>
                {fsa.postal_code} — missing {fsa.missing.join(", ")}
              </span>
              <span style={{ color: scoreColor(fsa.density_score ?? fsa.score) }}>
                {(fsa.density_score ?? fsa.score).toFixed(1)}/4
              </span>
            </div>
          ))}
          {score.underserved_fsas.length > 3 && (
            <button className="show-all-btn" onClick={() => setShowAll(!showAll)}>
              {showAll ? "Voir moins" : `Voir tout (${score.underserved_fsas.length})`}
            </button>
          )}
        </div>
      )}

      {/* Action buttons */}
      <div className="score-card-actions">
        {onAskAgent && (
          <button
            className="action-btn"
            onClick={() =>
              onAskAgent(
                `Quelles sont les priorites d'investissement pour ${score.borough}? Analyse les lacunes et recommande des actions concretes.`
              )
            }
          >
            Demander a l'agent
          </button>
        )}
      </div>

      <div className="export-buttons">
        <button
          className="export-btn"
          onClick={() => {
            window.open(`/api/export/${encodeURIComponent(score.borough)}`, "_blank");
          }}
        >
          Export CSV
        </button>
        <button
          className="export-btn"
          onClick={() => {
            const lines = [
              `# Planning Brief: ${score.borough}`,
              ``,
              `**Date:** ${new Date().toLocaleDateString("en-CA")}`,
              `**15-Minute City Score:** ${avgDensity.toFixed(1)}/4.0 (${label})`,
              `**Population:** ${score.total_population.toLocaleString()}`,
              `**FSA Zones:** ${score.fsa_count}`,
              ``,
              `## Summary`,
              `${score.underserved_fsas.length} of ${score.fsa_count} FSA zones are underserved, affecting ${score.underserved_population.toLocaleString()} residents.`,
              ``,
              `## Category Adequacy`,
            ];
            for (const d of aggregated) {
              const pct = Math.round(d.adequacy_ratio * 100);
              lines.push(
                `- **${d.category}**: ${d.actual} facilities / ${d.expected} needed (${pct}%)`
              );
            }
            if (score.underserved_fsas.length > 0) {
              lines.push(``, `## Underserved Zones`);
              for (const fsa of score.underserved_fsas) {
                const ds = fsa.density_score ?? fsa.score;
                lines.push(
                  `- **${fsa.postal_code}** (${fsa.fsa_name}): ${ds.toFixed(1)}/4 — missing ${fsa.missing.join(", ")}`
                );
              }
            }
            lines.push(
              ``,
              `## Recommendations`,
              `- Prioritize facility investment in the ${score.underserved_fsas.length} underserved FSA zones`,
              `- Focus on missing categories to close the most critical gaps`,
              `- Assess transit headway improvements to increase accessibility radii`
            );

            const blob = new Blob([lines.join("\n")], { type: "text/markdown" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `${score.borough.toLowerCase().replace(/ /g, "-")}_planning_brief.md`;
            a.click();
            URL.revokeObjectURL(url);
          }}
        >
          Planning Brief
        </button>
      </div>
    </div>
  );
}
