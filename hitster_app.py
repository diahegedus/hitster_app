import streamlit as st
import random
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import google.generativeai as genai
import time

# --- 1. SESSION STATE ---
if 'game_started' not in st.session_state:
    st.session_state.game_started = False

# --- 2. KONFIGURÁCIÓ ---
st.set_page_config(
    page_title="Hitster TV Party", 
    page_icon="🎵", 
    layout="wide",
    initial_sidebar_state="collapsed" if st.session_state.game_started else "expanded"
)

# --- 3. STÍLUS (FÜGGŐLEGES TIMELINE DESIGN) 🎨 ---
st.markdown("""
<style>
    /* HÁTTÉR */
    .stApp {
        background: radial-gradient(circle at center, #2b2d42 0%, #1a1a2e 100%);
        color: #edf2f4;
    }
    #MainMenu, footer {visibility: hidden;}

    /* IDŐVONAL KÁRTYA (Széles) */
    .timeline-card {
        background: linear-gradient(90deg, #1DB954 0%, #117a35 100%);
        color: white;
        padding: 15px 25px;
        border-radius: 12px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin: 0 auto;
        max-width: 600px; /* Ne legyen túl széles TV-n se */
        box-shadow: 0 4px 10px rgba(0,0,0,0.3);
        border: 1px solid rgba(255,255,255,0.1);
    }
    .card-year { font-size: 2.5em; font-weight: 900; margin-right: 20px; text-shadow: 2px 2px 0 rgba(0,0,0,0.2); }
    .card-info { text-align: left; flex-grow: 1; }
    .card-artist { font-size: 1em; opacity: 0.9; }
    .card-title { font-size: 1.4em; font-weight: bold; }

    /* BESZÚRÓ GOMBOK (DROP ZONES) */
    /* Ezek a gombok mostantól szaggatott vonalú dobozok a kártyák között */
    .insert-btn-wrapper button {
        background-color: transparent !important;
        border: 2px dashed #555 !important;
        color: #888 !important;
        border-radius: 10px !important;
        width: 100%;
        max-width: 600px;
        margin: 5px auto;
        display: block;
        transition: all 0.2s;
    }
    .insert-btn-wrapper button:hover {
        border-color: #00d4ff !important;
        color: #00d4ff !important;
        background-color: rgba(0, 212, 255, 0.05) !important;
        transform: scale(1.02);
    }

    /* FŐ GOMBOK (Indítás, Tovább) - Ezek maradnak színesek */
    .main-action-btn button {
        background: linear-gradient(90deg, #ff4b4b 0%, #d90429 100%) !important;
        color: white !important;
        border: none !important;
        font-weight: bold;
        font-size: 1.2em;
    }

    /* REJTÉLYES DOBOZ (STICKY - Mindig látható felül) */
    .mystery-sticky {
        position: sticky;
        top: 0;
        z-index: 999;
        background: rgba(26, 26, 46, 0.95);
        padding: 15px 0;
        border-bottom: 2px solid #ff4b4b;
        margin-bottom: 20px;
        backdrop-filter: blur(5px);
    }
    .mystery-box {
        border: 2px solid #ff4b4b;
        border-radius: 15px;
        padding: 15px;
        text-align: center;
        background: #222;
        max-width: 600px;
        margin: 0 auto;
    }

    /* PONTOZÁS */
    .score-container {
        display: flex;
        justify-content: center;
        gap: 20px;
        margin-bottom: 20px;
    }
    .score-box {
        background: rgba(255,255,255,0.05);
        padding: 10px 20px;
        border-radius: 10px;
        text-align: center;
        min-width: 100px;
    }
    .score-active { border: 2px solid #00d4ff; box-shadow: 0 0 10px #00d4ff; }

</style>
""", unsafe_allow_html=True)

# --- 4. LOGIKA ---
def fix_card_with_ai(card, api_key):
    if not api_key: return card
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-pro')
        prompt = f"""What is the ORIGINAL release year of "{card['title']}" by "{card['artist']}"? Return ONLY the year (4 digits)."""
        response = model.generate_content(prompt)
        text = response.text.strip()
        if text.isdigit():
            ai_year = int(text)
            if 1900 < ai_year <= 2025 and ai_year < card['year']:
                card['year'] = ai_year
    except: pass
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
        st.error(f"Hiba: {e}")
        return []

def prepare_next_turn():
    st.session_state.turn_index += 1
    if st.session_state.deck:
        next_song = st.session_state.deck.pop()
        if st.session_state.get('gemini_key'):
            fix_card_with_ai(next_song, st.session_state.gemini_key)
        st.session_state.current_mystery_song = next_song
        st.session_state.game_phase = "GUESSING"
    else:
        st.session_state.game_phase = "GAME_OVER"

# --- 5. APP STRUKTÚRA ---
if 'players' not in st.session_state: st.session_state.players = ["Jorgosz", "Lilla", "Józsi", "Dia"]

with st.sidebar:
    st.header("⚙️ DJ Pult")
    api_id = st.text_input("Spotify ID", type="password")
    api_secret = st.text_input("Spotify Secret", type="password")
    pl_url = st.text_input("Playlist Link", value="https://open.spotify.com/playlist/2WQxrq5bmHMlVuzvtwwywV?si=KGQWViY9QESfrZc21btFzA")
    gemini_key_input = st.text_input("Gemini API (Opcionális)", type="password")
    st.markdown('<div class="main-action-btn">', unsafe_allow_html=True)
    if st.button("🚀 BULI INDÍTÁSA"):
        if api_id and api_secret and pl_url:
            with st.spinner("Betöltés..."):
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
    st.markdown('</div>', unsafe_allow_html=True)

if st.session_state.game_started:
    curr_p = st.session_state.players[st.session_state.turn_index % len(st.session_state.players)]
    
    # --- FELSŐ RÉSZ (FIX) ---
    st.markdown('<div class="mystery-sticky">', unsafe_allow_html=True)
    
    # Pontszámok (Kompakt)
    cols = st.columns(len(st.session_state.players))
    for i, p in enumerate(st.session_state.players):
        active = "score-active" if p == curr_p else ""
        timeline_len = len(st.session_state.timelines.get(p, []))
        cols[i].markdown(f"""
            <div class='score-box {active}'>
                <div style='font-size:0.8em; opacity:0.8'>{p}</div>
                <div style='font-size:1.5em; font-weight:bold; color:#ffcc00'>{timeline_len}</div>
            </div>
        """, unsafe_allow_html=True)

    # Rejtélyes dal doboz
    if st.session_state.game_phase == "GUESSING":
        song = st.session_state.current_mystery_song
        st.markdown(f"""
        <div class='mystery-box'>
            <div style='color:#bbb; font-size:0.9em;'>Most játszott:</div>
            <div style='font-size:1.2em; color:#fff;'>{song['artist']}</div>
            <div style='font-size:1.8em; font-weight:bold; color:#ff4b4b;'>{song['title']}</div>
        </div>
        """, unsafe_allow_html=True)
    elif st.session_state.game_phase == "REVEAL":
        res_color = "#00ff00" if st.session_state.success else "#ff0000"
        st.markdown(f"""
        <div class='mystery-box' style='border-color:{res_color}'>
            <h2 style='color:{res_color}; margin:0;'>{st.session_state.game_msg}</h2>
        </div>
        """, unsafe_allow_html=True)
        
    st.markdown('</div>', unsafe_allow_html=True) 
    # --- FELSŐ RÉSZ VÉGE ---

    # --- FÜGGŐLEGES IDŐVONAL ---
    if st.session_state.game_phase == "GUESSING":
        # Lejátszó
        c1, c2, c3 = st.columns([1,2,1])
        with c2:
             st.components.v1.iframe(f"https://open.spotify.com/embed/track/{st.session_state.current_mystery_song['spotify_id']}", height=80)
        
        st.markdown(f"<h3 style='text-align:center'>👇 {curr_p}, hova teszed az idővonaladon? 👇</h3>", unsafe_allow_html=True)
        
        timeline = st.session_state.timelines[curr_p]
        
        # A CIKLUS MOST FÜGGŐLEGESEN ÉPÍTKEZIK
        for i in range(len(timeline) + 1):
            
            # 1. BESZÚRÓ GOMB (GAP)
            st.markdown('<div class="insert-btn-wrapper">', unsafe_allow_html=True)
            if st.button(f"➕ Ide illik? ➕", key=f"gap_{i}"):
                song = st.session_state.current_mystery_song
                prev_ok = (i==0) or (timeline[i-1]['year'] <= song['year'])
                next_ok = (i==len(timeline)) or (timeline[i]['year'] >= song['year'])
                st.session_state.success = (prev_ok and next_ok)
                st.session_state.game_msg = f"{song['year']}"
                if st.session_state.success: st.session_state.timelines[curr_p].insert(i, song)
                st.session_state.game_phase = "REVEAL"
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

            # 2. KÁRTYA (HA VAN)
            if i < len(timeline):
                card = timeline[i]
                st.markdown(f"""
                <div class='timeline-card'>
                    <div class='card-year'>{card['year']}</div>
                    <div class='card-info'>
                        <div class='card-artist'>{card['artist']}</div>
                        <div class='card-title'>{card['title']}</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # Kis nyilacska lefelé
                if i < len(timeline) - 0:
                    st.markdown("<div style='text-align:center; font-size:1.5em; opacity:0.3; margin:-10px 0;'>⬇</div>", unsafe_allow_html=True)

    elif st.session_state.game_phase == "REVEAL":
        if st.session_state.success: st.balloons()
        
        st.markdown('<div class="main-action-btn" style="text-align:center; margin:20px;">', unsafe_allow_html=True)
        st.button("Következő Játékos ➡️", on_click=prepare_next_turn)
        st.markdown('</div>', unsafe_allow_html=True)

        # Csak a kártyák listája (gombok nélkül)
        timeline = st.session_state.timelines[curr_p]
        for card in timeline:
            highlight = "border: 3px solid #ffd166; transform: scale(1.05);" if (card == st.session_state.current_mystery_song and st.session_state.success) else ""
            st.markdown(f"""
            <div class='timeline-card' style='{highlight}'>
                <div class='card-year'>{card['year']}</div>
                <div class='card-info'>
                    <div class='card-artist'>{card['artist']}</div>
                    <div class='card-title'>{card['title']}</div>
                </div>
            </div>
            <div style='text-align:center; font-size:1.5em; opacity:0.3; margin:-10px 0;'>⬇</div>
            """, unsafe_allow_html=True)

    elif st.session_state.game_phase == "GAME_OVER":
        st.markdown("<h1 style='text-align:center; color:gold'>🏆 JÁTÉK VÉGE! 🏆</h1>", unsafe_allow_html=True)
        winner = max(st.session_state.timelines, key=lambda k: len(st.session_state.timelines[k]))
        st.markdown(f"<h2 style='text-align:center'>Győztes: {winner}</h2>", unsafe_allow_html=True)
        st.balloons()
        st.markdown('<div class="main-action-btn" style="text-align:center;">', unsafe_allow_html=True)
        if st.button("Újra"): st.session_state.clear(); st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

else:
    st.markdown("<h1 style='text-align:center; margin-top:100px;'>📺 TV HITSTER</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align:center; color:#aaa'>Nyisd ki a bal oldali menüt a kezdéshez!</h3>", unsafe_allow_html=True)
