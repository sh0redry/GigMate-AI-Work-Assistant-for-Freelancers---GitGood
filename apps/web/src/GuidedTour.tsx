import { t } from "./i18n.ts";
import { useStableState as useState } from "./useStableState";
import { useEffect, useRef } from "react";

type View =
  | "business"
  | "create"
  | "approvals"
  | "planning"
  | "review"
  | "connect"
  | "guide"
  | "management";

type Step = {
  title: string;
  body: string;
  /** CSS selectors tried in order; the first visible one is highlighted. */
  target?: string[];
  /** The step ends when the user opens this page themselves. */
  waitFor?: View;
};

const STORAGE_PREFIX = "gigmate-tour-v1:";

export function tourSeen(accountId: string) {
  try {
    return (
      globalThis.localStorage?.getItem(STORAGE_PREFIX + accountId) === "done"
    );
  } catch {
    return false;
  }
}

function markSeen(accountId: string) {
  try {
    globalThis.localStorage?.setItem(STORAGE_PREFIX + accountId, "done");
  } catch {
    /* Without storage the tour may show again next time; nothing breaks. */
  }
}

export function tourSteps(): Step[] {
  return [
    {
      title: t("欢迎使用 GigMate"),
      body: t(
        "跟着做 3 件事就能开始：连接 WhatsApp、选要跟进的聊天、看 AI 帮你整理的工单和回复。每一步都要你自己点，随时可以跳过。",
      ),
    },
    {
      title: t("第 1 步：连接 WhatsApp"),
      body: t("点亮起来的「WhatsApp 连接」。"),
      target: ['[data-tour="nav-connect"]'],
      waitFor: "connect",
    },
    {
      title: t("扫码，然后勾选业务聊天"),
      body: t(
        "用手机 WhatsApp 的「关联设备」扫这里的二维码。连上后只勾选和客人谈生意的聊天，私人聊天不要勾，GigMate 不会读取没勾选的聊天。",
      ),
      target: ['[data-tour="connect-page"]', "#workspace-content"],
    },
    {
      title: t("第 2 步：看看新单"),
      body: t("点亮起来的「新建工单」。在手机上先点「更多」。"),
      target: ['[data-tour="nav-create"]', ".mobile-more"],
      waitFor: "create",
    },
    {
      title: t("AI 认出的新单在这里"),
      body: t(
        "客人提出新生意时，AI 会在这里放一份建单建议。你核对后才会建单；不是新单就点「忽略这条建议」。也可以直接在下面手动填，缺的可以先空着。",
      ),
      target: ['[data-tour="create-suggestions"]', "#workspace-content"],
    },
    {
      title: t("第 3 步：批准回复"),
      body: t("点亮起来的「回复审批」。"),
      target: ['[data-tour="nav-approvals"]'],
      waitFor: "approvals",
    },
    {
      title: t("回复一定经过你"),
      body: t(
        "AI 起草给客人的话都放在这里，你看过、批准后才会发出去，不会自己乱发。",
      ),
      target: ['[data-tour="approvals-page"]', "#workspace-content"],
    },
    {
      title: t("完成了"),
      body: t(
        "以后改期、补地址、撞期提醒都会出现在「业务工作台」。想再看一次引导，到「功能与使用说明」点「重新查看新手引导」。",
      ),
    },
  ];
}

function visibleRect(selectors: string[] | undefined) {
  for (const selector of selectors ?? []) {
    const element = document.querySelector(selector);
    if (!element) continue;
    const rect = element.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0) return { selector, rect };
  }
  return null;
}

/**
 * Interactive first-run walkthrough: dims the page, cuts a hole around the
 * real control, and for "open this page" steps waits for the user to click
 * that control themselves. Only the highlighted control is clickable.
 */
export function GuidedTour({
  accountId,
  view,
  onClose,
}: {
  accountId: string;
  view: View;
  onClose: () => void;
}) {
  const steps = tourSteps();
  const [index, setIndex] = useState(0),
    [rect, setRect] = useState<DOMRect | null>(null);
  const card = useRef<HTMLDivElement>(null);
  const step = steps[index];
  const finish = () => {
    markSeen(accountId);
    onClose();
  };
  // Waiting steps advance when the user opens the page themselves.
  useEffect(() => {
    if (step?.waitFor && view === step.waitFor)
      setIndex((i) => Math.min(i + 1, steps.length - 1));
  }, [view, step?.waitFor, steps.length]);
  // Content loads asynchronously and layouts change; keep the hole aligned.
  // Re-measure only when the page (not the tour itself) changes or the
  // window resizes, and only re-render when the position actually moved.
  useEffect(() => {
    const update = () => {
      const next = visibleRect(step?.target)?.rect ?? null;
      setRect((old) =>
        old === next ||
        (old &&
          next &&
          old.top === next.top &&
          old.left === next.left &&
          old.width === next.width &&
          old.height === next.height)
          ? old
          : next,
      );
    };
    update();
    const win = globalThis.window;
    win?.addEventListener?.("resize", update);
    win?.addEventListener?.("scroll", update, true);
    const Observer = globalThis.MutationObserver;
    const observer =
      Observer && globalThis.document?.body
        ? new Observer((records) => {
            if (records.some((r) => !(r.target as Element).closest?.(".tour")))
              update();
          })
        : null;
    observer?.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
    });
    return () => {
      observer?.disconnect();
      win?.removeEventListener?.("resize", update);
      win?.removeEventListener?.("scroll", update, true);
    };
  }, [index]);
  useEffect(() => {
    card.current?.focus();
  }, [index]);
  if (!step) return null;
  const pad = 6;
  const hole = rect && {
    top: Math.max(rect.top - pad, 0),
    left: Math.max(rect.left - pad, 0),
    width: rect.width + pad * 2,
    height: rect.height + pad * 2,
  };
  const viewportHeight = globalThis.window?.innerHeight || 800,
    viewportWidth = globalThis.window?.innerWidth || 1200;
  const below = hole ? hole.top + hole.height + 12 : 0;
  const cardStyle = hole
    ? below + 220 < viewportHeight
      ? {
          top: below,
          left: Math.max(16, Math.min(hole.left, viewportWidth - 376)),
        }
      : {
          bottom: viewportHeight - hole.top + 12,
          left: Math.max(16, Math.min(hole.left, viewportWidth - 376)),
        }
    : undefined;
  const last = index === steps.length - 1;
  return (
    <div
      className="tour"
      onKeyDown={(e) => {
        if (e.key === "Escape") finish();
      }}
    >
      {hole ? (
        <>
          {/* Four blockers around the hole: only the highlighted control works. */}
          <div
            className="tour-block"
            style={{ top: 0, left: 0, right: 0, height: hole.top }}
          />
          <div
            className="tour-block"
            style={{
              top: hole.top + hole.height,
              left: 0,
              right: 0,
              bottom: 0,
            }}
          />
          <div
            className="tour-block"
            style={{
              top: hole.top,
              left: 0,
              width: hole.left,
              height: hole.height,
            }}
          />
          <div
            className="tour-block"
            style={{
              top: hole.top,
              left: hole.left + hole.width,
              right: 0,
              height: hole.height,
            }}
          />
          <div className="tour-ring" style={hole} />
        </>
      ) : (
        <div className="tour-block" style={{ inset: 0 }} />
      )}
      <div
        ref={card}
        className={`tour-card ${hole ? "" : "centered"}`}
        style={cardStyle}
        role="dialog"
        aria-modal="false"
        aria-labelledby="tour-title"
        aria-describedby="tour-body"
        tabIndex={-1}
      >
        <small className="eyebrow">
          {t("新手引导 {0}/{1}", index + 1, steps.length)}
        </small>
        <h2 id="tour-title">{step.title}</h2>
        <p id="tour-body" aria-live="polite">
          {step.body}
        </p>
        <div className="tour-actions">
          <button type="button" className="secondary" onClick={finish}>
            {last ? t("关闭") : t("跳过引导")}
          </button>
          {index > 0 && !last && (
            <button
              type="button"
              className="secondary"
              onClick={() => setIndex((i) => i - 1)}
            >
              {t("上一步")}
            </button>
          )}
          {step.waitFor && view !== step.waitFor && rect ? (
            <span className="subtle">{t("等你点亮起来的按钮…")}</span>
          ) : last ? (
            <button type="button" onClick={finish}>
              {t("开始使用")}
            </button>
          ) : (
            <button type="button" onClick={() => setIndex((i) => i + 1)}>
              {t("下一步")}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
