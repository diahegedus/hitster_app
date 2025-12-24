import streamlit as st
import random
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# --- 1. Konfiguráció ---
st.set_page_config(page_title="Hitster Party", page_icon="🎵", layout="wide")

st.markdown("""
<style>
    .timeline-card {
        background-color: #1DB954;
        color: white;
        padding: 10px;
        border-radius: 8px;
        text-align: center;
        margin: 5px;
        font-weight: bold;
        font-size: 0.9em;
    }
    .mystery-card {
        border: 2px dashed #333;
        padding: 20px;
        text-align: center;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

# --- 2. Spotify Betöltő Funkció ---
def load_spotify_playlist(client_id, client_secret, playlist_url):
    try:
        auth_manager = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
        sp = spotipy.Spotify(auth_manager=auth_manager)
        
        results = sp.playlist_items(playlist_url)
        tracks = results['items']
        while results['next']:
            results = sp.next(results)
            tracks.extend(results['items'])
            
        music_db = []
        for item in tracks:
            track = item['track']
            if not track: continue
            
            # Évszám kinyerése
            release_date = track['album']['release_date']
            year = release_date.split('-')[0]
            
            if year and year.isdigit():
                music_db.append({
                    "artist": track['artists'][0]['name'],
                    "title": track['name'],
                    "year": int(year),
                    "spotify_id": track['id']
                })
        return music_db
    except Exception as e:
        st.error(f"Hiba a Spotify betöltésnél: {e}")
        return []

# --- 3. Játékállapot (State) ---

if 'players' not in st.session_state:
    st.session_state.players = ["Jorgosz", "Lilla", "Józsi"]

if 'game_started' not in st.session_state:
    st.session_state.game_started = False

# --- 4. OLDALSÁV: Beállítások és Belépés ---
with st.sidebar:
    st.header("⚙️ Beállítások")
    
    st.write("Add meg a Spotify adataidat a játék indításához. (Nem mentjük el őket!)")
    
    # type="password" elrejti a karaktereket csillagokkal
    api_id = st.text_input("Client ID", type="password")
    api_secret = st.text_input("Client Secret", type="password")
    pl_url = st.text_input("Playlist Link", value="https://open.spotify.com/playlist/2WQxrq5bmHMlVuzvtwwywV?si=KGQWViY9QESfrZc21btFzA")
    
    start_btn = st.button("🚀 Játék Indítása")
    
    st.divider()
    if st.button("Játékosok Reset"):
        st.session_state.clear()
        st.rerun()

# --- 5. Logika: Indítás ---
if start_btn:
    if api_id and api_secret and pl_url:
        with st.spinner("Dalok letöltése..."):
            deck = load_spotify_playlist(api_id, api_secret, pl_url)
            if deck:
                # Siker! Inicializáljuk a játékot
                random.shuffle(deck)
                st.session_state.deck = deck
                
                # Idővonalak kiosztása
                st.session_state.timelines = {
                    p: [st.session_state.deck.pop()] 
                    for p in st.session_state.players
                }
                
                st.session_state.turn_index = 0
                st.session_state.current_mystery_song = st.session_state.deck.pop()
                st.session_state.game_phase = "GUESSING"
                st.session_state.game_started = True
                st.rerun()
    else:
        st.warning("Kérlek tölts ki minden mezőt!")

# --- 6. JÁTÉKTÉR ---

if not st.session_state.game_started:
    st.title("🎵 Hitster Party")
    st.info("👈 Kérlek add meg a Spotify adataidat az oldalsávon a kezdéshez!")
    st.markdown("### Hogyan szerezz adatokat?")
    st.markdown("1. Menj a [Spotify Developers](https://developer.spotify.com/dashboard) oldalra.")
    st.markdown("2. Hozz létre egy appot, és másold ki a Client ID / Secret kódokat.")
    st.markdown("3. Illessz be egy nyilvános lejátszási lista linket.")

else:
    # --- ITT FUT A JÁTÉK ---
    
    # Függvények a játékhoz
    def handle_guess(insert_index):
        current_player = st.session_state.players[st.session_state.turn_index]
        timeline = st.session_state.timelines[current_player]
        song = st.session_state.current_mystery_song
        
        # Ellenőrzés
        prev_ok = (insert_index == 0) or (timeline[insert_index-1]['year'] <= song['year'])
        next_ok = (insert_index == len(timeline)) or (timeline[insert_index]['year'] >= song['year'])
        
        is_correct = prev_ok and next_ok
        
        if is_correct:
            st.session_state.timelines[current_player].insert(insert_index, song)
            st.session_state.game_msg = f"✅ Helyes! ({song['year']})"
            st.toast("Eltaláltad!", icon="🎉")
        else:
            st.session_state.game_msg = f"❌ Nem nyert! Ez a dal {song['year']}-es volt."
            st.toast("Sajnos nem...", icon="😢")
            
        st.session_state.game_phase = "REVEAL"

    def next_turn():
        st.session_state.turn_index = (st.session_state.turn_index + 1) % len(st.session_state.players)
        if st.session_state.deck:
            st.session_state.current_mystery_song = st.session_state.deck.pop()
            st.session_state.game_phase = "GUESSING"
        else:
            st.session_state.game_phase = "GAME_OVER"
        st.rerun()

    # UI Megjelenítés
    player_name = st.session_state.players[st.session_state.turn_index]
    st.title(f"{player_name} köre 🎲")
    
    mys_song = st.session_state.current_mystery_song
    
    # Zenelejátszó
    if mys_song:
        st.components.v1.iframe(f"https://open.spotify.com/embed/track/{mys_song['spotify_id']}?utm_source=generator", height=80)
        st.markdown(f"<div class='mystery-card'><h3>{mys_song['artist']} - {mys_song['title']}</h3></div>", unsafe_allow_html=True)

    # Idővonal
    timeline = st.session_state.timelines[player_name]
    
    if st.session_state.game_phase == "GUESSING":
        st.write("Hova illeszted be?")
        cols = st.columns(len(timeline) * 2 + 1)
        for i in range(len(timeline) + 1):
            with cols[i*2]:
                if st.button("👇", key=f"b{i}"):
                    handle_guess(i)
                    st.rerun()
            if i < len(timeline):
                card = timeline[i]
                with cols[i*2+1]:
                    st.markdown(f"<div class='timeline-card'>{card['year']}<br>{card['artist']}<br>{card['title']}</div>", unsafe_allow_html=True)
                    
    elif st.session_state.game_phase == "REVEAL":
        st.subheader(st.session_state.game_msg)
        
        # Megmutatjuk a frissített idővonalat
        d_cols = st.columns(len(timeline))
        for idx, card in enumerate(timeline):
            with d_cols[idx]:
                border = "border: 3px solid gold;" if card == mys_song and "Helyes" in st.session_state.game_msg else ""
                st.markdown(f"<div class='timeline-card' style='{border}'>{card['year']}<br>{card['artist']}<br>{card['title']}</div>", unsafe_allow_html=True)
                
        st.button("Következő játékos ➡️", on_click=next_turn, type="primary")

    elif st.session_state.game_phase == "GAME_OVER":
        st.balloons()
        st.success("Elfogyott a pakli! Nézzük az eredményeket:")
        for p in st.session_state.players:
            count = len(st.session_state.timelines[p])
            st.write(f"**{p}**: {count} kártya")
