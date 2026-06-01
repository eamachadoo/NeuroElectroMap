// brain3d.jsx — 3D anatomical view using Plotly.
//
// • Two Mesh3d traces (LH + RH) rendered semi-transparent so that deep sEEG
//   electrodes inside the cortex remain visible.
// • Vertices are coloured by their Brodmann area (per-vertex BA labels from
//   the decimated mesh). Unlabelled cortex (BA 0) is shown in a neutral tone
//   that adapts to the active light/dark theme.
// • Electrodes are rendered as a Scatter3d trace with always-visible "E#"
//   labels (in line with the design decision: prioritise quick identification
//   for clinicians).
// • Click an electrode → selects it in the side panel.
//   Click a region on the mesh → selects its BA in the side panel.
//   Hover over the mesh → highlights the BA in the legend.
//
// Selected / hovered electrodes are highlighted by updating only the marker
// colour array (cheap), avoiding a full mesh re-render.

const { useEffect: _b3dEffect, useMemo: _b3dMemo, useRef: _b3dRef,
        useState: _b3dState } = React;

/* ───────────────────────── colour helpers ───────────────────────────── */

function _hexFromCssVar(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

function _resolveThemeColors() {
  return {
    bg:           _hexFromCssVar("--bg",           "#0d1117"),
    surface:      _hexFromCssVar("--surface",      "#161c24"),
    surface2:     _hexFromCssVar("--surface-2",    "#1d242e"),
    ink:          _hexFromCssVar("--ink",          "#e8ecf2"),
    muted:        _hexFromCssVar("--muted",        "#8b95a5"),
    accent:       _hexFromCssVar("--accent",       "#5da7e6"),
    elec:         _hexFromCssVar("--elec",         "#ff7665"),
    border:       _hexFromCssVar("--border",       "#2a3340"),
  };
}

/* Per-vertex colour array from BA labels.
 * BA 0 (vast majority of cortex) → neutral cortex colour from the theme. */
function _buildVertexColors(baLabels, regions, fallback) {
  const colorByBA = {};
  Object.values(regions).forEach((r) => { colorByBA[r.ba] = r.color; });
  const out = new Array(baLabels.length);
  for (let i = 0; i < baLabels.length; i++) {
    const ba = baLabels[i];
    out[i] = (ba && colorByBA[ba]) || fallback;
  }
  return out;
}

/* ───────────────────────── main component ───────────────────────────── */

function Brain3D(props) {
  const {
    data,
    selectedBA, selectedElec, hoveredBA,
    onHoverRegion, onSelectRegion, onSelectElectrode,
  } = props;

  const wrapRef = _b3dRef(null);
  const plotRef = _b3dRef(null);
  const [theme, setTheme] = _b3dState(
    document.documentElement.getAttribute("data-theme") || "light"
  );
  const [ready, setReady] = _b3dState(false);

  // Watch theme switches so the scene background tracks light/dark.
  _b3dEffect(() => {
    const obs = new MutationObserver(() => {
      setTheme(document.documentElement.getAttribute("data-theme") || "light");
    });
    obs.observe(document.documentElement, {
      attributes: true, attributeFilter: ["data-theme"],
    });
    return () => obs.disconnect();
  }, []);

  // Cortex base colour adapts to the theme (lighter than surface so coloured
  // BAs pop, darker than ink so it doesn't visually compete with electrodes).
  const cortexFallback = theme === "dark" ? "#5a6878" : "#cdd5e0";

  /* Per-vertex colour arrays — computed once per mesh / theme change. */
  const vertexColors = _b3dMemo(() => ({
    lh: _buildVertexColors(data.mesh.lh.ba_labels, data.regions, cortexFallback),
    rh: _buildVertexColors(data.mesh.rh.ba_labels, data.regions, cortexFallback),
  }), [data, cortexFallback]);

  /* Mesh traces — built once per data load. */
  const meshTraces = _b3dMemo(() => {
    function trace(hemi, name, hemiKey) {
      const verts = hemi.vertices;
      const faces = hemi.faces;
      const labels = hemi.ba_labels;
      const colors = vertexColors[hemiKey];
      // Hover text only mentions the BA — full anatomy lookup happens via
      // the panel after click.
      const text = labels.map((ba) =>
        ba ? `BA ${ba}` : "Unlabelled cortex"
      );
      return {
        type: "mesh3d",
        x: verts.map((v) => v[0]),
        y: verts.map((v) => v[1]),
        z: verts.map((v) => v[2]),
        i: faces.map((f) => f[0]),
        j: faces.map((f) => f[1]),
        k: faces.map((f) => f[2]),
        vertexcolor: colors,
        opacity: 0.45,
        flatshading: false,
        lighting: { ambient: 0.7, diffuse: 0.6, specular: 0.05, roughness: 0.95 },
        hoverinfo: "text",
        text,
        showlegend: false,
        name,
        meta: { kind: "mesh", hemi: hemiKey },
      };
    }
    return [
      trace(data.mesh.lh, "Left hemisphere",  "lh"),
      trace(data.mesh.rh, "Right hemisphere", "rh"),
    ];
  }, [data, vertexColors]);

  /* Electrode trace — small marker/colour arrays so it can be rebuilt cheaply
   * when selection / hover changes. */
  const electrodeTrace = _b3dMemo(() => {
    const t = _resolveThemeColors();
    const xs = [], ys = [], zs = [], texts = [], hovers = [], ids = [];
    const colors = [], sizes = [];
    data.electrodes.forEach((e) => {
      const c = e.corrected_mm;
      xs.push(c[0]); ys.push(c[1]); zs.push(c[2]);
      texts.push("E" + e.id);
      const label = e.brodmann_area
        ? `BA ${e.brodmann_area} — ${e.anatomy_label || ""}`
        : (e.aseg_label || "Unknown");
      hovers.push(`<b>E${e.id}</b><br>${label}<br>shift ${e.shift_mm.toFixed(1)} mm`);
      ids.push(e.id);
      const isSel = selectedElec === e.id;
      const isInRegion = selectedBA && e.brodmann_area === selectedBA;
      colors.push(isSel ? t.accent : t.elec);
      sizes.push(isSel ? 8 : isInRegion ? 6 : 4.5);
    });
    return {
      type: "scatter3d",
      x: xs, y: ys, z: zs,
      mode: "markers+text",
      marker: {
        size: sizes,
        color: colors,
        line: { width: 0.5, color: t.surface },
        opacity: 0.95,
      },
      text: texts,
      textposition: "top center",
      textfont: { size: 9, color: t.ink, family: "IBM Plex Sans, sans-serif" },
      hoverinfo: "text",
      hovertext: hovers,
      customdata: ids,
      name: "Electrodes",
      showlegend: false,
      meta: { kind: "electrodes" },
    };
  }, [data, selectedElec, selectedBA, theme]);

  /* Plotly layout — scene background + camera defaults follow the theme. */
  const layout = _b3dMemo(() => {
    const t = _resolveThemeColors();
    return {
      scene: {
        bgcolor: t.bg,
        xaxis: { visible: false, showbackground: false },
        yaxis: { visible: false, showbackground: false },
        zaxis: { visible: false, showbackground: false },
        camera: {
          eye:    { x: -1.6, y: -1.6, z: 0.4 },
          center: { x: 0,    y: 0,    z: 0   },
          up:     { x: 0,    y: 0,    z: 1   },
        },
        aspectmode: "data",
      },
      paper_bgcolor: "rgba(0,0,0,0)",
      margin: { l: 0, r: 0, t: 0, b: 0 },
      showlegend: false,
      hoverlabel: {
        bgcolor: t.surface, bordercolor: t.border,
        font: { color: t.ink, family: "IBM Plex Sans, sans-serif", size: 12 },
      },
    };
  }, [theme]);

  /* Mount / update the figure. */
  _b3dEffect(() => {
    if (!plotRef.current || !window.Plotly) return;
    const traces = [...meshTraces, electrodeTrace];
    const config = {
      responsive: true, displaylogo: false,
      modeBarButtonsToRemove: ["toImage", "tableRotation", "resetCameraLastSave3d"],
    };
    window.Plotly.react(plotRef.current, traces, layout, config).then(() => {
      setReady(true);
    });
  }, [meshTraces, electrodeTrace, layout]);

  /* Wire click + hover handlers (rebound on each react render so they capture
   * the latest props). */
  _b3dEffect(() => {
    const plot = plotRef.current;
    if (!plot || !plot.on) return;

    function onClick(ev) {
      if (!ev || !ev.points || ev.points.length === 0) return;
      const pt = ev.points[0];
      const kind = pt.data?.meta?.kind;
      if (kind === "electrodes") {
        onSelectElectrode(pt.customdata);
      } else if (kind === "mesh") {
        const hemiKey = pt.data.meta.hemi;
        const hemi = data.mesh[hemiKey];
        const ba = hemi.ba_labels[pt.pointNumber];
        if (ba > 0) onSelectRegion(ba);
      }
    }
    function onHover(ev) {
      if (!ev || !ev.points || ev.points.length === 0) return;
      const pt = ev.points[0];
      const kind = pt.data?.meta?.kind;
      if (kind === "mesh") {
        const hemiKey = pt.data.meta.hemi;
        const hemi = data.mesh[hemiKey];
        const ba = hemi.ba_labels[pt.pointNumber];
        if (ba > 0) onHoverRegion(ba);
      }
    }
    function onUnhover() { onHoverRegion(null); }

    plot.on("plotly_click", onClick);
    plot.on("plotly_hover", onHover);
    plot.on("plotly_unhover", onUnhover);

    return () => {
      // Plotly doesn't expose `off` for these events — purge() is too heavy.
      // Replace event handlers by reassigning the internal _ev (best-effort).
      if (plot.removeAllListeners) {
        plot.removeAllListeners("plotly_click");
        plot.removeAllListeners("plotly_hover");
        plot.removeAllListeners("plotly_unhover");
      }
    };
  }, [data, onSelectElectrode, onSelectRegion, onHoverRegion]);

  /* Cleanup on unmount. */
  _b3dEffect(() => () => {
    if (plotRef.current && window.Plotly) {
      window.Plotly.purge(plotRef.current);
    }
  }, []);

  return (
    <div className="brain3dwrap" ref={wrapRef}>
      <div ref={plotRef} className="brain3dplot" />
      {!ready && <div className="brain3d-spinner">Rendering mesh… (~1–2 s)</div>}
      <div className="braincount">
        All <strong>{data.electrodes.length}</strong> electrodes in real
        tkRAS coordinates · cortex semi-transparent so deep contacts stay visible.
      </div>
    </div>
  );
}

Object.assign(window, { Brain3D });
