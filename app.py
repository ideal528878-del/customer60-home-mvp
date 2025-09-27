from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import tempfile, os

app = Flask(__name__)
CORS(app)  # CORS=他サイト(例:CodePen)からの呼び出し許可
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))  # APIキーは環境変数から取得

@app.route("/analyze", methods=["POST"])
def analyze():
    # 1) フロントから録音ファイルを受け取る
    f = request.files["file"]
    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
        f.save(tmp.name)
        # Whisperで文字起こし
        with open(tmp.name, "rb") as media:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=media
            )
    text = transcript.text or ""

    # 2) GPTで6項目採点（JSON形式で返すよう指示）
    rubric = """
項目は以下の6つ:
1: 提案の許可
2: ニーズを聴く
3: PREP法
4: ご注文のお礼
5: お届け時のお礼
6: 次に繋げる一言

必ず次のJSON形式で出力:
{
 "scores": {"1":"◯/×/△","2":"◯/×/△","3":"◯/×/△","4":"◯/×/△","5":"◯/×/△","6":"◯/×/△"},
 "evidence": {"1":"根拠抜粋","2":"...","3":"...","4":"...","5":"...","6":"..."},
 "improvements": ["改善点1","改善点2","改善点3"]
}
"""
    chat = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "あなたは厳格で公平な検定官です。"},
            {"role": "user", "content": f"次の発話を採点してください。\n{rubric}\n---\n発話:\n{text}"}
        ]
    )
    result_text = chat.choices[0].message.content

    return jsonify({"text": text, "result": result_text})

# 動作確認用エンドポイント
@app.route("/health", methods=["GET"])
def health():
    return "ok", 200

if __name__ == "__main__":
    # ローカル

