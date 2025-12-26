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
    # Ez az alapállapot
    state = {
        "game_phase": "LOBBY",
        "players": ["Játékos 1", "Játékos 2"], # Alap nevek
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
        
        # Egyszerűsített logika a stabilitásért
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
        # Szigorú prompt a 4 jegyű számhoz
        prompt = f"What is the ORIGINAL release year of '{card['title']}' by '{card['artist']}'? Return ONLY the year (e.g. 1980)."
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
    
    /* MOBIL GOMBOK */
    .mob-btn { 
        width: 100%; padding: 20px; margin: 10px 0; 
        background: rgba(255,255,255,0.1); border: 2px dashed #777; 
        color: white; font-size: 1.5em; border-radius: 12px; cursor: pointer; text-align: center;
    }
    .mob-btn:active { background: #00d4ff; color: black; }
    
    /* TV STATUS */
    .tv-status {
        padding: 20px; border-radius: 15px; text-align: center; 
        font-size: 1.5em; font-weight: bold; margin: 20px 0;
        background: rgba(0,0,0,0.5); border: 2px solid #555; animation: pulse 2s infinite;
    }
    @keyframes pulse { 0% {border-color: #555;} 50% {border-color: #00d4ff;} 100% {border-color: #555;} }
</style>
""", unsafe_allow_html=True)

# --- 4. SZEREP VÁLASZTÁS (AZ OLDALSÁVON) ---
if 'user_role' not in st.session_state:
    st.session_state.user_role = "tv" # Alapértelmezett

with st.sidebar:
    st.title("🎛️ MENÜ")
    role_selection = st.radio("Ki vagy te?", ["📺 TV (Kijelző)", "📱 Játékos (Telefon)"])
    
    new_role = "tv" if "TV" in role_selection else "player"
    if new_role != st.session_state.user_role:
        st.session_state.user_role = new_role
        st.rerun()

    st.divider()

    # TV ADMIN GOMBOK
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
                        # Osztás
                        for p in state['players']:
                            if state['deck']:
                                c = state['deck'].pop()
                                if groq_key: c = fix_card_with_groq(c, groq_key)
                                state['timelines'][p].append(c)
                        # Első dal
                        if state['deck']:
                            first = state['deck'].pop()
                            if groq_key: first = fix_card_with_groq(first, groq_key)
                            state['current_mystery_song'] = first
                        
                        save_state(state)
                        st.rerun()

# --- 5. JÁTÉK NÉZETEK ---
state = load_state()

# ==========================
# 📺 TV NÉZET (NEM FRISSÜL MAGÁTÓL!)
# ==========================
if st.session_state.user_role == "tv":
    st.title("📺 Hitster Party")

    if state.get('game_phase') == "LOBBY":
        st.info("👈 Állítsd be a játékot a bal oldali menüben!")
        st.markdown("---")
        st.markdown("### 📱 Telefon csatlakoztatása:")
        st.markdown("1. Nyisd meg ezt az oldalt a telefonodon.")
        st.markdown("2. A bal menüben válaszd ki: **📱 Játékos (Telefon)**")

    elif state.get('game_phase') == "GUESSING":
        curr_p = state['players'][state['turn_index'] % len(state['players'])]
        song = state['current_mystery_song']
        
        # 1. ZENE (Iframe nem töltődik újra, mert nincs st.rerun loop)
        st.markdown(f"### 🎶 Most játszik: {song['artist']} - ???")
        st.components.v1.iframe(f"https://open.spotify.com/embed/track/{song['spotify_id']}", height=80)
        
        st.markdown(f"<div class='tv-status'>👉 {curr_p} tippel a telefonján...</div>", unsafe_allow_html=True)
        st.caption("A zene szól. Ha a játékos végzett, nyomd meg a gombot lent!")
        
        # 2. IDŐVONAL
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
        
        # 3. KÉZI FRISSÍTÉS (HÁZIGAZDA)
        col1, col2 = st.columns([3, 1])
        with col2:
            # Ez a gomb olvassa ki a fájlt, amit a telefon írt
            if st.button("👀 MUTASD AZ EREDMÉNYT!", type="primary", use_container_width=True):
                state = load_state() # Most olvassuk be a friss állapotot!
                if state.get('waiting_for_reveal'):
                    state['game_phase'] = "REVEAL"
                    state['waiting_for_reveal'] = False
                    save_state(state)
                    st.rerun()
                else:
                    st.toast("⚠️ A játékos még nem küldte el a tippet!", icon="⏳")

    elif state.get('game_phase') == "REVEAL":
        song = state['current_mystery_song']
        color = "#00ff00" if state['success'] else "#ff4b4b"
        msg = "TALÁLT! 🎉" if state['success'] else "NEM TALÁLT... 😢"
        
        st.markdown(f"<h1 style='text-align:center; color:{color}; font-size:3em;'>{msg}</h1>", unsafe_allow_html=True)
        st.markdown(f"<h2 style='text-align:center'>{song['artist']} - {song['title']} ({song['year']})</h2>", unsafe_allow_html=True)
        st.components.v1.iframe(f"https://open.spotify.com/embed/track/{song['spotify_id']}", height=80)
        
        curr_p = state['players'][state['turn_index'] % len(state['players'])]
        timeline = state['timelines'][curr_p]
        
        # Timeline megjelenítése (ha talált, az új kártya kiemelve)
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
    
    # Névválasztó (egyszerűsítve)
    if 'my_name' not in st.session_state:
        temp_state = load_state()
        players_list = temp_state.get('players', ["Játékos 1", "Játékos 2"])
        selected_player = st.selectbox("Ki vagy te?", players_list)
        if st.button("Belépés"):
            st.session_state.my_name = selected_player
            st.rerun()
    else:
        me = st.session_state.my_name
        st.info(f"Belépve mint: **{me}**")
        
        state = load_state() # Telefon mindig frissít gombnyomásra
        
        if state.get('game_phase') == "GUESSING":
            curr_p = state['players'][state['turn_index'] % len(state['players'])]
            
            if curr_p == me:
                st.success("🔴 TE JÖSSZ! Válassz helyet:")
                
                timeline = state['timelines'][me]
                
                # GOMBOK GENERÁLÁSA
                for i in range(len(timeline) + 1):
                    # Kártya előtte
                    if i > 0:
                        prev = timeline[i-1]
                        st.caption(f"{prev['year']} - {prev['title']}")
                    
                    # A Lényeg: A gomb
                    if st.button(f"⬇️ IDE ILLESZTEM ⬇️", key=f"mob_{i}", use_container_width=True):
                        song = state['current_mystery_song']
                        # Ellenőrzés
                        prev_ok = (i==0) or (timeline[i-1]['year'] <= song['year'])
                        next_ok = (i==len(timeline)) or (timeline[i]['year'] >= song['year'])
                        
                        state['success'] = (prev_ok and next_ok)
                        if state['success']:
                            state['timelines'][me].insert(i, song)
                        
                        state['waiting_for_reveal'] = True # Jelezzük a TV-nek!
                        save_state(state)
                        st.success("Elküldve! Nézd a TV-t!")
                        time.sleep(1) # Kis pihi
                        st.rerun()
                    
                    # Kártya utána
                    if i < len(timeline):
                        nxt = timeline[i]
                        st.caption(f"{nxt['year']} - {nxt['title']}")

            else:
                st.warning(f"Most {curr_p} gondolkodik...")
                if st.button("🔄 Frissítés (Ha én jövök)"): st.rerun()
                
        elif state.get('game_phase') == "REVEAL":
            st.info("Eredményhirdetés a TV-n...")
            if st.button("🔄 Frissítés"): st.rerun()
        
        else:
            st.write("Várakozás a játék indítására...")
            if st.button("🔄 Frissítés"): st.rerun()
