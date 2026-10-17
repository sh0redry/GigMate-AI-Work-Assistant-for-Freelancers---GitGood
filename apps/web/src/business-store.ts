import { t } from "./i18n.ts";
import { stableShare, privateReadDenied } from "./read-cache.ts";
import {
  changeContext,
  type Change,
  type BusinessApi,
  type BusinessSnapshot,
} from "./workspace-api.ts";

export type BusinessState = {
  data: BusinessSnapshot | null;
  selected: string;
  loading: boolean;
  mutating: boolean;
  stale: boolean;
  error: string;
  notice: string;
  updatedAt: number;
};
export class BusinessStore {
  private state: BusinessState = {
    data: null,
    selected: "",
    loading: false,
    mutating: false,
    stale: true,
    error: "",
    notice: "",
    updatedAt: 0,
  };
  private checkedAt = 0;
  private reading = false;
  private listeners = new Set<() => void>();
  private controller: AbortController | null = null;
  private generation = 0;
  private active = false;
  private api: BusinessApi;
  private expired: () => void;
  private now: () => number;
  constructor(api: BusinessApi, expired: () => void, now = Date.now) {
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
  private patch(value: Partial<BusinessState>) {
    const next = stableShare(this.state, { ...this.state, ...value });
    if (next === this.state) return;
    this.state = next;
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
      ...(privateReadDenied(error) ? { data: null } : {}),
      loading: false,
      mutating: false,
      stale: true,
      error:
        error instanceof Error
          ? error.message
          : t("数据读取失败，请刷新重试。"),
    });
  }
  async refresh() {
    if (!this.active || this.state.mutating) return;
    this.controller?.abort();
    const controller = new AbortController();
    this.controller = controller;
    const generation = ++this.generation;
    this.reading = true;
    this.patch({
      loading:
        !this.state.data || this.state.data.selected !== this.state.selected,
    });
    try {
      const data = await this.api.load(this.state.selected, controller.signal);
      if (!this.active || generation !== this.generation) return;
      this.checkedAt = this.now();
      const next = stableShare(this.state.data, data);
      this.patch({
        data: next,
        selected: data.selected,
        loading: false,
        stale: false,
        error: "",
        updatedAt:
          next === this.state.data ? this.state.updatedAt : this.checkedAt,
      });
    } catch (error) {
      if (
        this.active &&
        generation === this.generation &&
        !controller.signal.aborted
      )
        this.failure(error);
    } finally {
      if (generation === this.generation) this.reading = false;
    }
  }
  poll() {
    if (!this.reading) void this.refresh();
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
      this.now() - this.checkedAt < 10000
    );
  }
  private async mutate(operation: () => Promise<string>) {
    if (!this.ready()) {
      if (!this.state.mutating) {
        this.patch({
          error: t("请先刷新并核对最新数据，再执行操作。"),
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
              error instanceof Error
                ? error.message
                : t("请重新核对当前提议。"),
          });
          await this.refresh();
        }
      }
    }
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
      !canConfirm(change, order.version, changeContext(data, change) ?? -1)
    )
      return Promise.resolve();
    return this.mutate(async () => {
      await this.api.confirm(data, change);
      return t(
        "已保存本次提议；仍需客户核实的信息保持待确认，日历与待办按确认状态更新。",
      );
    });
  }
}

export function canConfirm(
  change: Change,
  orderVersion: number,
  contextVersion: number,
) {
  return (
    ["schedule", "address"].includes(change.field) &&
    change.status === "proposed" &&
    change.conflict_ids.length === 0 &&
    change.base_work_order_version === orderVersion &&
    change.context_version === contextVersion
  );
}
export function changePresentation(change: Change, current: boolean) {
  if (
    current &&
    change.status === "needs_review" &&
    change.field === "schedule" &&
    (!change.new_value ||
      typeof change.new_value !== "object" ||
      !["timed", "date_only"].includes(change.new_value.kind))
  )
    return {
      label: t("待复核"),
      text: t(
        "时间尚不完整或格式需核对。请补充结束时间或时长，再生成可确认的日历提议。",
      ),
      warning: true,
    };
  if (change.status === "confirmed")
    return {
      label: t("已确认"),
      text:
        change.customer_confirmation === "confirmed"
          ? t("商户已接受此提议；日历与待办按工单的当前确认状态更新。")
          : t("商户已接受此值，仍等待客户核实；这不代表客户已经确认。"),
      warning: false,
    };
  if (change.status !== "proposed" || !current)
    return {
      label: t("已失效，需复核"),
      text: t(
        "业务或来源消息已经变化。这条历史提议不能再确认，请核对当前有效提议。",
      ),
      warning: true,
    };
  if (change.conflict_ids.length)
    return {
      label: t("时间冲突"),
      text: t("该时段与另一项已确认预约重叠，不能确认。"),
      warning: true,
    };
  return {
    label: t("待商户确认"),
    text: t(
      "商户接受后会保存此值；仍需客户核实的内容保持待确认，日历与准备待办按确认状态处理。",
    ),
    warning: false,
  };
}
