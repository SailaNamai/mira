document.addEventListener('DOMContentLoaded', () => {
  const messages = document.getElementById('messages');
  const input = document.getElementById('user-input');

  function scrollToBottom() {
    if (messages) {
      messages.scrollTop = messages.scrollHeight;
    }
  }

  function updateVh() {
    const height = window.visualViewport
      ? window.visualViewport.height
      : window.innerHeight;
    document.documentElement.style.setProperty('--vh', `${height * 0.01}px`);
  }

  // Scroll when input gains focus (keyboard likely appears)
  if (input) {
    input.addEventListener('focus', () => {
      setTimeout(scrollToBottom, 300);
    });
  }

  // Scroll when visualViewport changes
  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', () => {
      updateVh();
      scrollToBottom();
    });
  }

  // Fallbacks
  window.addEventListener('resize', () => {
    updateVh();
    scrollToBottom();
  });
  window.addEventListener('orientationchange', updateVh);

  updateVh(); // initial call
});
