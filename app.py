<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8" />
  <title>音声録音テスト</title>
</head>
<body>
  <h2>音声録音デモ</h2>
  <button id="startBtn">🎤 録音開始</button>
  <button id="stopBtn" disabled>⏹️ 録音停止</button>
  <p id="status"></p>

  <script>
    const SERVER = "https://customer60-home-mvp.onrender.com"; 
    let mediaRecorder;
    let audioChunks = [];

    const startBtn = document.getElementById("startBtn");
    const stopBtn = document.getElementById("stopBtn");
    const status = document.getElementById("status");

    // 録音開始
    startBtn.onclick = async () => {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder = new MediaRecorder(stream);

      mediaRecorder.ondataavailable = e => {
        if (e.data.size > 0) audioChunks.push(e.data);
      };

      mediaRecorder.onstop = async () => {
        const blob = new Blob(audioChunks, { type: "audio/webm" });
        const formData = new FormData();
        formData.append("file", blob, "recording.webm");

        status.textContent = "⏳ サーバーに送信中…";

        try {
          const res = await fetch(`${SERVER}/analyze`, {   // ← 修正済み
            method: "POST",
            body: formData
          });
          const data = await res.json();
          status.textContent = "✅ テキスト: " + data.text + "\n結果: " + data.result;
        } catch (err) {
          status.textContent = "❌ エラー: " + err.message;
        }

        audioChunks = [];
      };

      mediaRecorder.start();
      startBtn.disabled = true;
      stopBtn.disabled = false;
      status.textContent = "🎙️ 録音中…";
    };

    // 録音停止
    stopBtn.onclick = () => {
      mediaRecorder.stop();
      startBtn.disabled = false;
      stopBtn.disabled = true;
      status.textContent = "🛑 録音停止";
    };
  </script>
</body>
</html>

