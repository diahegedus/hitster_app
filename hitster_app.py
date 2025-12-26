import streamlit as st
import random
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import time
import json
import os

# --- GROQ IMPORT ---
try:
    from groq import Groq
except ImportError:
    Groq = None

# --- 1. FÁJL ALAPÚ SZINKRONIZÁCIÓ (KÖZÖS AGY) ---
DB_FILE = "party_state.json"

def init_db():
    if not os.path.exists(DB_FILE):
        reset_db()

def reset_db():
    default_state = {
        "game_phase": "LOBBY", # LOBBY, GUESSING, REVEAL, GAME_OVER
        "players": [],
        "timelines": {},
        "deck": [],
        "current_mystery_song": None,
        "turn_index": 0,
        "game_msg": "",
        "success": False,
        "waiting_for_reveal": False, # Ez jelzi a TV-nek, hogy történt tipp
        "last_player_action": ""
    }
    with open(DB_FILE, 'w') as f: json.dump(default_state, f)

def load_state():
    if not os.path.exists(DB_FILE): init_db()
    try:
        with open(DB_FILE, 'r') as f: return json.load(f)
    except: return {}

def save_state(state):
    with open(DB_FILE, 'w') as f: json.dump(state, f)

# --- 2. SPOTIFY & AI LOGIKA ---
def load_spotify_tracks(api_id, api_secret, playlist_url):
    try:
        auth_manager = SpotifyClientCredentials(client_id=api_id, client_secret=api_secret)
        sp = spotipy.Spotify(auth_manager=auth_manager)
        if "?" in playlist_url: clean_url = playlist_url.split("?")[0]
        else: clean_url = playlist_url
        resource_id = clean_url.split("/")[-1]
        tracks_data = []
        
        # Egyszerűsített lekérés (Album vagy Playlist)
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

# --- 3. KONFIGURÁCIÓ ---
st.set_page_config(page_title="Hitster Party", page_icon="🎵", layout="wide")

# URL Paraméterek ellenőrzése
# Ha a link végén ott van, hogy /?role=player, akkor telefon nézet lesz
query_params = st.query_params
role = query_params.get("role", "tv") # Alapértelmezett a TV

# CSS Stílus
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
    
    /* Telefonos gombok */
    .mob-btn { 
        width: 100%; padding: 15px; margin: 5px 0; 
        background: rgba(255,255,255,0.1); border: 1px dashed #777; 
        color: white; font-size: 1.2em; border-radius: 8px; cursor: pointer;
    }
    .mob-btn:hover { background: #00d4ff; color: black; }
    
    /* Nagy állapotjelző TV-n */
    .status-box {
        padding: 20px; border-radius: 15px; text-align: center; 
        font-size: 1.5em; font-weight: bold; margin: 20px 0;
        background: rgba(0,0,0,0.5); border: 2px solid #555;
    }
</style>
""", unsafe_allow_html=True)

# --- 4. 📺 TV NÉZET (DEFAULT) ---
if role == "tv":
    st.title("📺 TV Kijelző")
    
    # Oldalsáv csak a TV-n van
    with st.sidebar:
        st.header("⚙️ DJ Pult")
        api_id = st.text_input("Spotify ID", type="password")
        api_secret = st.text_input("Spotify Secret", type="password")
        groq_key = st.text_input("Groq Key", type="password")
        pl_url = st.text_input("Playlist URL")
        
        if st.button("JÁTÉK INDÍTÁSA / ÚJRAINDÍTÁS"):
            if api_id and api_secret and pl_url:
                with st.spinner("Zene betöltése..."):
                    deck = load_spotify_tracks(api_id, api_secret, pl_url)
                    if deck:
                        random.shuffle(deck)
                        # State inicializálás
                        new_state = {
                            "game_phase": "GUESSING",
                            "players": ["Játékos 1", "Játékos 2"], # Alapértelmezett, mobilon majd felülírják
                            "timelines": {"Játékos 1": [], "Játékos 2": []},
                            "deck": deck,
                            "current_mystery_song": None,
                            "turn_index": 0,
                            "game_msg": "",
                            "success": False,
                            "waiting_for_reveal": False
                        }
                        # Osztás
                        for p in new_state['players']:
                            if new_state['deck']:
                                c = new_state['deck'].pop()
                                if groq_key: c = fix_card_with_groq(c, groq_key)
                                new_state['timelines'][p].append(c)
                        # Első dal
                        if new_state['deck']:
                            first = new_state['deck'].pop()
                            if groq_key: first = fix_card_with_groq(first, groq_key)
                            new_state['current_mystery_song'] = first
                        
                        save_state(new_state)
                        st.rerun()

    state = load_state()

    if state.get('game_phase') == "LOBBY":
        st.info("Kérlek indítsd el a játékot a bal oldali menüben!")
        
        # Linkek generálása
        base_url = "https://hitster-party.streamlit.app" # Ide majd a te URL-ed kerül
        # Mivel Cloudban vagy, az URL dinamikus, de a user látja a böngészőben
        st.markdown(f"### 📱 Telefon Link:")
        st.code(f"{st.query_params.get('embed_options', '')}/?role=player", language="text")
        st.caption("A fenti címhez írd hozzá: /?role=player")

    elif state.get('game_phase') == "GUESSING":
        curr_p = state['players'][state['turn_index'] % len(state['players'])]
        song = state['current_mystery_song']
        
        # 1. ZENE ÉS INFO (Ez nem frissül magától, így végigmegy a zene!)
        st.markdown(f"### 🎶 Most játszik: {song['artist']} - ???")
        st.components.v1.iframe(f"https://open.spotify.com/embed/track/{song['spotify_id']}", height=80)
        
        st.markdown(f"<div class='status-box'>👉 {curr_p} tippel a telefonján...</div>", unsafe_allow_html=True)
        
        # 2. IDŐVONAL MEGJELENÍTÉSE
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
        
        # 3. FRISSÍTÉS GOMB (A Házigazda nyomja meg, ha a játékos kész)
        col1, col2 = st.columns([3, 1])
        with col2:
            if st.button("👀 MUTASD AZ EREDMÉNYT!", type="primary", use_container_width=True):
                # Ekkor olvassuk ki újra a fájlt, amibe a telefon írt
                state = load_state() 
                if state['waiting_for_reveal']:
                    state['game_phase'] = "REVEAL"
                    state['waiting_for_reveal'] = False
                    save_state(state)
                    st.rerun()
                else:
                    st.toast("A játékos még nem tippelt!")

    elif state.get('game_phase') == "REVEAL":
        # EREDMÉNYHIRDETÉS
        song = state['current_mystery_song']
        color = "green" if state['success'] else "red"
        msg = "TALÁLT! 🎉" if state['success'] else "NEM TALÁLT... 😢"
        
        st.markdown(f"<h1 style='text-align:center; color:{color}; font-size:3em;'>{msg}</h1>", unsafe_allow_html=True)
        st.markdown(f"<h2 style='text-align:center'>{song['artist']} - {song['title']} ({song['year']})</h2>", unsafe_allow_html=True)
        
        # Itt már látszik az új kártya is a timeline-on (ha talált)
        curr_p = state['players'][state['turn_index'] % len(state['players'])]
        timeline = state['timelines'][curr_p]
        cols = st.columns(len(timeline))
        for i, card in enumerate(timeline):
            border = "border: 3px solid yellow;" if card == song else ""
            if i < len(cols):
                cols[i].markdown(f"<div class='timeline-card' style='{border}'><div class='card-year'>{card['year']}</div><div class='card-title'>{card['title']}</div></div>", unsafe_allow_html=True)

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

# --- 📱 TELEFON NÉZET (/role=player) ---
elif role == "player":
    st.header("📱 Távirányító")
    
    # Egyszerű névválasztás
    if 'my_name' not in st.session_state:
        # Betöltjük a játékosokat a DB-ből
        temp_state = load_state()
        players_list = temp_state.get('players', ["Játékos 1", "Játékos 2"])
        selected_player = st.selectbox("Ki vagy te?", players_list)
        if st.button("Belépés"):
            st.session_state.my_name = selected_player
            st.rerun()
    else:
        me = st.session_state.my_name
        st.success(f"Szia {me}!")
        
        # Itt olvassuk a közös állapotot
        state = load_state()
        
        if state.get('game_phase') == "GUESSING":
            curr_p = state['players'][state['turn_index'] % len(state['players'])]
            
            if curr_p == me:
                st.info("🔴 TE JÖSSZ! Hallgasd a zenét a TV-n, és válassz helyet:")
                
                timeline = state['timelines'][me]
                # Gombok generálása
                for i in range(len(timeline) + 1):
                    # Kártya előtte (ha van)
                    if i > 0:
                        prev_card = timeline[i-1]
                        st.markdown(f"<div style='text-align:center; opacity:0.7'>{prev_card['year']} - {prev_card['title']}</div>", unsafe_allow_html=True)
                    
                    # GOMB
                    if st.button(f"⬇️ IDE ILLESZTEM ⬇️", key=f"mob_{i}", use_container_width=True):
                        # LOGIKA
                        song = state['current_mystery_song']
                        prev_ok = (i==0) or (timeline[i-1]['year'] <= song['year'])
                        next_ok = (i==len(timeline)) or (timeline[i]['year'] >= song['year'])
                        
                        state['success'] = (prev_ok and next_ok)
                        if state['success']:
                            state['timelines'][me].insert(i, song)
                        
                        state['waiting_for_reveal'] = True # Jelezzük a TV-nek
                        save_state(state)
                        st.success("Tipp elküldve! Nézd a TV-t!")
                        time.sleep(1)
                        st.rerun()
                    
                    # Kártya utána (ha van)
                    if i < len(timeline):
                        next_card = timeline[i]
                        st.markdown(f"<div style='text-align:center; opacity:0.7'>{next_card['year']} - {next_card['title']}</div>", unsafe_allow_html=True)

            else:
                st.warning(f"Most {curr_p} gondolkodik...")
                if st.button("Frissítés"): st.rerun()
                
        elif state.get('game_phase') == "REVEAL":
            st.info("Eredményhirdetés a TV-n...")
            if st.button("Frissítés"): st.rerun()
        
        else:
            st.write("Várakozás a játékra...")
            if st.button("Frissítés"): st.rerun()
