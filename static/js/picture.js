// picture.js

document.addEventListener('DOMContentLoaded', () => {
  const trigger = document.querySelector('.icon-camera');
  if (!trigger) return;

  // Inject styles once
  if (!document.getElementById('scanner-overlay-style')) {
    const style = document.createElement('style');
    style.id = 'scanner-overlay-style';
    style.textContent = `
      .camera-overlay {
        position: fixed !important;
        top: 0; left: 0;
        width: 100vw; height: 100vh;
        background: black;
        z-index: 9999;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
      }
      .camera-overlay video,
      .camera-overlay img.preview {
        width: 100%;
        height: 100%;
        object-fit: contain;
        background: black;
      }
      .camera-overlay .bottom-bar {
        position: absolute;
        bottom: 80px;
        left: 50%;
        transform: translateX(-50%);
        display: flex;
        gap: 30px;
        z-index: 1004;
      }
      .camera-overlay .btn {
        padding: 16px 36px;
        font-size: 18px;
        font-weight: 600;
        border: none;
        border-radius: 50px;
        cursor: pointer;
        min-width: 150px;
        transition: all 0.2s;
      }
      .camera-overlay .btn-close,
      .camera-overlay .btn-redo {
        background: rgba(255,255,255,0.2);
        color: white;
        backdrop-filter: blur(10px);
        border: 2px solid rgba(255,255,255,0.3);
      }
      .camera-overlay .btn-primary {
        background: #28a745;
        color: white;
        box-shadow: 0 6px 20px rgba(40,167,69,0.4);
      }
    `;
    document.head.appendChild(style);
  }

  trigger.addEventListener('click', openCameraOverlay);

  function openCameraOverlay() {
    const overlay = document.createElement('div');
    overlay.className = 'camera-overlay';

    const video = document.createElement('video');
    video.autoplay = true;
    video.playsInline = true;
    video.muted = true;

    const bottomBar = document.createElement('div');
    bottomBar.className = 'bottom-bar';

    // Initial buttons: Close + Capture
    const closeBtn = document.createElement('button');
    closeBtn.textContent = 'Close';
    closeBtn.className = 'btn btn-close';

    const captureBtn = document.createElement('button');
    captureBtn.textContent = 'Capture';
    captureBtn.className = 'btn btn-primary';

    bottomBar.append(closeBtn, captureBtn);
    overlay.append(video, bottomBar);
    document.body.appendChild(overlay);

    let stream = null;
    let capturedBlob = null;

    // Start camera
    navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
      .then(s => {
        stream = s;
        video.srcObject = stream;
      })
      .catch(err => {
        console.error('Camera access denied:', err);
        alert('Camera access denied or unavailable');
        overlay.remove();
      });

    const closeAll = () => {
      if (stream) stream.getTracks().forEach(t => t.stop());
      overlay.remove();
    };

    closeBtn.addEventListener('click', closeAll);

    // Switch to preview mode after capture
    const showPreview = (blob) => {
      capturedBlob = blob;

      // Replace video with image
      video.remove();
      const img = document.createElement('img');
      img.src = URL.createObjectURL(blob);
      img.className = 'preview';
      overlay.insertBefore(img, bottomBar);

      // Replace buttons: Redo + Send
      bottomBar.innerHTML = '';

      const redoBtn = document.createElement('button');
      redoBtn.textContent = 'Redo';
      redoBtn.className = 'btn btn-redo';

      const sendBtn = document.createElement('button');
      sendBtn.textContent = 'Send';
      sendBtn.className = 'btn btn-primary';

      bottomBar.append(redoBtn, sendBtn);

      redoBtn.addEventListener('click', () => {
      img.remove();
      overlay.insertBefore(video, bottomBar);
      video.srcObject = stream;
      bottomBar.innerHTML = '';

      // Recreate buttons
      const newCloseBtn = document.createElement('button');
      newCloseBtn.textContent = 'Close';
      newCloseBtn.className = 'btn btn-close';
      newCloseBtn.addEventListener('click', closeAll);

      const newCaptureBtn = document.createElement('button');
      newCaptureBtn.textContent = 'Capture';
      newCaptureBtn.className = 'btn btn-primary';
      newCaptureBtn.addEventListener('click', () => {
        const canvas = document.createElement('canvas');
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(video, 0, 0);

        canvas.toBlob(blob => {
          if (blob) showPreview(blob);
        }, 'image/jpeg', 0.92);
      });

      bottomBar.append(newCloseBtn, newCaptureBtn);
    });

      sendBtn.addEventListener('click', () => {
        if (!capturedBlob) return;

        const formData = new FormData();
        formData.append('picture', capturedBlob, 'picture.jpeg');

        fetch('/picture', {
          method: 'POST',
          body: formData
        })
        .then(res => res.text())
        .then(txt => {
          console.log('[Picture] Uploaded:', txt);
          closeAll();
        })
        .catch(err => {
          console.error('Upload failed:', err);
          alert('Failed to send picture');
        });
      });
    };

    // Capture button
    captureBtn.addEventListener('click', () => {
      const canvas = document.createElement('canvas');
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(video, 0, 0);

      canvas.toBlob(blob => {
        if (blob) showPreview(blob);
      }, 'image/jpeg', 0.92);
    });
  }
});