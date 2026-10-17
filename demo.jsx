import React, { useState, useMemo } from "react";

// ---- mock data (stand-in for real /scan API responses) ----------------
const PAIRS_DB = {
  double_bottom: [
    { pair: "GBP/JPY", tf: "4h", score: 91, stage: "complete", detail: "Neckline broken at 191.420, breakout confirmed", spark: [3,2,1,0,1,3,2,1,0,2,4,5,6] },
    { pair: "EUR/USD", tf: "1h", score: 78, stage: "near_complete", detail: "Two troughs near 1.08420, watching neckline 1.08910", spark: [4,3,2,1,2,3,2,1,2,3,3.4,3.6,3.5] },
    { pair: "AUD/USD", tf: "4h", score: 63, stage: "forming", detail: "Two troughs near 0.65310, watching neckline 0.65890", spark: [5,4,3,2,3,4,3,2.5,3,3.2,3.4,3.3,3.1] },
    { pair: "USD/CAD", tf: "1day", score: 55, stage: "forming", detail: "Two troughs near 1.36200, watching neckline 1.37050", spark: [2,2.5,2,1.5,2,2.8,2,1.7,2.1,2.4,2.6,2.5,2.3] },
  ],
  bull_flag: [
    { pair: "USD/JPY", tf: "1h", score: 88, stage: "near_complete", detail: "Bull pole then consolidation, channel top 156.240", spark: [1,3,5,7,6.8,6.9,6.7,6.8,6.9,6.85,6.9,6.95,6.9] },
    { pair: "NZD/USD", tf: "4h", score: 74, stage: "forming", detail: "Bull pole then consolidation, channel top 0.59680", spark: [1,2,4,6,5.8,5.9,5.7,5.9,5.8,5.85,5.9,5.88,5.9] },
    { pair: "EUR/JPY", tf: "4h", score: 68, stage: "forming", detail: "Bull pole then consolidation, channel top 169.310", spark: [2,3,5,7,6.9,6.85,6.8,6.9,6.85,6.9,6.88,6.9,6.87] },
  ],
  ascending_triangle: [
    { pair: "EUR/GBP", tf: "1day", score: 82, stage: "near_complete", detail: "Flat resistance, rising support — apex close, width tightening", spark: [3,4,3.5,4,3.8,4,3.9,4,3.95,4,3.97,4,3.98] },
    { pair: "AUD/JPY", tf: "4h", score: 59, stage: "forming", detail: "Flat resistance, rising support", spark: [2,4,3,4,3.4,4,3.6,4,3.7,4,3.75,4,3.8] },
  ],
};

const PATTERN_LABELS = {
  double_bottom: "Double bottom",
  bull_flag: "Bull flag",
  ascending_triangle: "Ascending triangle",
};

const STAGE_META = {
  complete: { label: "Breakout confirmed", color: "#3ED598" },
  near_complete: { label: "Near completion", color: "#F2A93B" },
  forming: { label: "Forming", color: "#5B6472" },
};

function Sparkline({ data, color }) {
  const w = 96, h = 28, pad = 2;
  const min = Math.min(...data), max = Math.max(...data);
  const range = max - min || 1;
  const pts = data.map((v, i) => {
    const x = pad + (i / (data.length - 1)) * (w - pad * 2);
    const y = h - pad - ((v - min) / range) * (h - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function ForexSetupScanner() {
  const [inputMode, setInputMode] = useState("text");
  const [text, setText] = useState("double bottom with a clear neckline, looking for pairs about to break out");
  const [imageName, setImageName] = useState(null);
  const [status, setStatus] = useState("idle"); // idle | scanning | done
  const [patternKey, setPatternKey] = useState(null);
  const [minStage, setMinStage] = useState("forming");

  const results = patternKey ? PAIRS_DB[patternKey] || [] : [];

  const filtered = useMemo(() => {
    const order = { forming: 0, near_complete: 1, complete: 2 };
    return results.filter(r => order[r.stage] >= order[minStage]);
  }, [results, minStage]);

  function runScan() {
    setStatus("scanning");
    setTimeout(() => {
      const keys = Object.keys(PAIRS_DB);
      const guess = text.toLowerCase().includes("flag") ? "bull_flag"
        : text.toLowerCase().includes("triangle") ? "ascending_triangle"
        : "double_bottom";
      setPatternKey(guess);
      setStatus("done");
    }, 1100);
  }

  const font = { body: "'IBM Plex Mono', ui-monospace, monospace", head: "'Space Grotesk', 'IBM Plex Mono', sans-serif" };
  const bg = "#0B0E13", panel = "#12161D", border = "#232A34", textPrimary = "#E7E9ED", textSecondary = "#7C8494", accent = "#F2A93B";

  return (
    <div style={{ background: bg, color: textPrimary, fontFamily: font.body, padding: "28px 24px", borderRadius: 12, maxWidth: 760 }}>
      <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500&family=IBM+Plex+Mono:wght@400;500&display=swap" />

      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 4 }}>
        <div style={{ fontFamily: font.head, fontSize: 18, fontWeight: 500, letterSpacing: 0.2 }}>Setup scanner</div>
        <div style={{ fontSize: 11, color: textSecondary, letterSpacing: 1 }}>FOREX &middot; DEMO DATA</div>
      </div>
      <div style={{ fontSize: 12, color: textSecondary, marginBottom: 20 }}>
        Paste a setup, get the pairs currently forming it or already breaking out.
      </div>

      {/* input mode toggle */}
      <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
        {["text", "image"].map(m => (
          <button key={m} onClick={() => setInputMode(m)}
            style={{
              background: inputMode === m ? panel : "transparent",
              border: `1px solid ${inputMode === m ? accent : border}`,
              color: inputMode === m ? accent : textSecondary,
              borderRadius: 6, padding: "5px 12px", fontSize: 11, fontFamily: font.body,
              letterSpacing: 0.5, cursor: "pointer", textTransform: "uppercase"
            }}>
            {m === "text" ? "Describe setup" : "Upload chart"}
          </button>
        ))}
      </div>

      {inputMode === "text" ? (
        <textarea value={text} onChange={e => setText(e.target.value)} rows={3}
          style={{
            width: "100%", background: panel, border: `1px solid ${border}`, borderRadius: 8,
            color: textPrimary, fontFamily: font.body, fontSize: 13, padding: 12, resize: "vertical", boxSizing: "border-box"
          }} />
      ) : (
        <label style={{
          display: "flex", alignItems: "center", justifyContent: "center", height: 74,
          border: `1px dashed ${border}`, borderRadius: 8, color: textSecondary, fontSize: 12, cursor: "pointer"
        }}>
          {imageName || "Click to attach a chart screenshot (PNG/JPG)"}
          <input type="file" accept="image/*" style={{ display: "none" }}
            onChange={e => setImageName(e.target.files[0]?.name || null)} />
        </label>
      )}

      <button onClick={runScan} disabled={status === "scanning"}
        style={{
          marginTop: 12, background: accent, color: "#241705", border: "none", borderRadius: 8,
          padding: "9px 18px", fontFamily: font.head, fontWeight: 500, fontSize: 13, cursor: "pointer",
          opacity: status === "scanning" ? 0.6 : 1
        }}>
        {status === "scanning" ? "Scanning 12 pairs \u00d7 3 timeframes\u2026" : "Scan forex pairs"}
      </button>

      {status === "done" && (
        <div style={{ marginTop: 26 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
            <div style={{ fontSize: 13, color: textSecondary }}>
              Interpreted as <span style={{ color: textPrimary }}>{PATTERN_LABELS[patternKey]}</span> &middot; {filtered.length} match{filtered.length === 1 ? "" : "es"}
            </div>
            <select value={minStage} onChange={e => setMinStage(e.target.value)}
              style={{ background: panel, color: textSecondary, border: `1px solid ${border}`, borderRadius: 6, fontSize: 11, padding: "4px 8px", fontFamily: font.body }}>
              <option value="forming">All stages</option>
              <option value="near_complete">Near-complete & complete</option>
              <option value="complete">Complete only</option>
            </select>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {filtered.map((r, i) => {
              const meta = STAGE_META[r.stage];
              return (
                <div key={i} style={{
                  background: panel, border: `1px solid ${border}`, borderRadius: 8,
                  padding: "12px 14px", display: "flex", alignItems: "center", gap: 14
                }}>
                  <div style={{ width: 78 }}>
                    <div style={{ fontFamily: font.head, fontSize: 14, fontWeight: 500 }}>{r.pair}</div>
                    <div style={{ fontSize: 10, color: textSecondary }}>{r.tf}</div>
                  </div>
                  <Sparkline data={r.spark} color={meta.color} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12, color: textPrimary, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.detail}</div>
                    <div style={{ fontSize: 10, color: meta.color, marginTop: 2, letterSpacing: 0.3 }}>{meta.label.toUpperCase()}</div>
                  </div>
                  <div style={{ textAlign: "right", width: 44 }}>
                    <div style={{ fontFamily: font.head, fontSize: 15, fontWeight: 500 }}>{r.score}</div>
                    <div style={{ fontSize: 9, color: textSecondary }}>score</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {status === "idle" && (
        <div style={{ marginTop: 20, fontSize: 11, color: textSecondary, lineHeight: 1.6 }}>
          Demo runs on mock data. Wired to the real backend, this calls <code>POST /scan</code> and returns live matches from Twelve Data.
        </div>
      )}
    </div>
  );
}
