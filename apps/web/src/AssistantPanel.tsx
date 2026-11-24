import { useEffect, useMemo, useRef, useState } from "react";
import { t } from "./i18n.ts";
import {
  assistantApi,
  FINAL_STATES,
  type AssistantCapabilities,
  type AssistantContext,
  type AssistantDraft,
  type AssistantTurn,
  type SourceRef,
} from "./assistant-api";

type Api = ReturnType<typeof assistantApi>;
type Pending = {
  key: string;
  body: {
    question: string;
    thread_id?: string | null;
    context?: AssistantContext;
  };
};

const MAX_POLLS = 60;

/** Merchant questions to the bounded assistant (ADR 0011).
 *
 * Answers are read-only. A draft can be placed in the composer (`onAdopt`), but
 * nothing here sends, approves or confirms; the existing send review still applies. */
export function AssistantPanel({
  csrf,
  conversation,
  order,
  sources = [],
  adoptEnabled = false,
  onAdopt,
  onOpenOrder,
  onSessionExpired,
  pollMs = 1000,
  api: injected,
}: {
  csrf: string;
  conversation?: string;
  order?: { id: string; version: number } | null;
  sources?: SourceRef[];
  adoptEnabled?: boolean;
  onAdopt?: (text: string) => void;
  onOpenOrder?: (id: string) => void;
  onSessionExpired: () => void;
  pollMs?: number;
  api?: Api;
}) {
  const api = useMemo(() => injected ?? assistantApi(csrf), [injected, csrf]);
  const [caps, setCaps] = useState<AssistantCapabilities | null>(null);
  const [question, setQuestion] = useState("");
  const [thread, setThread] = useState<string | null>(null);
  const [turns, setTurns] = useState<AssistantTurn[]>([]);
  const [drafts, setDrafts] = useState<Record<string, AssistantDraft>>({});
  const [pending, setPending] = useState<Pending | null>(null);
  const [uncertainDraft, setUncertainDraft] = useState("");
  const [notice, setNotice] = useState("");
  const [asking, setAsking] = useState(false);
  const [adopting, setAdopting] = useState(false);
  const alive = useRef({ active: true, abort: new AbortController() });

  useEffect(() => {
    const current = { active: true, abort: new AbortController() };
    alive.current = current;
    api
      .capabilities(current.abort.signal)
      .then((value) => current.active && setCaps(value))
      .catch((error) => {
        if (!current.active) return;
        if (error?.code === "UNAUTHENTICATED") onSessionExpired();
        else
          setNotice(
            error?.message ?? t("暂时无法连接本地服务，请检查服务后刷新。"),
          );
      });
    return () => {
      current.active = false;
      current.abort.abort();
    };
  }, [api, onSessionExpired]);

  function report(error: { code?: string; message?: string }) {
    if (error?.code === "UNAUTHENTICATED") onSessionExpired();
    setNotice(
      error?.message ?? t("操作未能完成或结果暂无法确认，请刷新核对后再操作。"),
    );
  }

  function upsert(turn: AssistantTurn) {
    setTurns((old) =>
      old.some((value) => value.id === turn.id)
        ? old.map((value) => (value.id === turn.id ? turn : value))
        : [...old, turn],
    );
  }

  async function loadDraft(id: string) {
    const current = alive.current;
    try {
      const draft = await api.draft(id, current.abort.signal);
      if (current.active) setDrafts((old) => ({ ...old, [id]: draft }));
      return draft;
    } catch (error) {
      if (current.active) report(error as Error);
      return null;
    }
  }

  async function follow(id: string) {
    const current = alive.current;
    for (let attempt = 0; attempt < MAX_POLLS && current.active; attempt++) {
      await new Promise((resolve) => setTimeout(resolve, pollMs));
      if (!current.active) return;
      try {
        const turn = await api.turn(id, current.abort.signal);
        if (!current.active) return;
        upsert(turn);
        if (FINAL_STATES.has(turn.status)) {
          if (turn.answer?.draft_id) await loadDraft(turn.answer.draft_id);
          return;
        }
      } catch (error) {
        if (current.active) report(error as Error);
        return;
      }
    }
    if (current.active)
      setNotice(t("助手仍在处理，可以稍后点“刷新回答”查看。"));
  }

  async function send(next: Pending) {
    const current = alive.current;
    setAsking(true);
    setNotice("");
    try {
      const turn = await api.ask(next.body, next.key, current.abort.signal);
      if (!current.active) return;
      setPending(null);
      setThread(turn.thread_id);
      setQuestion("");
      upsert(turn);
      if (!FINAL_STATES.has(turn.status)) void follow(turn.id);
    } catch (error) {
      if (!current.active) return;
      const code = (error as { code?: string }).code;
      // Unknown outcome: keep the exact body and key so "check" cannot ask twice.
      setPending(code === "RESULT_UNKNOWN" ? next : null);
      report(error as Error);
    } finally {
      if (current.active) setAsking(false);
    }
  }

  async function ask() {
    const text = question.trim();
    if (!text || asking || pending) return;
    const current = alive.current;
    let context: AssistantContext | undefined;
    if (conversation) {
      try {
        const version = await api.conversationVersion(
          conversation,
          current.abort.signal,
        );
        if (!current.active) return;
        context = {
          conversation_id: conversation,
          expected_context_version: version,
          ...(order
            ? {
                work_order_id: order.id,
                expected_work_order_version: order.version,
              }
            : {}),
          selected_sources: sources,
        };
      } catch (error) {
        if (current.active) report(error as Error);
        return;
      }
    }
    await send({
      key: crypto.randomUUID(),
      body: {
        question: text,
        thread_id: thread,
        ...(context ? { context } : {}),
      },
    });
  }

  async function adopt(draftId: string) {
    if (!onAdopt || adopting || uncertainDraft) return;
    const current = alive.current;
    setAdopting(true);
    try {
      const draft = await api.consume(draftId, current.abort.signal);
      if (!current.active) return;
      setDrafts((old) => ({ ...old, [draftId]: draft }));
      if (draft.text) onAdopt(draft.text);
    } catch (error) {
      if (!current.active) return;
      // Never consume twice automatically; the merchant re-checks the draft state.
      if ((error as { code?: string }).code === "RESULT_UNKNOWN")
        setUncertainDraft(draftId);
      report(error as Error);
    } finally {
      if (current.active) setAdopting(false);
    }
  }

  async function recheckDraft(draftId: string) {
    const draft = await loadDraft(draftId);
    if (!draft || !alive.current.active) return;
    setUncertainDraft("");
    // A consumed draft's text may enter the composer again; it only replaces local text.
    if (draft.status === "consumed" && draft.text && onAdopt)
      onAdopt(draft.text);
  }

  const enabled = caps?.enabled ?? false;
  return (
    <section className="assistant-panel" aria-label={t("AI 助手")}>
      <h3>{t("AI 助手")}</h3>
      {caps && (
        <p className="assistant-disclosure">
          {!caps.enabled
            ? t("助手已关闭。")
            : caps.engine === "rules"
              ? t("目前助手只用本地规则回答，不会把聊天内容发给模型供应商。")
              : caps.sends_customer_text
                ? t(
                    "助手会把所选聊天最近的已授权消息（不含电话号码）发送给 {0} 处理。",
                    caps.vendor ?? "",
                  )
                : t("助手使用 {0}，不会发送客户消息内容。", caps.vendor ?? "")}
        </p>
      )}
      <p className="assistant-scope">
        {conversation
          ? order
            ? t("将基于当前聊天和所选工单回答。")
            : t("将基于当前聊天回答。")
          : t("将基于你的日程和工单回答。")}
        {sources.length > 0 &&
          " " + t("已选 {0} 条客户消息作为回复依据。", sources.length)}
      </p>
      <ol className="assistant-turns">
        {turns.map((turn) => (
          <AssistantTurnItem
            key={turn.id}
            turn={turn}
            draft={
              turn.answer?.draft_id ? drafts[turn.answer.draft_id] : undefined
            }
            uncertain={
              !!turn.answer?.draft_id && uncertainDraft === turn.answer.draft_id
            }
            canAdopt={!!onAdopt && adoptEnabled && !adopting && !uncertainDraft}
            onAdopt={adopt}
            onRecheck={recheckDraft}
            onRefresh={async () => {
              try {
                upsert(await api.turn(turn.id, alive.current.abort.signal));
              } catch (error) {
                report(error as Error);
              }
            }}
            onOpenOrder={onOpenOrder}
          />
        ))}
      </ol>
      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}
      {pending && (
        <button
          className="secondary"
          disabled={asking}
          onClick={() => void send(pending)}
        >
          {t("核对上次提问")}
        </button>
      )}
      <label>
        {t("问 AI 助手")}
        <textarea
          value={question}
          maxLength={1000}
          rows={2}
          placeholder={t(
            "例如：下周哪天有空？哪些工单在等客户回复？帮我回一下，说周二下午可以。",
          )}
          disabled={!enabled || asking || !!pending}
          onChange={(e) => setQuestion(e.target.value)}
        />
      </label>
      <button
        disabled={!enabled || asking || !!pending || !question.trim()}
        onClick={() => void ask()}
      >
        {asking ? t("正在提问…") : t("提问")}
      </button>
    </section>
  );
}

const STATUS: Record<string, string> = {
  queued: "排队中",
  running: "处理中",
  completed: "已回答",
  failed: "未能回答",
  unknown: "结果不确定",
  superseded: "已作废",
};

const REVOKED: Record<string, string> = {
  merchant: "已撤销",
  context_changed: "聊天有新消息，草稿已失效",
  order_changed: "工单有变化，草稿已失效",
  consent_revoked: "处理授权已暂停，草稿已失效",
  source_changed: "客户消息已修改，草稿已失效",
};

function AssistantTurnItem({
  turn,
  draft,
  uncertain,
  canAdopt,
  onAdopt,
  onRecheck,
  onRefresh,
  onOpenOrder,
}: {
  turn: AssistantTurn;
  draft?: AssistantDraft;
  uncertain: boolean;
  canAdopt: boolean;
  onAdopt: (id: string) => void;
  onRecheck: (id: string) => void;
  onRefresh: () => void;
  onOpenOrder?: (id: string) => void;
}) {
  const answer = turn.answer;
  const messages =
    answer?.citations.filter((c) => c.kind === "message").length ?? 0;
  return (
    <li className={`assistant-turn status-${turn.status}`}>
      {/* Merchant and model/server text is business data: rendered as text, never translated. */}
      <p className="assistant-question">{turn.question}</p>
      <p className="assistant-status">
        {t(STATUS[turn.status] ?? turn.status)}
      </p>
      {!FINAL_STATES.has(turn.status) && (
        <button className="secondary" onClick={onRefresh}>
          {t("刷新回答")}
        </button>
      )}
      {turn.status === "superseded" && (
        <p>{t("聊天或工单刚有更新，这次回答已作废，请重新提问。")}</p>
      )}
      {turn.status === "unknown" && (
        <p>{t("这次处理结果不确定，不会自动重试，请重新提问。")}</p>
      )}
      {turn.status === "failed" && (
        <p>
          {t("这次没能回答（{0}），请换个说法再问。", turn.error_code ?? "")}
        </p>
      )}
      {answer && <p className="assistant-answer">{answer.text}</p>}
      {answer && answer.unverified_claims.length > 0 && (
        <div className="notice">
          <p>{t("以下内容未经核实，发送前请确认：")}</p>
          <ul>
            {answer.unverified_claims.map((claim) => (
              <li key={claim}>{claim}</li>
            ))}
          </ul>
        </div>
      )}
      {messages > 0 && (
        <p className="assistant-citation">
          {t("依据：{0} 条客户消息", messages)}
        </p>
      )}
      {answer?.citations.some((c) => c.kind === "free_slots") && (
        <p className="assistant-citation">
          {t("依据：你的工作时间和已确认预约")}
        </p>
      )}
      {onOpenOrder &&
        answer?.work_order_ids.map((id, index) => (
          <button
            className="secondary"
            key={id}
            onClick={() => onOpenOrder(id)}
          >
            {t("打开相关工单 {0}", index + 1)}
          </button>
        ))}
      {draft && (
        <div className="assistant-draft">
          {draft.status === "proposed" && canAdopt && (
            <button onClick={() => onAdopt(draft.id)}>
              {t("放入输入框（不发送）")}
            </button>
          )}
          {draft.status === "proposed" && !canAdopt && !uncertain && (
            <p>{t("可在客户会话中把草稿放入输入框。")}</p>
          )}
          {draft.status === "consumed" && (
            <p>{t("已放入输入框，请核对后再发送。")}</p>
          )}
          {draft.status === "expired" && <p>{t("草稿已过期，请重新提问。")}</p>}
          {draft.status === "revoked" && (
            <p>{t(REVOKED[draft.revoke_reason ?? "merchant"] ?? "已撤销")}</p>
          )}
          {uncertain && (
            <button className="secondary" onClick={() => onRecheck(draft.id)}>
              {t("核对草稿状态")}
            </button>
          )}
        </div>
      )}
    </li>
  );
}
