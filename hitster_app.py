import streamlit as st
import random
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import google.generativeai as genai
import time

# --- 1. SESSION STATE KEZELÉS ---
if 'game_started' not in st.session_state:
    st.session_state.game_started = False

# --- 2. KONFIGURÁCIÓ ---
st.set_page_config(
    page_title="Hitster TV Party", 
    page_icon="🎵", 
    layout="wide",
    initial_sidebar_state="collapsed" if st.session_state.game_started else "expanded"
)

# --- 3. VIZUÁLIS TUNING (CSS MAGIC) ✨ ---
st.markdown("""
<style>
    /* 1. HÁTTÉR: Mély, modern színátmenet */
    .stApp {
        background: radial-gradient(circle at center, #2b2d42 0%, #1a1a2e 100%);
        color: #edf2f4;
        font-family: 'Helvetica Neue', sans-serif;
    }

    /* 2. ELTÜNTETJÜK A FELESLEGES ELEMEKET (De a menügomb marad!) */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* 3. EREDMÉNYJELZŐ (GLASSMORPHISM) */
    .score-card {
        background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 20px;
        padding: 15px;
        text-align: center;
        transition: all 0.3s ease;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
    }
    
    /* Az aktív játékos NEON keretet kap */
    .score-active {
        border: 2px solid #00d4ff;
        box-shadow: 0 0 20px rgba(0, 212, 255, 0.6);
        transform: scale(1.08);
        background: rgba(0, 212, 255, 0.1);
    }
    
    .score-num {
        font-size: 3.5em; /* Óriás számok TV-re */
        font-weight: 800;
        color: #ffd166;
        margin: 0;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.5);
    }
    
    .score-name {
        font-size: 1.2em;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-top: 5px;
    }

    /* 4. IDŐVONAL KÁRTYÁK (Spotify Stílus) */
    .timeline-card {
        background: linear-gradient(145deg, #1DB954 0%, #117a35 100%);
        color: white;
        padding: 20px 10px;
        border-radius: 15px;
        text-align: center;
        margin: 10px 5px;
        box-shadow: 0 10px 20px rgba(0,0,0,0.4);
        border: 1px solid rgba(255,255,255,0.2);
        transition: transform 0.2s;
    }
    .timeline-card:hover {
        transform: translateY(-5px);
    }
    
    .timeline-year {
        font-size: 2.2em;
        font-weight: 900;
        border-bottom: 2px solid rgba(255,255,255,0.4);
        margin-bottom: 8px;
        padding-bottom: 5px;
        text-shadow: 1px 1px 2px rgba(0,0,0,0.3);
    }

    /* 5. REJTÉLYES DOBOZ (PULZÁLÓ ANIMÁCIÓ) */
    @keyframes pulse-border {
        0% { border-color: #ff4b4b; box-shadow: 0 0 0 0 rgba(255, 75, 75, 0.7); }
        70% { border-color: #ff4b4b; box-shadow: 0 0 20px 10px rgba(255, 75, 75, 0); }
        100% { border-color: #ff4b4b; box-shadow: 0 0 0 0 rgba(255, 75, 75, 0); }
    }
    
    .mystery-box {
        background-color: rgba(30, 30, 30, 0.8);
        border: 3px solid #ff4b4b;
        border-radius: 20px;
        padding: 30px;
        text-align: center;
        margin: 20px 0;
        animation: pulse-border 2s infinite;
    }
    
    .mystery-artist { font-size: 1.2em; color: #bbb; margin-bottom: 5px; }
    .mystery-title { font-size: 2.2em; font-weight: bold; color: white; margin: 0; }

    /* 6. GOMBOK */
    div.stButton > button {
        background: linear-gradient(90deg, #ff4b4b 0%, #d90429 100%);
        color: white;
        font-size: 18px !important;
        font-weight: bold;
        padding: 12px 28px;
        border-radius: 50px;
        border: none;
        box-shadow: 0 4px 15px rgba(255, 75, 75, 0.4);
        transition: all 0.3s ease;
        width: 100%;
    }
    div.stButton > button:hover {
        transform: scale(1.05);
        box-shadow: 0 6px 20px rgba(255, 75, 75, 0.6);
    }
    div.stButton > button:active {
        transform: scale(0.95);
    }
    
    /* Kisebb "IDE" gombok az idővonalban */
    div[data-testid="column"] button {
        background: #4a4e69;
        box-shadow: none;
        font-size: 14px !important;
        padding: 8px 0;
    }
    div[data-testid="column"] button:hover {
        background: #00d4ff;
        color: #1a1a2e;
    }

</style>
""", unsafe_allow_html=True)

# --- 4. AI LOGIKA ---
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

# --- 5. SPOTIFY LETÖLTÉS ---
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
            st.error("Érvénytelen link!")
            return []
        return tracks_data
    except Exception as e:
        st.error(f"Spotify Hiba: {e}")
        return []

# --- 6. CALLBACKS ---
def prepare_next_turn():
    st.session_state.turn_index += 1
    if st.session_state.deck:
        next_song = st.session_state.deck.pop()
        # AI Elemzés
        if st.session_state.get('gemini_key'):
            fix_card_with_ai(next_song, st.session_state.gemini_key)
        
        st.session_state.current_mystery_song = next_song
        st.session_state.game_phase = "GUESSING"
    else:
        st.session_state.game_phase = "GAME_OVER"

# --- 7. INDÍTÁS ÉS SIDEBAR ---
if 'players' not in st.session_state: st.session_state.players = ["Jorgosz", "Lilla", "Józsi", "Dia"]

with st.sidebar:
    st.header("⚙️ DJ Pult")
    api_id = st.text_input("Spotify Client ID", type="password")
    api_secret = st.text_input("Spotify Client Secret", type="password")
    pl_url = st.text_input("Playlist Link", value="https://open.spotify.com/playlist/2WQxrq5bmHMlVuzvtwwywV?si=KGQWViY9QESfrZc21btFzA")
    gemini_key_input = st.text_input("Gemini API Key (Opcionális)", type="password")
    st.divider()
    
    if st.button("🚀 BULI INDÍTÁSA", type="primary"):
        if api_id and api_secret and pl_url:
            with st.spinner("Lemezek válogatása... 💿"):
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

# --- 8. FŐ JÁTÉKTÉR ---
if st.session_state.game_started:
    # Aktív játékos
    curr_p = st.session_state.players[st.session_state.turn_index % len(st.session_state.players)]
    
    # Eredményjelző
    st.markdown("<br>", unsafe_allow_html=True)
    cols = st.columns(len(st.session_state.players))
    for i, p in enumerate(st.session_state.players):
        style = "score-active" if p == curr_p else ""
        if p not in st.session_state.timelines: st.session_state.timelines[p] = []
        
        with cols[i]:
            st.markdown(f"""
            <div class='score-card {style}'>
                <p class='score-name'>{p}</p>
                <p class='score-num'>{len(st.session_state.timelines[p])}</p>
            </div>
            """, unsafe_allow_html=True)
            
    st.markdown("<hr style='border-top: 1px solid rgba(255,255,255,0.1); margin: 30px 0;'>", unsafe_allow_html=True)

    if st.session_state.game_phase == "GUESSING":
        st.markdown(f"<h1 style='text-align:center; font-size: 3em; margin-bottom: 20px;'>🎧 Te jössz, <span style='color:#00d4ff'>{curr_p}</span>!</h1>", unsafe_allow_html=True)
        song = st.session_state.current_mystery_song
        
        c1, c2, c3 = st.columns([1, 2, 1])
        with c2:
            st.markdown(f"""
            <div class='mystery-box'>
                <div class='mystery-artist'>{song['artist']}</div>
                <div class='mystery-title'>{song['title']}</div>
            </div>
            """, unsafe_allow_html=True)
            st.components.v1.iframe(f"https://open.spotify.com/embed/track/{song['spotify_id']}", height=80)
        
        st.markdown("<h3 style='text-align:center; margin-top:30px;'>👇 Hova illik ez a dal? Válassz helyet! 👇</h3>", unsafe_allow_html=True)
        
        timeline = st.session_state.timelines[curr_p]
        t_cols = st.columns(len(timeline)*2 + 1)
        
        for i in range(len(timeline)+1):
            with t_cols[i*2]:
                st.markdown("<div style='height: 100%; display: flex; align-items: center; justify-content: center;'>", unsafe_allow_html=True)
                if st.button("Itt?", key=f"b{i}", use_container_width=True):
                    prev_ok = (i==0) or (timeline[i-1]['year'] <= song['year'])
                    next_ok = (i==len(timeline)) or (timeline[i]['year'] >= song['year'])
                    st.session_state.success = (prev_ok and next_ok)
                    st.session_state.game_msg = f"🏆 TALÁLT! ({song['year']})" if st.session_state.success else f"❌ SAJNOS NEM... ({song['year']})"
                    if st.session_state.success: st.session_state.timelines[curr_p].insert(i, song)
                    st.session_state.game_phase = "REVEAL"
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)
                
            if i < len(timeline):
                with t_cols[i*2+1]:
                    card = timeline[i]
                    st.markdown(f"""
                    <div class='timeline-card'>
                        <div class='timeline-year'>{card['year']}</div>
                        <div style='font-size:0.9em;'>{card['artist']}</div>
                        <div style='font-weight:bold; font-size:1.1em;'>{card['title']}</div>
                    </div>
                    """, unsafe_allow_html=True)

    elif st.session_state.game_phase == "REVEAL":
        if st.session_state.success:
            st.balloons()
            st.markdown(f"<div style='text-align:center; padding: 20px; background: rgba(0,255,0,0.2); border-radius: 15px;'><h1>{st.session_state.game_msg}</h1></div>", unsafe_allow_html=True)
        else:
            st.snow() # Hóesés, ha rossz a válasz (szomorúbb hatás)
            st.markdown(f"<div style='text-align:center; padding: 20px; background: rgba(255,0,0,0.2); border-radius: 15px;'><h1>{st.session_state.game_msg}</h1></div>", unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1, 2, 1])
        with c2:
            st.button("KÖVETKEZŐ JÁTÉKOS ➡️", on_click=prepare_next_turn, type="primary")
        
        st.markdown("<br>", unsafe_allow_html=True)
        timeline = st.session_state.timelines[curr_p]
        d_cols = st.columns(len(timeline))
        for idx, card in enumerate(timeline):
            with d_cols[idx]:
                is_new = (card == st.session_state.current_mystery_song and st.session_state.success)
                style = "border: 4px solid #ffd166; transform: scale(1.1); box-shadow: 0 0 15px gold;" if is_new else ""
                st.markdown(f"""
                <div class='timeline-card' style='{style}'>
                    <div class='timeline-year'>{card['year']}</div>
                    <div>{card['artist']}</div>
                    <div><b>{card['title']}</b></div>
                </div>
                """, unsafe_allow_html=True)

    elif st.session_state.game_phase == "GAME_OVER":
        st.title("🎉 VÉGE A BULINAK! 🎉")
        winner = max(st.session_state.timelines, key=lambda k: len(st.session_state.timelines[k]))
        st.markdown(f"<h1 style='text-align:center; font-size:4em; color: gold;'>A GYŐZTES: {winner}</h1>", unsafe_allow_html=True)
        st.balloons()
        if st.button("Új Játék Indítása", use_container_width=True): 
            st.session_state.clear()
            st.rerun()
else:
    # Kezdőképernyő
    st.markdown("<h1 style='text-align:center; margin-top: 100px;'>📺 Hitster TV Party</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align:center; color: #aaa;'>Nyisd ki a bal oldali menüt (>), és add meg az adatokat a kezdéshez!</h3>", unsafe_allow_html=True)
