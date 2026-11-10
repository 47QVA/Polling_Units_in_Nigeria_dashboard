"""
Nigeria Polling Units - Performance Dashboard (Streamlit)
Run:  streamlit run app.py
Needs: pip install streamlit pandas plotly requests
Put Nigeria_polling_units.csv in the same folder as this file.
Optional (offline): put nigeria_states.geojson in the same folder.
"""
import json, difflib
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

BASE = Path(__file__).parent
CSV_PATH = BASE / "Nigeria_polling_units.csv"
LOCAL_GEOJSON = BASE / "nigeria_states.geojson"
GEOJSON_URLS = [
    "https://github.com/wmgeolab/geoBoundaries/raw/main/releaseData/gbOpen/NGA/ADM1/geoBoundaries-NGA-ADM1_simplified.geojson",
    "https://raw.githubusercontent.com/wmgeolab/geoBoundaries/main/releaseData/gbOpen/NGA/ADM1/geoBoundaries-NGA-ADM1_simplified.geojson",
]

COLORS = {"75 - 100%": "#5B4B9E", "50 - 75%": "#8FC69A", "25 - 50%": "#F9BE6E", "0 - 25%": "#F07A45"}

ZONES = {
    "North Central": ["benue", "kogi", "kwara", "nasarawa", "niger", "plateau", "fct"],
    "North East": ["adamawa", "bauchi", "borno", "gombe", "taraba", "yobe"],
    "North West": ["jigawa", "kaduna", "kano", "katsina", "kebbi", "sokoto", "zamfara"],
    "South East": ["abia", "anambra", "ebonyi", "enugu", "imo"],
    "South South": ["akwa ibom", "bayelsa", "cross river", "delta", "edo", "rivers"],
    "South West": ["ekiti", "lagos", "ogun", "ondo", "osun", "oyo"],
}
STATE_ZONE = {s: z for z, ss in ZONES.items() for s in ss}

# key: (group, label, question, column)
INDICATORS = {
    "COVERAGE INDICATORS": [
        ("Polling units", "How many polling units are in each state?", "polling_units"),
        ("Wards", "How many wards are in each state?", "wards"),
        ("LGAs", "How many LGAs are in each state?", "lgas"),
        ("Senatorial districts", "How many senatorial districts per state?", "senatorial"),
        ("Federal constituencies", "How many federal constituencies per state?", "constituencies"),
    ],
    "DENSITY INDICATORS": [
        ("PUs per ward", "Average polling units per ward?", "pu_per_ward"),
        ("PUs per LGA", "Average polling units per LGA?", "pu_per_lga"),
        ("Wards per LGA", "Average wards per LGA?", "ward_per_lga"),
        ("Largest ward (PUs)", "Largest ward size by polling units?", "max_ward_pu"),
        ("Share of national PUs", "Share of national polling units (%)?", "share_pct"),
    ],
}
IND_LOOKUP = {lbl: (q, col) for g in INDICATORS.values() for lbl, q, col in g}
DEFAULT_IND = "Polling units"

st.set_page_config(page_title="Polling Units Dashboard", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
.block-container{padding-top:1.5rem;padding-bottom:1rem;max-width:100%}
[data-testid="stHeader"],.stAppHeader{display:none}
[data-testid="stToolbar"]{display:none}
[data-testid="stSidebar"]{display:none}
.big-title{display:flex;align-items:center;gap:14px;min-height:76px}
.big-title .q{font-size:64px;font-weight:800;color:#2F3A4A;line-height:1.15}
.big-title .t{border-left:2px solid #ccc;padding-left:12px;font-size:22px;font-weight:700;color:#2F3A4A;line-height:1.2}
.grp{font-size:12px;font-weight:700;color:#8A94A6;letter-spacing:1px;margin:14px 0 6px}
div[data-testid="stButton"] button{border-radius:20px;border:1px solid #DDE1E7;background:#fff;color:#2F3A4A;
  padding:2px 14px;font-size:14px;justify-content:flex-start}
div[data-testid="stButton"] button[kind="primary"]{background:#F5EEF8;border-color:#7B3F8C;color:#2F3A4A}
.kpi{display:flex;align-items:center;gap:10px}
.kpi .dot{width:14px;height:14px;border-radius:50%;background:#E0531F}
.kpi .n{font-size:34px;font-weight:800;color:#2F3A4A;line-height:1}
.kpi .s{font-size:13px;color:#555}
.question{text-align:center;font-size:24px;font-weight:700;color:#5E6B7D;margin:8px 0}
.legend{display:grid;grid-template-columns:auto auto;gap:6px 28px;font-size:15px;color:#2F3A4A}
.legend span{display:inline-block;width:40px;height:16px;margin-right:10px;vertical-align:middle}
.note{font-size:12px;color:#8A94A6}
.rhead{color:#8A94A6;font-size:15px}
.beta{background:#EFE3FA;color:#7B3F8C;font-size:11px;border-radius:10px;padding:2px 8px;margin-left:6px}
@media (max-width: 1100px){
  .big-title{gap:8px;min-height:60px}
  .big-title .q{font-size:48px}
  .big-title .t{font-size:17px}
  .legend{gap:6px;font-size:12px}
  .legend span{width:24px;margin-right:6px}
}
</style>""", unsafe_allow_html=True)


# ---------------- DATA ----------------
@st.cache_data(show_spinner="Loading polling units...")
def load_data(path):
    df = pd.read_csv(path, dtype=str).drop(columns=["Unnamed: 0", ""], errors="ignore")
    for c in ["state", "lg", "ward", "location", "senatorial", "house_of_rep"]:
        df[c] = df[c].fillna("").str.strip().str.lower()
    df["lga_key"] = df["state"] + "|" + df["lg_code"]
    df["ward_key"] = df["lga_key"] + "|" + df["ward_code"]
    df["zone"] = df["state"].map(STATE_ZONE).fillna("Unknown")
    return df


@st.cache_data
def state_metrics(df):
    g = df.groupby("state")
    m = pd.DataFrame({
        "polling_units": g.size(),
        "wards": g["ward_key"].nunique(),
        "lgas": g["lga_key"].nunique(),
        "senatorial": g["senatorial"].nunique(),
        "constituencies": g["house_of_rep"].nunique(),
        "max_ward_pu": df.groupby(["state", "ward_key"]).size().groupby("state").max(),
    })
    m["pu_per_ward"] = (m.polling_units / m.wards).round(1)
    m["pu_per_lga"] = (m.polling_units / m.lgas).round(1)
    m["ward_per_lga"] = (m.wards / m.lgas).round(1)
    m["share_pct"] = (m.polling_units / m.polling_units.sum() * 100).round(2)
    m["zone"] = m.index.map(STATE_ZONE)
    return m.reset_index()


def _norm(s):
    s = str(s).lower().replace(" state", "").replace("-", " ").strip()
    if "capital" in s or "abuja" in s or s == "fct":
        return "fct"
    return {"nassarawa": "nasarawa", "akwa-ibom": "akwa ibom", "cross-river": "cross river"}.get(s, s)


@st.cache_data(show_spinner="Loading map...")
def load_geojson(states):
    gj = None
    if LOCAL_GEOJSON.exists():
        gj = json.loads(LOCAL_GEOJSON.read_text(encoding="utf-8"))
    else:
        for url in GEOJSON_URLS:
            try:
                r = requests.get(url, timeout=20)
                r.raise_for_status()
                gj = r.json()
                break
            except Exception:
                continue
    if not gj:
        return None
    # auto-detect the property holding the state name
    props = gj["features"][0]["properties"]
    best, score = None, -1
    for k, v in props.items():
        if isinstance(v, str):
            hits = sum(_norm(f["properties"].get(k, "")) in states for f in gj["features"])
            if hits > score:
                best, score = k, hits
    for f in gj["features"]:
        n = _norm(f["properties"].get(best, ""))
        if n not in states:
            close = difflib.get_close_matches(n, states, n=1, cutoff=0.6)
            n = close[0] if close else n
        f["id"] = n
        f["properties"]["dashboard_state"] = n
    return gj


def centroids(gj):
    out = {}
    for f in gj["features"]:
        geom = f["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        ring = max((p[0] for p in polys), key=len)
        out[f["id"]] = (sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring))
    return out


def _inside_ring(lon, lat, ring):
    inside = False
    x1, y1 = ring[-1]
    for x2, y2 in ring:
        if (y2 > lat) != (y1 > lat) and lon < (x1 - x2) * (lat - y2) / (y1 - y2) + x2:
            inside = not inside
        x1, y1 = x2, y2
    return inside


@st.cache_data(show_spinner=False)
def map_click_targets(gj, states, spacing=0.15):
    targets = []
    for feature in gj["features"]:
        state = feature["properties"]["dashboard_state"]
        if state not in states:
            continue
        geometry = feature["geometry"]
        polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
        for polygon in polygons:
            outer = polygon[0]
            min_lon, max_lon = min(p[0] for p in outer), max(p[0] for p in outer)
            min_lat, max_lat = min(p[1] for p in outer), max(p[1] for p in outer)
            lon = (int(min_lon / spacing) + 0.5) * spacing
            while lon < max_lon:
                lat = (int(min_lat / spacing) + 0.5) * spacing
                while lat < max_lat:
                    if _inside_ring(lon, lat, outer) and not any(
                        _inside_ring(lon, lat, hole) for hole in polygon[1:]
                    ):
                        targets.append((state, lon, lat))
                    lat += spacing
                lon += spacing
    return targets


def bucket(pct):
    if pct >= 75: return "75 - 100%"
    if pct >= 50: return "50 - 75%"
    if pct >= 25: return "25 - 50%"
    return "0 - 25%"


# ---------------- STATE ----------------
ss = st.session_state
ss.setdefault("indicator", DEFAULT_IND)
ss.setdefault("zone", "All zones")
ss.setdefault("state", "All states")
ss.setdefault("search", "")
ss.setdefault("map_version", 0)


def reset():
    ss.indicator, ss.zone, ss.state, ss.search = DEFAULT_IND, "All zones", "All states", ""
    ss.map_version += 1


def on_state_change():
    ss.map_version += 1


def on_zone_change():
    ss.map_version += 1


if not CSV_PATH.exists():
    st.error(f"CSV not found: {CSV_PATH}")
    st.stop()

df = load_data(str(CSV_PATH))
metrics = state_metrics(df)
all_states = sorted(metrics.state)
pending_state = ss.pop("_pending_map_state", None)
if pending_state in all_states:
    ss.state = pending_state
    ss.map_version += 1

left, mid, right = st.columns([1.15, 2.7, 1.35], gap="medium")

# ---------------- LEFT: indicators ----------------
with left:
    st.markdown('<div class="big-title"><div class="q">PU</div><div class="t">Performance<br>Dashboard</div></div>',
                unsafe_allow_html=True)
    c1, c2 = st.columns([1.4, 1])
    c1.text_input("Search", key="search", placeholder="🔍 Search Indicators", label_visibility="collapsed")
    c2.button("↺ Reset Filters", on_click=reset, width="stretch")
    with st.container(height=560, border=False):
        q = ss.search.lower()
        for grp, items in INDICATORS.items():
            shown = [i for i in items if q in i[0].lower()]
            if not shown:
                continue
            st.markdown(f'<div class="grp">{grp}</div>', unsafe_allow_html=True)
            for lbl, _, _ in shown:
                if st.button(f"⌂  {lbl}", key=f"ind_{lbl}",
                             type="primary" if ss.indicator == lbl else "secondary"):
                    ss.indicator = lbl
                    st.rerun()

# ---------------- MIDDLE: KPI + map ----------------
question, col = IND_LOOKUP[ss.indicator]
view = metrics if ss.zone == "All zones" else metrics[metrics.zone == ss.zone]
fdf = df if ss.zone == "All zones" else df[df.zone == ss.zone]
if ss.state != "All states":
    fdf = fdf[fdf.state == ss.state]

with mid:
    k, f1, f2 = st.columns([1.3, 1, 1])
    k.markdown(f'<div class="kpi"><div class="dot"></div><div><div class="n">{len(fdf):,}</div>'
               f'<div class="s">Polling units tracked</div></div></div>', unsafe_allow_html=True)
    f1.selectbox("Zone", ["All zones"] + list(ZONES), key="zone", label_visibility="collapsed",
                 on_change=on_zone_change)
    opts = ["All states"] + (all_states if ss.zone == "All zones" else sorted(view.state))
    if ss.state not in opts:
        ss.state = "All states"
    f2.selectbox("State", opts, key="state", label_visibility="collapsed",
                 format_func=lambda s: s.title() if s != "fct" else "FCT",
                 on_change=on_state_change)

    st.markdown(f'<div class="question">{question}</div>', unsafe_allow_html=True)

    lg1, lg2 = st.columns([1.2, 1])
    lg1.markdown('<div class="legend">' + "".join(
        f'<div><span style="background:{COLORS[b]}"></span>{b}</div>'
        for b in ["75 - 100%", "25 - 50%", "50 - 75%", "0 - 25%"]) + "</div>", unsafe_allow_html=True)
    lg2.markdown('<div class="note">Each score is the state value as a % of the highest state for the selected '
                 'indicator and zone. Click a state to view more information.</div>',
                 unsafe_allow_html=True)

    plot = view[["state", col, "zone"]].copy()
    mx = plot[col].max() or 1
    plot["score"] = (plot[col] / mx * 100).round(1)
    plot["band"] = plot["score"].apply(bucket)

    gj = load_geojson(tuple(all_states))
    if gj:
        cen = centroids(gj)
        values = plot.set_index("state")
        fig = go.Figure()
        for feature in gj["features"]:
            state = feature["properties"]["dashboard_state"]
            if state not in values.index:
                continue
            geometry = feature["geometry"]
            polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
            row = values.loc[state]
            for polygon in polygons:
                ring = polygon[0]
                fig.add_trace(go.Scatter(
                    x=[point[0] for point in ring], y=[point[1] for point in ring],
                    mode="lines", fill="toself", fillcolor=COLORS[row["band"]],
                    customdata=[[state, row[col], row["score"]] for _ in ring],
                    line=dict(color="#E0531F" if state == ss.state else "#2F3A4A",
                              width=2.5 if state == ss.state else 0.8),
                    hoveron="fills", hovertemplate="<b>" +
                    ("FCT" if state == "fct" else state.title()) + "</b><br>" + ss.indicator +
                    ": %{customdata[1]:,}<br>Score: %{customdata[2]}%<extra></extra>",
                    showlegend=False))
        labels = [state for state in plot.state if state in cen]
        targets = map_click_targets(gj, tuple(labels))
        target_values = [values.loc[state] for state, _, _ in targets]
        fig.add_trace(go.Scatter(
            x=[lon for _, lon, _ in targets], y=[lat for _, _, lat in targets],
            customdata=[[state, row[col], row["score"]] for (state, _, _), row in zip(targets, target_values)],
            mode="markers", marker=dict(size=18, color="rgba(0,0,0,0.01)", line=dict(width=0)),
            hovertemplate="<b>%{customdata[0]}</b><br>" + ss.indicator +
                          ": %{customdata[1]:,}<br>Score: %{customdata[2]}%<extra></extra>",
            showlegend=False))
        fig.add_trace(go.Scatter(
            x=[cen[state][0] for state in labels], y=[cen[state][1] for state in labels],
            text=["FCT" if state == "fct" else state.title() for state in labels],
            customdata=[[state, values.loc[state, col], values.loc[state, "score"]] for state in labels],
            mode="markers+text", textposition="middle center",
            textfont=dict(size=9, color="#2F3A4A"),
            marker=dict(size=12, color="rgba(0,0,0,0.01)", line=dict(width=0)),
            hovertemplate="<b>%{text}</b><br>" + ss.indicator +
                          ": %{customdata[1]:,}<br>Score: %{customdata[2]}%<extra></extra>",
            showlegend=False))
        fig.update_xaxes(range=[2, 15], visible=False, fixedrange=True, constrain="domain")
        fig.update_yaxes(range=[3.5, 14.2], visible=False, fixedrange=True,
                         scaleanchor="x", scaleratio=1, constrain="domain")
        fig.update_layout(height=600, margin=dict(l=0, r=0, t=0, b=0), dragmode=False,
                          clickmode="event+select",
                          showlegend=False, plot_bgcolor="rgba(0,0,0,0)",
                          paper_bgcolor="rgba(0,0,0,0)")
        ev = st.plotly_chart(fig, width="stretch", on_select="rerun", selection_mode="points",
                             key=f"map_{ss.map_version}", config={"displayModeBar": False})
        pts = (ev or {}).get("selection", {}).get("points", [])
        clicked_state = None
        if pts:
            point = pts[0]
            clicked_state = point.get("location") or (
                point.get("customdata", [None])[0] if point.get("customdata") else None)
        if clicked_state in all_states and clicked_state != ss.state:
            ss["_pending_map_state"] = clicked_state
            st.rerun()
    else:
        st.warning("Map boundaries unavailable (no internet). Save nigeria_states.geojson beside app.py. "
                   "Showing bar chart instead.")
        p = plot.sort_values(col)
        fig = go.Figure(go.Bar(x=p[col], y=p.state.str.title(), orientation="h",
                               marker_color=[COLORS[b] for b in p.band]))
        fig.update_layout(height=900, margin=dict(l=0, r=0, t=0, b=0))
        st.plotly_chart(fig, width="stretch")

# ---------------- RIGHT: drill-down ----------------
with right:
    scope = "Nigeria" if ss.state == "All states" else ("FCT" if ss.state == "fct" else ss.state.title())
    st.markdown(f'<div class="rhead">Drill-down: <b>{scope}</b><span class="beta">beta mode</span></div>',
                unsafe_allow_html=True)

    with st.expander("STATE SUMMARY", expanded=True):
        a, b = st.columns(2)
        a.metric("Polling units", f"{len(fdf):,}")
        b.metric("Wards", f"{fdf.ward_key.nunique():,}")
        a.metric("LGAs", f"{fdf.lga_key.nunique():,}")
        b.metric("Senatorial", f"{fdf.senatorial.nunique():,}")
        a.metric("Fed. constituencies", f"{fdf.house_of_rep.nunique():,}")
        b.metric("PUs / ward", f"{len(fdf) / max(fdf.ward_key.nunique(), 1):.1f}")

    with st.expander("STATE RANKING"):
        r = view[["state", col]].sort_values(col, ascending=False).reset_index(drop=True)
        r.index += 1
        r["state"] = r.state.str.title()
        st.dataframe(r.rename(columns={"state": "State", col: ss.indicator}), width="stretch", height=300)

    with st.expander("LGA BREAKDOWN"):
        lga = fdf.groupby(["state", "lg"]).agg(PUs=("code", "size"), Wards=("ward_key", "nunique")) \
            .reset_index().sort_values("PUs", ascending=False)
        lga.columns = ["State", "LGA", "PUs", "Wards"]
        st.dataframe(lga, hide_index=True, width="stretch", height=300)

    with st.expander("WARD BREAKDOWN"):
        w = fdf.groupby(["state", "lg", "ward"]).size().reset_index(name="PUs").sort_values("PUs", ascending=False)
        w.columns = ["State", "LGA", "Ward", "PUs"]
        st.dataframe(w, hide_index=True, width="stretch", height=300)

    with st.expander("SENATORIAL & CONSTITUENCIES"):
        s = fdf.groupby("senatorial").size().reset_index(name="PUs").sort_values("PUs", ascending=False)
        st.dataframe(s.rename(columns={"senatorial": "Senatorial district"}), hide_index=True,
                     width="stretch", height=200)
        h = fdf.groupby("house_of_rep").size().reset_index(name="PUs").sort_values("PUs", ascending=False)
        st.dataframe(h.rename(columns={"house_of_rep": "Federal constituency"}), hide_index=True,
                     width="stretch", height=200)

    with st.expander("FIND A POLLING UNIT"):
        term = st.text_input("Location / code", placeholder="e.g. primary school or 10/12/01/033")
        if term:
            t = term.lower()
            hit = fdf[fdf.location.str.contains(t, regex=False) | fdf.code.str.contains(t, regex=False)]
            st.caption(f"{len(hit):,} match(es)")
            st.dataframe(hit[["code", "state", "lg", "ward", "location"]].head(500), hide_index=True,
                         width="stretch", height=300)
        st.download_button("⬇ Download filtered data (CSV)", fdf.drop(columns=["lga_key", "ward_key"])
                           .to_csv(index=False).encode(), f"polling_units_{scope}.csv", "text/csv")
