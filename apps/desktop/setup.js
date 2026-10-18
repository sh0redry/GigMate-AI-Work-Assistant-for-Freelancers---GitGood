const form = document.querySelector("#setup"),
  start = document.querySelector("#start"),
  progress = document.querySelector("#progress");
let status;
window.gigmateSetup.progress((message) => {
  progress.textContent = message;
});
window.gigmateSetup.status().then((value) => {
  status = value;
  document.querySelector("#fresh").hidden = !status.needsReset;
  document.querySelector("#password").required = status.needsReset;
  start.textContent = status.needsReset ? "清理旧数据并一键启动" : "一键启动";
  document.querySelector("#username").value = status.username;
  document.querySelector("#key-state").textContent = status.keyConfigured
    ? "已保存 API Key，留空则继续使用本机配置。"
    : "未启用 AI：填入自己的 Key 并勾选授权即可启用。";
  progress.textContent = status.needsReset
    ? "请设置账号，确认从空白数据开始。"
    : "已找到本机配置，正在准备启动。";
});
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!status) return;
  if (status.needsReset && !document.querySelector("#clean").checked) {
    progress.textContent = "请先核对并勾选清理旧 GigMate 数据。";
    return;
  }
  start.disabled = true;
  try {
    await window.gigmateSetup.start({
      username: document.querySelector("#username").value,
      password: document.querySelector("#password").value,
      modelKey: document.querySelector("#model-key").value,
      aiConsent: document.querySelector("#ai-consent").checked,
      cleanInstall: document.querySelector("#clean").checked,
    });
    document.querySelector("#password").value = "";
    document.querySelector("#model-key").value = "";
    status = await window.gigmateSetup.status();
    document.querySelector("#fresh").hidden = !status.needsReset;
  } catch {
    /* Main process sends a content-free, actionable status. */
  } finally {
    start.disabled = false;
  }
});
document.querySelector("#docker").addEventListener("click", async () => {
  await window.gigmateSetup.installDocker();
  progress.textContent =
    "已打开 Docker 官方安装包下载。完成安装、许可和系统权限确认后，回这里点“一键启动”；其他环境会自动配置。";
});
