########################################################################################
"""############################        mira.py         ##############################"""
"""##############     MIRA = Multi-Intent Recognition Assistant     #################"""
########################################################################################

########################################################################################
"""############################     System imports     ##############################"""
########################################################################################
import os
import json
import webview
import subprocess
import io
import base64
import sqlite3
import ssl
import threading
from PIL import Image
from PyQt6 import QtGui, QtWidgets
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineCertificateError
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from threading import Thread
from pathlib import Path
from datetime import datetime

########################################################################################
"""############################    Services imports    ##############################"""
########################################################################################
"""###### System config ######"""
from services.passkeys import ALLOWED_KEYS, SECRET_KEY
from services.user_managment import AppState, HasAttachment, FileSupport, FilePool, get_chat_state
from services.config import BASE_PATH, get_local_ip, init_qwen_vl, init_qwen, ACTIVE_DEVICES, enforce_resource_safety
from services.mkcert import check_mkcert
from services.media import discover_playlists
from services.smart_plugs import load_plugs_from_db
"""###### DB ######"""
from services.db_access import init_db, connect
from services.db_get import get_settings, GetDB, food_search
from services.db_persist import save_settings, save_nutrition_user_values, persist_nutri_item, persist_nutrition_intake, \
                                update_today_consumed_items, init_users

"""###### Voice-in ######"""
from services.stt_distil_whisper import get_distil_whisper_model, transcribe_audio as transcribe_distil_whisper
from services.stt_vosk import get_vosk_model, transcribe_audio as transcribe_vosk
"""###### Intent + Command ######"""
from services.llm_intent import ask_intent, ask_wikipedia, ask_web
from services.command_library import command_lookup
"""###### Chat ######"""
from services.llm_chat import ChatSession, ask_weather, ChatContext
# Cast to text
from services.url_to_txt import save_url_text
from services.file_to_txt import file_to_txt
# VL
from services.llm_vl import image_inference
"""###### Voice-out ######"""
from services.tts_xtts_v2 import voice_out, init_tts_service, clean_voice_chunks, get_xtts_v2_model

"""####### Barcode/Nutrition ######"""
from services.llm_vl import scan_barcode
from services.api_openfoodfacts import lookup_barcode

########################################################################################
"""##########################         System           ##############################"""
########################################################################################
mira = Flask(__name__, static_folder="static", template_folder="templates")
socketio = SocketIO(mira)
CORS(mira, resources={
    r"/upload_audio": {"origins": "*"},
    r"/receive": {"origins": "*"},
    r"/login": {"origins": "*"}
})
mira.secret_key = SECRET_KEY

def init_all():
    print("[System] Starting services.")
    # Initial init
    init_db()
    FilePool.ensure_directories()
    init_users()
    check_mkcert()
    enforce_resource_safety()

    # Utility
    load_plugs_from_db()
    discover_playlists()

    # Init text LLM
    init_qwen()  # Qwen3

    # Init TTS
    get_xtts_v2_model()

    # Init STT
    stt_engine = GetDB.get_stt()
    stt_mode = GetDB.get_stt_mode()
    if stt_engine == "vosk":
        get_vosk_model()  # Vosk is always mode=cpu
    elif stt_engine == "distil-whisper":
        get_distil_whisper_model(stt_mode)

    # Init VL LLM
    init_qwen_vl()  # Qwen3 VL

    # Initialize TTS service with socketio
    init_tts_service(socketio)

    print("[System] All services initialized.")

# For the non-dockerized version
class CustomWebEnginePage(QWebEnginePage):
    @staticmethod
    def certificate_error(error: QWebEngineCertificateError) -> bool:
        print(f"[SSL] Certificate error for {error.url().toString()}")
        if error.isOverridable():
            error.acceptCertificate()
            return True
        return False

# Flask subprocess
# We need ssl or the browser will not allow mic access from local network
def run_https_flask():
    # Suppress /attachment_status logs
    import logging
    class AttachmentStatusFilter(logging.Filter):
        def filter(self, record):
            return "/attachment_status" not in record.getMessage()

    logging.getLogger('werkzeug').addFilter(AttachmentStatusFilter())

    cert = BASE_PATH / "mira_cert.pem"
    key = BASE_PATH / "mira_key.pem"

    # Create proper SSL context for gevent
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain(certfile=str(cert), keyfile=str(key))

    socketio.run(mira, debug=False, use_reloader=False, host='0.0.0.0', port=5001, ssl_context=ssl_context, allow_unsafe_werkzeug=True)

# local network for browser addon and for the cloudflare tunnel
# tunnel explodes if it has to deal with https from this end
# sudo systemctl daemon-reload
# sudo systemctl restart cloudflared-mira-tunnel
# journalctl -u cloudflared-mira-tunnel -f
def run_http_flask():
    # we need http for the Chromium extension and for the cloudflare tunnel
    socketio.run(mira, debug=False, use_reloader=False, host='0.0.0.0', port=5002, allow_unsafe_werkzeug=True)

# this is the window that opens on the host for people who have a non-dockerized install
# untested for wayland
def set_qt_identity():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])  # fallback if not yet created
    app.setApplicationName("Mira")
    app.setWindowIcon(QtGui.QIcon("icon.png"))

########################################################################################
"""############################        Health          ##############################"""
########################################################################################
# TODO: implement

########################################################################################
"""##########################     User Management       #############################"""
########################################################################################
# check user authentication
@mira.before_request
def check_access():
    # List of routes that don't require authentication
    public_routes = [
        "/static/",
        "/login",
        "/receive",
        "/favicon.ico",
    ]

    # Check if this is a public route
    is_public = any(request.path.startswith(route) for route in public_routes)

    # Special case for /receive from localhost
    if request.path == "/receive" and request.remote_addr in ["127.0.0.1", "::1"]:
        is_public = True

    if is_public:
        return None

    # Check if user is authenticated
    if not session.get('authenticated'):
        print(f"[BeforeRequest] Refused unauthorized access to {request.path} from {request.remote_addr}")

        # Store the current path to redirect after login
        if request.path not in ['/login', '/']:
            session['next_url'] = request.path

        # Use external URL for proper redirects behind proxy
        return redirect(url_for('login', _external=True))

    # Validate user ID exists in session
    if not session.get('user_id'):
        print(f"[BeforeRequest] Session missing user_id for path {request.path}, forcing new login")
        session.clear()
        return redirect(url_for('login', _external=True), code=302)
    print(f"[BeforeRequest] Allowed User {session.get('user_id')}")
    return None

# login page and form handling
@mira.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        # Show login form
        print(f"[Login] Showing login page.")
        return render_template('login.html')

    # Debug logging for POST requests
    print(f"[Login] POST request received to /login")
    #print(f"[Login] Form data: {request.form}")
    #print(f"[Login] Request headers: {dict(request.headers)}")

    # Handle form submission (POST)
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()

    # Check credentials against allowed users
    print(f"[Login] Checking credentials.")
    for user in ALLOWED_KEYS:
        if user['user_name'] == username and user['password'] == password:
            # Successful authentication: get user ID from database
            try:
                with connect(readonly=True) as conn:
                    conn.row_factory = sqlite3.Row
                    user_row = conn.execute("""
                                            SELECT id
                                            FROM user_info
                                            WHERE user_name = ?
                                            """, (username,)).fetchone()

                    if not user_row:
                        flash('User not found in database', 'error')
                        print(f"[Login] User not in DB: System error.")
                        return render_template('login.html', error='System error')

                    # Clear existing session first to avoid stale data
                    session.clear()

                    # Set session data
                    session['authenticated'] = True
                    session['username'] = username
                    session['user_id'] = user_row['id']  # int

                    # Create a ChatSession
                    ChatContext.create_session(session['user_id'])

                    print(f"[Login] Successful for user: {username} (ID: {session['user_id']})")

                    # Use url_for with _external=True to generate full URLs
                    next_url = request.args.get('next') or url_for('index', _external=True)
                    return redirect(next_url)

            except Exception as e:
                print(f"[Login] Database error: {e}")
                flash('Database error during login. Please try again.', 'error')
                return render_template('login.html', error='System error')

    # Failed login
    print(f"[Login] Failed attempt for username: {username}")
    flash('Invalid username or password', 'error')
    return render_template('login.html', error='Invalid username or password')

@mira.route("/")
def index():
    if not session.get('authenticated'):
        return redirect(url_for('login'))

    # Get user data to pass to frontend
    user_id = session.get('user_id')
    username = session.get('username')

    # Debug to see what we're actually getting
    print(f"[Debug] Rendering index with user_id={user_id}, username={username}")

    # Render frontend with user data
    return render_template('index.html',
                           user_id=user_id,
                           username=username,
                           authenticated=True)

@socketio.on('connect')
def handle_connect():
    if 'authenticated' not in session or not session.get('authenticated'):
        print("[Socket.io] Unauthenticated connection - no session created")
        return

    user_id = session.get('user_id')
    # Unique socket ID for this connection
    socket_id = request.sid # type: ignore[attr-defined]

    # Register device
    ACTIVE_DEVICES[socket_id] = {
        'user_id': user_id,
        'device_name': request.headers.get('User-Agent', 'Unknown Device'),
        'last_active': datetime.now()
    }

    print(f"[Device] New connection: user_id={user_id}, socket_id={socket_id}")

@socketio.on('disconnect')
def handle_disconnect():
    socket_id = request.sid # type: ignore[attr-defined]
    if socket_id in ACTIVE_DEVICES:
        user_id = ACTIVE_DEVICES[socket_id]['user_id']
        print(f"[Device] Disconnected: user_id={user_id}, socket_id={socket_id}")
        del ACTIVE_DEVICES[socket_id]

# socket event handler
@socketio.on('get_attachment_status')
def handle_attachment_status():
    user_id = session.get('user_id')
    emit('attachment_status', {
        "has_attachment": HasAttachment.has_attachment(user_id),
        "user_id": user_id
    })

########################################################################################
"""###########################        Voice-in         ##############################"""
########################################################################################
# when audio is recorded by the frontend
@mira.route('/upload_audio', methods=['POST'])
def upload_audio():
    """
    Handle audio upload and transcription based on database settings.
    Supports both Vosk and Distil-Whisper STT engines.
    """
    user_id = session.get('user_id')

    try:
        with AppState.acquire(user_id):

            audio = request.files['audio']

            # Get STT settings from database
            stt_engine = GetDB.get_stt()
            stt_mode = GetDB.get_stt_mode()
            print(f"[STT] Loaded DB settings. Engine: '{stt_engine}', Mode: '{stt_mode}'")

            # Get user-specific audio paths
            webm_path, wav_path = FilePool.get_audio_paths(user_id)

            # Convert to WAV
            audio.save(webm_path)
            try:
                subprocess.run([
                    "ffmpeg", "-y", "-loglevel", "error", "-i", str(webm_path),
                    "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav_path)
                ], check=True)
            except subprocess.CalledProcessError as e:
                print(f"[FFmpeg] WAV conversion failed: {e}")
                return jsonify({"error": "Audio conversion failed"}), 500

            # Choose transcription engine
            try:
                if stt_engine.lower() == 'distil-whisper':
                    print(f"[STT] Using Distil-Whisper engine ({stt_mode.upper()} mode)")
                    result = transcribe_distil_whisper(wav_path)
                else:
                    print("[STT] Using Vosk engine")
                    result = transcribe_vosk(wav_path, wake_word="please")
                return jsonify({"transcript": result["text"]})

            except Exception as e:
                print(f"[STT] Transcription failed with {stt_engine}: {e}")
                return jsonify({"error": "Transcription failed"}), 500

    except TimeoutError as e:
        return jsonify({
            "error": str(e),
        }), 503  # Service Unavailable

########################################################################################
"""###########################        Voice-out         #############################"""
########################################################################################
@mira.route("/start_voice", methods=["POST"])
def start_voice():
    """Start voice synthesis"""
    data = request.json
    text = data.get("text", "")
    user_id = session.get('user_id')

    if not user_id:
        return jsonify({"error": "user_id is required"}), 400

    try:
        with AppState.acquire(user_id):
            try:
                # Clean user's previous files first
                clean_voice_chunks(user_id)

                # Start synthesis in background thread
                print(f"[TTS] Starting synthesis for User: {user_id}")
                Thread(target=voice_out, args=(text, user_id)).start() # TODO: Lock this thread, create a bucket...
                return jsonify({"status": "voice synthesis started", "user_id": user_id})
            except Exception as e:
                return jsonify({"error": str(e)}), 500

    except TimeoutError as e:
        return jsonify({
            "error": str(e),
        }), 503  # Service Unavailable

########################################################################################
"""############################      Chat+Intent       ##############################"""
########################################################################################
"""
Data structure: {"intent": "chat", "command": "Pass to Mira.", "matched": user_msg}
    - Intent can be action/chat. 
    - Commands are in services/command_library.py and the intent prompt in services/prompts_system.py
    - user_msg is split by the LLM (intent route) and set as user_msg field in each of n json objects
        - That means we can resolve chat cleanly without confusing it with commands
        - new data structure: {complete object}\n{complete object}\n...

ChatState is global per user, so the piping is simpler = 
    - tunnel into all three (hardcode, intent, chat) for each complete object.
    - dont have to constantly convert data when passing from front- to backend.
"""

@mira.route("/hardcode", methods=["POST"])
def hardcode():
    # Get user-specific state instead of global ChatState
    chat_state = get_chat_state()
    user_id = session.get('user_id')
    data = request.get_json(silent=True) or {}
    user_msg = data.get("message", "").strip()
    chat_state.user_msg = user_msg

    try:
        with AppState.acquire(user_id):
            # wikipedia in user message
            if "wikipedia" in user_msg.lower():
                ask_wikipedia(user_msg)
                chat_state.intent = {"intent": "chat", "command": "Pass to Mira.", "matched": user_msg}
                HasAttachment.set_attachment(user_id, True)
                print("[Hardcode] Detected wikipedia")
                return jsonify({"reply": "Hardcode detected: wikipedia"})

            # web and search in user message (dummy pipeline)
            elif "web" in user_msg and "search" in user_msg.lower():
                ask_web(user_msg)
                chat_state.intent = {"intent": "chat", "command": "Pass to Mira.", "matched": user_msg}
                HasAttachment.set_attachment(user_id, True)
                print("[Hardcode] Detected web search")
                return jsonify({"reply": "Hardcode detected: web search"})

            else:
                # no hardcode detected
                chat_state.intent = None
                return jsonify({"reply": "No hardcode detected"})  # frontend dives into /intent

    except TimeoutError as e:
        return jsonify({
            "error": str(e),
        }), 503  # Service Unavailable

@mira.route("/intent", methods=["POST"])
def intent():
    # Get user-specific state
    chat_state = get_chat_state()
    user_id = session.get('user_id')
    user_msg = chat_state.user_msg or ""

    # Bypass if hardcode already set intent to chat
    if chat_state.intent and isinstance(chat_state.intent, dict) and chat_state.intent.get(
            "intent") == "chat":  # <-- CHANGED
        print("[Intent] Detected chat, bypassing.")
        return jsonify({"reply": "Bypass intent"})

    try:
        with AppState.acquire(user_id):
            try:
                raw_intent = ask_intent(user_msg)  # returns JSONL string: {complete object}\n{complete object}\n...
                intents = []
                commands = []

                # separate properly
                for line in raw_intent.strip().splitlines():
                    if not line.strip():
                        continue
                    obj = json.loads(line)

                    # If obj is a list, iterate through its items
                    # TODO: Figure out why we need this duplication and unify
                    if isinstance(obj, list):
                        for item in obj:
                            intents.append(item)
                            intent_type = item.get("intent", "")
                            command = item.get("command", "")
                            if intent_type == "action":
                                if command == "get weather":
                                    chat_state.weather = ask_weather(user_id, user_msg)
                                    print(f"[Intent] Determined weather: {chat_state.weather}")
                                    # mark as bypass so frontend continues into /chat
                                    return jsonify({"reply": "Bypass intent"})
                                else:
                                    if command_lookup(command, user_msg):
                                        commands.append(command)
                                    else:
                                        print(f"[Intent] Ignored invalid command: {command}")
                            elif intent_type == "chat":
                                chat_state.intent = item
                    # If obj is a dict, iterate through its items
                    elif isinstance(obj, dict):
                        intents.append(obj)
                        intent_type = obj.get("intent", "")
                        command = obj.get("command", "")
                        if intent_type == "action":
                            if command == "get weather":
                                chat_state.weather = ask_weather(user_id, user_msg)
                                print(f"[Intent] Determined weather: {chat_state.weather}")
                                # mark as bypass so frontend continues into /chat
                                return jsonify({"reply": "Bypass intent"})
                            else:
                                if command_lookup(command, user_msg):
                                    commands.append(command)
                                else:
                                    print(f"[Intent] Ignored invalid command: {command}")
                        elif intent_type == "chat":
                            chat_state.intent = obj

                # Decide what to return based on intent composition
                if commands and any(i.get("intent") == "chat" for i in intents if isinstance(i, dict)):
                    # Mixed case: both action and chat
                    chat_intent = next(
                        (i for i in intents if isinstance(i, dict) and i.get("intent") == "chat"),
                        None
                    )
                    if chat_intent:
                        chat_state.intent = chat_intent
                    print(f"[Intent] Determined actions: {commands} and chat")
                    return jsonify({"reply": f"Handled action: {', '.join(commands)}; Chat"})

                elif commands:
                    # only actions
                    chat_state.intent = intents
                    print(f"[Intent] Determined actions: {commands}")
                    return jsonify({"reply": f"Handled action: {', '.join(commands)}"})
                else:
                    # only chat
                    print("[Intent] Determined chat intent, passing to /chat")
                    return jsonify({"reply": "Bypass intent"})

            except json.JSONDecodeError:
                return jsonify({"reply": "Invalid intent response: not a valid JSON"})
            except Exception as e:
                return jsonify({"reply": f"Error parsing intent: {str(e)}"})

    except TimeoutError as e:
        return jsonify({
            "error": str(e),
        }), 503  # Service Unavailable

@mira.route("/chat", methods=["POST"])
def chat():
    chat_state = get_chat_state()
    # Get current user's ID
    user_id = session.get('user_id')
    # Get the user's specific session
    chat_session = ChatContext.get_session(user_id)

    try:
        with AppState.acquire(user_id):
            # Unique case (voice out but not chat)
            # So weather context doesn't taint the chat session
            if chat_state.weather:
                response = chat_state.weather
                chat_state.weather = None  # reset
                return jsonify({"reply": response})

            # Default to the raw user message
            user_msg = chat_state.user_msg or ""
            intent = chat_state.intent

            if isinstance(intent, dict) and intent.get("intent") == "chat":
                # Prefer the matched field if present
                matched_text = intent.get("matched")
                if matched_text:
                    user_msg = matched_text

                try:
                    # Channel to VL if an image is attached
                    # Small and probably even big VL models suck at longer text context
                    user_id = session.get('user_id')
                    if HasAttachment.has_attachment(user_id) and HasAttachment.is_picture(user_id):
                        img_path = FilePool.get_picture_path(user_id)
                        print(f"[VL] Reading attachment...")
                        assistant_reply = image_inference(img_path, user_msg)
                        HasAttachment.clear(user_id)  # both is picture and attachment
                        socketio.emit('attachment_update', {
                            "has_attachment": False,
                            "type": "consumed"
                        })
                        return jsonify({"reply": assistant_reply})

                    # Channel to txt model if we've converted an allowed input into .txt
                    elif HasAttachment.has_attachment(user_id):
                        txt_path = FilePool.get_output_path(user_id)
                        try:
                            context = txt_path.read_text(encoding="utf-8")
                            combined_input = context + "\n\n" + user_msg
                        except Exception as e:
                            print(f"[Chat] Failed to read attachment: {e}")
                            combined_input = user_msg
                        socketio.emit('attachment_update', {
                            "has_attachment": False,
                            "type": "consumed"
                        })
                        HasAttachment.set_attachment(user_id,False)
                    else:
                        # Is just regular chat without attachment = continue
                        combined_input = user_msg

                    # Pass to txt LLM
                    assistant_reply = chat_session.ask(combined_input)

                except Exception as e:
                    print(f"[Chat] Error: {e}")
                    assistant_reply = "Error processing message."

                return jsonify({"reply": assistant_reply})

            else:
                # Action intents already handled in /intent
                # Front end doesn't analyze. It just tunnels into all three routes, so we need this last else.
                return jsonify({"reply": ""})

    except TimeoutError as e:
        return jsonify({
            "error": str(e),
        }), 503  # Service Unavailable

@mira.route("/new_chat", methods=["POST"])
def new_chat():
    user_id = session.get('user_id')

    try:
        with AppState.acquire(user_id):

            # Create a new session for this user only
            ChatContext.create_session(user_id)  # This replaces the old session
            ChatContext.chat_session = ChatSession(user_id)

            # Reset the file and attachment managers
            HasAttachment.clear(user_id)
            FilePool.cleanup_user_files(user_id)

            # Reset user-specific state
            chat_state = get_chat_state()
            chat_state.intent = None
            chat_state.user_msg = None
            chat_state.weather = None
            chat_state.picture = None
            print("[Chat] Started new chat session")
            return jsonify({"status": "new session started"})

    except TimeoutError as e:
        return jsonify({
            "error": str(e),
        }), 503  # Service Unavailable

########################################################################################
"""#########################  Attachment&BrowserPlugin ##############################"""
########################################################################################
# receiving from picture.js (phone camera)
@mira.route('/picture', methods=['POST'])
def picture():

    # Match to user
    user_id = session.get('user_id')

    try:
        with AppState.acquire(user_id):

            # Save file
            picture_path = FilePool.get_picture_path(user_id)
            file = request.files.get('picture')
            file.save(picture_path)

            # Set global attachment state
            HasAttachment.set_attachment(user_id, True)
            HasAttachment.set_picture(user_id, True)

            # Notify frontend via Socket.IO
            socketio.emit('attachment_update', {
                "has_attachment": True,
                "type": "picture",
                "user_id": user_id
            })
            print(f"[Picture] Attached for user {user_id}: {picture_path}")
            return "Picture received and ready", 200

    except TimeoutError as e:
        return jsonify({
            "error": str(e),
        }), 503  # Service Unavailable


@mira.route('/receive', methods=['POST'])
def receive():
    """
    When we receive from the browser extension.
    Can be one of text, link, picture.
    """
    # For authenticated users, use their user_id
    user_id = session.get('user_id') if session.get('authenticated') else None

    # For unauthenticated localhost requests, use a temporary ID (browser extension)
    if not user_id and request.remote_addr in ["127.0.0.1", "::1"]:
        user_id = "1"

    if not user_id:
        return jsonify({"status": "error", "message": "No user session"}), 401

    try:
        with AppState.acquire(user_id):

            data = request.get_json(silent=True) or {}
            print(f"[Receive] Payload from extension for user {user_id}:", data)

            payload_type = data.get("type")
            content = data.get("content", "").strip()
            print("[Receive] Content:", content, "\nAs type:", payload_type)

            # IMAGE
            if payload_type == "image_blob" and content:
                picture_path = FilePool.get_picture_path(user_id)
                print(f"[Receive] Received image_blob ({len(content)} base64 chars)")

                try:
                    # prepare for VL LLM
                    image_data = base64.b64decode(content)
                    img = Image.open(io.BytesIO(image_data))
                    if img.mode in ("RGBA", "LA", "P"):
                        img = img.convert("RGB")
                    img.save(picture_path, format="JPEG", quality=92)
                    print(f"[Receive] Image saved from browser: {picture_path} ({picture_path.stat().st_size} bytes)")

                    # set flags
                    HasAttachment.clear(user_id) # Both attachment and picture

                    # notify frontend
                    socketio.emit('attachment_update', {
                        "has_attachment": True,
                        "type": "picture",
                        "user_id": user_id
                    })
                    return jsonify({"status": "ok", "attachment": True}), 200

                # Extension uses Chromium's native picture copy, which should be pretty reliable, still:
                except Exception as e:
                    print(f"[Receive] Failed to process image_blob: {type(e).__name__}: {e}")
                    return jsonify({"status": "error", "message": "Invalid image data"}), 400

            # PAGE / LINK
            if payload_type in ("page", "link") and content:
                print(f"[Receive] Saving {payload_type}: {content}")
                output_path = FilePool.get_output_path(user_id)
                save_url_text(content, output_path) # content=url
                HasAttachment.set_attachment(user_id, True)
                socketio.emit('attachment_update', {
                    "has_attachment": True,
                    "type": "text",
                    "user_id": user_id
                })
                return jsonify({"status": "ok", "attachment": True}), 200

            # TEXT SELECTION
            if payload_type == "selection" and content:
                output_path = FilePool.get_output_path(user_id)
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"[Receive] Text selection saved ({len(content)} chars): {output_path}")
                HasAttachment.set_attachment(user_id, True)
                socketio.emit('attachment_update', {
                    "has_attachment": True,
                    "type": "text",
                    "user_id": user_id
                })
                return jsonify({"status": "ok", "attachment": True}), 200

            return jsonify({"status": "ignored"}), 200 # Can't actually happen but PyCharm will complain

    except TimeoutError as e:
        return jsonify({
            "error": str(e),
        }), 503  # Service Unavailable

# Receiving upload through frontend button.
@mira.route("/upload", methods=["POST"])
def upload():
    """
    Checks against services/config.py FileSupport.
    """
    if "file" not in request.files:
        return jsonify({"status": "no file received"}), 400

    # get user ID
    user_id = session.get('user_id')

    try:
        with AppState.acquire(user_id):

            # Check if file type is supported
            file = request.files["file"]
            filename_path = Path(file.filename)
            if not FileSupport.is_supported(filename_path):
                return jsonify({"status": "unsupported file type"}), 415

            # Save to temp location first
            temp_upload_path = BASE_PATH / "temp" / f"temp_upload_{user_id}_{file.filename}"
            temp_upload_path.parent.mkdir(parents=True, exist_ok=True)
            file.save(temp_upload_path)

            # Decide how to process based on type
            ext = filename_path.suffix.lower()
            if ext in FileSupport.IMAGE_EXTENSIONS:
                picture_path = FilePool.get_picture_path(user_id)
                # Open and convert to JPEG
                with Image.open(temp_upload_path) as img:
                    # Ensure compatibility with JPEG (no alpha channel, no palette)
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGB")
                    img.save(picture_path, format="JPEG", quality=90)

                print(f"[Upload] Converted image to JPEG: {picture_path}")
                HasAttachment.set_picture(user_id, True)
            else:
                output_path = FilePool.get_output_path(user_id)
                file_to_txt(temp_upload_path, output_path)
                print(f"[Upload] Received file: {file.filename}")

            HasAttachment.set_attachment(user_id, True)

            # Cleanup temp file
            try:
                temp_upload_path.unlink()
            except Exception as e:
                print(f"[Upload] Cleanup failed: {e}")

            return jsonify({"status": "ok", "filename": file.filename})

    except TimeoutError as e:
        return jsonify({
            "error": str(e),
        }), 503  # Service Unavailable

# removes attachment
@mira.route("/remove_attachment", methods=["POST"])
def remove_attachment():
    user_id = session.get('user_id')
    HasAttachment.clear(user_id)
    FilePool.cleanup_user_files(user_id)
    print("[Attachment] Removed via frontend")
    return jsonify({"status": "attachment cleared"})

########################################################################################
"""############################     Settings-Modal     ##############################"""
########################################################################################
# load settings on modal open
@mira.route("/api/settings", methods=["GET"])
def load_settings():
    print("[Settings modal] Loading.")
    user_id = session.get('user_id')
    return jsonify(get_settings(user_id))

# persist settings on save button
@mira.route("/api/settings", methods=["POST"])
def persist_settings():

    user_id = session.get('user_id')
    try:
        with AppState.acquire(user_id):

            data = request.get_json()
            save_settings(user_id, data)
            # refresh plugs
            load_plugs_from_db()
            print("[Settings modal] Saved.")
            return jsonify({"status": "ok"})

    except TimeoutError as e:
        return jsonify({
            "error": str(e),
        }), 503  # Service Unavailable

########################################################################################
"""############################         Lists          ##############################"""
########################################################################################
# persist frontend edits to shopping list
@mira.route('/save_shopping_list', methods=['POST'])
def save_shopping_list():
    user_id = 99 # Lists are shared across all users, so we lock with 99
    try:
        with AppState.acquire(user_id):

            items = request.get_json()
            shopping_list_path = BASE_PATH / "static" / "lists" / "shopping_list.json"
            # Write the updated list back to the file
            with open(shopping_list_path, 'w', encoding='utf-8') as f:
                json.dump(items, f, indent=2, ensure_ascii=False)
            return jsonify(items), 200

    except TimeoutError as e:
        return jsonify({
            "error": str(e),
        }), 503  # Service Unavailable

# persist frontend edits to to-do list
@mira.route('/save_todo_list', methods=['POST'])
def save_todo_list():
    user_id = 99 # Lists are shared across all users, so we lock with 99
    try:
        with AppState.acquire(user_id):

            todo_list_path = BASE_PATH / "static" / "lists" / "to_do_list.json"
            items = request.get_json()
            # Write the updated list back to the file
            with open(todo_list_path, 'w', encoding='utf-8') as f:
                json.dump(items, f, indent=2, ensure_ascii=False)
            return jsonify(items), 200

    except TimeoutError as e:
        return jsonify({
            "error": str(e),
        }), 503  # Service Unavailable

########################################################################################
"""############################       Nutrition        ##############################"""
########################################################################################
# when we've made a picture of a barcode
@mira.route('/nutrition/scan/', methods=['POST'])
def receive_barcode_image():
    user_id = session.get('user_id')
    try:
        with AppState.acquire(user_id):

            image_path = FilePool.get_barcode_path(user_id)
            try:
                # 1. receive and write to disk
                file = request.files['file']
                file.save(image_path)
                print(f"[Barcode] Saved uploaded image to {image_path}")
                # 2. Scan the saved image
                code = scan_barcode(str(image_path))  # scan_barcode expects a str path
                if not code:
                    print(f"[Barcode] No barcode found in image")
                    return {"error": "No barcode found in image"}, 400
                print(f"[Barcode] Determined as: {code}")
                # 3. Check Barcode against local DB
                product = GetDB.get_nutri_item(code)
                if product: print(f"[Barcode] Retrieved product from local DB.")
                # 4. Not found? Check online DB
                if not product:
                    product = lookup_barcode(code)
                    if not product:
                        print(f"[Barcode] No product found at OpenFoodFacts with {code}.")
                        return {"error": f"No product found for barcode {code}"}, 404
                    else: print(f"[Barcode] Fetched product from OpenFoodFacts.")
                # 5. Return product
                return { # frontend returns to input state (user product verification and entry of amount consumed dialogue)
                    "barcode": code,
                    "product_name": product.get("product_name"),
                    "nutriments": product.get("nutriments", {}),
                    "quantity": product.get("quantity"),
                    "serving_size": product.get("serving_size"),
                    "product_quantity": product.get("product_quantity"),
                }
            except Exception as e:
                print(f"[Barcode] Error: {e}")
                return {"error": str(e)}, 500

    except TimeoutError as e:
        return jsonify({
            "error": str(e),
        }), 503  # Service Unavailable

# when we receive product data after barcode scan
@mira.route('/nutrition/product', methods=['POST'])
def receive_scanned_product():
    """
    Expected JSON payload:
    {
      "barcode": "Number",
      "product_name": "Greek Yogurt",
      "quantity": "500", -- normalized
      "serving_size": "150", -- normalized
      "product_quantity": "4",
      "nutriments": {
        "energy_kcal_100g": 59,
        "protein_100g": 10.0,
        "carbohydrates_100g": 3.6,
        "fat_100g": 0.4,
      }
    }
    :return:
    """
    user_id = session.get('user_id')
    try:
        with AppState.acquire(user_id):

            data = request.get_json() # Frontend sends valid json
            persist_nutri_item(data) # Write to DB
            print(f"[Nutrition] Received scanned product: {data['product_name']} ({data['barcode']})")
            return jsonify({"message": "Product received successfully"}), 200 # Frontend tunnels back into route nutrition/log

    except TimeoutError as e:
        return jsonify({
            "error": str(e),
        }), 503  # Service Unavailable

# when we receive the actual intake
@mira.route('/nutrition/log', methods=['POST'])
def log_nutrition_intake():
    """
    Expected JSON payload:
    {
        "product_name": "PRODUCT",
        "quantity_consumed": 330,           // in grams or ml (already converted)
        "kcal_consumed": 0,
        "carbs_consumed": 0,
        "fat_consumed": 0,
        "protein_consumed": 12.5
    }
    """
    user_id = session.get('user_id')
    try:
        with AppState.acquire(user_id):

            data = request.get_json() # Frontend sends valid json
            persist_nutrition_intake(data) # Write to DB
            print(f"[Nutrition] Logged intake: {data['product_name']}: "
                  f"{data['kcal_consumed']}kcal, {data['protein_consumed']}g protein")
            return jsonify({"message": "Intake logged successfully"}), 200 # frontend returns to input ready state

    except TimeoutError as e:
        return jsonify({
            "error": str(e),
        }), 503  # Service Unavailable

# when we enter daily nutri intake
@mira.route('/nutrition/settings', methods=['POST'])
def receive_nutrition_settings():
    user_id = session.get('user_id')
    try:
        with AppState.acquire(user_id):

            data = request.get_json()
            save_nutrition_user_values(data)
            print(f"[Nutrition Settings] Saved: {data}")
            return jsonify({"message": "Nutrition settings saved"}), 200

    except TimeoutError as e:
        return jsonify({
            "error": str(e),
        }), 503  # Service Unavailable

# get daily max allowed values
@mira.route('/nutrition/settings', methods=['GET'])
def get_nutrition_settings():
    values = GetDB.get_nutrition_user_values()
    print(f"[Nutrition Settings] Loaded: {values}")
    return jsonify(values)

# get already consumed today.
@mira.route('/nutrition/today', methods=['GET'])
def get_today_totals():
    totals = GetDB.get_today_nutrition_totals()
    return jsonify(totals)

# get the items consumed today
@mira.route('/nutrition/today/items', methods=['GET'])
def get_today_items():
    items = GetDB.get_today_consumed_items()
    return jsonify(items)

# update/remove item that was consumed today
@mira.route('/nutrition/today/items', methods=['POST'])
def update_today_items():
    user_id = session.get('user_id')
    try:
        with AppState.acquire(user_id):

            data = request.get_json(silent=True) or []
            if not isinstance(data, list):
                return jsonify({"error": "Expected a list of items"}), 400
            success = update_today_consumed_items(data)
            if success:
                return jsonify({"status": "ok"})
            else:
                return jsonify({"error": "Failed to update database"}), 500

    except TimeoutError as e:
        return jsonify({
            "error": str(e),
        }), 503  # Service Unavailable

# when the user searches for food items
@mira.route('/nutrition/search', methods=['GET'])
def nutrition_search():
    user_id = session.get('user_id')
    try:
        with AppState.acquire(user_id):

            # Returns LocalDB as most salient, FoundationFoods next, and then BrandedFoods.
            query = request.args.get('q', '').strip()
            # only begin live search at three letters entered.
            if not query or len(query) < 3:
                return jsonify([])

            items = food_search(query)
            if items: print(f"[Nutrition] Returned search result")
            return jsonify(items)

    except TimeoutError as e:
        return jsonify({
            "error": str(e),
        }), 503  # Service Unavailable

########################################################################################
"""############################          Run           ##############################"""
########################################################################################
if __name__ == '__main__':
    init_all()

    # Start Flask
    # HTTPS server
    flask_thread = threading.Thread(target=run_https_flask, daemon=True)
    flask_thread.start()
    # HTTP server
    http_thread = threading.Thread(target=run_http_flask, daemon=True)
    http_thread.start()

    # ONLY run the GUI when not in Docker
    if os.getenv("IN_DOCKER", "").lower() != "true":
        # Launch WebView using Qt backend
        set_qt_identity()
        # Build the URL
        local_ip = get_local_ip()
        url = f"https://{local_ip}:5001/login"

        # actually create the window
        window = webview.create_window(
            "Mira",
            url,
            width=400,
            height=600,
            resizable=True,  # This one and frameless conflict for me.
            frameless=False,  # remove window frame (titlebar)
            min_size=(300, 400),
            transparent=True,
        )


        def configure():
            """
            Threading during startup: Slower machines might need this guard.
            """
            w = window
            try:
                top = w.gui.window()
            except Exception:
                top = None
            if top is None:
                # try again shortly if not ready
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(100, configure)
                return
            # X11-specific transparency configuration
            top.setWindowFlag(Qt.WindowType.FramelessWindowHint, False)
            top.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            top.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
            # X11 specific: ensure compositing is enabled
            top.setWindowOpacity(0.75)  # Matches CSS opacity
            # no idea
            webview_widget = top.findChild(QtWidgets.QWidget, "QWebEngineView")
            if webview_widget is None:
                for child in top.findChildren(QtWidgets.QWidget):
                    if child.metaObject().className().startswith("QWebEngine"):
                        webview_widget = child
                        break
            if webview_widget is not None:
                webview_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
                webview_widget.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
                try:
                    custom_page = CustomWebEnginePage(webview_widget)
                    webview_widget.setPage(custom_page)
                    custom_page.setBackgroundColor(QColor(0, 0, 0, 0))
                except Exception as e:
                    print(f"Transparency or certificate configuration error: {e}")
                try:
                    page = webview_widget.page()
                    # Explicitly set transparent background
                    page.setBackgroundColor(QColor(0, 0, 0, 0))
                except Exception as e:
                    print(f"Transparency configuration error: {e}")


        # pass zero-arg callback
        webview.start(gui='qt', debug=False, func=configure)
        print("[Unbound] Running without Docker.")

        # For local development, start the single HTTP server
        socketio.run(mira, debug=False, host='0.0.0.0', port=5000)
    else:
        # In Docker, don't start any servers here - WSGI will handle it
        print("[Docker] Host GUI disabled. Use nginx reverse proxy.")
        # Keep alive for development, but in production WSGI handles this
        import time

        while True:
            time.sleep(1)