import streamlit as st
import random
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import time
import json
import os

# --- 0. ALAPOK ---
try:
    from groq import Groq
except ImportError:
    Groq = None

DB_FILE = "party_state.json"

# --- 1. ADATBÁZIS KEZELÉS ---
def init_db():
    if not os.path.exists(DB_FILE):
        reset_db()

def reset_db():
    state = {
        "game_phase": "LOBBY",
        "players": ["Játékos 1", "Játékos 2"], 
        "timelines": {"Játékos 1": [], "Játékos 2": []},
        "deck": [],
        "current_mystery_song": None,
        "turn_index": 0,
        "game_msg": "",
        "success": False,
        "waiting_for_reveal": False
    }
    with open(DB_FILE, 'w') as f: json.dump(state, f)

def load_state():
    if not os.path.exists(DB_FILE): init_db()
    try:
        with open(DB_FILE, 'r') as f: return json.load(f)
    except: return {}

def save_state(state):
    with open(DB_FILE, 'w') as f: json.dump(state, f)

# --- 2. SPOTIFY & AI ---
def load_spotify_tracks(api_id, api_secret, playlist_url):
    try:
        auth_manager = SpotifyClientCredentials(client_id=api_id, client_secret=api_secret)
        sp = spotipy.Spotify(auth_manager=auth_manager)
        if "?" in playlist_url: clean_url = playlist_url.split("?")[0]
        else: clean_url = playlist_url
        resource_id = clean_url.split("/")[-1]
        tracks_data = []
        
        if "album" in clean_url:
            results = sp.album_tracks(resource_id)
            album_info = sp.album(resource_id)
            year = int(album_info['release_date'][:4])
            items = results['items']
            while results['next']:
                results = sp.next(results)
                items.extend(results['items'])
            for track in items:
                tracks_data.append({"artist": track['artists'][0]['name'], "title": track['name'], "year": year, "spotify_id": track['id']})
        elif "playlist" in clean_url:
            results = sp.playlist_items(resource_id)
            items = results['items']
            while results['next']:
                results = sp.next(results)
                items.extend(results['items'])
            for item in items:
                t = item['track']
                if t and t['album']['release_date']:
                    tracks_data.append({"artist": t['artists'][0]['name'], "title": t['name'], "year": int(t['album']['release_date'][:4]), "spotify_id": t['id']})
        return tracks_data
    except: return []

def fix_card_with_groq(card, api_key):
    if not api_key or Groq is None: return card
    try:
        client = Groq(api_key=api_key)
        prompt = f"Fact Check: ORIGINAL release year of '{card['title']}' by '{card['artist']}'? Reply ONLY 4-digit year."
        completion = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": prompt}], temperature=0, max_tokens=10)
        text = completion.choices[0].message.content.strip()
        if text.isdigit():
            ai_year = int(text)
            if 1900 < ai_year <= 2025 and ai_year != card['year']:
                card['year'] = ai_year
                card['fixed_by_ai'] = True
    except: pass
    return card

# --- 3. UI BEÁLLÍTÁS ---
st.set_page_config(page_title="Hitster Party", page_icon="🎵", layout="wide")

st.markdown("""
<style>
    .stApp { background: radial-gradient(circle at center, #2b2d42 0%, #1a1a2e 100%); color: #edf2f4; }
    #MainMenu, footer {visibility: hidden;}
    .timeline-card {
        background: linear-gradient(180deg, #1DB954 0%, #117a35 100%);
        color: white; padding: 10px; border-radius: 10px; text-align: center;
        border: 1px solid rgba(255,255,255,0.2); margin-bottom: 5px;
        min-height: 100px; display: flex; flex-direction: column; justify-content: center;
    }
    .card-year { font-size: 1.8em; font-weight: 900; border-bottom: 1px solid rgba(255,255,255,0.3); }
    .card-title { font-weight: bold; font-size: 1.1em; line-height: 1.2; }
    
    /* JAVÍTOTT MOBIL GOMB STÍLUS */
    .mob-insert-btn { 
        width: 100%; padding: 15px; margin: 5px 0; 
        background: rgba(0, 212, 255, 0.15); border: 2px dashed #00d4ff; 
        color: white; font-size: 1.1em; border-radius: 8px; cursor: pointer; text-align: center;
    }
    .mob-insert-btn:hover { background: #00d4ff; color: black; }
    
    .mob-card-box {
        background: rgba(255,255,255,0.05); padding: 10px; border-radius: 8px;
        text-align: center; margin-bottom: 5px; border: 1px solid #444;
    }

    .tv-status {
        padding: 20px; border-radius: 15px; text-align: center; 
        font-size: 1.5em; font-weight: bold; margin: 20px 0;
        background: rgba(0,0,0,0.5); border: 2px solid #555; animation: pulse 2s infinite;
    }
    @keyframes pulse { 0% {border-color: #555;} 50% {border-color: #00d4ff;} 100% {border-color: #555;} }
</style>
""", unsafe_allow_html=True)

# --- 4. SZEREP VÁLASZTÁS ---
if 'user_role' not in st.session_state:
    st.session_state.user_role = "tv"

with st.sidebar:
    st.title("🎛️ MENÜ")
    role_selection = st.radio("Ki vagy te?", ["📺 TV (Kijelző)", "📱 Játékos (Telefon)"])
    
    new_role = "tv" if "TV" in role_selection else "player"
    if new_role != st.session_state.user_role:
        st.session_state.user_role = new_role
        st.rerun()

    st.divider()

    if st.session_state.user_role == "tv":
        st.header("⚙️ Beállítások")
        api_id = st.text_input("Spotify ID", type="password")
        api_secret = st.text_input("Spotify Secret", type="password")
        groq_key = st.text_input("Groq Key", type="password")
        pl_url = st.text_input("Playlist URL")
        
        if st.button("🚀 ÚJ JÁTÉK INDÍTÁSA", type="primary"):
            if api_id and api_secret and pl_url:
                with st.spinner("Kártyák keverése..."):
                    deck = load_spotify_tracks(api_id, api_secret, pl_url)
                    if deck:
                        random.shuffle(deck)
                        state = {
                            "game_phase": "GUESSING",
                            "players": ["Játékos 1", "Játékos 2"], 
                            "timelines": {"Játékos 1": [], "Játékos 2": []},
                            "deck": deck,
                            "current_mystery_song": None,
                            "turn_index": 0,
                            "game_msg": "",
                            "success": False,
                            "waiting_for_reveal": False
                        }
                        for p in state['players']:
                            if state['deck']:
                                c = state['deck'].pop()
                                if groq_key: c = fix_card_with_groq(c, groq_key)
                                state['timelines'][p].append(c)
                        if state['deck']:
                            first = state['deck'].pop()
                            if groq_key: first = fix_card_with_groq(first, groq_key)
                            state['current_mystery_song'] = first
                        
                        save_state(state)
                        st.rerun()

# --- 5. JÁTÉK NÉZETEK ---
state = load_state()

# ==========================
# 📺 TV NÉZET
# ==========================
if st.session_state.user_role == "tv":
    st.title("📺 Hitster Party")

    if state.get('game_phase') == "LOBBY":
        st.info("👈 Indítsd el a játékot a bal oldali menüben!")
        st.write("Csatlakozáshoz nyisd meg ezt az oldalt telefonon, és válaszd a 'Játékos' módot.")

    elif state.get('game_phase') == "GUESSING":
        curr_p = state['players'][state['turn_index'] % len(state['players'])]
        song = state['current_mystery_song']
        
        st.markdown(f"### 🎶 Most játszik: {song['artist']} - ???")
        st.components.v1.iframe(f"https://open.spotify.com/embed/track/{song['spotify_id']}", height=80)
        
        st.markdown(f"<div class='tv-status'>👉 {curr_p} tippel a telefonján...</div>", unsafe_allow_html=True)
        
        timeline = state['timelines'][curr_p]
        cols = st.columns(len(timeline))
        for i, card in enumerate(timeline):
            cols[i].markdown(f"""
            <div class='timeline-card'>
                <div class='card-year'>{card['year']}</div>
                <div class='card-title'>{card['title']}</div>
            </div>
            """, unsafe_allow_html=True)
            
        st.divider()
        
        col1, col2 = st.columns([3, 1])
        with col2:
            # GOMB: Erre kell kattintani, ha a játékos végzett a telefonon!
            if st.button("👀 MUTASD AZ EREDMÉNYT!", type="primary", use_container_width=True):
                state = load_state() 
                if state.get('waiting_for_reveal'):
                    state['game_phase'] = "REVEAL"
                    state['waiting_for_reveal'] = False
                    save_state(state)
                    st.rerun()
                else:
                    st.warning("⚠️ Még nem tippeltek!")

    elif state.get('game_phase') == "REVEAL":
        song = state['current_mystery_song']
        color = "#00ff00" if state['success'] else "#ff4b4b"
        msg = "TALÁLT! 🎉" if state['success'] else "NEM TALÁLT... 😢"
        
        st.markdown(f"<h1 style='text-align:center; color:{color}; font-size:3em;'>{msg}</h1>", unsafe_allow_html=True)
        st.markdown(f"<h2 style='text-align:center'>{song['artist']} - {song['title']} ({song['year']})</h2>", unsafe_allow_html=True)
        st.components.v1.iframe(f"https://open.spotify.com/embed/track/{song['spotify_id']}", height=80)
        
        curr_p = state['players'][state['turn_index'] % len(state['players'])]
        timeline = state['timelines'][curr_p]
        
        cols = st.columns(len(timeline))
        for i, card in enumerate(timeline):
            style = "border: 3px solid #ffd700; transform: scale(1.05);" if card == song else ""
            if i < len(cols):
                cols[i].markdown(f"""
                <div class='timeline-card' style='{style}'>
                    <div class='card-year'>{card['year']}</div>
                    <div class='card-title'>{card['title']}</div>
                </div>
                """, unsafe_allow_html=True)

        st.divider()
        if st.button("➡️ KÖVETKEZŐ KÖR", type="primary", use_container_width=True):
            state['turn_index'] += 1
            if state['deck']:
                next_song = state['deck'].pop()
                if groq_key: next_song = fix_card_with_groq(next_song, groq_key)
                state['current_mystery_song'] = next_song
                state['game_phase'] = "GUESSING"
            else:
                state['game_phase'] = "GAME_OVER"
            save_state(state)
            st.rerun()

    elif state.get('game_phase') == "GAME_OVER":
        st.title("🏆 JÁTÉK VÉGE!")
        st.balloons()

# ==========================
# 📱 TELEFON NÉZET
# ==========================
elif st.session_state.user_role == "player":
    st.header("📱 Játékos")
    
    if 'my_name' not in st.session_state:
        temp_state = load_state()
        players_list = temp_state.get('players', ["Játékos 1", "Játékos 2"])
        selected_player = st.selectbox("Ki vagy te?", players_list)
        if st.button("Belépés", use_container_width=True):
            st.session_state.my_name = selected_player
            st.rerun()
    else:
        me = st.session_state.my_name
        st.info(f"Belépve mint: **{me}**")
        
        state = load_state() # Mindig frissít gombnyomásra
        
        if state.get('game_phase') == "GUESSING":
            curr_p = state['players'][state['turn_index'] % len(state['players'])]
            
            if curr_p == me:
                st.success("🔴 TE JÖSSZ! Válassz helyet:")
                
                timeline = state['timelines'][me]
                
                # JAVÍTOTT CIKLUS (Nincs duplikáció!)
                # 1. Gomb az elejére
                if st.button("⬇️ IDE ILLESZTEM (Elejére) ⬇️", key="mob_btn_start", use_container_width=True):
                    # --- Tippelés logika ---
                    song = state['current_mystery_song']
                    # 0. helyre rakjuk
                    next_ok = (len(timeline) == 0) or (timeline[0]['year'] >= song['year'])
                    state['success'] = next_ok
                    state['game_msg'] = "TALÁLT!" if state['success'] else "NEM..."
                    if state['success']: state['timelines'][me].insert(0, song)
                    state['waiting_for_reveal'] = True
                    save_state(state)
                    st.rerun()

                # 2. Kártyák és a utánuk lévő gombok
                for i, card in enumerate(timeline):
                    # Kártya megjelenítése
                    st.markdown(f"""
                    <div class='mob-card-box'>
                        <div style='font-size:1.5em; font-weight:bold'>{card['year']}</div>
                        <div>{card['title']}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Gomb a kártya után
                    if st.button(f"⬇️ IDE ILLESZTEM ⬇️", key=f"mob_btn_{i+1}", use_container_width=True):
                        # --- Tippelés logika ---
                        song = state['current_mystery_song']
                        pos = i + 1
                        prev_ok = (timeline[pos-1]['year'] <= song['year'])
                        # Ha ez az utolsó hely, akkor a következő mindig OK
                        next_ok = (pos == len(timeline)) or (timeline[pos]['year'] >= song['year'])
                        
                        state['success'] = (prev_ok and next_ok)
                        state['game_msg'] = "TALÁLT!" if state['success'] else "NEM..."
                        if state['success']: state['timelines'][me].insert(pos, song)
                        state['waiting_for_reveal'] = True
                        save_state(state)
                        st.rerun()

            else:
                st.warning(f"Most {curr_p} gondolkodik...")
                if st.button("🔄 Frissítés", use_container_width=True): st.rerun()
                
        elif state.get('game_phase') == "REVEAL":
            # MOST MÁR A TELEFONON IS LÁTSZIK AZ EREDMÉNY!
            song = state['current_mystery_song']
            color = "green" if state['success'] else "red"
            msg = "TALÁLT! 🎉" if state['success'] else "NEM TALÁLT... 😢"
            
            st.markdown(f"<h2 style='text-align:center; color:{color};'>{msg}</h2>", unsafe_allow_html=True)
            st.markdown(f"<div class='mob-card-box' style='border-color:{color}'>HELYES ÉV: <b>{song['year']}</b><br>{song['title']}</div>", unsafe_allow_html=True)
            
            st.info("Nézd a TV-t a részletekért!")
            if st.button("🔄 Frissítés", use_container_width=True): st.rerun()
        
        else:
            st.write("Várakozás a játékra...")
            if st.button("🔄 Frissítés", use_container_width=True): st.rerun()
