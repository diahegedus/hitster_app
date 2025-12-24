import streamlit as st
import random
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# --- 1. KONFIGURÁCIÓ & TV STÍLUS (CSS) ---
st.set_page_config(page_title="Hitster TV Party", page_icon="📺", layout="wide")

# Itt varázsoljuk át a kinézetet
st.markdown("""
<style>
    /* Háttér és alap színek - Sötét téma a TV miatt */
    .stApp {
        background: linear-gradient(135deg, #1e1e2e 0%, #2d2b55 100%);
        color: white;
    }
    
    /* Eredményjelző kártyák a tetején */
    .score-card {
        background-color: rgba(255, 255, 255, 0.1);
        border-radius: 15px;
        padding: 15px;
        text-align: center;
        border: 2px solid transparent;
        transition: transform 0.2s;
    }
    .score-active {
        border: 3px solid #00d4ff; /* Kiemelés, ha ő jön */
        background-color: rgba(0, 212, 255, 0.15);
        transform: scale(1.05);
        box-shadow: 0 0 15px #00d4ff;
    }
    .score-num {
        font-size: 2.5em;
        font-weight: bold;
        color: #ffcc00;
        margin: 0;
    }
    .score-name {
        font-size: 1.2em;
        font-weight: 600;
        margin: 0;
    }

    /* Idővonal kártyák */
    .timeline-card {
        background: linear-gradient(180deg, #1DB954 0%, #158a3e 100%);
        color: white;
        padding: 15px;
        border-radius: 12px;
        text-align: center;
        margin: 5px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    .timeline-year {
        font-size: 1.8em;
        font-weight: 900;
        border-bottom: 1px solid rgba(255,255,255,0.3);
        margin-bottom: 5px;
        padding-bottom: 5px;
    }
    .timeline-info {
        font-size: 0.9em;
        line-height: 1.2;
    }
    
    /* A rejtélyes dal kártyája */
    .mystery-box {
        background-color: #333;
        border: 3px dashed #ff4b4b;
        border-radius: 15px;
        padding: 20px;
        text-align: center;
        margin: 20px 0;
    }

    /* Gombok tuningolása */
    div.stButton > button {
        background-color: #ff4b4b;
        color: white;
        font-size: 20px !important;
        padding: 10px 24px;
        border-radius: 30px;
        border: none;
        box-shadow: 0 4px 0 #b33232;
        transition: all 0.1s;
    }
    div.stButton > button:active {
        box-shadow: none;
        transform: translateY(4px);
    }
    /* Kisebb gombok az idővonal közé */
    div[data-testid="column"] button {
        background-color: #444;
        box-shadow: none;
        font-size: 16px !important;
        padding: 5px;
    }
    div[data-testid="column"] button:hover {
        background-color: #00d4ff;
    }

</style>
""", unsafe_allow_html=True)

# --- 2. SPOTIFY LOGIKA (Ugyanaz maradt) ---
def load_spotify_playlist(client_id, client_secret, playlist_url):
    try:
        auth_manager = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
        sp = spotipy.Spotify(auth_manager=auth_manager)
        
        # Kezeli a ?si=... és egyéb paramétereket
        pl_id = playlist_url.split('/')[-1].split('?')[0]
        
        results = sp.playlist_items(pl_id)
        tracks = results['items']
        while results['next']:
            results = sp.next(results)
            tracks.extend(results['items'])
            
        music_db = []
        for item in tracks:
            track = item['track']
            if not track: continue
            
            # Évszám
            if track['album']['release_date']:
                year = track['album']['release_date'].split('-')[0]
                if year.isdigit():
                    music_db.append({
                        "artist": track['artists'][0]['name'],
                        "title": track['name'],
                        "year": int(year),
                        "spotify_id": track['id']
                    })
        return music_db
    except Exception as e:
        st.error(f"Hiba: {e}")
        return []

# --- 3. JÁTÉK ÁLLAPOT (STATE) ---
if 'players' not in st.session_state:
    st.session_state.players = ["Jorgosz", "Lilla", "Józsi"]

if 'game_started' not in st.session_state:
    st.session_state.game_started = False

# --- 4. BEÁLLÍTÁSOK (SIDEBAR) ---
with st.sidebar:
    st.header("⚙️ DJ Pult")
    st.write("Add meg a Spotify kulcsokat:")
    api_id = st.text_input("Client ID", type="password")
    api_secret = st.text_input("Client Secret", type="password")
    pl_url = st.text_input("Playlist Link", value="https://open.spotify.com/playlist/2WQxrq5bmHMlVuzvtwwywV?si=LfJsaghwQqOweKjygM8vMA")
    
    if st.button("🚀 BULI INDÍTÁSA", type="primary"):
        if api_id and api_secret and pl_url:
            with st.spinner("Zenék betöltése..."):
                deck = load_spotify_playlist(api_id, api_secret, pl_url)
                if deck:
                    random.shuffle(deck)
                    st.session_state.deck = deck
                    # Kezdő lap kiosztása
                    st.session_state.timelines = {p: [st.session_state.deck.pop()] for p in st.session_state.players}
                    st.session_state.turn_index = 0
                    st.session_state.current_mystery_song = st.session_state.deck.pop()
                    st.session_state.game_phase = "GUESSING"
                    st.session_state.game_started = True
                    st.rerun()
        else:
            st.error("Hiányzó adatok!")
            
    st.divider()
    st.write("Játékosok módosítása (Újraindítás kell):")
    st.session_state.players[0] = st.text_input("Játékos 1", st.session_state.players[0])
    st.session_state.players[1] = st.text_input("Játékos 2", st.session_state.players[1])
    st.session_state.players[2] = st.text_input("Játékos 3", st.session_state.players[2])

# --- 5. FŐ JÁTÉKTÉR ---

if not st.session_state.game_started:
    st.title("📺 TV HITSTER PARTY")
    st.markdown("### 👋 Szia! Kösd rá a gépet a TV-re!")
    st.info("Az indításhoz használd az oldalsávot a bal oldalon. (Mobilon a bal felső sarok >)")

else:
    # VÁLTOZÓK
    current_player_idx = st.session_state.turn_index
    current_player_name = st.session_state.players[current_player_idx]
    
    # --- EREDMÉNYJELZŐ (SCOREBOARD) ---
    st.markdown("<br>", unsafe_allow_html=True)
    score_cols = st.columns(len(st.session_state.players))
    
    for idx, player in enumerate(st.session_state.players):
        score = len(st.session_state.timelines[player]) # A pont = kártyák száma
        is_active = (idx == current_player_idx)
        active_class = "score-active" if is_active else ""
        
        with score_cols[idx]:
            st.markdown(f"""
            <div class="score-card {active_class}">
                <p class="score-name">{player}</p>
                <p class="score-num">{score}</p>
                <p style="font-size:0.8em; margin:0;">kártya</p>
            </div>
            """, unsafe_allow_html=True)

    st.divider()

    # --- JÁTÉK LOGIKA ---
    def handle_guess(insert_index):
        p_name = st.session_state.players[st.session_state.turn_index]
        timeline = st.session_state.timelines[p_name]
        song = st.session_state.current_mystery_song
        
        # Szabály ellenőrzés
        prev_ok = (insert_index == 0) or (timeline[insert_index-1]['year'] <= song['year'])
        next_ok = (insert_index == len(timeline)) or (timeline[insert_index]['year'] >= song['year'])
        
        if prev_ok and next_ok:
            st.session_state.timelines[p_name].insert(insert_index, song)
            st.session_state.game_msg = f"IGEN! ELTALÁLTAD! 🎉 ({song['year']})"
            st.session_state.success = True
        else:
            st.session_state.game_msg = f"SAJNOS NEM! 😭 Ez a dal {song['year']}-es volt."
            st.session_state.success = False
            
        st.session_state.game_phase = "REVEAL"

    def next_turn():
        st.session_state.turn_index = (st.session_state.turn_index + 1) % 3
        if st.session_state.deck:
            st.session_state.current_mystery_song = st.session_state.deck.pop()
            st.session_state.game_phase = "GUESSING"
        else:
            st.session_state.game_phase = "GAME_OVER"
        st.rerun()

    # --- UI MEGJELENÍTÉS ---
    
    if st.session_state.game_phase == "GUESSING":
        st.markdown(f"<h2 style='text-align: center;'>🎧 {current_player_name}, te jössz!</h2>", unsafe_allow_html=True)
        
        # Zenelejátszó középen
        mys_song = st.session_state.current_mystery_song
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown(f"""
            <div class="mystery-box">
                <h3 style="color:white; margin:0;">{mys_song['artist']}</h3>
                <h2 style="color:#ff4b4b; font-size:2em; margin:0;">{mys_song['title']}</h2>
                <p>Mikor jelent meg?</p>
            </div>
            """, unsafe_allow_html=True)
            # Spotify Player
            st.components.v1.iframe(f"https://open.spotify.com/embed/track/{mys_song['spotify_id']}?utm_source=generator", height=80)

        # Idővonal + Gombok
        st.write("")
        st.markdown("### 👇 Válassz helyet az idővonaladon:")
        
        timeline = st.session_state.timelines[current_player_name]
        
        # Dinamikus oszlopok: Gomb - Kártya - Gomb - Kártya...
        t_cols = st.columns(len(timeline) * 2 + 1)
        
        for i in range(len(timeline) + 1):
            with t_cols[i*2]:
                st.markdown("<br>", unsafe_allow_html=True) # Kis helyigazítás
                if st.button("IDE", key=f"btn_{i}", use_container_width=True):
                    handle_guess(i)
                    st.rerun()
            
            if i < len(timeline):
                card = timeline[i]
                with t_cols[i*2+1]:
                    st.markdown(f"""
                    <div class="timeline-card">
                        <div class="timeline-year">{card['year']}</div>
                        <div class="timeline-info">{card['artist']}<br><i>{card['title']}</i></div>
                    </div>
                    """, unsafe_allow_html=True)

    elif st.session_state.game_phase == "REVEAL":
        # EREDMÉNYHIRDETÉS
        if st.session_state.success:
            st.balloons()
            st.success(st.session_state.game_msg)
        else:
            st.error(st.session_state.game_msg)
            
        st.markdown(f"### Így néz ki most {current_player_name} idővonala:")
        
        timeline = st.session_state.timelines[current_player_name]
        d_cols = st.columns(len(timeline))
        
        for idx, card in enumerate(timeline):
            with d_cols[idx]:
                # Ha ez volt a nyertes kártya, legyen arany kerete
                style = "border: 4px solid #ffcc00; transform: scale(1.1);" if (card == st.session_state.current_mystery_song and st.session_state.success) else ""
                
                st.markdown(f"""
                <div class="timeline-card" style='{style}'>
                    <div class="timeline-year">{card['year']}</div>
                    <div class="timeline-info">{card['artist']}<br><i>{card['title']}</i></div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("<br><br>", unsafe_allow_html=True)
        # Nagy gomb középen
        c1, c2, c3 = st.columns([1, 2, 1])
        with c2:
            st.button("KÖVETKEZŐ JÁTÉKOS ➡️", on_click=next_turn, use_container_width=True)

    elif st.session_state.game_phase == "GAME_OVER":
        st.title("🏆 VÉGE A JÁTÉKNAK!")
        st.balloons()
        
        # Győztes keresése
        winner = max(st.session_state.timelines, key=lambda k: len(st.session_state.timelines[k]))
        st.markdown(f"<h1 style='text-align: center; color: gold;'>A GYŐZTES: {winner}</h1>", unsafe_allow_html=True)
        
        if st.button("ÚJ JÁTÉK INDÍTÁSA", use_container_width=True):
            st.session_state.clear()
            st.rerun()
