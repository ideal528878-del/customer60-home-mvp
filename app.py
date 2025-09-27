from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import tempfile, os, traceback

app = Flask(__name__)
CORS(app)  # CodePen 等からの呼び出し許可

# OpenAI クライアント（環境変数 OPENAI_API_KEY を利用）
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.route("/", methods=["GET"])
def index():
    return "ok", 200

@app.route("/health", methods=["GET"])
def health():
    return "ok", 200

@app.route("/analyze", methods=["POST"])
def analyze():
    """
    CodePen からの FormData(file=録音blob) を受け取り、
    1) Whisper で文字起こし
    2) LLM で6項目採点
    を行い JSON で返す。
    """
    try:
        if "file" not in request.files:
            return jsonify({"error": "file フィールドがありません"}), 400

        f = request.files["file"]

        # 一時ファイルに保存して Whisper へ
        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
            f.save(tmp.name)
            with open(tmp.name, "rb") as media:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=media
                )
        text = (getattr(transcript, "text", None) or "").strip()

        rubric = (
            "項目は以下の6つ:\n"
            "1: 提案の許可\n"
            "2: ニーズを聴く\n"
            "3: PREP法\n"
            "4: ご注文のお礼\n"
            "5: お届け時のお礼\n"
            "6: 次に繋げる一言\n"
            "\n"
            "必ず次のJSON形式で出力:\n"
            "{\n"
            ' "scores": {"1":"◯/×/△","2":"◯/×/△","3":"◯/×/△","4":"◯/×/△","5":"◯/×/△","6":"◯/×/△"},\n'
            ' "evidence": {"1":"根拠抜粋","2":"...","3":"...","4":"...","5":"...","6":"..."},\n'
            ' "improvements": ["改善点1","改善点2","改善点3"]\n'
            "}\n"
        )

        chat = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "あなたは厳格で公平な検定官です。"},
                {"role": "user", "content": f"次の発話を採点してください。\n{rubric}\n---\n発話:\n{text}"}
            ]
        )
        result_text = chat.choices[0].message.content

        return jsonify({"text": text, "result": result_text}), 200

    except Exception as e:
        # 例外はログに出しつつ、フロントにメッセージを返す
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # ローカル開発用（Render 本番では gunicorn 起動）
    app.run(host="0.0.0.0", port=5000)
