import { t } from "./i18n.ts";
import { useEffect, useMemo } from "react";
import { useStableState as useState } from "./useStableState";
import { LoopCommand } from "./LoopCommand";
import type { LoopApi, Loop } from "./business-loop-api";
import { allPages, workspaceApi, type Order, type Task } from "./workspace-api";
import { fieldValue, taskStates } from "./work-order-view";

export function ProductTools({
  api,
  csrf,
  orders,
  onOpenOrder,
  onDone,
  onError,
  onBusy,
  revision,
}: {
  api: LoopApi;
  csrf: string;
  orders: Order[];
  onOpenOrder: (id: string) => void;
  onDone: () => void;
  onError: (e: unknown) => void;
  onBusy: (v: boolean) => void;
  revision: number;
}) {
  const read = useMemo(() => workspaceApi(csrf), [csrf]);
  const [question, setQuestion] = useState(""),
    [answer, setAnswer] = useState<Loop["WorkspaceQueryResult"] | null>(null),
    [querying, setQuerying] = useState(false),
    [tasks, setTasks] = useState<Task[]>([]),
    [scope, setScope] = useState(""),
    [ready, setReady] = useState(false);
  useEffect(() => {
    const abort = new AbortController();
    setReady(false);
    void allPages<Task>(read, "/tasks", abort.signal)
      .then((value) => {
        if (!abort.signal.aborted) {
          setTasks(value);
          setReady(true);
        }
      })
      .catch((e) => {
        if (!abort.signal.aborted) onError(e);
      });
    return () => abort.abort();
  }, [read, revision, onError]);
  async function query(value = question) {
    if (querying || !value.trim()) return;
    setQuerying(true);
    setAnswer(null);
    try {
      setAnswer(
        (
          await read<{ data: Loop["WorkspaceQueryResult"] }>(
            "/workspace-query",
            { question: value },
          )
        ).data,
      );
    } catch (e) {
      onError(e);
    } finally {
      setQuerying(false);
    }
  }
  return (
    <>
      <section className="panel">
        <h2>{t("快速问工作台")}</h2>
        <p>
          {t(
            "从当前账号的记录查询安排。只支持下方四类问题，不会修改工单或发送消息。",
          )}
        </p>
        <div className="command-row">
          {[
            t("今天有什么安排"),
            t("明天有什么安排"),
            t("哪些在等客户"),
            t("有什么待决定"),
          ].map((q) => (
            <button
              className="secondary"
              disabled={querying}
              key={q}
              onClick={() => {
                setQuestion(q);
                void query(q);
              }}
            >
              {q}
            </button>
          ))}
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void query();
          }}
        >
          <label>
            {t("你的问题")}
            <input
              maxLength={200}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
            />
          </label>
          <button disabled={querying || !question.trim()}>
            {t("查询记录")}
          </button>
        </form>
        {answer && (
          <div role="status">
            {!answer.supported ? (
              <p>{t("暂时只支持上面四类问题，请选择一个。不会猜测答案。")}</p>
            ) : (
              <>
                <p>
                  {answer.day}{" "}
                  {t("· 查询完成；结果是业务记录，不代表 AI 已确认。")}
                </p>
                {!answer.items.length && <p>{t("这类记录暂时为空。")}</p>}
                {answer.items.map((item, i) => (
                  <p key={i}>
                    {item.title}{" "}
                    {item.work_order_id && (
                      <button
                        className="secondary"
                        onClick={() => onOpenOrder(item.work_order_id!)}
                      >
                        {t("查看工单")}
                      </button>
                    )}
                  </p>
                ))}
              </>
            )}
          </div>
        )}
      </section>
      <section className="panel">
        <h2>{t("处理待办")}</h2>
        <p>
          {t(
            "完成待办只记录你的处理决定，不代表客户确认了时间或地址。关联需求条目会一起更新。",
          )}
        </p>
        <label>
          {t("工单范围")}
          <select value={scope} onChange={(e) => setScope(e.target.value)}>
            <option value="">{t("全部开放工单")}</option>
            {orders
              .filter((o) => !["completed", "cancelled"].includes(o.status))
              .map((o) => (
                <option key={o.id} value={o.id}>
                  {o.summary}
                </option>
              ))}
          </select>
        </label>
        {tasks
          .filter(
            (t) =>
              (!scope || t.work_order_id === scope) &&
              ["pending", "blocked"].includes(t.state),
          )
          .map((task) => {
            const order = orders.find((o) => o.id === task.work_order_id);
            if (!order || ["completed", "cancelled"].includes(order.status))
              return null;
            return (
              <article className="task" key={task.id}>
                <h3>{task.title}</h3>
                <p>
                  {taskStates[task.state]} · {fieldValue(task.due)}
                </p>
                <p>
                  {t("来源：")}
                  {task.sources
                    .map(
                      (s) => `${s.message_id.slice(-6)} r${s.message_revision}`,
                    )
                    .join(" · ")}
                </p>
                {(["completed", "cancelled"] as const).map((state) => (
                  <LoopCommand
                    key={state}
                    api={api}
                    onDone={onDone}
                    onError={onError}
                    onBusy={onBusy}
                    disabled={
                      !ready || !["pending", "blocked"].includes(task.state)
                    }
                    label={
                      state === "completed"
                        ? t("核对完成待办")
                        : t("核对取消待办")
                    }
                    intent={{
                      path: `/tasks/${task.id}/status`,
                      body: {
                        expected_version: order.version,
                        expected_state: task.state as "pending" | "blocked",
                        state,
                      },
                      review: t(
                        "工单“{0}” v{1}，待办“{2}”：{3}。请核对原文来源和依赖任务；不会确认客户的约定。",
                        order.summary,
                        order.version,
                        task.title,
                        state === "completed" ? t("完成") : t("取消"),
                      ),
                    }}
                  />
                ))}
              </article>
            );
          })}
        {ready &&
          !tasks.some(
            (t) =>
              (!scope || t.work_order_id === scope) &&
              ["pending", "blocked"].includes(t.state) &&
              orders.some(
                (o) =>
                  o.id === t.work_order_id &&
                  !["completed", "cancelled"].includes(o.status),
              ),
          ) && <p>{t("当前没有待处理的待办。")}</p>}
      </section>
    </>
  );
}
