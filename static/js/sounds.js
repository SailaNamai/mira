// static/js/sounds.js

function playSuccess() {
  const audio = new Audio("/static/sounds/modern_14.mp3");
  audio.play();
}

function playFailure() {
  const audio = new Audio("/static/sounds/wood_block_1.mp3");
  audio.play();
}
