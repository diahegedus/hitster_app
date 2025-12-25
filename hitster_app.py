import streamlit as st
import random
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import musicbrainzngs
import google.generativeai as genai
import time

# --- 1. KONFIGURÁCIÓ & STÍLUS ---
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
    .timeline-info { font-size: 0.9em; line-height: 1.2; }
    .mystery-box { background-color: #333; border: 3px dashed #ff4b4b; border-radius: 15px; padding: 20px; text-align: center; margin: 20px 0; }
    div.stButton > button { background-color: #ff4b4b; color: white; font-size: 20px !important; padding: 10px 24px; border-radius: 30px; border: none; box-shadow: 0 4px 0 #b33232; transition: all 0.1s; }
    div.stButton > button:active { box-shadow: none; transform: translateY(4px); }
    div[data-testid="column"] button { background-color: #444; box-shadow: none; font-size: 16px !important; padding: 5px; }
    div[data-testid="column"] button:hover { background-color: #00d4ff; }
</style>
""", unsafe_allow_html=True)

# --- 2. MUSICBRAINZ KERESŐ ---
def get_original_year_mb(artist, title, spotify_year):
    """MusicBrainz keresés."""
    musicbrainzngs.set_useragent("HitsterPartyApp", "1.0", "contact@example.com")
    try:
        result = musicbrainzngs.search_recordings(artist=artist, recording=title, limit=5)
        candidates = []
        if 'recording-list' in result:
            for recording in result['recording-list']:
                if 'release-list' in recording:
                    for release in recording['release-list']:
                        if 'date' in release:
                            date_str = release['date']
                            try:
                                year = int(date_str.split('-')[0])
                                if 1900 < year <= 2025:
                                    candidates.append(year)
                            except: continue
        
        if candidates:
            mb_year = min(candidates)
            if mb_year < spotify_year:
                return mb_year, "MusicBrainz"
            
        return spotify_year, "Spotify"
    except:
        return spotify_year, "Spotify"

# --- 3. GEMINI KERESŐ (AI) ---
def get_year_from_gemini(api_key, artist, title, current_year):
    """Gemini AI megkérdezése."""
    # Ha nincs kulcs megadva, azonnal visszatérünk az eredeti évvel
    if not api_key: 
        return current_year, "Nincs AI Kulcs"
    
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-pro')
        
        prompt = f"""
        What is the ORIGINAL release year of the song "{title}" by "{artist}"?
        Ignore remasters, compilations, or re-releases. I need the year when the song was FIRST released to the public.
        Return ONLY the year as a 4-digit number (e.g. 1984). Do not write any other text.
        """
        
        response = model.generate_content(prompt)
        text = response.text.strip()
        
        if text.isdigit():
            ai_year = int(text)
            if 1900 < ai_year <= 2025:
                if ai_year < current_year:
                    return ai_year, "Gemini AI"
                else:
                    return current_year, "Gemini (nem volt régebbi)"
        
        return current_year, "Gemini (hiba)"
    except Exception as e:
        print(f"Gemini hiba: {e}")
        return current_year, "Gemini Hiba"

# --- 4. ADATBETÖLTÉS ÉS FELDOLGOZÁS ---
# Itt adjuk át a gemini_key-t paraméterként
def load_and_process_playlist(spotify_id, spotify_secret, playlist_url, gemini_key):
    try:
        # 1. Spotify letöltés
        auth_manager = SpotifyClientCredentials(client_id=spotify_id, client_secret=spotify_secret)
        sp = spotipy.Spotify(auth_manager=auth_manager)
        
        clean_id = playlist_url.split('/')[-1].split('?')[0]
        tracks_data = []
        
        # Album vagy Playlist kezelése
        if "album" in playlist_url:
            album_info = sp.album(clean_id)
            album_year = int(album_info['release_date'].split('-')[0])
            results = sp.album_tracks(clean_id)
            items = results['items']
            while results['next']:
                results = sp.next(results)
                items.extend(results['items'])
            for track in items:
                tracks_data.append({"artist": track['artists'][0]['name'], "title": track['name'], "year": album_year, "spotify_id": track['id']})
        else:
            results = sp.playlist_items(clean_id)
            items = results['items']
            while results['next']:
                results = sp.next(results)
                items.extend(results['items'])
            for item in items:
                track = item['track']
                if track and track['album']['release_date']:
                    year_str = track['album']['release_date'].split('-')[0]
                    if year_str.isdigit():
                        tracks_data.append({"artist": track['artists'][0]['name'], "title": track['name'], "year": int(year_str), "spotify_id": track['id']})

        # 2. Javítás (MusicBrainz + Gemini)
        final_db = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        total = len(tracks_data)
        
        for i, song in enumerate(tracks_data):
            artist = song['artist']
            title = song['title']
            year = song['year']
            
            status_text.markdown(f"**Feldolgozás:** {artist} - {title} ({year})")
            
            # A) Megkérdezzük a MusicBrainz-t
            mb_year, source = get_original_year_mb(artist, title, year)
            
            # B) Ha a MusicBrainz nem talált jobbat (maradt a Spotify év), ÉS van Gemini kulcs -> Kérdezzük a Geminit
            if source == "Spotify" and gemini_key:
                # Csak akkor hívjuk meg, ha a felhasználó megadta a kulcsot
                gemini_year, g_source = get_year_from_gemini(gemini_key, artist, title, year)
                if gemini_year < year:
                    year = gemini_year
                time.sleep(0.5) # Kis pihi az API kímélésére
            else:
                year = mb_year
            
            song['year'] = year
            final_db.append(song)
            progress_bar.progress((i + 1) / total)
            
        status_text.empty()
        progress_bar.empty()
        return final_db

    except Exception as e:
        st.error(f"Kritikus hiba: {e}")
        return []

# --- 5. JÁTÉK ÁLLAPOT ---
if 'players' not in st.session_state:
    st.session_state.players = ["Jorgosz", "Lilla", "Józsi", "Dia"]
if 'game_started' not in st.session_state:
    st.session_state.game_started = False

# --- 6. OLDALSÁV (BEÁLLÍTÁSOK) ---
with st.sidebar:
    st.header("⚙️ DJ Pult")
    
    st.subheader("1. Spotify Adatok (Kötelező)")
    api_id = st.text_input("Spotify Client ID", type="password")
    api_secret = st.text_input("Spotify Client Secret", type="password")
    pl_url = st.text_input("Playlist/Album Link", value="https://open.spotify.com/playlist/2WQxrq5bmHMlVuzvtwwywV?si=KGQWViY9QESfrZc21btFzA")
    
    st.subheader("2. AI Javítás (Opcionális)")
    st.caption("Ha beírod a kulcsot, a Gemini kijavítja a hibás évszámokat.")
    # ITT AZ ÚJ MEZŐ:
    gemini_key_input = st.text_input("Google Gemini API Key", type="password")
    
    st.divider()
    
    if st.button("🚀 BULI INDÍTÁSA", type="primary"):
        if api_id and api_secret and pl_url:
            with st.spinner("Zenék letöltése és AI elemzése... (Ez eltarthat egy percig)"):
                # Átadjuk a beírt kulcsot a függvénynek
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
        else:
            st.error("A Spotify adatok kötelezőek!")

    st.divider()
    st.write("Játékosok:")
    for i in range(len(st.session_state.players)):
        st.session_state.players[i] = st.text_input(f"Játékos {i+1}", st.session_state.players[i])

# --- 7. FŐ JÁTÉKTÉR ---
if not st.session_state.game_started:
    st.title("📺 TV HITSTER PARTY + AI 🧠")
    st.markdown("### 👋 Szia! A legokosabb zenei kvíz.")
    st.info("Töltsd ki az adatokat bal oldalt. Ha megadod a Gemini kulcsot, a játék felismeri a Remastered dalok eredeti évét is!")
    st.write(f"Játékosok: {', '.join(st.session_state.players)}")

else:
    # Változók
    current_player_idx = st.session_state.turn_index % len(st.session_state.players)
    current_player_name = st.session_state.players[current_player_idx]
    
    # Eredményjelző
    st.markdown("<br>", unsafe_allow_html=True)
    score_cols = st.columns(len(st.session_state.players))
    for idx, player in enumerate(st.session_state.players):
        if player not in st.session_state.timelines: st.session_state.timelines[player] = []
        score = len(st.session_state.timelines[player])
        active_class = "score-active" if (idx == current_player_idx) else ""
        with score_cols[idx]:
            st.markdown(f"""
            <div class="score-card {active_class}">
                <p class="score-name">{player}</p>
                <p class="score-num">{score}</p>
            </div>
            """, unsafe_allow_html=True)

    st.divider()

    # Logika
    def handle_guess(insert_index):
        p_name = st.session_state.players[st.session_state.turn_index % len(st.session_state.players)]
        timeline = st.session_state.timelines[p_name]
        song = st.session_state.current_mystery_song
        
        prev_ok = (insert_index == 0) or (timeline[insert_index-1]['year'] <= song['year'])
        next_ok = (insert_index == len(timeline)) or (timeline[insert_index]['year'] >= song['year'])
        
        if prev_ok and next_ok:
            st.session_state.timelines[p_name].insert(insert_index, song)
            st.session_state.game_msg = f"IGEN! ELTALÁLTAD! 🎉 ({song['year']})"
            st.session_state.success = True
        else:
            st.session_state.game_msg = f"SAJNOS NEM! 😭 Ez a dal {song['year']}-es volt."
            st.session_state.success = False
        st.session_state.game_phase = "REVEAL"

    def next_turn():
        st.session_state.turn_index += 1
        if st.session_state.deck:
            st.session_state.current_mystery_song = st.session_state.deck.pop()
            st.session_state.game_phase = "GUESSING"
        else:
            st.session_state.game_phase = "GAME_OVER"
        st.rerun()

    # Megjelenítés
    if st.session_state.game_phase == "GUESSING":
        st.markdown(f"<h2 style='text-align: center;'>🎧 {current_player_name}, te jössz!</h2>", unsafe_allow_html=True)
        mys_song = st.session_state.current_mystery_song
        c1, c2, c3 = st.columns([1, 2, 1])
        with c2:
            st.markdown(f"<div class='mystery-box'><h3>{mys_song['artist']}</h3><h2 style='color:#ff4b4b;'>{mys_song['title']}</h2></div>", unsafe_allow_html=True)
            st.components.v1.iframe(f"https://open.spotify.com/embed/track/{mys_song['spotify_id']}", height=80)

        st.markdown("### 👇 Válassz helyet:")
        timeline = st.session_state.timelines[current_player_name]
        t_cols = st.columns(len(timeline) * 2 + 1)
        for i in range(len(timeline) + 1):
            with t_cols[i*2]:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("IDE", key=f"btn_{i}", use_container_width=True):
                    handle_guess(i)
                    st.rerun()
            if i < len(timeline):
                card = timeline[i]
                with t_cols[i*2+1]:
                    st.markdown(f"<div class='timeline-card'><div class='timeline-year'>{card['year']}</div><div>{card['artist']}<br><i>{card['title']}</i></div></div>", unsafe_allow_html=True)

    elif st.session_state.game_phase == "REVEAL":
        if st.session_state.success:
            st.balloons()
            st.success(st.session_state.game_msg)
        else:
            st.error(st.session_state.game_msg)
        
        timeline = st.session_state.timelines[current_player_name]
        d_cols = st.columns(len(timeline))
        for idx, card in enumerate(timeline):
            with d_cols[idx]:
                style = "border: 4px solid #ffcc00; transform: scale(1.1);" if (card == st.session_state.current_mystery_song and st.session_state.success) else ""
                st.markdown(f"<div class='timeline-card' style='{style}'><div class='timeline-year'>{card['year']}</div><div>{card['artist']}<br><i>{card['title']}</i></div></div>", unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1,2,1])
        with c2: st.button("KÖVETKEZŐ ➡️", on_click=next_turn, use_container_width=True)

    elif st.session_state.game_phase == "GAME_OVER":
        st.title("🏆 VÉGE!")
        winner = max(st.session_state.timelines, key=lambda k: len(st.session_state.timelines[k]))
        st.markdown(f"<h1 style='text-align:center; color:gold;'>GYŐZTES: {winner}</h1>", unsafe_allow_html=True)
        if st.button("ÚJRA", use_container_width=True): st.session_state.clear(); st.rerun()
