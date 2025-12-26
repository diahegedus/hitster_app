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

# --- 1. FÁJL ALAPÚ SZINKRONIZÁCIÓ ---
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
        "game_phase": "LOBBY",
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

# --- 2. KONFIGURÁCIÓ ÉS STÍLUS ---
st.set_page_config(page_title="Hitster Party", page_icon="🎵", layout="wide")

st.markdown("""
<style>
    .stApp { background: radial-gradient(circle at center, #2b2d42 0%, #1a1a2e 100%); color: #edf2f4; }
    #MainMenu, footer {visibility: hidden;}
    
    /* Kártyák */
    .timeline-card {
        background: linear-gradient(180deg, #1DB954 0%, #117a35 100%);
        color: white; padding: 10px; border-radius: 10px; text-align: center;
        border: 1px solid rgba(255,255,255,0.2); margin-bottom: 5px;
        min-height: 100px; display: flex; flex-direction: column; justify-content: center;
    }
    .card-year { font-size: 1.5em; font-weight: 900; border-bottom: 1px solid rgba(255,255,255,0.3); }
    .card-title { font-weight: bold; font-size: 1.1em; line-height: 1.2; }
    
    /* Gombok mobilon */
    .insert-btn-container button { 
        width: 100%; min-height: 60px; 
        border: 1px dashed #777; 
        background: rgba(255,255,255,0.05); 
        color: #aaa;
    }
    .insert-btn-container button:hover { 
        background: #00d4ff; color: black; border-style: solid;
    }
    
    .link-box {
        background: #2ecc71; color: black; padding: 15px; border-radius: 10px; 
        text-align: center; font-size: 1.1em; font-weight: bold; margin-bottom: 20px;
        border: 2px solid white;
    }
</style>
""", unsafe_allow_html=True)

# --- 3. LOGIKA (SPOTIFY & GROQ) ---
def load_spotify_tracks(api_id, api_secret, playlist_url):
    try:
        auth_manager = SpotifyClientCredentials(client_id=api_id, client_secret=api_secret)
        sp = spotipy.Spotify(auth_manager=auth_manager)
        if "?" in playlist_url: clean_url = playlist_url.split("?")[0]
        else: clean_url = playlist_url
        resource_id = clean_url.split("/")[-1]
        tracks_data = []
        
        if "album" in clean_url:
            album_info = sp.album(resource_id)
            album_year = int(album_info['release_date'].split('-')[0])
            results = sp.album_tracks(resource_id)
            items = results['items']
            while results['next']:
                results = sp.next(results)
                items.extend(results['items'])
            for track in items:
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
    except Exception as e:
        st.error(f"Hiba: {e}")
        return []

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

# --- 4. FELHASZNÁLÓI FELÜLET ---

if not os.path.exists(DB_FILE): init_db()

with st.sidebar:
    st.header("⚙️ Beállítások")
    view_mode = st.radio("Nézet:", ["📺 TV (Kijelző)", "📱 Játékos (Távirányító)"])
    st.markdown("---")
    
    st.info("ℹ️ Mivel felhőben vagy, küldd el a fenti böngésző címet (URL) a játékosoknak!")
    
    st.markdown("---")
    api_id = st.text_input("Spotify ID", type="password")
    api_secret = st.text_input("Spotify Secret", type="password")
    groq_key = st.text_input("Groq Key", type="password")
    pl_url = st.text_input("Playlist URL")
    
    if st.button("🔄 Játék Törlése"):
        reset_db()
        st.rerun()

# --- A) TV NÉZET ---
if view_mode == "📺 TV (Kijelző)":
    st.title("📺 Hitster Party")
    
    placeholder = st.empty()
    # Frissítés kezelése
    if 'last_run' not in st.session_state: st.session_state.last_run = 0
    
    state = load_state()
    
    with placeholder.container():
        if state['game_phase'] == "LOBBY":
            st.markdown("<h1 style='text-align:center'>CSATLAKOZZATOK!</h1>", unsafe_allow_html=True)
            st.markdown("<div class='link-box'>Nyisd meg ezt a weboldalt a telefonodon!</div>", unsafe_allow_html=True)
            
            if state['players']:
                st.write("Játékosok:")
                cols = st.columns(4)
                for i, p in enumerate(state['players']):
                    cols[i % 4].success(f"👤 {p}")
            
            if len(state['players']) > 0:
                if st.button("🚀 INDÍTÁS", type="primary"):
                    if api_id and api_secret and pl_url:
                        with st.spinner("Zene betöltése..."):
                            deck = load_spotify_tracks(api_id, api_secret, pl_url)
                            if deck:
                                random.shuffle(deck)
                                state['deck'] = deck
                                state['timelines'] = {p: [] for p in state['players']}
                                for p in state['players']:
                                    if state['deck']:
                                        c = state['deck'].pop()
                                        if groq_key: c = fix_card_with_groq(c, groq_key)
                                        state['timelines'][p].append(c)
                                if state['deck']:
                                    first = state['deck'].pop()
                                    if groq_key: first = fix_card_with_groq(first, groq_key)
                                    state['current_mystery_song'] = first
                                    state['game_phase'] = "GUESSING"
                                    state['game_started'] = True
                                    save_state(state)
                                    st.rerun()

        elif state['game_phase'] in ["GUESSING", "REVEAL"]:
            curr_p = state['players'][state['turn_index'] % len(state['players'])]
            
            # Pontszámok
            scols = st.columns(len(state['players']))
            for i, p in enumerate(state['players']):
                style = "border: 3px solid #00d4ff;" if p == curr_p else "opacity: 0.5;"
                score = len(state['timelines'][p])
                scols[i].markdown(f"<div style='text-align:center; padding:10px; background:#333; border-radius:10px; {style}'>{p}<br><b>{score}</b></div>", unsafe_allow_html=True)
            
            st.divider()
            
            song = state['current_mystery_song']
            if state['game_phase'] == "GUESSING":
                st.markdown(f"<h2 style='text-align:center'>🎶 {song['artist']} - ???</h2>", unsafe_allow_html=True)
                st.components.v1.iframe(f"https://open.spotify.com/embed/track/{song['spotify_id']}", height=80)
                st.info(f"👉 {curr_p} a telefonján tippel!")
                
            elif state['game_phase'] == "REVEAL":
                color = "green" if state['success'] else "red"
                msg = "TALÁLT! 🎉" if state['success'] else "NEM TALÁLT... 😢"
                st.markdown(f"<h1 style='text-align:center; color:{color}'>{msg}</h1>", unsafe_allow_html=True)
                st.markdown(f"<h3 style='text-align:center'>{song['artist']} - {song['title']} ({song['year']})</h3>", unsafe_allow_html=True)
                st.components.v1.iframe(f"https://open.spotify.com/embed/track/{song['spotify_id']}", height=80)

            st.markdown(f"### {curr_p} idővonala:")
            timeline = state['timelines'][curr_p]
            # Kártyák megjelenítése
            if timeline:
                # Egyszerűsített megjelenítés TV-n (csak kártyák sorban)
                cols = st.columns(len(timeline))
                for i, card in enumerate(timeline):
                    border = "border: 2px solid yellow;" if (state['game_phase']=="REVEAL" and card==song and state['success']) else ""
                    cols[i].markdown(f"""
                    <div class='timeline-card' style='{border}'>
                        <div class='card-year'>{card['year']}</div>
                        <div class='card-title'>{card['title']}</div>
                    </div>
                    """, unsafe_allow_html=True)

        elif state['game_phase'] == "GAME_OVER":
            st.balloons()
            st.title("🏆 JÁTÉK VÉGE!")
    
    # Automata frissítés (hogy a telefonos gombnyomás megjelenjen a TV-n)
    time.sleep(2)
    st.rerun()

# --- B) JÁTÉKOS NÉZET ---
elif view_mode == "📱 Játékos (Távirányító)":
    st.header("📱 Távirányító")
    
    if 'my_name' not in st.session_state: st.session_state.my_name = None

    if not st.session_state.my_name:
        name_input = st.text_input("Írd be a neved:")
        if st.button("BELÉPÉS"):
            if name_input:
                state = load_state()
                if name_input not in state['players']:
                    state['players'].append(name_input)
                    save_state(state)
                st.session_state.my_name = name_input
                st.rerun()
    else:
        me = st.session_state.my_name
        st.success(f"Belépve: {me}")
        state = load_state()
        
        if state['game_phase'] == "LOBBY":
            st.info("Várakozás a játék indítására a TV-n...")
            if st.button("Frissítés"): st.rerun()
            
        elif state['game_phase'] == "GUESSING":
            curr_p = state['players'][state['turn_index'] % len(state['players'])]
            
            if curr_p == me:
                st.markdown("### 🔴 TE JÖSSZ!")
                timeline = state['timelines'][me]
                
                # GRID RENDER (MOBIL)
                for i in range(len(timeline) + 1):
                    # GOMB
                    btn_key = f"mob_btn_{i}_{int(time.time())}" # Egyedi kulcs
                    st.markdown('<div class="insert-btn-container">', unsafe_allow_html=True)
                    if st.button(f"IDE ({i+1})", key=btn_key):
                        song = state['current_mystery_song']
                        prev_ok = (i==0) or (timeline[i-1]['year'] <= song['year'])
                        next_ok = (i==len(timeline)) or (timeline[i]['year'] >= song['year'])
                        state['success'] = (prev_ok and next_ok)
                        state['game_msg'] = "TALÁLT!" if state['success'] else "NEM..."
                        if state['success']: state['timelines'][me].insert(i, song)
                        state['game_phase'] = "REVEAL"
                        save_state(state)
                        st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    # KÁRTYA
                    if i < len(timeline):
                        card = timeline[i]
                        st.info(f"{card['year']} - {card['title']}")
                        st.markdown("<div style='text-align:center'>⬇️</div>", unsafe_allow_html=True)
            else:
                st.warning(f"Most {curr_p} jön...")
                if st.button("Frissítés"): st.rerun()

        elif state['game_phase'] == "REVEAL":
            st.write(f"Eredmény: {state['game_msg']}")
            if st.button("➡️ KÖVETKEZŐ KÖR"):
                state['turn_index'] += 1
                if state['deck']:
                    next_song = state['deck'].pop()
                    if groq_key: next_song = fix_card_with_groq(next_song, groq_key)
                    state['current_mystery_song'] = next_song
                    state['game_phase'] = "GUESSING"
                else: state['game_phase'] = "GAME_OVER"
                save_state(state)
                st.rerun()
