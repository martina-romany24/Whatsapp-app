from flask import Flask, request, jsonify, send_from_directory
import requests
import csv
import io
import time
import threading
import os
import json

app = Flask(__name__)

BASE_URL    = "https://waba.360dialog.io/v1/messages"
CONFIG_FILE = "/tmp/api_config.json"

def load_config():
    """Railway Variables أولوية دايماً، لو مفيش يرجع للملف"""
    # أولاً: Railway Variables
    api_key        = os.environ.get("API_KEY", "")
    phone_number_id = os.environ.get("PHONE_NUMBER_ID", "")

    # لو مفيش Variables، ارجع للملف المؤقت
    if not api_key and os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                saved = json.load(f)
                api_key        = saved.get("api_key", "")
                phone_number_id = saved.get("phone_number_id", "")
        except:
            pass

    return {"api_key": api_key, "phone_number_id": phone_number_id}

def save_config(api_key, phone_number_id):
    """حفظ في الملف المؤقت فقط لو مفيش Railway Variables"""
    if not os.environ.get("API_KEY"):
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump({"api_key": api_key, "phone_number_id": phone_number_id}, f)
        except:
            pass

progress_data = {
    "total": 0, "done": 0,
    "success": 0, "fail": 0,
    "log": [], "running": False
}

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/config', methods=['GET', 'POST'])
def config():
    if request.method == 'POST':
        data = request.json
        save_config(data.get('api_key', ''), data.get('phone_number_id', ''))
        return jsonify({"status": "ok"})
    cfg = load_config()
    return jsonify({
        "api_key":        cfg["api_key"][:6] + "***" if cfg["api_key"] else "",
        "phone_number_id": cfg["phone_number_id"],
        "configured":     bool(cfg["api_key"])
    })

@app.route('/send', methods=['POST'])
def send():
    global progress_data
    if progress_data["running"]:
        return jsonify({"error": "إرسال جاري بالفعل"}), 400

    cfg = load_config()
    if not cfg["api_key"]:
        return jsonify({"error": "من فضلك أدخل API Key أولاً"}), 400

    data      = request.json
    msg_text  = data.get("message_text", "")
    image_url = data.get("image_url", "")
    link_url  = data.get("link_url", "")
    link_text = data.get("link_text", "")
    numbers   = data.get("numbers", [])

    if not numbers or not msg_text:
        return jsonify({"error": "بيانات ناقصة"}), 400

    progress_data = {
        "total": len(numbers), "done": 0,
        "success": 0, "fail": 0,
        "log": [], "running": True
    }

    def run():
        headers = {
            "D360-API-KEY": cfg["api_key"],
            "Content-Type": "application/json"
        }
        for phone in numbers:
            try:
                if image_url:
                    payload = {
                        "messaging_product": "whatsapp", "to": phone,
                        "type": "image",
                        "image": {"link": image_url, "caption": msg_text}
                    }
                else:
                    full_text = msg_text
                    if link_url:
                        full_text += f"\n\n🔗 {link_text + ': ' if link_text else ''}{link_url}"
                    payload = {
                        "messaging_product": "whatsapp", "to": phone,
                        "type": "text", "text": {"body": full_text}
                    }

                resp = requests.post(BASE_URL, headers=headers, json=payload).json()

                if resp.get("messages"):
                    progress_data["success"] += 1
                    progress_data["log"].append(f"✅ {phone}")
                else:
                    err = resp.get("meta", {}).get("developer_message", "خطأ غير معروف")
                    progress_data["fail"] += 1
                    progress_data["log"].append(f"❌ {phone} - {err}")

            except Exception as e:
                progress_data["fail"] += 1
                progress_data["log"].append(f"❌ {phone} - {str(e)}")

            progress_data["done"] += 1
            time.sleep(2)

        progress_data["running"] = False

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"status": "started"})

@app.route('/progress')
def progress():
    return jsonify(progress_data)

@app.route('/parse-csv', methods=['POST'])
def parse_csv():
    file = request.files.get('file')
    if not file:
        return jsonify({"numbers": []})
    content = file.read().decode('utf-8-sig', errors='ignore')
    reader  = csv.DictReader(io.StringIO(content))
    numbers = []
    for row in reader:
        phone = (row.get('phone') or row.get('Phone') or list(row.values())[0] or '').strip()
        phone = phone.replace('+', '').replace(' ', '')
        if phone and phone.isdigit() and 7 <= len(phone) <= 15:
            numbers.append(phone)
    return jsonify({"numbers": numbers, "count": len(numbers)})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
