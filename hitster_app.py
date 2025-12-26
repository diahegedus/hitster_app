import streamlit as st
import random
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import time
import json
import sqlite3
import os
import qrcode
from io import BytesIO

# --- 0. KONFIGURÁCIÓ ÉS URL KEZELÉS ---
st.set_page_config(page_title="Hitster Party", page_icon="🎵", layout="wide")

# 🔗 URL Paraméter feldolgozása (Fix #3)
if "role" in st.query_params:
    if st.query_params["role"] == "player":
        st.session_state.user_role = "player"
    elif st.query_params["role"] == "tv":
        st.session_state.user_role = "tv"

if 'user_role' not in st.session_state: st.session_state.user_role = "tv"

# --- ALAPOK ---
try:
    from groq import Groq
except ImportError:
    Groq = None

DB_FILE = "hitster_party.db"

# --- 1. ADATBÁZIS KEZELÉS (WAL + Optimistic Locking) ---
def get_db_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS game_state
                     (id INTEGER PRIMARY KEY, data TEXT)''')
        c.execute("SELECT count(*) FROM game_state WHERE id=1")
        if c.fetchone()[0] == 0:
            default_state = {
                "version": 0, # 🔒 Optimistic Locking
                "game_phase": "LOBBY",
                "players": [],
                "timelines": {},
                "lives": {},
                "deck": [],
                "current_mystery_song": None,
                "turn_index": 0,
                "game_msg": "",
                "fun_fact": "",
                "success": False,
                "waiting_for_reveal": False,
                "reveal_processed": False,
                "reveal_ui_shown": False, # ♻️ UI Villogás ellen
                "sound_trigger": None,
                "sound_played": False,
                "winner": None,
                "target_score": 10,
                "correct_answer_log": None
            }
            c.execute("INSERT INTO game_state (id, data) VALUES (1, ?)", (json.dumps(default_state),))
            conn.commit()

def reset_db():
    current = load_state()
    players = current.get('players', [])
    with get_db_connection() as conn:
        c = conn.cursor()
        new_state = {
            "version": current.get('version', 0) + 1,
            "game_phase": "LOBBY",
            "players": players,
            "timelines": {},
            "lives": {},
            "deck": [],
            "current_mystery_song": None,
            "turn_index": 0,
            "game_msg": "",
            "fun_fact": "",
            "success": False,
            "waiting_for_reveal": False,
            "reveal_processed": False,
            "reveal_ui_shown": False,
            "winner": None,
            "target_score": 10,
            "correct_answer_log": None,
            "sound_trigger": None,
            "sound_played": False
        }
        c.execute("UPDATE game_state SET data = ? WHERE id = 1", (json.dumps(new_state),))
        conn.commit()

def load_state():
    if not os.path.exists(DB_FILE): init_db()
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT data FROM game_state WHERE id=1")
            row = c.fetchone()
            if row: return json.loads(row[0])
            else: init_db(); return load_state()
    except: return {}

def save_state(state):
    try:
        # 🔒 Verzió növelése mentéskor
        state['version'] = state.get('version', 0) + 1
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("UPDATE game_state SET data = ? WHERE id = 1", (json.dumps(state),))
            conn.commit()
    except Exception as e:
        st.error(f"DB Save Error: {e}")

# --- 2. GAME LOGIC ENGINE ---
def check_guess_logic(timeline, song, pos):
    if pos == 0:
        if not timeline: return True
        return timeline[0]['year'] >= song['year']
    if pos == len(timeline):
        return timeline[-1]['year'] <= song['year']
    prev_card = timeline[pos-1]
    next_card = timeline[pos]
    return (prev_card['year'] <= song['year']) and (next_card['year'] >= song['year'])

# --- 3. SPOTIFY & AI (VALÓDI CACHE ⚡) ---
@st.cache_data(ttl=3600, show_spinner=False)
def load_spotify_tracks(api_id, api_secret, playlist_url):
    try:
        LIMIT = 150
        auth_manager = SpotifyClientCredentials(client_id=api_id, client_secret=api_secret)
        sp = spotipy.Spotify(auth_manager=auth_manager)
        if "?" in playlist_url: clean_url = playlist_url.split("?")[0]
        else: clean_url = playlist_url
        resource_id = clean_url.split("/")[-1]
        tracks_data = []
        
        def get_image(item_obj):
            try: return item_obj['images'][0]['url']
            except: return "https://via.placeholder.com/150"

        if "album" in clean_url:
            results = sp.album_tracks(resource_id)
            album_info = sp.album(resource_id)
            year = int(album_info['release_date'][:4])
            img_url = get_image(album_info)
            items = results['items']
            while results['next'] and len(items) < LIMIT:
                results = sp.next(results)
                items.extend(results['items'])
            for track in items:
                if len(tracks_data) >= LIMIT: break
                tracks_data.append({
                    "artist": track['artists'][0]['name'], "title": track['name'], "year": year, 
                    "spotify_id": track['id'], "image": img_url
                })
        elif "playlist" in clean_url:
            results = sp.playlist_items(resource_id)
            items = results['items']
            while results['next'] and len(items) < LIMIT:
                results = sp.next(results)
                items.extend(results['items'])
            for item in items:
                if len(tracks_data) >= LIMIT: break
                t = item['track']
                if t and t['album']['release_date']:
                    tracks_data.append({
                        "artist": t['artists'][0]['name'], "title": t['name'], "year": int(t['album']['release_date'][:4]), 
                        "spotify_id": t['id'], "image": get_image(t['album'])
                    })
        return tracks_data
    except: return []

# ⚡ Fix #1: Cache Kulcs Javítás (Nincs API kulcs a paraméterekben)
@st.cache_data(ttl=86400, show_spinner=False)
def fix_card_with_groq_cached(artist, title, original_year):
    # A kulcsot belülről szerezzük meg, így nem része a cache hash-nek
    api_key = st.secrets.get("GROQ_KEY") or st.session_state.get("manual_groq_key")
    
    if not api_key or Groq is None: return original_year
    try:
        client = Groq(api_key=api_key)
        prompt = f"Fact Check: ORIGINAL release year of '{title}' by '{artist}'? Reply ONLY 4-digit year."
        completion = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": prompt}], temperature=0, max_tokens=10)
        text = completion.choices[0].message.content.strip()
        if text.isdigit():
            ai_year = int(text)
            if 1900 < ai_year <= 2025: return ai_year
    except: pass
    return original_year

def process_card_ai(card):
    new_year = fix_card_with_groq_cached(card['artist'], card['title'], card['year'])
    if new_year != card['year']:
        card['year'] = new_year
        card['fixed_by_ai'] = True
    return card

@st.cache_data(ttl=86400, show_spinner=False)
def get_fun_fact_cached(artist, title):
    api_key = st.secrets.get("GROQ_KEY") or st.session_state.get("manual_groq_key")
    if not api_key or Groq is None: return "Jó kis zene!"
    try:
        client = Groq(api_key=api_key)
        prompt = f"Tell me a very short (max 1 sentence), interesting trivia fact about the song '{title}' by '{artist}' in HUNGARIAN language. Don't mention the release year."
        completion = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": prompt}], temperature=0.7, max_tokens=100)
        return completion.choices[0].message.content.strip()
    except: return "Szuper sláger!"

# --- 4. UI BEÁLLÍTÁS & HANGOK ---
st.markdown("""
<style>
    .stApp { background: radial-gradient(circle at center, #2b2d42 0%, #1a1a2e 100%); color: #edf2f4; }
    #MainMenu, footer {visibility: hidden;}
    .timeline-card {
        background: #222; color: white; border-radius: 10px; text-align: center;
        border: 1px solid rgba(255,255,255,0.2); margin-bottom: 5px; overflow: hidden;
        transition: transform 0.2s; box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    .timeline-card img { width: 100%; object-fit: cover; height: 150px; border-bottom: 2px solid #1DB954; }
    .card-content { padding: 10px; }
    .card-year { font-size: 1.5em; font-weight: 900; color: #1DB954; }
    .card-title { font-weight: bold; font-size: 0.9em; line-height: 1.2; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .reveal-highlight { border: 3px solid #ffd700 !important; transform: scale(1.05); box-shadow: 0 0 15px #ffd700; }
    .mob-insert-btn { width: 100%; padding: 15px; margin: 10px 0; background: rgba(255,255,255,0.1); border: 2px dashed #777; color: white; font-size: 1.2em; border-radius: 8px; cursor: pointer; text-align: center; }
    .mob-insert-btn:hover { background: #00d4ff; color: black; border-style: solid; }
    .mob-card-box { display: flex; align-items: center; gap: 10px; background: rgba(0,0,0,0.4); padding: 10px; border-radius: 8px; border: 1px solid #444; }
    .mob-card-box img { width: 50px; height: 50px; border-radius: 5px; }
    .tv-status { padding: 20px; border-radius: 15px; text-align: center; font-size: 1.5em; font-weight: bold; margin: 20px 0; background: rgba(0,0,0,0.5); border: 2px solid #555; animation: pulse 2s infinite; }
    @keyframes pulse { 0% {border-color: #555;} 50% {border-color: #00d4ff;} 100% {border-color: #555;} }
    .trivia-box { background: rgba(255, 255, 0, 0.1); border-left: 5px solid yellow; padding: 15px; margin-top: 20px; font-style: italic; font-size: 1.2em; }
    .player-tag { background: #444; padding: 5px 10px; margin: 2px; border-radius: 15px; display: inline-block; font-size: 0.9em; border: 1px solid #777; }
</style>
""", unsafe_allow_html=True)

def play_sound_if_needed(state):
    if state.get('sound_trigger') and not state.get('sound_played'):
        sounds = {
            "success": "https://www.myinstants.com/media/sounds/correct.mp3",
            "fail": "https://www.myinstants.com/media/sounds/wrong-answer-sound-effect.mp3",
            "win": "https://www.myinstants.com/media/sounds/tada-fanfare-a.mp3",
            "gameover": "https://www.myinstants.com/media/sounds/spongebob-fail.mp3"
        }
        url = sounds.get(state['sound_trigger'])
        if url:
            # iOS fallback hozzáadva
            st.markdown(f'<audio autoplay muted playsinline><source src="{url}" type="audio/mpeg"></audio>', unsafe_allow_html=True)
            return True
    return False

# --- 5. LOGIKA ---
if 'refresher' not in st.session_state: st.session_state.refresher = 0
if not os.path.exists(DB_FILE): init_db()
state = load_state()

# SECRETS kezelés
default_id = st.secrets.get("SPOTIFY_ID", "")
default_secret = st.secrets.get("SPOTIFY_SECRET", "")
default_groq = st.secrets.get("GROQ_KEY", "")

# Ha nincs secret, akkor a session state-ből olvassuk a manuálisat
if default_groq:
    st.session_state.manual_groq_key = default_groq

with st.sidebar:
    st.title("🎛️ MENÜ")
    role_selection = st.radio("Ki vagy te?", ["📺 TV (Kijelző)", "📱 Játékos (Telefon)"], 
                              index=0 if st.session_state.user_role == "tv" else 1)
    
    new_role = "tv" if "TV" in role_selection else "player"
    if new_role != st.session_state.user_role:
        st.session_state.user_role = new_role
        st.rerun()

    st.divider()

    if st.session_state.user_role == "tv":
        st.header("⚙️ Beállítások")
        
        # JÁTÉKOS HOZZÁADÁSA
        if state['game_phase'] == "LOBBY":
            st.subheader("👥 Játékosok")
            new_p = st.text_input("Játékos neve:", key="new_player_input")
            if st.button("Hozzáad"):
                if len(new_p) > 12: st.error("Max 12 karakter!")
                elif not new_p.strip(): st.error("Üres név!")
                elif new_p in state['players']: st.error("Foglalt név!")
                else:
                    state['players'].append(new_p)
                    save_state(state)
                    st.success(f"{new_p} hozzáadva!")
                    st.rerun()
            if state['players']:
                st.write("Csatlakoztak:")
                for p in state['players']:
                    st.markdown(f"<span class='player-tag'>{p}</span>", unsafe_allow_html=True)
                if st.button("🗑️ Lista Törlése"):
                    state['players'] = []
                    save_state(state)
                    st.rerun()
            st.divider()

        api_id = st.text_input("Spotify ID", value=default_id, type="password")
        api_secret = st.text_input("Spotify Secret", value=default_secret, type="password")
        groq_key_input = st.text_input("Groq Key", value=default_groq, type="password")
        
        # Mentjük a manuális kulcsot a sessionbe, hogy a cache elérje
        if groq_key_input: st.session_state.manual_groq_key = groq_key_input
        
        pl_url = st.text_input("Playlist URL", value="https://open.spotify.com/playlist/37i9dQZF1DXbTxeAdrVG2l")
        target_score = st.number_input("🏆 Cél:", min_value=1, value=10)
        
        if state['game_phase'] == "LOBBY":
            if st.button("🚀 JÁTÉK START", type="primary", disabled=len(state['players']) == 0):
                if api_id and api_secret and pl_url:
                    with st.spinner("Zene betöltése..."):
                        deck = load_spotify_tracks(api_id, api_secret, pl_url)
                        if not deck:
                            st.error("❌ HIBA: Nem sikerült betölteni a zenéket!")
                        else:
                            random.shuffle(deck)
                            current_players = state['players']
                            new_state = {
                                "version": state.get('version', 0) + 1,
                                "game_phase": "GUESSING",
                                "players": current_players,
                                "timelines": {p: [] for p in current_players},
                                "lives": {p: 3 for p in current_players},
                                "deck": deck,
                                "current_mystery_song": None,
                                "turn_index": 0,
                                "game_msg": "",
                                "fun_fact": "",
                                "success": False,
                                "waiting_for_reveal": False,
                                "reveal_processed": False,
                                "reveal_ui_shown": False,
                                "winner": None,
                                "target_score": target_score,
                                "correct_answer_log": None,
                                "sound_trigger": None,
                                "sound_played": False
                            }
                            for p in new_state['players']:
                                if new_state['deck']:
                                    c = new_state['deck'].pop()
                                    c = process_card_ai(c) # Cache-elt hívás
                                    new_state['timelines'][p].append(c)
                            if new_state['deck']:
                                first = new_state['deck'].pop()
                                first = process_card_ai(first)
                                new_state['current_mystery_song'] = first
                            
                            save_state(new_state)
                            st.rerun()
        else:
            if st.button("🔄 ÚJ PARTI (RESET)", type="primary"):
                reset_db()
                st.rerun()

# ==========================
# 📺 TV NÉZET
# ==========================
if st.session_state.user_role == "tv":
    st.title("📺 Hitster Party Pro")

    if play_sound_if_needed(state):
        state['sound_played'] = True
        save_state(state)

    if state.get('game_phase') == "LOBBY":
        st.info("👈 Állítsd össze a csapatot!")
        
        # QR KÓD (Fix #3: URL Paraméter)
        c1, c2 = st.columns([2, 1])
        with c1:
            st.write("📲 **Csatlakozás QR kóddal:**")
            # Megpróbáljuk kitalálni az URL-t, de input mező a legbiztosabb
            base_url = st.text_input("Böngésző linkje (a QR kódhoz):", value="https://te-appod.streamlit.app")
            if base_url:
                qr_link = f"{base_url}?role=player"
                qr = qrcode.make(qr_link)
                buf = BytesIO()
                qr.save(buf)
                st.image(buf, width=250, caption="Szkenneld be!")
        with c2:
            st.metric("Csatlakozva", f"{len(state['players'])} fő")

    elif state.get('game_phase') == "GUESSING":
        if not state['players']:
            st.error("Nincsenek játékosok!")
        else:
            curr_p = state['players'][state['turn_index'] % len(state['players'])]
            song = state['current_mystery_song']
            
            # PONTOK
            cols = st.columns(len(state['players']))
            for i, p in enumerate(state['players']):
                is_active = (p == curr_p)
                lives = state['lives'].get(p, 3)
                hearts = "❤️" * lives + "🖤" * (3-lives)
                score = len(state['timelines'].get(p, []))
                target = state.get('target_score', 10)
                style = "border: 2px solid #00d4ff; background: rgba(0, 212, 255, 0.1);" if is_active else "background: rgba(255,255,255,0.05); opacity: 0.6;"
                cols[i].markdown(f"<div style='{style} padding: 10px; border-radius: 10px; text-align: center;'><div style='font-size: 1.2em; font-weight: bold;'>{p}</div><div>{hearts}</div><div style='font-size: 2em; font-weight: 900;'>{score} / {target}</div></div>", unsafe_allow_html=True)

            st.divider()
            st.markdown(f"### 🎶 Most játszik: {song['artist']} - ???")
            st.components.v1.iframe(f"https://open.spotify.com/embed/track/{song['spotify_id']}", height=80)
            
            # FRAGMENT WATCHDOG
            @st.fragment(run_every=1)
            def auto_reveal_watcher():
                current_state = load_state()
                # 🔒 ATOMIC LOCK & UI CHECK (Fix #4)
                if current_state.get('waiting_for_reveal') and not current_state.get('reveal_processed'):
                    
                    if not current_state.get('reveal_ui_shown'):
                        st.success("✅ TIPP ÉRKEZETT! KIÉRTÉKELÉS...")
                        current_state['reveal_ui_shown'] = True # Csak egyszer mutatjuk
                        save_state(current_state)
                    
                    # LOGIKA ÉS LOCK
                    current_state['reveal_processed'] = True
                    current_state['game_phase'] = "REVEAL"
                    current_state['waiting_for_reveal'] = False
                    
                    current_state['fun_fact'] = get_fun_fact_cached(current_state['current_mystery_song']['artist'], current_state['current_mystery_song']['title'])
                    
                    curr_p_name = current_state['players'][current_state['turn_index'] % len(current_state['players'])]
                    
                    if current_state['success']:
                        current_state['sound_trigger'] = "success"
                    else:
                        current_state['lives'][curr_p_name] -= 1
                        current_state['sound_trigger'] = "fail"
                    
                    current_state['sound_played'] = False
                    
                    if len(current_state['timelines'][curr_p_name]) >= current_state.get('target_score', 10):
                        current_state['game_phase'] = "VICTORY"
                        current_state['winner'] = curr_p_name
                        current_state['sound_trigger'] = "win"
                    elif current_state['lives'][curr_p_name] <= 0:
                         current_state['game_phase'] = "GAME_OVER"
                         current_state['sound_trigger'] = "gameover"
                    
                    save_state(current_state)
                    st.session_state.refresher += 1
                    st.rerun()
                else:
                    st.markdown(f"<div class='tv-status'>👉 {curr_p} tippel a telefonján...</div>", unsafe_allow_html=True)

            auto_reveal_watcher()
            st.divider()
            
            timeline = state['timelines'][curr_p]
            if timeline:
                t_cols = st.columns(len(timeline))
                for i, card in enumerate(timeline):
                    with t_cols[i]:
                        st.markdown(f"<div class='timeline-card'><img src='{card.get('image', '')}'><div class='card-content'><div class='card-year'>{card['year']}</div><div class='card-title'>{card['title']}</div></div></div>", unsafe_allow_html=True)

    elif state.get('game_phase') == "REVEAL":
        song = state['current_mystery_song']
        color = "#00ff00" if state['success'] else "#ff4b4b"
        msg = "TALÁLT! 🎉" if state['success'] else "NEM TALÁLT... 😢"
        
        c1, c2 = st.columns([1, 2])
        with c1: st.image(song.get('image'), use_container_width=True)
        with c2:
            st.markdown(f"<h1 style='color:{color}; font-size:3em; margin:0;'>{msg}</h1>", unsafe_allow_html=True)
            st.markdown(f"<h2>{song['artist']} - {song['title']}</h2>", unsafe_allow_html=True)
            st.markdown(f"<h1 style='font-size:4em; font-weight:900;'>{song['year']}</h1>", unsafe_allow_html=True)
            if state.get('fun_fact'): st.markdown(f"<div class='trivia-box'>🧠 <b>Tudtad?</b> {state['fun_fact']}</div>", unsafe_allow_html=True)
        
        st.divider()
        
        curr_p = state['players'][state['turn_index'] % len(state['players'])]
        timeline = state['timelines'][curr_p]
        if timeline:
            t_cols = st.columns(len(timeline))
            for i, card in enumerate(timeline):
                css_class = "timeline-card reveal-highlight" if (state['success'] and card['spotify_id'] == song['spotify_id']) else "timeline-card"
                with t_cols[i]:
                    st.markdown(f"<div class='{css_class}'><img src='{card.get('image', '')}'><div class='card-content'><div class='card-year'>{card['year']}</div><div class='card-title'>{card['title']}</div></div></div>", unsafe_allow_html=True)

        if st.button("➡️ KÖVETKEZŐ KÖR", type="primary", use_container_width=True):
            state['turn_index'] += 1
            if state['deck']:
                next_song = state['deck'].pop()
                next_song = process_card_ai(next_song)
                state['current_mystery_song'] = next_song
                state['game_phase'] = "GUESSING"
                state['fun_fact'] = ""
                state['correct_answer_log'] = None
                state['sound_trigger'] = None
                state['sound_played'] = False
                state['reveal_processed'] = False
                state['reveal_ui_shown'] = False # Reset flag
            else: state['game_phase'] = "GAME_OVER"
            save_state(state)
            st.rerun()

    elif state.get('game_phase') == "VICTORY":
        st.balloons()
        st.title(f"🏆 GYŐZTES: {state.get('winner')}! 🏆")
        st.image("https://media.giphy.com/media/26tOZ42Mg6pbTUPHW/giphy.gif")
        if st.button("Új játék"): reset_db(); st.rerun()

    elif state.get('game_phase') == "GAME_OVER":
        st.title("💀 JÁTÉK VÉGE! Elfogytak az életek.")
        if st.button("Újra"): reset_db(); st.rerun()

# ==========================
# 📱 TELEFON NÉZET
# ==========================
elif st.session_state.user_role == "player":
    st.header("📱 Játékos")
    
    if 'my_name' not in st.session_state:
        players_list = state.get('players', [])
        if not players_list:
            st.warning("Még nincsenek játékosok! Add hozzá őket a TV-n.")
            if st.button("Frissítés"): st.rerun()
        else:
            selected_player = st.selectbox("Ki vagy te?", players_list)
            if st.button("Belépés", use_container_width=True):
                st.session_state.my_name = selected_player
                st.rerun()
    else:
        me = st.session_state.my_name
        lives = state['lives'].get(me, 3)
        st.caption(f"Belépve: **{me}** | Életek: {'❤️' * lives}")
        
        if st.button("🔄 Frissítés", use_container_width=True): st.rerun()

        # 🔒 OPTIMISTIC LOCKING BETÖLTÉS (Fix #2)
        state = load_state()
        local_version = state.get('version', 0)

        if state.get('game_phase') == "GUESSING":
            curr_p = state['players'][state['turn_index'] % len(state['players'])]
            
            if curr_p == me:
                if state.get('waiting_for_reveal'):
                    st.success("✅ TIPP ELKÜLDVE!")
                    st.info("Nézd a TV-t!")
                else:
                    st.success("🔴 TE JÖSSZ!")
                    timeline = state['timelines'][me]
                    
                    def try_save_guess(pos):
                        # Újratöltés mentés előtt ellenőrzéshez
                        fresh_state = load_state()
                        if fresh_state.get('version', 0) != local_version:
                            st.toast("⚠️ A játék állapota frissült, próbáld újra!")
                            time.sleep(1)
                            st.rerun()
                            return

                        song = fresh_state['current_mystery_song']
                        already_in = any(c['spotify_id'] == song['spotify_id'] for c in timeline)
                        
                        if not already_in:
                            fresh_state['success'] = check_guess_logic(timeline, song, pos)
                            fresh_state['correct_answer_log'] = song
                            if fresh_state['success']: fresh_state['timelines'][me].insert(pos, song)
                            
                            fresh_state['waiting_for_reveal'] = True
                            fresh_state['reveal_processed'] = False
                            save_state(fresh_state)
                            st.rerun()

                    if st.button("⬇️ IDE (Elejére) ⬇️", key="mob_btn_start", use_container_width=True):
                        try_save_guess(0)

                    for i, card in enumerate(timeline):
                        st.markdown(f"<div class='mob-card-box'><img src='{card.get('image', '')}'><div><div style='font-weight:bold; font-size:1.2em'>{card['year']}</div><div>{card['title']}</div></div></div>", unsafe_allow_html=True)
                        if st.button(f"⬇️ IDE ⬇️", key=f"mob_btn_{i+1}", use_container_width=True):
                            try_save_guess(i + 1)
            else:
                st.warning(f"Most {curr_p} gondolkodik...")
                
        elif state.get('game_phase') == "REVEAL":
            song = state.get('correct_answer_log') or state['current_mystery_song']
            color = "green" if state['success'] else "red"
            msg = "TALÁLT!" if state['success'] else "NEM TALÁLT..."
            st.markdown(f"<h2 style='text-align:center; color:{color};'>{msg}</h2>", unsafe_allow_html=True)
            if song:
                st.image(song.get('image', ''), use_container_width=True)
                st.markdown(f"<div style='text-align:center'>HELYES ÉV: <b>{song['year']}</b><br>{song['title']}</div>", unsafe_allow_html=True)
            st.info("Várd meg a következő kört!")
        
        else:
            st.info("Várakozás a játékra...")
