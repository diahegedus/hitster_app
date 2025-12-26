import streamlit as st
import random
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import time
import json
import os
import socket

# Próbáljuk importálni a Groq-ot
try:
    from groq import Groq
except ImportError:
    Groq = None

# --- 1. FÁJL ALAPÚ ÁLLAPOT KEZELÉS (EZ A SZINKRONIZÁCIÓ LELKE) ---
DB_FILE = "party_state.json"

def init_db():
    if not os.path.exists(DB_FILE):
        reset_db()

def reset_db():
    default_state = {
        "game_started": False,
        "players": [],
        "timelines": {},
        "deck": [],
        "current_mystery_song": None,
        "turn_index": 0,
        "game_phase": "LOBBY", # LOBBY, GUESSING, REVEAL, GAME_OVER
        "game_msg": "",
        "success": False,
        "last_update": time.time()
    }
    with open(DB_FILE, 'w') as f:
        json.dump(default_state, f)

def load_state():
    if not os.path.exists(DB_FILE): init_db()
    try:
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_state(state):
    state["last_update"] = time.time()
    with open(DB_FILE, 'w') as f:
        json.dump(state, f)

# Segédfüggvény: IP cím lekérése a csatlakozáshoz
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "Nem sikerült lekérni. Nézd meg a parancssorban (ipconfig)."

# --- 2. KONFIGURÁCIÓ ÉS STÍLUS ---
st.set_page_config(page_title="Hitster Party", page_icon="🎵", layout="wide")

st.markdown("""
<style>
    .stApp { background: radial-gradient(circle at center, #2b2d42 0%, #1a1a2e 100%); color: #edf2f4; }
    #MainMenu, footer {visibility: hidden;}
    .timeline-card {
        background: linear-gradient(180deg, #1DB954 0%, #117a35 100%);
        color: white; padding: 10px; border-radius: 10px; text-align: center;
        border: 1px solid rgba(255,255,255,0.2); margin-bottom: 5px;
    }
    .card-year { font-size: 1.5em; font-weight: 900; border-bottom: 1px solid rgba(255,255,255,0.3); }
    .card-title { font-weight: bold; font-size: 1.1em; }
    .big-msg { font-size: 2em; text-align: center; font-weight: bold; padding: 20px; border: 2px solid white; border-radius: 15px; margin: 20px 0; }
    .insert-btn-container button { width: 100%; min-height: 60px; border: 1px dashed #777; background: rgba(255,255,255,0.05); }
    .insert-btn-container button:hover { background: #00d4ff; color: black; }
</style>
""", unsafe_allow_html=True)

# --- 3. JÁTÉK LOGIKA (Backend) ---
def load_spotify_tracks(api_id, api_secret, playlist_url):
    try:
        auth_manager = SpotifyClientCredentials(client_id=api_id, client_secret=api_secret)
        sp = spotipy.Spotify(auth_manager=auth_manager)
        if "?" in playlist_url: clean_url = playlist_url.split("?")[0]
        else: clean_url = playlist_url
        resource_id = clean_url.split("/")[-1]
        tracks_data = []
        
        results = None
        if "album" in clean_url:
            album_info = sp.album(resource_id)
            album_year = int(album_info['release_date'].split('-')[0])
            results = sp.album_tracks(resource_id)
            # Album logic simplified for brevity
            for track in results['items']:
                 tracks_data.append({"artist": track['artists'][0]['name'], "title": track['name'], "year": album_year, "spotify_id": track['id']})
        elif "playlist" in clean_url:
            results = sp.playlist_items(resource_id)
            items = results['items']
            while results['next']:
                results = sp.next(results)
                items.extend(results['items'])
            for item in items:
                track = item['track']
                if track and track['album'] and track['album']['release_date']:
                    year_str = track['album']['release_date'].split('-')[0]
                    if year_str.isdigit():
                        tracks_data.append({"artist": track['artists'][0]['name'], "title": track['name'], "year": int(year_str), "spotify_id": track['id']})
        return tracks_data
    except: return []

def fix_card_with_groq(card, api_key):
    if not api_key or Groq is None: return card
    try:
        client = Groq(api_key=api_key)
        prompt = f"Fact Check: ORIGINAL release year of '{card['title']}' by '{card['artist']}'? Reply ONLY 4-digit year."
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": prompt}], temperature=0, max_tokens=10
        )
        text = completion.choices[0].message.content.strip()
        if text.isdigit():
            ai_year = int(text)
            if 1900 < ai_year <= 2025 and ai_year != card['year']:
                card['year'] = ai_year
                card['fixed_by_ai'] = True
    except: pass
    return card

# --- 4. FELHASZNÁLÓI FELÜLET (ROLES) ---

# Inicializálás
if not os.path.exists(DB_FILE): init_db()

# OLDALSÁV - BEÁLLÍTÁSOK (Csak itt kell megadni)
with st.sidebar:
    st.header("⚙️ Rendszer Beállítások")
    view_mode = st.radio("Nézet kiválasztása:", ["📺 TV (Kijelző)", "📱 Játékos (Távirányító)"])
    
    st.markdown("---")
    st.info(f"📱 **Csatlakozás telefonnal:**\n\nÍrd be ezt a böngészőbe:\n`http://{get_local_ip()}:8501`")
    st.markdown("---")

    # Csak a TV módban, vagy adminnak kellenek a kulcsok
    api_id = st.text_input("Spotify ID", type="password")
    api_secret = st.text_input("Spotify Secret", type="password")
    groq_key = st.text_input("Groq Key", type="password")
    pl_url = st.text_input("Playlist URL")
    
    if st.button("🔄 Játék Törlése / Újraindítása"):
        reset_db()
        st.rerun()

# --- A) TV NÉZET (CSAK MEGJELENÍTÉS) ---
if view_mode == "📺 TV (Kijelző)":
    st.title("📺 Hitster Party - Kijelző")
    
    # Auto-refresh loop
    placeholder = st.empty()
    
    # Ez a trükk, hogy folyamatosan frissüljön a TV
    if 'last_run' not in st.session_state: st.session_state.last_run = 0
    
    state = load_state()
    
    with placeholder.container():
        # 1. LOBBY FÁZIS
        if state['game_phase'] == "LOBBY":
            st.markdown("<h1 style='text-align:center'>VÁRAKOZÁS JÁTÉKOSOKRA...</h1>", unsafe_allow_html=True)
            st.markdown(f"<h3 style='text-align:center'>Csatlakozz: http://{get_local_ip()}:8501</h3>", unsafe_allow_html=True)
            
            if state['players']:
                st.write("Csatlakozott játékosok:")
                cols = st.columns(len(state['players']) if len(state['players']) > 0 else 1)
                for i, p in enumerate(state['players']):
                    cols[i % 4].success(f"👤 {p}")
            
            if len(state['players']) > 0:
                if st.button("🚀 JÁTÉK INDÍTÁSA (TV-ről)", type="primary"):
                    if api_id and api_secret and pl_url:
                        deck = load_spotify_tracks(api_id, api_secret, pl_url)
                        if deck:
                            random.shuffle(deck)
                            state['deck'] = deck
                            state['timelines'] = {p: [] for p in state['players']}
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
                                state['game_phase'] = "GUESSING"
                                state['game_started'] = True
                                save_state(state)
                                st.rerun()

        # 2. JÁTÉK FÁZIS
        elif state['game_phase'] in ["GUESSING", "REVEAL"]:
            curr_p = state['players'][state['turn_index'] % len(state['players'])]
            
            # Felső sáv: Pontszámok
            scols = st.columns(len(state['players']))
            for i, p in enumerate(state['players']):
                active = "border: 2px solid cyan;" if p == curr_p else ""
                score = len(state['timelines'][p])
                scols[i].markdown(f"<div style='text-align:center; padding:10px; background:#444; border-radius:10px; {active}'>{p}<br><b>{score}</b></div>", unsafe_allow_html=True)
            
            st.divider()
            
            # Rejtélyes dal
            song = state['current_mystery_song']
            if state['game_phase'] == "GUESSING":
                st.markdown(f"<div class='big-msg'>Most szól: {song['artist']} - ???</div>", unsafe_allow_html=True)
                # Spotify Player
                st.components.v1.iframe(f"https://open.spotify.com/embed/track/{song['spotify_id']}", height=80)
                st.info(f"👉 {curr_p} következik! Nézd a telefonod!")
                
            elif state['game_phase'] == "REVEAL":
                res_color = "#00ff00" if state['success'] else "#ff4b4b"
                st.markdown(f"<div class='big-msg' style='color:{res_color}'>{state['game_msg']}</div>", unsafe_allow_html=True)
                st.markdown(f"<h3 style='text-align:center'>{song['artist']} - {song['title']} ({song['year']})</h3>", unsafe_allow_html=True)
                st.components.v1.iframe(f"https://open.spotify.com/embed/track/{song['spotify_id']}", height=80)

            # Idővonal megjelenítése (Csak a kártyák, gombok nélkül)
            st.markdown(f"### {curr_p} idővonala:")
            timeline = state['timelines'][curr_p]
            tcols = st.columns(len(timeline))
            for i, card in enumerate(timeline):
                style = "border: 2px solid yellow;" if (state['game_phase']=="REVEAL" and card==song and state['success']) else ""
                tcols[i].markdown(f"""
                <div class='timeline-card' style='{style}'>
                    <div class='card-year'>{card['year']}</div>
                    <div class='card-title'>{card['title']}</div>
                </div>
                """, unsafe_allow_html=True)

        elif state['game_phase'] == "GAME_OVER":
            st.balloons()
            st.title("🏆 JÁTÉK VÉGE!")
    
    # Automatikus frissítés 2 másodpercenként
    time.sleep(2)
    st.rerun()


# --- B) JÁTÉKOS NÉZET (TÁVIRÁNYÍTÓ) ---
elif view_mode == "📱 Játékos (Távirányító)":
    st.header("📱 Távirányító")
    
    # 1. Bejelentkezés
    if 'my_name' not in st.session_state:
        st.session_state.my_name = None

    if not st.session_state.my_name:
        name_input = st.text_input("Hogy hívnak?")
        if st.button("Belépés a játékba"):
            if name_input:
                state = load_state()
                if name_input not in state['players']:
                    state['players'].append(name_input)
                    save_state(state)
                st.session_state.my_name = name_input
                st.rerun()
    else:
        # Már be van lépve
        me = st.session_state.my_name
        st.success(f"Bejelentkezve mint: {me}")
        
        # Játékállapot betöltése
        state = load_state()
        
        if state['game_phase'] == "LOBBY":
            st.info("Várakozás a játék indítására a TV-n...")
            if st.button("Frissítés"): st.rerun()
            
        elif state['game_phase'] == "GUESSING":
            curr_p = state['players'][state['turn_index'] % len(state['players'])]
            
            if curr_p == me:
                st.markdown("### 🔴 TE JÖSSZ! 🔴")
                st.write("Hova illik a dal?")
                
                timeline = state['timelines'][me]
                
                # GRID GENERÁLÁSA A TELEFONRA
                # Itt minden elem egy sor, hogy mobilon jól látszódjon
                for i in range(len(timeline) + 1):
                    # GOMB
                    btn_key = f"mob_btn_{i}_{int(time.time())}" # Egyedi kulcs
                    st.markdown('<div class="insert-btn-container">', unsafe_allow_html=True)
                    if st.button(f"Ide illesztem (Pozíció {i+1})", key=btn_key):
                        # --- LOGIKA VÉGREHAJTÁSA ---
                        song = state['current_mystery_song']
                        prev_ok = (i==0) or (timeline[i-1]['year'] <= song['year'])
                        next_ok = (i==len(timeline)) or (timeline[i]['year'] >= song['year'])
                        
                        state['success'] = (prev_ok and next_ok)
                        state['game_msg'] = "TALÁLT!" if state['success'] else "NEM..."
                        if state['success']:
                            state['timelines'][me].insert(i, song)
                        
                        state['game_phase'] = "REVEAL"
                        save_state(state)
                        st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)

                    # KÁRTYA (Ha van még)
                    if i < len(timeline):
                        card = timeline[i]
                        st.info(f"{card['year']} - {card['title']}")
                        st.markdown("<div style='text-align:center'>⬇️</div>", unsafe_allow_html=True)

            else:
                st.warning(f"Most {curr_p} gondolkodik...")
                if st.button("Frissítés (Hogy lássam, ha én jövök)"): st.rerun()

        elif state['game_phase'] == "REVEAL":
            st.write(f"Eredmény: {state['game_msg']}")
            if st.button("KÖVETKEZŐ KÖR >>"):
                # Következő kör logika
                state['turn_index'] += 1
                if state['deck']:
                    next_song = state['deck'].pop()
                    # Itt most nincs AI hívás, hogy gyors legyen, vagy csak ha be van állítva
                    # Az egyszerűség kedvéért a telefonos nézetben nem hívunk API-t, 
                    # bízunk benne, hogy a betöltéskor vagy a TV lekezelte. 
                    # De a biztonság kedvéért:
                    state['current_mystery_song'] = next_song
                    state['game_phase'] = "GUESSING"
                else:
                    state['game_phase'] = "GAME_OVER"
                save_state(state)
                st.rerun()
