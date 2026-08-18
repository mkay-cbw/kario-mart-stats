import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from streamlit_cookies_controller import CookieController
import pandas as pd
import streamlit as st
import psycopg2
import uuid
import warnings
warnings.filterwarnings('ignore', message='.*pandas only supports SQLAlchemy.*')


# ==========================================
# 1. CONNECTION & COOKIES
# ==========================================
@st.cache_resource
def init_connection():
    return psycopg2.connect(**st.secrets["postgres"])
conn = init_connection()
cursor = conn.cursor()
cookie_manager = CookieController()


# ==========================================
# 2. SESSION STATES
# ==========================================

# Authentication
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "master" not in st.session_state:
    st.session_state.master = False
if "username" not in st.session_state:
    st.session_state["username"] = None

# Tournament parameters
if "active_players" not in st.session_state:
    st.session_state.active_players = []
if "event" not in st.session_state:
    st.session_state.event = None
if "total_races" not in st.session_state:
    st.session_state.total_races = 4
if "selection_mode" not in st.session_state:
    st.session_state.selection_mode = "Zufällig"
if "game_mode" not in st.session_state:
    st.session_state.game_mode = "Kario"

# Tournament flow & UI control
if "tournament_active" not in st.session_state:
    st.session_state.tournament_active = False
if "current_round" not in st.session_state:
    st.session_state.current_round = 1
if "backup_races" not in st.session_state:
    st.session_state.backup_races = {}
if "final_check_failed" not in st.session_state:
    st.session_state.final_check_failed = False
if "waiting_for_placement" not in st.session_state:
    st.session_state.waiting_for_placement = False

# Security prompts
if "confirm_delete_player" not in st.session_state:
    st.session_state.confirm_delete_player = None
if "confirm_delete_event" not in st.session_state:
    st.session_state.confirm_delete_event = None
if "confirm_delete_tournament" not in st.session_state:
    st.session_state.confirm_delete_tournament = None


# ==========================================
# 3. HELPER FUNCTIONS
# ==========================================
def prevent_accidental_reload():
    st.iframe(
        """
        <script>
            const main_window = window.parent.document.defaultView;
            main_window.addEventListener('beforeunload', function (event) {
                event.preventDefault();
                event.returnValue = ''; 
                return '';
            });
        </script>
        """,
        height=1,
        width="stretch",
    )

def has_duplicates(lst):
    """Checks for duplicates in a list."""
    return len(lst) != len(set(lst))

def placement_selection(name, prefix_key, default_val=None, custom_title=None, disabled=False):
    """Generates two 1x6 Segmented Controls and validates the input."""
    title = custom_title if custom_title else f"**{name}:**"
    st.write(title)

    val1 = default_val if default_val in [1, 2, 3, 4, 5, 6] else None
    val2 = default_val if default_val in [7, 8, 9, 10, 11, 12] else None

    if disabled:
        disable_segmented_control(f"seg1_{prefix_key}_{name}")
        disable_segmented_control(f"seg2_{prefix_key}_{name}")

    place1 = st.segmented_control("Platz 1-6", options=[1, 2, 3, 4, 5, 6], default=val1, key=f"seg1_{prefix_key}_{name}", label_visibility="collapsed")
    place2 = st.segmented_control("Platz 7-12", options=[7, 8, 9, 10, 11, 12], default=val2, key=f"seg2_{prefix_key}_{name}", label_visibility="collapsed")

    if (place1 is not None) and (place2 is not None):
        return "two_positions"
    if (place1 is None) and (place2 is None):
        return "missing"

    return place1 if place1 is not None else place2


# ==========================================
# 4. HTML INJECTIONS
# ==========================================
def header(text, font_size=st.secrets["custom_theme"]["header_font_size"], font_weight=st.secrets["custom_theme"]["bold_font_weight"], font_color=st.secrets["custom_theme"]["font_color"], border=st.secrets["custom_theme"]["border"], highlight_color=st.secrets["custom_theme"]["highlight_color"], padding_left=st.secrets["custom_theme"]["padding_left"], padding_bottom=st.secrets["custom_theme"]["padding_bottom"]):
    st.html(
        f"""
            <p style="
                font-size: {font_size}; 
                font-weight: {font_weight}; 
                line-height: 1.5; 
                color: {font_color}; 
                border-left: {border} solid {highlight_color}; 
                padding-left: {padding_left}; margin: 10px 0;
                margin-bottom: {padding_bottom};
            ">
                {text}
            </p>
        """,
        unsafe_allow_javascript=True
    )

def semibold(text, font_size=st.secrets["custom_theme"]["base_font_size"], font_weight=st.secrets["custom_theme"]["semibold_font_weight"], font_color=st.secrets["custom_theme"]["font_color"], padding_bottom=st.secrets["custom_theme"]["padding_bottom"]):
    st.html(
        f"""
            <p style="
                font-size: {font_size}; 
                font-weight: {font_weight}; 
                color: {font_color}; 
                margin-bottom: {padding_bottom};
            ">
                {text}
            </p>
        """,
        unsafe_allow_javascript=True
    )

def centered_success(text):
    st.html("""<div id="center-success-marker"></div>""", unsafe_allow_javascript=True)
    st.success(text)

def style_tabs(padding_top=st.secrets["custom_theme"]["padding_top"], font_size=st.secrets["custom_theme"]["header_font_size"], font_weight=st.secrets["custom_theme"]["bold_font_weight"]):
    st.html(
        f"""
            <style>
                div[data-testid="stMainBlockContainer"], .block-container {{
                    padding-top: {padding_top}
                }}
                /* Force parent flex wrapper to span the full width */
                div[data-testid="stTabs"] > div[data-orientation="horizontal"] {{
                    width: 100% !important;
                }}

                /* Force tablist to span the full width of wrapper */
                div[data-testid="stTabs"] div[role="tablist"] {{
                    width: 100% !important;
                }}

                /* Force tabs to grow equally */
                div[data-testid="stTabs"] div[role="tab"] {{
                    flex: 1 1 0% !important;
                    justify-content: center !important;
                }}

                /* Increase font/icon size */
                div[data-testid="stTabs"] div[role="tab"] p {{
                    font-size: {font_size} !important;
                    font-weight: {font_weight} !important; 
                }}
            </style>
        """,
        unsafe_allow_javascript=True
    )

def style_metrics(label_font_size=st.secrets["custom_theme"]["base_font_size"], label_font_weight=st.secrets["custom_theme"]["semibold_font_weight"], metrics_font_size=st.secrets["custom_theme"]["metrics_font_size"], metrics_font_weight=st.secrets["custom_theme"]["metrics_font_weight"]):
    st.html(
        f"""
            <style>
                /* Label */
                [data-testid="stMetricLabel"] p {{
                    font-size: {label_font_size} !important;
                    font-weight: {label_font_weight} !important;
                    white-space: pre-line !important;
                    word-break: break-word !important;
                }}
                /* Metric value */
                [data-testid="stMetricValue"] {{
                    font-size: {metrics_font_size} !important;
                    font-weight: {metrics_font_weight} !important;
                }}
            </style>
        """, unsafe_allow_javascript=True)

def style_centered_success():
    st.html(
        """
            <style>
                div[data-testid="stElementContainer"]:has(#center-success-marker) + div[data-testid="stElementContainer"] div[data-testid="stAlert"] > div {
                    display: flex;
                    justify-content: center;
                    align-items: center;
                }
            </style>
        """
    )

def style_expander(font_size=st.secrets["custom_theme"]["base_font_size"]):
    st.html(
        f"""
            <style>
                div[data-testid="stExpander"] summary p {{
                    font-size: {font_size} !important;
                }}
            </style>
        """, unsafe_allow_javascript=True)

def disable_segmented_control(key):
    st.html(
        f"""
            <style>
                .st-key-{key} button[data-variant="segmented_control"] {{
                    pointer-events: none !important;
                }}
            </style>
        """,
        unsafe_allow_javascript=True
    )

def disable_selectbox(key):
    st.html(
        f"""
            <style>
                .st-key-{key} div[data-testid="stSelectbox"] {{
                    pointer-events: none !important;
                }}
            </style>
        """,
        unsafe_allow_javascript=True
    )


# ==========================================
# 5. CACHED SQL FUNCTIONS
# ==========================================
@st.cache_data
def get_is_master(session_id):
    df = pd.read_sql_query(
        """
            SELECT master 
            FROM active_sessions 
            WHERE session_id = %s AND expires_at > CURRENT_TIMESTAMP;
        """, conn, params=[session_id])
    return df["master"][0] if not df.empty else None

@st.cache_data
def get_points_mapping():
    df = pd.read_sql_query("SELECT * FROM points_mapping;", conn)
    return dict(zip(df["placement"], df["points"]))

@st.cache_data
def get_df_players():
    return pd.read_sql_query("SELECT * FROM players ORDER BY name ASC;", conn)

@st.cache_data
def get_df_tracks():
    return pd.read_sql_query("SELECT * FROM tracks ORDER BY name ASC;", conn)

@st.cache_data
def get_df_events():
    return pd.read_sql_query("SELECT * FROM events ORDER BY name ASC;", conn)

@st.cache_data
def get_df_h2h_track(track_name, players):
    placeholders = ",".join(["%s"] * len(players))
    query = f"""
        SELECT 
            rr.player_name as "Spieler", 
            ROUND(AVG(rr.placement), 2) as "Ø-Platz",
            COUNT(rr.race_id) as "race_count"
        FROM race_results rr 
        JOIN races r ON rr.race_id = r.id 
        WHERE r.track_name = %s 
        AND r.id IN (
            SELECT race_id FROM race_results 
            WHERE player_name IN ({placeholders}) 
            GROUP BY race_id 
            HAVING COUNT(DISTINCT player_name) = %s
        ) 
        AND rr.player_name IN ({placeholders}) 
        GROUP BY rr.player_name 
        ORDER BY AVG(rr.placement) ASC;
    """
    params = [track_name] + list(players) + [len(players)] + list(players)
    df = pd.read_sql_query(query, conn, params=params)

    shared_races = 0
    if not df.empty:
        shared_races = int(df["race_count"].iloc[0])
        df = df.drop(columns=["race_count"])

    return df, shared_races

@st.cache_data
def get_df_avg_track(track_name, players):
    placeholders = ",".join(["%s"] * len(players))
    query = f"""
        SELECT 
            rr.player_name as "Spieler", 
            ROUND(AVG(rr.placement), 2) as "Ø-Platz",
            COUNT(rr.id) as "Gefahren" 
        FROM race_results rr 
        JOIN races r ON rr.race_id = r.id 
        WHERE r.track_name = %s 
        AND rr.player_name IN ({placeholders}) 
        GROUP BY rr.player_name 
        ORDER BY AVG(rr.placement) ASC;
    """
    params = [track_name] + list(players)
    return pd.read_sql_query(query, conn, params=params)

@st.cache_data
def get_player_stats(profile_name, event_filter, mode_filter, track_filter):

    # Filter conditions
    event_cond = " AND tr.event_name = %s" if event_filter != "Alle Events" else ""
    event_cond_2 = " AND tr2.event_name = %s" if event_filter != "Alle Events" else ""
    track_cond = " AND r.track_name = %s" if track_filter != "Alle Strecken" else ""
    mode_cond = " AND tr.kario = 1" if mode_filter == "Kario" else (" AND tr.kario = 0" if mode_filter == "Mario" else "")
    mode_cond_2 = " AND tr2.kario = 1" if mode_filter == "Kario" else (" AND tr2.kario = 0" if mode_filter == "Mario" else "")

    query_races = f"""
        SELECT 
            COUNT(rr.id) as total_races,
            SUM(pm.points) as total_points,
            AVG(pm.points) as avg_race_points,
            AVG(rr.placement) as avg_race_placement,
            SUM(CASE WHEN rr.placement = 1 THEN 1 ELSE 0 END) as race_wins,
            AVG(CASE WHEN r.picked_by_name = rr.player_name THEN rr.placement ELSE NULL END) as avg_race_placement_picked
        FROM race_results rr 
        JOIN points_mapping pm ON rr.placement = pm.placement 
        JOIN races r ON rr.race_id = r.id 
        JOIN tournament_results tr ON r.tournament_id = tr.tournament_id AND rr.player_name = tr.player_name 
        WHERE rr.player_name = %s 
        {event_cond}
        {track_cond}
        {mode_cond};
    """
    params_races = [profile_name]
    if event_filter != "Alle Events":
        params_races += [event_filter]
    if track_filter != "Alle Strecken":
        params_races += [track_filter]
    df_races = pd.read_sql_query(query_races, conn, params=params_races).iloc[0]

    query_normalized = f"""
        WITH tournament_stats AS (
            SELECT 
                r.tournament_id,
                SUM(pm.points) AS t_points,
                COUNT(rr.id) AS t_races
            FROM race_results rr 
            JOIN points_mapping pm ON rr.placement = pm.placement 
            JOIN races r ON rr.race_id = r.id 
            JOIN tournament_results tr ON r.tournament_id = tr.tournament_id AND rr.player_name = tr.player_name 
            WHERE rr.player_name = %s 
            {event_cond}
            {track_cond}
            {mode_cond}
            GROUP BY r.tournament_id
        )
        SELECT AVG((t_points::NUMERIC / t_races) * 4) AS avg_normalized_points
        FROM tournament_stats;
    """
    params_normalized = [profile_name]
    if event_filter != "Alle Events":
        params_normalized += [event_filter]
    if track_filter != "Alle Strecken":
        params_normalized += [track_filter]
    df_normalized = pd.read_sql_query(query_normalized, conn, params=params_normalized)
    avg_normalized_points = df_normalized["avg_normalized_points"].iloc[0]

    query_tournaments = f"""
        SELECT 
            COUNT(DISTINCT tr.tournament_id) as total_tournaments,
            AVG(tr.final_placement) as avg_tournament_placement,
            SUM(CASE WHEN tr.final_placement = 1 THEN 1 ELSE 0 END) as tournament_wins,
            AVG(tr.beer_finished_after) as avg_beer_finished_after
        FROM tournament_results tr 
        WHERE tr.player_name = %s 
        {event_cond}
        {mode_cond};
    """
    params_tournaments = [profile_name]
    if event_filter != "Alle Events":
        params_tournaments += [event_filter]
    df_tournaments = pd.read_sql_query(query_tournaments, conn, params=params_tournaments).iloc[0]

    query_best = f"""
        SELECT 
            r.track_name as "Strecke", 
            COUNT(rr.id) as "Gefahren", 
            ROUND(AVG(rr.placement), 2) as "Ø-Platz" 
        FROM race_results rr 
        JOIN races r ON rr.race_id = r.id 
        JOIN tournament_results tr ON r.tournament_id = tr.tournament_id AND rr.player_name = tr.player_name 
        WHERE rr.player_name = %s 
        {event_cond}
        {mode_cond} 
        GROUP BY r.track_name 
        ORDER BY AVG(rr.placement) ASC LIMIT {st.secrets["custom_theme"]["ranking_limit"]};
    """
    params_best = [profile_name]
    if event_filter != "Alle Events":
        params_best += [event_filter]
    df_best = pd.read_sql_query(query_best, conn, params=params_best)

    query_favorites = f"""
        SELECT 
            r.track_name as "Strecke", 
            COUNT(r.id) as "Gewählt", 
            ROUND((
                SELECT AVG(rr2.placement) 
                FROM race_results rr2 
                JOIN races r2 ON rr2.race_id = r2.id 
                JOIN tournament_results tr2 ON r2.tournament_id = tr2.tournament_id AND rr2.player_name = tr2.player_name 
                WHERE r2.track_name = r.track_name 
                AND rr2.player_name = %s 
                {event_cond_2}
                {mode_cond_2}
            ), 2) as "Ø-Platz" 
        FROM races r 
        JOIN tournament_results tr ON r.tournament_id = tr.tournament_id AND tr.player_name = r.picked_by_name 
        WHERE r.picked_by_name = %s 
        {event_cond}
        {mode_cond} 
        GROUP BY r.track_name 
        ORDER BY COUNT(r.id) DESC, r.track_name ASC LIMIT {st.secrets["custom_theme"]["ranking_limit"]};
    """
    params_fav = [profile_name, profile_name]
    if event_filter != "Alle Events":
        params_fav = [profile_name, event_filter, profile_name, event_filter]
    df_fav = pd.read_sql_query(query_favorites, conn, params=params_fav)

    return df_races, avg_normalized_points, df_tournaments, df_best, df_fav

@st.cache_data
def get_track_stats(selected_track):
    query_play_count = f"""
        SELECT COUNT(*) as count 
        FROM races 
        WHERE track_name = %s;
    """
    play_count = pd.read_sql_query(query_play_count, conn, params=[selected_track])['count'].values[0]

    query_most_picked = f"""
        SELECT 
            picked_by_name as "Spieler", 
            COUNT(*) as "Gewählt" 
        FROM races 
        WHERE track_name = %s 
        AND picked_by_name IS NOT NULL 
        GROUP BY "Spieler" 
        ORDER BY "Gewählt" DESC LIMIT {st.secrets["custom_theme"]["ranking_limit"]};
    """
    df_most_picked = pd.read_sql_query(query_most_picked, conn, params=[selected_track])

    query_placement = f"""
        SELECT 
            player_name as "Spieler", 
            AVG(rr.placement) as "Ø-Platz" 
        FROM race_results rr 
        JOIN races r ON rr.race_id = r.id 
        WHERE r.track_name = %s 
        GROUP BY player_name 
        ORDER BY "Ø-Platz" ASC;
    """
    df_placement = pd.read_sql_query(query_placement, conn, params=[selected_track])

    query_points = f"""
        SELECT 
            player_name as "Spieler", 
            AVG(pm.points) as "Ø-Punkte" 
        FROM race_results rr 
        JOIN races r ON rr.race_id = r.id 
        JOIN points_mapping pm ON rr.placement = pm.placement 
        WHERE r.track_name = %s 
        GROUP BY player_name 
        ORDER BY "Ø-Punkte" DESC;
    """
    df_points = pd.read_sql_query(query_points, conn, params=[selected_track])

    query_wins = f"""
        SELECT 
            player_name as "Spieler", 
            COUNT(*) as "Rennsiege"
        FROM race_results rr 
        JOIN races r ON rr.race_id = r.id 
        WHERE r.track_name = %s 
        AND rr.placement = 1 
        GROUP BY player_name 
        ORDER BY "Rennsiege" DESC;
    """
    df_wins = pd.read_sql_query(query_wins, conn, params=[selected_track])

    return play_count, df_most_picked, df_placement, df_points, df_wins

@st.cache_data
def get_h2h_data(players, event_filter, track_filter, mode_filter):

    # Filter conditions
    placeholders = ",".join(["%s"] * len(players))
    event_cond = " AND tr.event_name = %s" if event_filter != "Alle Events" else ""
    track_cond = " AND r.track_name = %s" if track_filter != "Alle Strecken" else ""
    mode_cond = " AND tr.kario = 1" if mode_filter == "Kario" else (" AND tr.kario = 0" if mode_filter == "Mario" else "")
    subquery_shared = f"""
        SELECT r.tournament_id 
        FROM race_results rr 
        JOIN races r ON rr.race_id = r.id 
        WHERE rr.player_name IN ({placeholders}) 
        GROUP BY r.tournament_id 
        HAVING COUNT(DISTINCT rr.player_name) = %s
    """

    query_h2h_r = f"""
        SELECT 
            rr.player_name as player, 
            pm.points, 
            rr.placement, 
            r.tournament_id, 
            CASE WHEN rr.placement = 1 THEN 1 ELSE 0 END as race_win 
        FROM race_results rr 
        JOIN races r ON rr.race_id = r.id 
        JOIN tournament_results tr ON r.tournament_id = tr.tournament_id AND rr.player_name = tr.player_name 
        JOIN points_mapping pm ON rr.placement = pm.placement 
        WHERE r.tournament_id IN ({subquery_shared}) 
        AND rr.player_name IN ({placeholders})
        {event_cond} 
        {track_cond} 
        {mode_cond};
    """
    params_r = list(players) + [len(players)] + list(players)
    if event_filter != "Alle Events":
        params_r.append(event_filter)
    if track_filter != "Alle Strecken":
        params_r.append(track_filter)
    df_r = pd.read_sql_query(query_h2h_r, conn, params=params_r)

    query_h2h_t = f"""
        SELECT 
            tr.player_name as player, 
            tr.final_placement, 
            (
                SELECT (SUM(pm2.points)::NUMERIC / COUNT(rr2.id)) * 4 
                FROM race_results rr2 
                JOIN points_mapping pm2 ON rr2.placement = pm2.placement 
                JOIN races r2 ON rr2.race_id = r2.id 
                WHERE r2.tournament_id = tr.tournament_id 
                AND rr2.player_name = tr.player_name
            ) as tournament_points, 
            CASE WHEN tr.final_placement = 1 THEN 1 ELSE 0 END as tournament_win 
        FROM tournament_results tr 
        WHERE tr.tournament_id IN ({subquery_shared}) 
        AND tr.player_name IN ({placeholders}) 
        {event_cond} 
        {mode_cond};
    """
    params_t = list(players) + [len(players)] + list(players)
    if event_filter != "Alle Events":
        params_t.append(event_filter)
    df_t = pd.read_sql_query(query_h2h_t, conn, params=params_t)

    return df_r, df_t

@st.cache_data
def get_tournament_edit_data(tournament_id):
    df_event = pd.read_sql_query(f"""
        SELECT event_name 
        FROM tournament_results 
        WHERE tournament_id = %s 
        LIMIT 1;
    """, conn, params=[tournament_id])
    event_name = df_event["event_name"].iloc[0]

    df_placements = pd.read_sql_query("""
        SELECT 
            player_name, 
            final_placement 
        FROM tournament_results 
        WHERE tournament_id = %s
        ORDER BY final_placement ASC;
    """, conn, params=[tournament_id])

    df_points = pd.read_sql_query("""
        SELECT 
            rr.player_name, 
            SUM(pm.points) as total_points 
        FROM race_results rr 
        JOIN races r ON rr.race_id = r.id 
        JOIN points_mapping pm ON rr.placement = pm.placement 
        WHERE r.tournament_id = %s 
        GROUP BY rr.player_name
        ORDER BY total_points DESC;
    """, conn, params=[tournament_id])

    df_beer = pd.read_sql_query("""
        SELECT 
            player_name, 
            final_placement,
            beer_finished_after, 
            kario 
        FROM tournament_results 
        WHERE tournament_id = %s
        ORDER BY final_placement ASC;
    """, conn, params=[tournament_id])

    df_race_count = pd.read_sql_query("""
        SELECT COUNT(*) as c 
        FROM races 
        WHERE tournament_id = %s;
    """, conn, params=[tournament_id])
    num_races = int(df_race_count['c'].iloc[0]) if not df_race_count.empty else 1

    df_race_list = pd.read_sql_query("""
        SELECT 
            id as race_id, 
            track_name 
        FROM races 
        WHERE tournament_id = %s;
    """, conn, params=[tournament_id])

    return event_name, df_placements, df_points, df_beer, num_races, df_race_list

@st.cache_data
def get_race_edit_data(race_id):
    df_race_info = pd.read_sql_query("""
        SELECT 
            track_name, 
            picked_by_name 
        FROM races 
        WHERE id = %s;
    """, conn, params=[race_id])
    track_name = df_race_info['track_name'].iloc[0] if not df_race_info.empty else None
    picked_by = df_race_info['picked_by_name'].iloc[0] if not df_race_info.empty else None

    df_placements = pd.read_sql_query("""
        SELECT 
            player_name, 
            placement 
        FROM race_results 
        WHERE race_id = %s
        ORDER BY placement ASC;
    """, conn, params=[race_id])

    return track_name, picked_by, df_placements

@st.cache_data
def get_history_list():
    query = f"""
        SELECT 
            t.id as "Turnier-ID", 
            t.date as "Datum", 
            STRING_AGG(tr.player_name, ', ' ORDER BY tr.final_placement ASC) as "Teilnehmer",
            CASE WHEN tr.kario = 1 THEN 'Kario' ELSE 'Mario' END as "Modus",
            tr.event_name as "Event"
        FROM tournaments t 
        JOIN tournament_results tr ON t.id = tr.tournament_id 
        GROUP BY t.id, t.date, tr.kario, tr.event_name
        ORDER BY t.id DESC;
    """
    df =  pd.read_sql_query(query, conn)

    if not df.empty:
        df.insert(0, "Turnier-Nr.", range(len(df), 0, -1))
        df = df.sort_values(by="Turnier-ID", ascending=False).reset_index(drop=True)

    return df


# ==========================================
# 6. AUTHENTICATION CHECK
# ==========================================
if not st.session_state["authenticated"]:
    saved_session_id = cookie_manager.get("session_id")

    if saved_session_id:
        cur = conn.cursor()
        is_master = get_is_master(saved_session_id)
        if is_master is not None:
            st.session_state["authenticated"] = True
            st.session_state["master"] = True if is_master == 1 else False
            new_expires_at = datetime.now() + timedelta(days=st.secrets["cookies"]["expires_after_days"])
            cur.execute("""
                UPDATE active_sessions 
                SET expires_at = %s 
                WHERE session_id = %s;
            """, [new_expires_at, saved_session_id])
            conn.commit()
            get_is_master.clear()
            cookie_manager.set("session_id", saved_session_id, max_age=st.secrets["cookies"]["expires_after_days"]*24*60*60)
            time.sleep(0.3)
        else:
            cur.execute("DELETE FROM active_sessions WHERE session_id = %s;", [saved_session_id])
            conn.commit()
            get_is_master.clear()
            cookie_manager.remove("session_id")
            time.sleep(0.3)


# ==========================================
# 7. PAGE CONFIG
# ==========================================

# HTML injections
style_tabs()
style_metrics()
style_centered_success()
style_expander()

# Sidebar
with st.sidebar:
    st.subheader("🔒 Anmeldung")
    if not st.session_state.authenticated:

        # Login
        st.write("**Passwort:**")
        password = st.text_input("Passwort", type="password", label_visibility="collapsed")
        if st.button("**Anmelden**", type="secondary", width="stretch"):
            if password == st.secrets["passwords"]["master_pw"]:
                st.session_state.authenticated = True
                st.session_state.master = True
                new_session_id = str(uuid.uuid4())
                expires_at = datetime.now() + timedelta(days=st.secrets["cookies"]["expires_after_days"])
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO active_sessions (session_id, master, expires_at)
                    VALUES (%s, 1, %s);
                """, [new_session_id, expires_at])
                conn.commit()
                get_is_master.clear()
                cookie_manager.set("session_id", new_session_id, max_age=st.secrets["cookies"]["expires_after_days"]*24*60*60)
                time.sleep(0.3)
                st.rerun()
            elif password == st.secrets["passwords"]["user_pw"]:
                st.session_state.authenticated = True
                new_session_id = str(uuid.uuid4())
                expires_at = datetime.now() + timedelta(days=st.secrets["cookies"]["expires_after_days"])
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO active_sessions (session_id, master, expires_at)
                    VALUES (%s, 0, %s);
                """, [new_session_id, expires_at])
                conn.commit()
                get_is_master.clear()
                cookie_manager.set("session_id", new_session_id, max_age=st.secrets["cookies"]["expires_after_days"]*24*60*60)
                time.sleep(0.3)
                st.rerun()
            else:
                st.error("❌ Falsches Passwort!")
    else:

        # Login successful
        if st.session_state.master:
            centered_success("🔒 Angemeldet als Admin")
        else:
            centered_success("🔒 Angemeldet")
        if st.button("**Abmelden**", type="secondary", width="stretch"):
            st.session_state.authenticated = False
            st.session_state.master = False
            current_session_id = cookie_manager.get("session_id")
            if current_session_id:
                cur = conn.cursor()
                cur.execute("DELETE FROM active_sessions WHERE session_id = %s;", [current_session_id])
                conn.commit()
            cookie_manager.remove("session_id")
            time.sleep(0.3)
            st.rerun()

# Prevent accidental reload
if st.session_state.tournament_active or st.session_state.waiting_for_placement:
    prevent_accidental_reload()

st.set_page_config(page_title="Kario Mart Dashboard", page_icon="🏎️", layout="centered")
tab1, tab2, tab3, tab4, tab5 = st.tabs(["🎮", "👤", "🏁", "⚔️", "📋"], width="stretch")

df_players = get_df_players()
df_tracks = get_df_tracks()
df_events = get_df_events()

# ==========================================
# TAB 1: TOURNAMENT TRACKING
# ==========================================
with tab1:
    if not st.session_state.authenticated:
        st.warning("🔒 Melde dich in der Sidebar an, um Turniere zu erfassen.")
    else:

        # Tournament setup
        if not st.session_state.tournament_active and not st.session_state.waiting_for_placement:
            header("Setup")

            st.write("**Spieler:**")
            selected_names = st.multiselect("Spieler", df_players["name"].tolist(), key="players_tab1", default=["Pfeiffer", "Markus"] if len(df_players) >= 2 else [], label_visibility="collapsed")

            st.write("**Event:**")
            selected_event = st.selectbox("Event", ["Kein Event"] + df_events["name"].tolist(), key="events_tab1", label_visibility="collapsed", index=0, placeholder="")

            st.write("**Anzahl Rennen:**")
            num_races = st.number_input("Anzahl Rennen", min_value=1, max_value=48, value=4, step=1, label_visibility="collapsed")

            st.write("**Auswahlmodus:**")
            selection_mode = st.segmented_control("Strecken-Auswahlmodus", options=["Zufällig", "Auswahl"], default="Zufällig", label_visibility="collapsed")

            st.write("**Spielmodus:**")
            game_mode = st.segmented_control("Spielmodus", options=["Kario", "Mario"], default="Kario", label_visibility="collapsed")

            st.write("")

            # Start
            if st.button("**Starten**", type="primary"):
                if len(selected_names) < 2:
                    st.error("❌ Ein Turnier erfordert mindestens 2 Spieler!")
                else:
                    st.session_state.total_races = int(num_races)
                    st.session_state.event = selected_event if selected_event != "Kein Event" else None
                    st.session_state.current_round = 1
                    st.session_state.selection_mode = selection_mode
                    st.session_state.game_mode = game_mode
                    st.session_state.active_players = selected_names
                    st.session_state.tournament_active = True
                    st.rerun()

        # Races
        elif st.session_state.tournament_active and not st.session_state.waiting_for_placement:

            header("Rennergebnisse")

            active_players = st.session_state.active_players
            all_races_valid = True
            first_invalid_race = None

            # Expanders
            for race_num in range(1, st.session_state.total_races + 1):
                should_be_open = (race_num == st.session_state.current_round)
                if should_be_open:
                    expander_title = f"🔥 **Rennen {race_num}**"
                elif st.session_state.get("final_check_failed", False):
                    expander_title = f"✅ **Rennen {race_num}**"
                elif race_num < st.session_state.current_round:
                    expander_title = f"✅ **Rennen {race_num}**"
                else:
                    expander_title = f"**Rennen {race_num}**"

                with st.expander(expander_title, expanded=should_be_open):

                    # Track
                    all_track_names = df_tracks["name"].tolist()
                    saved_track = st.session_state.backup_races.get(f"track_{race_num}", None)
                    track_index = all_track_names.index(saved_track) if saved_track in all_track_names else None

                    st.write("**Strecke:**")
                    track_name = st.selectbox("Strecke", all_track_names, index=track_index, key=f"track_{race_num}", label_visibility="collapsed", placeholder="")

                    picked_by_name = None
                    if st.session_state.selection_mode == "Auswahl":
                        saved_picker = st.session_state.backup_races.get(f"picker_{race_num}", None)
                        picker_index = active_players.index(saved_picker) if saved_picker in active_players else None
                        st.write("**Gewählt von:**")
                        picked_by_name = st.selectbox("Gewählt von", active_players, index=picker_index, key=f"picker_{race_num}", label_visibility="collapsed", placeholder="")

                    # Head-to-Head
                    df_h2h_track, shared_races = get_df_h2h_track(track_name, tuple(active_players))
                    if not df_h2h_track.empty:
                        st.write("**Ø-Platz (H2H):**")
                        st.write(f"Gemeinsame Rennen: {shared_races}")
                        st.dataframe(df_h2h_track, hide_index=True, width="stretch")
                    else:
                        df_avg_track = get_df_avg_track(track_name, tuple(active_players))
                        if not df_avg_track.empty:
                            st.write("**Ø-Platz (Individuell):**")
                            st.dataframe(df_avg_track, hide_index=True, width="stretch")
                        elif track_name is not None:
                            st.info("Keine Statistiken für diese Strecke vorhanden.")

                    # Placements
                    placements = {}
                    error = False
                    placement_error = False
                    duplicate = False
                    track_missing = False
                    for name in active_players:
                        saved_placement = st.session_state.backup_races.get(f"placement_{race_num}_{name}", None)
                        val = placement_selection(name, prefix_key=f"r_{race_num}", default_val=saved_placement)
                        if val in ["two_positions", "missing"]:
                            error = True
                            placement_error = True
                        else:
                            placements[name] = int(val)
                    if not placement_error and has_duplicates(list(placements.values())):
                        error = True
                        duplicate = True
                    if track_name is None:
                        error = True
                        track_missing = True
                    if error:
                        all_races_valid = False
                        if first_invalid_race is None:
                            first_invalid_race = race_num

                    st.write("")

                    # Next
                    if should_be_open:
                        if race_num < st.session_state.total_races:
                            if st.button(f"**Weiter**", key=f"btn_next_{race_num}"):
                                if placement_error:
                                    st.error("❌ Exakt eine Platzierung pro Spieler wählen!")
                                elif duplicate:
                                    st.error("❌ Doppelte Platzierung!")
                                elif track_missing:
                                    st.error("❌ Gefahrene Strecke wählen!")
                                else:
                                    st.session_state.current_round = race_num + 1
                                    st.rerun()

            st.write("")

            col_save, col_cancel = st.columns([3, 1])
            with col_save:

                # Save
                if st.button("**Speichern**", type="primary"):
                    if not all_races_valid:
                        st.error(f"❌ Fehler! Überprüfe Rennen {first_invalid_race}.")
                        st.session_state.current_round = first_invalid_race
                        st.session_state.final_check_failed = True
                        time.sleep(2)
                        st.rerun()
                    else:
                        st.session_state.final_check_failed = False
                        st.session_state.backup_races = {}

                        # Backup
                        for race in range(1, st.session_state.total_races + 1):
                            st.session_state.backup_races[f"track_{race}"] = st.session_state[f"track_{race}"]
                            if st.session_state.selection_mode == "Auswahl":
                                st.session_state.backup_races[f"picker_{race}"] = st.session_state[f"picker_{race}"]
                            for name in active_players:
                                p1 = st.session_state.get(f"seg1_r_{race}_{name}")
                                p2 = st.session_state.get(f"seg2_r_{race}_{name}")
                                placement_val = p1 if p1 is not None else p2
                                st.session_state.backup_races[f"placement_{race}_{name}"] = int(placement_val) if placement_val is not None else None

                        st.session_state.tournament_active = False
                        st.session_state.waiting_for_placement = True
                        st.rerun()

            with col_cancel:

                # Cancel
                if st.button("❌ **Abbrechen**"):
                    st.session_state.backup_races = {}
                    st.session_state.final_check_failed = False
                    st.session_state.tournament_active = False
                    st.rerun()

        # Finalize tournament
        elif st.session_state.waiting_for_placement:
            header("Endplatzierungen")

            active_players = st.session_state.active_players
            selected_event = st.session_state.event
            final_placements = {}
            beer_finished = {}
            placement_error = False
            ui_error_beer = False

            # Total points
            points_dict = {name: 0 for name in active_players}
            points_mapping = get_points_mapping()
            for race in range(1, st.session_state.total_races + 1):
                for name in active_players:
                    placement = st.session_state.backup_races.get(f"placement_{race}_{name}")
                    if placement in points_mapping:
                        points_dict[name] += points_mapping[placement]

            # Tournament placements
            active_players.sort(key=lambda name: points_dict[name], reverse=True)
            for name in active_players:
                val = placement_selection(name, prefix_key="fp", custom_title=f"**{name}** ({points_dict[name]} Punkte)**:**")
                if val in ["two_positions", "missing"]:
                    placement_error = True
                else:
                    final_placements[name] = int(val)

            # Kario
            if st.session_state.game_mode == "Kario":
                st.write("---")
                header("Bier")

                for name in active_players:
                    st.write(f"**{name}:**")
                    beer_options = list(range(1, st.session_state.total_races + 1))
                    beer_options.append("❌")
                    beer_val = st.segmented_control(f"Beer_{name}", options=beer_options, key=f"beer_fp_{name}", label_visibility="collapsed")
                    if beer_val is None:
                        ui_error_beer = True
                    else:
                        if beer_val == "❌":
                            beer_finished[name] = "❌"
                        else:
                            beer_finished[name] = int(beer_val)

            st.divider()

            col_finalize, col_cancel = st.columns([3, 1])
            with col_finalize:

                # Finalize
                if st.button("**Abschließen**", type="primary"):
                    if placement_error:
                        st.error("❌ Exakt eine Platzierung pro Spieler wählen!")
                    elif st.session_state.game_mode == "Kario" and ui_error_beer:
                        st.error("❌ Für alle Spieler angeben, wann das Bier geleert wurde!")
                    else:
                        cur = conn.cursor()
                        if "❌" in list(beer_finished.values()):
                            st.error("⚠️ Bier nicht geleert, Endplatzierung wird auf 12 gesetzt!")

                        # "tournaments" table
                        berlin_tz = ZoneInfo("Europe/Berlin")
                        current_timestamp = datetime.now(tz=berlin_tz).strftime("%Y-%m-%d %H:%M:%S")
                        cur.execute("""
                            INSERT INTO tournaments (date) 
                            VALUES (%s)
                            RETURNING id;
                        """, [current_timestamp])
                        tournament_id = cur.fetchone()[0]

                        # "races" table
                        for race_num in range(1, st.session_state.total_races + 1):
                            saved_track = st.session_state.backup_races[f"track_{race_num}"]
                            saved_picker = st.session_state.backup_races.get(f"picker_{race_num}", None)
                            cur.execute("""
                                INSERT INTO races (tournament_id, track_name, picked_by_name) 
                                VALUES (%s, %s, %s)
                                RETURNING id;
                            """, (tournament_id, saved_track, saved_picker))
                            race_id = cur.fetchone()[0]

                            # "race_results" table
                            for name in active_players:
                                placement = st.session_state.backup_races[f"placement_{race_num}_{name}"]
                                cur.execute("""
                                    INSERT INTO race_results (race_id, player_name, placement) 
                                    VALUES (%s, %s, %s);
                                """, (race_id, name, int(placement)))

                        # "tournament_results" table
                        kario_val = 1 if st.session_state.game_mode == "Kario" else 0
                        for player_name, final_place in final_placements.items():
                            beer_val = beer_finished.get(player_name, None)
                            if beer_val == "❌":
                                beer_val = None
                                final_place = 12
                            cur.execute("""
                                INSERT INTO tournament_results (tournament_id, player_name, final_placement, beer_finished_after, kario, event_name) 
                                VALUES (%s, %s, %s, %s, %s, %s);
                            """, (tournament_id, player_name, final_place, beer_val, kario_val, selected_event))

                        conn.commit()
                        st.cache_data.clear()
                        st.session_state.backup_races = {}
                        st.session_state.waiting_for_placement = False
                        time.sleep(2)
                        st.rerun()

            with col_cancel:

                # Back
                if st.button("**Zurück**"):
                    st.session_state.waiting_for_placement = False
                    st.session_state.tournament_active = True
                    st.session_state.current_round = st.session_state.total_races + 1
                    st.session_state.final_check_failed = False
                    st.rerun()

                # Cancel
                if st.button("**Abbrechen**"):
                    st.session_state.waiting_for_placement = False
                    st.rerun()

# ==========================================
# TAB 2: PLAYER PROFILES
# ==========================================
with tab2:
    header("Verwaltung")

    if not st.session_state.authenticated:
        st.warning("🔒 Melde dich an.")

    # Normal Login (no delete)
    elif not st.session_state.master:

        # PLayers
        with st.expander("**Spieler-Datenbank**"):

            # Add
            st.write("**Neuer Spieler:**")
            new_name = st.text_input("Neuer Spieler", label_visibility="collapsed")
            if st.button("**Hinzufügen**", type="primary", key="add_player"):
                if new_name.strip():
                    try:
                        cur = conn.cursor()
                        cur.execute("""
                            INSERT INTO players (name) 
                            VALUES (%s);
                        """, (new_name.strip(),))
                        conn.commit()
                        get_df_players.clear()
                        st.success(f"{new_name} hinzugefügt!")
                        time.sleep(2)
                        st.rerun()
                    except psycopg2.IntegrityError:
                        st.error("❌ Name existiert bereits!")

        # Events
        with st.expander("**Event-Datenbank**"):

            # Add
            st.write("**Neues Event:**")
            new_event = st.text_input("Neues Event", label_visibility="collapsed")
            if st.button("**Hinzufügen**", type="primary", key="add_event"):
                if new_event.strip():
                    try:
                        cur = conn.cursor()
                        cur.execute("""
                            INSERT INTO events (name) 
                            VALUES (%s);
                        """, (new_event.strip(),))
                        conn.commit()
                        get_df_events.clear()
                        st.success(f"{new_event} hinzugefügt!")
                        time.sleep(2)
                        st.rerun()
                    except psycopg2.IntegrityError:
                        st.error("❌ Event existiert bereits!")

    # Master Login
    else:

        # Players
        with st.expander("**Spieler-Datenbank**"):
            col_add, col_del = st.columns(2)

            # Add
            with col_add:
                st.write("**Neuer Spieler:**")
                new_name = st.text_input("Neuer Spieler", label_visibility="collapsed")
                if st.button("**Hinzufügen**", type="primary", key="add_player_master"):
                    if new_name.strip():
                        try:
                            cur = conn.cursor()
                            cur.execute("""
                                INSERT INTO players (name)
                                VALUES (%s);
                            """, (new_name.strip(),))
                            conn.commit()
                            get_df_players.clear()
                            st.success(f"{new_name} hinzugefügt!")
                            time.sleep(2)
                            st.rerun()
                        except psycopg2.IntegrityError:
                            st.error("❌ Name existiert bereits!")

            # Delete
            with col_del:
                st.write("**Löschen:**")
                delete_name = st.selectbox("Löschen", df_players["name"].tolist(), label_visibility="collapsed", index=None, placeholder="")
                if st.session_state.get("confirm_delete_player") != delete_name or st.session_state.get("confirm_delete_player") is None:
                    if st.button("**Löschen**", type="secondary", key="del_player_master"):
                        st.session_state.confirm_delete_player = delete_name
                        st.rerun()
                else:
                    st.error(f"⚠️ **{delete_name}** unwiderruflich löschen?")
                    c_conf1, c_conf2 = st.columns(2)
                    with c_conf1:
                        if st.button("**Löschen**", type="primary", width="stretch"):
                            cur = conn.cursor()
                            cur.execute("""
                                DELETE FROM players
                                WHERE name = %s;
                            """, [delete_name])
                            conn.commit()
                            get_df_players.clear()
                            st.error(f"{delete_name} gelöscht!")
                            st.session_state.confirm_delete_player = None
                            time.sleep(2)
                            st.rerun()
                    with c_conf2:
                        if st.button("**Abbrechen**", width="stretch"):
                            st.session_state.confirm_delete_player = None
                            st.rerun()

        # Events
        with st.expander("**Event-Datenbank**"):
            col_add, col_del = st.columns(2)

            # Add
            with col_add:
                st.write("**Neues Event:**")
                new_event = st.text_input("Neues Event", label_visibility="collapsed")
                if st.button("**Hinzufügen**", type="primary", key="add_event_master"):
                    if new_event.strip():
                        try:
                            cur = conn.cursor()
                            cur.execute("""
                                INSERT INTO events (name)
                                VALUES (%s);
                            """, (new_event.strip(),))
                            conn.commit()
                            get_df_events.clear()
                            st.success(f"{new_event} hinzugefügt!")
                            time.sleep(2)
                            st.rerun()
                        except psycopg2.IntegrityError:
                            st.error("❌ Event existiert bereits!")

            # Delete
            with col_del:
                st.write("**Löschen:**")
                delete_event = st.selectbox("Löschen", df_events["name"].tolist(), label_visibility="collapsed", index=None, placeholder="")
                if st.session_state.get("confirm_delete_event") != delete_event or st.session_state.get("confirm_delete_event") is None:
                    if st.button("**Löschen**", type="secondary", key="del_event_master"):
                        st.session_state.confirm_delete_event = delete_event
                        st.rerun()
                else:
                    st.error(f"⚠️ **{delete_event}** unwiderruflich löschen?")
                    c_conf1, c_conf2 = st.columns(2)
                    with c_conf1:
                        if st.button("**Löschen**", type="primary", width="stretch"):
                            cur = conn.cursor()
                            cur.execute("""
                                DELETE FROM events
                                WHERE name = %s;
                            """, [delete_event])
                            conn.commit()
                            get_df_events.clear()
                            st.error(f"{delete_event} gelöscht!")
                            st.session_state.confirm_delete_event = None
                            time.sleep(2)
                            st.rerun()
                    with c_conf2:
                        if st.button("**Abbrechen**", width="stretch"):
                            st.session_state.confirm_delete_event = None
                            st.rerun()

    st.divider()

    # Player stats
    header("Filter")
    if not df_players.empty:
        # st.write("**Spieler:**")
        st.write("**Spieler:**")
        profile_name = st.selectbox("Spieler", df_players["name"].tolist(), label_visibility="collapsed")

        # Filter event
        st.write("**Event:**")
        event_filter = st.selectbox("Event", ["Alle Events"] + df_events["name"].tolist(), key="event_filter_tab2", label_visibility="collapsed", index=0, placeholder="")

        # Filter track
        st.write("**Strecke:**")
        track_filter = st.selectbox("Strecke", ["Alle Strecken"] + df_tracks["name"].tolist(), key="track_filter_tab2", label_visibility="collapsed", index=0, placeholder="")

        # Filter game mode
        st.write("**Spielmodus:**")
        mode_filter = st.segmented_control("Modus", options=["Gesamt", "Kario", "Mario"], default="Gesamt", key="mode_filter_tab2", label_visibility="collapsed")

        # Race metrics
        df_races, avg_normalized_points, df_tournaments, df_best, df_fav = get_player_stats(profile_name, event_filter, mode_filter, track_filter)

        st.divider()

        header("Spieler-Statistiken")
        if pd.notnull(df_races["total_races"]) and df_races["total_races"] > 0:

            total_pts = df_races["total_points"] or 0
            total_races = df_races["total_races"] or 1

            # Metrics display
            st.write("**Metriken:**")
            m_col1, m_col2, m_col3, m_col4 = st.columns(4)
            with m_col1:
                st.metric("Ø-Platz Rennen", f"{df_races['avg_race_placement']:.2f}")
                if track_filter == "Alle Strecken":
                    st.metric("Ø-Platz Rennen\n(w.s.g.)", f"{df_races['avg_race_placement_picked']:.2f}" if pd.notnull(df_races['avg_race_placement_picked']) else "N/A")
                    st.metric("Ø-Platz Turnier", f"{df_tournaments['avg_tournament_placement']:.2f}" if pd.notnull(df_tournaments['avg_tournament_placement']) else "N/A")
            with m_col2:
                st.metric("Ø-Punkte / Rennen", f"{df_races['avg_race_points']:.2f}")
                if track_filter == "Alle Strecken":
                    st.metric("Ø-Punkte / Turnier\n(4 R.)", f"{avg_normalized_points:.2f}")
                    if mode_filter != "Mario":
                        st.metric("Ø-Rennen / Bier", f"{df_tournaments['avg_beer_finished_after']:.2f}" if pd.notnull(df_tournaments['avg_beer_finished_after']) else "N/A")
            with m_col3:
                st.metric("Rennsiege", f"{int(df_races['race_wins'] or 0)}")
                if track_filter == "Alle Strecken":
                    st.metric("Turniersiege", f"{int(df_tournaments['tournament_wins'] or 0)}")
            with m_col4:
                st.metric("Rennen", f"{int(df_races['total_points'])}")
                if track_filter == "Alle Strecken":
                    st.metric("Turniere", f"{int(df_tournaments['total_tournaments'] or 0)}")

            st.write("**Ranglisten:**")
            t_col1, t_col2 = st.columns(2)
            with t_col1:
                semibold("🔝 Beste Strecken")
                st.dataframe(df_best, hide_index=True, width="stretch")
            with t_col2:
                semibold("❤️ Lieblingsstrecken")
                st.dataframe(df_fav, hide_index=True, width="stretch")
        else:
            st.info("Keine Statistiken für diesen Spieler vorhanden.")

# ==========================================
# TAB 3: TRACK DATABASE
# ==========================================
with tab3:
    header("Filter")

    st.write("**Strecke:**")
    selected_track = st.selectbox("Strecke", df_tracks["name"].tolist(), label_visibility="collapsed")

    st.divider()

    header("Strecken-Statistiken")
    play_count, df_most_picked, df_placement, df_points, df_wins = get_track_stats(selected_track)
    st.write(f"**Gespielt:** {play_count}x")

    if play_count > 0:
        st.write(f"**Gewählt:**")
        st.dataframe(df_most_picked, hide_index=True, width="stretch")
        st.write("**Ranglisten:**")
        rl1, rl2, rl3 = st.columns(3)
        with rl1:
            semibold("Nach Ø-Platz")
            st.dataframe(df_placement, hide_index=True, width="stretch")
        with rl2:
            semibold("Nach Ø-Punkten")
            st.dataframe(df_points, hide_index=True, width="stretch")
        with rl3:
            semibold("Nach Anzahl Siegen")
            st.dataframe(df_wins, hide_index=True, width="stretch")

# ==========================================
# TAB 4: HEAD-TO-HEAD
# ==========================================
with tab4:
    header("Filter")
    st.write("**Spieler:**")
    rivals = st.multiselect("Spieler", df_players["name"].tolist(), key="players_tab4", default=["Pfeiffer", "Markus"] if len(df_players) >= 2 else [], label_visibility="collapsed")

    # Filter event
    st.write("**Event:**")
    event_filter = st.selectbox("Event", ["Alle Events"] + df_events["name"].tolist(), key="event_filter_tab4", label_visibility="collapsed", index=0, placeholder="")

    # Filter track
    st.write("**Strecke:**")
    track_filter = st.selectbox("Strecke", ["Alle Strecken"] + df_tracks["name"].tolist(), key="track_filter_tab4", label_visibility="collapsed", index=0, placeholder="")

    # Filter game mode
    st.write("**Spielmodus:**")
    mode_filter = st.segmented_control("Modus", options=["Gesamt", "Kario", "Mario"], default="Gesamt", key="mode_filter_tab4", label_visibility="collapsed")

    st.divider()

    header("Vergleich")

    if len(rivals) >= 2:
        df_h2h_r, df_h2h_t = get_h2h_data(tuple(rivals), event_filter, track_filter, mode_filter)

        if not df_h2h_r.empty:
            if track_filter == "Alle Strecken":
                c1, c2 = st.columns(2)
                with c1:
                    semibold("Rennsiege")
                    st.bar_chart(df_h2h_r.groupby("player")["race_win"].sum().reset_index().set_index("player"), color=st.secrets["custom_theme"]["highlight_color"])
                    semibold("Ø-Platz Rennen ↓")
                    st.bar_chart(df_h2h_r.groupby("player")["placement"].mean().reset_index().set_index("player"), color=st.secrets["custom_theme"]["highlight_color"])
                    semibold("Ø-Punkte / Rennen")
                    st.bar_chart(df_h2h_r.groupby("player")["points"].mean().reset_index().set_index("player"), color=st.secrets["custom_theme"]["highlight_color"])

                with c2:
                    if not df_h2h_t.empty:
                        semibold("Turniersiege")
                        st.bar_chart(df_h2h_t.groupby("player")["tournament_win"].sum().reset_index().set_index("player"), color=st.secrets["custom_theme"]["highlight_color"])
                        semibold("Ø-Platz Turnier ↓")
                        st.bar_chart(df_h2h_t.groupby("player")["final_placement"].mean().reset_index().set_index("player"), color=st.secrets["custom_theme"]["highlight_color"])
                        semibold("Ø-Punkte / Turnier")
                        st.bar_chart(df_h2h_t.groupby("player")["tournament_points"].mean().reset_index().set_index("player"), color=st.secrets["custom_theme"]["highlight_color"])
            else:
                semibold("Rennsiege")
                st.bar_chart(df_h2h_r.groupby("player")["race_win"].sum().reset_index().set_index("player"), color=st.secrets["custom_theme"]["highlight_color"])
                semibold("Ø-Platz Rennen ↓")
                st.bar_chart(df_h2h_r.groupby("player")["placement"].mean().reset_index().set_index("player"), color=st.secrets["custom_theme"]["highlight_color"])
                semibold("Ø-Punkte / Rennen")
                st.bar_chart(df_h2h_r.groupby("player")["points"].mean().reset_index().set_index("player"), color=st.secrets["custom_theme"]["highlight_color"])

        else:
            st.info("Keine Statistiken für diese Spieler vorhanden.")
    else:
        st.info("Mindestens 2 Spieler wählen.")

# ==========================================
# TAB 5: HISTORY & EDITING
# ==========================================
with tab5:
    header("Turnierverlauf")

    df_history = get_history_list()

    if df_history.empty:
        st.info("Keine Turniere vorhanden.")
    else:

        st.dataframe(df_history, width="stretch", hide_index=True, column_order=["Turnier-Nr.", "Datum", "Teilnehmer", "Modus", "Event"], height=st.secrets["custom_theme"]["dataframe_height"])

        st.divider()

        header("Turnier-Nr.")
        num_to_id = dict(zip(df_history["Turnier-Nr."], df_history["Turnier-ID"]))
        selected_tournament_num = st.selectbox("Turnier zum Bearbeiten", df_history['Turnier-Nr.'].tolist(),key="select_edit_id",label_visibility="collapsed")
        selected_tournament_id = num_to_id.get(selected_tournament_num)

        st.divider()

        if selected_tournament_id:
            disable_edit = False if st.session_state.master else True

            event_name, df_current_placements, df_current_points, df_current_beer, num_races_in_tournament, df_race_list = get_tournament_edit_data(selected_tournament_id)
            current_points_dict = dict(zip(df_current_points["player_name"], df_current_points["total_points"]))

            # Event
            header("Event")
            current_event_index = df_events["name"].tolist().index(event_name) + 1 if pd.notna(event_name) else 0
            if disable_edit:
                disable_selectbox("edit_event")
            new_event = st.selectbox("Event", ["Kein Event"] + df_events["name"].tolist(), key="edit_event", label_visibility="collapsed", index=current_event_index, placeholder="")
            if not disable_edit:
                if st.button("**Aktualisieren**", type="primary", key="event_update"):
                    cur = conn.cursor()
                    if new_event == "Kein Event":
                        new_event = None
                    cur.execute("""
                        UPDATE tournament_results
                        SET event_name = %s
                        WHERE tournament_id = %s;
                    """, (new_event, selected_tournament_id))
                    conn.commit()
                    st.cache_data.clear()
                    st.success("Event aktualisiert!")
                    time.sleep(2)
                    st.rerun()

            st.divider()


            # Tournament placements
            header("Endergebnisse")

            edited_final_placements = {}
            ui_error_fp = False

            for _, row in df_current_placements.iterrows():
                val = placement_selection(row['player_name'], prefix_key=f"edit_fp_{selected_tournament_id}", custom_title=f"**{row['player_name']}** ({current_points_dict.get(row['player_name'], 0)} Punkte)**:**", default_val=int(row['final_placement']), disabled=disable_edit)
                if val in ["two_positions", "missing"]:
                    ui_error_fp = True
                else:
                    edited_final_placements[row['player_name']] = int(val)

            st.write("")

            if not disable_edit:
                if st.button("**Aktualisieren**", type="primary", key="races_update"):
                    if ui_error_fp:
                        st.error("❌ Exakt eine Platzierung pro Spieler wählen!")
                    else:
                        cur = conn.cursor()
                        for player_name, new_final_placement in edited_final_placements.items():
                            cur.execute("""
                                UPDATE tournament_results 
                                SET final_placement = %s 
                                WHERE tournament_id = %s AND player_name = %s;
                            """, (new_final_placement, selected_tournament_id, player_name))
                        conn.commit()
                        st.cache_data.clear()
                        st.success("Endergebnisse aktualisiert!")
                        time.sleep(2)
                        st.rerun()

            # Kario
            kario = (df_current_beer['kario'] == 1).any()
            if kario:
                st.divider()
                header("Bier")


                beer_options = list(range(1, num_races_in_tournament + 1))
                beer_options.append("❌")

                edited_beer = {}
                ui_error_b_fp = False

                for _, row in df_current_beer.iterrows():

                    st.write(f"**{row['player_name']}:**")
                    beer_default = "❌"
                    if pd.notna(row["beer_finished_after"]):
                        beer_default = row["beer_finished_after"]

                    if disable_edit:
                        disable_segmented_control(f"edit_beer_fp_{selected_tournament_id}_{row['player_name']}")
                    beer_val = st.segmented_control(f"Beer_{row['player_name']}", options=beer_options, key=f"edit_beer_fp_{selected_tournament_id}_{row['player_name']}", label_visibility="collapsed", default=beer_default)
                    if beer_val is None:
                        ui_error_b_fp = True
                    else:
                        if beer_val == "❌":
                            edited_beer[row['player_name']] = "❌"
                        else:
                            edited_beer[row['player_name']] = int(beer_val)

                st.write("")

                if not disable_edit:
                    if st.button("**Aktualisieren**", type="primary", key="beer_update"):
                        if ui_error_b_fp:
                            st.error("❌ Für alle Spieler angeben, wann das Bier geleert wurde!")
                        else:
                            cur = conn.cursor()
                            # if "❌" in list(edited_beer.values()):
                            #     st.error("⚠️ Bier nicht geleert, Endplatzierung wird auf 12 gesetzt!")

                            for player_name, new_beer_val in edited_beer.items():
                                if new_beer_val == "❌":
                                    new_beer_val = None
                                #     new_final_placement = 12
                                #     cur.execute("""
                                #         UPDATE tournament_results
                                #         SET final_placement = %s
                                #         WHERE tournament_id = %s AND player_name = %s;
                                #     """, (new_final_placement, selected_tournament_id, player_name))

                                cur.execute("""
                                    UPDATE tournament_results 
                                    SET beer_finished_after = %s 
                                    WHERE tournament_id = %s AND player_name = %s;
                                """, (new_beer_val, selected_tournament_id, player_name))

                            conn.commit()
                            st.cache_data.clear()
                            for key in list(st.session_state.keys()):
                                if f"edit_fp_{selected_tournament_id}" in key:
                                    del st.session_state[key]
                            st.success("Biere aktualisiert!")
                            time.sleep(2)
                            st.rerun()

            st.divider()

            # Races
            header("Rennergebnisse")


            for idx, r_row in df_race_list.iterrows():
                race_id = int(r_row['race_id'])
                with st.expander(f"**Rennen {idx + 1}** (ID #{race_id})**:** {r_row['track_name']}"):
                    curr_track_name, picker_name_db, df_race_placements = get_race_edit_data(race_id)
                    all_track_names = df_tracks["name"].tolist()

                    st.write("**Strecke:**")
                    track_index = all_track_names.index(curr_track_name) if curr_track_name in all_track_names else 0
                    if disable_edit:
                        disable_selectbox(f"edit_track_{race_id}")
                    edit_track_name = st.selectbox("Strecke", all_track_names, index=track_index, key=f"edit_track_{race_id}", label_visibility="collapsed")
                    race_players = df_race_placements['player_name'].tolist()

                    edit_picked_by_name = None
                    if picker_name_db is not None or st.session_state.get("selection_mode") == "Auswahl":
                        st.write("**Gewählt von:**")
                        picker_index = race_players.index(picker_name_db) if picker_name_db in race_players else 0
                        if disable_edit:
                            disable_selectbox(f"edit_picker_{race_id}")
                        edit_picked_by_name = st.selectbox("Gewählt von", race_players, index=picker_index, key=f"edit_picker_{race_id}", label_visibility="collapsed")

                    edited_race_placements = {}
                    ui_race_error = False
                    has_duplicate_race = False

                    for _, p_row in df_race_placements.iterrows():
                        val = placement_selection(p_row['player_name'], prefix_key=f"edit_r_{race_id}", default_val=int(p_row['placement']), disabled=disable_edit)

                        if val in ["two_positions", "missing"]:
                            ui_race_error = True
                        else:
                            edited_race_placements[p_row['player_name']] = int(val)

                    # if not ui_race_error and has_duplicates(list(edited_race_placements.values())):
                    #     ui_race_error = True
                    #     has_duplicate_race = True

                    st.write("")

                    if not disable_edit:
                        if st.button("**Aktualisieren**", key=f"btn_update_race_{race_id}", type="primary"):
                            if ui_race_error and not has_duplicate_race:
                                st.error("❌ Exakt eine Platzierung pro Spieler wählen!")
                            # elif has_duplicate_race:
                            #     st.error("❌ Doppelte Platzierung!")
                            else:
                                cur = conn.cursor()

                                cur.execute("""
                                    UPDATE races 
                                    SET track_name = %s, picked_by_name = %s 
                                    WHERE id = %s;
                                """, (edit_track_name, edit_picked_by_name, race_id))

                                for p_name, new_place in edited_race_placements.items():
                                    cur.execute("""
                                        UPDATE race_results 
                                        SET placement = %s 
                                        WHERE race_id = %s AND player_name = %s;
                                    """, (new_place, race_id, p_name))

                                conn.commit()
                                st.cache_data.clear()
                                st.success("Rennergebnis aktualisiert!")
                                time.sleep(2)
                                st.rerun()

            if not disable_edit:

                st.write("---")

                # Delete tournament
                if st.session_state.get("confirm_delete_tournament") != selected_tournament_id:
                    if st.button("**Löschen**", type="secondary", key=f"btn_del_{selected_tournament_id}"):
                        st.session_state.confirm_delete_tournament = selected_tournament_id
                        st.rerun()
                else:
                    st.error(f"⚠️ **Turnier Nr. {selected_tournament_num}** unwiderruflich löschen?")
                    c_conf1, c_conf2 = st.columns(2)

                    with c_conf1:
                        if st.button("**Löschen**", type="primary", key=f"btn_del_confirm_{selected_tournament_id}", width="stretch"):
                            cur = conn.cursor()
                            cur.execute("""
                                DELETE FROM tournaments 
                                WHERE id = %s;
                            """, [selected_tournament_id])
                            conn.commit()
                            st.cache_data.clear()

                            st.session_state.confirm_delete_tournament = None
                            st.error(f"Turnier #{selected_tournament_id} gelöscht!")
                            time.sleep(2)
                            st.rerun()

                    with c_conf2:
                        if st.button("**Abbrechen**", width="stretch"):
                            st.session_state.confirm_delete_tournament = None
                            st.rerun()
