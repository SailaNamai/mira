########################################################################################
"""############################        mira.py         ##############################"""
"""##############     MIRA = Multi-Intent Recognition Assistant     #################"""
########################################################################################

########################################################################################
"""############################     System imports     ##############################"""
########################################################################################
import os
import json
import threading
import webview
import subprocess
import io
import base64
from PIL import Image
from PyQt6 import QtGui, QtWidgets
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineCertificateError
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from threading import Thread
from pathlib import Path

########################################################################################
"""############################    Services imports    ##############################"""
########################################################################################
# System config
from services.config import HasAttachment, BASE_PATH, ALLOWED_KEYS, SECRET_KEY, get_local_ip, ChatContext, ChatState, \
    init_qwen_vl, FileSupport, init_qwen
from services.mkcert import check_mkcert
# DB
from services.db_access import init_db
from services.db_persist import save_settings, save_nutrition_user_values, persist_nutri_item, persist_nutrition_intake, update_today_consumed_items
from services.db_get import get_settings, GetDB, food_search
# Cast to text
from services.url_to_txt import save_url_text
from services.file_to_txt import file_to_txt
from services.stt_vosk import get_vosk_model, transcribe_audio
# Intent
from services.llm_intent import ask_intent, ask_wikipedia, ask_web
# VL
from services.llm_vl import image_inference
# Chat
from services.llm_chat import ChatSession, ask_weather
from services.tts import init_tts, voice_out, split_into_chunks, clean_voice_chunks
# Command
from services.command_library import command_lookup
#from services.browser.chromium import chromium_print
from services.media import discover_playlists
from services.smart_plugs import load_plugs_from_db
# Barcode/Nutrition
from services.llm_vl import scan_barcode
from services.api_openfoodfacts import lookup_barcode

########################################################################################
"""###########################         Setup           ##############################"""
########################################################################################
mira = Flask(__name__, static_folder="static", template_folder="templates")
socketio = SocketIO(mira)
CORS(mira, resources={
    r"/upload_audio": {"origins": "*"},
    r"/receive": {"origins": "*"}
})
mira.secret_key = SECRET_KEY

# For the non-dockerized version
class CustomWebEnginePage(QWebEnginePage):
    @staticmethod
    def certificate_error(error: QWebEngineCertificateError) -> bool:
        print(f"[SSL] Certificate error for {error.url().toString()}")
        if error.isOverridable():
            error.acceptCertificate()
            return True
        return False

@socketio.on('connect')
def handle_connect():
    print("[Socket.io] Client connected")

# serve frontend for the webview
@mira.route("/")
def index():
    return render_template("index.html")

########################################################################################
"""############################     Settings-Modal     ##############################"""
########################################################################################
# load settings on modal open
@mira.route("/api/settings", methods=["GET"])
def load_settings():
    print("[Settings modal] Loading.")
    return jsonify(get_settings())

# persist settings on save button
@mira.route("/api/settings", methods=["POST"])
def persist_settings():
    data = request.get_json()
    save_settings(data)
    # refresh plugs
    load_plugs_from_db()
    print("[Settings modal] Saved.")
    return jsonify({"status": "ok"})

########################################################################################
"""#########################  Attachment&BrowserPlugin ##############################"""
########################################################################################
# receiving from picture.js (phone camera)
@mira.route('/picture', methods=['POST'])
def picture():
    picture_path = BASE_PATH / "temp" / "picture.jpeg"
    file = request.files.get('picture')
    file.save(picture_path)
    # Set global attachment state
    HasAttachment.set_attachment(True)
    HasAttachment.set_picture(True)

    # Notify frontend via Socket.IO
    socketio.emit('attachment_update', {
        "has_attachment": True,
        "type": "picture"
    })
    print(f"[Picture] Attached: {picture_path}")
    return "Picture received and ready", 200

"""
When we receive from the browser extension.
Can be one of text, link, picture.
"""
@mira.route('/receive', methods=['POST'])
def receive():
    data = request.get_json(silent=True) or {}
    print("[Receive] Payload from extension:", data)

    payload_type = data.get("type")
    content = data.get("content", "").strip()
    print("[Receive] Content:", content, "\nAs type:", payload_type)

    # IMAGE
    if payload_type == "image_blob" and content:
        picture_path = BASE_PATH / "temp" / "picture.jpeg"
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
            HasAttachment.set_attachment(True)
            HasAttachment.set_picture(True)

            # notify frontend
            socketio.emit('attachment_update', {
                "has_attachment": True,
                "type": "picture"
            })
            return jsonify({"status": "ok", "attachment": True}), 200

        # Extension uses Chromium's native picture copy, which should be pretty reliable, still:
        except Exception as e:
            print(f"[Receive] Failed to process image_blob: {type(e).__name__}: {e}")
            return jsonify({"status": "error", "message": "Invalid image data"}), 400

    # PAGE / LINK
    if payload_type in ("page", "link") and content:
        print(f"[Receive] Saving {payload_type}: {content}")
        save_url_text(content) # writes to output.txt
        HasAttachment.set_attachment(True)
        socketio.emit('attachment_update', {"has_attachment": True, "type": payload_type})
        return jsonify({"status": "ok", "attachment": True}), 200

    # TEXT SELECTION
    if payload_type == "selection" and content:
        txt_path = BASE_PATH / "temp" / "output.txt"
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"[Receive] Text selection saved ({len(content)} chars) → {txt_path}")
        HasAttachment.set_attachment(True)
        socketio.emit('attachment_update', {"has_attachment": True, "type": "selection"})
        return jsonify({"status": "ok", "attachment": True}), 200

    return jsonify({"status": "ignored"}), 200 # Can't actually happen but PyCharm will complain

"""
Receiving upload through frontend button.
Check against services/config.py FileSupport.
"""
@mira.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"status": "no file received"}), 400

    # Check if file type is supported
    file = request.files["file"]
    filename_path = Path(file.filename)
    if not FileSupport.is_supported(filename_path):
        return jsonify({"status": "unsupported file type"}), 415

    # Save the uploaded file to disk
    upload_path = BASE_PATH / "temp" / file.filename
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    file.save(upload_path)

    # Decide how to process based on type
    ext = filename_path.suffix.lower()
    if ext in FileSupport.IMAGE_EXTENSIONS:
        picture_path = BASE_PATH / "temp" / "picture.jpeg"
        # Open and convert to JPEG
        with Image.open(upload_path) as img:
            # Ensure compatibility with JPEG (no alpha channel, no palette)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(picture_path, format="JPEG", quality=90)

        print(f"[Upload] Converted image to JPEG: {picture_path}")
        HasAttachment.set_picture(True)
    else:
        file_to_txt(upload_path)
        print(f"[Upload] Received file: {file.filename}")

    HasAttachment.set_attachment(True)

    # Cleanup: remove the original uploaded file
    try:
        upload_path.unlink()
        print(f"[Upload] Removed original file: {upload_path}")
    except Exception as e:
        print(f"[Upload] Cleanup failed: {e}")

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
    items = request.get_json()
    shopping_list_path = BASE_PATH / "static" / "lists" / "shopping_list.json"
    # Write the updated list back to the file
    with open(shopping_list_path, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    return jsonify(items), 200

# persist frontend edits to to-do list
@mira.route('/save_todo_list', methods=['POST'])
def save_todo_list():
    todo_list_path = BASE_PATH / "static" / "lists" / "to_do_list.json"
    items = request.get_json()
    # Write the updated list back to the file
    with open(todo_list_path, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    return jsonify(items), 200

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
        
ChatState is global, so the piping is simpler = 
    - tunnel into all three (hardcode, intent, chat) for each complete object.
    - dont have to constantly convert data when passing from front- to backend.
"""
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
        return jsonify({"reply": "No hardcode detected"}) # frontend dives into /intent

@mira.route("/intent", methods=["POST"])
def intent():
    user_msg = ChatState.user_msg or ""
    # Bypass if hardcode already set intent to chat
    if ChatState.intent and isinstance(ChatState.intent, dict) and ChatState.intent.get("intent") == "chat":
        print("[Intent] Detected chat, bypassing.")
        return jsonify({"reply": "Bypass intent"})

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
                            ChatState.weather = ask_weather(user_msg)
                            print(f"[Intent] Determined weather: {ChatState.weather}")
                            # mark as bypass so frontend continues into /chat
                            return jsonify({"reply": "Bypass intent"})
                        else:
                            if command_lookup(command, user_msg): commands.append(command)
                            else: print(f"[Intent] Ignored invalid command: {command}")
                    elif intent_type == "chat":
                        ChatState.intent = item
            # If obj is a dict, iterate through its items
            elif isinstance(obj, dict):
                intents.append(obj)
                intent_type = obj.get("intent", "")
                command = obj.get("command", "")
                if intent_type == "action":
                    if command == "get weather":
                        ChatState.weather = ask_weather(user_msg)
                        print(f"[Intent] Determined weather: {ChatState.weather}")
                        # mark as bypass so frontend continues into /chat
                        return jsonify({"reply": "Bypass intent"})
                    else:
                        if command_lookup(command, user_msg): commands.append(command)
                        else: print(f"[Intent] Ignored invalid command: {command}")
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

# Chat route
@mira.route("/chat", methods=["POST"])
def chat():
    # Unique case (voice out but not chat)
    # So weather context doesn't taint the chat session
    if ChatState.weather:
        response = ChatState.weather
        ChatState.weather = None  # reset
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
            # Channel to VL if an image is attached
            # Small and probably even big VL models suck at longer text context
            if HasAttachment.has_attachment() and HasAttachment.is_picture():
                img_path = BASE_PATH / "temp" / "picture.jpeg"
                print(f"[VL] Reading attachment...")
                assistant_reply = image_inference(img_path, user_msg)
                HasAttachment.clear() # both is picture and attachment
                socketio.emit('attachment_update', {
                    "has_attachment": False,
                    "type": "consumed"
                })
                return jsonify({"reply": assistant_reply})

            # Channel to txt model if we've converted an allowed input into .txt
            elif HasAttachment.has_attachment():
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
                # Is just regular chat without attachment = continue
                combined_input = user_msg

            # Pass to txt LLM
            assistant_reply = ChatContext.chat_session.ask(combined_input)

        except Exception as e:
            print(f"[Chat] Error: {e}")
            assistant_reply = "Error processing message."

        return jsonify({"reply": assistant_reply})

    else:
        # Action intents already handled in /intent
        # Front end doesn't analyze. It just tunnels into all three routes, so we need this last else.
        return jsonify({"reply": ""})

@mira.route("/new_chat", methods=["POST"])
def new_chat():
    ChatContext.chat_session = ChatSession()
    HasAttachment.set_attachment(False)
    print("[Chat] Started new chat session")
    return jsonify({"status": "new session started"})

########################################################################################
"""############################         Voice          ##############################"""
########################################################################################
# TODO: Should migrate to using socket.io.js to notify the front end of a chunk to play.
#   - Frontend needs to have a playback bucket that it plays until empty (chunk generation is faster than voice playback).

# determine voice chunk amount
# Reasons to chunk: 1) Latency (how quickly the app can respond) 2) model restrictions
@mira.route("/voice_chunks", methods=["POST"])
def get_chunk_count():
    # first return to the frontend how many chunks to expect, so that we don't constantly need to poll.
    text = request.json.get("text", "")
    clean_voice_chunks()
    # Apply unique naming scheme with timestamp because mobile browsers will use stale data and not update the files.
    timestamp, chunks = split_into_chunks(text)
    return jsonify({ #Frontend tunnels back into route /voice_out
        "count": len(chunks),
        "timestamp": timestamp
    })

@mira.route("/voice_out", methods=["POST"])
def synth():
    # re-extract
    data = request.json
    text = data.get("text", "")
    timestamp = data.get("timestamp") # ("%Y%m%d%H%M%S%f")

    try:
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
    # Convert to WAV for Vosk (mono, 16kHz, 16-bit PCM)
    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", str(webm_path),
            "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav_path)
        ], check=True)
    except subprocess.CalledProcessError as e:
        print(f"[FFmpeg] WAV conversion failed: {e}")
        return jsonify({"error": "Audio conversion failed"}), 500

    # Transcribe the WAV using Vosk
    result = transcribe_audio(wav_path)

    return jsonify({ "transcript": result["text"] })

########################################################################################
"""############################       Nutrition        ##############################"""
########################################################################################
# when we've made a picture of a barcode
@mira.route('/nutrition/scan/', methods=['POST'])
def receive_barcode_image():
    image_path = BASE_PATH / "temp" / "barcode.jpeg"
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
    data = request.get_json() # Frontend sends valid json
    persist_nutri_item(data) # Write to DB
    print(f"[Nutrition] Received scanned product: {data['product_name']} ({data['barcode']})")
    return jsonify({"message": "Product received successfully"}), 200 # Frontend tunnels back into route nutrition/log

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
    data = request.get_json() # Frontend sends valid json
    persist_nutrition_intake(data) # Write to DB
    print(f"[Nutrition] Logged intake: {data['product_name']}: "
          f"{data['kcal_consumed']}kcal, {data['protein_consumed']}g protein")
    return jsonify({"message": "Intake logged successfully"}), 200 # frontend returns to input ready state

# when we enter daily nutri intake
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
    data = request.get_json(silent=True) or []
    if not isinstance(data, list):
        return jsonify({"error": "Expected a list of items"}), 400
    success = update_today_consumed_items(data)
    if success:
        return jsonify({"status": "ok"})
    else:
        return jsonify({"error": "Failed to update database"}), 500

# when the user searches for food items
@mira.route('/nutrition/search', methods=['GET'])
def nutrition_search():
    # Returns LocalDB as most salient, FoundationFoods next, and then BrandedFoods.
    query = request.args.get('q', '').strip()
    # only begin live search at three letters entered.
    if not query or len(query) < 3:
        return jsonify([])

    items = food_search(query)
    if items: print(f"[Nutrition] Returned search result")
    return jsonify(items)

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
        return redirect(url_for('index'))
    print("[Login] Refused.")
    return jsonify({"error": "Unauthorized"}), 403

# check user authentication
@mira.before_request
def check_access():
    # Allow static, login, and /receive from localhost (for browser extension)
    if request.path.startswith("/static/") or request.path == "/login" or \
       (request.path == "/receive" and request.remote_addr in ["127.0.0.1", "::1"]):
        print(f"[BeforeRequest] Allowed: {request.path} from {request.remote_addr}")
        return None

    if session.get('authenticated'):
        #print("[BeforeRequest] Authenticated.")
        return None

    print("[BeforeRequest] Refused unauthorized access.")
    return jsonify({"error": "Unauthorized"}), 403

# socket event handler
@socketio.on('get_attachment_status')
def handle_attachment_status():
    emit('attachment_status', {
        "has_attachment": HasAttachment.has_attachment()
    })

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
    ssl_context = (cert, key)
    socketio.run(mira, debug=True, use_reloader=False, host='0.0.0.0', port=5001, ssl_context=ssl_context, allow_unsafe_werkzeug=True)

# local network for browser addon and for the cloudflare tunnel
# tunnel explodes if it has to deal with https from this end
# sudo systemctl daemon-reload
# sudo systemctl restart cloudflared-mira-tunnel
# journalctl -u cloudflared-mira-tunnel -f
def run_http_flask():
    # we need http for the Chromium extension and for the cloudflare tunnel
    socketio.run(mira, debug=True, use_reloader=False, host='0.0.0.0', port=5002, allow_unsafe_werkzeug=True)

# this is the window that opens on the host for people who have a non-dockerized install
# untested for wayland
def set_qt_identity():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])  # fallback if not yet created
    app.setApplicationName("Mira")
    app.setWindowIcon(QtGui.QIcon("icon.png"))

if __name__ == '__main__':
    # Initial init
    init_db()
    check_mkcert()
    load_plugs_from_db()
    discover_playlists()
    # Start Flask
    # HTTPS server
    flask_thread = threading.Thread(target=run_https_flask, daemon=True)
    flask_thread.start()
    # HTTP server
    http_thread = threading.Thread(target=run_http_flask, daemon=True)
    http_thread.start()
    # Init text LLM and create a chat session
    init_qwen()
    ChatContext.chat_session = ChatSession()
    # Init TTS
    init_tts() # XTTS-v2
    get_vosk_model() # Vosk
    # Init VL LLM
    init_qwen_vl()
    # Only run the standalone window outside docker
    if os.getenv("IN_DOCKER", "").lower() != "true":
        # Launch WebView using Qt backend
        set_qt_identity()

        # Get the first allowed key
        first_key = next(iter(ALLOWED_KEYS))
        # Build the URL with the selected key and local ip
        local_ip = get_local_ip()
        url = f"https://{local_ip}:5001/login?token={first_key}"
        # actually create the window
        window = webview.create_window(
            "Mira",
            url,
            width=400,
            height=600,
            resizable=True, # This one and frameless conflict for me.
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
    else:
        print("[Docker] GUI disabled, Flask servers only.")
        # keep alive so docker doesn't exit with code 0
        stop_event = threading.Event()
        try:
            print("Container running. Press CTRL+C to exit.")
            stop_event.wait()
        except KeyboardInterrupt:
            print("Shutting down container...")

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

    # Transcribe the MP3 instead of the original webm
    #transcriber = WhisperTranscriber()
    #result = transcriber.transcribe_audio(mp3_path)
    """