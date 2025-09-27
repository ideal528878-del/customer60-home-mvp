# app.py
import io
import json
import os
from typing import Any, Dict

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from werkzeug.datastructures import FileStorage

# OpenAI Python SDK v1 系（requirements.txt の openai==1.x と整合）
from openai import OpenAI
from pydantic import BaseModel, Field

# =========================
# Flask 基本セットアップ
# =========================
app = Flask(__name__, static_folder="static", static_url_path="/static")
CORS(app)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20MB まで受け付け

# Gunicorn の Procfile は `web: gunicorn app:app --workers 1 --threads 4 --timeout 120`
# なので、Flask インスタンス名は必ず `app` にしておくこと

# =========================
# OpenAI クライアント
# =========================
# 環境変数 OPENAI_API_KEY は Render のダッシュボードで設定済みの想定
client = OpenAI()  # 自動で env の OPENAI_API_KEY を参照

# =========================
# Pydantic スキーマ（採点JSONの形を固定化）
# =========================
class ScoreDetail(BaseModel):
    clarity: int = Field(..., ge=1, le=5)
    politeness: int = Field(..., ge=1, le=5)
    speed: int = Field(..., ge=1, le=5)
    empathy: int = Field(..., ge=1, le=5)

class ScoreResult(BaseModel):
    total: int = Field(..., ge=0, le=100)
    detail: ScoreDetail
    feedback: str

# =========================
# Util: 安全な JSON パース（モデル検証込み）
# =========================
def parse_score_json(text: str) -> Dict[str, Any]:
    """
    GPT からの出力（JSON文字列想定）を dict 化してバリデーション。
    失敗時は簡易フォールバック。
    """
    try:
        data = json.loads(text)
        validated = ScoreResult(**data)
        return json.loads(validated.model_dump_json())
    except Exception:
        # フォールバック（最低限の形で返す）
        return {
            "total": 0,
            "detail": {"clarity": 1, "politeness": 1, "speed": 1, "empathy": 1},
            "feedback": "JSON解析に失敗しました。プロンプト/出力形式を見直してください。"
        }

# =========================
# ルート: HTML を返す（※HTMLは app.py にベタ書きしない）
# =========================
@app.route("/")
def root() -> Any:
    # static/index.html を配信（HTML/JS は必ず別ファイルに分離）
    return send_from_directory("static", "index.html")

@app.route("/health")
def health() -> Any:
    return "ok", 200

# =========================
# /analyze: 音声受け取り → Whisper → GPT 採点 → JSON
# =========================
@app.route("/analyze", methods=["POST"])
def analyze() -> Any:
    # 1) 音声の存在チェック
    if "audio" not in request.files:
        return jsonify({"error": "audio file missing"}), 400

    audio_file: FileStorage = request.files["audio"]

    # 2) Whisper による文字起こし（OpenAI API / whisper-1）
    #    FileStorage はそのまま file= に渡せます。念のためストリーム位置を先頭に。
    try:
        audio_file.stream.seek(0)
        transcript_resp = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,  # FileStorage を直接渡す
            # language="ja",  # 必要に応じて固定（自動判定に任せるなら省略）
        )
        # SDK v1 系は .text で取り出せる
        transcript_text: str = transcript_resp.text if hasattr(transcript_resp, "text") else str(transcript_resp)
    except Exception as e:
        return jsonify({"error": "transcription failed", "detail": str(e)}), 500

    # 3) GPT に採点を依頼（JSON で返すよう強制）
    system_prompt = (
        "あなたは接客の採点アシスタントです。"
        "与えられた発話内容を、以下のJSONスキーマに沿って厳密に採点し、純粋なJSONだけを返してください。"
        "余計な文章や説明は一切出力しないでください。"
        "\n\n"
        "JSONスキーマ:\n"
        "{\n"
        '  "total": 0〜100 の整数,\n'
        '  "detail": {\n'
        '    "clarity": 1〜5 の整数,\n'
        '    "politeness": 1〜5 の整数,\n'
        '    "speed": 1〜5 の整数,\n'
        '    "empathy": 1〜5 の整数\n'
        "  },\n"
        '  "feedback": "改善アドバイス（日本語・200字以内）"\n'
        "}\n"
        "\n"
        "採点観点:\n"
        "- clarity: 聞き取りやすさ、要点の明確さ\n"
        "- politeness: 丁寧さ、敬語の適切さ\n"
        "- speed: 話速の適切さ（早過ぎ/遅過ぎの回避）\n"
        "- empathy: 共感や気遣いが感じられるか\n"
        "\n"
        "返答は**JSON文字列のみ**。コードブロックや前置き・後置きは不要。"
    )

    user_prompt = (
        "以下が文字起こし結果です。これを採点してください。\n\n"
        f"--- TRANSCRIPT START ---\n{transcript_text}\n--- TRANSCRIPT END ---"
    )

    try:
        chat = client.chat.completions.create(
            model="gpt-4o-mini",  # コスト軽めのモデル例。必要に応じて変更可
            temperature=0.2,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw_text = chat.choices[0].message.content.strip()
        score_json = parse_score_json(raw_text)
    except Exception as e:
        return jsonify({"error": "scoring failed", "detail": str(e)}), 500

    # 4) 応答を統合して返す
    return jsonify(
        {
            "ok": True,
            "transcript": transcript_text,
            "score": score_json,
        }
    ), 200


# =========================
# 直接起動（ローカル確認用）
# =========================
if __name__ == "__main__":
    # Render 本番は gunicorn で起動されるためここは通らない想定
    # ローカルで動かす場合は:
    #   export OPENAI_API_KEY=xxxxx
    #   python app.py
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=True)

