const { contextBridge, ipcRenderer } = require("electron");
contextBridge.exposeInMainWorld(
  "gigmateSetup",
  Object.freeze({
    status: () => ipcRenderer.invoke("gigmate:status"),
    start: (options) => ipcRenderer.invoke("gigmate:start", options),
    installDocker: () => ipcRenderer.invoke("gigmate:install-docker"),
    progress: (callback) => {
      const listener = (_, message) => callback(String(message));
      ipcRenderer.on("gigmate:progress", listener);
      return () => ipcRenderer.removeListener("gigmate:progress", listener);
    },
  }),
);
