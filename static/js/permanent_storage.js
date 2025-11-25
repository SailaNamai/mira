async function requestPersistentStorage() {
  if (navigator.storage && navigator.storage.persist) {
    const isPersisted = await navigator.storage.persisted();
    if (isPersisted) {
      console.log("Already using persistent storage");
      return true;
    }

    const granted = await navigator.storage.persist();
    if (granted) {
      console.log("Persistent storage granted");
    } else {
      console.warn("Persistent storage denied");
    }
    return granted;
  } else {
    console.warn("Persistent storage API not supported");
    return false;
  }
}

document.addEventListener('DOMContentLoaded', () => {
  requestPersistentStorage();
});