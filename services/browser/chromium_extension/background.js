// background.js

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "passMira",
    title: "Mira",
    contexts: ["page", "selection", "image", "link"]
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== "passMira") return;

  let payload = {};

  // 1. Text selection
  if (info.selectionText) {
    payload.type = "selection";
    payload.content = info.selectionText;

  // use Chrome's native image fetcher
  } else if (info.srcUrl) {
    try {
      // fetch the actual raw image bytes
      const response = await fetch(info.srcUrl, { credentials: "omit" });
      const blob = await response.blob();

      payload.type = "image_blob";           // special type
      payload.content = await blobToBase64(blob);  // base64 string
      payload.filename = "image-from-web." + (blob.type.split("/")[1] || "png");
    } catch (e) {
      console.error("Failed to fetch image blob:", e);
      return; // silently fail
    }

  // 3. Right-click on a link that looks like an image
  } else if (info.linkUrl && info.linkUrl.match(/\.(jpg|jpeg|png|gif|webp|avif|bmp)(\?.*)?$/i)) {
    // fetch raw bytes
    try {
      const response = await fetch(info.linkUrl, { credentials: "omit" });
      const blob = await response.blob();
      payload.type = "image_blob";
      payload.content = await blobToBase64(blob);
      payload.filename = info.linkUrl.split("/").pop().split("?")[0];
    } catch (e) {
      console.error("Failed to fetch linked image:", e);
      return;
    }

  // 4. Normal link or page
  } else if (info.linkUrl) {
    payload.type = "link";
    payload.content = info.linkUrl;
  } else {
    payload.type = "page";
    payload.content = tab.url;
  }

  // Send to Flask
  fetch("http://127.0.0.1:5002/receive", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  }).then(r => console.log("Mira ←", r.status));
});

// Helper: blob to base64
function blobToBase64(blob) {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(reader.result.split(",")[1]); // strip data: prefix
    reader.readAsDataURL(blob);
  });
}