import os
import time
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st
from streamlit_scroll_to_top import scroll_to_here
from streamlit_gsheets import GSheetsConnection
from math import isnan

# ==========================================
# 1. INITIALISIERUNG & CONFIG
# ==========================================

st.set_page_config(page_title="Kario Mart Dashboard", page_icon="🏎️", layout="centered")
st.write("### Kario Mart Dashboard")

# Passwort-Schutz
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# Sidebar
with st.sidebar:
    st.subheader("🔒 Admin-Bereich")
    if not st.session_state.authenticated:
        st.write("**Passwort:**")
        passwort = st.text_input("Passwort", type="password", label_visibility="collapsed")
        if st.button("Anmelden"):
            if passwort == st.secrets["passworte"]["admin_passwort"]:
                st.session_state.authenticated = True
                st.success("Erfolgreich angemeldet!")
                time.sleep(1.5)
                st.rerun()
            else:
                st.error("❌ Falsches Passwort!")
    else:
        st.success("🔒 Angemeldet als Admin")
        if st.button("Abmelden"):
            st.session_state.authenticated = False
            st.rerun()

sheets_conn = st.connection("gsheets", type=GSheetsConnection)

# Lokale .db Datei als Cache
DB_FILE = "kario_mart_cache.db"

# Lösche alten Cache falls vorhanden
if "session_initialized" not in st.session_state:
    if os.path.exists(DB_FILE):
        try:
            os.remove(DB_FILE)
        except Exception as e:
            st.warning("Alter Cache konnte nicht gelöscht werden.")
    st.session_state.session_initialized = True

conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cursor = conn.cursor()

cursor.execute("PRAGMA foreign_keys = ON;")

cursor.execute("CREATE TABLE IF NOT EXISTS spieler (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE);")

cursor.execute("CREATE TABLE IF NOT EXISTS strecken (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, cup TEXT NOT NULL);")

cursor.execute("CREATE TABLE IF NOT EXISTS punkte_mapping (platzierung INTEGER PRIMARY KEY CHECK (platzierung BETWEEN 1 AND 12), punkte INTEGER NOT NULL);")

cursor.execute("CREATE TABLE IF NOT EXISTS turniere (id INTEGER PRIMARY KEY AUTOINCREMENT, datum TIMESTAMP DEFAULT CURRENT_TIMESTAMP);")

cursor.execute("CREATE TABLE IF NOT EXISTS rennen (id INTEGER PRIMARY KEY AUTOINCREMENT, turnier_id INTEGER REFERENCES turniere(id) ON DELETE CASCADE, strecken_name TEXT REFERENCES strecken(name) ON DELETE RESTRICT, gewaehlt_von_name TEXT REFERENCES spieler(name) ON DELETE SET NULL);")

cursor.execute("CREATE TABLE IF NOT EXISTS renn_ergebnisse (id INTEGER PRIMARY KEY AUTOINCREMENT, rennen_id INTEGER REFERENCES rennen(id) ON DELETE CASCADE, spieler_name TEXT REFERENCES spieler(name) ON DELETE CASCADE, platzierung INTEGER REFERENCES punkte_mapping(platzierung), UNIQUE (rennen_id, spieler_name));")

cursor.execute("CREATE TABLE IF NOT EXISTS turnier_ergebnisse (id INTEGER PRIMARY KEY AUTOINCREMENT, turnier_id INTEGER REFERENCES turniere(id) ON DELETE CASCADE, spieler_name TEXT REFERENCES spieler(name) ON DELETE CASCADE, endplatzierung INTEGER CHECK (endplatzierung BETWEEN 1 AND 12), bier_finished_nach INTEGER, UNIQUE (turnier_id, spieler_name));")

# Fügt Bier Spalte hinzu, falls noch nicht vorhanden
try:
    cursor.execute("ALTER TABLE turnier_ergebnisse ADD COLUMN bier_finished_nach INTEGER;")
except sqlite3.OperationalError:
    pass  # Spalte existiert bereits

conn.commit()

ALL_TABLES = ["spieler", "strecken", "punkte_mapping", "turniere", "rennen", "renn_ergebnisse", "turnier_ergebnisse"]

# ==========================================
# 2. CLOUD SYNC
# ==========================================

# State für API-Cooldown
if "last_sync" not in st.session_state: 
    st.session_state.last_sync = 0

def lade_aus_cloud():
    """Holt die frischen Daten aus Google Sheets, wenn der Server neu aufwacht."""
    with st.spinner("☁️ Lade aktuellen Spielstand aus der Cloud..."):
        for tabelle in ALL_TABLES:
            try:
                df_sheet = sheets_conn.read(worksheet=tabelle, ttl=0)
                if df_sheet is not None and not df_sheet.empty:
                    df_sheet.to_sql(tabelle, conn, if_exists="append", index=False)
            except Exception:
                pass

def speichere_in_cloud(force=False, tabellen=None):
    """Schiebt die lokale Datenbank zu Google Sheets hoch."""
    if tabellen is None:
        tabellen = ALL_TABLES
    now = time.time()
    if not force and (now - st.session_state.last_sync < 10):
        st.warning("Nicht gespeichert, um Cloud nicht zu überlasten. Versuche in wenigen Sekunden einen manuellen Sync.")
        time.sleep(1.5)
        return

    with st.spinner("💾 Speichere Daten in der Cloud..."):
        for tabelle in tabellen:
            try:
                df_sync = pd.read_sql_query(f"SELECT * FROM {tabelle};", conn)
                sheets_conn.update(worksheet=tabelle, data=df_sync)
            except Exception:
                st.error("❌ Cloud überlastet, versuche in wenigen Sekunden einen manuellen Sync!")
        st.success("Cloud-Sync erfolgreich!")
        st.session_state.last_sync = time.time()
        
# Cloud-Speicher-Button in der Sidebar
if st.session_state.authenticated:
    with st.sidebar:
        st.divider()
        st.subheader("☁️ Cloud-Synchronisation")
        if st.button("💾 Speichern", type="primary"):
            speichere_in_cloud(force=True)

# ==========================================
# 3. SEED-DATEN & SESSION-STATES
# ========================================== 
cursor.execute("SELECT COUNT(*) FROM spieler;")
if cursor.fetchone()[0] == 0:
    lade_aus_cloud()    
    cursor.execute("SELECT COUNT(*) FROM spieler;")
    
    if cursor.fetchone()[0] == 0:
        punkte_daten = [(1, 15), (2, 12), (3, 10), (4, 9), (5, 8), (6, 7), (7, 6), (8, 5), (9, 4), (10, 3), (11, 2), (12, 1)]
        cursor.executemany("INSERT OR IGNORE INTO punkte_mapping (platzierung, punkte) VALUES (?, ?);", punkte_daten)
        
        spieler_daten = [("Anja",), ("Pfeiffer",), ("Markus",)]
        cursor.executemany("INSERT OR IGNORE INTO spieler (name) VALUES (?);", spieler_daten)
        
        strecken_daten = [
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
        cursor.executemany("INSERT OR IGNORE INTO strecken (name, cup) VALUES (?, ?);", strecken_daten)
        conn.commit()
        speichere_in_cloud(force=True, tabellen=["spieler", "strecken", "punkte_mapping"])
        st.rerun()

# Stammdaten für Selectboxen
df_spieler = pd.read_sql_query("SELECT * FROM spieler ORDER BY name ASC;", conn)

df_strecken = pd.read_sql_query("SELECT * FROM strecken ORDER BY name ASC;", conn)

# Session States
if "turnier_aktiv" not in st.session_state: st.session_state.turnier_aktiv = False
if "aktuelle_runde" not in st.session_state: st.session_state.aktuelle_runde = 1
if "gesamt_rennen" not in st.session_state: st.session_state.gesamt_rennen = 4
if "turnier_id" not in st.session_state: st.session_state.turnier_id = None
if "aktive_spieler_namen" not in st.session_state: st.session_state.aktive_spieler_namen = []
if "wahl_modus" not in st.session_state: st.session_state.wahl_modus = "Zufällig"
if "spielmodus" not in st.session_state: st.session_state.spielmodus = "Kario"
if "warten_auf_endplatzierung" not in st.session_state: st.session_state.warten_auf_endplatzierung = False
if "scroll_to_top" not in st.session_state: st.session_state.scroll_to_top = False

# ==========================================
# 4. HILFSFUNKTIONEN
# ==========================================
def hat_duplikate(liste):
    """Prüft auf Duplikate."""
    return len(liste) != len(set(liste))

def ui_platzierung_auswahl(name, prefix_key, default_val=None, custom_title=None):
    """Erzeugt zwei 1x6 Segmented Controls und validiert die Eingabe."""
    title = custom_title if custom_title else f"**{name}:**"
    st.write(title)
    
    d1 = default_val if default_val in [1, 2, 3, 4, 5, 6] else None
    d2 = default_val if default_val in [7, 8, 9, 10, 11, 12] else None
    
    p1 = st.segmented_control("Platz 1-6", options=[1, 2, 3, 4, 5, 6], default=d1, key=f"seg1_{prefix_key}_{name}", label_visibility="collapsed")
    p2 = st.segmented_control("Platz 7-12", options=[7, 8, 9, 10, 11, 12], default=d2, key=f"seg2_{prefix_key}_{name}", label_visibility="collapsed")
    
    st.write("") 
    
    if (p1 is not None) and (p2 is not None):
        return "doppelt" 
    if (p1 is None) and (p2 is None):
        return "fehlt"   
    return p1 if p1 is not None else p2

# Scroll
if st.session_state.scroll_to_top:
    scroll_to_here(0, key='top')
    st.session_state.scroll_to_top = False

tab1, tab2, tab3, tab4, tab5 = st.tabs(["🏁 Turnier-Erfassung", "👤 Spieler", "🗺️ Strecken", "⚔️ Head-to-Head", "📋 Verlauf"])

# ==========================================
# TAB 1: TURNIER-ERFASSUNG
# ==========================================
with tab1:
    if not st.session_state.authenticated:
        st.warning("🔒 Melde dich in der Sidebar an, um Turniere zu erfassen oder den Verlauf zu editieren.")
    else:
        # Neues Turnier
        if not st.session_state.turnier_aktiv and not st.session_state.warten_auf_endplatzierung:
            st.write("#### Neues Turnier")
            
            st.write("**Spieler:**")
            ausgewaehlte_namen = st.multiselect("Spieler", df_spieler["name"].tolist(), key="spieler_tab1", default=["Pfeiffer", "Markus"] if len(df_spieler) >= 2 else [], label_visibility="collapsed")
            
            st.write("**Anzahl Rennen:**")
            anzahl_rennen = st.number_input("Anzahl Rennen", min_value=1, max_value=48, value=4, step=1, label_visibility="collapsed")
            
            st.write("**Strecken-Auswahlmodus:**")
            wahl_modus = st.segmented_control("Strecken-Auswahlmodus", options=["Zufällig", "Auswahl"], default="Zufällig", label_visibility="collapsed")

            st.write("**Spielmodus:**")
            spielmodus = st.segmented_control("Spielmodus", options=["Kario", "Mario"], default="Kario", label_visibility="collapsed")

            st.divider()

            if st.button("Starten", type="primary"):
                if len(ausgewaehlte_namen) < 2:
                    st.error("❌ Ein Turnier erfordert mindestens 2 Spieler!")
                else:
                    berlin_tz = ZoneInfo("Europe/Berlin")
                    aktueller_timestamp = datetime.now(tz=berlin_tz).strftime("%Y-%m-%d %H:%M:%S")

                    c = conn.cursor()
                    c.execute("INSERT INTO turniere (datum) VALUES (?);", (aktueller_timestamp,))
                    st.session_state.turnier_id = c.lastrowid
                    conn.commit()

                    st.session_state.gesamt_rennen = int(anzahl_rennen)
                    st.session_state.aktuelle_runde = 1
                    st.session_state.wahl_modus = wahl_modus
                    st.session_state.spielmodus = spielmodus
                    st.session_state.aktive_spieler_namen = ausgewaehlte_namen
                    st.session_state.turnier_aktiv = True
                    st.rerun()

        # Rennen
        elif st.session_state.turnier_aktiv and not st.session_state.warten_auf_endplatzierung:

            progress_float = st.session_state.aktuelle_runde / st.session_state.gesamt_rennen
            st.write(f"#### Rennen {st.session_state.aktuelle_runde} von {st.session_state.gesamt_rennen}")
            st.progress(progress_float)             

            aktive_namen = st.session_state.aktive_spieler_namen
            
            st.write("**Strecke:**")
            strecke_name = st.selectbox("Strecke", df_strecken["name"].tolist(), key=f"track_{st.session_state.aktuelle_runde}", label_visibility="collapsed")

            wer_gewaehlt_name = None
            if st.session_state.wahl_modus == "Auswahl":
                st.write("**Gewählt von:**")
                wer_gewaehlt_name = st.selectbox("Gewählt von", aktive_namen, key=f"picker_{st.session_state.aktuelle_runde}", label_visibility="collapsed")

            # H2H Durchschnittsplatzierung auf dieser Strecke
            formatted_names = ",".join([f"'{n}'" for n in aktive_namen])
            names_str = f"({formatted_names})"
            
            df_h2h_track = pd.read_sql_query(f"SELECT re.spieler_name as Spieler, ROUND(AVG(re.platzierung), 2) as 'Ø-Platz' FROM renn_ergebnisse re JOIN rennen r ON re.rennen_id = r.id WHERE r.strecken_name = '{strecke_name}' AND r.id IN (SELECT rennen_id FROM renn_ergebnisse WHERE spieler_name IN {names_str} GROUP BY rennen_id HAVING COUNT(DISTINCT spieler_name) = {len(aktive_namen)}) AND re.spieler_name IN {names_str} GROUP BY re.spieler_name ORDER BY AVG(re.platzierung) ASC;", conn)
            
            if not df_h2h_track.empty:
                st.write("**Ø-Platz auf dieser Strecke:**")
                st.dataframe(df_h2h_track, hide_index=True, width='stretch')
            else:
                st.info("Noch keine gemeinsamen Rennen auf dieser Strecke.")

            st.divider()

            st.write("#### Platzierungen")
            platzierungen = {}
            eingabe_fehler = False

            for name in aktive_namen:
                val = ui_platzierung_auswahl(name, prefix_key=f"r_{st.session_state.aktuelle_runde}")
                if val in ["doppelt", "fehlt"]:
                    eingabe_fehler = True
                else:
                    platzierungen[name] = int(val)

            st.divider()

            col1, col2 = st.columns([3, 1])
            with col1:
                if st.button("Speichern", type="primary"):
                    if eingabe_fehler:
                        st.error("❌ Exakt eine Platzierung pro Spieler wählen!")
                    elif hat_duplikate(list(platzierungen.values())):
                        st.error("❌ Doppelte Platzierung!")
                    else:
                        c = conn.cursor()
                        c.execute("INSERT INTO rennen (turnier_id, strecken_name, gewaehlt_von_name) VALUES (?, ?, ?);", (st.session_state.turnier_id, strecke_name, wer_gewaehlt_name))
                        r_id = c.lastrowid
                        
                        for s_name, platz in platzierungen.items():
                            c.execute("INSERT INTO renn_ergebnisse (rennen_id, spieler_name, platzierung) VALUES (?, ?, ?);", (r_id, s_name, platz))
                        conn.commit()

                        if st.session_state.aktuelle_runde >= st.session_state.gesamt_rennen:
                            st.session_state.turnier_aktiv = False
                            st.session_state.warten_auf_endplatzierung = True
                        else:
                            st.session_state.aktuelle_runde += 1
                        st.session_state.scroll_to_top = True
                        st.rerun()
            with col2:
                if st.button("Zurück"):
                    if st.session_state.aktuelle_runde > 1:
                        c = conn.cursor()
                        c.execute("SELECT MAX(id) FROM rennen WHERE turnier_id = ?;", (st.session_state.turnier_id,))
                        last_race_id = c.fetchone()[0]
                        if last_race_id:
                            c.execute("DELETE FROM rennen WHERE id = ?;", (last_race_id,))
                            conn.commit()
                            st.session_state.aktuelle_runde -= 1
                            st.session_state.scroll_to_top = True
                            st.rerun()
                    else:
                        c = conn.cursor()
                        c.execute("DELETE FROM turniere WHERE id = ?;", (st.session_state.turnier_id,))
                        conn.commit()
                        st.session_state.turnier_aktiv = False
                        st.session_state.turnier_id = None
                        st.session_state.scroll_to_top = True
                        st.rerun()
                if st.button("Abbrechen"):
                    c = conn.cursor()
                    c.execute("DELETE FROM turniere WHERE id = ?;", (st.session_state.turnier_id,))
                    conn.commit()
                    st.session_state.turnier_aktiv = False
                    st.session_state.turnier_id = None
                    st.session_state.scroll_to_top = True
                    st.rerun()

        # Endplatzierungen
        elif st.session_state.warten_auf_endplatzierung:

            st.write("#### Turnier-Endplatzierungen")
            aktive_namen = st.session_state.aktive_spieler_namen

            df_punkte = pd.read_sql_query(f"SELECT re.spieler_name, SUM(m.punkte) as total_punkte FROM renn_ergebnisse re JOIN rennen r ON re.rennen_id = r.id JOIN punkte_mapping m ON re.platzierung = m.platzierung WHERE r.turnier_id = {st.session_state.turnier_id} GROUP BY re.spieler_name;", conn)
            punkte_dict = dict(zip(df_punkte["spieler_name"], df_punkte["total_punkte"]))

            end_platzierungen = {}
            bier_finished = {}
            eingabe_fehler = False
            eingabe_fehler_bier = False

            for name in aktive_namen:
                val = ui_platzierung_auswahl(name, prefix_key="ep", custom_title=f"**{name}** ({punkte_dict[name]} Punkte)**:**")
                if val in ["doppelt", "fehlt"]:
                    eingabe_fehler = True
                else:
                    end_platzierungen[name] = int(val)
                
            # Kario
            if st.session_state.spielmodus == "Kario":
                st.write("---")
                st.write("#### Bier")
                for name in aktive_namen:
                    st.write(f"**{name}:**")
                    bier_options = list(range(1, st.session_state.gesamt_rennen + 1))
                    bier_options.append("❌")
                    b_val = st.segmented_control(f"Bier_{name}", options=bier_options, key=f"bier_ep_{name}", label_visibility="collapsed")
                    if b_val is None:
                        eingabe_fehler_bier = True
                    else:
                        if b_val == "❌":
                            bier_finished[name] = "❌"
                        else:
                            bier_finished[name] = int(b_val)

            st.divider()

            col1, col2 = st.columns([3, 1])
            with col1:
                if st.button("Abschließen", type="primary"):
                    if eingabe_fehler:
                        st.error("❌ Exakt eine Platzierung pro Spieler wählen!")
                    elif st.session_state.spielmodus == "Kario" and eingabe_fehler_bier:
                        st.error("❌ Für alle Spieler angeben, wann das Bier geleert wurde!")
                    else:
                        c = conn.cursor()
                        if "❌" in list(bier_finished.values()):
                            st.warning("Bier nicht geleert, Endplatzierung wird auf 12 gesetzt!")
                            time.sleep(1.5)

                        for s_name, endplatz in end_platzierungen.items():
                            b_val = bier_finished.get(s_name, None)
                            if b_val == "❌":
                                b_val = None
                                endplatz = 12
                            c.execute("INSERT INTO turnier_ergebnisse (turnier_id, spieler_name, endplatzierung, bier_finished_nach) VALUES (?, ?, ?, ?);", (st.session_state.turnier_id, s_name, endplatz, b_val))
                        conn.commit()
                        
                        speichere_in_cloud(tabellen=["turniere", "rennen", "renn_ergebnisse", "turnier_ergebnisse"])
                        
                        st.session_state.warten_auf_endplatzierung = False
                        st.session_state.turnier_id = None
                        st.success("Turnier vollständig verbucht und in der Cloud gesichert!")
                        time.sleep(1.5)
                        st.rerun()
            with col2:
                if st.button("Zurück"):
                    c = conn.cursor()
                    c.execute("SELECT MAX(id) FROM rennen WHERE turnier_id = ?;", (st.session_state.turnier_id,))
                    last_race_id = c.fetchone()[0]
                    if last_race_id:
                        c.execute("DELETE FROM rennen WHERE id = ?;", (last_race_id,))
                        conn.commit()

                        st.session_state.warten_auf_endplatzierung = False
                        st.session_state.turnier_aktiv = True  
                        st.session_state.scroll_to_top = True
                        st.rerun()
                        
                if st.button("Abbrechen"):
                    c = conn.cursor()
                    c.execute("DELETE FROM turniere WHERE id = ?;", (st.session_state.turnier_id,))
                    conn.commit()
                    st.session_state.warten_auf_endplatzierung = False
                    st.session_state.turnier_id = None
                    st.session_state.scroll_to_top = True
                    st.rerun()

# ==========================================
# TAB 2: SPIELER-PROFILE & VERWALTUNG
# ==========================================
with tab2:
    with st.expander("👤 Verwaltung Spieler-Datenbank"):
        if not st.session_state.authenticated:
            st.warning("🔒 Melde dich an.")
        else:
            col_add, col_del = st.columns(2)
            with col_add:
                st.write("**Neuer Spieler:**")
                neuer_name = st.text_input("Neuer Spieler", label_visibility="collapsed")
                if st.button("Hinzufügen", type="primary"):
                    if neuer_name.strip():
                        try:
                            cursor.execute("INSERT INTO spieler (name) VALUES (?);", (neuer_name.strip(),))
                            conn.commit()
                            speichere_in_cloud(tabellen=["spieler"])
                            st.success(f"{neuer_name} hinzugefügt!")
                            time.sleep(1.5)
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.error("❌ Name existiert bereits!")
            with col_del:
                if not df_spieler.empty:
                    st.write("**Löschen:**")
                    loesch_name = st.selectbox("Löschen", df_spieler["name"].tolist(), label_visibility="collapsed")
                    if st.button("Löschen", type="secondary"):
                        cursor.execute("DELETE FROM spieler WHERE name = ?;", (loesch_name,))
                        conn.commit()
                        speichere_in_cloud(tabellen=["spieler", "rennen", "renn_ergebnisse", "turnier_ergebnisse"])
                        st.success(f"{loesch_name} gelöscht!")
                        time.sleep(1.5)
                        st.rerun()

    st.divider()

    st.write("#### Spieler-Statistiken")
    if not df_spieler.empty:
        st.write("**Spieler:**")
        profil_name = st.selectbox("Spieler", df_spieler["name"].tolist(), label_visibility="collapsed")

        df_r_stats = pd.read_sql_query(f"SELECT AVG(re.platzierung) as avg_r_platz, SUM(m.punkte) as gesamt_punkte, COUNT(re.id) as gesamt_rennen, AVG(m.punkte) as avg_r_punkte FROM renn_ergebnisse re JOIN punkte_mapping m ON re.platzierung = m.platzierung WHERE re.spieler_name = '{profil_name}';", conn)

        df_t_platz = pd.read_sql_query(f"SELECT AVG(endplatzierung) as avg_t_platz FROM turnier_ergebnisse WHERE spieler_name = '{profil_name}';", conn)

        df_r_siege = pd.read_sql_query(f"SELECT COUNT(*) as r_siege FROM renn_ergebnisse WHERE spieler_name = '{profil_name}' AND platzierung = 1;", conn)

        df_t_siege = pd.read_sql_query(f"SELECT COUNT(*) as t_siege FROM turnier_ergebnisse WHERE spieler_name = '{profil_name}' AND endplatzierung = 1;", conn)

        df_beste_strecken = pd.read_sql_query(f"SELECT r.strecken_name as 'Strecke', COUNT(re.id) as 'Gefahren', ROUND(AVG(re.platzierung), 2) as 'Ø-Platz' FROM renn_ergebnisse re JOIN rennen r ON re.rennen_id = r.id WHERE re.spieler_name = '{profil_name}' GROUP BY r.strecken_name ORDER BY AVG(re.platzierung) ASC LIMIT 5;", conn)

        df_lieblings_strecken = pd.read_sql_query(f"SELECT r.strecken_name as 'Strecke', COUNT(r.id) as 'Gewählt', ROUND((SELECT AVG(re2.platzierung) FROM renn_ergebnisse re2 JOIN rennen r2 ON re2.rennen_id = r2.id WHERE r2.strecken_name = r.strecken_name AND re2.spieler_name = '{profil_name}'), 2) as 'Ø-Platz' FROM rennen r WHERE r.gewaehlt_von_name = '{profil_name}' GROUP BY r.strecken_name ORDER BY COUNT(r.id) DESC, r.strecken_name ASC LIMIT 5;", conn)

        if df_r_stats["gesamt_rennen"].values[0] > 0:
            tot_pts = df_r_stats["gesamt_punkte"].values[0] or 0
            tot_races = df_r_stats["gesamt_rennen"].values[0] or 1
            genormte_punkte = (tot_pts / tot_races) * 4

            m_col1, m_col2, m_col3, m_col4 = st.columns(4)
            with m_col1:
                st.metric("**Ø-Platz Rennen**", f"{df_r_stats['avg_r_platz'].values[0]:.2f}")
                st.metric("**Ø-Platz Turnier**", f"{df_t_platz['avg_t_platz'].values[0]:.2f}" if pd.notnull(df_t_platz['avg_t_platz'].values[0]) else "N/A")
            with m_col2:
                st.metric("**Ø-Punkte / Rennen**", f"{df_r_stats['avg_r_punkte'].values[0]:.2f}")
                st.metric("**Ø-Punkte / Turnier (4 R.)**", f"{genormte_punkte:.2f}")
            with m_col3:
                st.metric("**Rennsiege**", f"{df_r_siege['r_siege'].values[0]} 🏁")
                st.metric("**Turniersiege**", f"{df_t_siege['t_siege'].values[0]} 🏆")
            with m_col4:
                st.metric("**Rennen (Gesamt)**", f"{tot_races}")
                st.metric("**Punkte (Gesamt)**", f"{tot_pts}")

            st.divider()
            st.write("#### 🏆 Ranglisten")
            t_col1, t_col2 = st.columns(2)
            with t_col1:
                st.write("**🔝 Beste Strecken**")
                st.dataframe(df_beste_strecken, hide_index=True, width="stretch")
            with t_col2:
                st.write("**❤️ Lieblingsstrecken**")
                st.dataframe(df_lieblings_strecken, hide_index=True, width="stretch")
        else:
            st.info("Keine Renndaten für diesen Spieler.")

# ==========================================
# TAB 3: STRECKEN-DATENBANK
# ==========================================
with tab3:
    st.write("#### Strecken-Statistiken")
    
    st.write("**Strecke:**")
    selected_track = st.selectbox("Strecke", df_strecken["name"].tolist(), label_visibility="collapsed")

    df_play_count = pd.read_sql_query(f"SELECT COUNT(*) as anz FROM rennen WHERE strecken_name = '{selected_track}';", conn)

    df_most_picked = pd.read_sql_query(f"SELECT gewaehlt_von_name as name, COUNT(*) as c FROM rennen WHERE strecken_name = '{selected_track}' AND gewaehlt_von_name IS NOT NULL GROUP BY gewaehlt_von_name ORDER BY c DESC LIMIT 1;", conn)

    st.write(f"**Wie oft gespielt:** {df_play_count['anz'].values[0]}x")
    st.write(f"**Am öftesten gewählt von:** {df_most_picked['name'].values[0] if not df_most_picked.empty else 'Niemandem'}")

    st.divider()
    st.write("#### 🏆 Ranglisten")

    query_siege = f"SELECT spieler_name as Spieler, COUNT(*) as Rennsiege FROM renn_ergebnisse re JOIN rennen r ON re.rennen_id = r.id WHERE r.strecken_name = '{selected_track}' AND re.platzierung = 1 GROUP BY spieler_name ORDER BY Rennsiege DESC;"
    query_platz = f"SELECT spieler_name as Spieler, AVG(re.platzierung) as 'Ø-Platz' FROM renn_ergebnisse re JOIN rennen r ON re.rennen_id = r.id WHERE r.strecken_name = '{selected_track}' GROUP BY spieler_name ORDER BY 'Ø-Platz' ASC;"
    query_punkte = f"SELECT spieler_name as Spieler, AVG(m.punkte) as 'Ø-Punkte' FROM renn_ergebnisse re JOIN rennen r ON re.rennen_id = r.id JOIN punkte_mapping m ON re.platzierung = m.platzierung WHERE r.strecken_name = '{selected_track}' GROUP BY spieler_name ORDER BY 'Ø-Punkte' DESC;"

    rl1, rl2, rl3 = st.columns(3)
    with rl1:
        st.write("**Nach Ø-Platz**")
        st.dataframe(pd.read_sql_query(query_platz, conn), hide_index=True, width="stretch")
    with rl2:
        st.write("**Nach Ø-Punkten**")
        st.dataframe(pd.read_sql_query(query_punkte, conn), hide_index=True, width="stretch")
    with rl3:
        st.write("**Nach Anzahl Siegen**")
        st.dataframe(pd.read_sql_query(query_siege, conn), hide_index=True, width="stretch")

# ==========================================
# TAB 4: HEAD-TO-HEAD
# ==========================================
with tab4:
    st.write("#### Rivalen-Vergleich")
    
    st.write("**Spieler:**")
    rivalen = st.multiselect("Spieler", df_spieler["name"].tolist(), key="spieler_tab4", default=["Pfeiffer", "Markus"] if len(df_spieler) >= 2 else [], label_visibility="collapsed")

    if len(rivalen) >= 2:
        formatted_names = ",".join([f"'{name}'" for name in rivalen])
        names_str = f"({formatted_names})"
        
        st.write("**Filterung nach Strecke:**")
        h2h_strecke = st.selectbox("Filterung nach Strecke", ["Alle Strecken"] + df_strecken["name"].tolist(), label_visibility="collapsed")

        subquery_gemeinsam = f"SELECT r.turnier_id FROM renn_ergebnisse re JOIN rennen r ON re.rennen_id = r.id WHERE re.spieler_name IN {names_str} GROUP BY r.turnier_id HAVING COUNT(DISTINCT re.spieler_name) = {len(rivalen)}"
        track_condition = f"AND r.strecken_name = '{h2h_strecke}'" if h2h_strecke != "Alle Strecken" else ""

        df_h2h_r = pd.read_sql_query(f"SELECT re.spieler_name as spieler, m.punkte, re.platzierung, r.turnier_id, CASE WHEN re.platzierung = 1 THEN 1 ELSE 0 END as ist_rennsieg FROM renn_ergebnisse re JOIN rennen r ON re.rennen_id = r.id JOIN punkte_mapping m ON re.platzierung = m.platzierung WHERE r.turnier_id IN ({subquery_gemeinsam}) AND re.spieler_name IN {names_str} {track_condition};", conn)

        df_h2h_t = pd.read_sql_query(f"SELECT spieler_name as spieler, endplatzierung, (SELECT SUM(m2.punkte) FROM renn_ergebnisse re2 JOIN punkte_mapping m2 ON re2.platzierung = m2.platzierung JOIN rennen r2 ON re2.rennen_id = r2.id WHERE r2.turnier_id = te.turnier_id AND re2.spieler_name = te.spieler_name) as turnier_punkte, CASE WHEN endplatzierung = 1 THEN 1 ELSE 0 END as ist_turniersieg FROM turnier_ergebnisse te WHERE turnier_id IN ({subquery_gemeinsam}) AND spieler_name IN {names_str};", conn)

        if not df_h2h_r.empty:
            c1, c2 = st.columns(2)
            with c1:
                st.write("**Rennsiege**")
                st.bar_chart(df_h2h_r.groupby("spieler")["ist_rennsieg"].sum().reset_index().set_index("spieler"))
                st.write("**Ø-Platz Rennen ↓**")
                st.bar_chart(df_h2h_r.groupby("spieler")["platzierung"].mean().reset_index().set_index("spieler"))
                st.write("**Ø-Punkte / Rennen**")
                st.bar_chart(df_h2h_r.groupby("spieler")["punkte"].mean().reset_index().set_index("spieler"))
                
            with c2:
                if h2h_strecke == "Alle Strecken":
                    if not df_h2h_t.empty:
                        st.write("**Turniersiege**")
                        st.bar_chart(df_h2h_t.groupby("spieler")["ist_turniersieg"].sum().reset_index().set_index("spieler"))
                        st.write("**Ø-Platz Turnier ↓**")
                        st.bar_chart(df_h2h_t.groupby("spieler")["endplatzierung"].mean().reset_index().set_index("spieler"))
                        st.write("**Ø-Punkte / Turnier**")
                        st.bar_chart(df_h2h_t.groupby("spieler")["turnier_punkte"].mean().reset_index().set_index("spieler"))
                else:
                    st.info("Turnier-Metriken bei Streckenfilter ausgeblendet.")

# ==========================================
# TAB 5: VERLAUF & EDITIEREN
# ==========================================
with tab5:
    st.write("#### Turnierverlauf")

    df_verlauf = pd.read_sql_query("SELECT t.id as 'Turnier-ID', t.datum as 'Spieldatum', GROUP_CONCAT(te.spieler_name, ', ') as 'Teilnehmer' FROM turniere t JOIN turnier_ergebnisse te ON t.id = te.turnier_id GROUP BY t.id ORDER BY t.id DESC;", conn)

    if df_verlauf.empty:
        st.info("Noch keine Turniere gespeichert.")
    else:
        st.dataframe(df_verlauf, width="stretch", hide_index=True)
        st.divider()

        if not st.session_state.authenticated:
            st.warning("🔒 Melde dich an.")
        else:
            st.write("#### Bearbeiten")
            st.write("**Turnier-ID:**")
            ausgewaehltes_turnier = st.selectbox("Turnier-ID zum Bearbeiten", df_verlauf['Turnier-ID'].tolist(), key="select_edit_id", label_visibility="collapsed")

            st.divider()

            if ausgewaehltes_turnier:
                st.write("#### Turnier-Endplatzierungen")
                df_aktuelle_platze = pd.read_sql_query(f"SELECT spieler_name, endplatzierung FROM turnier_ergebnisse WHERE turnier_id = {ausgewaehltes_turnier};", conn)

                edit_endplatzierungen = {}
                eingabe_fehler_ep = False
                
                for _, row in df_aktuelle_platze.iterrows():
                    val = ui_platzierung_auswahl(row['spieler_name'], prefix_key=f"edit_ep_{ausgewaehltes_turnier}", default_val=int(row['endplatzierung']))
                    if val in ["doppelt", "fehlt"]:
                        eingabe_fehler_ep = True
                    else:
                        edit_endplatzierungen[row['spieler_name']] = int(val)

                if st.button("Aktualisieren", type="primary", key="rennen_akt"):
                    if eingabe_fehler_ep:
                        st.error("❌ Exakt eine Platzierung pro Spieler wählen!")
                    else:
                        c = conn.cursor()
                        for s_name, ep_neu in edit_endplatzierungen.items():
                            c.execute("UPDATE turnier_ergebnisse SET endplatzierung = ? WHERE turnier_id = ? AND spieler_name = ?;", (ep_neu, ausgewaehltes_turnier, s_name))
                        conn.commit()
                        speichere_in_cloud(tabellen=["turnier_ergebnisse"])
                        st.success("Aktualisiert!")
                        time.sleep(1.5)
                        st.rerun()

                # Kario
                df_aktuelle_bier = pd.read_sql_query(f"SELECT spieler_name, bier_finished_nach FROM turnier_ergebnisse WHERE turnier_id = {ausgewaehltes_turnier};", conn)
                is_kario = df_aktuelle_bier['bier_finished_nach'].notna().any()
                if is_kario:
                    st.divider()
                    st.write("#### Bier")

                    # Gesamtanzahl Rennen
                    c_rennen = conn.cursor()
                    c_rennen.execute("SELECT COUNT(*) FROM rennen WHERE turnier_id = ?;", (ausgewaehltes_turnier,))
                    anz_rennen_im_turnier = c_rennen.fetchone()[0] or 1
                    bier_options = list(range(1, anz_rennen_im_turnier + 1))
                    bier_options.append("❌")

                    edit_bier = {}
                    eingabe_fehler_b_ep = False

                    for _, row in df_aktuelle_bier.iterrows():
                        st.write(f"**{row['spieler_name']}:**")
                        b_default = "❌"
                        if not isnan(row["bier_finished_nach"]):
                            b_default = row["bier_finished_nach"]
                            pass
                        b_val = st.segmented_control(f"Bier_{row['spieler_name']}",
                                                     options=bier_options,
                                                     key=f"edit_bier_ep_{ausgewaehltes_turnier}_{row['spieler_name']}",
                                                     label_visibility="collapsed",
                                                     default=b_default)
                        if b_val is None:
                            eingabe_fehler_b_ep = True
                        else:
                            if b_val == "❌":
                                edit_bier[row['spieler_name']] = "❌"
                            else:
                                edit_bier[row['spieler_name']] = int(b_val)

                    if st.button("Aktualisieren", type="primary", key="bier_akt"):
                        if eingabe_fehler_b_ep:
                            st.error("❌ Für alle Spieler angeben, wann das Bier geleert wurde!")
                        else:
                            c = conn.cursor()
                            if "❌" in list(edit_bier.values()):
                                st.warning("Bier nicht geleert, Endplatzierung wird auf 12 gesetzt!")
                                time.sleep(1.5)
                            for s_name, b_neu in edit_bier.items():
                                if b_neu == "❌":
                                    b_neu = None
                                    ep_neu = 12
                                    c.execute("UPDATE turnier_ergebnisse SET endplatzierung = ? WHERE turnier_id = ? AND spieler_name = ?;", (ep_neu, ausgewaehltes_turnier, s_name))
                                c.execute("UPDATE turnier_ergebnisse SET bier_finished_nach = ? WHERE turnier_id = ? AND spieler_name = ?;", (b_neu, ausgewaehltes_turnier, s_name))
                            conn.commit()
                            speichere_in_cloud(tabellen=["turnier_ergebnisse"])
                            st.success("Aktualisiert!")
                            time.sleep(1.5)
                            st.rerun()

                st.divider()
                st.write("#### Rennergebnisse")
                df_rennen_liste = pd.read_sql_query(f"SELECT id as rennen_id, strecken_name FROM rennen WHERE turnier_id = {ausgewaehltes_turnier};", conn)

                for idx, r_row in df_rennen_liste.iterrows():
                    r_id = int(r_row['rennen_id'])
                    with st.expander(f"🏎️ Rennen {idx + 1} (ID #{r_id}): {r_row['strecken_name']}"):
                        c_race = conn.cursor()
                        c_race.execute("SELECT strecken_name, gewaehlt_von_name FROM rennen WHERE id = ?;", (r_id,))
                        curr_race = c_race.fetchone()

                        alle_strecken_namen = df_strecken["name"].tolist()
                        curr_track_name = curr_race[0]
                        
                        st.write("**Strecke:**")
                        neue_strecke_name = st.selectbox("Strecke", alle_strecken_namen, index=alle_strecken_namen.index(curr_track_name) if curr_track_name in alle_strecken_namen else 0, key=f"edit_track_select_{r_id}", label_visibility="collapsed")

                        df_res_players = pd.read_sql_query(f"SELECT spieler_name, platzierung FROM renn_ergebnisse WHERE rennen_id = {r_id};", conn)
                        picker_options = ["Niemand (Zufall)"] + df_res_players["spieler_name"].tolist()
                        curr_picker_index = picker_options.index(curr_race[1]) if curr_race[1] is not None and curr_race[1] in picker_options else 0

                        st.write("**Gewählt von:**")
                        neuer_picker_name = st.selectbox("Gewählt von", picker_options, index=curr_picker_index, key=f"edit_picker_select_{r_id}", label_visibility="collapsed")
                        neuer_picker_name_val = None if neuer_picker_name == "Niemand (Zufall)" else neuer_picker_name

                        st.write("**Platzierungen:**")
                        edit_race_platzierungen = {}
                        eingabe_fehler_r = False
                        
                        for _, p_row in df_res_players.iterrows():
                            val = ui_platzierung_auswahl(p_row['spieler_name'], prefix_key=f"edit_race_p_{r_id}", default_val=int(p_row['platzierung']))
                            if val in ["doppelt", "fehlt"]:
                                eingabe_fehler_r = True
                            else:
                                edit_race_platzierungen[p_row['spieler_name']] = int(val)

                        if st.button("Aktualisieren", key=f"btn_save_race_{r_id}", type="primary"):
                            if eingabe_fehler_r:
                                st.error("❌ Exakt eine Platzierung pro Spieler wählen!")
                            elif hat_duplikate(list(edit_race_platzierungen.values())):
                                st.error("❌ Doppelte Platzierung!")
                            else:
                                c = conn.cursor()
                                c.execute("UPDATE rennen SET strecken_name = ?, gewaehlt_von_name = ? WHERE id = ?;", (neue_strecke_name, neuer_picker_name_val, r_id))
                                for s_name, pl_neu in edit_race_platzierungen.items():
                                    c.execute("UPDATE renn_ergebnisse SET platzierung = ? WHERE rennen_id = ? AND spieler_name = ?;", (pl_neu, r_id, s_name))
                                conn.commit()
                                speichere_in_cloud(tabellen=["rennen", "renn_ergebnisse"])
                                st.success("Aktualisiert!")
                                time.sleep(1.5)
                                st.rerun()

                st.divider()
                if st.button("❌ Gesamtes Turnier löschen", type="secondary", key=f"btn_del_{ausgewaehltes_turnier}"):
                    c = conn.cursor()
                    c.execute("DELETE FROM turniere WHERE id = ?;", (ausgewaehltes_turnier,))
                    conn.commit()
                    speichere_in_cloud(tabellen=["turniere", "rennen", "renn_ergebnisse", "turnier_ergebnisse"])
                    st.success("Gelöscht!")
                    time.sleep(1.5)
                    st.rerun()

conn.close()
