import uuid

from flask import Flask, jsonify, request, send_from_directory

from chatbot import chat_turn, new_conversation

app = Flask(__name__, static_folder=None)

# 브라우저(세션 id)별 대화 기록 — 로컬 데모용 메모리 저장
conversations = {}


@app.route("/")
def index():
    return send_from_directory(app.root_path, "index.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    text = (data.get("message") or "").strip()
    if not text:
        return jsonify(error="메시지를 입력하세요."), 400

    sid = data.get("session_id") or str(uuid.uuid4())
    messages = conversations.setdefault(sid, new_conversation())
    try:
        reply = chat_turn(messages, text)
    except Exception as e:
        return jsonify(error=f"답변 실패: {e}", session_id=sid), 500
    return jsonify(reply=reply, session_id=sid)


@app.route("/api/reset", methods=["POST"])
def reset():
    conversations.pop((request.get_json(silent=True) or {}).get("session_id"), None)
    return jsonify(ok=True)


if __name__ == "__main__":
    # 로컬 전용(127.0.0.1). 외부 공개 시 인증/HTTPS 추가 필요
    app.run(host="127.0.0.1", port=5000, debug=False)

