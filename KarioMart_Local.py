import streamlit as st
import pandas as pd
import sqlite3
import os

# 1. LOKALE DATENBANK INITIALISIEREN & ERWEITERN
DB_FILE = "kario_mart_local.db"
db_exists = os.path.exists(DB_FILE)

conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

# Tabellen erstellen mit strikten CASCADE-Regeln für sauberes Löschen/Editieren
cursor.execute(
    "CREATE TABLE IF NOT EXISTS spieler (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE);")
cursor.execute(
    "CREATE TABLE IF NOT EXISTS strecken (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, cup TEXT NOT NULL);")
cursor.execute(
    "CREATE TABLE IF NOT EXISTS punkte_mapping (platzierung INTEGER PRIMARY KEY CHECK (platzierung BETWEEN 1 AND 12), punkte INTEGER NOT NULL);")
cursor.execute(
    "CREATE TABLE IF NOT EXISTS turniere (id INTEGER PRIMARY KEY AUTOINCREMENT, datum TIMESTAMP DEFAULT CURRENT_TIMESTAMP);")
cursor.execute(
    "CREATE TABLE IF NOT EXISTS rennen (id INTEGER PRIMARY KEY AUTOINCREMENT, turnier_id INTEGER REFERENCES turniere(id) ON DELETE CASCADE, strecken_id INTEGER REFERENCES strecken(id) ON DELETE RESTRICT, gewaehlt_von INTEGER REFERENCES spieler(id) ON DELETE SET NULL);")
cursor.execute(
    "CREATE TABLE IF NOT EXISTS renn_ergebnisse (id INTEGER PRIMARY KEY AUTOINCREMENT, rennen_id INTEGER REFERENCES rennen(id) ON DELETE CASCADE, spieler_id INTEGER REFERENCES spieler(id) ON DELETE CASCADE, platzierung INTEGER REFERENCES punkte_mapping(platzierung), UNIQUE (rennen_id, spieler_id));")

cursor.execute("""
CREATE TABLE IF NOT EXISTS turnier_ergebnisse (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    turnier_id INTEGER REFERENCES turniere(id) ON DELETE CASCADE,
    spieler_id INTEGER REFERENCES spieler(id) ON DELETE CASCADE,
    endplatzierung INTEGER CHECK (endplatzierung BETWEEN 1 AND 12),
    UNIQUE (turnier_id, spieler_id)
);
""")
conn.commit()

# Startdaten (Seed-Daten)
if not db_exists:
    punkte_daten = [(1, 15), (2, 12), (3, 10), (4, 9), (5, 8), (6, 7), (7, 6),
                    (8, 5), (9, 4), (10, 3), (11, 2), (12, 1)]
    cursor.executemany(
        "INSERT OR IGNORE INTO punkte_mapping (platzierung, punkte) VALUES (?, ?);",
        punkte_daten)
    spieler_daten = [("Anja",), ("Pfeiffer",), ("Markus",)]
    cursor.executemany("INSERT OR IGNORE INTO spieler (name) VALUES (?);",
                       spieler_daten)
    strecken_daten = [
        # Pilz-Cup
        ("Mario-Kart-Stadion", "Pilz-Cup"),
        ("Wasserpark", "Pilz-Cup"),
        ("Zuckersüßer Canyon", "Pilz-Cup"),
        ("Steinblock-Ruinen", "Pilz-Cup"),

        # Blumen-Cup
        ("Marios Piste", "Blumen-Cup"),
        ("Toads Hafenstadt", "Blumen-Cup"),
        ("Prisforce-Stadion", "Blumen-Cup"),
        ("Shy Guys Wasserfälle", "Blumen-Cup"),

        # Stern-Cup
        ("Sonnenflughafen", "Stern-Cup"),
        ("Delfinlagune", "Stern-Cup"),
        ("Discodrom", "Stern-Cup"),
        ("Wario-Abfahrt", "Stern-Cup"),

        # Spezial-Cup
        ("Wolkenstraße", "Spezial-Cup"),
        ("Knochentrockene Dünen", "Spezial-Cup"),
        ("Bowsers Festung", "Spezial-Cup"),
        ("Regenbogen-Boulevard", "Spezial-Cup"),

        # Panzer-Cup
        ("Wii Kuhmuh-Weide", "Panzer-Cup"),
        ("GBA Marios Piste", "Panzer-Cup"),
        ("DS Cheep-Cheep-Strand", "Panzer-Cup"),
        ("N64 Toads Turnpike", "Panzer-Cup"),

        # Bananen-Cup
        ("GCN Trockene Wüste", "Bananen-Cup"),
        ("SNES Donut-Ebene 3", "Bananen-Cup"),
        ("N64 Marios Rennbahn", "Bananen-Cup"),
        ("3DS DK Alpin", "Bananen-Cup"),

        # Blatt-Cup
        ("DS Wario-Arena", "Blatt-Cup"),
        ("GBA Saharaland", "Blatt-Cup"),
        ("3DS Musikpark", "Blatt-Cup"),
        ("N64 Yoshi-Tal", "Blatt-Cup"),

        # Blitz-Cup
        ("DS Ticktack-Trauma", "Blitz-Cup"),
        ("3DS Röhrenraserei", "Blitz-Cup"),
        ("Wii Vulkangrollen", "Blitz-Cup"),
        ("N64 Regenbogen-Boulevard", "Blitz-Cup"),

        # Ei-Cup
        ("GCN Yoshi-Circuit", "Ei-Cup"),
        ("Excitebike-Stadion", "Ei-Cup"),
        ("Große Verfolgungsjagd", "Ei-Cup"),
        ("Mute City", "Ei-Cup"),

        # Triforce-Cup
        ("Wii Warios Goldmine", "Triforce-Cup"),
        ("SNES Regenbogen-Boulevard", "Triforce-Cup"),
        ("Polarkreis", "Triforce-Cup"),
        ("Hyrule-Piste", "Triforce-Cup"),

        # Crossing-Cup
        ("Baby-Park", "Crossing-Cup"),
        ("Käseland", "Crossing-Cup"),
        ("Wilder Wario-Wanderweg", "Crossing-Cup"),
        ("Animal Crossing", "Crossing-Cup"),

        # Glocken-Cup
        ("3DS Koopa-Großstadtbucht", "Glocken-Cup"),
        ("GBA Schleifchenstraße", "Glocken-Cup"),
        ("Superglocken-U-Bahn", "Glocken-Cup"),
        ("Big Blue", "Glocken-Cup"),

        # Goldener Turbo-Cup
        ("Tour Paris-Parcours", "Goldener Turbo-Cup"),
        ("3DS Toads Piste", "Goldener Turbo-Cup"),
        ("N64 Schoko-Sumpf", "Goldener Turbo-Cup"),
        ("Wii Kokos-Promenade", "Goldener Turbo-Cup"),

        # Glückskatzen-Cup
        ("Tour Tokio-Tempotour", "Glückskatzen-Cup"),
        ("DS Pilz-Pass", "Glückskatzen-Cup"),
        ("GBA Wolkenpiste", "Glückskatzen-Cup"),
        ("Ninja-Dojo", "Glückskatzen-Cup"),

        # Rüben-Cup
        ("Tour New-York-Speedway", "Rüben-Cup"),
        ("SNES Marios Piste 3", "Rüben-Cup"),
        ("N64 Kalimari-Wüste", "Rüben-Cup"),
        ("DS Waluigi-Flipper", "Rüben-Cup"),

        # Propeller-Cup
        ("Tour Sydney-Spritztour", "Propeller-Cup"),
        ("GBA Schneeland", "Propeller-Cup"),
        ("Wii Pilz-Schlucht", "Propeller-Cup"),
        ("Eiscreme-Eskapade", "Propeller-Cup"),

        # Fels-Cup
        ("Tour London-Tour", "Fels-Cup"),
        ("GBA Buu-Huu-Tal", "Fels-Cup"),
        ("3DS Gebirgspfad", "Fels-Cup"),
        ("Wii Blätterwald", "Fels-Cup"),

        # Mond-Cup
        ("Tour Pflaster von Berlin", "Mond-Cup"),
        ("DS Peachs Schlossgarten", "Mond-Cup"),
        ("Bergbescherung", "Mond-Cup"),
        ("3DS Regenbogen-Boulevard", "Mond-Cup"),

        # Frucht-Cup
        ("Tour Ausfahrt Amsterdam", "Frucht-Cup"),
        ("GBA Flussufer-Park", "Frucht-Cup"),
        ("Wii DK Skikane", "Frucht-Cup"),
        ("Yoshis Eiland", "Frucht-Cup"),

        # Bumerang-Cup
        ("Tour Bangkok-Abendrot", "Bumerang-Cup"),
        ("DS Marios Piste", "Bumerang-Cup"),
        ("GCN Waluigi-Arena", "Bumerang-Cup"),
        ("Tour Überholspur Singapur", "Bumerang-Cup"),

        # Feder-Cup
        ("Tour Athen-Aufruhr", "Feder-Cup"),
        ("GCN Daisys Dampfer", "Feder-Cup"),
        ("Wii Mondblick-Straße", "Feder-Cup"),
        ("Bad-Parcours", "Feder-Cup"),

        # Doppelkirschen-Cup
        ("Tour Los-Angeles-Lap", "Doppelkirschen-Cup"),
        ("GBA Sonnenuntergangs-Wüste", "Doppelkirschen-Cup"),
        ("Wii Koopa-Kap", "Doppelkirschen-Cup"),
        ("Tour Vancouver-Wildpfad", "Doppelkirschen-Cup"),

        # Eichel-Cup
        ("Tour Rom-Rambazamba", "Eichel-Cup"),
        ("GCN DK Bergland", "Eichel-Cup"),
        ("Wii Daisys Piste", "Eichel-Cup"),
        ("Piranha-Pflanzen-Bucht", "Eichel-Cup"),

        # Stachi-Cup
        ("Tour Madrid-Drive", "Stachi-Cup"),
        ("3DS Rosalinas Eiswelt", "Stachi-Cup"),
        ("SNES Bowsers Festung 3", "Stachi-Cup"),
        ("Wii Regenbogen-Boulevard", "Stachi-Cup")
    ]
    cursor.executemany(
        "INSERT OR IGNORE INTO strecken (name, cup) VALUES (?, ?);",
        strecken_daten)
    conn.commit()

# Stammdaten laden
df_spieler = pd.read_sql_query("SELECT * FROM spieler ORDER BY name ASC", conn)
df_strecken = pd.read_sql_query("SELECT * FROM strecken ORDER BY name ASC",
                                conn)

# SESSION STATE INITIALISIEREN
if "turnier_aktiv" not in st.session_state: st.session_state.turnier_aktiv = False
if "aktuelle_runde" not in st.session_state: st.session_state.aktuelle_runde = 1
if "gesamt_rennen" not in st.session_state: st.session_state.gesamt_rennen = 4
if "turnier_id" not in st.session_state: st.session_state.turnier_id = None
if "aktive_spieler_ids" not in st.session_state: st.session_state.aktive_spieler_ids = []
if "wahl_modus" not in st.session_state: st.session_state.wahl_modus = "Zufällig gewählt"
if "warten_auf_endplatzierung" not in st.session_state: st.session_state.warten_auf_endplatzierung = False


# Hilfsfunktion für Duplikatsprüfung
def hat_duplikate(liste):
    return len(liste) != len(set(liste))


st.set_page_config(page_title="Kario Mart Dashboard", page_icon="🏎️",
                   layout="centered")
st.title("Kario Mart Stats")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🏁 Turnier-Erfassung",
    "👤 Spieler",
    "🗺️ Strecken",
    "⚔️ Head-to-Head",
    "📋 Verlauf"
])

# ==========================================
# TAB 1: TURNIER-ERFASSUNG (Mit Validierung)
# ==========================================
with tab1:
    if not st.session_state.turnier_aktiv and not st.session_state.warten_auf_endplatzierung:
        st.header("1. Neues Turnier")
        ausgewaehlte_namen = st.multiselect("Spieler:",
                                            df_spieler["name"].tolist(),
                                            key="spieler_tab1",
                                            default=["Pfeiffer", "Markus"] if len(
                                                df_spieler) >= 2 else [])
        anzahl_rennen = st.number_input("Anzahl Rennen:",
                                        min_value=1, max_value=48, value=4,
                                        step=1)
        wahl_modus = st.radio("Strecken-Auswahlmodus:",
                              ["Zufällig", "Auswahl"])

        if st.button("Starten", type="primary"):
            if len(ausgewaehlte_namen) < 2:
                st.error("Ein Turnier erfordert mindestens 2 Spieler!")
            else:
                c = conn.cursor()
                c.execute("INSERT INTO turniere DEFAULT VALUES;")
                st.session_state.turnier_id = c.lastrowid
                conn.commit()

                st.session_state.gesamt_rennen = int(anzahl_rennen)
                st.session_state.aktuelle_runde = 1
                st.session_state.wahl_modus = wahl_modus
                st.session_state.aktive_spieler_ids = \
                    df_spieler[df_spieler["name"].isin(ausgewaehlte_namen)][
                        "id"].tolist()
                st.session_state.turnier_aktiv = True
                st.rerun()

    elif st.session_state.turnier_aktiv and not st.session_state.warten_auf_endplatzierung:
        st.header("2. Rennergebnisse")
        st.subheader(
            f"Rennen {st.session_state.aktuelle_runde} von {st.session_state.gesamt_rennen}")

        df_aktive_spieler = df_spieler[
            df_spieler["id"].isin(st.session_state.aktive_spieler_ids)]
        aktive_namen = df_aktive_spieler["name"].tolist()

        strecke_name = st.selectbox("Strecke:",
                                    df_strecken["name"].tolist(),
                                    key=f"track_{st.session_state.aktuelle_runde}")
        selected_strecke_id = int(
            df_strecken[df_strecken["name"] == strecke_name]["id"].values[0])

        wer_gewaehlt_id = None
        if st.session_state.wahl_modus == "Auswahl":
            wer_gewaehlt_name = st.selectbox("Gewählt von:",
                                             aktive_namen,
                                             key=f"picker_{st.session_state.aktuelle_runde}")
            wer_gewaehlt_id = int(
                df_spieler[df_spieler["name"] == wer_gewaehlt_name][
                    "id"].values[0])

        st.write("#### Platzierungen:")
        platzierungen = {}
        for _, row in df_aktive_spieler.iterrows():
            p = st.number_input(f"{row['name']}:",
                                min_value=1, max_value=12, step=1,
                                key=f"p_{row['id']}_{st.session_state.aktuelle_runde}")
            platzierungen[int(row['id'])] = int(p)

        col_speichern, col_abbrechen = st.columns([3, 1])
        with col_speichern:
            if st.button(f"Speichern",
                         type="primary"):
                if hat_duplikate(list(platzierungen.values())):
                    st.error(
                        "❌ Fehler: Platzierungen dürfen nicht doppelt vergeben werden!")
                else:
                    c = conn.cursor()
                    c.execute(
                        "INSERT INTO rennen (turnier_id, strecken_id, gewaehlt_von) VALUES (?, ?, ?);",
                        (st.session_state.turnier_id, selected_strecke_id,
                         wer_gewaehlt_id))
                    r_id = c.lastrowid
                    for s_id, platz in platzierungen.items():
                        c.execute(
                            "INSERT INTO renn_ergebnisse (rennen_id, spieler_id, platzierung) VALUES (?, ?, ?);",
                            (r_id, s_id, platz))
                    conn.commit()

                    if st.session_state.aktuelle_runde >= st.session_state.gesamt_rennen:
                        st.session_state.turnier_aktiv = False
                        st.session_state.warten_auf_endplatzierung = True
                    else:
                        st.session_state.aktuelle_runde += 1
                    st.rerun()
        with col_abbrechen:
            if st.button("Abbrechen"):
                c = conn.cursor()
                c.execute("DELETE FROM turniere WHERE id = ?;",
                          (st.session_state.turnier_id,))
                conn.commit()
                st.session_state.turnier_aktiv = False
                st.rerun()

    elif st.session_state.warten_auf_endplatzierung:
        st.header("3. Turnier-Endplatzierungen")
        df_aktive_spieler = df_spieler[
            df_spieler["id"].isin(st.session_state.aktive_spieler_ids)]

        end_platzierungen = {}
        for _, row in df_aktive_spieler.iterrows():
            ep = st.number_input(f"{row['name']}:",
                                 min_value=1, max_value=12, step=1,
                                 key=f"ep_{row['id']}")
            end_platzierungen[int(row['id'])] = int(ep)

        if st.button("Abschließen", type="primary"):
            c = conn.cursor()
            for s_id, endplatz in end_platzierungen.items():
                c.execute(
                    "INSERT INTO turnier_ergebnisse (turnier_id, spieler_id, endplatzierung) VALUES (?, ?, ?);",
                    (st.session_state.turnier_id, s_id, endplatz))
            conn.commit()
            st.session_state.warten_auf_endplatzierung = False
            st.session_state.turnier_id = None
            st.success("Turnier vollständig verbucht!")
            st.rerun()

# ==========================================
# TAB 2: SPIELER-PROFILE & VERWALTUNG
# ==========================================
with tab2:
    st.header("Spieler-Leistungsprofile")

    # NEU: Spieler hinzufügen/entfernen Option
    with st.expander("👤 Verwaltung Spieler-Datenbank (Hinzufügen / Entfernen)"):
        col_add, col_del = st.columns(2)
        with col_add:
            neuer_name = st.text_input("Neuer Spieler:")
            if st.button("Hinzufügen", type="primary"):
                if neuer_name.strip():
                    try:
                        cursor.execute(
                            "INSERT INTO spieler (name) VALUES (?);",
                            (neuer_name.strip(),))
                        conn.commit()
                        st.success(f"{neuer_name} hinzugefügt!")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Name existiert bereits.")
        with col_del:
            if not df_spieler.empty:
                loesch_name = st.selectbox("Löschen:",
                                           df_spieler["name"].tolist())
                if st.button("Löschen",
                             type="secondary"):
                    cursor.execute("DELETE FROM spieler WHERE name = ?;",
                                   (loesch_name,))
                    conn.commit()
                    st.success(f"{loesch_name} gelöscht!")
                    st.rerun()

    st.divider()

    if not df_spieler.empty:
        profil_name = st.selectbox("Spieler:",
                                   df_spieler["name"].tolist())
        p_id = int(
            df_spieler[df_spieler["name"] == profil_name]["id"].values[0])

        # Basis-Metriken laden
        df_r_stats = pd.read_sql_query(
            f"SELECT AVG(re.platzierung) as avg_r_platz, SUM(m.punkte) as gesamt_punkte, COUNT(re.id) as gesamt_rennen, AVG(m.punkte) as avg_r_punkte FROM renn_ergebnisse re JOIN punkte_mapping m ON re.platzierung = m.platzierung WHERE re.spieler_id = {p_id}",
            conn)
        df_t_platz = pd.read_sql_query(
            f"SELECT AVG(endplatzierung) as avg_t_platz FROM turnier_ergebnisse WHERE spieler_id = {p_id}",
            conn)
        df_r_siege = pd.read_sql_query(
            f"SELECT COUNT(*) as r_siege FROM renn_ergebnisse WHERE spieler_id = {p_id} AND platzierung = 1",
            conn)
        df_t_siege = pd.read_sql_query(
            f"SELECT COUNT(*) as t_siege FROM turnier_ergebnisse WHERE spieler_id = {p_id} AND endplatzierung = 1",
            conn)

        # Abfrage für die Top 5 besten Strecken (Ø-Platzierung)
        query_beste_strecken = f"""
                SELECT s.name as 'Strecke', 
                       COUNT(re.id) as 'Gefahren', 
                       ROUND(AVG(re.platzierung), 2) as 'Ø-Platz' 
                FROM renn_ergebnisse re 
                JOIN rennen r ON re.rennen_id = r.id 
                JOIN strecken s ON r.strecken_id = s.id 
                WHERE re.spieler_id = {p_id} 
                GROUP BY s.name 
                ORDER BY AVG(re.platzierung) ASC 
                LIMIT 5
            """
        df_beste_strecken = pd.read_sql_query(query_beste_strecken, conn)

        # Abfrage für die Top 5 Lieblingsstrecken (Am häufigsten selbst gewählt)
        query_lieblings_strecken = f"""
                SELECT s.name as 'Strecke', 
                       COUNT(r.id) as 'Gewählt',
                       ROUND((SELECT AVG(re2.platzierung) FROM renn_ergebnisse re2 JOIN rennen r2 ON re2.rennen_id = r2.id WHERE r2.strecken_id = s.id AND re2.spieler_id = {p_id}), 2) as 'Ø-Platz'
                FROM rennen r 
                JOIN strecken s ON r.strecken_id = s.id
                WHERE r.gewaehlt_von = {p_id} 
                GROUP BY s.id, s.name 
                ORDER BY COUNT(r.id) DESC, s.name ASC
                LIMIT 5
            """
        df_lieblings_strecken = pd.read_sql_query(query_lieblings_strecken,
                                                  conn)

        if df_r_stats["gesamt_rennen"].values[0] > 0:
            tot_pts = df_r_stats["gesamt_punkte"].values[0] or 0
            tot_races = df_r_stats["gesamt_rennen"].values[0] or 1
            genormte_punkte = (tot_pts / tot_races) * 4

            # Übersichtliche Kachel-Zeile für allgemeine Statistiken
            m_col1, m_col2, m_col3, m_col4 = st.columns(4)
            with m_col1:
                st.metric(label="Ø-Platz Rennen",
                          value=f"{df_r_stats['avg_r_platz'].values[0]:.2f}")
                st.metric(label="Ø-Platz Turnier",
                          value=f"{df_t_platz['avg_t_platz'].values[0]:.2f}" if pd.notnull(
                              df_t_platz['avg_t_platz'].values[0]) else "N/A")
            with m_col2:
                st.metric(label="Ø-Punkte pro Rennen",
                          value=f"{df_r_stats['avg_r_punkte'].values[0]:.2f}")
                st.metric(label="Ø-Punkte pro Turnier (4 R.)",
                          value=f"{genormte_punkte:.2f}")
            with m_col3:
                st.metric(label="Rennsiege",
                          value=f"{df_r_siege['r_siege'].values[0]} 🏁")
                st.metric(label="Turniersiege",
                          value=f"{df_t_siege['t_siege'].values[0]} 🏆")
            with m_col4:
                st.metric(label="Rennen (Gesamt)", value=f"{tot_races}")
                st.metric(label="Punkte (Gesamt)", value=f"{tot_pts}")

            st.divider()

            # Anzeige der Tabellen für Beste Strecken und Lieblingsstrecken nebeneinander
            t_col1, t_col2 = st.columns(2)
            with t_col1:
                st.subheader("🔝 Beste Strecken")
                if not df_beste_strecken.empty:
                    st.dataframe(df_beste_strecken, hide_index=True,
                                 width="stretch")
                else:
                    st.info("Noch keine Renndaten vorhanden.")

            with t_col2:
                st.subheader("❤️ Lieblingsstrecken")
                if not df_lieblings_strecken.empty:
                    st.dataframe(df_lieblings_strecken, hide_index=True,
                                 width="stretch")
                else:
                    st.info(
                        "Bisher wurden in Turnieren keine Strecken von diesem Spieler selbst gewählt.")
        else:
            st.info("Keine Renndaten für diesen Spieler vorhanden.")

# ==========================================
# TAB 3: STRECKEN-DATENBANK
# ==========================================
with tab3:
    st.header("Strecken-Spezifische Statistiken")
    selected_track = st.selectbox("Strecke:",
                                  df_strecken["name"].tolist())
    t_id = int(
        df_strecken[df_strecken["name"] == selected_track]["id"].values[0])

    df_play_count = pd.read_sql_query(
        f"SELECT COUNT(*) as anz FROM rennen WHERE strecken_id = {t_id}", conn)
    df_most_picked = pd.read_sql_query(
        f"SELECT s.name, COUNT(*) as c FROM rennen r JOIN spieler s ON r.gewaehlt_von = s.id WHERE r.strecken_id = {t_id} GROUP BY s.id ORDER BY c DESC LIMIT 1",
        conn)

    st.write(f"**Wie oft gespielt:** {df_play_count['anz'].values[0]}x")
    st.write(
        f"**Am öftesten gewählt von:** {df_most_picked['name'].values[0] if not df_most_picked.empty else 'Niemandem (Nur Zufall)'}")

    st.divider()
    st.subheader(f"🏆 Ranglisten für: {selected_track}")

    query_siege = f"SELECT s.name as Spieler, COUNT(*) as Rennsiege FROM renn_ergebnisse re JOIN rennen r ON re.rennen_id = r.id JOIN spieler s ON re.spieler_id = s.id WHERE r.strecken_id = {t_id} AND re.platzierung = 1 GROUP BY s.id ORDER BY Rennsiege DESC"
    query_platz = f"SELECT s.name as Spieler, AVG(re.platzierung) as 'Ø-Platz' FROM renn_ergebnisse re JOIN rennen r ON re.rennen_id = r.id JOIN spieler s ON re.spieler_id = s.id WHERE r.strecken_id = {t_id} GROUP BY s.id ORDER BY 'Ø-Platz' ASC"
    query_punkte = f"SELECT s.name as Spieler, AVG(m.punkte) as 'Ø-Punkte' FROM renn_ergebnisse re JOIN rennen r ON re.rennen_id = r.id JOIN spieler s ON re.spieler_id = s.id JOIN punkte_mapping m ON re.platzierung = m.platzierung WHERE r.strecken_id = {t_id} GROUP BY s.id ORDER BY 'Ø-Punkte' DESC"

    rl1, rl2, rl3 = st.columns(3)

    with rl1:
        st.markdown("**Nach Ø-Platz**")
        st.dataframe(pd.read_sql_query(query_platz, conn), hide_index=True,
                     width="stretch")
    with rl2:
        st.markdown("**Nach Ø-Punkten**")
        st.dataframe(pd.read_sql_query(query_punkte, conn), hide_index=True,
                     width="stretch")
    with rl3:
        st.markdown("**Nach Anzahl Siegen**")
        st.dataframe(pd.read_sql_query(query_siege, conn), hide_index=True,
                     width="stretch")

# ==========================================
# TAB 4: HEAD-TO-HEAD (Dynamische Ausblendung)
# ==========================================
with tab4:
    st.header("Rivalen-Vergleich (Gemeinsame Turniere)")
    rivalen = st.multiselect("Spieler:",
                             df_spieler["name"].tolist(),
                             key="spieler_tab4",
                             default=["Pfeiffer", "Markus"] if len(
                                 df_spieler) >= 2 else [])

    if len(rivalen) >= 2:
        selected_ids = df_spieler[df_spieler["name"].isin(rivalen)][
            "id"].tolist()
        ids_str = f"({','.join(map(str, selected_ids))})"

        strecken_filter_liste = ["Alle Strecken"] + df_strecken[
            "name"].tolist()
        h2h_strecke = st.selectbox("Filterung nach Strecke:",
                                   strecken_filter_liste)

        subquery_gemeinsam = f"SELECT r.turnier_id FROM renn_ergebnisse re JOIN rennen r ON re.rennen_id = r.id WHERE re.spieler_id IN {ids_str} GROUP BY r.turnier_id HAVING COUNT(DISTINCT re.spieler_id) = {len(selected_ids)}"

        track_condition = ""
        if h2h_strecke != "Alle Strecken":
            tr_id = int(
                df_strecken[df_strecken["name"] == h2h_strecke]["id"].values[
                    0])
            track_condition = f"AND r.strecken_id = {tr_id}"

        query_h2h_races = f"SELECT s.name as spieler, m.punkte, re.platzierung, r.turnier_id, CASE WHEN re.platzierung = 1 THEN 1 ELSE 0 END as ist_rennsieg FROM renn_ergebnisse re JOIN rennen r ON re.rennen_id = r.id JOIN spieler s ON re.spieler_id = s.id JOIN punkte_mapping m ON re.platzierung = m.platzierung WHERE r.turnier_id IN ({subquery_gemeinsam}) AND re.spieler_id IN {ids_str} {track_condition};"
        df_h2h_r = pd.read_sql_query(query_h2h_races, conn)

        query_h2h_tournaments = f"SELECT s.name as spieler, te.endplatzierung, CASE WHEN te.endplatzierung = 1 THEN 1 ELSE 0 END as ist_turniersieg FROM turnier_ergebnisse te JOIN spieler s ON te.spieler_id = s.id WHERE te.turnier_id IN ({subquery_gemeinsam}) AND te.spieler_id IN {ids_str};"
        df_h2h_t = pd.read_sql_query(query_h2h_tournaments, conn)

        if not df_h2h_r.empty:
            df_pts = df_h2h_r.groupby("spieler")["punkte"].sum().reset_index()
            df_avg_r = df_h2h_r.groupby("spieler")[
                "platzierung"].mean().reset_index()
            df_r_wins = df_h2h_r.groupby("spieler")[
                "ist_rennsieg"].sum().reset_index()

            # NEU: Durchschnittl. Punkte pro Rennen
            df_avg_r_pts = df_h2h_r.groupby("spieler")[
                "punkte"].mean().reset_index()

            df_avg_t_pts = df_h2h_r.groupby(["spieler", "turnier_id"])[
                "punkte"].sum().groupby("spieler").mean().reset_index()
            df_avg_t_platz = df_h2h_t.groupby("spieler")[
                "endplatzierung"].mean().reset_index() if not df_h2h_t.empty else pd.DataFrame()
            df_t_wins = df_h2h_t.groupby("spieler")[
                "ist_turniersieg"].sum().reset_index() if not df_h2h_t.empty else pd.DataFrame()

            c1, c2 = st.columns(2)
            with c1:
                st.subheader("Rennsiege")
                st.bar_chart(df_r_wins.set_index("spieler"))
                st.subheader("Ø-Platz Rennen ↓")
                st.bar_chart(df_avg_r.set_index("spieler"))
                st.subheader("Ø-Punkte pro Rennen")
                st.bar_chart(df_avg_r_pts.set_index("spieler"))

            with c2:
                # BEDINGUNG: Zeige Turnierstatistiken NUR bei "Alle Strecken"
                if h2h_strecke == "Alle Strecken":
                    st.subheader("Turniersiege")
                    if not df_t_wins.empty: st.bar_chart(
                        df_t_wins.set_index("spieler"))
                    st.subheader("Ø-Platz Turnier ↓")
                    if not df_avg_t_platz.empty: st.bar_chart(
                        df_avg_t_platz.set_index("spieler"))
                    st.subheader("Ø-Punkte pro Turnier")
                    st.bar_chart(df_avg_t_pts.set_index("spieler"))
                else:
                    st.info(
                        "💡 Turnier-Metriken sind ausgeblendet, da nach einer spezifischen Strecke gefiltert wird.")
        else:
            st.warning(
                "Keine Renndaten für diese Filterkonstellation gefunden.")

# ==========================================
# TAB 5: VERLAUF & VOLLSTÄNDIGES EDITIEREN
# ==========================================
with tab5:
    st.header("📋 Turnierverlauf")

    query_verlauf = "SELECT t.id as 'Turnier-ID', t.datum as 'Spieldatum', GROUP_CONCAT(s.name, ', ') as 'Teilnehmer' FROM turniere t JOIN turnier_ergebnisse te ON t.id = te.turnier_id JOIN spieler s ON te.spieler_id = s.id GROUP BY t.id ORDER BY t.id DESC"
    df_verlauf = pd.read_sql_query(query_verlauf, conn)

    if df_verlauf.empty:
        st.info("Noch keine Turniere verbucht.")
    else:
        st.write("### Abgeschlossene Turniere")
        st.dataframe(df_verlauf, width="stretch", hide_index=True)

        st.divider()
        st.subheader("🛠️ Turnier & Rennen modifizieren")

        turnier_ids = df_verlauf['Turnier-ID'].tolist()
        ausgewaehltes_turnier = st.selectbox(
            "Turnier-ID:", turnier_ids,
            key="select_edit_id")

        if ausgewaehltes_turnier:
            # TEIL A: TURNIER-ENDPLATZIERUNG EDITIEREN
            st.markdown("#### A) Turnier-Endplatzierungen")
            df_aktuelle_platze = pd.read_sql_query(
                f"SELECT te.spieler_id, s.name, te.endplatzierung FROM turnier_ergebnisse te JOIN spieler s ON te.spieler_id = s.id WHERE te.turnier_id = {ausgewaehltes_turnier}",
                conn)

            edit_endplatzierungen = {}
            for _, row in df_aktuelle_platze.iterrows():
                ep_neu = st.number_input(f"{row['name']}:",
                                         min_value=1, max_value=12,
                                         value=int(row['endplatzierung']),
                                         step=1,
                                         key=f"edit_ep_{ausgewaehltes_turnier}_{row['spieler_id']}")
                edit_endplatzierungen[int(row['spieler_id'])] = int(ep_neu)

            if st.button("Aktualisieren",
                         type="primary"):
                c = conn.cursor()
                for s_id, ep_neu in edit_endplatzierungen.items():
                    c.execute(
                        "UPDATE turnier_ergebnisse SET endplatzierung = ? WHERE turnier_id = ? AND spieler_id = ?",
                        (ep_neu, ausgewaehltes_turnier, s_id))
                conn.commit()
                st.success("Turnier-Endplatzierungen aktualisiert!")
                st.rerun()

            st.divider()

            # TEIL B: RENNEN DIESES TURNIERS EDITIEREN
            st.markdown(
                "#### B) Rennen & Einzelergebnisse")

            # Alle Rennen des Turniers laden
            df_rennen_liste = pd.read_sql_query(
                f"SELECT r.id as rennen_id, s.name as strecken_name FROM rennen r JOIN strecken s ON r.strecken_id = s.id WHERE r.turnier_id = {ausgewaehltes_turnier}",
                conn)

            for idx, r_row in df_rennen_liste.iterrows():
                r_id = int(r_row['rennen_id'])

                with st.expander(
                        f"🏎️ Rennen {idx + 1} (ID #{r_id}): {r_row['strecken_name']}"):
                    # Aktuelle Werte des Rennens auslesen
                    c_race = conn.cursor()
                    c_race.execute(
                        "SELECT strecken_id, gewaehlt_von FROM rennen WHERE id = ?",
                        (r_id,))
                    curr_race = c_race.fetchone()

                    # Strecke ändern
                    alle_strecken_namen = df_strecken["name"].tolist()
                    curr_track_name = \
                        df_strecken[df_strecken["id"] == curr_race[0]][
                            "name"].values[0]
                    neue_strecke_name = st.selectbox("Strecke:",
                                                     alle_strecken_namen,
                                                     index=alle_strecken_namen.index(
                                                         curr_track_name),
                                                     key=f"edit_track_select_{r_id}")
                    neue_strecke_id = int(
                        df_strecken[df_strecken["name"] == neue_strecke_name][
                            "id"].values[0])

                    # Wer hat gewählt ändern
                    df_res_players = pd.read_sql_query(
                        f"SELECT re.spieler_id, s.name, re.platzierung FROM renn_ergebnisse re JOIN spieler s ON re.spieler_id = s.id WHERE re.rennen_id = {r_id}",
                        conn)
                    player_names_in_race = df_res_players["name"].tolist()

                    picker_options = [
                                         "Niemand (Zufall)"] + player_names_in_race
                    curr_picker_index = 0
                    if curr_race[1] is not None:
                        curr_picker_name = \
                            df_spieler[df_spieler["id"] == curr_race[1]][
                                "name"].values[0]
                        if curr_picker_name in picker_options:
                            curr_picker_index = picker_options.index(
                                curr_picker_name)

                    neuer_picker_name = st.selectbox("Gewählt von:",
                                                     picker_options,
                                                     index=curr_picker_index,
                                                     key=f"edit_picker_select_{r_id}")
                    neuer_picker_id = None if neuer_picker_name == "Niemand (Zufall)" else int(
                        df_spieler[df_spieler["name"] == neuer_picker_name][
                            "id"].values[0])

                    # Ergebnisse der Spieler im Rennen editieren
                    st.write("*Platzierungen:*")
                    edit_race_platzierungen = {}
                    for _, p_row in df_res_players.iterrows():
                        p_neu = st.number_input(f"{p_row['name']}:",
                                                min_value=1, max_value=12,
                                                value=int(
                                                    p_row['platzierung']),
                                                step=1,
                                                key=f"edit_race_p_{r_id}_{p_row['spieler_id']}")
                        edit_race_platzierungen[
                            int(p_row['spieler_id'])] = int(p_neu)

                    if st.button(f"Speichern",
                                 key=f"btn_save_race_{r_id}"):
                        if hat_duplikate(
                                list(edit_race_platzierungen.values())):
                            st.error(
                                "❌ Fehler: Platzierungen dürfen nicht doppelt vergeben werden!")
                        else:
                            c = conn.cursor()
                            # 1. Update des Rennens (Strecke & Wahl)
                            c.execute(
                                "UPDATE rennen SET strecken_id = ?, gewaehlt_von = ? WHERE id = ?",
                                (neue_strecke_id, neuer_picker_id, r_id))
                            # 2. Update der Platzierungen
                            for s_id, pl_neu in edit_race_platzierungen.items():
                                c.execute(
                                    "UPDATE renn_ergebnisse SET platzierung = ? WHERE rennen_id = ? AND spieler_id = ?",
                                    (pl_neu, r_id, s_id))
                            conn.commit()
                            st.success(
                                f"Rennen #{r_id} erfolgreich aktualisiert!")
                            st.rerun()

            st.divider()
            if st.button("❌ Löschen",
                         type="secondary",
                         key=f"btn_del_{ausgewaehltes_turnier}"):
                c = conn.cursor()
                c.execute("DELETE FROM turniere WHERE id = ?;",
                          (ausgewaehltes_turnier,))
                conn.commit()
                st.success(f"Turnier #{ausgewaehltes_turnier} wurde gelöscht.")
                st.rerun()

conn.close()
