// app.jsx — NeuroElectroMap viewer shell.
// Holds top-level state (theme, view mode, selection, hover) and lays out the
// top bar + brain stage + side panel. Brain components and the side panel
// live in their own files (brain2d.jsx, brain3d.jsx, panel.jsx).
//
// Multi-patient (Switch mode):
//   • If `window.NEM_MANIFEST` is present, the top bar shows a case selector
//     and patient data is fetched on demand from `<id>/data.json`.
//   • If only legacy `window.NEM_DATA` is present, the viewer renders that
//     single-patient bundle directly (no case selector).

const { useState, useEffect, useMemo } = React;

/* ───────────────────────────── helpers ─────────────────────────────── */

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
}

function getInitialTheme() {
  const stored = localStorage.getItem("nem-theme");
  if (stored === "light" || stored === "dark") return stored;
  return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

function getInitialPatientId(manifest) {
  if (!manifest || !manifest.patients || manifest.patients.length === 0) return null;
  const stored = localStorage.getItem("nem-patient");
  if (stored && manifest.patients.some((p) => p.id === stored)) return stored;
  return manifest.patients[0].id;
}

/* ───────────────────────────── top bar ─────────────────────────────── */

function BrandMark({ accent }) {
  return (
    <svg width="26" height="26" viewBox="0 0 26 26" aria-hidden="true">
      <circle cx="13" cy="13" r="11" fill="none" stroke={accent} strokeWidth="1.6" />
      <circle cx="13" cy="13" r="3.2" fill={accent} />
      <circle cx="6.5"  cy="9"    r="1.7" fill="#d6342b" />
      <circle cx="19"   cy="8"    r="1.7" fill="#d6342b" />
      <circle cx="18"   cy="18.5" r="1.7" fill="#d6342b" />
    </svg>
  );
}

function CaseSelector({ manifest, currentId, onChange }) {
  return (
    <select
      className="caseselect"
      value={currentId || ""}
      onChange={(e) => onChange(e.target.value)}
      title="Switch patient"
    >
      {manifest.patients.map((p) => (
        <option key={p.id} value={p.id}>
          {p.patient_id} · {p.n_electrodes} electrodes
        </option>
      ))}
    </select>
  );
}

function ViewToggle({ mode, onChange }) {
  return (
    <div className="segtoggle" role="group" aria-label="View mode">
      <button className={mode === "2d" ? "on" : ""} onClick={() => onChange("2d")}>2D</button>
      <button className={mode === "3d" ? "on" : ""} onClick={() => onChange("3d")}>3D</button>
    </div>
  );
}

function ThemeToggle({ theme, onChange }) {
  const isDark = theme === "dark";
  return (
    <button
      className="iconbtn"
      title={isDark ? "Switch to light theme" : "Switch to dark theme"}
      onClick={() => onChange(isDark ? "light" : "dark")}
    >
      {isDark ? (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
             strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79Z"/>
        </svg>
      ) : (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
             strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="4"/>
          <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/>
        </svg>
      )}
    </button>
  );
}

/* ───────────────────────────── legend ──────────────────────────────── */

function Legend({ regions, hoveredBA, onHover, onSelect }) {
  const list = useMemo(
    () => Object.values(regions).sort((a, b) => a.ba - b.ba),
    [regions]
  );
  if (list.length === 0) return null;
  return (
    <div className="legend">
      <div className="legend-t">Brodmann areas present ({list.length})</div>
      <div className="legend-grid">
        {list.map((r) => (
          <button
            key={r.ba}
            className={"leg" + (hoveredBA === r.ba ? " on" : "")}
            onMouseEnter={() => onHover(r.ba)}
            onMouseLeave={() => onHover(null)}
            onClick={() => onSelect(r.ba)}
          >
            <span className="leg-dot" style={{ background: r.color }} />
            <span className="leg-l">BA {r.ba} — {r.name}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

/* ───────────────────────────── transient screens ───────────────────── */

function LoadingScreen({ patientId }) {
  return (
    <div className="errscreen">
      <div className="errcard" style={{ textAlign: "center" }}>
        <div className="brain3d-spinner" style={{ position: "static", marginBottom: 10 }}>
          Loading {patientId}…
        </div>
        <p>Fetching mesh + electrodes from <code>{patientId}/data.json</code></p>
      </div>
    </div>
  );
}

function LoadErrorScreen({ patientId, message }) {
  return (
    <div className="errscreen">
      <div className="errcard">
        <h1>Could not load <code>{patientId}</code></h1>
        <p>{message}</p>
        <p style={{ marginTop: 14 }}>
          Run the pipeline for this subject:<br/>
          <code>make run MRI=… CT=… SUBJECT_DIR=…</code>
        </p>
      </div>
    </div>
  );
}

function MissingDataScreen() {
  return (
    <div className="errscreen">
      <div className="errcard">
        <h1>No patient data loaded</h1>
        <p>
          The viewer expects either <code>outputs/viewer/manifest.js</code>
          (multi-patient) or <code>outputs/viewer/data.js</code>
          (single-patient legacy) next to the project root. Generate one by
          running the pipeline with the <code>--export-viewer</code> flag:
        </p>
        <p style={{ marginTop: 14 }}>
          <code>make run-ds004473</code>
        </p>
        <p style={{ marginTop: 14 }}>
          Then refresh this page. If you opened <code>viewer/index.html</code>
          directly from the file system, the browser blocks
          <code>fetch()</code> on <code>file://</code> URLs — run
          <code>make viewer</code> (or <code>make desktop</code>) so the
          viewer is served over loopback HTTP.
        </p>
      </div>
    </div>
  );
}

/* ───────────────────────────── App ─────────────────────────────────── */

function App() {
  const manifest = window.NEM_MANIFEST || null;
  const hasManifest = !!(manifest && manifest.patients && manifest.patients.length > 0);

  const [theme,        setTheme]      = useState(getInitialTheme());
  const [viewMode,     setViewMode]   = useState("2d");
  const [selectedBA,   setSelectedBA] = useState(null);
  const [selectedElec, setSelectedElec] = useState(null);
  const [hoveredBA,    setHoveredBA] = useState(null);

  const [currentPatientId, setCurrentPatientId] = useState(
    () => getInitialPatientId(manifest)
  );

  // Patient data: starts from legacy window.NEM_DATA if there's no manifest,
  // otherwise will be populated by the fetch effect below.
  const [data, setData] = useState(() => (hasManifest ? null : window.NEM_DATA || null));
  const [loadError, setLoadError] = useState(null);

  /* Theme persistence */
  useEffect(() => {
    applyTheme(theme);
    localStorage.setItem("nem-theme", theme);
  }, [theme]);

  /* Fetch patient data when the case selector changes. */
  useEffect(() => {
    if (!hasManifest || !currentPatientId) return;
    const patient = manifest.patients.find((p) => p.id === currentPatientId);
    if (!patient) return;

    let cancelled = false;
    setData(null);
    setLoadError(null);
    // Selection state belongs to the previous patient — drop it.
    setSelectedBA(null);
    setSelectedElec(null);
    setHoveredBA(null);

    fetch("../outputs/viewer/" + patient.data_url, { cache: "no-store" })
      .then((r) => r.ok ? r.json() : Promise.reject(`HTTP ${r.status} ${r.statusText}`))
      .then((d) => {
        if (cancelled) return;
        setData(d);
        localStorage.setItem("nem-patient", currentPatientId);
      })
      .catch((e) => {
        if (cancelled) return;
        setLoadError(String(e));
      });

    return () => { cancelled = true; };
  }, [currentPatientId, hasManifest, manifest]);

  /* Empty / loading / error states */
  if (!hasManifest && !data) return <MissingDataScreen />;
  if (hasManifest && loadError)
    return <LoadErrorScreen patientId={currentPatientId} message={loadError} />;
  if (hasManifest && !data)
    return <LoadingScreen patientId={currentPatientId} />;

  const accent = getComputedStyle(document.documentElement)
    .getPropertyValue("--accent").trim() || "#2563a8";

  const clearSelection = () => { setSelectedBA(null); setSelectedElec(null); };
  const selectBA       = (ba) => { setSelectedBA(ba); setSelectedElec(null); };
  const selectElec     = (id) => {
    setSelectedElec(id);
    const e = data.electrodes.find((x) => x.id === id);
    setSelectedBA(e ? e.brodmann_area : null);
  };

  const sharedProps = {
    data,
    selectedBA, selectedElec,
    hoveredBA,
    onHoverRegion: setHoveredBA,
    onSelectRegion: selectBA,
    onSelectElectrode: selectElec,
  };

  const Brain = viewMode === "2d" ? window.Brain2D : window.Brain3D;

  return (
    <div className="app">
      {/* top bar */}
      <header className="topbar">
        <div className="brand">
          <BrandMark accent={accent} />
          <span className="brand-name">NeuroElectro<b>Map</b></span>
        </div>
        <div className="casebar">
          {hasManifest ? (
            <CaseSelector
              manifest={manifest}
              currentId={currentPatientId}
              onChange={setCurrentPatientId}
            />
          ) : (
            <span className="casebar-id">{data.patient_id}</span>
          )}
          <span className="casenote">
            {data.electrodes.length} electrodes · {Object.keys(data.regions).length} BA regions
          </span>
        </div>
        <div className="topright">
          <ViewToggle mode={viewMode} onChange={setViewMode} />
          <ThemeToggle theme={theme} onChange={setTheme} />
        </div>
      </header>

      {/* body */}
      <div className="body">
        <main className="stage">
          <Brain {...sharedProps} />
          <Legend
            regions={data.regions}
            hoveredBA={hoveredBA}
            onHover={setHoveredBA}
            onSelect={selectBA}
          />
          {(selectedBA || selectedElec) && (
            <button className="clearsel" onClick={clearSelection}>Clear selection ✕</button>
          )}
        </main>

        <aside className="panel">
          <Panel {...sharedProps} onClearSelection={clearSelection} />
        </aside>
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
