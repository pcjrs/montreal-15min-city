import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { MapView, type MapCategory } from "./components/MapView";
import { ChatPanel, type ChatPanelHandle } from "./components/ChatPanel";
import { ScoreCard } from "./components/ScoreCard";
import { BoroughSelector } from "./components/BoroughSelector";
import { KPIBar } from "./components/KPIBar";
import { StatsView } from "./components/StatsView";
import type { Facility, TransitStop, FSA, BoroughScore, DesertData } from "./types";
import "leaflet/dist/leaflet.css";
import "./app.css";

type Tab = "carte" | "stats";

const MAP_CATEGORIES: { value: MapCategory; label: string }[] = [
  { value: "global", label: "Global" },
  { value: "healthcare", label: "\u{1F3E5} Sante" },
  { value: "education", label: "\u{1F393} Edu" },
  { value: "transport", label: "\u{1F68C} Transport" },
  { value: "cultural", label: "\u{1F3AD} Culture" },
  { value: "recreation", label: "\u26BD Loisirs" },
];

export default function App() {
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [stops, setStops] = useState<TransitStop[]>([]);
  const [fsas, setFsas] = useState<FSA[]>([]);
  const [deserts, setDeserts] = useState<DesertData[]>([]);
  const [selectedBorough, setSelectedBorough] = useState<string | null>(null);
  const [boroughScore, setBoroughScore] = useState<BoroughScore | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [scoreLoading, setScoreLoading] = useState(false);
  const chatRef = useRef<ChatPanelHandle>(null);

  const [activeTab, setActiveTab] = useState<Tab>("carte");
  const [mapCategory, setMapCategory] = useState<MapCategory>("global");
  const [showFacilities, setShowFacilities] = useState(false);
  const [showStops, setShowStops] = useState(false);

  // Command palette
  const [cmdOpen, setCmdOpen] = useState(false);
  const [cmdQuery, setCmdQuery] = useState("");
  const cmdInputRef = useRef<HTMLInputElement>(null);
  const [cmdSelected, setCmdSelected] = useState(0);

  useEffect(() => {
    const safeFetch = async (url: string) => {
      const r = await fetch(url);
      if (!r.ok) throw new Error(`${url}: ${r.status} ${r.statusText}`);
      return r.json();
    };

    Promise.all([
      safeFetch("/api/facilities"),
      safeFetch("/api/transit-stops"),
      safeFetch("/api/population"),
      safeFetch("/api/deserts"),
    ])
      .then(([facData, stopData, popData, desertData]) => {
        setFacilities(facData.facilities || []);
        setStops(stopData.stops || []);
        setFsas(popData.fsas || []);
        setDeserts(desertData.all_fsas || []);
      })
      .catch((err) => {
        console.error("Failed to load data:", err);
        setError(String(err));
      })
      .finally(() => setLoading(false));
  }, []);

  // Cmd+K handler
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setCmdOpen((v) => !v);
        setCmdQuery("");
        setCmdSelected(0);
      }
      if (e.key === "Escape" && cmdOpen) {
        setCmdOpen(false);
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [cmdOpen]);

  useEffect(() => {
    if (cmdOpen) {
      setTimeout(() => cmdInputRef.current?.focus(), 50);
    }
  }, [cmdOpen]);

  const handleBoroughSelect = useCallback(async (borough: string) => {
    setSelectedBorough(borough);
    setActiveTab("carte");
    setScoreLoading(true);
    try {
      const res = await fetch(`/api/score/${encodeURIComponent(borough)}`);
      if (res.ok) {
        setBoroughScore(await res.json());
      }
    } finally {
      setScoreLoading(false);
    }
  }, []);

  const handleMapClick = useCallback((lat: number, lon: number) => {
    chatRef.current?.sendQuery(
      `What facilities and transit stops are near coordinates ${lat.toFixed(4)}, ${lon.toFixed(4)}?`
    );
  }, []);

  const handleAskAgent = useCallback((query: string) => {
    chatRef.current?.sendQuery(query);
  }, []);

  const boroughs = [...new Set(fsas.map((f) => f.borough))].sort();

  // Command palette items
  const cmdItems = useMemo(() => {
    const items: { icon: string; label: string; hint: string; action: () => void }[] = [
      {
        icon: "\u{1F6A8}",
        label: "Zones critiques",
        hint: "triage",
        action: () => { setActiveTab("stats"); setCmdOpen(false); },
      },
      {
        icon: "\u{1F30D}",
        label: "Vue d'ensemble",
        hint: "reset",
        action: () => { setSelectedBorough(null); setBoroughScore(null); setActiveTab("carte"); setCmdOpen(false); },
      },
      {
        icon: "\u{1F4CA}",
        label: "Statistiques",
        hint: "tab",
        action: () => { setActiveTab("stats"); setCmdOpen(false); },
      },
      {
        icon: "\u{1F5FA}\uFE0F",
        label: "Carte",
        hint: "tab",
        action: () => { setActiveTab("carte"); setCmdOpen(false); },
      },
    ];

    if (selectedBorough) {
      items.push({
        icon: "\u{1F4C4}",
        label: `Rapport ${selectedBorough}`,
        hint: "export",
        action: () => {
          window.open(`/api/export/${encodeURIComponent(selectedBorough)}`, "_blank");
          setCmdOpen(false);
        },
      });
    }

    for (const b of boroughs) {
      items.push({
        icon: "\u{1F3D8}\uFE0F",
        label: b,
        hint: "arrondissement",
        action: () => { handleBoroughSelect(b); setCmdOpen(false); },
      });
    }

    if (!cmdQuery) return items;
    const q = cmdQuery.toLowerCase();
    return items.filter((item) => item.label.toLowerCase().includes(q));
  }, [cmdQuery, boroughs, selectedBorough, handleBoroughSelect]);

  function handleCmdKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setCmdSelected((v) => Math.min(v + 1, cmdItems.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setCmdSelected((v) => Math.max(v - 1, 0));
    } else if (e.key === "Enter" && cmdItems[cmdSelected]) {
      e.preventDefault();
      cmdItems[cmdSelected].action();
    }
  }

  if (loading) {
    return (
      <div className="loading-screen">
        <div className="skeleton-layout">
          <div className="skeleton-bar" />
          <div className="skeleton-bar" style={{ height: 40 }} />
          <div className="skeleton-bar" style={{ height: 36 }} />
          <div className="skeleton-body">
            <div className="skeleton-map" />
            <div className="skeleton-chat" />
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="loading-screen">
        <p style={{ color: "#ef4444" }}>Failed to load data</p>
        <p style={{ fontSize: "0.8rem", color: "#8b8d98", maxWidth: 500, textAlign: "center" }}>{error}</p>
        <button onClick={() => window.location.reload()} style={{ marginTop: "1rem", padding: "0.5rem 1rem", background: "#3b82f6", color: "white", border: "none", borderRadius: "0.375rem", cursor: "pointer" }}>
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>{"\u{1F3D9}\uFE0F"} Ville 15 Minutes &mdash; Montreal</h1>
        <div className="header-controls">
          <button
            className="export-btn"
            onClick={() => setCmdOpen(true)}
            style={{ fontSize: "0.75rem", display: "flex", alignItems: "center", gap: "0.4rem" }}
          >
            <span>Recherche</span>
            <span className="cmd-kbd">Ctrl+K</span>
          </button>
          <BoroughSelector
            boroughs={boroughs}
            selected={selectedBorough}
            onSelect={handleBoroughSelect}
          />
        </div>
      </header>

      <KPIBar deserts={deserts} />

      <div className="tab-bar">
        <button
          className={`tab-btn ${activeTab === "carte" ? "active" : ""}`}
          onClick={() => setActiveTab("carte")}
        >
          {"\u{1F5FA}\uFE0F"} Carte
        </button>
        <button
          className={`tab-btn ${activeTab === "stats" ? "active" : ""}`}
          onClick={() => setActiveTab("stats")}
        >
          {"\u{1F4CA}"} Stats
        </button>
      </div>

      <div className="app-body">
        <div className="main-content">
          {activeTab === "carte" && (
            <>
              <div className="map-controls">
                <div className="category-filter">
                  {MAP_CATEGORIES.map((cat) => (
                    <label key={cat.value} className={`cat-radio ${mapCategory === cat.value ? "active" : ""}`}>
                      <input
                        type="radio"
                        name="mapCategory"
                        value={cat.value}
                        checked={mapCategory === cat.value}
                        onChange={() => setMapCategory(cat.value)}
                      />
                      {cat.label}
                    </label>
                  ))}
                </div>
                <div className="layer-toggles">
                  <label>
                    <input type="checkbox" checked={showStops} onChange={() => setShowStops((v) => !v)} />
                    Stops
                  </label>
                  <label>
                    <input type="checkbox" checked={showFacilities} onChange={() => setShowFacilities((v) => !v)} />
                    Facilities
                  </label>
                </div>
              </div>
              <div className="map-container">
                {boroughScore && (
                  <ScoreCard
                    score={boroughScore}
                    loading={scoreLoading}
                    onAskAgent={handleAskAgent}
                  />
                )}
                <MapView
                  facilities={facilities}
                  stops={stops}
                  deserts={deserts}
                  fsas={fsas}
                  selectedBorough={selectedBorough}
                  boroughScore={boroughScore}
                  onMapClick={handleMapClick}
                  onFsaClick={handleBoroughSelect}
                  category={mapCategory}
                  showFacilities={showFacilities}
                  showStops={showStops}
                />
                <div className="color-legend">
                  <div className="legend-title">Score</div>
                  <div className="legend-scale">
                    <div className="legend-item" style={{ backgroundColor: "#ef4444" }} />
                    <div className="legend-item" style={{ backgroundColor: "#f97316" }} />
                    <div className="legend-item" style={{ backgroundColor: "#eab308" }} />
                    <div className="legend-item" style={{ backgroundColor: "#84cc16" }} />
                    <div className="legend-item" style={{ backgroundColor: "#22c55e" }} />
                  </div>
                  <div className="legend-labels">
                    <span>0</span>
                    <span>1</span>
                    <span>2</span>
                    <span>3</span>
                    <span>4</span>
                  </div>
                </div>
              </div>
            </>
          )}

          {activeTab === "stats" && (
            <StatsView deserts={deserts} onSelectBorough={handleBoroughSelect} />
          )}
        </div>

        <ChatPanel
          ref={chatRef}
          boroughs={boroughs}
          onBoroughSelect={handleBoroughSelect}
          selectedBorough={selectedBorough}
        />
      </div>

      {/* Command Palette */}
      {cmdOpen && (
        <div className="cmd-palette-overlay" onClick={() => setCmdOpen(false)}>
          <div className="cmd-palette" onClick={(e) => e.stopPropagation()}>
            <input
              ref={cmdInputRef}
              value={cmdQuery}
              onChange={(e) => { setCmdQuery(e.target.value); setCmdSelected(0); }}
              onKeyDown={handleCmdKeyDown}
              placeholder="Rechercher un arrondissement ou une commande..."
            />
            <div className="cmd-list">
              {cmdItems.map((item, i) => (
                <div
                  key={`${item.label}-${item.hint}`}
                  className={`cmd-item ${i === cmdSelected ? "selected" : ""}`}
                  onClick={item.action}
                  onMouseEnter={() => setCmdSelected(i)}
                >
                  <span className="cmd-item-icon">{item.icon}</span>
                  <span className="cmd-item-label">{item.label}</span>
                  <span className="cmd-item-hint">{item.hint}</span>
                </div>
              ))}
              {cmdItems.length === 0 && (
                <div className="cmd-item" style={{ color: "var(--text-muted)" }}>
                  Aucun resultat
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
