import time
from math import isnan
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st
from streamlit_float import *
import psycopg2
import warnings
warnings.filterwarnings('ignore', message='.*pandas only supports SQLAlchemy.*')


# ==========================================
# 1. CONNECTION
# ==========================================
@st.cache_resource
def init_connection():
    return psycopg2.connect(**st.secrets["postgres"])
conn = init_connection()
cursor = conn.cursor()
float_init()

# ==========================================
# 2. SESSION STATES
# ==========================================

# Authentication
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "master" not in st.session_state:
    st.session_state.master = False

# Tournament parameters
if "tournament_id" not in st.session_state:
    st.session_state.tournament_id = None
if "active_players" not in st.session_state:
    st.session_state.active_players = []
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
if "confirm_delete_tournament" not in st.session_state:
    st.session_state.confirm_delete_tournament = None


# ==========================================
# 3. HELPER FUNCTIONS
# ==========================================
def has_duplicates(lst):
    """Checks for duplicates in a list."""
    return len(lst) != len(set(lst))

def ui_placement_selection(name, prefix_key, default_val=None, custom_title=None, disabled=False):
    """Generates two 1x6 Segmented Controls and validates the input."""
    title = custom_title if custom_title else f"**{name}:**"
    st.write(title)
    # st.write("")

    val1 = default_val if default_val in [1, 2, 3, 4, 5, 6] else None
    val2 = default_val if default_val in [7, 8, 9, 10, 11, 12] else None

    place1 = st.segmented_control("Platz 1-6", options=[1, 2, 3, 4, 5, 6], default=val1, key=f"seg1_{prefix_key}_{name}", label_visibility="collapsed", disabled=disabled)
    place2 = st.segmented_control("Platz 7-12", options=[7, 8, 9, 10, 11, 12], default=val2, key=f"seg2_{prefix_key}_{name}", label_visibility="collapsed", disabled=disabled)

    if (place1 is not None) and (place2 is not None):
        return "two_positions"
    if (place1 is None) and (place2 is None):
        return "missing"

    return place1 if place1 is not None else place2

def header(text, border=st.secrets["custom_theme"]["border"], color=st.secrets["custom_theme"]["color"], padding_v=st.secrets["custom_theme"]["padding_v"], padding_h=st.secrets["custom_theme"]["padding_h"], border_radius=st.secrets["custom_theme"]["border_radius"], font_size=st.secrets["custom_theme"]["font_size"], font_weight=st.secrets["custom_theme"]["font_weight"]):
    st.markdown(
        f"""
            <p style="
                font-size: {font_size}px; 
                font-weight: {font_weight}; 
                line-height: 1.5; 
                color: #FAFAFA; 
                border-left: {border * 2}px solid {color}; 
                padding-left: {padding_h}px; margin: 10px 0;">
                {text}
            </p>
        """,
        unsafe_allow_html=True
)

# ==========================================
# 4. CACHED FUNCTIONS
# ==========================================
@st.cache_data
def get_points_mapping_count():
    return pd.read_sql_query("SELECT COUNT(*) FROM points_mapping;", conn)["count"][0]

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
            GROUP BY race_id HAVING COUNT(DISTINCT player_name) = %s
        ) 
        AND rr.player_name IN ({placeholders}) 
        GROUP BY rr.player_name ORDER BY AVG(rr.placement) ASC;
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
        GROUP BY rr.player_name ORDER BY AVG(rr.placement) ASC;
    """
    params = [track_name] + list(players)
    return pd.read_sql_query(query, conn, params=params)

@st.cache_data
def get_player_stats(profile_name, kario_cond, kario_cond_tr2):
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
        {kario_cond};
    """
    df_races = pd.read_sql_query(query_races, conn, params=(profile_name,))

    query_tournaments = f"""
        SELECT 
            COUNT(DISTINCT tr.tournament_id) as total_tournaments,
            AVG(tr.final_placement) as avg_tournament_placement,
            SUM(CASE WHEN tr.final_placement = 1 THEN 1 ELSE 0 END) as tournament_wins,
            AVG(tr.beer_finished_after) as avg_beer_finished_after
        FROM tournament_results tr 
        WHERE tr.player_name = %s 
        {kario_cond};
    """
    df_tournaments = pd.read_sql_query(query_tournaments, conn, params=(profile_name,))

    query_best = f"""
        SELECT 
            r.track_name as "Strecke", 
            COUNT(rr.id) as "Gefahren", 
            ROUND(AVG(rr.placement), 2) as "Ø-Platz" 
        FROM race_results rr 
        JOIN races r ON rr.race_id = r.id 
        JOIN tournament_results tr ON r.tournament_id = tr.tournament_id AND rr.player_name = tr.player_name 
        WHERE rr.player_name = %s 
        {kario_cond} 
        GROUP BY r.track_name ORDER BY AVG(rr.placement) ASC LIMIT 5;
    """
    df_best = pd.read_sql_query(query_best, conn, params=(profile_name,))

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
                {kario_cond_tr2}
            ), 2) as "Ø-Platz" 
        FROM races r 
        JOIN tournament_results tr ON r.tournament_id = tr.tournament_id AND tr.player_name = r.picked_by_name 
        WHERE r.picked_by_name = %s 
        {kario_cond} 
        GROUP BY r.track_name ORDER BY COUNT(r.id) DESC, r.track_name ASC LIMIT 5;
    """
    df_fav = pd.read_sql_query(query_favorites, conn, params=(profile_name, profile_name))

    return df_races.iloc[0], df_tournaments.iloc[0], df_best, df_fav

@st.cache_data
def get_track_stats(selected_track):
    query_play_count = f"""
        SELECT COUNT(*) as count 
        FROM races 
        WHERE track_name = %s;
    """
    df_play_count = pd.read_sql_query(query_play_count, conn, params=(selected_track,))

    query_most_picked = f"""
        SELECT 
            picked_by_name as "Spieler", 
            COUNT(*) as "Gewählt" 
        FROM races 
        WHERE track_name = %s 
        AND picked_by_name IS NOT NULL 
        GROUP BY "Spieler" ORDER BY "Gewählt" DESC LIMIT 5;
    """
    df_most_picked = pd.read_sql_query(query_most_picked, conn, params=(selected_track,))

    query_placement = f"""
        SELECT 
            player_name as "Spieler", 
            AVG(rr.placement) as "Ø-Platz" 
        FROM race_results rr 
        JOIN races r ON rr.race_id = r.id 
        WHERE r.track_name = %s 
        GROUP BY player_name ORDER BY "Ø-Platz" ASC;
    """
    df_placement = pd.read_sql_query(query_placement, conn, params=(selected_track,))

    query_points = f"""
        SELECT 
            player_name as "Spieler", 
            AVG(pm.points) as "Ø-Punkte" 
        FROM race_results rr 
        JOIN races r ON rr.race_id = r.id 
        JOIN points_mapping pm ON rr.placement = pm.placement 
        WHERE r.track_name = %s 
        GROUP BY player_name ORDER BY "Ø-Punkte" DESC;
    """
    df_points = pd.read_sql_query(query_points, conn, params=(selected_track,))

    query_wins = f"""
        SELECT 
            player_name as "Spieler", 
            COUNT(*) as "Rennsiege"
        FROM race_results rr 
        JOIN races r ON rr.race_id = r.id 
        WHERE r.track_name = %s 
        AND rr.placement = 1 
        GROUP BY player_name ORDER BY "Rennsiege" DESC;
    """
    df_wins = pd.read_sql_query(query_wins, conn, params=(selected_track,))

    return df_play_count, df_most_picked, df_placement, df_points, df_wins

@st.cache_data
def get_h2h_data(players, h2h_track, h2h_mode):
    h2h_placeholders = ",".join(["%s"] * len(players))
    h2h_kario_cond = " AND tr.kario = 1" if h2h_mode == "Kario" else (" AND tr.kario = 0" if h2h_mode == "Mario" else "")
    subquery_shared = f"""
        SELECT r.tournament_id 
        FROM race_results rr 
        JOIN races r ON rr.race_id = r.id 
        WHERE rr.player_name IN ({h2h_placeholders}) 
        GROUP BY r.tournament_id HAVING COUNT(DISTINCT rr.player_name) = %s
    """
    track_condition = " AND r.track_name = %s" if h2h_track != "Alle Strecken" else ""

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
        AND rr.player_name IN ({h2h_placeholders}) 
        {track_condition} 
        {h2h_kario_cond};
    """
    params_r = list(players) + [len(players)] + list(players)
    if h2h_track != "Alle Strecken":
        params_r.append(h2h_track)
    df_r = pd.read_sql_query(query_h2h_r, conn, params=params_r)

    query_h2h_t = f"""
        SELECT 
            tr.player_name as player, 
            tr.final_placement, 
            (
                SELECT SUM(pm2.points) 
                FROM race_results rr2 
                JOIN points_mapping pm2 ON rr2.placement = pm2.placement 
                JOIN races r2 ON rr2.race_id = r2.id 
                WHERE r2.tournament_id = tr.tournament_id 
                AND rr2.player_name = tr.player_name
            ) as tournament_points, 
            CASE WHEN tr.final_placement = 1 THEN 1 ELSE 0 END as tournament_win 
        FROM tournament_results tr 
        WHERE tr.tournament_id IN ({subquery_shared}) 
        AND tr.player_name IN ({h2h_placeholders}) 
        {h2h_kario_cond};
    """
    params_t = list(players) + [len(players)] + list(players)
    df_t = pd.read_sql_query(query_h2h_t, conn, params=params_t)

    return df_r, df_t

@st.cache_data
def get_tournament_edit_data(tournament_id):
    df_placements = pd.read_sql_query("""
        SELECT 
            player_name, 
            final_placement 
        FROM tournament_results 
        WHERE tournament_id = %s;
    """, conn, params=(tournament_id,))

    df_points = pd.read_sql_query("""
        SELECT 
            rr.player_name, 
            SUM(pm.points) as total_points 
        FROM race_results rr 
        JOIN races r ON rr.race_id = r.id 
        JOIN points_mapping pm ON rr.placement = pm.placement 
        WHERE r.tournament_id = %s 
        GROUP BY rr.player_name;
    """, conn, params=(tournament_id,))

    df_beer = pd.read_sql_query("""
        SELECT 
            player_name, 
            beer_finished_after, 
            kario 
        FROM tournament_results 
        WHERE tournament_id = %s;
    """, conn, params=(tournament_id,))

    df_race_count = pd.read_sql_query("""
        SELECT COUNT(*) as c 
        FROM races 
        WHERE tournament_id = %s;
    """, conn, params=(tournament_id,))
    num_races = int(df_race_count['c'].iloc[0]) if not df_race_count.empty else 1

    df_race_list = pd.read_sql_query("""
        SELECT 
            id as race_id, 
            track_name 
        FROM races 
        WHERE tournament_id = %s;
    """, conn, params=(tournament_id,))

    return df_placements, df_points, df_beer, num_races, df_race_list

@st.cache_data
def get_race_edit_data(race_id):
    df_race_info = pd.read_sql_query("""
        SELECT 
            track_name, 
            picked_by_name 
        FROM races 
        WHERE id = %s;
    """, conn, params=(race_id,))
    track_name = df_race_info['track_name'].iloc[0] if not df_race_info.empty else None
    picked_by = df_race_info['picked_by_name'].iloc[0] if not df_race_info.empty else None

    df_placements = pd.read_sql_query("""
        SELECT 
            player_name, 
            placement 
        FROM race_results 
        WHERE race_id = %s;
    """, conn, params=(race_id,))

    return track_name, picked_by, df_placements

@st.cache_data
def get_history_list():
    query = f"""
        SELECT 
            t.id as "Turnier-ID", 
            t.date as "Datum", 
            STRING_AGG(tr.player_name, ', ') as "Teilnehmer" 
        FROM tournaments t 
        JOIN tournament_results tr ON t.id = tr.tournament_id 
        GROUP BY t.id, t.date ORDER BY t.id DESC;
    """
    df =  pd.read_sql_query(query, conn)

    if not df.empty:
        df.insert(0, "Turnier-Nr.", range(len(df), 0, -1))
        df = df.sort_values(by="Turnier-ID", ascending=False).reset_index(drop=True)

    return df


# ==========================================
# 3. PAGE CONFIG & DATABASE INITIALIZATION
# ==========================================
st.set_page_config(page_title="Kario Mart Dashboard", page_icon="🏎️", layout="centered")

st.markdown(
    """
        <style>
            header[data-testid="stHeader"] {
                display: none;
            }
            
            /* Toolbar (Deploy/Share/GitHub) entfernen */
            [data-testid="stToolbar"] {
                display: none;
            }
            
            /* Sidebar wirklich oben beginnen lassen */
            [data-testid="stSidebar"] {
                top: 0 !important;
                height: 100vh !important;
            }
            
            /* Hauptbereich ebenfalls nach oben schieben */
            [data-testid="stAppViewContainer"] {
                margin-top: 0 !important;
            }
        </style>
    """,
    unsafe_allow_html=True
)

# Custom CSS for sidebar
st.markdown(
    """
        <style>
        /* Force the sidebar to float on top */
        [data-testid="stSidebar"] {
            position: absolute !important;
            z-index: 9999 !important;
            height: 100vh !important;
            box-shadow: 5px 0px 15px rgba(0,0,0,0.15);
            top: 0 !important;
        }
        
        /* Stop main content container from squeezing or shifting */
        [data-testid="stAppViewBlockContainer"] {
            margin-left: 0px !important;
            width: 100% !important;
            max-width: 100% !important;
            padding-left: 5rem !important; /* Leave a small gap for the sidebar toggle button */
        }
        </style>
    """,
    unsafe_allow_html=True
)

# Custom CSS for tabs
st.markdown(
    f"""
        <style>        
        /* Remove top padding */
        [data-testid="stMainBlockContainer"],
        .main .block-container {{
            padding-top: 3.5rem !important;
            margin-top: 0 !important;
        }}


        /* Font size */
        .st-key-tabs div[data-baseweb="button-group"] button div {{
            font-size: {st.secrets["custom_theme"]["font_size"]}px !important;
        }}
        
        /* Reset buttons */
        .st-key-tabs div[data-baseweb="button-group"] button {{
            border: none !important;
            margin: 0 !important;
            box-sizing: border-box !important;
        }}
        
        /* Lines between buttons */
        .st-key-tabs div[data-baseweb="button-group"] button + button {{
            border-left: {st.secrets["custom_theme"]["border"]}px solid {st.secrets["custom_theme"]["color"]} !important;
        }}
        
         /* Border */
        .st-key-tabs div[data-baseweb="button-group"] {{
            border: {st.secrets["custom_theme"]["border"]}px solid {st.secrets["custom_theme"]["color"]} !important;
            border-radius: {st.secrets["custom_theme"]["border_radius"]}px; 
            overflow: hidden !important;
        }}
        </style>
    """,
    unsafe_allow_html=True,
)
tab1, tab2, tab3, tab4, tab5 = "🎮", "👤", "🏁", "⚔️", "📋"
container = st.container(width="stretch")
with container:
    tab = st.segmented_control("Tabs", options=[tab1, tab2, tab3, tab4, tab5], default=tab1, width="stretch", label_visibility="collapsed", key="tabs")
css_config = float_css_helper(background="var(--default-backgroundColor)", transform="translateX(-50%)", width="90%", max_width="700px", top="4rem", left="50%", z_index="999")
container.float(css_config)

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
                st.success("Anmeldung erfolgreich!")
                time.sleep(2)
                st.rerun()
            elif password == st.secrets["passwords"]["user_pw"]:
                st.session_state.authenticated = True
                st.success("Anmeldung erfolgreich!")
                time.sleep(2)
                st.rerun()
            else:
                st.error("❌ Falsches Passwort!")
    else:

        # Login successful
        if st.session_state.master:
            st.success("🔒 Angemeldet als Admin")
        else:
            st.success("🔒 Angemeldet")
        if st.button("**Abmelden**", type="secondary", width="stretch"):
            st.session_state.authenticated = False
            st.session_state.master = False
            st.rerun()

# Database initialization
# cursor.execute("""
#     CREATE TABLE IF NOT EXISTS players (
#         id SERIAL PRIMARY KEY, 
#         name TEXT NOT NULL UNIQUE
#     );
# """)
# cursor.execute("""
#     CREATE TABLE IF NOT EXISTS tracks (
#         id SERIAL PRIMARY KEY, 
#         name TEXT NOT NULL UNIQUE, 
#         cup TEXT NOT NULL
#     );
# """)
# cursor.execute("""
#     CREATE TABLE IF NOT EXISTS points_mapping (
#         placement INTEGER PRIMARY KEY CHECK (placement BETWEEN 1 AND 12), 
#         points INTEGER NOT NULL
#     );
# """)
# cursor.execute("""
#     CREATE TABLE IF NOT EXISTS tournaments (
#         id SERIAL PRIMARY KEY, 
#         date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
#     );
# """)
# cursor.execute("""
#     CREATE TABLE IF NOT EXISTS races (
#         id SERIAL PRIMARY KEY, 
#         tournament_id INTEGER REFERENCES tournaments(id) ON DELETE CASCADE, 
#         track_name TEXT REFERENCES tracks(name) ON DELETE RESTRICT, 
#         picked_by_name TEXT REFERENCES players(name) ON DELETE SET NULL
#     );
# """)
# cursor.execute("""
#     CREATE TABLE IF NOT EXISTS race_results (
#         id SERIAL PRIMARY KEY, 
#         race_id INTEGER REFERENCES races(id) ON DELETE CASCADE, 
#         player_name TEXT REFERENCES players(name) ON DELETE CASCADE, 
#         placement INTEGER REFERENCES points_mapping(placement), 
#         UNIQUE (race_id, player_name)
#     );
# """)
# cursor.execute("""
#     CREATE TABLE IF NOT EXISTS tournament_results (
#         id SERIAL PRIMARY KEY, 
#         tournament_id INTEGER REFERENCES tournaments(id) ON DELETE CASCADE, 
#         player_name TEXT REFERENCES players(name) ON DELETE CASCADE, 
#         final_placement INTEGER CHECK (final_placement BETWEEN 1 AND 12), 
#         beer_finished_after INTEGER, 
#         kario INTEGER, 
#         UNIQUE (tournament_id, player_name)
#     );
# """)
# conn.commit()

# ==========================================
# 4. SEED DATA
# ==========================================
points_mapping_count = get_points_mapping_count()
if points_mapping_count == 0:

    # Points mapping
    points_data = [(1, 15), (2, 12), (3, 10), (4, 9), (5, 8), (6, 7), (7, 6), (8, 5), (9, 4), (10, 3), (11, 2), (12, 1)]
    cursor.executemany("""
        INSERT INTO points_mapping (placement, points)
        VALUES (%s, %s);
    """, points_data)

    # Player data
    player_data = [("Anja",), ("Pfeiffer",), ("Markus",)]
    cursor.executemany("""
        INSERT INTO players (name)
        VALUES (%s);
    """, player_data)

    # Track data
    track_data = [
        ("Mario Kart-Stadion", "Pilz-Cup"), ("Wasserpark", "Pilz-Cup"), ("Zuckersüßer Canyon", "Pilz-Cup"), ("Steinblock-Ruinen", "Pilz-Cup"),
        ("Marios Piste", "Blumen-Cup"), ("Toads Hafenstadt", "Blumen-Cup"), ("Gruselwusel-Villa", "Blumen-Cup"), ("Shy Guys Wasserfälle", "Blumen-Cup"),
        ("Sonnenflughafen", "Stern-Cup"), ("Delfinlagune", "Stern-Cup"), ("Discodrom", "Stern-Cup"), ("Wario-Abfahrt", "Stern-Cup"),
        ("Wolkenstraße", "Spezial-Cup"), ("Knochentrockene Dünen", "Spezial-Cup"), ("Bowsers Festung", "Spezial-Cup"), ("Regenbogen-Boulevard", "Spezial-Cup"),
        ("Wii Kuhmuh-Weide", "Panzer-Cup"), ("GBA Marios Piste", "Panzer-Cup"), ("DS Cheep-Cheep-Strand", "Panzer-Cup"), ("N64 Toads Autobahn", "Panzer-Cup"),
        ("GCN Staubtrockene Wüste", "Bananen-Cup"), ("SNES Donut-Ebene 3", "Bananen-Cup"), ("N64 Königliche Rennpiste", "Bananen-Cup"), ("3DS DK Dschungel", "Bananen-Cup"),
        ("DS Wario-Arena", "Blatt-Cup"), ("GCN Sorbet-Land", "Blatt-Cup"), ("3DS Instrumentalpiste", "Blatt-Cup"), ("N64 Yoshi-Tal", "Blatt-Cup"),
        ("DS Ticktack-Trauma", "Blitz-Cup"), ("3DS Röhrenraserei", "Blitz-Cup"), ("Wii Vulkangrollen", "Blitz-Cup"), ("N64 Regenbogen-Boulevard", "Blitz-Cup"),
        ("GCN Yoshis Piste", "Ei-Cup"), ("Excitebike-Stadion", "Ei-Cup"), ("Große Drachenmauer", "Ei-Cup"), ("Mute City", "Ei-Cup"),
        ("Wii Warios Goldmine", "Triforce-Cup"), ("SNES Regenbogen-Boulevard", "Triforce-Cup"), ("Polarkreis-Parcours", "Triforce-Cup"), ("Hyrule-Piste", "Triforce-Cup"),
        ("GCN Baby-Park", "Crossing-Cup"), ("GBA Käseland", "Crossing-Cup"), ("Wilder Wipfelweg", "Crossing-Cup"), ("Animal Crossing-Dorf", "Crossing-Cup"),
        ("3DS Koopa-Großstadtfieber", "Glocken-Cup"), ("GBA Party-Straße", "Glocken-Cup"), ("Marios-Metro", "Glocken-Cup"), ("Big Blue", "Glocken-Cup"),
        ("Tour Paris-Parcours", "Goldener Turbo-Cup"), ("3DS Toads Piste", "Goldener Turbo-Cup"), ("N64 Schoko-Sumpf", "Goldener Turbo-Cup"), ("Wii Kokos-Promenade", "Goldener Turbo-Cup"),
        ("Tour Tokio-Tempotour", "Glückskatzen-Cup"), ("DS Pilz-Pass", "Glückskatzen-Cup"), ("GBA Wolkenpiste", "Glückskatzen-Cup"), ("Tour Ninja-Dojo", "Glückskatzen-Cup"),
        ("Tour New-York-Speedway", "Rüben-Cup"), ("SNES Marios Piste 3", "Rüben-Cup"), ("N64 Kalimari-Wüste", "Rüben-Cup"), ("DS Waluigi-Flipper", "Rüben-Cup"),
        ("Tour Sydney-Spritztour", "Propeller-Cup"), ("GBA Schneeland", "Propeller-Cup"), ("Wii Pilz-Schlucht", "Propeller-Cup"), ("Eiscreme-Eskapade", "Propeller-Cup"),
        ("Tour London-Tour", "Fels-Cup"), ("GBA Buu-Huu-Tal", "Fels-Cup"), ("3DS Gebirgspfad", "Fels-Cup"), ("Wii Blätterwald", "Fels-Cup"),
        ("Tour Pflaster von Berlin", "Mond-Cup"), ("DS Peachs Schlossgarten", "Mond-Cup"), ("Tour Bergbescherung", "Mond-Cup"), ("3DS Regenbogen-Boulevard", "Mond-Cup"),
        ("Tour Ausfahrt Amsterdam", "Frucht-Cup"), ("GBA Flussufer-Park", "Frucht-Cup"), ("Wii DK Skikane", "Frucht-Cup"), ("Yoshis Eiland", "Frucht-Cup"),
        ("Tour Bangkok-Abendrot", "Bumerang-Cup"), ("DS Marios Piste", "Bumerang-Cup"), ("GCN Waluigi-Arena", "Bumerang-Cup"), ("Tour Überholspur Singapur", "Bumerang-Cup"),
        ("Tour Athen auf Abwegen", "Feder-Cup"), ("GCN Daisys Dampfer", "Feder-Cup"), ("Wii Mondblickstraße", "Feder-Cup"), ("Bad-Parcours", "Feder-Cup"),
        ("Tour Los-Angeles-Strandpartie", "Doppelkirschen-Cup"), ("GBA Sonnenuntergangs-Wüste", "Doppelkirschen-Cup"), ("Wii Koopa-Kap", "Doppelkirschen-Cup"), ("Tour Vancouver-Wildpfad", "Doppelkirschen-Cup"),
        ("Tour Rom-Rambazamba", "Eichel-Cup"), ("GCN DK-Bergland", "Eichel-Cup"), ("Wii Daisys Piste", "Eichel-Cup"), ("Tour Piranha-Pflanzen-Bucht", "Eichel-Cup"),
        ("Tour Stadtrundfahrt Madrid", "Stachi-Cup"), ("3DS Rosalinas Eisplanet", "Stachi-Cup"), ("SNES Bowsers Festung 3", "Stachi-Cup"), ("Wii Regenbogen-Boulevard", "Stachi-Cup")
    ]
    cursor.executemany("""
        INSERT INTO tracks (name, cup)
        VALUES (%s, %s);
    """, track_data)

    conn.commit()
    st.cache_data.clear()
    st.rerun()

# Get players and tracks for dropdowns
df_players = get_df_players()
df_tracks = get_df_tracks()


# ==========================================
# TAB 1: TOURNAMENT TRACKING
# ==========================================
if tab == tab1:
    if not st.session_state.authenticated:
        st.warning("🔒 Melde dich in der Sidebar an, um Turniere zu erfassen.")
    else:

        # Tournament setup
        if not st.session_state.tournament_active and not st.session_state.waiting_for_placement:
            header("Setup")
            st.write("")

            st.write("**Spieler:**")
            selected_names = st.multiselect("Spieler", df_players["name"].tolist(), key="players_tab1", default=["Pfeiffer", "Markus"] if len(df_players) >= 2 else [], label_visibility="collapsed")

            st.write("**Anzahl Rennen:**")
            num_races = st.number_input("Anzahl Rennen", min_value=1, max_value=48, value=4, step=1, label_visibility="collapsed")

            st.write("**Strecken-Auswahlmodus:**")
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
                    st.session_state.current_round = 1
                    st.session_state.selection_mode = selection_mode
                    st.session_state.game_mode = game_mode
                    st.session_state.active_players = selected_names
                    st.session_state.tournament_active = True
                    st.rerun()

        # Races
        elif st.session_state.tournament_active and not st.session_state.waiting_for_placement:

            header("Rennergebnisse")
            st.write("")
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
                    ui_error = False
                    duplicate = False
                    for name in active_players:
                        saved_placement = st.session_state.backup_races.get(f"placement_{race_num}_{name}", None)
                        val = ui_placement_selection(name, prefix_key=f"r_{race_num}", default_val=saved_placement)
                        if val in ["two_positions", "missing"]:
                            error = True
                            ui_error = True
                        else:
                            placements[name] = int(val)
                    if not ui_error and has_duplicates(list(placements.values())):
                        error = True
                        duplicate = True
                    if error:
                        all_races_valid = False
                        if first_invalid_race is None:
                            first_invalid_race = race_num

                    st.write("")

                    # Next
                    if should_be_open:
                        if race_num < st.session_state.total_races:
                            if st.button(f"**Weiter**", key=f"btn_next_{race_num}"):
                                if ui_error:
                                    st.error("❌ Exakt eine Platzierung pro Spieler wählen!")
                                elif duplicate:
                                    st.error("❌ Doppelte Platzierung!")
                                else:
                                    st.session_state.current_round = race_num + 1
                                    st.rerun()

            st.write("")

            col_save, col_cancel = st.columns([3, 1])
            with col_save:

                # Save
                if st.button("**Speichern**", type="primary"):
                    if not all_races_valid:
                        st.error(f"❌ Fehler bei den Platzierungen! Überprüfe Rennen {first_invalid_race}.")
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
                    st.session_state.tournament_id = None
                    st.rerun()

        # Finalize tournament
        elif st.session_state.waiting_for_placement:
            header("Turnierplatzierungen")
            st.write("")
            active_players = st.session_state.active_players
            final_placements = {}
            beer_finished = {}
            ui_error = False
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
            for name in active_players:
                val = ui_placement_selection(name, prefix_key="fp", custom_title=f"**{name}** ({points_dict[name]} Punkte)**:**")
                if val in ["two_positions", "missing"]:
                    ui_error = True
                else:
                    final_placements[name] = int(val)

            # Kario
            if st.session_state.game_mode == "Kario":
                st.write("---")
                header("Bier")
                st.write("")
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
                    if ui_error:
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
                        tournament_id = cur.execute("""
                            INSERT INTO tournaments (date) 
                            VALUES (%s)
                            RETURNING id;
                        """, (current_timestamp,))
                        st.session_state.tournament_id = cur.fetchone()[0]

                        # "races" table
                        for race_num in range(1, st.session_state.total_races + 1):
                            saved_track = st.session_state.backup_races[f"track_{race_num}"]
                            saved_picker = st.session_state.backup_races.get(f"picker_{race_num}", None)
                            cur.execute("""
                                INSERT INTO races (tournament_id, track_name, picked_by_name) 
                                VALUES (%s, %s, %s)
                                RETURNING id;
                            """, (st.session_state.tournament_id, saved_track, saved_picker))
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
                                INSERT INTO tournament_results (tournament_id, player_name, final_placement, beer_finished_after, kario) 
                                VALUES (%s, %s, %s, %s, %s);
                            """, (st.session_state.tournament_id, player_name, final_place, beer_val, kario_val))

                        conn.commit()
                        st.cache_data.clear()
                        st.session_state.backup_races = {}
                        st.session_state.waiting_for_placement = False
                        st.session_state.tournament_id = None
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
                    st.session_state.tournament_id = None
                    st.rerun()

# ==========================================
# TAB 2: PLAYER PROFILES
# ==========================================
if tab == tab2:
    header("Verwaltung")
    st.write("")
    with st.expander("**Spieler-Datenbank**"):
        if not st.session_state.authenticated:
            st.warning("🔒 Melde dich an.")
        else:
            col_add, col_del = st.columns(2)

            # Add
            with col_add:
                st.write("**Neuer Spieler:**")
                new_name = st.text_input("Neuer Spieler", label_visibility="collapsed")
                if st.button("**Hinzufügen**", type="primary"):
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
                if not df_players.empty:
                    st.write("**Löschen:**")
                    delete_name = st.selectbox("Löschen", df_players["name"].tolist(), label_visibility="collapsed", index=None, placeholder="")
                    if st.session_state.get("confirm_delete_player") != delete_name or st.session_state.get("confirm_delete_player") is None:
                        if st.button("**Löschen**", type="secondary"):
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
                                """, (delete_name,))
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

    st.divider()

    # Player stats
    header("Spieler-Statistiken")
    st.write("")
    if not df_players.empty:
        st.write("**Spieler:**")
        profile_name = st.selectbox("Spieler", df_players["name"].tolist(), label_visibility="collapsed")

        # Filter game mode
        t2_mode = st.segmented_control("Statistiken filtern", options=["Gesamt", "Kario", "Mario"], default="Gesamt", key="t2_mode", label_visibility="collapsed")

        # Filter conditions
        kario_cond = ""
        kario_cond_tr2 = ""
        if t2_mode == "Kario":
            kario_cond = " AND tr.kario = 1"
            kario_cond_tr2 = " AND tr2.kario = 1"
        elif t2_mode == "Mario":
            kario_cond = " AND tr.kario = 0"
            kario_cond_tr2 = " AND tr2.kario = 0"

        # Race metrics
        df_races, df_tournaments, df_best, df_fav = get_player_stats(profile_name, kario_cond, kario_cond_tr2)

        # Formatting
        st.markdown("""
            <style>
                [data-testid="stMetricLabel"], 
                [data-testid="stMetricLabel"] * {
                    white-space: pre-wrap !important;
                }
            </style>
        """, unsafe_allow_html=True)

        if pd.notnull(df_races["total_races"]) and df_races["total_races"] > 0:
            total_pts = df_races["total_points"] or 0
            total_races = df_races["total_races"] or 1
            normalized_points = (total_pts / total_races) * 4

            # Metrics display
            m_col1, m_col2, m_col3, m_col4 = st.columns(4)
            with m_col1:
                st.metric("**Ø-Platz Rennen**", f"{df_races['avg_race_placement']:.2f}")
                st.metric("**Ø-Platz Rennen\n(w.s.g.)**", f"{df_races['avg_race_placement_picked']:.2f}" if pd.notnull(df_races['avg_race_placement_picked']) else "N/A")
                st.metric("**Ø-Platz Turnier**", f"{df_tournaments['avg_tournament_placement']:.2f}" if pd.notnull(df_tournaments['avg_tournament_placement']) else "N/A")
            with m_col2:
                st.metric("**Ø-Punkte / Rennen**", f"{df_races['avg_race_points']:.2f}")
                st.metric("**Ø-Punkte / Turnier\n(4 R.)**", f"{normalized_points:.2f}")
                st.metric("**Ø-Rennen / Bier**", f"{df_tournaments['avg_beer_finished_after']:.2f}" if pd.notnull(df_tournaments['avg_beer_finished_after']) else "N/A")
            with m_col3:
                st.metric("**Rennsiege**", f"{int(df_races['race_wins'] or 0)}")
                st.metric("**Turniersiege**", f"{int(df_tournaments['tournament_wins'] or 0)}")
            with m_col4:
                st.metric("**Rennen**", f"{int(total_races)}")
                st.metric("**Turniere**", f"{int(df_tournaments['total_tournaments'] or 0)}")

            st.divider()

            # Ranking display
            header("Ranglisten")
            st.write("")
            t_col1, t_col2 = st.columns(2)
            with t_col1:
                st.write("**🔝 Beste Strecken**")
                st.dataframe(df_best, hide_index=True, width="stretch")
            with t_col2:
                st.write("**❤️ Lieblingsstrecken**")
                st.dataframe(df_fav, hide_index=True, width="stretch")
        else:
            st.info("Keine Statistiken für diesen Spieler vorhanden.")

# ==========================================
# TAB 3: TRACK DATABASE
# ==========================================
if tab == tab3:
    header("Strecken-Statistiken")
    st.write("")
    st.write("**Strecke:**")
    selected_track = st.selectbox("Strecke", df_tracks["name"].tolist(), label_visibility="collapsed")
    df_play_count, df_most_picked, df_placement, df_points, df_wins = get_track_stats(selected_track)

    st.write(f"**Gespielt:** {df_play_count['count'].values[0]}x")

    if df_play_count['count'].values[0] > 0:
        st.dataframe(df_most_picked, hide_index=True, width="stretch")

        st.write("---")

        header("Ranglisten")
        st.write("")
        rl1, rl2, rl3 = st.columns(3)
        with rl1:
            st.write("**Nach Ø-Platz**")
            st.dataframe(df_placement, hide_index=True, width="stretch")
        with rl2:
            st.write("**Nach Ø-Punkten**")
            st.dataframe(df_points, hide_index=True, width="stretch")
        with rl3:
            st.write("**Nach Anzahl Siegen**")
            st.dataframe(df_wins, hide_index=True, width="stretch")

# ==========================================
# TAB 4: HEAD-TO-HEAD
# ==========================================
if tab == tab4:
    header("Vergleich")
    st.write("")
    st.write("**Spieler:**")
    rivals = st.multiselect("Spieler", df_players["name"].tolist(), key="players_tab4", default=["Pfeiffer", "Markus"] if len(df_players) >= 2 else [], label_visibility="collapsed")

    if len(rivals) >= 2:
        h2h_placeholders = ",".join(["%s"] * len(rivals))

        st.write("**Filterung nach Strecke:**")
        h2h_track = st.selectbox("Filterung nach Strecke", ["Alle Strecken"] + df_tracks["name"].tolist(), label_visibility="collapsed")

        # Filter game mode
        h2h_mode = st.segmented_control("Modus filtern", options=["Gesamt", "Kario", "Mario"], default="Gesamt", key="h2h_mode", label_visibility="collapsed")

        df_h2h_r, df_h2h_t = get_h2h_data(tuple(rivals), h2h_track, h2h_mode)

        if not df_h2h_r.empty:
            c1, c2 = st.columns(2)
            with c1:
                st.write("**Rennsiege**")
                st.bar_chart(df_h2h_r.groupby("player")["race_win"].sum().reset_index().set_index("player"), color="#FF4B4B")
                st.write("**Ø-Platz Rennen ↓**")
                st.bar_chart(df_h2h_r.groupby("player")["placement"].mean().reset_index().set_index("player"), color="#FF4B4B")
                st.write("**Ø-Punkte / Rennen**")
                st.bar_chart(df_h2h_r.groupby("player")["points"].mean().reset_index().set_index("player"), color="#FF4B4B")

            with c2:
                if h2h_track == "Alle Strecken":
                    if not df_h2h_t.empty:
                        st.write("**Turniersiege**")
                        st.bar_chart(df_h2h_t.groupby("player")["tournament_win"].sum().reset_index().set_index("player"), color="#FF4B4B")
                        st.write("**Ø-Platz Turnier ↓**")
                        st.bar_chart(df_h2h_t.groupby("player")["final_placement"].mean().reset_index().set_index("player"), color="#FF4B4B")
                        st.write("**Ø-Punkte / Turnier**")
                        st.bar_chart(df_h2h_t.groupby("player")["tournament_points"].mean().reset_index().set_index("player"), color="#FF4B4B")
                else:
                    st.info("Turnier-Statistiken bei Streckenfilter ausgeblendet.")
        else:
            st.info("Keine Statistiken für diese Spieler vorhanden.")

# ==========================================
# TAB 5: HISTORY & EDITING
# ==========================================
if tab == tab5:
    header("Turnierverlauf")
    st.write("")

    df_history = get_history_list()

    if df_history.empty:
        st.info("Keine Turniere vorhanden.")
    else:

        st.dataframe(df_history, width="stretch", hide_index=True, column_order=["Turnier-Nr.", "Teilnehmer", "Datum"])
        st.divider()

        header("Turnier-Nr.")
        st.write("")

        num_to_id = dict(zip(df_history["Turnier-Nr."], df_history["Turnier-ID"]))
        selected_tournament_num = st.selectbox("Turnier zum Bearbeiten", df_history['Turnier-Nr.'].tolist(),key="select_edit_id",label_visibility="collapsed")
        selected_tournament_id = num_to_id.get(selected_tournament_num)

        st.divider()

        if selected_tournament_id:
            disable_edit = False if st.session_state.master else True

            # Tournament placements
            header("Endergebnisse")
            st.write("")
            df_current_placements, df_current_points, df_current_beer, num_races_in_tournament, df_race_list = get_tournament_edit_data(selected_tournament_id)
            current_points_dict = dict(zip(df_current_points["player_name"], df_current_points["total_points"]))

            edited_final_placements = {}
            ui_error_fp = False

            for _, row in df_current_placements.iterrows():
                val = ui_placement_selection(row['player_name'], prefix_key=f"edit_fp_{selected_tournament_id}", custom_title=f"**{row['player_name']}** ({current_points_dict.get(row['player_name'], 0)} Punkte)**:**", default_val=int(row['final_placement']))
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
                        for key in list(st.session_state.keys()):
                            if f"edit_fp_{selected_tournament_id}" in key:
                                del st.session_state[key]
                        st.rerun()

            # Kario
            kario = (df_current_beer['kario'] == 1).any()
            if kario:
                st.divider()
                header("Bier")
                st.write("")

                beer_options = list(range(1, num_races_in_tournament + 1))
                beer_options.append("❌")

                edited_beer = {}
                ui_error_b_fp = False

                for _, row in df_current_beer.iterrows():

                    st.write(f"**{row['player_name']}:**")
                    beer_default = "❌"
                    if not isnan(row["beer_finished_after"]):
                        beer_default = row["beer_finished_after"]

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
                            if "❌" in list(edited_beer.values()):
                                st.error("⚠️ Bier nicht geleert, Endplatzierung wird auf 12 gesetzt!")

                            for player_name, new_beer_val in edited_beer.items():
                                if new_beer_val == "❌":
                                    new_beer_val = None
                                    new_final_placement = 12
                                    cur.execute("""
                                        UPDATE tournament_results 
                                        SET final_placement = %s 
                                        WHERE tournament_id = %s AND player_name = %s;
                                    """, (new_final_placement, selected_tournament_id, player_name))

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
                            time.sleep(2)
                            st.rerun()

            st.divider()

            # Races
            header("Rennergebnisse")
            st.write("")

            for idx, r_row in df_race_list.iterrows():
                race_id = int(r_row['race_id'])
                with st.expander(f"**Rennen {idx + 1}** (ID #{race_id})**:** {r_row['track_name']}"):
                    curr_track_name, picker_name_db, df_race_placements = get_race_edit_data(race_id)
                    all_track_names = df_tracks["name"].tolist()

                    st.write("**Strecke:**")
                    track_index = all_track_names.index(curr_track_name) if curr_track_name in all_track_names else 0
                    edit_track_name = st.selectbox("Strecke", all_track_names, index=track_index, key=f"edit_track_{race_id}", label_visibility="collapsed")
                    race_players = df_race_placements['player_name'].tolist()

                    edit_picked_by_name = None
                    if picker_name_db is not None or st.session_state.get("selection_mode") == "Auswahl":
                        st.write("**Gewählt von:**")
                        picker_index = race_players.index(picker_name_db) if picker_name_db in race_players else 0
                        edit_picked_by_name = st.selectbox("Gewählt von", race_players, index=picker_index, key=f"edit_picker_{race_id}", label_visibility="collapsed")

                    edited_race_placements = {}
                    ui_race_error = False
                    has_duplicate_race = False

                    for _, p_row in df_race_placements.iterrows():
                        val = ui_placement_selection(p_row['player_name'], prefix_key=f"edit_r_{race_id}", default_val=int(p_row['placement']))

                        if val in ["two_positions", "missing"]:
                            ui_race_error = True
                        else:
                            edited_race_placements[p_row['player_name']] = int(val)

                    if not ui_race_error and has_duplicates(list(edited_race_placements.values())):
                        ui_race_error = True
                        duplicate_race = True

                    st.write("")

                    if not disable_edit:
                        if st.button("**Aktualisieren**", key=f"btn_update_race_{race_id}", type="primary"):
                            if ui_race_error and not duplicate_race:
                                st.error("❌ Exakt eine Platzierung pro Spieler wählen!")
                            elif duplicate_race:
                                st.error("❌ Doppelte Platzierung!")
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
                                st.success("Rennen aktualisiert!")
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
                            """, (selected_tournament_id,))
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
