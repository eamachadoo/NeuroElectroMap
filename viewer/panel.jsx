// panel.jsx — side panel with 3 states:
//   1. Overview         — patient stats + region list
//   2. Region detail    — BA info + function + electrodes in this region
//   3. Electrode detail — coords (tkRAS + MNI), BA, anatomy, shift correction
//
// Selection state lives in App. This component is stateless.
// No mock signal data (signal/impedance/amplitude/trace) — only fields
// the pipeline actually produces.

const { useMemo: _useMemo } = React;

/* ───────────────────────── helpers ─────────────────────────────────── */

function _mean(xs) {
  if (!xs || xs.length === 0) return 0;
  return xs.reduce((s, v) => s + v, 0) / xs.length;
}

function _fmtCoord(c) {
  if (!c) return "—";
  return `${c[0].toFixed(1)}, ${c[1].toFixed(1)}, ${c[2].toFixed(1)}`;
}

/* group BAs into anatomical "lobes" for the overview list */
const _LOBE_ORDER = ["Motor", "Somatosensory", "Frontal", "Parietal",
                     "Temporal", "Auditory", "Language", "Occipital", "Other"];

function _groupRegionsByLobe(regions) {
  const out = {};
  Object.values(regions).forEach((r) => {
    const key = r.group || "Other";
    (out[key] = out[key] || []).push(r);
  });
  Object.values(out).forEach((arr) => arr.sort((a, b) => a.ba - b.ba));
  return _LOBE_ORDER
    .filter((k) => out[k])
    .map((k) => [k, out[k]])
    .concat(Object.entries(out).filter(([k]) => !_LOBE_ORDER.includes(k)));
}

/* ───────────────────────── Overview ────────────────────────────────── */

function Overview({ data, onSelectRegion, onSelectElectrode }) {
  const electrodes = data.electrodes;
  const meanShift = _mean(electrodes.map((e) => e.shift_mm));
  const regionsByLobe = _useMemo(() => _groupRegionsByLobe(data.regions), [data.regions]);

  // For each region, count electrodes implanted in it
  const elecCountByBA = _useMemo(() => {
    const m = {};
    electrodes.forEach((e) => {
      m[e.brodmann_area] = (m[e.brodmann_area] || 0) + 1;
    });
    return m;
  }, [electrodes]);

  return (
    <div className="pbody">
      <div className="p-eyebrow">Overview · {data.patient_id}</div>
      <h2 className="p-title">Implantation map</h2>
      <p className="p-lead">
        Hover or click a Brodmann area to inspect it, or pick an electrode from the list.
      </p>

      <div className="statrow">
        <div className="stat">
          <div className="stat-n">{electrodes.length}</div>
          <div className="stat-l">Electrodes</div>
        </div>
        <div className="stat">
          <div className="stat-n">{Object.keys(data.regions).length}</div>
          <div className="stat-l">BA regions</div>
        </div>
        <div className="stat">
          <div className="stat-n">{meanShift.toFixed(1)}</div>
          <div className="stat-l">Mean shift (mm)</div>
        </div>
      </div>

      {regionsByLobe.map(([lobe, regs]) => (
        <React.Fragment key={lobe}>
          <div className="p-sec">{lobe} · {regs.length}</div>
          <div className="rlist">
            {regs.map((r) => (
              <button key={r.ba} className="rrow" onClick={() => onSelectRegion(r.ba)}>
                <span className="rrow-dot" style={{ background: r.color }} />
                <span className="rrow-name">BA {r.ba} — {r.name}</span>
                <span className="rrow-grp">{r.group}</span>
                <span className="rrow-n">{elecCountByBA[r.ba] || 0}</span>
                <span className="chev">›</span>
              </button>
            ))}
          </div>
        </React.Fragment>
      ))}

      <p className="p-note" style={{ marginTop: 22 }}>
        Coordinates are in patient tkRAS (FreeSurfer surface space).
        MNI coordinates are also stored per electrode for future cross-patient comparison.
      </p>
    </div>
  );
}

/* ───────────────────────── Region detail ───────────────────────────── */

function RegionDetail({ region, regionElectrodes, schematicElectrodes,
                       onBackToOverview, onSelectElectrode }) {
  const info = window.nemRegionInfo(region.ba);
  const allHere = regionElectrodes.length + schematicElectrodes.length;
  const meanShift = _mean(
    [...regionElectrodes, ...schematicElectrodes].map((e) => e.shift_mm)
  );

  return (
    <div className="pbody">
      <button className="crumb" onClick={onBackToOverview}>‹ All regions</button>

      <div className="rd-head">
        <span className="rd-chip" style={{ background: region.color }} />
        <div>
          <h2 className="p-title">BA {region.ba}</h2>
          <div className="p-eyebrow" style={{ marginTop: 4 }}>{region.group}</div>
        </div>
      </div>

      <p className="p-lead">{info.name}</p>
      <p className="p-note" style={{ marginTop: 4 }}>{info.fn}</p>

      <div className="statrow">
        <div className="stat">
          <div className="stat-n">{allHere}</div>
          <div className="stat-l">Electrodes here</div>
        </div>
        <div className="stat">
          <div className="stat-n">{meanShift.toFixed(1)}</div>
          <div className="stat-l">Mean shift (mm)</div>
        </div>
        <div className="stat">
          <div className="stat-n" style={{ color: region.color }}>●</div>
          <div className="stat-l">Atlas colour</div>
        </div>
      </div>

      <div className="p-sec">Mapped to this Brodmann area</div>
      {regionElectrodes.length === 0 ? (
        <p className="p-note">No electrodes mapped specifically to this BA in this patient.</p>
      ) : (
        <div className="elist">
          {regionElectrodes.map((e) => (
            <button key={e.id} className="erow" onClick={() => onSelectElectrode(e.id)}>
              <span className="erow-id">{window.nemElecLabel(e.id)}</span>
              <span className="erow-anat" title={e.anatomy_label}>{e.anatomy_label || "—"}</span>
              <span className="erow-shift">{(e.pial_distance_mm ?? e.shift_mm).toFixed(1)} mm</span>
              <span className="chev">›</span>
            </button>
          ))}
        </div>
      )}

      {schematicElectrodes.length > 0 && (
        <>
          <div className="p-sec">Other electrodes in this anatomical area</div>
          <p className="p-note" style={{ marginTop: 0, marginBottom: 10 }}>
            Placed in this schematic area via Desikan-Killiany cortical labels
            (no specific Brodmann mapping).
          </p>
          <div className="elist">
            {schematicElectrodes.map((e) => (
              <button key={e.id} className="erow" onClick={() => onSelectElectrode(e.id)}>
                <span className="erow-id">{window.nemElecLabel(e.id)}</span>
                <span className="erow-anat" title={e.aseg_label}>{e.aseg_label || "—"}</span>
                <span className="erow-shift">{(e.pial_distance_mm ?? e.shift_mm).toFixed(1)} mm</span>
                <span className="chev">›</span>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

/* ───────────────────────── Electrode detail ────────────────────────── */

function ElectrodeDetail({ elec, region, onBackToRegion, onBackToOverview, onGoToRegion }) {
  const hasBA = elec.brodmann_area > 0;
  const info = hasBA ? window.nemRegionInfo(elec.brodmann_area) : null;
  const asegInfo = window.nemAsegInfo(elec.aseg_group || "unknown");

  return (
    <div className="pbody">
      <button className="crumb"
              onClick={hasBA ? onBackToRegion : onBackToOverview}>
        {hasBA ? `‹ Back to BA ${elec.brodmann_area}` : "‹ Back to overview"}
      </button>

      <div className="ed-head">
        <div className="ed-badge">{window.nemElecLabel(elec.id)}</div>
        <div>
          <h2 className="p-title">Electrode {window.nemElecLabel(elec.id)}</h2>
          {hasBA ? (
            <button className="reglink" onClick={onGoToRegion}>
              <span className="reglink-dot" style={{ background: region.color }} />
              BA {elec.brodmann_area} — {info.name}
            </button>
          ) : (
            <div className="reglink" style={{ cursor: "default" }}>
              <span className="reglink-dot" style={{ background: asegInfo.color }} />
              {asegInfo.label}
            </div>
          )}
        </div>
      </div>

      <div className="attrgrid">
        {/* Anatomy summary — prefer BA, fall back to aseg */}
        <div className="attr attr-wide">
          <div className="attr-k">Anatomy</div>
          <div className="attr-v" style={{ fontFamily: "inherit" }}>
            {hasBA && elec.anatomy_label
              ? elec.anatomy_label
              : (elec.aseg_label || "—")}
          </div>
        </div>

        {/* Brodmann area (only if mapped) + shift */}
        {hasBA ? (
          <>
            <div className="attr">
              <div className="attr-k">Brodmann area</div>
              <div className="attr-v">BA {elec.brodmann_area}</div>
            </div>
            <div className="attr">
              <div className="attr-k">Distance from cortex</div>
              <div className="attr-v">
                {(elec.pial_distance_mm ?? elec.shift_mm).toFixed(2)} mm
              </div>
            </div>
          </>
        ) : (
          <>
            <div className="attr">
              <div className="attr-k">Volumetric atlas</div>
              <div className="attr-v" style={{ fontFamily: "inherit" }}>{asegInfo.label}</div>
            </div>
            <div className="attr">
              <div className="attr-k">Distance from cortex</div>
              <div className="attr-v">
                {(elec.pial_distance_mm ?? elec.shift_mm).toFixed(2)} mm
              </div>
            </div>
          </>
        )}

        {/* Secondary aseg label when we already have a BA — shows depth context */}
        {hasBA && elec.aseg_label && elec.aseg_group !== "cortical" && (
          <div className="attr attr-wide">
            <div className="attr-k">Volumetric label</div>
            <div className="attr-v" style={{ fontFamily: "inherit" }}>
              {elec.aseg_label} <span style={{
                fontSize: "10.5px", color: "var(--muted)", fontWeight: 500,
              }}>· {asegInfo.label}</span>
            </div>
          </div>
        )}

        <div className="attr attr-wide">
          <div className="attr-k">Patient space (tkRAS, mm)</div>
          <div className="attr-v">{_fmtCoord(elec.corrected_mm)}</div>
        </div>

        {elec.mni_mm && (
          <div className="attr attr-wide">
            <div className="attr-k">MNI Talairach (mm)</div>
            <div className="attr-v">{_fmtCoord(elec.mni_mm)}</div>
          </div>
        )}
      </div>

      {hasBA && elec.shift_mm > 10 && (
        <p className="p-note" style={{ marginTop: 14 }}>
          Large brain-shift correction expected for depth (sEEG) electrodes —
          the "corrected" position is the nearest cortical surface vertex along
          the electrode trajectory, not the contact's true depth.
        </p>
      )}
      {!hasBA && elec.aseg_group === "unknown" && (
        <p className="p-note" style={{ marginTop: 14 }}>
          No anatomical label could be assigned. This often indicates a
          segmentation artifact — a high-HU object outside the brain volume
          (cable, connector, partial-volume effect) that was detected by the
          HU threshold but is not a contact in tissue.
        </p>
      )}
    </div>
  );
}

/* ───────────────────────── Panel router ────────────────────────────── */

function Panel(props) {
  const { data, selectedBA, selectedElec,
          onSelectRegion, onSelectElectrode, onClearSelection } = props;

  // Electrode detail
  if (selectedElec) {
    const elec = data.electrodes.find((e) => e.id === selectedElec);
    if (elec) {
      const region = data.regions[String(elec.brodmann_area)]
                   || { ba: elec.brodmann_area, color: "#888", group: "Other" };
      return (
        <ElectrodeDetail
          elec={elec}
          region={region}
          onBackToRegion={() => onSelectRegion(elec.brodmann_area)}
          onBackToOverview={onClearSelection}
          onGoToRegion={() => onSelectRegion(elec.brodmann_area)}
        />
      );
    }
  }

  // Region detail
  if (selectedBA) {
    // The BA may not be in this patient's exported data.regions (e.g. user
    // clicked a sub-region on the 2D schematic that no electrode landed in).
    // Synthesise a stub from the static atlas metadata so we can still show
    // the user *what* this region is, even if the count of contacts is zero.
    let region = data.regions[String(selectedBA)];
    if (!region) {
      const info = window.nemRegionInfo(selectedBA);
      region = {
        ba:           selectedBA,
        name:         info.name,
        group:        info.group,
        schematic_id: info.schematic_id,
        color:        info.color,
      };
    }
    const here = data.electrodes.filter((e) => e.brodmann_area === selectedBA);
    const schemHere = data.electrodes.filter((e) =>
      e.brodmann_area === 0 && e.schematic_id === region.schematic_id
    );
    return (
      <RegionDetail
        region={region}
        regionElectrodes={here}
        schematicElectrodes={schemHere}
        onBackToOverview={onClearSelection}
        onSelectElectrode={onSelectElectrode}
      />
    );
  }

  // Overview
  return (
    <Overview
      data={data}
      onSelectRegion={onSelectRegion}
      onSelectElectrode={onSelectElectrode}
    />
  );
}

Object.assign(window, { Panel });
