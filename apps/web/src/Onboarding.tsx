import { useEffect, useState } from "react";
import { t } from "./i18n";
type Page =
  | "connect"
  | "create"
  | "business"
  | "approvals"
  | "planning"
  | "review";
export function Onboarding({
  accountId,
  busy,
  onOpen,
}: {
  accountId: string;
  busy: boolean;
  onOpen: (page: Page) => void;
}) {
  const [step, setStep] = useState<number | null>(null);
  const key = `gigmate-tutorial-v1:${accountId}`;
  useEffect(() => {
    try {
      setStep(window.localStorage.getItem(key) === "done" ? null : 0);
    } catch {
      setStep(0);
    }
  }, [key]);
  const steps = [
    {
      title: t("先选择允许处理的聊天"),
      text: t(
        "到 WhatsApp 连接页连接账号，只勾选业务客户，再保存会话授权；读取聊天不等于允许发送。",
      ),
      page: "connect" as const,
    },
    {
      title: t("一件业务建一张工单"),
      text: t(
        "到新建工单查看 AI 建议，也可手动建单。同一客户的另一件事可以另建单；不知道的字段留空。",
      ),
      page: "create" as const,
    },
    {
      title: t("核对原文，再确认安排"),
      text: t(
        "在业务工作台核对地址和完整时段。客人提出、客人确认和你的确认是不同步骤；过期提议要重新分析。",
      ),
      page: "business" as const,
    },
    {
      title: t("回复先批准，再明确发送"),
      text: t(
        "查看收件人和完整草稿。不想发可以取消草稿；批准不会立即发送，还要明确提交发送。",
      ),
      page: "approvals" as const,
    },
    {
      title: t("查看日历和待办"),
      text: t(
        "正式安排会进入日历。缺结束时间不会编造时长；可导出已确认安排，或到人工复核处理仍不清楚的消息。",
      ),
      page: "planning" as const,
    },
  ];
  function finish() {
    try {
      window.localStorage.setItem(key, "done");
    } catch {}
    setStep(null);
  }
  return (
    <>
      <button className="secondary" disabled={busy} onClick={() => setStep(0)}>
        {t("新手教程")}
      </button>
      {step !== null && (
        <aside
          className="panel onboarding"
          role="dialog"
          aria-label={t("新手教程")}
          aria-modal="false"
        >
          <small>{t("第 {0} / {1} 步", step + 1, steps.length)}</small>
          <h2>{steps[step].title}</h2>
          <p>{steps[step].text}</p>
          <div className="reply-actions">
            <button disabled={busy} onClick={() => onOpen(steps[step].page)}>
              {t("打开本步页面")}
            </button>
            {step > 0 && (
              <button
                disabled={busy}
                className="secondary"
                onClick={() => setStep(step - 1)}
              >
                {t("上一步")}
              </button>
            )}
            <button
              disabled={busy}
              onClick={() =>
                step === steps.length - 1 ? finish() : setStep(step + 1)
              }
            >
              {step === steps.length - 1 ? t("完成教程") : t("下一步")}
            </button>
            <button disabled={busy} className="text-button" onClick={finish}>
              {t("跳过教程")}
            </button>
          </div>
          <small>
            {t("教程只介绍操作，不会授权聊天、创建工单或发送消息。")}
          </small>
        </aside>
      )}
    </>
  );
}
