// static/js/attachment.js

const attachIcon = document.querySelector(".icon-attach");
const fileInput = document.getElementById("file-input");
const removeIcon = document.querySelector(".icon-remove-attachment");
// Socket.IO
const socket = io(); // Connect to the Socket.IO server

let hasAttachment = false;

function updateAttachmentUI() {
    removeIcon.style.display = hasAttachment ? "block" : "none";
}

/* Poll for attachment status (from /receive or backend state)
setInterval(() => {
    fetch("/attachment_status")
        .then(res => res.json())
        .then(data => {
            if (data.has_attachment !== hasAttachment) {
                hasAttachment = data.has_attachment;
                updateAttachmentUI();
            }
        })
        .catch(() => {}); // silent fail
}, 1000);*/

// Listen for attachment updates
socket.on('attachment_update', (data) => {
    hasAttachment = data.has_attachment;
    updateAttachmentUI();
});
// Request initial attachment status
socket.emit('get_attachment_status');

// Optional: Manual status check method
function checkAttachmentStatus() {
    socket.emit('get_attachment_status');
}

// --- File upload ---
attachIcon.addEventListener("click", () => {
    fileInput.click();
});

fileInput.addEventListener("change", () => {
    const file = fileInput.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    fetch("/upload", {
        method: "POST",
        body: formData
    })
    .then(res => res.json())
    .then(() => {
        hasAttachment = true;
        updateAttachmentUI();
    });
});

// --- Remove attachment ---
removeIcon.addEventListener("click", (e) => {
    e.stopPropagation();
    fileInput.value = ""; // clear file input
    hasAttachment = false;
    updateAttachmentUI();

    fetch("/remove_attachment", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({})
    });
});