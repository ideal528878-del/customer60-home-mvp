# app.py（全体そのまま使える安全版）

from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from openai import OpenAI
import tempfile, os, traceback

app = Flask(__name__)
CORS(app)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="ja">
<head><meta charset="UTF-8"><title>音声採点デモ</title></head>
<body>
  <h2>録音して送信</h2>
  <button id="startBtn">録音開始</button>
  <button id="stopBtn" disabled>録音停止</button>
  <button id="sendBtn" disabled>サーバーへ送信</button>

  <p><strong>文字起こし:</strong></p>
  <pre id="transcript"></pre>

  <p><strong>採点結果:</strong></p>
  <pre id="result"></pre>

  <script>
    let mediaRecorder;
    let audioChunks = [];
    const startBtn = document.getElementById("startBtn");
    const stopBtn = document.getElementById("stopBtn");
    const sendBtn = document.getElementById("sendBtn");
    const transcriptEl = document.getElementById("transcript");
    const resultEl = document.getElementById("result");

    startBtn.onclick = async () => {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
      audioChunks = [];
      mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
      mediaRecorder.onstop = () => { sendBtn.disabled = false; };
      mediaRecorder.start();
      startBtn.disabled = true; stopBtn.disabled = false;
    };

    stopBtn.onclick = () => {
      mediaRecorder.stop();
      startBtn.disabled = false; stopBtn.disabled = true;
    };

    sendBtn.onclick = async () => {
      const blob = new Blob(audioChunks, { type: "audio/webm" });
      const arrayBuffer = await blob.arrayBuffer();
      const audioBuffer = await new AudioContext().decodeAudioData(arrayBuffer);

      const wavBuffer = encodeWAV(audioBuffer);
      const wavBlob = new Blob([wavBuffer], { type: "audio/wav" });
      const formData = new FormData();
      formData.append("file", wavBlob, "recording.wav");

      try {
        const res = await fetch("/analyze", { method: "POST", body: formData });
        // 失敗時はエラーテキストを表示する（HTMLが返ってきた場合の可視化）
        if (!res.ok) {
          const raw = await res.text();
          throw new Error(`HTTP ${res.status}: ${raw.substring(0,300)}`);
        }
        const data = await res.json();
        transcriptEl.textContent = data.text || "（文字起こしなし）";
        resultEl.textContent = data.result || JSON.stringify(data, null, 2);
      } catch (err) {
        resultEl.textContent = "エラー: " + err.message;
      }
    };

    function encodeWAV(audioBuffer) {
      const numOfChan = audioBuffer.numberOfChannels,
            length = audioBuffer.length * numOfChan * 2 + 44,
            buffer = new ArrayBuffer(length),
            view = new DataView(buffer),
            channels = [],
            sampleRate = audioBuffer.sampleRate;
      let offset = 0;

      function writeString(s) {
        for (let i = 0; i < s.length; i++) { view.setUint8(offset + i, s.charCodeAt(i)); }
        offset += s.length;
      }
      function floatTo16BitPCM(view, offset, input) {
        for (let i = 0; i < input.length; i++, offset += 2) {
          let s = Math.max(-1, Math.min(1, input[i]));
          view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
        }
      }

      writeString("RIFF"); view.setUint32(offset, 36 + audioBuffer.length * numOfChan * 2, true); offset += 4;
      writeString("WAVE");
      writeString("fmt "); view.setUint32(offset, 16, true); offset += 4;
      view.setUint16(offset, 1, true); offset += 2;
      view.setUint16(offset, numOfChan, true); offset += 2;
      view.setUint32(offset, sampleRate, true); offset += 4;
      view.setUint32(offset, sampleRate * numOfChan * 2, true); offset += 4;
      view.setUint16(offset, numOfChan * 2, true); offset += 2;
      view.setUint16(offset, 16, true); offset += 2;
      writeString("data"); view.setUint32(offset, audioBuffer.length * numOfChan * 2, true); offset += 4;

      for (let i = 0; i < numOfChan; i++) channels.push(audioBuffer.getChannelData(i));
      let interleaved = new Float32Array(audioBuffer.length * numOfChan);
      for (let i = 0; i < audioBuffer.length; i++) {
        for (let c = 0; c < numOfChan; c++) interleaved[i * numOfChan + c] = channels[c][i];
      }
      floatTo16BitPCM(view, offset, interleaved);
      return buffer;
    }
  </script>
</body>
</html>
"""

@app.route("/", methods=["GET"])
def index():
    return Response(HTML_PAGE, mimetype="text/html; charset=utf-8")

@app.get("/health")
def health():
    return "ok", 200

@app.route("/analyze", methods=["POST"])
def analyze():
    tmp_path = None
    try:
        if "file" not in request.files:
            return jsonify({"error": "no file"}), 400

        f = request.files["file"]
        # 一時ファイルへ保存
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            f.save(tmp.name)
            tmp_path = tmp.name

        # 1) Whisper で文字起こし
        with open(tmp_path, "rb") as media:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=media
            )
        text = getattr(transcript, "text", "") or ""

        # 2) GPT で採点
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

    except Exception as e:
        # 例外を JSON で返す（ブラウザが HTML を受けてしまう問題を防ぐ）
        return jsonify({
            "error": str(e),
            "trace": traceback.format_exc()
        }), 500
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
