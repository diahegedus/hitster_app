import streamlit as st
import random
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import google.generativeai as genai
import time

# --- 1. SESSION STATE ---
if 'game_started' not in st.session_state:
    st.session_state.game_started = False
if 'players' not in st.session_state:
    st.session_state.players = [] 
if 'ai_logs' not in st.session_state:
    st.session_state.ai_logs = []

# --- 2. KONFIGURÁCIÓ ---
st.set_page_config(
    page_title="Hitster TV Party", 
    page_icon="🎵", 
    layout="wide",
    initial_sidebar_state="collapsed" if st.session_state.game_started else "expanded"
)

# --- 3. STÍLUS 🎨 ---
st.markdown("""
<style>
    .stApp {
        background: radial-gradient(circle at center, #2b2d42 0%, #1a1a2e 100%);
        color: #edf2f4;
    }
    #MainMenu, footer {visibility: hidden;}

    /* KÁRTYA STÍLUS */
    .timeline-card {
        background: linear-gradient(180deg, #1DB954 0%, #117a35 100%);
        color: white;
        padding: 10px;
        border-radius: 10px;
        text-align: center;
        box-shadow: 0 4px 8px rgba(0,0,0,0.4);
        border: 1px solid rgba(255,255,255,0.2);
        transition: transform 0.2s;
        height: 100%;
        position: relative;
    }
    .timeline-card:hover { transform: scale(1.03); z-index: 10; }
    
    .card-year { 
        font-size: 2em; font-weight: 900; 
        border-bottom: 1px solid rgba(255,255,255,0.3); margin-bottom: 5px;
        text-shadow: 1px 1px 2px black; 
    }
    .ai-badge { font-size: 0.5em; vertical-align: super; color: #ffff00; text-shadow: 0 0 5px gold; }
    .card-title { font-weight: bold; font-size: 1.1em; line-height: 1.2; }
    .card-artist { font-size: 0.9em; opacity: 0.9; margin-bottom: 5px; }

    /* GOMBOK */
    div[data-testid="column"] button {
        background-color: rgba(255,255,255,0.1) !important;
        border: 1px dashed #777 !important;
        color: #aaa !important;
        border-radius: 8px !important;
        font-size: 12px !important;
        padding: 10px 0 !important;
        width: 100%;
        transition: all 0.2s;
    }
    div[data-testid="column"] button:hover {
        background-color: #00d4ff !important;
        color: #000 !important;
        border-style: solid !important;
        transform: scale(1.1);
    }

    /* HEADER */
    .mystery-sticky {
        position: sticky; top: 0; z-index: 100;
        background: rgba(26, 26, 46, 0.95);
        padding: 15px 0; border-bottom: 2px solid #ff4b4b; margin-bottom: 20px;
        backdrop-filter: blur(10px);
    }
    .mystery-box {
        border: 2px solid #ff4b4b; border-radius: 15px; padding: 10px;
        text-align: center; background: #222; max-width: 500px; margin: 0 auto;
    }
    .score-box {
        background: rgba(255,255,255,0.05); padding: 5px 15px;
        border-radius: 8px; text-align: center; border: 1px solid transparent;
    }
    .score-active { border-color: #00d4ff; background: rgba(0, 212, 255, 0.1); }
    .player-tag { background: #444; padding: 5px 10px; margin: 2px; border-radius: 15px; display: inline-block; font-size: 0.9em; }
    
    /* LOG DOBOZ */
    .log-box {
        font-family: monospace; font-size: 0.8em; background: #000; color: #0f0; padding: 10px; border-radius: 5px; max-height: 200px; overflow-y: auto;
    }
</style>
""", unsafe_allow_html=True)

# --- 4. OKOS AI LOGIKA (FAILSAFE) ---
def log_ai(message):
    timestamp = time.strftime("%H:%M:%S")
    st.session_state.ai_logs.insert(0, f"[{timestamp}] {message}")

def fix_card_with_ai(card, api_key):
    if not api_key: 
        return card
    
    genai.configure(api_key=api_key)
    
    # Kézzel definiált lista - ezeket próbáljuk sorban
    # Nem használjuk a list_models()-t, mert az is hibát dobhat
    models_to_try = ['gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-pro', 'gemini-1.0-pro']
    
    prompt = f"""
    Fact Check: What is the ORIGINAL single/album release year of "{card['title']}" by "{card['artist']}"?
    - Reply with ONLY the 4-digit year. Example: 1980
    """

    for model_name in models_to_try:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            text = response.text.strip()
            
            if text.isdigit():
                ai_year = int(text)
                orig_year = card['year']
                log_ai(f"✅ Siker ({model_name}): {card['title']} -> {ai_year}")
                
                if 1900 < ai_year <= 2025:
                    if ai_year != orig_year and abs(ai_year - orig_year) > 0:
                        card['year'] = ai_year
                        card['fixed_by_ai'] = True
                        st.toast(f"AI javította: {orig_year} -> {ai_year}", icon="🤖")
                return card # Ha sikerült, kilépünk
            
        except Exception:
            # Ha ez a modell nem megy, csendben próbáljuk a következőt
            continue
            
    # Ha egyik sem sikerült
    log_ai(f"⚠️ Egyik AI modell sem válaszolt a dalra: {card['title']}")
    return card

def load_spotify_tracks(spotify_id, spotify_secret, playlist_url):
    try:
        auth_manager = SpotifyClientCredentials(client_id=spotify_id, client_secret=spotify_secret)
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
        else:
            st.error("Hibás link!")
            return []
        return tracks_data
    except Exception as e:
        st.error(f"Spotify Hiba: {e}")
        return []

def add_player_callback():
    name = st.session_state.new_player_name
    if name and name not in st.session_state.players:
        st.session_state.players.append(name)
        st.session_state.new_player_name = "" 

# --- 5. OLDALSÁV ---
with st.sidebar:
    st.title("👥 Játékosok")
    st.text_input("Írd be a nevet és nyomj Entert:", key="new_player_name", on_change=add_player_callback)
    
    if st.session_state.players:
        st.write("Csatlakoztak:")
        for p in st.session_state.players:
            st.markdown(f"<span class='player-tag'>👤 {p}</span>", unsafe_allow_html=True)
        if st.button("🗑️ Lista törlése"):
            st.session_state.players = []
            st.rerun()
    else:
        st.info("Adj hozzá valakit!")

    st.divider()
    st.header("⚙️ Beállítások")
    api_id = st.text_input("Spotify ID", type="password")
    api_secret = st.text_input("Spotify Secret", type="password")
    pl_url = st.text_input("Playlist Link", value="https://open.spotify.com/playlist/2WQxrq5bmHMlVuzvtwwywV?si=KGQWViY9QESfrZc21btFzA")
    
    st.markdown("### 🧠 AI és Diagnosztika")
    gemini_key_input = st.text_input("Gemini API Key", type="password")
    
    st.markdown("<b>AI Napló:</b>", unsafe_allow_html=True)
    log_content = "<br>".join(st.session_state.ai_logs)
    st.markdown(f"<div class='log-box'>{log_content}</div>", unsafe_allow_html=True)
    
    st.markdown("---")
    
    if st.button("🚀 BULI INDÍTÁSA", type="primary", disabled=len(st.session_state.players) == 0):
        if len(st.session_state.players) > 0 and api_id and api_secret and pl_url:
            with st.spinner("Lemezek válogatása..."):
                raw_deck = load_spotify_tracks(api_id, api_secret, pl_url)
                if raw_deck:
                    random.shuffle(raw_deck)
                    st.session_state.deck = raw_deck
                    st.session_state.gemini_key = gemini_key_input
                    st.session_state.timelines = {}
                    for p in st.session_state.players:
                        if not st.session_state.deck: break
                        card = st.session_state.deck.pop()
                        if gemini_key_input: fix_card_with_ai(card, gemini_key_input)
                        st.session_state.timelines[p] = [card]
                    
                    if st.session_state.deck:
                        first = st.session_state.deck.pop()
                        if gemini_key_input: fix_card_with_ai(first, gemini_key_input)
                        st.session_state.current_mystery_song = first
                        st.session_state.turn_index = 0
                        st.session_state.game_phase = "GUESSING"
                        st.session_state.game_started = True
                        st.rerun()

# --- 6. FŐ APP ---
if st.session_state.game_started:
    curr_p = st.session_state.players[st.session_state.turn_index % len(st.session_state.players)]
    
    # HEADER
    st.markdown('<div class="mystery-sticky">', unsafe_allow_html=True)
    c_scores = st.columns(len(st.session_state.players))
    for i, p in enumerate(st.session_state.players):
        active = "score-active" if p == curr_p else ""
        score = len(st.session_state.timelines.get(p, []))
        c_scores[i].markdown(f"<div class='score-box {active}'><b>{p}</b>: {score}</div>", unsafe_allow_html=True)

    if st.session_state.game_phase == "GUESSING":
        song = st.session_state.current_mystery_song
        st.markdown(f"""
        <div class='mystery-box'>
            <div style='color:#bbb; font-size:0.8em;'>Most szól:</div>
            <div style='font-size:1.1em; color:#fff;'>{song['artist']} - <span style='color:#ff4b4b; font-weight:bold'>{song['title']}</span></div>
        </div>
        """, unsafe_allow_html=True)
    elif st.session_state.game_phase == "REVEAL":
        color = "#00ff00" if st.session_state.success else "#ff4b4b"
        st.markdown(f"<h2 style='text-align:center; color:{color}; margin:0;'>{st.session_state.game_msg}</h2>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True) 

    # JÁTÉKTÉR
    if st.session_state.game_phase == "GUESSING":
        c1, c2, c3 = st.columns([1,2,1])
        with c2:
             st.components.v1.iframe(f"https://open.spotify.com/embed/track/{st.session_state.current_mystery_song['spotify_id']}", height=80)
        
        st.markdown(f"<h3 style='text-align:center'>👇 {curr_p} idővonala 👇</h3>", unsafe_allow_html=True)
        
        timeline = st.session_state.timelines[curr_p]
        
        # --- GRID RENDER ---
        CARDS_PER_ROW = 4
        
        for row_start in range(0, len(timeline), CARDS_PER_ROW):
            row_end = min(row_start + CARDS_PER_ROW, len(timeline))
            
            elements = []
            for i in range(row_start, row_end):
                elements.append({"type": "btn", "index": i})
                elements.append({"type": "card", "index": i})
            
            # Utolsó záró gomb
            if row_end == len(timeline):
                 elements.append({"type": "btn", "index": row_end})

            if elements:
                cols = st.columns([1 if e["type"]=="btn" else 4 for e in elements])
                
                for idx, el in enumerate(elements):
                    with cols[idx]:
                        i = el["index"]
                        if el["type"] == "btn":
                            st.markdown("<br>", unsafe_allow_html=True)
                            # FONTOS: Itt tesszük bele a játékos nevét a kulcsba!
                            # key = btn_JatekosNeve_0
                            unique_key = f"btn_{curr_p}_{i}"
                            
                            if st.button("➕", key=unique_key, use_container_width=True):
                                song = st.session_state.current_mystery_song
                                prev_ok = (i==0) or (timeline[i-1]['year'] <= song['year'])
                                next_ok = (i==len(timeline)) or (timeline[i]['year'] >= song['year'])
                                st.session_state.success = (prev_ok and next_ok)
                                st.session_state.game_msg = f"TALÁLT! ({song['year']})" if st.session_state.success else f"NEM... ({song['year']})"
                                if st.session_state.success: st.session_state.timelines[curr_p].insert(i, song)
                                st.session_state.game_phase = "REVEAL"
                                st.rerun()
                        else:
                            card = timeline[i]
                            ai_badge = "<span class='ai-badge'>✨</span>" if card.get('fixed_by_ai') else ""
                            st.markdown(f"""
                            <div class='timeline-card'>
                                <div class='card-year'>{card['year']}{ai_badge}</div>
                                <div class='card-title'>{card['title']}</div>
                                <div class='card-artist'>{card['artist']}</div>
                            </div>
                            """, unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)

    elif st.session_state.game_phase == "REVEAL":
        if st.session_state.success: st.balloons()
        
        def next_turn():
            st.session_state.turn_index += 1
            if st.session_state.deck:
                next_song = st.session_state.deck.pop()
                if st.session_state.get('gemini_key'):
                    fix_card_with_ai(next_song, st.session_state.gemini_key)
                st.session_state.current_mystery_song = next_song
                st.session_state.game_phase = "GUESSING"
            else:
                st.session_state.game_phase = "GAME_OVER"

        c1, c2, c3 = st.columns([1,1,1])
        c2.button("KÖVETKEZŐ ➡️", on_click=next_turn, type="primary", use_container_width=True)
        
        timeline = st.session_state.timelines[curr_p]
        CARDS_PER_ROW = 5
        for row_start in range(0, len(timeline), CARDS_PER_ROW):
            row_cards = timeline[row_start : row_start + CARDS_PER_ROW]
            cols = st.columns(len(row_cards))
            for idx, card in enumerate(row_cards):
                is_new = (card == st.session_state.current_mystery_song and st.session_state.success)
                style = "border: 3px solid #ffd166; transform: scale(1.05);" if is_new else ""
                ai_badge = "<span class='ai-badge'>✨</span>" if card.get('fixed_by_ai') else ""
                cols[idx].markdown(f"""
                <div class='timeline-card' style='{style}'>
                    <div class='card-year'>{card['year']}{ai_badge}</div>
                    <div class='card-title'>{card['title']}</div>
                </div>
                """, unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)

    elif st.session_state.game_phase == "GAME_OVER":
        st.title("JÁTÉK VÉGE!")
        if st.button("Újra"): st.session_state.clear(); st.rerun()

else:
    st.title("📺 Hitster Party")
    st.info("Add hozzá a játékosokat a bal oldali menüben!")
