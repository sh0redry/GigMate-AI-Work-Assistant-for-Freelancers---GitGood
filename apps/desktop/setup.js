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
  start.textContent = "保存设置并启动";
  document.querySelector("#username").value = status.username;
  document.querySelector("#ai-consent").checked = status.aiEnabled;
  document.querySelector("#input-price").value = status.inputPrice;
  document.querySelector("#output-price").value = status.outputPrice;
  document.querySelector("#budget").value = status.budget;
  document.querySelector("#key-state").textContent = status.keyConfigured
    ? "已保存 API Key，留空则继续使用本机配置。"
    : "未启用 AI：请配置自己的 Key、美元价格并明确授权。";
  progress.textContent = status.needsReset
    ? "请设置独立账号；不会清理任何已有环境。"
    : "已找到本机配置，正在准备启动。";
});
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!status) return;
  start.disabled = true;
  try {
    await window.gigmateSetup.start({
      username: document.querySelector("#username").value,
      password: document.querySelector("#password").value,
      modelKey: document.querySelector("#model-key").value,
      aiConsent: document.querySelector("#ai-consent").checked,
      aiEnabled:
        document.querySelector("#ai-consent").checked &&
        !document.querySelector("#clear-key").checked,
      clearKey: document.querySelector("#clear-key").checked,
      inputPrice: document.querySelector("#input-price").value,
      outputPrice: document.querySelector("#output-price").value,
      budget: document.querySelector("#budget").value,
    });
    document.querySelector("#password").value = "";
    document.querySelector("#model-key").value = "";
    document.querySelector("#clear-key").checked = false;
    status = await window.gigmateSetup.status();
    document.querySelector("#fresh").hidden = !status.needsReset;
    document.querySelector("#ai-consent").checked = status.aiEnabled;
    document.querySelector("#key-state").textContent = status.aiEnabled
      ? "AI 已启用。"
      : "AI 未启用，可手动处理；请核对 Key、授权和美元价格。";
  } catch {
    /* Main process sends a content-free, actionable status. */
  } finally {
    start.disabled = false;
  }
});

let cleanupPlan;
const cleanupList = document.querySelector("#cleanup-list"),
  cleanupDelete = document.querySelector("#cleanup-delete"),
  cleanupStatus = document.querySelector("#cleanup-status");
function clearCleanup() {
  cleanupPlan = undefined;
  cleanupDelete.disabled = true;
  document.querySelector("#cleanup-resources").replaceChildren();
  document.querySelector("#cleanup-confirmation").value = "";
}
document
  .querySelector("#include-legacy")
  .addEventListener("change", clearCleanup);
cleanupList.addEventListener("click", async () => {
  clearCleanup();
  cleanupList.disabled = true;
  try {
    cleanupPlan = await window.gigmateSetup.cleanupPlan(
      document.querySelector("#include-legacy").checked,
    );
    for (const entry of cleanupPlan.entries) {
      const label = document.createElement("label"),
        input = document.createElement("input");
      input.type = "checkbox";
      input.value = `${entry.kind}:${entry.id}`;
      label.className = "check";
      label.append(
        input,
        document.createTextNode(
          `${entry.kind} · ${entry.name} · ID ${entry.id} · 项目 ${entry.project} · 创建 ${entry.created}${entry.legacy ? " · 旧开发环境/可能含备份" : ""}`,
        ),
      );
      document.querySelector("#cleanup-resources").append(label);
    }
    cleanupDelete.disabled = !cleanupPlan.entries.length;
    cleanupStatus.textContent =
      "仅勾选你确实要删除的资源。清单两分钟后失效，删除不可恢复。当前工作台不在清单内。";
  } catch {
    cleanupStatus.textContent =
      "无法获取清单，请核对本机 Docker 后重试；未执行删除。";
  } finally {
    cleanupList.disabled = false;
  }
});
cleanupDelete.addEventListener("click", async () => {
  if (!cleanupPlan) return;
  const selected = [
    ...document.querySelectorAll("#cleanup-resources input:checked"),
  ].map((input) => input.value);
  const confirmation = document.querySelector("#cleanup-confirmation").value;
  if (!selected.length || confirmation !== "删除所选数据") {
    cleanupStatus.textContent = "请选择资源并准确输入：删除所选数据";
    return;
  }
  cleanupDelete.disabled = true;
  try {
    await window.gigmateSetup.cleanup({
      token: cleanupPlan.token,
      selected,
      confirmation,
    });
    cleanupStatus.textContent = "所选资源已删除。";
  } catch {
    cleanupStatus.textContent =
      "删除未完成或结果待核对，请重新读取清单；不会自动重复删除。";
  } finally {
    clearCleanup();
  }
});
document.querySelector("#docker").addEventListener("click", async () => {
  await window.gigmateSetup.installDocker();
  progress.textContent =
    "已打开 Docker 官方安装包下载。完成安装、许可和系统权限确认后，回这里点“一键启动”；其他环境会自动配置。";
});
