import type { Change, ReplayApi, ReplaySnapshot } from "./workspace-api";

// The two implemented replay inputs are bound to this fictional fixture, not the selected row.
export const SAMPLE_ORDER_ID = "00000000-0000-4000-8000-000000000003";
export type ReplayState = {
  data: ReplaySnapshot | null;
  selected: string;
  loading: boolean;
  mutating: boolean;
  stale: boolean;
  error: string;
  notice: string;
  updatedAt: number;
};
export class ReplayStore {
  private state: ReplayState = {
    data: null,
    selected: "",
    loading: false,
    mutating: false,
    stale: true,
    error: "",
    notice: "",
    updatedAt: 0,
  };
  private listeners = new Set<() => void>();
  private controller: AbortController | null = null;
  private generation = 0;
  private active = false;
  private api: ReplayApi;
  private expired: () => void;
  private now: () => number;
  constructor(api: ReplayApi, expired: () => void, now = Date.now) {
    this.api = api;
    this.expired = expired;
    this.now = now;
  }
  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  private patch(value: Partial<ReplayState>) {
    this.state = { ...this.state, ...value };
    for (const listener of this.listeners) listener();
  }
  start() {
    this.active = true;
    void this.refresh();
  }
  dispose() {
    this.active = false;
    this.generation++;
    this.controller?.abort();
  }
  private failure(error: unknown) {
    if ((error as { code?: string })?.code === "UNAUTHENTICATED") {
      this.dispose();
      this.patch({
        data: null,
        selected: "",
        loading: false,
        mutating: false,
        stale: true,
        notice: "",
      });
      this.expired();
      return;
    }
    this.patch({
      loading: false,
      mutating: false,
      stale: true,
      error:
        error instanceof Error ? error.message : "数据读取失败，请刷新重试。",
    });
  }
  async refresh() {
    if (!this.active || this.state.mutating) return;
    this.controller?.abort();
    const controller = new AbortController();
    this.controller = controller;
    const generation = ++this.generation;
    this.patch({ loading: true });
    try {
      const data = await this.api.load(this.state.selected, controller.signal);
      if (!this.active || generation !== this.generation) return;
      this.patch({
        data,
        selected: data.selected,
        loading: false,
        stale: false,
        error: "",
        updatedAt: this.now(),
      });
    } catch (error) {
      if (
        this.active &&
        generation === this.generation &&
        !controller.signal.aborted
      )
        this.failure(error);
    }
  }
  poll() {
    if (!this.state.loading) void this.refresh();
  }
  select(id: string) {
    if (this.state.mutating || id === this.state.selected) return;
    this.patch({ selected: id, notice: "" });
    void this.refresh();
  }
  ready() {
    return (
      this.active &&
      !!this.state.data &&
      !this.state.stale &&
      !this.state.loading &&
      !this.state.mutating &&
      this.now() - this.state.updatedAt < 10000
    );
  }
  private async mutate(operation: () => Promise<string>) {
    if (!this.ready()) {
      if (!this.state.mutating) {
        this.patch({
          error: "请先刷新并核对最新数据，再执行操作。",
          stale: true,
        });
        void this.refresh();
      }
      return;
    }
    this.controller?.abort();
    const generation = ++this.generation;
    this.patch({ mutating: true, error: "", notice: "" });
    try {
      const notice = await operation();
      if (!this.active || generation !== this.generation) return;
      this.patch({ mutating: false, notice });
      await this.refresh();
    } catch (error) {
      if (this.active && generation === this.generation) {
        this.failure(error);
        // A rejected stale version needs a fresh snapshot, never a repeated write.
        if (
          ["VERSION_CONFLICT", "APPROVAL_STALE", "SCHEDULE_CONFLICT"].includes(
            (error as { code?: string })?.code ?? "",
          )
        ) {
          this.patch({
            notice:
              error instanceof Error ? error.message : "请重新核对当前提议。",
          });
          await this.refresh();
        }
      }
    }
  }
  replay(scenario: "reschedule" | "available", username: string) {
    if (username !== "merchant" || this.state.selected !== SAMPLE_ORDER_ID)
      return Promise.resolve();
    return this.mutate(async () =>
      (await this.api.replay(scenario))
        ? "这条样例已经处理过，没有重复创建消息、提议或待办。"
        : "样例消息已进入队列。请等待提议出现，正式安排尚未改变。",
    );
  }
  confirm(id: string) {
    const data = this.state.data;
    const change = data?.changes.find((c) => c.id === id);
    const order = data?.orders.find((o) => o.id === this.state.selected);
    if (
      !data ||
      data.selected !== this.state.selected ||
      !change ||
      !order ||
      !canConfirm(change, order.version, data.contextVersion)
    )
      return Promise.resolve();
    return this.mutate(async () => {
      await this.api.confirm(data, change);
      return "已确认并持久化工单、日历和待办。";
    });
  }
}

export function canConfirm(
  change: Change,
  orderVersion: number,
  contextVersion: number,
) {
  return (
    change.status === "proposed" &&
    change.conflict_ids.length === 0 &&
    change.base_work_order_version === orderVersion &&
    change.context_version === contextVersion
  );
}
export function changePresentation(change: Change, current: boolean) {
  if (change.status === "confirmed")
    return {
      label: "已确认",
      text: "已同步正式日历，旧自动待办已取消，并已生成新的准备事项。",
      warning: false,
    };
  if (change.status !== "proposed" || !current)
    return {
      label: "已失效，需复核",
      text: "业务或来源消息已经变化。这条历史提议不能再确认，请核对当前有效提议。",
      warning: true,
    };
  if (change.conflict_ids.length)
    return {
      label: "时间冲突",
      text: "该时段与另一项已确认预约重叠，不能确认。",
      warning: true,
    };
  return {
    label: "待商户确认",
    text: "确认后将同步正式日历，取消旧自动待办并生成新的准备事项。",
    warning: false,
  };
}
