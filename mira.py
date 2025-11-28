########################################################################################
"""############################        mira.py         ##############################"""
"""##############     MIRA = Multi-Intent Recognition Assistant     #################"""
########################################################################################

########################################################################################
"""############################     System imports     ##############################"""
########################################################################################
import json
import threading
import webview
import subprocess
from PyQt6 import QtGui, QtWidgets
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineCertificateError
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from datetime import datetime
from threading import Thread
from pathlib import Path
from collections import Counter

########################################################################################
"""############################    Services imports    ##############################"""
########################################################################################
# global vars
from services.globals import HasAttachment, BASE_PATH, ALLOWED_KEYS, SECRET_KEY, get_local_ip
# DB
from services.db_access import init_db
from services.db_persist import save_settings, save_nutrition_user_values, persist_nutri_item_values, update_package_item_count
from services.db_get import get_settings, GetDB
# cast to text
from services.url_to_txt import save_url_text
from services.file_to_txt import is_supported_file, file_to_txt
from services.stt import get_vosk_model, transcribe_audio
# intent
from services.llm_intent import ask_intent, ask_wikipedia, ask_web
# Chat
from services.llm_chat import ChatSession, ask_weather
from services.tts import init_tts, voice_out, split_into_chunks, clean_voice_chunks
# command
from services.command_library import command_lookup
#from services.browser.chromium import chromium_print
from services.music import discover_playlists
from services.smart_plugs import load_plugs_from_db
# barcode/nutrition
from services.barcode import lookup_barcode

########################################################################################
"""###########################         Setup           ##############################"""
########################################################################################
mira = Flask(__name__, static_folder="static", template_folder="templates")
chat_session = ChatSession()
socketio = SocketIO(mira)
CORS(mira, resources={
    r"/upload_audio": {"origins": "*"},
    r"/receive": {"origins": "*"}
})
mira.secret_key = SECRET_KEY

class CustomWebEnginePage(QWebEnginePage):
    def certificateError(self, error: QWebEngineCertificateError) -> bool:
        print(f"[SSL] Certificate error for {error.url().toString()}")
        if error.isOverridable():
            error.acceptCertificate()
            return True
        return False

@socketio.on('connect')
def handle_connect():
    print('Client connected')

# serve frontend for the webview
@mira.route("/")
def index():
    return render_template("index.html")

########################################################################################
"""############################     Settings-Modal     ##############################"""
########################################################################################
# load settings
@mira.route("/api/settings", methods=["GET"])
def load_settings():
    return jsonify(get_settings())

# persist settings
@mira.route("/api/settings", methods=["POST"])
def persist_settings():
    data = request.get_json()
    save_settings(data)
    load_plugs_from_db()
    return jsonify({"status": "ok"})

########################################################################################
"""#########################  Attachment&BrowserPlugin ##############################"""
########################################################################################
# receiving chromium payload
@mira.route('/receive', methods=['POST'])
def receive():
    data = request.get_json()
    print("Received:", data)
    payload = data.get("type")

    if payload in ("page", "link"):
        #chromium_print(data)
        url = data.get("content")
        save_url_text(url)
        HasAttachment.set_attachment(True)
        # Emit a socket event to notify clients
        socketio.emit('attachment_update', {
            "has_attachment": True,
            "type": payload
        })
        return jsonify({"status": "ok", "attachment": True}), 200

    if payload == "selection":
        txt_path = BASE_PATH / "temp" / "output.txt"
        # overwrite
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(data.get('content', ''))
        HasAttachment.set_attachment(True)
        # Emit a socket event to notify clients
        socketio.emit('attachment_update', {
            "has_attachment": True,
            "type": payload
        })
        return jsonify({"status": "ok", "attachment": True}), 200

    return jsonify({"status": "ignored", "attachment": False}), 200

# upload attachment
@mira.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"status": "no file received"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"status": "empty filename"}), 400

    filename_path = Path(file.filename)
    if not is_supported_file(filename_path):
        return jsonify({"status": "unsupported file type"}), 415

    # Save the uploaded file to disk
    upload_path = BASE_PATH / "temp" / file.filename
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    file.save(upload_path)

    # Now process the saved file
    file_to_txt(upload_path)

    print(f"[Upload] Received file: {file.filename}")
    HasAttachment.set_attachment(True)
    return jsonify({"status": "ok", "filename": file.filename})

# removes attachment
@mira.route("/remove_attachment", methods=["POST"])
def remove_attachment():
    HasAttachment.set_attachment(False)
    print("[Attachment] Removed via frontend")
    return jsonify({"status": "attachment cleared"})

########################################################################################
"""############################         Lists          ##############################"""
########################################################################################
# persist frontend edits to shopping list
@mira.route('/save_shopping_list', methods=['POST'])
def save_shopping_list():
    try:
        items = request.get_json()
        shopping_list_path = BASE_PATH / "static" / "lists" / "shopping_list.json"
        # Write the updated list back to the file
        with open(shopping_list_path, 'w', encoding='utf-8') as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
        return jsonify(items), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# persist frontend edits to to-do list
@mira.route('/save_todo_list', methods=['POST'])
def save_todo_list():
    todo_list_path = BASE_PATH / "static" / "lists" / "to_do_list.json"
    try:
        items = request.get_json()
        # Write the updated list back to the file
        with open(todo_list_path, 'w', encoding='utf-8') as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
        return jsonify(items), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

########################################################################################
"""############################      Chat+Intent       ##############################"""
########################################################################################
# starts new chat session
@mira.route("/new_chat", methods=["POST"])
def new_chat():
    global chat_session
    chat_session = ChatSession()
    HasAttachment.set_attachment(False)
    return jsonify({"status": "new session started"})

class ChatState:
    intent = None
    user_msg = None
    weather = None

# --- Hardcode route ---
@mira.route("/hardcode", methods=["POST"])
def hardcode():
    data = request.get_json(silent=True) or {}
    user_msg = data.get("message", "").strip()
    ChatState.user_msg = user_msg

    if "wikipedia" in user_msg:
        ask_wikipedia(user_msg)
        ChatState.intent = {"intent": "chat", "command": "Pass to Mira.", "matched": user_msg}
        HasAttachment.set_attachment(True)
        print("[Hardcode] Detected wikipedia")
        return jsonify({"reply": "Hardcode detected: wikipedia"})

    elif "web" in user_msg and "search" in user_msg:
        ask_web(user_msg)
        ChatState.intent = {"intent": "chat", "command": "Pass to Mira.", "matched": user_msg}
        HasAttachment.set_attachment(True)
        print("[Hardcode] Detected web search")
        return jsonify({"reply": "Hardcode detected: web search"})

    else:
        # no hardcode detected
        ChatState.intent = None
        return jsonify({"reply": "No hardcode detected"})

# --- Intent route ---
@mira.route("/intent", methods=["POST"])
def intent():
    user_msg = ChatState.user_msg or ""
    # bypass if hardcode already set intent to chat
    if ChatState.intent and isinstance(ChatState.intent, dict) and ChatState.intent.get("intent") == "chat":
        return jsonify({"reply": "Bypass intent"})

    try:
        raw_intent = ask_intent(user_msg)  # returns JSONL string
        intents = []
        commands = []

        for line in raw_intent.strip().splitlines():
            if not line.strip():
                continue
            obj = json.loads(line)

            # If obj is a list, iterate through its items
            if isinstance(obj, list):
                for item in obj:
                    intents.append(item)
                    intent_type = item.get("intent", "")
                    command = item.get("command", "")
                    if intent_type == "action":
                        if command == "get Weather":
                            ChatState.weather = ask_weather(user_msg)
                            print(f"[Intent] Determined weather: {ChatState.weather}")
                            # mark as bypass so frontend continues into /chat
                            return jsonify({"reply": "Bypass intent"})
                        else:
                            command_lookup(command, user_msg)
                            commands.append(command)
                    elif intent_type == "chat":
                        ChatState.intent = item
            # If obj is a dict, iterate through its items
            elif isinstance(obj, dict):
                intents.append(obj)
                intent_type = obj.get("intent", "")
                command = obj.get("command", "")
                if intent_type == "action":
                    if command == "get Weather":
                        ChatState.weather = ask_weather(user_msg)
                        print(f"[Intent] Determined weather: {ChatState.weather}")
                        # mark as bypass so frontend continues into /chat
                        return jsonify({"reply": "Bypass intent"})
                    else:
                        command_lookup(command, user_msg)
                        commands.append(command)
                elif intent_type == "chat":
                    ChatState.intent = obj

        # Decide what to return based on intent composition
        if commands and any(i.get("intent") == "chat" for i in intents if isinstance(i, dict)):
            # Mixed case: both action and chat
            chat_intent = next(
                (i for i in intents if isinstance(i, dict) and i.get("intent") == "chat"),
                None
            )
            if chat_intent:
                ChatState.intent = chat_intent
            print(f"[Intent] Determined actions: {commands} and chat")
            return jsonify({"reply": f"Handled action: {', '.join(commands)}; Chat"})

        elif commands:
            # only actions
            ChatState.intent = intents
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

# --- Chat route ---
@mira.route("/chat", methods=["POST"])
def chat():
    # Weather special case
    if ChatState.weather:
        response = ChatState.weather
        ChatState.weather = None  # reset after use
        return jsonify({"reply": response})

    # Default to the raw user message
    user_msg = ChatState.user_msg or ""
    intent = ChatState.intent

    if isinstance(intent, dict) and intent.get("intent") == "chat":
        # Prefer the matched field if present
        matched_text = intent.get("matched")
        if matched_text:
            user_msg = matched_text

        try:
            if HasAttachment.has_attachment():
                txt_path = BASE_PATH / "temp" / "output.txt"
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
                HasAttachment.set_attachment(False)
            else:
                combined_input = user_msg

            assistant_reply = chat_session.ask(combined_input)

        except Exception as e:
            print(f"[Chat] Error: {e}")
            assistant_reply = "Error processing message."

        return jsonify({"reply": assistant_reply})

    else:
        # Action intents already handled in /intent
        return jsonify({"reply": ""})


########################################################################################
"""############################         Voice          ##############################"""
########################################################################################
# determine voice chunk amount
@mira.route("/voice_chunks", methods=["POST"])
def get_chunk_count():
    text = request.json.get("text", "")
    clean_voice_chunks()
    timestamp, chunks = split_into_chunks(text)
    return jsonify({
        "count": len(chunks),
        "timestamp": timestamp
    })

@mira.route("/voice_out", methods=["POST"])
def synth():
    data = request.json
    text = data.get("text", "")
    timestamp = data.get("timestamp") # ("%Y%m%d%H%M%S%f")

    try:
        if not timestamp:
            # Fallback to generating a new timestamp if not provided
            _, chunks = split_into_chunks(text)
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")

        # Use threading to start synthesis
        Thread(target=voice_out, args=(text, timestamp)).start()
        return jsonify({"status": "synthesis started", "timestamp": timestamp})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# when an audio command is recorded
@mira.route('/upload_audio', methods=['POST'])
def upload_audio():
    audio = request.files['audio']
    webm_path = BASE_PATH / "static" / "temp" / "input.webm"
    #mp3_path = BASE_PATH / "static" / "temp" / "input.mp3"
    wav_path = BASE_PATH / "static" / "temp" / "input.wav"

    audio.save(webm_path)
    """
    # Convert to MP3 using ffmpeg for faster_whisper
    # faster_whisper wasn't/isn't updated to cuda13
    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", str(webm_path),
            "-vn", "-ar", "44100", "-ac", "2", "-b:a", "192k", str(mp3_path)
        ], check=True)
    except subprocess.CalledProcessError as e:
        print(f"[FFmpeg] Conversion failed: {e}")
        return jsonify({"error": "Audio conversion failed"}), 500
    """
    # Convert to WAV for Vosk (mono, 16kHz, 16-bit PCM)
    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", str(webm_path),
            "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav_path)
        ], check=True)
    except subprocess.CalledProcessError as e:
        print(f"[FFmpeg] WAV conversion failed: {e}")
        return jsonify({"error": "Audio conversion failed"}), 500

    # Transcribe the MP3 instead of the original webm
    #transcriber = WhisperTranscriber()
    #result = transcriber.transcribe_audio(mp3_path)

    # Transcribe the WAV using Vosk
    result = transcribe_audio(wav_path)

    return jsonify({ "transcript": result["text"] })

########################################################################################
"""############################       Nutrition        ##############################"""
########################################################################################
# when we've scanned a barcode
@mira.route('/barcode', methods=['POST'])
def handle_scan():
    data = request.get_json()
    barcodes = data.get('barcodes')
    print(f"[Barcode] Received batch: {barcodes}")
    # get the most promising result
    counts = Counter(barcodes)
    most_common = counts.most_common(1)[0][0] if counts else None
    print(f"[Barcode] Most likely: {most_common}")
    product = lookup_barcode(most_common)
    persist_nutri_item_values(product)
    return jsonify(product or {}), 200

# when the user enters daily nutri intake
@mira.route('/nutrition/settings', methods=['POST'])
def receive_nutrition_settings():
    data = request.get_json()
    save_nutrition_user_values(data)
    print(f"[Nutrition Settings] Saved: {data}")
    return jsonify({"message": "Nutrition settings saved"}), 200

# get daily max allowed values
@mira.route('/nutrition/settings', methods=['GET'])
def get_nutrition_settings():
    values = GetDB.get_nutrition_user_values()
    return jsonify(values)

# when the user consumes something and possibly updates the package quantity
@mira.route('/nutrition/consume', methods=['POST'])
def consume_nutrition():
    data = request.get_json()
    barcode = data.get('barcode')
    grams = float(data.get('grams'))
    if not barcode or not grams:
        return jsonify({"error": "Missing 'barcode' or 'grams'"}), 400

    package_item_count = data.get('package_item_count')
    if package_item_count is not None:
        package_item_count = int(package_item_count)
        # check db for package_item_count and update if necessary
        update_package_item_count(barcode, package_item_count)
        print(f"[Nutrition/Consume]: Updated Package Item Count to {package_item_count}")
    print(f"[Nutrition/Consume]: Barcode: {barcode} Amount: {grams} ItemCount: {package_item_count}")
    # calc nutri values based on grams consumed

    # write consumption to DB

    # return the total for today to the frontend
    # today_actual = "kcal": row[0] or 0,"carbs": row[1] or 0,"fat": row[2] or 0,"protein": row[3] or 0
    today_actual = GetDB.get_nutrition_intake_today()
    if today_actual:
        return today_actual
    else:
        return jsonify({"error": "Internal server error"}), 500

########################################################################################
"""############################        System          ##############################"""
########################################################################################
# login
@mira.route('/login', methods=['GET'])
def login():
    token = request.args.get("token", "").strip()
    if token in ALLOWED_KEYS:
        session['authenticated'] = True
        print("[Login] Successful.")
        return redirect(url_for('index'))  # or wherever you want to land
    print("[Login] Refused.")
    return jsonify({"error": "Unauthorized"}), 403

# check user authentication
@mira.before_request
def check_access():
    # Allow static, login, and /receive from localhost (for extension)
    if request.path.startswith("/static/") or request.path == "/login" or \
       (request.path == "/receive" and request.remote_addr in ["127.0.0.1", "::1"]):
        print(f"[BeforeRequest] Allowed: {request.path} from {request.remote_addr}")
        return None

    if session.get('authenticated'):
        print("[BeforeRequest] Authenticated.")
        return None

    print("[BeforeRequest] Refused unauthorized access.")
    return jsonify({"error": "Unauthorized"}), 403

# socket event handler
@socketio.on('get_attachment_status')
def handle_attachment_status():
    emit('attachment_status', {
        "has_attachment": HasAttachment.has_attachment()
    })

# flask subprocess
def run_flask():
    # Suppress /attachment_status logs
    import logging
    class AttachmentStatusFilter(logging.Filter):
        def filter(self, record):
            return "/attachment_status" not in record.getMessage()

    logging.getLogger('werkzeug').addFilter(AttachmentStatusFilter())

    init_db()

    # we need fucking ssl or the browser will not allow mic access from local network
    # sudo apt install mkcert
    # sudo apt install libnss3-tools
    # mkcert -install
    # mkcert 192.168.{IP}.{IP}
    # mv 192.168.{IP}.{IP}.pem mira_cert.pem
    # mv 192.168.{IP}.{IP}-key.pem mira_key.pem

    cert = BASE_PATH / "mira_cert.pem"
    key = BASE_PATH / "mira_key.pem"
    ssl_context = (cert, key)
    socketio.run(mira, debug=True, use_reloader=False, host='0.0.0.0', port=5001, ssl_context=ssl_context) #

# local network for browser addon and for the cloudflare tunnel
# tunnel explodes if it has to deal with https from this end
# sudo systemctl daemon-reload
# sudo systemctl restart cloudflared-mira-tunnel
# journalctl -u cloudflared-mira-tunnel -f
def run_http_flask():
    # we need fucking http only for the Chromium extension... and apparently for the cloudflare tunnel
    socketio.run(mira, debug=True, use_reloader=False, host='0.0.0.0', port=5002)

def set_qt_identity():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])  # fallback if not yet created
    app.setApplicationName("Mira")
    app.setWindowIcon(QtGui.QIcon("icon.png"))

if __name__ == '__main__':
    # Start Flask in a background thread
    # HTTPS server
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    # HTTP server
    http_thread = threading.Thread(target=run_http_flask, daemon=True)
    http_thread.start()

    # various init
    load_plugs_from_db()
    discover_playlists()
    init_tts()
    get_vosk_model()

    # Launch WebView using Qt backend
    set_qt_identity()

    # Get the first allowed key
    first_key = next(iter(ALLOWED_KEYS))
    # Build the URL with the selected key and local ip
    local_ip = get_local_ip()
    url = f"https://{local_ip}:5001/login?token={first_key}"

    window = webview.create_window(
        "Mira",
        url,
        width=400,
        height=600,
        resizable=True,
        frameless=False,  # remove window frame (titlebar)
        min_size=(300, 400),
        transparent=True,
    )

    def configure():
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