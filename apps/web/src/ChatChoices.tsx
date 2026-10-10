import { useEffect, useState } from "react";
import type { Choice } from "./connection-api";
import { choiceExpired } from "./connection-state";
import { choicePage, type ChatFilter } from "./chat-choices";

export function ChatChoices({
  choices,
  picked,
  busy,
  canDiscover,
  clock,
  demo,
  onToggle,
}: {
  choices: Choice[];
  picked: string[];
  busy: boolean;
  canDiscover: boolean;
  clock: number;
  demo: boolean;
  onToggle: (id: string, checked: boolean) => void;
}) {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<ChatFilter>("all");
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(8);
  const view = choicePage(choices, search, filter, page, size);
  useEffect(() => {
    if (page !== view.page) setPage(view.page);
  }, [page, view.page]);
  return (
    <div className="chat-choices">
      <div className="chat-filters">
        <label>
          搜索已载入会话
          <input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            placeholder="会话名称或号码"
          />
        </label>
        <label>
          会话类型
          <select
            value={filter}
            onChange={(e) => {
              setFilter(e.target.value as ChatFilter);
              setPage(1);
            }}
          >
            <option value="all">全部</option>
            <option value="direct">个人聊天</option>
            <option value="group">群聊</option>
            <option value="selected">已授权</option>
            <option value="unknown">类型未提供</option>
          </select>
        </label>
      </div>
      <p className="subtle chat-metadata-help">
        名称和类型由接入服务提供；仅提供号码时不会猜测昵称。可重新发现会话刷新名称。
      </p>
      <p className="chat-page-summary" aria-live="polite">
        显示 {view.start}–{view.end} / {view.total} 个结果 · 已载入{" "}
        {choices.length} 个会话 · 已勾选 {picked.length} 个（含其他页）
      </p>
      <div className="chat-choice-page">
        {view.items.map(
          ({ choice: c, index, label, kind, kindLabel, numberOnly }) => (
            <label className="chat-choice" key={c.id}>
              <input
                type="checkbox"
                aria-label={`${label} · ${kindLabel} · 会话 ${index + 1}`}
                checked={picked.includes(c.id)}
                disabled={
                  busy ||
                  (!picked.includes(c.id) &&
                    (picked.length >= 100 ||
                      (!c.selected &&
                        (!canDiscover || choiceExpired(c, clock)))))
                }
                onChange={(e) => onToggle(c.id, e.target.checked)}
              />
              <span
                className={`chat-avatar ${kind === "group" ? "chat-avatar-group" : ""}`}
                aria-hidden="true"
              >
                {kind === "group" ? "群" : numberOnly ? "人" : [...label][0]}
              </span>
              <span className="chat-title">
                <strong>{label}</strong>
                <small>
                  <span className={`chat-kind chat-kind-${kind}`}>
                    {kindLabel}
                  </span>{" "}
                  ·{" "}
                  {c.selected
                    ? demo
                      ? "演示已授权"
                      : "服务端已授权"
                    : "尚未授权"}
                  {numberOnly ? " · 未提供昵称" : ""}
                  {!c.selected && choiceExpired(c, clock)
                    ? " · 选项已过期"
                    : ""}
                </small>
              </span>
            </label>
          ),
        )}
        {!view.total && choices.length > 0 && (
          <p className="chat-no-results" role="status">
            没有符合筛选条件的已载入会话。修改筛选，或载入更多会话；已勾选项仍保留。
          </p>
        )}
      </div>
      <nav className="chat-pagination" aria-label="会话列表分页">
        <label>
          每页
          <select
            value={size}
            onChange={(e) => {
              setSize(Number(e.target.value));
              setPage(1);
            }}
          >
            <option value="8">8 个</option>
            <option value="16">16 个</option>
            <option value="24">24 个</option>
          </select>
        </label>
        <span>
          第 {view.page} / {view.pages} 页
        </span>
        <div className="chat-page-buttons">
          <button
            type="button"
            className="secondary"
            disabled={view.page <= 1}
            onClick={() => setPage(view.page - 1)}
          >
            上一页
          </button>
          <button
            type="button"
            className="secondary"
            disabled={view.page >= view.pages}
            onClick={() => setPage(view.page + 1)}
          >
            下一页
          </button>
        </div>
      </nav>
    </div>
  );
}
