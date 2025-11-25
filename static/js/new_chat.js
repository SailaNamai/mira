// static/js/new_chat.js

document.querySelector(".icon-new-chat").addEventListener("click", () => {
    fetch("/new_chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({})
    })
    .then(res => res.json())
    .then(data => {
        console.log(data.status);
        document.getElementById("messages").innerHTML = ""; // Clear chat UI
    });
});
