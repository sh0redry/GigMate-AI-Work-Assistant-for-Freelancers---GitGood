const { contextBridge, ipcRenderer } = require("electron");
contextBridge.exposeInMainWorld(
  "gigmateSetup",
  Object.freeze({
    status: () => ipcRenderer.invoke("gigmate:status"),
    start: (options) => ipcRenderer.invoke("gigmate:start", options),
    installDocker: () => ipcRenderer.invoke("gigmate:install-docker"),
    cleanupPlan: (includeLegacy) =>
      ipcRenderer.invoke("gigmate:cleanup-plan", includeLegacy),
    cleanup: (options) => ipcRenderer.invoke("gigmate:cleanup", options),
    progress: (callback) => {
      const listener = (_, message) => callback(String(message));
      ipcRenderer.on("gigmate:progress", listener);
      return () => ipcRenderer.removeListener("gigmate:progress", listener);
    },
  }),
);
