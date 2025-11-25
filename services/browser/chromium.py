# services.browser.chromium.py

import subprocess
#from pdfminer.high_level import extract_text
from PyQt6.QtDBus import QDBusConnection
#from services.db_access import BASE

_chromium_process = None

def _dbus_available() -> bool:
    try:
        bus = QDBusConnection.sessionBus()
        return bus.isConnected()
    except Exception:
        return False

def chromium_start(url: str = "about:blank"):
    global _chromium_process
    try:
        if _chromium_process is None or _chromium_process.poll() is not None:
            # prefer "chromium" but some systems use "chromium-browser"
            exe = "chromium"
            try:
                _chromium_process = subprocess.Popen([exe, url])
            except FileNotFoundError:
                exe = "chromium-browser"
                _chromium_process = subprocess.Popen([exe, url])
            print(f"[Browser] {exe} started with {url}.")
        else:
            print("[Browser] Chromium already running.")
        if not _dbus_available():
            print("[Browser] Qt DBus session not available.")
        return _chromium_process
    except Exception as e:
        print(f"[Error] Failed to start Chromium: {e}")
        return None

def chromium_terminate():
    global _chromium_process
    try:
        if _chromium_process and _chromium_process.poll() is None:
            _chromium_process.terminate()
            _chromium_process.wait(timeout=5)
            print("[Browser] Chromium terminated.")
            _chromium_process = None
    except Exception as e:
        print(f"[Error] Failed to terminate Chromium: {e}")

# hopefully deprecated
"""
def chromium_print(data):
    url = data.get("content")
    if not url or not isinstance(url, str):
        print("[Print] Invalid URL")
        return None

    output_pdf = BASE / "temp" / "chromium_print.pdf"
    output_txt = output_pdf.with_suffix(".txt")

    for exe in ["chromium", "chromium-browser"]:
        try:
            subprocess.run([
                exe,
                "--headless",
                f"--print-to-pdf={output_pdf}",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-extensions",
                "--disable-javascript",
                "--disable-popup-blocking",
                "--disable-translate",
                "--disable-sync",
                "--disable-background-networking",
                "--disable-default-apps",
                "--run-all-compositor-stages-before-draw",
                "--virtual-time-budget=10000",
                "--print-to-pdf-no-header",
                "--emulate-media=print",
                url
            ], check=True)

            print(f"[Print] PDF saved to {output_pdf}")

            # Extract and save text using pdfminer.six
            try:
                if "wikipedia" in url:
                    text = extract_text(str(output_pdf), page_numbers=[0, 1])
                    output_txt.write_text(text, encoding="utf-8")
                    print(f"[Extract] First two pages saved to {output_txt}")
                    return text
                else:
                    text = extract_text(str(output_pdf))
                    output_txt.write_text(text, encoding="utf-8")
                    print(f"[Extract] Text saved to {output_txt}")
                    return text

            except Exception as e:
                print(f"[Extract] Failed to extract text: {e}")
                return None

        except FileNotFoundError:
            continue
        except subprocess.CalledProcessError as e:
            print(f"[Print] Chromium failed: {e}")
            return None

    print("[Print] Chromium executable not found")
    return None
"""