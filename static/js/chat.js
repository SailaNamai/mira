let mediaRecorder;

let isRecording = false;
let touchTriggered = false;
let recordingStartTime = null;

let voiceChunkQueue = [];
let isPlayingVoice = false;
const voiceChunkBuffer = {}; // {user_id: {chunks: [], currentPlaying: null}}

const chatForm = document.getElementById('chat-form');
const input = document.getElementById('user-input');
const submitButton = chatForm.querySelector('button');

/////////////////////////////////////////////////////////////////
// Voice-out: Socketio receiver bucket
/////////////////////////////////////////////////////////////////
// Socket.IO event listeners for voice chunks
socket.on('voice_chunk_ready', (data) => {
    console.log('[Voice] Chunk ready:', data);

    const { user_id, chunk_index, total_chunks, audio_url, text } = data;

    // Create buffer for this user if it doesn't exist
    if (!voiceChunkBuffer[user_id]) {
        voiceChunkBuffer[user_id] = {
            chunks: [],
            currentPlaying: null,
            totalExpected: total_chunks
        };
    }

    // Add chunk to buffer (sorted by index)
    voiceChunkBuffer[user_id].chunks.push({
        index: chunk_index,
        url: audio_url,
        text: text
    });

    // Sort chunks by index to ensure proper order
    voiceChunkBuffer[user_id].chunks.sort((a, b) => a.index - b.index);

    // If we're not currently playing and this is the first chunk (or we have all chunks), start playing
    if (!isPlayingVoice && voiceChunkBuffer[user_id].chunks.length > 0) {
        playNextVoiceChunk(user_id);
    }
});

socket.on('voice_synthesis_complete', (data) => {
    console.log('[Voice] Synthesis complete:', data);
    const { user_id, total_chunks } = data;

    if (voiceChunkBuffer[user_id]) {
        voiceChunkBuffer[user_id].totalExpected = total_chunks;

        // If we have all chunks but weren't playing (maybe first chunk arrived late), start playback
        if (!isPlayingVoice && voiceChunkBuffer[user_id].chunks.length >= total_chunks) {
            playNextVoiceChunk(user_id);
        }
    }
});

// Function to play voice chunks sequentially
async function playNextVoiceChunk(user_id) {
    if (!voiceChunkBuffer[user_id] || isPlayingVoice) return;

    const buffer = voiceChunkBuffer[user_id];

    // Get the next chunk to play (lowest index)
    const nextChunk = buffer.chunks.shift();
    if (!nextChunk) return;

    isPlayingVoice = true;
    buffer.currentPlaying = nextChunk;

    console.log(`[Voice] Playing chunk ${nextChunk.index}: ${nextChunk.text}`);

    try {
        const audio = new Audio(nextChunk.url);

        // Add to DOM for proper cleanup
        audio.style.display = 'none';
        document.body.appendChild(audio);

        await new Promise((resolve) => {
            audio.onended = () => {
                document.body.removeChild(audio);
                resolve();
            };
            audio.onerror = (e) => {
                console.error(`[Voice] Audio playback error for chunk ${nextChunk.index}:`, e);
                document.body.removeChild(audio);
                resolve();
            };
            audio.play().catch(e => {
                console.error(`[Voice] Failed to play audio:`, e);
                document.body.removeChild(audio);
                resolve();
            });
        });

    } catch (error) {
        console.error(`[Voice] Error playing chunk ${nextChunk.index}:`, error);
    } finally {
        buffer.currentPlaying = null;
        isPlayingVoice = false;

        // Check if there are more chunks to play
        if (buffer.chunks.length > 0) {
            setTimeout(() => playNextVoiceChunk(user_id), 100); // Small delay between chunks
        } else if (buffer.totalExpected && buffer.chunks.length === 0) {
            console.log(`[Voice] All chunks played for user ${user_id}`);
            // Clean up buffer after a delay to allow for any late chunks
            setTimeout(() => {
                if (voiceChunkBuffer[user_id] && voiceChunkBuffer[user_id].chunks.length === 0) {
                    delete voiceChunkBuffer[user_id];
                }
            }, 5000);
        }
    }
}

/////////////////////////////////////////////////////////////////
// Submit tunnels: Hardcode, Intent, Chat
/////////////////////////////////////////////////////////////////
// Submit handler
chatForm.addEventListener('submit', async e => {
  e.preventDefault();
  const userText = input.value.trim();
  if (!userText) return;

  addMessage(userText, 'user');
  input.value = '';
  input.disabled = true;

  try {
    // Step 1: Hardcode
    let response = await fetch('/hardcode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: userText })
    });
    let data = await response.json();
    let reply = data.reply;

    // Step 2: Intent (only if not bypass)
    if (reply !== "Hardcode detected: wikipedia" &&
        reply !== "Hardcode detected: web search") {
      response = await fetch('/intent', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userText })
      });
      data = await response.json();
      reply = data.reply;

      if (reply.startsWith("Handled action:")) {
        playSuccess();
        addMessage(reply, 'assistant');
      } else if (reply === "Unknown intent" || reply.startsWith("Invalid intent")) {
        playFailure();
        addMessage(reply, 'assistant');
      } else if (reply !== "Bypass intent") {
        addMessage(reply, 'assistant');
      }
    }

    // Step 3: Chat
    response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: userText })
        });
        data = await response.json();
        reply = data.reply;

        addMessage(reply, 'assistant');

        // NEW: Start voice synthesis without waiting or polling
        if (!reply.startsWith("Handled action:") &&
            reply !== "Unknown intent" &&
            !reply.startsWith("Invalid intent")) {

            // Get user_id from session or wherever you store it
            const userId = getUserId(); // You'll need to implement this

            if (userId) {
                try {
                    await fetch('/start_voice', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            text: reply,
                            user_id: userId
                        })
                    });
                    console.log('[Voice] Voice synthesis started');
                } catch (err) {
                    console.warn("[Voice] Failed to start synthesis:", err);
                }
            } else {
                console.warn("[Voice] No user_id available, skipping voice synthesis");
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

function getUserId() {
    const sources = [
        () => currentUser?.id // From global JavaScript variable
    ];

    for (const source of sources) {
        const userId = source();
        if (userId && userId !== 'null' && userId !== 'undefined') {
            // Convert to number if it's a number string
            return isNaN(userId) ? userId : parseInt(userId, 10);
        }
    }

    console.warn('[Voice] No user_id found, using fallback');
    return 1; // Fallback for development/testing
}

// Helper to add a message bubble
function addMessage(text, role) {
  const container = document.getElementById('messages');
  const div = document.createElement('div');
  div.className = `message ${role}`;
  div.innerHTML = text.replace(/\n/g, '<br>');
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

/////////////////////////////////////////////////////////////////
// Record
/////////////////////////////////////////////////////////////////
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

// Mobile: get microphone permission
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

// Mobile: start recording
submitButton.addEventListener('touchstart', async e => {
  const hasPermission = await requestMicPermission();
  if (hasPermission) {
    touchTriggered = true;
    await startRecording();

    // Visual feedback after 200ms
    setTimeout(() => {
      if (isRecording && touchTriggered) {
        submitButton.classList.add('green-active');
      }
    }, 200);
  } else {
    alert("Microphone permission is required");
  }
});

// Mobile: stop recording
submitButton.addEventListener('touchend', async e => {
  // Remove visual feedback immediately
  submitButton.classList.remove('green-active');

  // Delay stopRecording by 200ms to keep recording alive
  setTimeout(async () => {
    await stopRecording();
    touchTriggered = false;
  }, 200);
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