// background.js

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "passMira",
    title: "Mira",
    contexts: ["page", "selection", "image", "link"]
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId !== "passMira") return;

  let payload = {};

  if (info.selectionText) {
    payload.type = "selection";
    payload.content = info.selectionText;
  } else if (info.linkUrl) {
    payload.type = "link";
    payload.content = info.linkUrl;
  } else if (info.srcUrl) {
    payload.type = "image";
    payload.content = info.srcUrl;
  } else {
    payload.type = "page";
    payload.content = tab.url;
  }

  fetch("http://127.0.0.1:5002/receive", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  }).then(response => {
    console.log("Sent to Flask:", response.status);
  }).catch(error => {
    console.error("Error sending to Flask:", error);
  });

  console.log("Pass to Mira clicked!", payload);
});