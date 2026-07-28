import time
from math import isnan
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st
import psycopg2
import warnings
warnings.filterwarnings('ignore', message='.*pandas only supports SQLAlchemy.*')


# ==========================================
# CONNECTION & GLOBAL VARIABLES
# ==========================================
@st.cache_resource
def init_connection():
    return psycopg2.connect(**st.secrets["postgres"])
conn = init_connection()
cursor = conn.cursor()


# ==========================================
# 1. SESSION STATES
# ==========================================

# Authentication
if "authenticated" not in st.session_state: st.session_state.authenticated = False

# Tournament Parameters
if "tournament_id" not in st.session_state: st.session_state.tournament_id = None
if "active_players" not in st.session_state: st.session_state.active_players = []
if "total_races" not in st.session_state: st.session_state.total_races = 4
if "selection_mode" not in st.session_state: st.session_state.selection_mode = "Zufällig"
if "game_mode" not in st.session_state: st.session_state.game_mode = "Kario"

# Tournament Flow & UI Control
if "tournament_active" not in st.session_state: st.session_state.tournament_active = False
if "current_round" not in st.session_state: st.session_state.current_round = 1
if "waiting_for_final_placement" not in st.session_state: st.session_state.waiting_for_final_placement = False
if "final_check_failed" not in st.session_state: st.session_state.final_check_failed = False
if "backup_races" not in st.session_state: st.session_state.backup_races = {}

# Security Prompts
if "confirm_delete_player" not in st.session_state: st.session_state.confirm_delete_player = None
if "confirm_delete_tournament" not in st.session_state: st.session_state.confirm_delete_tournament = None


# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================

def has_duplicates(lst):
    """Checks for duplicates in a list."""
    return len(lst) != len(set(lst))

def ui_placement_selection(name, prefix_key, default_val=None, custom_title=None):
    """Generates two 1x6 Segmented Controls and validates the input."""
    title = custom_title if custom_title else f"**{name}:**"
    st.write(title)

    val1 = default_val if default_val in [1, 2, 3, 4, 5, 6] else None
    val2 = default_val if default_val in [7, 8, 9, 10, 11, 12] else None

    place1 = st.segmented_control("Platz 1-6", options=[1, 2, 3, 4, 5, 6], default=val1, key=f"seg1_{prefix_key}_{name}", label_visibility="collapsed")
    place2 = st.segmented_control("Platz 7-12", options=[7, 8, 9, 10, 11, 12], default=val2, key=f"seg2_{prefix_key}_{name}", label_visibility="collapsed")

    st.write("")
    if (place1 is not None) and (place2 is not None):
        return "doppelt"
    if (place1 is None) and (place2 is None):
        return "fehlt"

    return place1 if place1 is not None else place2


# ==========================================
# 3. PAGE CONFIG & DATABASE INITIALIZATION
# ==========================================

# Page Title and Tabs
st.set_page_config(page_title="Kario Mart Dashboard", page_icon="🏎️", layout="centered")
tab1, tab2, tab3, tab4, tab5 = st.tabs(["🏁 **Turnier-Erfassung**", "👤 **Spieler**", "🗺️ **Strecken**", "⚔️ **Head-to-Head**", "📋 **Verlauf**"])

# Sidebar
with st.sidebar:
    st.subheader("🔒 Admin-Bereich")
    if not st.session_state.authenticated:

        # Password prompt
        st.write("**Passwort:**")
        admin_password = st.text_input("Passwort", type="password", label_visibility="collapsed")

        if st.button("Anmelden", type="secondary", width="stretch"):
            if admin_password == st.secrets["passworte"]["admin_passwort"]:
                st.session_state.authenticated = True
                st.success("Anmeldung erfolgreich!")
                time.sleep(2)
                st.rerun()
            else:
                st.error("❌ Falsches Passwort!")
    else:

        # Login successful
        st.success("🔒 Angemeldet als Admin")
        if st.button("Abmelden", type="secondary", width="stretch"):
            st.session_state.authenticated = False
            st.rerun()

# Database Table Initialization
cursor.execute("""
    CREATE TABLE IF NOT EXISTS players (
        id SERIAL PRIMARY KEY, 
        name TEXT NOT NULL UNIQUE
    );
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS tracks (
        id SERIAL PRIMARY KEY, 
        name TEXT NOT NULL UNIQUE, 
        cup TEXT NOT NULL
    );
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS points_mapping (
        placement INTEGER PRIMARY KEY CHECK (placement BETWEEN 1 AND 12), 
        points INTEGER NOT NULL
    );
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS tournaments (
        id SERIAL PRIMARY KEY, 
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS races (
        id SERIAL PRIMARY KEY, 
        tournament_id INTEGER REFERENCES tournaments(id) ON DELETE CASCADE, 
        track_name TEXT REFERENCES tracks(name) ON DELETE RESTRICT, 
        picked_by_name TEXT REFERENCES players(name) ON DELETE SET NULL
    );
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS race_results (
        id SERIAL PRIMARY KEY, 
        race_id INTEGER REFERENCES races(id) ON DELETE CASCADE, 
        player_name TEXT REFERENCES players(name) ON DELETE CASCADE, 
        placement INTEGER REFERENCES points_mapping(placement), 
        UNIQUE (race_id, player_name)
    );
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS tournament_results (
        id SERIAL PRIMARY KEY, 
        tournament_id INTEGER REFERENCES tournaments(id) ON DELETE CASCADE, 
        player_name TEXT REFERENCES players(name) ON DELETE CASCADE, 
        final_placement INTEGER CHECK (final_placement BETWEEN 1 AND 12), 
        beer_finished_after INTEGER, 
        kario INTEGER, 
        UNIQUE (tournament_id, player_name)
    );
""")
conn.commit()

# ==========================================
# 4. SEED DATA
# ==========================================

# Insert Points Mapping and Tracks if not present
cursor.execute("""
    SELECT COUNT(*)
    FROM points_mapping;
""")
if cursor.fetchone()[0] == 0:
    points_data = [(1, 15), (2, 12), (3, 10), (4, 9), (5, 8), (6, 7), (7, 6), (8, 5), (9, 4), (10, 3), (11, 2), (12, 1)]
    cursor.executemany("""
        INSERT INTO points_mapping (placement, points)
        VALUES (%s, %s);
    """, points_data)

    player_data = [("Anja",), ("Pfeiffer",), ("Markus",)]
    cursor.executemany("""
        INSERT INTO players (name)
        VALUES (%s);
    """, player_data)

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
    time.sleep(2)
    st.rerun()

# Retrieve players and tracks in alphabetical order for dropdowns
df_players = pd.read_sql_query("""
    SELECT * 
    FROM players 
    ORDER BY name ASC;
""", conn)

df_tracks = pd.read_sql_query("""
    SELECT * 
    FROM tracks 
    ORDER BY name ASC;
""", conn)


# ==========================================
# TAB 1: TOURNAMENT TRACKING
# ==========================================
with tab1:
    if not st.session_state.authenticated:
        st.warning("🔒 Melde dich in der Sidebar an, um Turniere zu erfassen oder den Verlauf zu editieren.")
    else:

        # Tournament Setup
        if not st.session_state.tournament_active and not st.session_state.waiting_for_final_placement:
            st.write("##### Setup")

            st.write("**Spieler:**")
            selected_names = st.multiselect("Spieler", df_players["name"].tolist(), key="players_tab1", default=["Pfeiffer", "Markus"] if len(df_players) >= 2 else [], label_visibility="collapsed")

            st.write("**Anzahl Rennen:**")
            num_races = st.number_input("Anzahl Rennen", min_value=1, max_value=48, value=4, step=1, label_visibility="collapsed")

            st.write("**Strecken-Auswahlmodus:**")
            selection_mode = st.segmented_control("Strecken-Auswahlmodus", options=["Zufällig", "Auswahl"], default="Zufällig", label_visibility="collapsed")

            st.write("**Spielmodus:**")
            game_mode = st.segmented_control("Spielmodus", options=["Kario", "Mario"], default="Kario", label_visibility="collapsed")

            st.divider()

            if st.button("Starten", type="primary"):
                if len(selected_names) < 2:
                    st.error("❌ Ein Turnier erfordert mindestens 2 Spieler!")
                else:

                    # Set Session States
                    st.session_state.total_races = int(num_races)
                    st.session_state.current_round = 1
                    st.session_state.selection_mode = selection_mode
                    st.session_state.game_mode = game_mode
                    st.session_state.active_players = selected_names
                    st.session_state.tournament_active = True
                    st.rerun()

        # Races
        elif st.session_state.tournament_active and not st.session_state.waiting_for_final_placement:
            st.write("##### Rennplatzierungen")

            active_names = st.session_state.active_players
            all_races_valid = True
            first_invalid_race = None

            # Expander for each races
            for race_num in range(1, st.session_state.total_races + 1):
                should_be_open = (race_num == st.session_state.current_round)

                # Dynamic Expander Title based on current round
                if should_be_open:
                    expander_title = f"🔥 **Rennen {race_num}**"
                elif st.session_state.get("final_check_failed", False):
                    expander_title = f"✅ **Rennen {race_num}**"
                elif race_num < st.session_state.current_round:
                    expander_title = f"✅ **Rennen {race_num}**"
                else:
                    expander_title = f"**Rennen {race_num}**"

                with st.expander(expander_title, expanded=should_be_open):

                    # Track selection
                    all_track_names = df_tracks["name"].tolist()
                    saved_track = st.session_state.backup_races.get(f"track_{race_num}", all_track_names[0])
                    track_index = all_track_names.index(saved_track) if saved_track in all_track_names else 0

                    st.write("**Strecke:**")
                    track_name = st.selectbox("Strecke", all_track_names, index=track_index, key=f"track_{race_num}", label_visibility="collapsed")

                    picked_by_name = None
                    if st.session_state.selection_mode == "Auswahl":
                        saved_picker = st.session_state.backup_races.get(f"picker_{race_num}", active_names[0])
                        picker_index = active_names.index(saved_picker) if saved_picker in active_names else 0

                        st.write("**Gewählt von:**")
                        picked_by_name = st.selectbox("Gewählt von", active_names, index=picker_index, key=f"picker_{race_num}", label_visibility="collapsed")

                    # Head-to-Head Stats for the selected track
                    placeholders = ",".join(["%s"] * len(active_names))
                    query_h2h_track = f"""
                        SELECT 
                            rr.player_name as Spieler, 
                            ROUND(AVG(rr.placement), 2) as "Ø-Platz" 
                        FROM race_results rr 
                        JOIN races r ON rr.race_id = r.id 
                        WHERE r.track_name = %s 
                        AND r.id IN (
                            SELECT race_id 
                            FROM race_results 
                            WHERE player_name IN ({placeholders}) 
                            GROUP BY race_id 
                            HAVING COUNT(DISTINCT player_name) = %s
                        ) 
                        AND rr.player_name IN ({placeholders}) 
                        GROUP BY rr.player_name 
                        ORDER BY AVG(rr.placement) ASC;
                    """
                    params_h2h_track = [track_name] + active_names + [len(active_names)] + active_names
                    df_h2h_track = pd.read_sql_query(query_h2h_track, conn, params=params_h2h_track)

                    if not df_h2h_track.empty:
                        st.write("**Ø-Platz auf dieser Strecke:**")
                        st.dataframe(df_h2h_track, hide_index=True, width="stretch")
                    else:
                        st.info("Keine gemeinsamen Rennen auf dieser Strecke.")

                    st.write("---")

                    # Placements
                    st.write("**Platzierungen:**")
                    placements = {}
                    local_error = False
                    input_error = False
                    duplicate = False

                    for name in active_names:
                        saved_placement = st.session_state.backup_races.get(f"placement_{race_num}_{name}", None)
                        val = ui_placement_selection(name, prefix_key=f"r_{race_num}", default_val=saved_placement)

                        if val in ["doppelt", "fehlt"]:
                            local_error = True
                            input_error = True
                        else:
                            placements[name] = int(val)

                    if not input_error and has_duplicates(list(placements.values())):
                        local_error = True
                        duplicate = True

                    if local_error:
                        all_races_valid = False
                        if first_invalid_race is None:
                            first_invalid_race = race_num

                    # Next Round Button
                    if should_be_open:
                        if race_num < st.session_state.total_races:
                            st.write("---")
                            if st.button(f"Weiter", key=f"btn_next_{race_num}"):
                                if input_error:
                                    st.error("❌ Exakt eine Platzierung pro Spieler wählen!")
                                elif duplicate:
                                    st.error("❌ Doppelte Platzierung!")
                                else:
                                    st.session_state.current_round = race_num + 1
                                    st.rerun()

            st.divider()

            col_save, col_cancel = st.columns([3, 1])
            with col_save:

                # Save Tournament
                if st.button("Speichern", type="primary"):
                    if not all_races_valid:
                        st.error(f"❌ Fehler bei den Platzierungen! Überprüfe Rennen {first_invalid_race}.")
                        st.session_state.current_round = first_invalid_race
                        st.session_state.final_check_failed = True
                        time.sleep(2)
                        st.rerun()
                    else:
                        st.session_state.final_check_failed = False
                        st.session_state.backup_races = {}

                        for race in range(1, st.session_state.total_races + 1):
                            st.session_state.backup_races[f"track_{race}"] = st.session_state[f"track_{race}"]

                            if st.session_state.selection_mode == "Auswahl":
                                st.session_state.backup_races[f"picker_{race}"] = st.session_state[f"picker_{race}"]

                            for name in active_names:
                                p1 = st.session_state.get(f"seg1_r_{race}_{name}")
                                p2 = st.session_state.get(f"seg2_r_{race}_{name}")
                                placement_val = p1 if p1 is not None else p2
                                st.session_state.backup_races[f"placement_{race}_{name}"] = int(placement_val) if placement_val is not None else None

                        st.session_state.tournament_active = False
                        st.session_state.waiting_for_final_placement = True
                        st.rerun()

            with col_cancel:

                # Cancel Tournament Setup
                if st.button("❌ Abbrechen"):
                    st.session_state.backup_races = {}
                    st.session_state.final_check_failed = False
                    st.session_state.tournament_active = False
                    st.session_state.tournament_id = None
                    st.rerun()

        # Final Placements
        elif st.session_state.waiting_for_final_placement:
            st.write("##### Turnier-Endplatzierungen")
            active_names = st.session_state.active_players
            final_placements = {}
            beer_finished = {}
            input_error = False
            input_error_beer = False

            # Calculate total points so far
            points_dict = {name: 0 for name in active_names}
            df_points_map = pd.read_sql_query("""
                SELECT * 
                FROM points_mapping;
            """, conn)

            map_dict = dict(zip(df_points_map["placement"], df_points_map["points"]))

            for race in range(1, st.session_state.total_races + 1):
                for name in active_names:
                    placement = st.session_state.backup_races.get(f"placement_{race}_{name}")
                    if placement in map_dict:
                        points_dict[name] += map_dict[placement]

            # Request Final Placements
            for name in active_names:
                val = ui_placement_selection(name, prefix_key="fp", custom_title=f"**{name}** ({points_dict[name]} Punkte)**:**")
                if val in ["doppelt", "fehlt"]:
                    input_error = True
                else:
                    final_placements[name] = int(val)

            # Request Kario specific settings
            if st.session_state.game_mode == "Kario":
                st.write("---")
                st.write("##### Bier")

                for name in active_names:
                    st.write(f"**{name}:**")
                    beer_options = list(range(1, st.session_state.total_races + 1))
                    beer_options.append("❌")
                    beer_val = st.segmented_control(f"Beer_{name}", options=beer_options, key=f"beer_fp_{name}", label_visibility="collapsed")

                    if beer_val is None:
                        input_error_beer = True
                    else:
                        if beer_val == "❌":
                            beer_finished[name] = "❌"
                        else:
                            beer_finished[name] = int(beer_val)

            st.divider()

            col1, col2 = st.columns([3, 1])
            with col1:

                # Complete Tournament Button
                if st.button("Abschließen", type="primary"):
                    if input_error:
                        st.error("❌ Exakt eine Platzierung pro Spieler wählen!")
                    elif st.session_state.game_mode == "Kario" and input_error_beer:
                        st.error("❌ Für alle Spieler angeben, wann das Bier geleert wurde!")
                    else:
                        cur = conn.cursor()
                        if "❌" in list(beer_finished.values()):
                            st.error("⚠️ Bier nicht geleert, Endplatzierung wird auf 12 gesetzt!")

                        # Save new tournament in DB
                        berlin_tz = ZoneInfo("Europe/Berlin")
                        current_timestamp = datetime.now(tz=berlin_tz).strftime("%Y-%m-%d %H:%M:%S")

                        cur.execute("""
                            INSERT INTO tournaments (date) 
                            VALUES (%s)
                            RETURNING id;
                        """, (current_timestamp,))
                        st.session_state.tournament_id = cur.fetchone()[0]

                        for race_num in range(1, st.session_state.total_races + 1):
                            saved_track = st.session_state.backup_races[f"track_{race_num}"]
                            saved_picker = st.session_state.backup_races.get(f"picker_{race_num}", None)

                            cur.execute("""
                                INSERT INTO races (tournament_id, track_name, picked_by_name) 
                                VALUES (%s, %s, %s)
                                RETURNING id;
                            """, (st.session_state.tournament_id, saved_track, saved_picker))
                            race_id = cur.fetchone()[0]

                            for name in active_names:
                                placement = st.session_state.backup_races[f"placement_{race_num}_{name}"]
                                cur.execute("""
                                    INSERT INTO race_results (race_id, player_name, placement) 
                                    VALUES (%s, %s, %s);
                                """, (race_id, name, int(placement)))

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

                        st.session_state.backup_races = {}
                        st.session_state.waiting_for_final_placement = False
                        st.session_state.tournament_id = None
                        time.sleep(2)
                        st.rerun()

            with col2:

                # Back Button
                if st.button("Zurück"):
                    st.session_state.waiting_for_final_placement = False
                    st.session_state.tournament_active = True
                    st.session_state.current_round = st.session_state.total_races + 1
                    st.session_state.final_check_failed = False
                    st.rerun()

                # Cancel Button
                if st.button("Abbrechen"):
                    st.session_state.waiting_for_final_placement = False
                    st.session_state.tournament_id = None
                    st.rerun()

# ==========================================
# TAB 2: PLAYER PROFILES & MANAGEMENT
# ==========================================
with tab2:
    with st.expander("👤 **Verwaltung Spieler-Datenbank**"):
        if not st.session_state.authenticated:
            st.warning("🔒 Melde dich an.")
        else:
            col_add, col_del = st.columns(2)

            with col_add:
                st.write("**Neuer Spieler:**")
                new_name = st.text_input("Neuer Spieler", label_visibility="collapsed")
                if st.button("Hinzufügen", type="primary"):
                    if new_name.strip():
                        try:
                            cur = conn.cursor()
                            cur.execute("""
                                INSERT INTO players (name) 
                                VALUES (%s);
                            """, (new_name.strip(),))
                            conn.commit()
                            st.success(f"{new_name} hinzugefügt!")
                            time.sleep(2)
                            st.rerun()
                        except psycopg2.IntegrityError:
                            st.error("❌ Name existiert bereits!")

            with col_del:
                if not df_players.empty:
                    st.write("**Löschen:**")
                    delete_name = st.selectbox("Löschen", df_players["name"].tolist(), label_visibility="collapsed")

                    if st.session_state.get("confirm_delete_player") != delete_name:
                        if st.button("Löschen", type="secondary"):
                            st.session_state.confirm_delete_player = delete_name
                            st.rerun()
                    else:
                        st.error(f"⚠️ **{delete_name}** unwiderruflich löschen%s")
                        c_conf1, c_conf2 = st.columns(2)

                        with c_conf1:
                            if st.button("Löschen", type="primary", width="stretch"):
                                cur = conn.cursor()
                                cur.execute("""
                                    DELETE FROM players 
                                    WHERE name = %s;
                                """, (delete_name,))
                                conn.commit()
                                st.error(f"{delete_name} gelöscht!")
                                st.session_state.confirm_delete_player = None
                                time.sleep(2)
                                st.rerun()

                        with c_conf2:
                            if st.button("Abbrechen", width="stretch"):
                                st.session_state.confirm_delete_player = None
                                st.rerun()

    st.divider()

    st.write("##### Spieler-Statistiken")
    if not df_players.empty:
        st.write("**Spieler:**")
        profile_name = st.selectbox("Spieler", df_players["name"].tolist(), label_visibility="collapsed")

        # Segmented Control for Filtering (Overall / Kario / Mario)
        t2_mode = st.segmented_control("Statistiken filtern", options=["Gesamt", "Kario", "Mario"], default="Gesamt", key="t2_mode", label_visibility="collapsed")

        # Kario Filter Conditions
        kario_cond = ""
        kario_cond_tr2 = ""
        if t2_mode == "Kario":
            kario_cond = " AND tr.kario = 1"
            kario_cond_tr2 = " AND tr2.kario = 1"
        elif t2_mode == "Mario":
            kario_cond = " AND tr.kario = 0"
            kario_cond_tr2 = " AND tr2.kario = 0"

        # Race Metrics
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
            WHERE rr.player_name = %s {kario_cond};
        """
        df_races = pd.read_sql_query(query_races, conn, params=(profile_name,))
        race_stats = df_races.iloc[0]

        # Tournament Metrics
        query_tournaments = f"""
            SELECT 
                COUNT(DISTINCT tr.tournament_id) as total_tournaments,
                AVG(tr.final_placement) as avg_tournament_placement,
                SUM(CASE WHEN tr.final_placement = 1 THEN 1 ELSE 0 END) as tournament_wins,
                AVG(tr.beer_finished_after) as avg_beer_finished_after
            FROM tournament_results tr 
            WHERE tr.player_name = %s {kario_cond};
        """
        df_tournaments = pd.read_sql_query(query_tournaments, conn, params=(profile_name,))
        tournament_stats = df_tournaments.iloc[0]

        # Rankings
        query_best = f"""
            SELECT 
                r.track_name as "Strecke", 
                COUNT(rr.id) as "Gefahren", 
                ROUND(AVG(rr.placement), 2) as "Ø-Platz" 
            FROM race_results rr 
            JOIN races r ON rr.race_id = r.id 
            JOIN tournament_results tr ON r.tournament_id = tr.tournament_id AND rr.player_name = tr.player_name 
            WHERE rr.player_name = %s {kario_cond} 
            GROUP BY r.track_name 
            ORDER BY AVG(rr.placement) ASC 
            LIMIT 5;
        """
        df_best_tracks = pd.read_sql_query(query_best, conn, params=(profile_name,))

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
                    AND rr2.player_name = %s {kario_cond_tr2}
                ), 2) as "Ø-Platz" 
            FROM races r 
            JOIN tournament_results tr ON r.tournament_id = tr.tournament_id AND tr.player_name = r.picked_by_name 
            WHERE r.picked_by_name = %s {kario_cond} 
            GROUP BY r.track_name 
            ORDER BY COUNT(r.id) DESC, r.track_name ASC 
            LIMIT 5;
        """
        df_favorite_tracks = pd.read_sql_query(query_favorites, conn, params=(profile_name, profile_name))

        # Formatting
        st.markdown("""
            <style>
                [data-testid="stMetricLabel"], 
                [data-testid="stMetricLabel"] * {
                    white-space: pre-wrap !important;
                }
            </style>
        """, unsafe_allow_html=True)

        if pd.notnull(race_stats["total_races"]) and race_stats["total_races"] > 0:
            total_pts = race_stats["total_points"] or 0
            total_races = race_stats["total_races"] or 1
            normalized_points = (total_pts / total_races) * 4

            # Metrics UI Display
            m_col1, m_col2, m_col3, m_col4 = st.columns(4)
            with m_col1:
                st.metric("**Ø-Platz Rennen**", f"{race_stats['avg_race_placement']:.2f}")
                st.metric("**Ø-Platz Rennen\n(w.s.g.)**", f"{race_stats['avg_race_placement_picked']:.2f}" if pd.notnull(race_stats['avg_race_placement_picked']) else "N/A")
                st.metric("**Ø-Platz Turnier**", f"{tournament_stats['avg_tournament_placement']:.2f}" if pd.notnull(tournament_stats['avg_tournament_placement']) else "N/A")
            with m_col2:
                st.metric("**Ø-Punkte / Rennen**", f"{race_stats['avg_race_points']:.2f}")
                st.metric("**Ø-Punkte / Turnier\n(4 R.)**", f"{normalized_points:.2f}")
                st.metric("**Ø-Rennen / Bier**", f"{tournament_stats['avg_beer_finished_after']:.2f}" if pd.notnull(tournament_stats['avg_beer_finished_after']) else "N/A")
            with m_col3:
                st.metric("**Rennsiege**", f"{int(race_stats['race_wins'] or 0)}")
                st.metric("**Turniersiege**", f"{int(tournament_stats['tournament_wins'] or 0)}")
            with m_col4:
                st.metric("**Rennen**", f"{int(total_races)}")
                st.metric("**Turniere**", f"{int(tournament_stats['total_tournaments'] or 0)}")

            st.divider()

            # Ranking Display
            st.write("##### 🏆 Ranglisten")
            t_col1, t_col2 = st.columns(2)
            with t_col1:
                st.write("**🔝 Beste Strecken**")
                st.dataframe(df_best_tracks, hide_index=True, width="stretch")
            with t_col2:
                st.write("**❤️ Lieblingsstrecken**")
                st.dataframe(df_favorite_tracks, hide_index=True, width="stretch")
        else:
            st.info("Keine Renndaten für diesen Spieler.")

# ==========================================
# TAB 3: TRACKS DATABASE
# ==========================================
with tab3:
    st.write("##### Strecken-Statistiken")
    st.write("**Strecke:**")
    selected_track = st.selectbox("Strecke", df_tracks["name"].tolist(), label_visibility="collapsed")

    df_play_count = pd.read_sql_query("""
        SELECT COUNT(*) as count 
        FROM races 
        WHERE track_name = %s;
    """, conn, params=(selected_track,))

    df_most_picked = pd.read_sql_query("""
        SELECT picked_by_name as name, COUNT(*) as c 
        FROM races 
        WHERE track_name = %s 
        AND picked_by_name IS NOT NULL 
        GROUP BY picked_by_name 
        ORDER BY c DESC 
        LIMIT 1;
    """, conn, params=(selected_track,))

    st.write(f"**Wie oft gespielt:** {df_play_count['count'].values[0]}x")
    st.write(f"**Am öftesten gewählt von:** {str(df_most_picked['name'].values[0]) + ' (' + str(df_most_picked['c'].values[0]) + 'x)' if not df_most_picked.empty else 'Niemandem'}")

    st.divider()
    st.write("##### 🏆 Ranglisten")

    query_wins = """
        SELECT player_name as Spieler, COUNT(*) as Rennsiege 
        FROM race_results rr 
        JOIN races r ON rr.race_id = r.id 
        WHERE r.track_name = %s 
        AND rr.placement = 1 
        GROUP BY player_name 
        ORDER BY Rennsiege DESC;
    """

    query_placement = """
        SELECT player_name as Spieler, AVG(rr.placement) as "Ø-Platz" 
        FROM race_results rr 
        JOIN races r ON rr.race_id = r.id 
        WHERE r.track_name = %s 
        GROUP BY player_name 
        ORDER BY "Ø-Platz" ASC;
    """

    query_points = """
        SELECT player_name as Spieler, AVG(pm.points) as "Ø-Punkte" 
        FROM race_results rr 
        JOIN races r ON rr.race_id = r.id 
        JOIN points_mapping pm ON rr.placement = pm.placement 
        WHERE r.track_name = %s 
        GROUP BY player_name 
        ORDER BY "Ø-Punkte" DESC;
    """

    rl1, rl2, rl3 = st.columns(3)
    with rl1:
        st.write("**Nach Ø-Platz**")
        st.dataframe(pd.read_sql_query(query_placement, conn, params=(selected_track,)), hide_index=True, width="stretch")
    with rl2:
        st.write("**Nach Ø-Punkten**")
        st.dataframe(pd.read_sql_query(query_points, conn, params=(selected_track,)), hide_index=True, width="stretch")
    with rl3:
        st.write("**Nach Anzahl Siegen**")
        st.dataframe(pd.read_sql_query(query_wins, conn, params=(selected_track,)), hide_index=True, width="stretch")

# ==========================================
# TAB 4: HEAD-TO-HEAD
# ==========================================
with tab4:
    st.write("##### Rivalen-Vergleich")
    st.write("**Spieler:**")
    rivals = st.multiselect("Spieler", df_players["name"].tolist(), key="players_tab4", default=["Pfeiffer", "Markus"] if len(df_players) >= 2 else [], label_visibility="collapsed")

    if len(rivals) >= 2:
        h2h_placeholders = ",".join(["%s"] * len(rivals))

        st.write("**Filterung nach Strecke:**")
        h2h_track = st.selectbox("Filterung nach Strecke", ["Alle Strecken"] + df_tracks["name"].tolist(), label_visibility="collapsed")

        # Segmented Control for Filtering (Overall / Kario / Mario)
        h2h_mode = st.segmented_control("Modus filtern", options=["Gesamt", "Kario", "Mario"], default="Gesamt", key="h2h_mode", label_visibility="collapsed")

        h2h_kario_cond = ""
        if h2h_mode == "Kario":
            h2h_kario_cond = " AND tr.kario = 1"
        elif h2h_mode == "Mario":
            h2h_kario_cond = " AND tr.kario = 0"

        subquery_shared = f"""
            SELECT r.tournament_id 
            FROM race_results rr 
            JOIN races r ON rr.race_id = r.id 
            WHERE rr.player_name IN ({h2h_placeholders}) 
            GROUP BY r.tournament_id 
            HAVING COUNT(DISTINCT rr.player_name) = %s
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
            {track_condition} {h2h_kario_cond};
        """

        params_h2h_r = rivals + [len(rivals)] + rivals
        if h2h_track != "Alle Strecken":
            params_h2h_r.append(h2h_track)

        df_h2h_r = pd.read_sql_query(query_h2h_r, conn, params=params_h2h_r)

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

        params_h2h_t = rivals + [len(rivals)] + rivals
        df_h2h_t = pd.read_sql_query(query_h2h_t, conn, params=params_h2h_t)

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
                    st.info("Turnier-Metriken bei Streckenfilter ausgeblendet.")

# ==========================================
# TAB 5: HISTORY & EDITING
# ==========================================
with tab5:
    st.write("##### Turnierverlauf")

    df_history = pd.read_sql_query("""
        SELECT 
            t.id as "Turnier-ID", 
            t.date as "Datum", 
            STRING_AGG(tr.player_name, ', ') as "Teilnehmer" 
        FROM tournaments t 
        JOIN tournament_results tr ON t.id = tr.tournament_id 
        GROUP BY t.id, t.date 
        ORDER BY t.id DESC;
    """, conn)

    if df_history.empty:
        st.info("Keine Turniere gespeichert.")
    else:
        st.dataframe(df_history, width="stretch", hide_index=True)
        st.divider()

        if not st.session_state.authenticated:
            st.warning("🔒 Melde dich an.")
        else:
            st.write("##### Bearbeiten")
            st.write("**Turnier-ID:**")
            selected_tournament_id = st.selectbox("Turnier-ID zum Bearbeiten", df_history['Turnier-ID'].tolist(), key="select_edit_id", label_visibility="collapsed")

            st.divider()

            if selected_tournament_id:
                st.write("##### Turnier-Endplatzierungen")
                df_current_placements = pd.read_sql_query("""
                    SELECT player_name, final_placement 
                    FROM tournament_results 
                    WHERE tournament_id = %s;
                """, conn, params=(selected_tournament_id,))

                df_current_points = pd.read_sql_query("""
                    SELECT rr.player_name, SUM(pm.points) as total_points 
                    FROM race_results rr 
                    JOIN races r ON rr.race_id = r.id 
                    JOIN points_mapping pm ON rr.placement = pm.placement 
                    WHERE r.tournament_id = %s 
                    GROUP BY rr.player_name;
                """, conn, params=(selected_tournament_id,))

                current_points_dict = dict(zip(df_current_points["player_name"], df_current_points["total_points"]))

                edited_final_placements = {}
                input_error_fp = False

                for _, row in df_current_placements.iterrows():
                    val = ui_placement_selection(row['player_name'], prefix_key=f"edit_fp_{selected_tournament_id}", custom_title=f"**{row['player_name']}** ({current_points_dict.get(row['player_name'], 0)} Punkte)**:**", default_val=int(row['final_placement']))
                    if val in ["doppelt", "fehlt"]:
                        input_error_fp = True
                    else:
                        edited_final_placements[row['player_name']] = int(val)

                if st.button("Aktualisieren", type="primary", key="races_update"):
                    if input_error_fp:
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
                        time.sleep(2)
                        st.rerun()

                # Kario Logic
                df_current_beer = pd.read_sql_query("""
                    SELECT player_name, beer_finished_after, kario 
                    FROM tournament_results 
                    WHERE tournament_id = %s;
                """, conn, params=(selected_tournament_id,))

                kario = (df_current_beer['kario'] == 1).any()
                if kario:
                    st.divider()
                    st.write("##### Bier")

                    cur = conn.cursor()
                    cur.execute("""
                        SELECT COUNT(*) 
                        FROM races 
                        WHERE tournament_id = %s;
                    """, (selected_tournament_id,))

                    num_races_in_tournament = cur.fetchone()[0] or 1
                    beer_options = list(range(1, num_races_in_tournament + 1))
                    beer_options.append("❌")

                    edited_beer = {}
                    input_error_b_fp = False

                    for _, row in df_current_beer.iterrows():
                        st.write(f"**{row['player_name']}:**")
                        beer_default = "❌"
                        if not isnan(row["beer_finished_after"]):
                            beer_default = row["beer_finished_after"]

                        beer_val = st.segmented_control(f"Beer_{row['player_name']}",
                                                     options=beer_options,
                                                     key=f"edit_beer_fp_{selected_tournament_id}_{row['player_name']}",
                                                     label_visibility="collapsed",
                                                     default=beer_default)
                        if beer_val is None:
                            input_error_b_fp = True
                        else:
                            if beer_val == "❌":
                                edited_beer[row['player_name']] = "❌"
                            else:
                                edited_beer[row['player_name']] = int(beer_val)

                    if st.button("Aktualisieren", type="primary", key="beer_update"):
                        if input_error_b_fp:
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
                st.write("##### Rennergebnisse")
                df_race_list = pd.read_sql_query("""
                    SELECT id as race_id, track_name 
                    FROM races 
                    WHERE tournament_id = %s;
                """, conn, params=(selected_tournament_id,))

                for idx, r_row in df_race_list.iterrows():
                    race_id = int(r_row['race_id'])
                    with st.expander(f"**Rennen {idx + 1}** (ID #{race_id})**:** {r_row['track_name']}"):
                        cur = conn.cursor()
                        cur.execute("""
                            SELECT track_name, picked_by_name 
                            FROM races 
                            WHERE id = %s;
                        """, (race_id,))
                        curr_race = cur.fetchone()

                        all_track_names = df_tracks["name"].tolist()
                        curr_track_name = curr_race[0]
                        picker_name_db = curr_race[1]

                        st.write("**")