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

# --- 3. STÍLUS (RÁCSOS WRAPPING) 🎨 ---
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
        font-size: 2em; 
        font-weight: 900; 
        border-bottom: 1px solid rgba(255,255,255,0.3); 
        margin-bottom: 5px;
        text-shadow: 1px 1px 2px black; 
    }
    .ai-badge {
        font-size: 0.4em; vertical-align: super; color: #ffff00;
    }
    
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
</style>
""", unsafe_allow_html=True)

# --- 4. OKOS AI LOGIKA (DEBUGGOLVA) ---
def fix_card_with_ai(card, api_key):
    """Kijavítja a dátumot, és visszajelzést ad."""
    if not api_key: 
        return card
    
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-pro')
        
        # Szigorúbb prompt
        prompt = f"""
        What is the ORIGINAL release year of the song "{card['title']}" by "{card['artist']}"?
        Ignore Remastered, Best Of, or Compilation dates.
        Return ONLY the 4-digit year (e.g. 1984). Nothing else.
        """
        
        response = model.generate_content(prompt)
        text = response.text.strip()
        
        if text.isdigit():
            ai_year = int(text)
            original_year = card['year']
            
            # Csak akkor javítunk, ha logikus (1900-2025)
            if 1900 < ai_year <= 2025:
                # HA az AI régebbit mond, MINT a Spotify -> JAVÍTUNK
                # VAGY ha a Spotify nagyon új (pl 2020), de a dal egyértelműen régi
                if ai_year < original_year:
                    card['year'] = ai_year
                    card['fixed_by_ai'] = True # Megjelöljük, hogy az AI nyúlt hozzá
    except Exception as e:
        # Ha hiba van, kiírjuk a konzolra (így látni fogod, ha baj van a kulccsal)
        print(f"AI HIBA: {e}")
        pass
        
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

# --- 5. FŐ APP ---
if 'players' not in st.session_state: st.session_state.players = ["Jorgosz", "Lilla", "Józsi", "Dia"]

with st.sidebar:
    st.header("⚙️ DJ Pult")
    api_id = st.text_input("Spotify ID", type="password")
    api_secret = st.text_input("Spotify Secret", type="password")
    pl_url = st.text_input("Playlist Link", value="https://open.spotify.com/playlist/2WQxrq5bmHMlVuzvtwwywV?si=KGQWViY9QESfrZc21btFzA")
    
    st.markdown("---")
    st.markdown("### 🧠 AI Beállítás")
    gemini_key_input = st.text_input("Gemini API Key", type="password", help="Ha ezt megadod, az AI javítja a hibás évszámokat.")
    
    if gemini_key_input:
        st.success("AI Kulcs megadva! ✅")
    else:
        st.warning("Nincs AI kulcs! A dátumok pontatlanok lehetnek (Spotify). ⚠️")
    
    st.markdown("---")
    
    if st.button("🚀 BULI INDÍTÁSA", type="primary"):
        if api_id and api_secret and pl_url:
            with st.spinner("Lemezek válogatása..."):
                raw_deck = load_spotify_tracks(api_id, api_secret, pl_url)
                if raw_deck:
                    random.shuffle(raw_deck)
                    st.session_state.deck = raw_deck
                    st.session_state.gemini_key = gemini_key_input
                    st.session_state.timelines = {}
                    
                    # Kezdő lapok kiosztása + AI Javítás
                    for p in st.session_state.players:
                        if not st.session_state.deck: break
                        card = st.session_state.deck.pop()
                        if gemini_key_input: fix_card_with_ai(card, gemini_key_input)
                        st.session_state.timelines[p] = [card]
                    
                    # Első rejtélyes dal + AI Javítás
                    if st.session_state.deck:
                        first = st.session_state.deck.pop()
                        if gemini_key_input: fix_card_with_ai(first, gemini_key_input)
                        st.session_state.current_mystery_song = first
                        st.session_state.turn_index = 0
                        st.session_state.game_phase = "GUESSING"
                        st.session_state.game_started = True
                        st.rerun()

if st.session_state.game_started:
    curr_p = st.session_state.players[st.session_state.turn_index % len(st.session_state.players)]
    
    # --- HEADER ---
    st.markdown('<div class="mystery-sticky">', unsafe_allow_html=True)
    
    # Pontszámok
    c_scores = st.columns(len(st.session_state.players))
    for i, p in enumerate(st.session_state.players):
        active = "score-active" if p == curr_p else ""
        score = len(st.session_state.timelines.get(p, []))
        c_scores[i].markdown(f"<div class='score-box {active}'><b>{p}</b>: {score}</div>", unsafe_allow_html=True)

    # Info Doboz
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

    # --- JÁTÉKTÉR ---
    if st.session_state.game_phase == "GUESSING":
        c1, c2, c3 = st.columns([1,2,1])
        with c2:
             st.components.v1.iframe(f"https://open.spotify.com/embed/track/{st.session_state.current_mystery_song['spotify_id']}", height=80)
        
        st.markdown(f"<h3 style='text-align:center'>👇 {curr_p} idővonala 👇</h3>", unsafe_allow_html=True)
        
        timeline = st.session_state.timelines[curr_p]
        
        # RÁCSOS ELRENDEZÉS
        CARDS_PER_ROW = 4
        for row_start in range(0, len(timeline) + 1, CARDS_PER_ROW):
            row_end = min(row_start + CARDS_PER_ROW, len(timeline))
            
            # Sor összerakása: Gomb, Kártya, Gomb, Kártya...
            cols_in_row = []
            for i in range(row_start, row_end):
                cols_in_row.append("btn")
                cols_in_row.append("card")
            if row_end == len(timeline):
                cols_in_row.append("btn")
                
            if not cols_in_row: continue

            # Oszlopok létrehozása
            spec = [1 if x == "btn" else 4 for x in cols_in_row]
            row_cols = st.columns(spec)
            
            col_idx = 0
            for i in range(row_start, row_end + 1):
                # GOMB
                if i <= len(timeline):
                    if col_idx < len(row_cols):
                        with row_cols[col_idx]:
                            st.markdown("<br>", unsafe_allow_html=True)
                            if st.button("➕", key=f"btn_{i}", use_container_width=True):
                                song = st.session_state.current_mystery_song
                                prev_ok = (i==0) or (timeline[i-1]['year'] <= song['year'])
                                next_ok = (i==len(timeline)) or (timeline[i]['year'] >= song['year'])
                                st.session_state.success = (prev_ok and next_ok)
                                st.session_state.game_msg = f"TALÁLT! ({song['year']})" if st.session_state.success else f"NEM... ({song['year']})"
                                if st.session_state.success: st.session_state.timelines[curr_p].insert(i, song)
                                st.session_state.game_phase = "REVEAL"
                                st.rerun()
                        col_idx += 1
                
                # KÁRTYA
                if i < row_end:
                    if col_idx < len(row_cols):
                        with row_cols[col_idx]:
                            card = timeline[i]
                            # Csillag jelzés, ha AI javította
                            ai_badge = "<span class='ai-badge'>✨</span>" if card.get('fixed_by_ai') else ""
                            st.markdown(f"""
                            <div class='timeline-card'>
                                <div class='card-year'>{card['year']}{ai_badge}</div>
                                <div class='card-title'>{card['title']}</div>
                                <div class='card-artist'>{card['artist']}</div>
                            </div>
                            """, unsafe_allow_html=True)
                        col_idx += 1
            st.markdown("<br>", unsafe_allow_html=True)

    elif st.session_state.game_phase == "REVEAL":
        if st.session_state.success: st.balloons()
        
        def next_turn():
            st.session_state.turn_index += 1
            if st.session_state.deck:
                next_song = st.session_state.deck.pop()
                # AI Elemzés (Következő körhöz)
                if st.session_state.get('gemini_key'):
                    fix_card_with_ai(next_song, st.session_state.gemini_key)
                st.session_state.current_mystery_song = next_song
                st.session_state.game_phase = "GUESSING"
            else:
                st.session_state.game_phase = "GAME_OVER"

        c1, c2, c3 = st.columns([1,1,1])
        c2.button("KÖVETKEZŐ ➡️", on_click=next_turn, type="primary", use_container_width=True)
        
        # Reveal nézet (csak kártyák)
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
    st.info("Nyisd ki a menüt a kezdéshez! (> gomb bal fent)")
