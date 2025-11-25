let mediaRecorder;
let audioChunks = [];
let isRecording = false;
let touchTriggered = false;
let recordingStartTime = null;

const chatForm = document.getElementById('chat-form');
const input = document.getElementById('user-input');
const submitButton = chatForm.querySelector('button');

// Desktop: start recording
submitButton.addEventListener('mousedown', async e => {
  if (touchTriggered) return;
  await startRecording();
});

// Desktop: stop recording
submitButton.addEventListener('mouseup', async e => {
  if (touchTriggered) return;
  await stopRecording();
});

// Mobile: start recording
async function requestMicPermission() {
  try {
    const permissionStatus = await navigator.permissions.query({ name: 'microphone' });

    if (permissionStatus.state === 'granted') {
      return true;
    } else if (permissionStatus.state === 'prompt') {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      return true;
    }
    return false;
  } catch (err) {
    console.error("Permission check failed:", err);
    return false;
  }
}

// Modify event listeners
submitButton.addEventListener('touchstart', async e => {
  const hasPermission = await requestMicPermission();
  if (hasPermission) {
    touchTriggered = true;
    await startRecording();
  } else {
    alert("Microphone permission is required");
  }
});

// Mobile: stop recording
submitButton.addEventListener('touchend', async e => {
  await stopRecording();
  touchTriggered = false;
});

async function startRecording() {
  try {
    recordingStartTime = Date.now();
    // Explicitly request permissions with more details
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true
      }
    });

    // Add permission check
    if (!stream.getAudioTracks().length) {
      console.error("No audio tracks available");
      return;
    }

    mediaRecorder = new MediaRecorder(stream, {
      mimeType: 'audio/webm'
    });
    audioChunks = [];
    isRecording = true;

    mediaRecorder.ondataavailable = e => {
      if (e.data.size > 0) {
        audioChunks.push(e.data);
      }
    };
    mediaRecorder.start();
  } catch (err) {
    console.error("Mic access failed:", err);
    // Provide user-friendly error handling
    alert("Microphone access denied. Please check browser permissions.");
  }
}

async function stopRecording() {
  if (!isRecording || !mediaRecorder || mediaRecorder.state !== 'recording') return;

  mediaRecorder.stop();
  isRecording = false;

  const recordingEndTime = Date.now();
  const duration = recordingEndTime - recordingStartTime;

  if (duration < 500) {
    console.warn(`Recording too short (${duration}ms), discarding.`);
    return;
  }

  mediaRecorder.onstop = async () => {
    const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
    const formData = new FormData();
    formData.append('audio', audioBlob, 'recording.webm');

    try {
      const res = await fetch('/upload_audio', {
        method: 'POST',
        body: formData
      });
      const data = await res.json();
      const transcribedText = data.transcript;

      if (transcribedText) {
        input.value = transcribedText;
        chatForm.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
      }
    } catch (err) {
      console.error("Audio upload failed:", err);
    }
  };
}

// Submit handler
chatForm.addEventListener('submit', async e => {
  e.preventDefault();
  const userText = input.value.trim();
  if (!userText) return;

  addMessage(userText, 'user');
  input.value = '';
  input.disabled = true;

  try {
    const response = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: userText })
    });
    const data = await response.json();
    const reply = data.reply;

    addMessage(reply, 'assistant');

    if (reply.startsWith("Handled action:")) {
      playSuccess();
    } else if (reply === "Unknown intent" || reply.startsWith("Invalid intent")) {
      playFailure();
    } else {
      try {
        await streamVoice(reply);
      } catch (err) {
        console.warn("Streaming voice synthesis failed:", err);
      }
    }

  } catch (err) {
    console.error(err);
    addMessage('Sorry, something went wrong.', 'assistant');
  } finally {
    input.disabled = false;
    input.focus();
  }
});

// Helper to add a message bubble
function addMessage(text, role) {
  const container = document.getElementById('messages');
  const div = document.createElement('div');
  div.className = `message ${role}`;
  div.innerHTML = text.replace(/\n/g, '<br>');
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

async function streamVoice(text) {
  const countResponse = await fetch('/voice_chunks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text })
  });
  const { timestamp, count } = await countResponse.json();

  await fetch('/voice_out', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, timestamp })
  });

  for (let i = 1; i <= count; i++) {
    const path = `/static/temp/output_${i}_${timestamp}.wav`;
    const exists = await waitForFile(path, 3000, 100);

    if (exists) {
      const audio = new Audio(path);
      await new Promise(resolve => {
        audio.onended = () => {
          audio.remove();
          resolve();
        };
        audio.onerror = resolve;
        audio.play();
      });
    } else {
      console.warn(`Chunk ${i} not found in time`);
    }
  }
}

async function waitForFile(url, timeout = 3000, interval = 100, minSize = 1024) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    try {
      const res = await fetch(url, { method: 'HEAD' });
      if (res.ok) {
        const size = parseInt(res.headers.get("Content-Length") || "0", 10);
        if (size >= minSize) return true;
      }
    } catch {}
    await new Promise(r => setTimeout(r, interval));
  }
  return false;
}
