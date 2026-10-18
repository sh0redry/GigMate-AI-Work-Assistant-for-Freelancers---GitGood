import { useMemo } from "react";
import { useStableState as useState } from "./useStableState";
import { t } from "./i18n";
import { businessLoopApi } from "./business-loop-api";
import { LoopCommand, LoopRecovery } from "./LoopCommand";
import type { Features } from "./features";
import type { BusinessSnapshot, Order } from "./workspace-api";
import {
  fieldNames,
  friendlyInstant,
  hongKongDateTime,
} from "./work-order-view";

type Field =
  | "address"
  | "schedule"
  | "summary"
  | "quantity"
  | "specification"
  | "deadline";
export function ManualFieldEditor({
  csrf,
  accountId,
  features,
  order,
  data,
  disabled,
  onDone,
  onBusy,
}: {
  csrf: string;
  accountId: string;
  features: Features;
  order: Order;
  data: BusinessSnapshot;
  disabled: boolean;
  onDone: () => void;
  onBusy: (busy: boolean) => void;
}) {
  const api = useMemo(
    () => businessLoopApi(csrf, accountId, features),
    [csrf, accountId, features],
  );
  const [show, setShow] = useState(false),
    [field, setField] = useState<Field>("address"),
    [text, setText] = useState(""),
    [start, setStart] = useState(""),
    [end, setEnd] = useState(""),
    [source, setSource] = useState(""),
    [confirmed, setConfirmed] = useState(false),
    [error, setError] = useState("");
  const sources = data.messages
    .filter((message) => message.direction === "incoming" && !message.revoked)
    .sort((a, b) => Date.parse(b.occurred_at) - Date.parse(a.occurred_at));
  const message = sources.find(
    (message) => `${message.id}:${message.revision}` === source,
  );
  const context = message
    ? (data.contexts?.[message.conversation_id] ?? data.contextVersion)
    : -1;
  const startUtc = hongKongDateTime(start),
    endUtc = hongKongDateTime(end);
  const value =
    field === "schedule"
      ? {
          kind: "timed",
          start_at: startUtc,
          end_at: endUtc,
          timezone: "Asia/Hong_Kong",
        }
      : field === "deadline"
        ? { kind: "instant", at: startUtc, timezone: "Asia/Hong_Kong" }
        : text.trim();
  const validValue =
    field === "schedule"
      ? !!startUtc && !!endUtc && Date.parse(endUtc) > Date.parse(startUtc)
      : field === "deadline"
        ? !!startUtc
        : !!text.trim();
  const intent = {
    path: `/work-orders/${order.id}/manual-field`,
    body: {
      expected_version: order.version,
      expected_context_version: context,
      conversation_id: message?.conversation_id,
      field,
      value,
      sources: message
        ? [{ message_id: message.id, message_revision: message.revision }]
        : [],
      customer_confirmed: confirmed,
      apply_calendar_update: field === "schedule",
    },
    review: t(
      "将「{0}」的{1}改为：{2}。依据：{3}。{4}",
      order.summary,
      fieldNames[field] ?? field,
      field === "schedule"
        ? `${start} → ${end}（香港时间）`
        : field === "deadline"
          ? start
          : text,
      message?.text ?? "",
      confirmed
        ? t("你已核对客户原文明确确认。")
        : t("保留为待客户确认，不记成客户已同意。"),
    ),
  };
  const done = () => {
    setShow(false);
    setText("");
    setSource("");
    setConfirmed(false);
    setError("");
    onDone();
  };
  return (
    <section
      className="manual-field-editor"
      aria-label={t("手动补充或修改工单")}
    >
      <button
        className="secondary"
        disabled={disabled || !!api.pending}
        onClick={() => setShow(!show)}
      >
        {t("手动补充／修改字段")}
      </button>
      {show && (
        <div className="review-sheet">
          <p>
            {t(
              "客户已经说清、AI 却没识别时，在这里补充。选择原文，核对后保存；不会发送消息。",
            )}
          </p>
          <label>
            {t("要修改的内容")}
            <select
              value={field}
              disabled={disabled}
              onChange={(event) => {
                setField(event.target.value as Field);
                setText("");
                setConfirmed(false);
              }}
            >
              {(
                [
                  "address",
                  "schedule",
                  "summary",
                  "quantity",
                  "specification",
                  "deadline",
                ] as Field[]
              ).map((name) => (
                <option key={name} value={name}>
                  {fieldNames[name]}
                </option>
              ))}
            </select>
          </label>
          {field === "schedule" || field === "deadline" ? (
            <>
              <label>
                {field === "deadline"
                  ? t("截止时间（香港时间）")
                  : t("开始时间（香港时间）")}
                <input
                  type="datetime-local"
                  value={start}
                  onChange={(event) => setStart(event.target.value)}
                />
              </label>
              {field === "schedule" && (
                <label>
                  {t("结束时间（香港时间）")}
                  <input
                    type="datetime-local"
                    value={end}
                    onChange={(event) => setEnd(event.target.value)}
                  />
                </label>
              )}
            </>
          ) : (
            <label>
              {t("正确内容")}
              <textarea
                value={text}
                maxLength={field === "summary" ? 120 : 2000}
                onChange={(event) => setText(event.target.value)}
              />
            </label>
          )}
          <label>
            {t("依据哪条客户消息")}
            <select
              value={source}
              onChange={(event) => {
                setSource(event.target.value);
                setConfirmed(false);
              }}
            >
              <option value="">{t("请选择客户原文")}</option>
              {sources.map((message) => (
                <option
                  key={`${message.id}:${message.revision}`}
                  value={`${message.id}:${message.revision}`}
                >
                  {friendlyInstant(message.occurred_at)} ·{" "}
                  {message.text ?? t("没有文字")}
                </option>
              ))}
            </select>
          </label>
          {message && <blockquote>{message.text}</blockquote>}
          <label className="inline-check">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(event) => setConfirmed(event.target.checked)}
            />
            {t("我已核对原文，客户明确确认了这个值")}
          </label>
          <p className="subtle">
            {t(
              "保存会更新工单；时间修改同步日历。旧的未发送草稿作废，仍缺的内容会重新准备询问。",
            )}
          </p>
          <LoopCommand
            api={api}
            intent={intent}
            label={t("核对修改")}
            disabled={disabled || !message || context < 1 || !validValue}
            onDone={done}
            onError={(error) =>
              setError(error instanceof Error ? error.message : t("保存失败"))
            }
            onBusy={onBusy}
          />
        </div>
      )}
      <LoopRecovery
        api={api}
        onDone={done}
        onError={(error) =>
          setError(error instanceof Error ? error.message : t("保存失败"))
        }
        onBusy={onBusy}
      />
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
