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
        "lives": {"Játékos 1": 3, "Játékos 2": 3}, # ❤️ Életek
        "deck": [],
        "current_mystery_song": None,
        "turn_index": 0,
        "game_msg": "",
        "fun_fact": "", # 🧠 AI Érdekesség
        "success": False,
        "waiting_for_reveal": False,
        "winner": None,
        "target_score": 10,
        "correct_answer_log": None
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
        
        # Helper a kép kinyeréséhez
        def get_image(item_obj):
            try: return item_obj['images'][0]['url']
            except: return "https://via.placeholder.com/150"

        if "album" in clean_url:
            results = sp.album_tracks(resource_id)
            album_info = sp.album(resource_id)
            year = int(album_info['release_date'][:4])
            img_url = get_image(album_info)
            items = results['items']
            while results['next']:
                results = sp.next(results)
                items.extend(results['items'])
            for track in items:
                tracks_data.append({
                    "artist": track['artists'][0]['name'], 
                    "title": track['name'], 
                    "year": year, 
                    "spotify_id": track['id'],
                    "image": img_url # 🖼️ Borítókép
                })
        elif "playlist" in clean_url:
            results = sp.playlist_items(resource_id)
            items = results['items']
            while results['next']:
                results = sp.next(results)
                items.extend(results['items'])
            for item in items:
                t = item['track']
                if t and t['album']['release_date']:
                    tracks_data.append({
                        "artist": t['artists'][0]['name'], 
                        "title": t['name'], 
                        "year": int(t['album']['release_date'][:4]), 
                        "spotify_id": t['id'],
                        "image": get_image(t['album']) # 🖼️ Borítókép
                    })
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

def get_fun_fact(card, api_key):
    if not api_key or Groq is None: return "Jó kis zene!"
    try:
        client = Groq(api_key=api_key)
        # 🧠 Fun Fact Prompt
        prompt = f"Tell me a very short (max 1 sentence), interesting trivia fact about the song '{card['title']}' by '{card['artist']}' in HUNGARIAN language. Don't mention the release year."
        completion = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": prompt}], temperature=0.7, max_tokens=100)
        return completion.choices[0].message.content.strip()
    except: return "Szuper sláger!"

# --- 3. UI BEÁLLÍTÁS ---
st.set_page_config(page_title="Hitster Party Pro", page_icon="🎵", layout="wide")

st.markdown("""
<style>
    .stApp { background: radial-gradient(circle at center, #2b2d42 0%, #1a1a2e 100%); color: #edf2f4; }
    #MainMenu, footer {visibility: hidden;}
    
    /* PROFI KÁRTYA STÍLUS KÉPPEL */
    .timeline-card {
        background: #222;
        color: white; border-radius: 10px; text-align: center;
        border: 1px solid rgba(255,255,255,0.2); margin-bottom: 5px; overflow: hidden;
        transition: transform 0.2s;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    .timeline-card img { width: 100%; object-fit: cover; height: 150px; border-bottom: 2px solid #1DB954; }
    .card-content { padding: 10px; }
    .card-year { font-size: 1.5em; font-weight: 900; color: #1DB954; }
    .card-title { font-weight: bold; font-size: 0.9em; line-height: 1.2; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    
    /* MOBIL GOMBOK */
    .mob-insert-btn { 
        width: 100%; padding: 15px; margin: 10px 0; 
        background: rgba(255,255,255,0.1); border: 2px dashed #777; 
        color: white; font-size: 1.2em; border-radius: 8px; cursor: pointer; text-align: center;
    }
    .mob-insert-btn:hover { background: #00d4ff; color: black; border-style: solid; }
    
    .mob-card-box {
        display: flex; align-items: center; gap: 10px;
        background: rgba(0,0,0,0.4); padding: 10px; border-radius: 8px; border: 1px solid #444;
    }
    .mob-card-box img { width: 50px; height: 50px; border-radius: 5px; }

    .tv-status {
        padding: 20px; border-radius: 15px; text-align: center; 
        font-size: 1.5em; font-weight: bold; margin: 20px 0;
        background: rgba(0,0,0,0.5); border: 2px solid #555; animation: pulse 2s infinite;
    }
    @keyframes pulse { 0% {border-color: #555;} 50% {border-color: #00d4ff;} 100% {border-color: #555;} }

    .trivia-box {
        background: rgba(255, 255, 0, 0.1); border-left: 5px solid yellow;
        padding: 15px; margin-top: 20px; font-style: italic; font-size: 1.2em;
    }
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

    # --- RÉGI, EGYSZERŰ KULCS BEVITEL ---
    if st.session_state.user_role == "tv":
        st.header("⚙️ Beállítások")
        # Nincs secrets.toml varázslat, csak sima input mezők
        api_id = st.text_input("Spotify ID", type="password")
        api_secret = st.text_input("Spotify Secret", type="password")
        groq_key = st.text_input("Groq Key", type="password")
        pl_url = st.text_input("Playlist URL", value="https://open.spotify.com/playlist/37i9dQZF1DXbTxeAdrVG2l")
        
        target_score = st.number_input("🏆 Cél pontszám (Győzelemhez):", min_value=5, value=10)
        
        if st.button("🚀 ÚJ JÁTÉK INDÍTÁSA", type="primary"):
            if api_id and api_secret and pl_url:
                with st.spinner("Zene betöltése és keverése..."):
                    deck = load_spotify_tracks(api_id, api_secret, pl_url)
                    if deck:
                        random.shuffle(deck)
                        state = {
                            "game_phase": "GUESSING",
                            "players": ["Játékos 1", "Játékos 2"], 
                            "timelines": {"Játékos 1": [], "Játékos 2": []},
                            "lives": {"Játékos 1": 3, "Játékos 2": 3}, # ❤️ START
                            "deck": deck,
                            "current_mystery_song": None,
                            "turn_index": 0,
                            "game_msg": "",
                            "fun_fact": "",
                            "success": False,
                            "waiting_for_reveal": False,
                            "winner": None,
                            "target_score": target_score,
                            "correct_answer_log": None
                        }
                        # Osztás (1-1 kártya)
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

# --- 5. LOGIKA ---
state = load_state()

# ==========================
# 📺 TV NÉZET
# ==========================
if st.session_state.user_role == "tv":
    st.title("📺 Hitster Party Pro")

    if state.get('game_phase') == "LOBBY":
        st.info("👈 Írd be a kulcsokat a bal oldali menüben és indítsd a játékot!")

    elif state.get('game_phase') == "GUESSING":
        curr_p = state['players'][state['turn_index'] % len(state['players'])]
        song = state['current_mystery_song']
        
        # 1. PONTOK & ÉLETEK SÁV
        cols = st.columns(len(state['players']))
        for i, p in enumerate(state['players']):
            is_active = (p == curr_p)
            lives = state['lives'].get(p, 3)
            hearts = "❤️" * lives + "🖤" * (3-lives)
            score = len(state['timelines'][p])
            target = state.get('target_score', 10)
            
            style = "border: 2px solid #00d4ff; background: rgba(0, 212, 255, 0.1);" if is_active else "background: rgba(255,255,255,0.05); opacity: 0.6;"
            
            cols[i].markdown(f"""
            <div style='{style} padding: 10px; border-radius: 10px; text-align: center;'>
                <div style='font-size: 1.2em; font-weight: bold;'>{p}</div>
                <div>{hearts}</div>
                <div style='font-size: 2em; font-weight: 900;'>{score} / {target}</div>
            </div>
            """, unsafe_allow_html=True)

        st.divider()

        # 2. ZENE
        st.markdown(f"### 🎶 Most játszik: {song['artist']} - ???")
        st.components.v1.iframe(f"https://open.spotify.com/embed/track/{song['spotify_id']}", height=80)
        
        st.markdown(f"<div class='tv-status'>👉 {curr_p} tippel a telefonján...</div>", unsafe_allow_html=True)
        
        # 3. IDŐVONAL (KÉPEKKEL!)
        timeline = state['timelines'][curr_p]
        num_cards = len(timeline)
        if num_cards > 0:
            t_cols = st.columns(num_cards)
            for i, card in enumerate(timeline):
                with t_cols[i]:
                    st.markdown(f"""
                    <div class='timeline-card'>
                        <img src='{card.get('image', '')}'>
                        <div class='card-content'>
                            <div class='card-year'>{card['year']}</div>
                            <div class='card-title'>{card['title']}</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

        st.divider()
        
        # 4. GOMB
        col1, col2 = st.columns([3, 1])
        with col2:
            if st.button("👀 EREDMÉNY MUTATÁSA", type="primary", use_container_width=True):
                state = load_state() 
                if state.get('waiting_for_reveal'):
                    state['game_phase'] = "REVEAL"
                    state['waiting_for_reveal'] = False
                    
                    # 🧠 AI FUN FACT GENERÁLÁS MOST
                    if groq_key:
                        with st.spinner("AI érdekesség keresése..."):
                            fact = get_fun_fact(state['current_mystery_song'], groq_key)
                            state['fun_fact'] = fact
                    
                    # ❤️ ÉLET LOGIKA
                    curr_p_name = state['players'][state['turn_index'] % len(state['players'])]
                    if not state['success']:
                        state['lives'][curr_p_name] -= 1
                    
                    # 🏆 GYŐZELEM / GAME OVER LOGIKA
                    if len(state['timelines'][curr_p_name]) >= state.get('target_score', 10):
                        state['game_phase'] = "VICTORY"
                        state['winner'] = curr_p_name
                    elif state['lives'][curr_p_name] <= 0:
                         state['game_phase'] = "GAME_OVER"
                         state['winner'] = "Senki (Elfogytak az életek)"

                    save_state(state)
                    st.rerun()
                else:
                    st.toast("⚠️ Még nem tippeltek!", icon="⏳")

    elif state.get('game_phase') == "REVEAL":
        song = state['current_mystery_song']
        color = "#00ff00" if state['success'] else "#ff4b4b"
        msg = "TALÁLT! 🎉" if state['success'] else "NEM TALÁLT... 😢"
        
        c1, c2 = st.columns([1, 2])
        with c1:
            st.image(song.get('image'), use_container_width=True)
        with c2:
            st.markdown(f"<h1 style='color:{color}; font-size:3em; margin:0;'>{msg}</h1>", unsafe_allow_html=True)
            st.markdown(f"<h2>{song['artist']} - {song['title']}</h2>", unsafe_allow_html=True)
            st.markdown(f"<h1 style='font-size:4em; font-weight:900;'>{song['year']}</h1>", unsafe_allow_html=True)
            
            # 🧠 FUN FACT
            if state.get('fun_fact'):
                st.markdown(f"<div class='trivia-box'>🧠 <b>Tudtad?</b> {state['fun_fact']}</div>", unsafe_allow_html=True)
        
        st.divider()

        if st.button("➡️ KÖVETKEZŐ KÖR", type="primary", use_container_width=True):
            state['turn_index'] += 1
            if state['deck']:
                next_song = state['deck'].pop()
                if groq_key: next_song = fix_card_with_groq(next_song, groq_key)
                state['current_mystery_song'] = next_song
                state['game_phase'] = "GUESSING"
                state['fun_fact'] = ""
                state['correct_answer_log'] = None
            else:
                state['game_phase'] = "GAME_OVER"
            save_state(state)
            st.rerun()

    elif state.get('game_phase') == "VICTORY":
        st.balloons()
        st.title(f"🏆 GYŐZTES: {state.get('winner')}! 🏆")
        st.image("https://media.giphy.com/media/26tOZ42Mg6pbTUPHW/giphy.gif")
        if st.button("Új játék"): reset_db(); st.rerun()

    elif state.get('game_phase') == "GAME_OVER":
        st.title("💀 JÁTÉK VÉGE!")
        st.error("Sajnos elfogytak az életek.")
        if st.button("Újra"): reset_db(); st.rerun()

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
        state = load_state()
        
        # Header info
        lives = state['lives'].get(me, 3)
        hearts = "❤️" * lives
        st.caption(f"Belépve: **{me}** | Életek: {hearts}")

        if state.get('game_phase') == "GUESSING":
            curr_p = state['players'][state['turn_index'] % len(state['players'])]
            
            if curr_p == me:
                st.success("🔴 TE JÖSSZ!")
                timeline = state['timelines'][me]
                
                # --- MOBIL GRID KÉPEKKEL ---
                # 1. Gomb az elejére
                if st.button("⬇️ IDE (Elejére)", key="mob_btn_start", use_container_width=True):
                    song = state['current_mystery_song']
                    next_ok = (len(timeline) == 0) or (timeline[0]['year'] >= song['year'])
                    state['success'] = next_ok
                    state['correct_answer_log'] = song
                    
                    if state['success']: state['timelines'][me].insert(0, song)
                    state['waiting_for_reveal'] = True
                    save_state(state)
                    st.rerun()

                for i, card in enumerate(timeline):
                    # Kártya képpel
                    st.markdown(f"""
                    <div class='mob-card-box'>
                        <img src='{card.get('image', '')}'>
                        <div>
                            <div style='font-weight:bold; font-size:1.2em'>{card['year']}</div>
                            <div>{card['title']}</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Gomb
                    if st.button(f"⬇️ IDE", key=f"mob_btn_{i+1}", use_container_width=True):
                        song = state['current_mystery_song']
                        pos = i + 1
                        prev_ok = (timeline[pos-1]['year'] <= song['year'])
                        next_ok = (pos == len(timeline)) or (timeline[pos]['year'] >= song['year'])
                        
                        state['success'] = (prev_ok and next_ok)
                        state['correct_answer_log'] = song
                        
                        if state['success']: state['timelines'][me].insert(pos, song)
                        state['waiting_for_reveal'] = True
                        save_state(state)
                        st.rerun()

            else:
                st.warning(f"Most {curr_p} gondolkodik...")
                if st.button("🔄 Frissítés", use_container_width=True): st.rerun()
                
        elif state.get('game_phase') == "REVEAL":
            song = state.get('correct_answer_log') or state['current_mystery_song']
            
            color = "green" if state['success'] else "red"
            msg = "TALÁLT!" if state['success'] else "NEM TALÁLT..."
            
            st.markdown(f"<h2 style='text-align:center; color:{color};'>{msg}</h2>", unsafe_allow_html=True)
            if song:
                st.image(song.get('image', ''), use_container_width=True)
                st.markdown(f"<div style='text-align:center'>HELYES ÉV: <b>{song['year']}</b><br>{song['title']}</div>", unsafe_allow_html=True)
            
            if st.button("🔄 Frissítés (Várj a következő körre)", use_container_width=True): st.rerun()
        
        else:
            st.info("Várakozás...")
            if st.button("🔄 Frissítés", use_container_width=True): st.rerun()
