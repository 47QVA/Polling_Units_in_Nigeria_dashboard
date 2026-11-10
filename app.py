"""
Nigeria Polling Units - mobile-first Streamlit dashboard.
Run with: streamlit run app.py
"""
import difflib
import json
import re
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

BASE = Path(__file__).parent
CSV_PATH = BASE / "Nigeria_polling_units.csv"
LOCAL_GEOJSON = BASE / "nigeria_states.geojson"
LOCAL_LGA_GEOJSON = BASE / "nigeria_lgas.geojson"
GEOJSON_URLS = [
    "https://github.com/wmgeolab/geoBoundaries/raw/main/releaseData/gbOpen/NGA/ADM1/geoBoundaries-NGA-ADM1_simplified.geojson",
    "https://raw.githubusercontent.com/wmgeolab/geoBoundaries/main/releaseData/gbOpen/NGA/ADM1/geoBoundaries-NGA-ADM1_simplified.geojson",
]
LGA_GEOJSON_URLS = [
    "https://github.com/wmgeolab/geoBoundaries/raw/main/releaseData/gbOpen/NGA/ADM2/geoBoundaries-NGA-ADM2_simplified.geojson",
    "https://raw.githubusercontent.com/wmgeolab/geoBoundaries/main/releaseData/gbOpen/NGA/ADM2/geoBoundaries-NGA-ADM2_simplified.geojson",
]

COLORS = {
    "75 - 100%": "#8B5CF6",
    "50 - 75%": "#34D399",
    "25 - 50%": "#FBBF24",
    "0 - 25%": "#FB7185",
}
MAP_BG = "#0E1117"
MAP_TEXT = "#E2E8F0"
MAP_BORDER = "#475569"
MAP_HIGHLIGHT = "#F8FAFC"

ZONES = {
    "North Central": ["benue", "kogi", "kwara", "nasarawa", "niger", "plateau", "fct"],
    "North East": ["adamawa", "bauchi", "borno", "gombe", "taraba", "yobe"],
    "North West": ["jigawa", "kaduna", "kano", "katsina", "kebbi", "sokoto", "zamfara"],
    "South East": ["abia", "anambra", "ebonyi", "enugu", "imo"],
    "South South": ["akwa ibom", "bayelsa", "cross river", "delta", "edo", "rivers"],
    "South West": ["ekiti", "lagos", "ogun", "ondo", "osun", "oyo"],
}
STATE_ZONE = {state: zone for zone, states in ZONES.items() for state in states}

INDICATORS = {
    "Polling units": ("How many polling units are in each state?", "polling_units"),
    "Wards": ("How many wards are in each state?", "wards"),
    "LGAs": ("How many LGAs are in each state?", "lgas"),
    "Senatorial districts": ("How many senatorial districts per state?", "senatorial"),
    "Federal constituencies": ("How many federal constituencies per state?", "constituencies"),
    "PUs per ward": ("Average polling units per ward?", "pu_per_ward"),
    "PUs per LGA": ("Average polling units per LGA?", "pu_per_lga"),
    "Wards per LGA": ("Average wards per LGA?", "ward_per_lga"),
    "Largest ward (PUs)": ("Largest ward size by polling units?", "max_ward_pu"),
    "Share of national PUs": ("Share of national polling units (%)?", "share_pct"),
}
DEFAULT_IND = "Polling units"
LGA_ALIASES = {
    ("adamawa", "girei"): "gire 1",
    ("fct", "municipal area council"): "municipal",
    ("sokoto", "sabon birni"): "s/birni",
    ("borno", "maiduguri"): "maiduguri m. c.",
    ("ogun", "yewa south"): "egbado south",
    ("ogun", "yewa north"): "egbado north",
    ("kebbi", "arewa dandi"): "arewa",
    ("kogi", "kogi"): "kogi . k. k.",
    ("abia", "osisioma ngwa"): "osisioma",
    ("imo", "ezinihitte"): "ezinihitte mbaise",
    ("kogi", "ogori magongo"): "ogori mangogo",
}

st.set_page_config(page_title="Nigeria Polling Units", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
<style>
.block-container{padding:.9rem 1rem 2rem;max-width:900px}
[data-testid="stHeader"],.stAppHeader,[data-testid="stToolbar"],[data-testid="stSidebar"]{display:none}
[data-testid="stBaseButton-secondary"],[data-testid="stBaseButton-primary"]{min-height:44px}
[data-testid="stSelectbox"] [role="combobox"]{min-height:44px}
[data-testid="stPlotlyChart"]{width:100%;margin:0 auto}
.map-legend{display:flex;flex-wrap:wrap;gap:8px 16px;font-size:.85rem}
.map-legend span{display:inline-flex;align-items:center;gap:6px;white-space:nowrap}
.map-legend i{width:18px;height:12px;border-radius:3px;display:inline-block}
.subtle{color:var(--text-color);opacity:.72}
@media (max-width:700px){
  .block-container{padding:.7rem .75rem 1.5rem}
  h1{font-size:1.65rem!important}
  h2{font-size:1.35rem!important}
  [data-testid="stMetricValue"]{font-size:1.35rem}
  [data-testid="stPlotlyChart"]{margin-left:-.25rem;width:calc(100% + .5rem)}
}
</style>
""", unsafe_allow_html=True)


@st.cache_data(show_spinner="Loading polling units...")
def load_data(path):
    df = pd.read_csv(path, dtype=str).drop(columns=["Unnamed: 0", ""], errors="ignore")
    for column in ["state", "lg", "ward", "location", "senatorial", "house_of_rep"]:
        df[column] = df[column].fillna("").str.strip().str.lower()
    df["lga_key"] = df["state"] + "|" + df["lg_code"]
    df["ward_key"] = df["lga_key"] + "|" + df["ward_code"]
    df["zone"] = df["state"].map(STATE_ZONE).fillna("Unknown")
    return df


@st.cache_data
def state_metrics(df):
    groups = df.groupby("state")
    metrics = pd.DataFrame({
        "polling_units": groups.size(),
        "wards": groups["ward_key"].nunique(),
        "lgas": groups["lga_key"].nunique(),
        "senatorial": groups["senatorial"].nunique(),
        "constituencies": groups["house_of_rep"].nunique(),
        "max_ward_pu": df.groupby(["state", "ward_key"]).size().groupby("state").max(),
    })
    metrics["pu_per_ward"] = (metrics.polling_units / metrics.wards).round(1)
    metrics["pu_per_lga"] = (metrics.polling_units / metrics.lgas).round(1)
    metrics["ward_per_lga"] = (metrics.wards / metrics.lgas).round(1)
    metrics["share_pct"] = (metrics.polling_units / metrics.polling_units.sum() * 100).round(2)
    metrics["zone"] = metrics.index.map(STATE_ZONE)
    return metrics.reset_index()


def _norm(value):
    name = str(value).lower().replace(" state", "").replace("-", " ").strip()
    if "capital" in name or "abuja" in name or name == "fct":
        return "fct"
    return {"nassarawa": "nasarawa", "akwa-ibom": "akwa ibom", "cross-river": "cross river"}.get(name, name)


def _key(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()


def _outer_rings(geometry):
    polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
    return [polygon[0] for polygon in polygons]


def _inside_ring(lon, lat, ring):
    inside = False
    x1, y1 = ring[-1]
    for x2, y2 in ring:
        if (y2 > lat) != (y1 > lat) and lon < (x1 - x2) * (lat - y2) / (y1 - y2) + x2:
            inside = not inside
        x1, y1 = x2, y2
    return inside


@st.cache_data(show_spinner="Loading state boundaries...")
def load_geojson(states):
    geojson = None
    if LOCAL_GEOJSON.exists():
        geojson = json.loads(LOCAL_GEOJSON.read_text(encoding="utf-8"))
    else:
        for url in GEOJSON_URLS:
            try:
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                geojson = response.json()
                break
            except requests.RequestException:
                continue
    if not geojson or not geojson.get("features"):
        return None

    properties = geojson["features"][0]["properties"]
    best = max(
        (key for key, value in properties.items() if isinstance(value, str)),
        key=lambda key: sum(_norm(feature["properties"].get(key, "")) in states
                            for feature in geojson["features"]),
        default=None,
    )
    if best is None:
        return None
    for feature in geojson["features"]:
        name = _norm(feature["properties"].get(best, ""))
        if name not in states:
            close = difflib.get_close_matches(name, states, n=1, cutoff=0.6)
            name = close[0] if close else name
        feature["id"] = name
        feature["properties"]["dashboard_state"] = name
    return geojson


@st.cache_data(show_spinner="Loading local government boundaries...")
def load_lga_geojson(states, lga_pairs):
    geojson = None
    if LOCAL_LGA_GEOJSON.exists():
        geojson = json.loads(LOCAL_LGA_GEOJSON.read_text(encoding="utf-8"))
    else:
        for url in LGA_GEOJSON_URLS:
            try:
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                geojson = response.json()
                break
            except requests.RequestException:
                continue
    if not geojson or not geojson.get("features"):
        return None, []

    state_geojson = load_geojson(states)
    if not state_geojson:
        return None, []
    state_rings = {
        feature["id"]: _outer_rings(feature["geometry"])
        for feature in state_geojson["features"]
    }

    pairs_by_state = {}
    pairs_by_name = {}
    for state, lga in lga_pairs:
        pairs_by_state.setdefault(state, {})[_key(lga)] = lga
        pairs_by_name.setdefault(_key(lga), []).append((state, lga))

    features, unmatched, seen = [], [], set()
    for feature in geojson["features"]:
        boundary_name = feature["properties"].get("shapeName", "")
        boundary_key = _key(boundary_name)
        exact_matches = pairs_by_name.get(boundary_key, [])
        state = exact_matches[0][0] if len(exact_matches) == 1 else None
        if state is None:
            rings = _outer_rings(feature["geometry"])
            ring = max(rings, key=len)
            point_count = max(1, len(ring) - 1)
            lon = sum(point[0] for point in ring[:point_count]) / point_count
            lat = sum(point[1] for point in ring[:point_count]) / point_count
            state = next((
                name for name, polygons in state_rings.items()
                if any(_inside_ring(lon, lat, polygon) for polygon in polygons)
            ), None)
        if state is None:
            unmatched.append(boundary_name)
            continue

        lga_names = pairs_by_state.get(state, {})
        target_key = _key(LGA_ALIASES.get((state, boundary_key), boundary_key))
        lga_name = lga_names.get(target_key)
        if lga_name is None:
            candidates = difflib.get_close_matches(target_key, list(lga_names), n=1, cutoff=0.72)
            lga_name = lga_names[candidates[0]] if candidates else None
        if lga_name is None or (state, lga_name) in seen:
            unmatched.append(boundary_name)
            continue

        seen.add((state, lga_name))
        feature["id"] = f"{state}|{lga_name}"
        feature["properties"]["dashboard_state"] = state
        feature["properties"]["dashboard_lga"] = lga_name
        features.append(feature)

    return {"type": "FeatureCollection", "features": features}, unmatched


def centroids(geojson):
    result = {}
    for feature in geojson["features"]:
        geometry = feature["geometry"]
        rings = _outer_rings(geometry)
        ring = max(rings, key=len)
        point_count = max(1, len(ring) - 1)
        result[feature["id"]] = (
            sum(point[0] for point in ring[:point_count]) / point_count,
            sum(point[1] for point in ring[:point_count]) / point_count,
        )
    return result


@st.cache_data(show_spinner=False)
def map_click_targets(geojson, states, spacing=0.15):
    targets = []
    for feature in geojson["features"]:
        state = feature["properties"]["dashboard_state"]
        if state not in states:
            continue
        geometry = feature["geometry"]
        polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
        for polygon in polygons:
            outer = polygon[0]
            min_lon, max_lon = min(point[0] for point in outer), max(point[0] for point in outer)
            min_lat, max_lat = min(point[1] for point in outer), max(point[1] for point in outer)
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


@st.cache_data(show_spinner=False)
def lga_click_targets(features, state, spacing=0.071):
    targets = []
    for feature in features:
        if feature["properties"]["dashboard_state"] != state:
            continue
        geometry = feature["geometry"]
        polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
        candidates = []
        for polygon in polygons:
            outer = polygon[0]
            min_lon, max_lon = min(point[0] for point in outer), max(point[0] for point in outer)
            min_lat, max_lat = min(point[1] for point in outer), max(point[1] for point in outer)
            lon = (int(min_lon / spacing) + 0.5) * spacing
            while lon < max_lon:
                lat = (int(min_lat / spacing) + 0.5) * spacing
                while lat < max_lat:
                    if _inside_ring(lon, lat, outer) and not any(
                        _inside_ring(lon, lat, hole) for hole in polygon[1:]
                    ):
                        candidates.append((lon, lat))
                    lat += spacing
                lon += spacing
        if not candidates:
            for polygon in polygons:
                outer = polygon[0]
                lon = sum(point[0] for point in outer[:-1]) / max(1, len(outer) - 1)
                lat = sum(point[1] for point in outer[:-1]) / max(1, len(outer) - 1)
                if _inside_ring(lon, lat, outer) and not any(
                    _inside_ring(lon, lat, hole) for hole in polygon[1:]
                ):
                    candidates.append((lon, lat))
        if candidates:
            center_lon = sum(point[0] for point in candidates) / len(candidates)
            center_lat = sum(point[1] for point in candidates) / len(candidates)
            lon, lat = min(
                candidates,
                key=lambda point: (point[0] - center_lon) ** 2 + (point[1] - center_lat) ** 2,
            )
            targets.append((feature["id"], lon, lat))
    return targets


def bucket(pct):
    if pct >= 75:
        return "75 - 100%"
    if pct >= 50:
        return "50 - 75%"
    if pct >= 25:
        return "25 - 50%"
    return "0 - 25%"


def format_name(name):
    return "FCT" if name == "fct" else name.title()


def format_value(value, column):
    if column == "share_pct":
        return f"{value:.2f}%"
    if column in {"pu_per_ward", "pu_per_lga", "ward_per_lga"}:
        return f"{value:.1f}"
    return f"{int(value):,}"


def legend():
    items = "".join(
        f'<span><i style="background:{COLORS[band]}"></i>{band}</span>'
        for band in ["75 - 100%", "50 - 75%", "25 - 50%", "0 - 25%"]
    )
    st.markdown(f'<div class="map-legend">{items}</div>', unsafe_allow_html=True)


def reset():
    ss.indicator = DEFAULT_IND
    ss.zone = "All zones"
    ss.zone_select = "All zones"
    ss.state = "All states"
    ss.state_select = "All states"
    ss.lga_choice = "All LGAs"
    ss.search = ""
    ss.map_version += 1


def on_state_change():
    ss.state = ss.state_select
    ss.lga_choice = "All LGAs"
    ss.map_version += 1


def on_zone_change():
    ss.zone = ss.zone_select
    ss.state = "All states"
    ss.state_select = "All states"
    ss.lga_choice = "All LGAs"
    ss.map_version += 1


def on_indicator_change():
    ss.map_version += 1


def back_to_nigeria():
    ss.state = "All states"
    ss.state_select = "All states"
    ss.zone_select = ss.zone
    ss.lga_choice = "All LGAs"
    ss.map_version += 1


ss = st.session_state
ss.setdefault("indicator", DEFAULT_IND)
ss.setdefault("zone", "All zones")
ss.setdefault("state", "All states")
ss.setdefault("zone_select", ss.zone)
ss.setdefault("state_select", ss.state)
ss.setdefault("lga_choice", "All LGAs")
ss.setdefault("search", "")
ss.setdefault("map_version", 0)

if not CSV_PATH.exists():
    st.error(f"CSV not found: {CSV_PATH}")
    st.stop()

df = load_data(str(CSV_PATH))
metrics = state_metrics(df)
all_states = tuple(sorted(metrics.state))
lga_pairs = tuple(sorted(set(zip(df.state, df.lg))))

pending_state = ss.pop("_pending_map_state", None)
if pending_state in all_states:
    ss.state = pending_state
    ss.state_select = pending_state
    ss.lga_choice = "All LGAs"
    ss.map_version += 1

if ss.state in all_states:
    state_data = df[df.state == ss.state]
    available_lgas = tuple(sorted(state_data.lg.unique()))
else:
    state_data = df.iloc[0:0]
    available_lgas = ()
pending_lga = ss.pop("_pending_lga", None)
if pending_lga in available_lgas:
    ss.lga_choice = pending_lga
    ss.map_version += 1
if ss.lga_choice not in ("All LGAs", *available_lgas):
    ss.lga_choice = "All LGAs"

selected_state = ss.state if ss.state in all_states else "All states"
st.title("Nigeria Polling Units")
st.caption("Explore polling units, wards and local governments across Nigeria.")

if selected_state != "All states":
    back_col, reset_col = st.columns(2)
    back_col.button("Back to Nigeria map", on_click=back_to_nigeria, width="stretch")
    reset_col.button("Reset filters", on_click=reset, width="stretch")
    st.subheader(format_name(selected_state))
else:
    st.button("Reset filters", on_click=reset, width="stretch")

st.selectbox(
    "Indicator",
    list(INDICATORS),
    key="indicator",
    on_change=on_indicator_change,
)
question, metric_column = INDICATORS[ss.indicator]

if selected_state == "All states":
    ss.zone_select = ss.zone
    ss.state_select = ss.state
    st.selectbox(
        "Zone",
        ["All zones", *ZONES],
        key="zone_select",
        on_change=on_zone_change,
    )
    zone = ss.zone
    zone_states = all_states if zone == "All zones" else tuple(
        state for state in all_states if STATE_ZONE.get(state) == ss.zone
    )
    state_options = ["All states", *zone_states]
    if ss.state not in state_options:
        ss.state = "All states"
        ss.state_select = "All states"
    st.selectbox(
        "State (or tap the map)",
        state_options,
        key="state_select",
        format_func=format_name,
        on_change=on_state_change,
    )

if selected_state == "All states":
    view = metrics if ss.zone == "All zones" else metrics[metrics.zone == ss.zone]
    chart_data = view[["state", metric_column]].copy()
    maximum = chart_data[metric_column].max() or 1
    chart_data["score"] = (chart_data[metric_column] / maximum * 100).round(1)
    chart_data["band"] = chart_data["score"].apply(bucket)

    st.metric("Polling units tracked", f"{int(view.polling_units.sum()):,}")
    st.markdown(question)
    legend()
    geojson = load_geojson(all_states)
    if geojson:
        values = chart_data.set_index("state")
        centers = centroids(geojson)
        visible_states = tuple(chart_data.state)
        figure = go.Figure()
        for feature in geojson["features"]:
            state = feature["properties"]["dashboard_state"]
            if state not in values.index:
                continue
            row = values.loc[state]
            geometry = feature["geometry"]
            polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
            for polygon in polygons:
                ring = polygon[0]
                figure.add_trace(go.Scatter(
                    x=[point[0] for point in ring],
                    y=[point[1] for point in ring],
                    mode="lines",
                    fill="toself",
                    fillcolor=COLORS[row["band"]],
                    line=dict(color=MAP_BORDER, width=0.8),
                    hoveron="fills",
                    hovertemplate=f"<b>{format_name(state)}</b><br>{ss.indicator}: "
                                  f"{format_value(row[metric_column], metric_column)}<extra></extra>",
                    showlegend=False,
                ))
        targets = map_click_targets(geojson, visible_states)
        figure.add_trace(go.Scatter(
            x=[lon for _, lon, _ in targets],
            y=[lat for _, _, lat in targets],
            customdata=[[state, values.loc[state, metric_column], values.loc[state, "score"]]
                        for state, _, _ in targets],
            mode="markers",
            marker=dict(size=18, color="rgba(0,0,0,0.01)"),
            hovertemplate="<b>%{customdata[0]}</b><br>" + ss.indicator +
                          ": %{customdata[1]:,}<br>Score: %{customdata[2]}%<extra></extra>",
            showlegend=False,
        ))
        labels = [state for state in visible_states if state in centers]
        figure.add_trace(go.Scatter(
            x=[centers[state][0] for state in labels],
            y=[centers[state][1] for state in labels],
            text=[format_name(state) for state in labels],
            customdata=[[state, values.loc[state, metric_column], values.loc[state, "score"]]
                        for state in labels],
            mode="markers+text",
            textposition="middle center",
            textfont=dict(size=9, color=MAP_TEXT),
            marker=dict(size=12, color="rgba(0,0,0,0.01)"),
            hovertemplate="<b>%{text}</b><br>" + ss.indicator +
                          ": %{customdata[1]:,}<br>Score: %{customdata[2]}%<extra></extra>",
            showlegend=False,
        ))
        figure.update_xaxes(range=[2, 15], visible=False, fixedrange=True, constrain="domain")
        figure.update_yaxes(range=[3.5, 14.2], visible=False, fixedrange=True,
                            scaleanchor="x", scaleratio=1, constrain="domain")
        figure.update_layout(
            height=440,
            margin=dict(l=0, r=0, t=4, b=4),
            dragmode=False,
            clickmode="event+select",
            showlegend=False,
            plot_bgcolor=MAP_BG,
            paper_bgcolor=MAP_BG,
            hoverlabel=dict(bgcolor="#1E293B", font_color=MAP_TEXT),
        )
        event = st.plotly_chart(
            figure,
            width="stretch",
            on_select="rerun",
            selection_mode="points",
            key=f"state_map_{ss.map_version}",
            config={"displayModeBar": False},
        )
        points = (event or {}).get("selection", {}).get("points", [])
        if points:
            custom = points[0].get("customdata")
            clicked_state = custom[0] if custom else None
            if clicked_state in all_states and clicked_state != ss.state:
                ss["_pending_map_state"] = clicked_state
                st.rerun()
    else:
        st.warning("State boundaries could not be loaded. Check the app's internet connection.")

    st.caption("Tap a state on the map or choose one above to see its local governments.")
    with st.expander("State ranking"):
        ranking = view[["state", metric_column]].sort_values(metric_column, ascending=False).copy()
        ranking["state"] = ranking.state.map(format_name)
        ranking = ranking.rename(columns={"state": "State", metric_column: ss.indicator})
        st.dataframe(ranking, hide_index=True, width="stretch", height=360)
else:
    state_metrics_row = metrics.loc[metrics.state == selected_state].iloc[0]
    pu_col, ward_col = st.columns(2)
    pu_col.metric("Polling units", f"{int(state_metrics_row.polling_units):,}")
    ward_col.metric("Wards", f"{int(state_metrics_row.wards):,}")
    lga_col, zone_col = st.columns(2)
    lga_col.metric("Local governments", f"{int(state_metrics_row.lgas):,}")
    zone_col.metric("Zone", STATE_ZONE.get(selected_state, "Unknown"))

    groups = state_data.groupby("lg", sort=False)
    lga_summary = pd.DataFrame({
        "polling_units": groups.size(),
        "wards": groups["ward_key"].nunique(),
        "senatorial": groups["senatorial"].nunique(),
        "constituencies": groups["house_of_rep"].nunique(),
    })
    ward_sizes = state_data.groupby(["lg", "ward_key"]).size()
    lga_summary["max_ward_pu"] = ward_sizes.groupby(level=0).max()
    lga_summary["pu_per_ward"] = (lga_summary.polling_units / lga_summary.wards).round(1)
    lga_summary["pu_per_lga"] = lga_summary.polling_units
    lga_summary["ward_per_lga"] = lga_summary.wards
    lga_summary["share_pct"] = (
        lga_summary.polling_units / max(len(state_data), 1) * 100
    ).round(2)
    lga_summary["lgas"] = 1
    lga_summary["map_key"] = [f"{selected_state}|{lga}" for lga in lga_summary.index]
    lga_summary["score"] = (
        lga_summary[metric_column] / (lga_summary[metric_column].max() or 1) * 100
    ).round(1)
    lga_summary["band"] = lga_summary.score.apply(bucket)
    lga_lookup = lga_summary.set_index("map_key")

    st.markdown(f"#### {ss.indicator} by local government")
    legend()
    lga_geojson, unmatched = load_lga_geojson(all_states, lga_pairs)
    if lga_geojson:
        available_features = [
            feature for feature in lga_geojson["features"]
            if feature["properties"]["dashboard_state"] == selected_state
        ]
        figure = go.Figure()
        map_features = []
        min_lon, min_lat, max_lon, max_lat = 180, 90, -180, -90
        for feature in available_features:
            properties = feature["properties"]
            map_key = feature["id"]
            if map_key not in lga_lookup.index:
                continue
            row = lga_lookup.loc[map_key]
            geometry = feature["geometry"]
            polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
            for polygon in polygons:
                outer = polygon[0]
                min_lon = min(min_lon, min(point[0] for point in outer))
                max_lon = max(max_lon, max(point[0] for point in outer))
                min_lat = min(min_lat, min(point[1] for point in outer))
                max_lat = max(max_lat, max(point[1] for point in outer))
                figure.add_trace(go.Scatter(
                    x=[point[0] for point in outer],
                    y=[point[1] for point in outer],
                    mode="lines",
                    fill="toself",
                    fillcolor=COLORS[row["band"]],
                    line=dict(color=MAP_HIGHLIGHT if ss.lga_choice == properties["dashboard_lga"]
                              else MAP_BORDER,
                              width=2 if ss.lga_choice == properties["dashboard_lga"] else 0.8),
                    customdata=[[properties["dashboard_lga"], row[metric_column], row["score"]]
                                for _ in outer],
                    hoveron="fills",
                    hovertemplate="<b>%{customdata[0]}</b><br>" + ss.indicator +
                                  ": %{customdata[1]:,}<br>Score: %{customdata[2]}%<extra></extra>",
                    showlegend=False,
                ))
            map_features.append(feature)

        targets = lga_click_targets(map_features, selected_state)
        figure.add_trace(go.Scatter(
            x=[lon for _, lon, _ in targets],
            y=[lat for _, _, lat in targets],
            customdata=[[map_key, lga_lookup.loc[map_key, metric_column],
                         map_key.split("|", 1)[1].title()]
                        for map_key, _, _ in targets],
            mode="markers",
            marker=dict(size=16, color=MAP_TEXT, line=dict(color=MAP_BG, width=1)),
            hovertemplate="<b>%{customdata[2]}</b><br>" + ss.indicator +
                          ": %{customdata[1]:,}<extra></extra>",
            showlegend=False,
        ))
        if min_lon < max_lon and min_lat < max_lat:
            pad = max(max_lon - min_lon, max_lat - min_lat) * 0.04
            figure.update_xaxes(
                range=[min_lon - pad, max_lon + pad], visible=False, fixedrange=True, constrain="domain"
            )
            figure.update_yaxes(
                range=[min_lat - pad, max_lat + pad], visible=False, fixedrange=True,
                scaleanchor="x", scaleratio=1, constrain="domain"
            )
        figure.update_layout(
            height=420,
            margin=dict(l=0, r=0, t=4, b=4),
            dragmode=False,
            clickmode="event+select",
            showlegend=False,
            plot_bgcolor=MAP_BG,
            paper_bgcolor=MAP_BG,
            hoverlabel=dict(bgcolor="#1E293B", font_color=MAP_TEXT),
        )
        event = st.plotly_chart(
            figure,
            width="stretch",
            on_select="rerun",
            selection_mode="points",
            key=f"lga_map_{selected_state}_{ss.map_version}",
            config={"displayModeBar": False},
        )
        points = (event or {}).get("selection", {}).get("points", [])
        if points:
            custom = points[0].get("customdata")
            map_key = custom[0] if custom else None
            if map_key and "|" in map_key:
                clicked_lga = map_key.split("|", 1)[1]
                if clicked_lga in available_lgas and clicked_lga != ss.lga_choice:
                    ss["_pending_lga"] = clicked_lga
                    st.rerun()
        if unmatched:
            st.warning(f"{len(unmatched)} local government boundary could not be matched to the dataset.")
        st.caption("Tap a local-government marker or choose one below.")
    else:
        st.warning("Local government boundaries could not be loaded. The local government list is still available.")

    st.selectbox(
        "Choose a local government (or tap the map)",
        ["All LGAs", *available_lgas],
        key="lga_choice",
        format_func=lambda name: (
            "All local governments" if name == "All LGAs"
            else f"{name.title()} · {int(lga_summary.loc[name, 'polling_units']):,} PUs"
        ),
    )
    if ss.lga_choice != "All LGAs":
        selected_lga = lga_summary.loc[ss.lga_choice]
        st.markdown(f"### {ss.lga_choice.title()}")
        pu_col, ward_col = st.columns(2)
        pu_col.metric("Polling units", f"{int(selected_lga.polling_units):,}")
        ward_col.metric("Wards", f"{int(selected_lga.wards):,}")
        st.metric(ss.indicator, format_value(selected_lga[metric_column], metric_column))
        ward_table = (
            state_data[state_data.lg == ss.lga_choice]
            .groupby("ward").size().reset_index(name="Polling units")
            .sort_values("Polling units", ascending=False)
            .rename(columns={"ward": "Ward"})
        )
        with st.expander("Wards in this local government"):
            st.dataframe(ward_table, hide_index=True, width="stretch", height=360)

    table_columns = ["polling_units", "wards"]
    table_labels = ["Polling units", "Wards"]
    if metric_column not in table_columns:
        table_columns.append(metric_column)
        table_labels.append(ss.indicator)
    lga_table = lga_summary.reset_index().rename(columns={"lg": "Local government"})
    lga_table["Local government"] = lga_table["Local government"].str.title()
    lga_table = lga_table[["Local government", *table_columns]].sort_values(
        "polling_units", ascending=False
    )
    lga_table.columns = ["Local government", *table_labels]
    with st.expander("All local government details"):
        st.dataframe(lga_table, hide_index=True, width="stretch", height=420)

if selected_state == "All states":
    search_data = df if ss.zone == "All zones" else df[df.zone == ss.zone]
else:
    search_data = state_data
if ss.lga_choice != "All LGAs" and selected_state != "All states":
    search_data = search_data[search_data.lg == ss.lga_choice]

with st.expander("Find a polling unit or download data"):
    term = st.text_input("Search by polling-unit location or code", key="search")
    if term:
        matches = search_data[
            search_data.location.str.contains(term.lower(), regex=False)
            | search_data.code.str.contains(term.lower(), regex=False)
        ]
        st.caption(f"{len(matches):,} match(es); showing up to 100.")
        st.dataframe(
            matches[["code", "state", "lg", "ward", "location"]].head(100),
            hide_index=True,
            width="stretch",
            height=320,
        )
    scope = format_name(selected_state) if selected_state != "All states" else (
        ss.zone if ss.zone != "All zones" else "Nigeria"
    )
    st.download_button(
        "Download current data as CSV",
        search_data.drop(columns=["lga_key", "ward_key"]).to_csv(index=False).encode(),
        f"polling_units_{_key(scope).replace(' ', '_')}.csv",
        "text/csv",
        width="stretch",
    )
