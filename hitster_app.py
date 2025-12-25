import streamlit as st
import random
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import google.generativeai as genai
import time

# --- 1. KONFIGURÁCIÓ ---
st.set_page_config(page_title="Hitster TV Party", page_icon="📺", layout="wide")

st.markdown("""
<style>
    .stApp { background: linear-gradient(135deg, #1e1e2e 0%, #2d2b55 100%); color: white; }
    .score-card { background-color: rgba(255, 255, 255, 0.1); border-radius: 15px; padding: 15px; text-align: center; border: 2px solid transparent; transition: transform 0.2s; }
    .score-active { border: 3px solid #00d4ff; background-color: rgba(0, 212, 255, 0.15); transform: scale(1.05); box-shadow: 0 0 15px #00d4ff; }
    .score-num { font-size: 2.5em; font-weight: bold; color: #ffcc00; margin: 0; }
    .score-name { font-size: 1.1em; font-weight: 600; margin: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .timeline-card { background: linear-gradient(180deg, #1DB954 0%, #158a3e 100%); color: white; padding: 15px; border-radius: 12px; text-align: center; margin: 5px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
    .timeline-year { font-size: 1.8em; font-weight: 900; border-bottom: 1px solid rgba(255,255,255,0.3); margin-bottom: 5px; padding-bottom: 5px; }
    .mystery-box { background-color: #333; border: 3px dashed #ff4b4b; border-radius: 15px; padding: 20px; text-align: center; margin: 20px 0; }
    div.stButton > button { background-color: #ff4b4b; color: white; font-size: 20px !important; padding: 10px 24px; border-radius: 30px; border: none; box-shadow: 0 4px 0 #b33232; transition: all 0.1s; }
    div.stButton > button:active { box-shadow: none; transform: translateY(4px); }
    div[data-testid="column"] button { background-color: #444; box-shadow: none; font-size: 16px !important; padding: 5px; }
    div[data-testid="column"] button:hover { background-color: #00d4ff; }
</style>
""", unsafe_allow_html=True)

# --- 2. GEMINI AI LOGIKA ---
def get_year_from_gemini(api_key, artist, title, current_year):
    if not api_key: return current_year
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-pro')
        prompt = f"""
        What is the ORIGINAL release year of the song "{title}" by "{artist}"?
        Ignore remasters, compilations. Return ONLY the year as a 4-digit number.
        """
        response = model.generate_content(prompt)
        text = response.text.strip()
        if text.isdigit():
            ai_year = int(text)
            if 1900 < ai_year <= 2025:
                if ai_year < current_year:
                    return ai_year
        return current_year
    except:
        return current_year

# --- 3. ADATBETÖLTÉS ---
def load_and_process_playlist(spotify_id, spotify_secret, playlist_url, gemini_key):
    try:
        auth_manager = SpotifyClientCredentials(client_id=spotify_id, client_secret=spotify_secret)
        sp = spotipy.Spotify(auth_manager=auth_manager)
        
        # URL tisztítása
        if "?" in playlist_url:
            clean_url = playlist_url.split("?")[0]
        else:
            clean_url = playlist_url
        resource_id = clean_url.split("/")[-1]
        
        tracks_data = []

        # ALBUM BETÖLTÉS
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
        
        # PLAYLIST BETÖLTÉS
        elif "playlist" in clean_url:
            results = sp.playlist_items(resource_id)
            items = results['items']
            while results['next']:
                results = sp.next(results)
                items.extend(results['items'])
            for item in items:
                track = item['track']
                # Csak akkor adjuk hozzá, ha van érvényes dátum
                if track and track['album'] and track['album']['release_date']:
                    year_str = track['album']['release_date'].split('-')[0]
                    if year_str.isdigit():
                        tracks_data.append({"artist": track['artists'][0]['name'], "title": track['name'], "year": int(year_str), "spotify_id": track['id']})
        
        else:
            st.error("Hiba: A link nem Album és nem Playlist!")
            return []

        # Feldolgozás
        final_db = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        total = len(tracks_data)
        
        for i, song in enumerate(tracks_data):
            if gemini_key:
                status_text.markdown(f"**AI Elemzés:** {song['artist']} - {song['title']}")
                song['year'] = get_year_from_gemini(gemini_key, song['artist'], song['title'], song['year'])
                time.sleep(0.5) 
            else:
                status_text.text(f"Betöltés: {song['artist']}")
            
            final_db.append(song)
            progress_bar.progress((i + 1) / total)
            
        status_text.empty()
        progress_bar.empty()
        return final_db
    except Exception as e:
        st.error(f"Hiba: {e}")
        return []

# --- 4. APP LOGIKA ---
if 'players' not in st.session_state: st.session_state.players = ["Jorgosz", "Lilla", "Józsi", "Dia"]
if 'game_started' not in st.session_state: st.session_state.game_started = False

with st.sidebar:
    st.header("⚙️ Beállítások")
    api_id = st.text_input("Spotify Client ID", type="password")
    api_secret = st.text_input("Spotify Client Secret", type="password")
    pl_url = st.text_input("Playlist Link", value="https://open.spotify.com/playlist/2WQxrq5bmHMlVuzvtwwywV?si=KGQWViY9QESfrZc21btFzA")
    gemini_key_input = st.text_input("Gemini API Key (Opcionális)", type="password")
    st.divider()
    if st.button("🚀 INDÍTÁS", type="primary"):
        if api_id and api_secret and pl_url:
            deck = load_and_process_playlist(api_id, api_secret, pl_url, gemini_key_input)
            if deck:
                random.shuffle(deck)
                st.session_state.deck = deck
                st.session_state.timelines = {p: [st.session_state.deck.pop()] for p in st.session_state.players}
                st.session_state.turn_index = 0
                st.session_state.current_mystery_song = st.session_state.deck.pop()
                st.session_state.game_phase = "GUESSING"
                st.session_state.game_started = True
                st.rerun()

# --- JÁTÉKTÉR ---
if st.session_state.game_started:
    curr_p = st.session_state.players[st.session_state.turn_index % len(st.session_state.players)]
    
    cols = st.columns(len(st.session_state.players))
    for i, p in enumerate(st.session_state.players):
        style = "score-active" if p == curr_p else ""
        if p not in st.session_state.timelines: st.session_state.timelines[p] = []
        cols[i].markdown(f"<div class='score-card {style}'><p class='score-name'>{p}</p><p class='score-num'>{len(st.session_state.timelines[p])}</p></div>", unsafe_allow_html=True)
    st.divider()

    if st.session_state.game_phase == "GUESSING":
        st.markdown(f"<h2 style='text-align:center'>Te jössz, {curr_p}!</h2>", unsafe_allow_html=True)
        song = st.session_state.current_mystery_song
        c1, c2, c3 = st.columns([1,2,1])
        c2.markdown(f"<div class='mystery-box'><h3>{song['artist']}</h3><h2>{song['title']}</h2></div>", unsafe_allow_html=True)
        c2.components.v1.iframe(f"https://open.spotify.com/embed/track/{song['spotify_id']}", height=80)
        
        timeline = st.session_state.timelines[curr_p]
        t_cols = st.columns(len(timeline)*2 + 1)
        for i in range(len(timeline)+1):
            if t_cols[i*2].button("IDE", key=f"b{i}", use_container_width=True):
                prev_ok = (i==0) or (timeline[i-1]['year'] <= song['year'])
                next_ok = (i==len(timeline)) or (timeline[i]['year'] >= song['year'])
                st.session_state.success = (prev_ok and next_ok)
                st.session_state.game_msg = f"Nyert! ({song['year']})" if st.session_state.success else f"Nem nyert! ({song['year']})"
                if st.session_state.success: st.session_state.timelines[curr_p].insert(i, song)
                st.session_state.game_phase = "REVEAL"
                st.rerun()
            if i < len(timeline):
                t_cols[i*2+1].markdown(f"<div class='timeline-card'><div class='timeline-year'>{timeline[i]['year']}</div>{timeline[i]['title']}</div>", unsafe_allow_html=True)

    elif st.session_state.game_phase == "REVEAL":
        if st.session_state.success: st.balloons(); st.success(st.session_state.game_msg)
        else: st.error(st.session_state.game_msg)
        if st.button("Tovább"):
            st.session_state.turn_index += 1
            if st.session_state.deck:
                st.session_state.current_mystery_song = st.session_state.deck.pop()
                st.session_state.game_phase = "GUESSING"
            else: st.session_state.game_phase = "GAME_OVER"
            st.rerun()

    elif st.session_state.game_phase == "GAME_OVER":
        st.title("Vége!")
        if st.button("Újra"): st.session_state.clear(); st.rerun()
else:
    st.title("📺 Hitster Party")
    st.info("Add meg az adatokat balra!")
