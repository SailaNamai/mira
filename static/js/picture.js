// picture.js

document.querySelector('.icon-camera').addEventListener('click', () => {
  // Create overlay
  const overlay = document.createElement('div');
  overlay.style.position = 'fixed';
  overlay.style.top = '0';
  overlay.style.left = '0';
  overlay.style.width = '100vw';
  overlay.style.height = '100vh';
  overlay.style.backgroundColor = 'black';
  overlay.style.zIndex = '9999';
  overlay.style.display = 'flex';
  overlay.style.flexDirection = 'column';
  overlay.style.alignItems = 'center';
  overlay.style.justifyContent = 'center';
  overlay.classList.add('camera-overlay');
  document.body.appendChild(overlay);

  // Create video element
  const video = document.createElement('video');
  video.autoplay = true;
  video.playsInline = true;
  video.style.width = '100%';
  video.style.height = '100%';
  video.style.objectFit = 'cover';
  overlay.appendChild(video);

  // Create button container
  const buttonContainer = document.createElement('div');
  buttonContainer.style.position = 'absolute';
  buttonContainer.style.bottom = '60px';
  buttonContainer.style.display = 'flex';
  buttonContainer.style.gap = '20px';
  overlay.appendChild(buttonContainer);

  // Capture button
  const captureButton = document.createElement('button');
  captureButton.textContent = 'Capture';
  captureButton.style.padding = '10px 20px';
  captureButton.style.fontSize = '16px';
  captureButton.style.cursor = 'pointer';
  buttonContainer.appendChild(captureButton);

  // Close button
  const closeButton = document.createElement('button');
  closeButton.textContent = 'Close';
  closeButton.style.padding = '10px 20px';
  closeButton.style.fontSize = '16px';
  closeButton.style.cursor = 'pointer';
  buttonContainer.appendChild(closeButton);

  // Start camera
  navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
    .then(stream => {
      video.srcObject = stream;
    })
    .catch(err => {
      console.error('Camera access error:', err);
    });

  // Capture logic
  captureButton.addEventListener('click', () => {
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const imageData = canvas.toDataURL('image/png');

    console.log('Captured image:', imageData);
    // You can send imageData to your server or use it in your app
  });

  // Close logic
  closeButton.addEventListener('click', () => {
    const stream = video.srcObject;
    if (stream) {
      stream.getTracks().forEach(track => track.stop());
    }
    overlay.remove();
  });
});
