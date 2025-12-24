import streamlit as st
import random

# --- 1. Zenei Adatbázis (Ezt bővítheted!) ---
# A Spotify linkek helyett most csak címeket használunk demo gyanánt.
# Ha van Spotify beágyazó kódod, azt is berakhatod az "url" mezőbe.
MUSIC_DB = [
    {"artist": "Queen", "title": "Bohemian Rhapsody", "year": 1975, "spotify_id": "7tFiyTwD0nx5a1eklYtX2J"},
    {"artist": "Britney Spears", "title": "Toxic", "year": 2003, "spotify_id": "6I9VzXrHxO9rA9A5euc8Ak"},
    {"artist": "Michael Jackson", "title": "Billie Jean", "year": 1982, "spotify_id": "5ChkMS8OtdzJeqyybCc9R5"},
    {"artist": "The Beatles", "title": "Hey Jude", "year": 1968, "spotify_id": "0aym2LBJBk9WA64cWCL9F7"},
    {"artist": "Adele", "title": "Rolling in the Deep", "year": 2010, "spotify_id": "1CkvWZme3pRgbzaxZnTlFW"},
    {"artist": "Nirvana", "title": "Smells Like Teen Spirit", "year": 1991, "spotify_id": "1f3yAtsJtY87CTmM8RLnxf"},
    {"artist": "Eminem", "title": "Lose Yourself", "year": 2002, "spotify_id": "5Z01UMHmPV4Nas8XRbLrRn"},
    {"artist": "Abba", "title": "Dancing Queen", "year": 1976, "spotify_id": "0GjEhVFGZW8afUYGk4Lu1Y"},
    {"artist": "Elvis Presley", "title": "Jailhouse Rock", "year": 1957, "spotify_id": "4gphxUgq0JSFv2BCLhNDiE"},
    {"artist": "Dua Lipa", "title": "Levitating", "year": 2020, "spotify_id": "39LLxExYz6ewLAcYrzQQyP"},
]

# --- 2. Konfiguráció ---
st.set_page_config(page_title="Hitster Klón", page_icon="🎵", layout="wide")

st.markdown("""
<style>
    .timeline-card {
        background-color: #1DB954; /* Spotify zöld */
        color: white;
        padding: 10px;
        border-radius: 8px;
        text-align: center;
        margin: 5px;
        font-weight: bold;
    }
    .mystery-card {
        border: 2px dashed #333;
        padding: 20px;
        text-align: center;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

# --- 3. Inicializálás (State) ---

if 'players' not in st.session_state:
    # ITT vannak az új nevek:
    st.session_state.players = ["Jorgosz", "Lilla", "Józsi"]

if 'timelines' not in st.session_state:
    # Mindenki kap egy kezdő kártyát
    random.shuffle(MUSIC_DB)
    st.session_state.deck = MUSIC_DB.copy()
    
    # Ez a sor most már automatikusan létrehozza az idővonalat 
    # a fenti "players" lista alapján (nem kell kézzel beírni a neveket):
    st.session_state.timelines = {
        player: [st.session_state.deck.pop()] 
        for player in st.session_state.players
    }

if 'turn_index' not in st.session_state:
    st.session_state.turn_index = 0

if 'current_mystery_song' not in st.session_state:
    if st.session_state.deck:
        st.session_state.current_mystery_song = st.session_state.deck.pop()
    else:
        st.session_state.current_mystery_song = None

if 'game_phase' not in st.session_state:
    st.session_state.game_phase = "GUESSING"

# --- 4. Logika ---

def check_guess(player_timeline, inserted_index, mystery_year):
    """
    Ellenőrzi, hogy a mystery_year jó helyre került-e az idővonalon.
    inserted_index: 0 jelenti a lista elejét, len(lista) a végét.
    """
    # 1. Ellenőrizzük az előtte lévő kártyát (ha van)
    if inserted_index > 0:
        prev_card = player_timeline[inserted_index - 1]
        if prev_card['year'] > mystery_year:
            return False # Hiba: a korábbi kártya frissebb, mint az új
            
    # 2. Ellenőrizzük a utána lévő kártyát (ha van)
    if inserted_index < len(player_timeline):
        next_card = player_timeline[inserted_index]
        if next_card['year'] < mystery_year:
            return False # Hiba: a következő kártya régebbi, mint az új
            
    return True

def handle_guess(insert_index):
    current_player = st.session_state.players[st.session_state.turn_index]
    timeline = st.session_state.timelines[current_player]
    song = st.session_state.current_mystery_song
    
    is_correct = check_guess(timeline, insert_index, song['year'])
    
    st.session_state.last_result = {
        "player": current_player,
        "song": song,
        "success": is_correct,
        "timeline_before": list(timeline) # Másolat mentése
    }
    
    if is_correct:
        # Beszúrjuk a helyes pozícióba
        st.session_state.timelines[current_player].insert(insert_index, song)
        st.session_state.game_msg = "✅ Helyes! A kártya bekerült az idővonaladba."
    else:
        st.session_state.game_msg = f"❌ Sajnos nem! A dal éve {song['year']} volt."
        # Hitster szabály: ha rontasz, a kártya kimegy a játékból (vagy eldobod)
    
    st.session_state.game_phase = "REVEAL"

def next_turn():
    # Következő játékos, új dal
    st.session_state.turn_index = (st.session_state.turn_index + 1) % 3
    if st.session_state.deck:
        st.session_state.current_mystery_song = st.session_state.deck.pop()
        st.session_state.game_phase = "GUESSING"
        st.session_state.game_msg = ""
    else:
        st.session_state.game_phase = "GAME_OVER"
    st.rerun()

# --- 5. UI Megjelenítés ---

st.title("🎵 Hitster Party Streamlit")

current_player = st.session_state.players[st.session_state.turn_index]
mys_song = st.session_state.current_mystery_song

# --- Fejléc: Ki jön? ---
st.info(f"Most **{current_player}** következik!")

# --- A REJTÉLYES DAL (DJ PULT) ---
if st.session_state.game_phase != "GAME_OVER":
    st.subheader("🎧 A DJ ezt játssza:")
    
    # Spotify beágyazás (Iframe) - Ez játssza le a zenét
    # Megjegyzés: Ez csak 30 mp preview-t ad ingyenesen, de játékhoz pont elég.
    if mys_song:
        spotify_url = f"https://open.spotify.com/embed/track/{mys_song['spotify_id']}?utm_source=generator"
        st.components.v1.iframe(spotify_url, height=80)
        
        st.markdown(f"""
        <div class='mystery-card'>
            <h3>{mys_song['artist']} - {mys_song['title']}</h3>
            <p style='color:gray'>(Mikor jelent meg?)</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.error("Elfogyott a pakli!")

# --- JÁTÉKOS IDŐVONALA ---
st.subheader(f"{current_player} idővonala:")

timeline = st.session_state.timelines[current_player]

# Itt jelenítjük meg a kártyákat és a GOMBOKAT közéjük
if st.session_state.game_phase == "GUESSING":
    st.write("Hova illeszted be az új dalt?")
    
    # Dinamikusan generáljuk a gombokat és a kártyákat felváltva
    # Példa: [GOMB 0] -> [Kártya 1990] -> [GOMB 1] -> [Kártya 2000] -> [GOMB 2]
    
    cols = st.columns(len(timeline) * 2 + 1)
    
    for i in range(len(timeline) + 1):
        # Beszúrási pont gombja
        with cols[i*2]: 
            if st.button("IDE 👇", key=f"btn_{i}"):
                handle_guess(i)
                st.rerun()
        
        # Maga a kártya (ha még nincs a végén)
        if i < len(timeline):
            card = timeline[i]
            with cols[i*2 + 1]:
                st.markdown(f"<div class='timeline-card'>{card['year']}<br>{card['artist']}<br>{card['title']}</div>", unsafe_allow_html=True)

elif st.session_state.game_phase == "REVEAL":
    # Eredményhirdetés fázis
    st.markdown(f"### {st.session_state.game_msg}")
    
    # Megmutatjuk az új állapotot
    display_cols = st.columns(len(timeline))
    for idx, card in enumerate(timeline):
        with display_cols[idx]:
             # Ha ez volt a most berakott kártya, emeljük ki
            is_new = (card == mys_song and "Helyes" in st.session_state.game_msg)
            border = "border: 4px solid gold;" if is_new else ""
            st.markdown(f"<div class='timeline-card' style='{border}'>{card['year']}<br>{card['artist']}<br>{card['title']}</div>", unsafe_allow_html=True)

    st.button("Következő kör ➡️", on_click=next_turn, type="primary")

elif st.session_state.game_phase == "GAME_OVER":
    st.success("Vége a játéknak! Szép munka.")
    # Itt lehetne kiírni, kinek van a leghosszabb idővonala
    winner = max(st.session_state.timelines, key=lambda k: len(st.session_state.timelines[k]))
    st.balloons()
    st.markdown(f"# A győztes: {winner} ({len(st.session_state.timelines[winner])} kártyával)")
    
    if st.button("Új játék"):
        st.session_state.clear()
        st.rerun()

# --- Debug / Egyéb játékosok állása (Sidebar) ---
with st.sidebar:
    st.header("Többi játékos idővonala")
    for p in st.session_state.players:
        if p != current_player:
            st.write(f"**{p}:**")
            # Csak az éveket írjuk ki listaként, hogy ne foglaljon sok helyet
            years = [str(c['year']) for c in st.session_state.timelines[p]]
            st.write(" ➡️ ".join(years))
            st.divider()
