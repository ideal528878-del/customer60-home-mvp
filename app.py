from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from openai import OpenAI
import tempfile, os

# Flask アプリ作成
app = Flask(__name__)
CORS(app)  # 他サイトからの呼び出し許可

# OpenAI クライアント
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 動作確認用エンドポイント
@app.route("/health")
def health():
    return "ok", 200

# メインの音声解析API
@app.route("/analyze", methods=["POST"])
def analyze():
    f = request.files["file"]  # フロントから届いた録音ファイル
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        f.save(tmp.name)
        # Whisperで文字起こし
        with open(tmp.name, "rb") as media:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=media
            )
    text = transcript.text or ""

    # 採点ルール
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

    # GPTで採点

