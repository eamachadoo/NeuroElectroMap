// brain2d.jsx — schematic lateral 2D view of the left hemisphere.
//
// • Cortical regions (lobes + sub-regions) are drawn from window.NEM_SCHEMATIC.
//   Each is coloured by the BA it represents in the current patient
//   (looked up via data.regions[ba].schematic_id). Regions with no matching
//   BA in this patient are shown dimmed.
// • Cortical electrodes (aseg_group === "cortical" OR with a BA hit) are
//   scattered inside their schematic region.
// • Non-cortical electrodes (white matter, hippocampus, thalamus, ventricle,
//   etc.) appear in a "Deep / non-cortical" pool below the brain silhouette,
//   one lane per aseg group. The pool includes "unknown" (segmentation
//   artifacts) so every electrode is reachable.

const { useState: _b2dState, useRef: _b2dRef, useMemo: _b2dMemo } = React;

/* ───────────────────────── deterministic scatter ────────────────────── */
function _hashCode(s) {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = (h * 33) ^ s.charCodeAt(i);
  return h >>> 0;
}
function _mulberry32(seed) {
  let a = seed | 0;
  return function () {
    a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/* ───────────────────────── tooltips ──────────────────────────────────── */

function RegionTooltip({ schemReg, bas, electrodeCount }) {
  return (
    <>
      <div className="braintip-name">{schemReg.group}</div>
      <div className="braintip-sub">{schemReg.description}</div>
      {bas.length > 0 && (
        <div className="braintip-bas">
          {bas.map((r) => (
            <span key={r.ba} className="braintip-bachip" style={{
              background: `color-mix(in srgb, ${r.color} 28%, transparent)`,
              color: "var(--ink)",
            }}>BA {r.ba}</span>
          ))}
        </div>
      )}
      <div className="braintip-meta">
        <span className="dot" style={{ background: bas[0]?.color || "var(--muted)" }} />
        {electrodeCount} electrode{electrodeCount === 1 ? "" : "s"}
      </div>
    </>
  );
}

function LaneTooltip({ info, count, sampleLabels }) {
  return (
    <>
      <div className="braintip-name">{info.label}</div>
      <div className="braintip-sub">{info.description}</div>
      {sampleLabels.length > 0 && (
        <div className="braintip-bas">
          {sampleLabels.map((l, i) => (
            <span key={i} className="braintip-bachip">{l}</span>
          ))}
        </div>
      )}
      <div className="braintip-meta">
        <span className="dot" style={{ background: info.color }} />
        {count} electrode{count === 1 ? "" : "s"}
      </div>
    </>
  );
}

function ElectrodeTooltip({ elec, regions }) {
  const ba = elec.brodmann_area;
  const reg = ba ? regions[String(ba)] : null;
  // Prefer BA label if present, otherwise show aseg_label
  const primary = ba
    ? `BA ${ba} — ${elec.anatomy_label || "?"}`
    : (elec.aseg_label || "Unknown");
  const dotColor = reg
    ? reg.color
    : (window.nemAsegInfo(elec.aseg_group).color);
  const dist = elec.pial_distance_mm ?? elec.shift_mm ?? 0;
  // Flag when the position is meaningfully off the cortical surface so the
  // user understands why the 3D view places the dot outside the mesh while
  // the 2D schematic keeps it inside the labelled region.
  const off = dist > 3.0
    ? <span style={{ color: "var(--muted)" }}> · off cortex</span>
    : null;
  return (
    <>
      <div className="braintip-name">Electrode {window.nemElecLabel(elec.id)}</div>
      <div className="braintip-sub">{primary}</div>
      <div className="braintip-meta">
        <span className="dot" style={{ background: dotColor }} />
        {dist.toFixed(1)} mm from cortex{off}
      </div>
    </>
  );
}

/* ───────────────────────── layout constants ──────────────────────────── */

const BRAIN_W       = 600;
const BRAIN_H       = 460;
const POOL_Y        = BRAIN_H + 22;     // start of pool area
const POOL_PAD_X    = 14;
const POOL_LANE_GAP = 6;
const POOL_LANE_TITLE_H = 14;
const POOL_LANE_BODY_MIN_H = 18;
const POOL_LANE_BODY_PER_ROW = 14;
const POOL_LANE_ELECS_PER_ROW = 30;     // visual density target
const POOL_BOTTOM_PAD = 14;

/* ───────────────────────── main component ────────────────────────────── */

function Brain2D(props) {
  const {
    data,
    selectedBA, selectedElec, hoveredBA,
    onHoverRegion, onSelectRegion, onSelectElectrode,
  } = props;

  const sch = window.NEM_SCHEMATIC;
  if (!sch) {
    return (
      <div className="brainwrap brainwrap-placeholder">
        <div className="placeholder-msg">
          <div className="placeholder-title">Schematic data missing</div>
          <div className="placeholder-sub">window.NEM_SCHEMATIC was not loaded.</div>
        </div>
      </div>
    );
  }

  /* Cortical-vs-pool split. An electrode is "on the schematic" if it has a
   * schematic_id matching one of our drawn regions (which requires a BA hit).
   * Everything else goes to the pool, grouped by aseg_group. */
  const corticalIds = _b2dMemo(() => new Set(sch.regions.map((r) => r.id)), []);

  const corticalElecs = _b2dMemo(
    () => data.electrodes.filter((e) => corticalIds.has(e.schematic_id)),
    [data.electrodes, corticalIds]
  );
  const poolElecs = _b2dMemo(
    () => data.electrodes.filter((e) => !corticalIds.has(e.schematic_id)),
    [data.electrodes, corticalIds]
  );

  /* basBySchId + elecsBySchId for cortical rendering */
  const basBySchId = _b2dMemo(() => {
    const m = {};
    Object.values(data.regions).forEach((r) => {
      (m[r.schematic_id] = m[r.schematic_id] || []).push(r);
    });
    Object.values(m).forEach((arr) => arr.sort((a, b) => a.ba - b.ba));
    return m;
  }, [data.regions]);

  const corticalElecsBySchId = _b2dMemo(() => {
    const m = {};
    corticalElecs.forEach((e) => {
      (m[e.schematic_id] = m[e.schematic_id] || []).push(e);
    });
    return m;
  }, [corticalElecs]);

  /* Pool lanes — one per aseg_group, sorted by metadata order */
  const poolLanes = _b2dMemo(() => {
    const byGroup = {};
    poolElecs.forEach((e) => {
      const g = e.aseg_group || "unknown";
      (byGroup[g] = byGroup[g] || []).push(e);
    });
    return Object.entries(byGroup)
      .map(([group, elecs]) => ({
        group,
        info: window.nemAsegInfo(group),
        electrodes: elecs,
      }))
      .sort((a, b) => a.info.order - b.info.order);
  }, [poolElecs]);

  /* Lane geometry — vertical stack, each lane gets multiple rows if needed */
  const laneLayouts = _b2dMemo(() => {
    let y = POOL_Y + 12;  // 12px below the divider for the eyebrow text
    const out = poolLanes.map((lane) => {
      const rows = Math.max(1, Math.ceil(lane.electrodes.length / POOL_LANE_ELECS_PER_ROW));
      const bodyH = Math.max(POOL_LANE_BODY_MIN_H, rows * POOL_LANE_BODY_PER_ROW);
      const layout = {
        y, titleY: y + 10,
        bodyY: y + POOL_LANE_TITLE_H,
        bodyH, width: BRAIN_W - 2 * POOL_PAD_X, x: POOL_PAD_X,
        totalH: POOL_LANE_TITLE_H + bodyH,
      };
      y += layout.totalH + POOL_LANE_GAP;
      return layout;
    });
    out.totalEnd = y;
    return out;
  }, [poolLanes]);

  const viewBoxH = poolLanes.length === 0
    ? BRAIN_H
    : (laneLayouts.totalEnd || BRAIN_H) + POOL_BOTTOM_PAD;

  /* Per-electrode 2D position (deterministic from id) */
  const electrodePositions = _b2dMemo(() => {
    const positions = {};
    // cortical electrodes — scatter in their schematic region
    sch.regions.forEach((reg) => {
      const here = corticalElecsBySchId[reg.id] || [];
      here.forEach((e) => {
        const rnd = _mulberry32(_hashCode(String(e.id)) + 1);
        const ang = rnd() * Math.PI * 2;
        const rad = Math.sqrt(rnd()) * reg.spread;
        positions[e.id] = {
          x: reg.label[0] + Math.cos(ang) * rad * 1.15,
          y: reg.label[1] + Math.sin(ang) * rad,
          inPool: false,
        };
      });
    });
    // pool electrodes — scatter inside their lane
    poolLanes.forEach((lane, i) => {
      const L = laneLayouts[i];
      lane.electrodes.forEach((e) => {
        const rnd = _mulberry32(_hashCode(String(e.id)) + 13);
        positions[e.id] = {
          x: L.x + 8 + rnd() * (L.width - 16),
          y: L.bodyY + 4 + rnd() * (L.bodyH - 8),
          inPool: true,
        };
      });
    });
    return positions;
  }, [corticalElecs, poolLanes, laneLayouts, corticalElecsBySchId]);

  /* Active schematic_id for selection + hover */
  const activeSchId = _b2dMemo(() => {
    if (selectedBA && data.regions[String(selectedBA)])
      return data.regions[String(selectedBA)].schematic_id;
    return null;
  }, [selectedBA, data.regions]);

  const hoverSchId = _b2dMemo(() => {
    if (hoveredBA && data.regions[String(hoveredBA)])
      return data.regions[String(hoveredBA)].schematic_id;
    return null;
  }, [hoveredBA, data.regions]);

  const corticalIsActive = !!(activeSchId || hoverSchId);

  /* Tooltip state */
  const wrapRef = _b2dRef(null);
  const [tip, setTip] = _b2dState(null);
  const [hoverElec, setHoverElec] = _b2dState(null);

  const moveTip = (e) => {
    const r = wrapRef.current?.getBoundingClientRect();
    if (!r) return;
    setTip((t) => (t ? { ...t, x: e.clientX - r.left, y: e.clientY - r.top } : t));
  };

  return (
    <div
      className="brainwrap"
      ref={wrapRef}
      onMouseMove={moveTip}
      onMouseLeave={() => { setTip(null); onHoverRegion(null); setHoverElec(null); }}
    >
      <svg viewBox={`0 0 ${BRAIN_W} ${viewBoxH}`} className="brainsvg" role="img"
           aria-label="Lateral brain schematic with subcortical pool">
        <defs>
          <clipPath id="cortexClip"><path d={sch.silhouette} /></clipPath>
        </defs>

        {/* base silhouette */}
        <path d={sch.silhouette} fill="var(--surface)" />

        {/* clipped cortical regions */}
        <g clipPath="url(#cortexClip)">
          {sch.regions.map((reg) => {
            const bas = basBySchId[reg.id] || [];
            const isPresent = bas.length > 0;
            const fillColor = isPresent ? bas[0].color : "var(--surface-2)";
            const active   = activeSchId === reg.id || hoverSchId === reg.id;
            const dim      = corticalIsActive && !active;
            let opacity;
            if (!isPresent)  opacity = 0.18;
            else if (active) opacity = 0.95;
            else if (dim)    opacity = 0.22;
            else             opacity = 0.72;

            // Even when no electrodes in this patient land here, the user
            // can still click to see what this region represents — we open
            // a side panel describing the canonical BA (e.g. "BA 22 —
            // Wernicke's Area — 0 electrodes in this patient").
            const targetBA = isPresent ? bas[0].ba : reg.canonical_ba;
            return (
              <path
                key={reg.id} d={reg.path}
                fill={fillColor}
                fillOpacity={opacity}
                stroke={active ? "var(--accent)" : "var(--surface)"}
                strokeWidth={active ? 2.4 : 1.2}
                style={{
                  cursor: "pointer",
                  transition: "fill-opacity .15s, stroke .15s, stroke-width .15s",
                }}
                onMouseEnter={() => {
                  if (targetBA != null) onHoverRegion(targetBA);
                  setTip({
                    x: 0, y: 0, kind: "region", schemReg: reg,
                    bas, count: (corticalElecsBySchId[reg.id] || []).length,
                  });
                }}
                onClick={() => {
                  if (targetBA != null) onSelectRegion(targetBA);
                }}
              />
            );
          })}
        </g>

        {/* silhouette outline on top */}
        <path d={sch.silhouette}
              fill="none" stroke="var(--border)" strokeWidth="1.4"
              pointerEvents="none" />

        {/* ─── pool divider + eyebrow ─── */}
        {poolLanes.length > 0 && (
          <>
            <rect x={POOL_PAD_X} y={POOL_Y}
                  width={BRAIN_W - 2 * POOL_PAD_X} height={0.8}
                  className="pool-divider" />
            <text x={POOL_PAD_X} y={POOL_Y + 12} className="pool-eyebrow">
              Deep / non-cortical electrodes · {poolElecs.length}
            </text>
          </>
        )}

        {/* ─── pool lanes ─── */}
        {poolLanes.map((lane, i) => {
          const L = laneLayouts[i];
          const sampleLabels = Array.from(new Set(lane.electrodes.map((e) => e.aseg_label))).slice(0, 4);
          return (
            <g key={lane.group}>
              <rect
                x={L.x} y={L.bodyY} width={L.width} height={L.bodyH}
                rx={6} ry={6}
                fill={lane.info.color} fillOpacity={0.10}
                stroke="var(--border)" strokeWidth={1}
                style={{ cursor: "default" }}
                onMouseEnter={() => setTip({
                  x: 0, y: 0, kind: "lane", info: lane.info,
                  count: lane.electrodes.length, sampleLabels,
                })}
              />
              <text x={L.x + 8} y={L.titleY + 2} className="pool-laneTitle">
                {lane.info.label}
              </text>
              <text x={L.x + L.width - 8} y={L.titleY + 2}
                    className="pool-laneCount" textAnchor="end">
                {lane.electrodes.length}
              </text>
            </g>
          );
        })}

        {/* ─── electrodes (both cortical + pool) ─── */}
        {data.electrodes.map((e) => {
          const pos = electrodePositions[e.id];
          if (!pos) return null;
          const isSel = selectedElec === e.id;
          const isHov = hoverElec === e.id;
          // Dim only cortical electrodes when a cortical region is active;
          // pool electrodes are independent of cortical selection.
          const dim = !pos.inPool && corticalIsActive
            && activeSchId !== e.schematic_id
            && hoverSchId  !== e.schematic_id;

          const r = pos.inPool ? (isSel || isHov ? 3.6 : 2.6)
                               : (isSel || isHov ? 4.6 : 3.6);

          return (
            <g key={e.id}
               style={{ cursor: "pointer" }}
               opacity={dim ? 0.20 : 1}
               onMouseEnter={() => {
                 setHoverElec(e.id);
                 setTip({ x: 0, y: 0, kind: "elec", elec: e });
               }}
               onMouseLeave={() => setHoverElec(null)}
               onClick={(ev) => { ev.stopPropagation(); onSelectElectrode(e.id); }}>
              {(isSel || isHov) && (
                <circle cx={pos.x} cy={pos.y} r={r + 3.5}
                        fill="none"
                        stroke={isSel ? "var(--accent)" : "var(--elec)"}
                        strokeWidth="2" opacity="0.7" />
              )}
              <circle cx={pos.x} cy={pos.y} r={r}
                      fill="var(--elec)"
                      stroke="var(--surface)" strokeWidth="0.8" />
            </g>
          );
        })}
      </svg>

      {/* electrode count notice */}
      <div className="braincount">
        <strong>{corticalElecs.length}</strong> cortical electrodes shown on the schematic
        {poolElecs.length > 0 && <> · <strong>{poolElecs.length}</strong> in the deep pool below</>}
        {" · "}all <strong>{data.electrodes.length}</strong> visible in the 3D view.
      </div>

      {/* tooltip */}
      {tip && (
        <div className="braintip" style={{ left: tip.x + 14, top: tip.y + 14 }}>
          {tip.kind === "region"
            ? <RegionTooltip schemReg={tip.schemReg} bas={tip.bas} electrodeCount={tip.count} />
            : tip.kind === "lane"
            ? <LaneTooltip info={tip.info} count={tip.count} sampleLabels={tip.sampleLabels} />
            : <ElectrodeTooltip elec={tip.elec} regions={data.regions} />}
        </div>
      )}
    </div>
  );
}

Object.assign(window, { Brain2D });
