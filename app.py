from flask import Flask, request, jsonify, send_from_directory
import requests
import csv
import io
import time
import threading
import os

app = Flask(__name__)

BASE_URL = "https://waba.360dialog.io/v1/messages"

# بيانات API - Ahmed بيحطها من واجهة التطبيق
api_config = {
    "api_key": "",
    "phone_number_id": ""
}

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
        api_config["api_key"]        = data.get('api_key', '')
        api_config["phone_number_id"] = data.get('phone_number_id', '')
        return jsonify({"status": "ok"})
    return jsonify({
        "api_key": api_config["api_key"][:6] + "***" if api_config["api_key"] else "",
        "phone_number_id": api_config["phone_number_id"]
    })

@app.route('/send', methods=['POST'])
def send():
    global progress_data
    if progress_data["running"]:
        return jsonify({"error": "إرسال جاري بالفعل"}), 400

    data       = request.json
    msg_text   = data.get("message_text", "")
    image_url  = data.get("image_url", "")
    link_url   = data.get("link_url", "")
    link_text  = data.get("link_text", "")
    numbers    = data.get("numbers", [])

    if not numbers or not msg_text:
        return jsonify({"error": "بيانات ناقصة"}), 400

    if not api_config["api_key"]:
        return jsonify({"error": "من فضلك أدخل API Key أولاً"}), 400

    progress_data = {
        "total": len(numbers), "done": 0,
        "success": 0, "fail": 0,
        "log": [], "running": True
    }

    def run():
        headers = {
            "D360-API-KEY": api_config["api_key"],
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
