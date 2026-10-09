import assert from "node:assert/strict";
import { test } from "node:test";
import {
  ReplayStore,
  SAMPLE_ORDER_ID,
  canConfirm,
  changePresentation,
} from "./src/replay-store.ts";

const flush = () => new Promise((resolve) => setImmediate(resolve));
const snapshot = (selected = SAMPLE_ORDER_ID) => ({
  orders: [{ id: selected, version: 3 }],
  selected,
  changes: [],
  messages: [],
  tasks: [],
  calendar: [],
  contextVersion: 4,
});
const proposal = (overrides = {}) => ({
  id: "change",
  work_order_id: SAMPLE_ORDER_ID,
  base_work_order_version: 3,
  context_version: 4,
  status: "proposed",
  conflict_ids: [],
  ...overrides,
});
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
function setup(overrides = {}, now) {
  const calls = { replay: 0, confirm: 0, expired: 0 };
  const api = {
    load: async (selected) => snapshot(selected || SAMPLE_ORDER_ID),
    replay: async () => {
      calls.replay++;
      return false;
    },
    confirm: async () => {
      calls.confirm++;
    },
    ...overrides,
  };
  const store = new ReplayStore(api, () => calls.expired++, now);
  store.start();
  return { store, calls, api };
}
test("late reads cannot undo a newer order selection, even when transport ignores abort", async () => {
  const reads = [];
  const { store } = setup({
    load: (selected, signal) => {
      const r = deferred();
      reads.push({ ...r, selected, signal });
      return r.promise;
    },
  });
  store.select("other");
  assert.equal(reads[0].signal.aborted, true);
  reads[1].resolve(snapshot("other"));
  await flush();
  reads[0].resolve(snapshot());
  await flush();
  assert.equal(store.getSnapshot().selected, "other");
  assert.equal(store.getSnapshot().data.selected, "other");
  store.dispose();
});
test("unmount ignores a late unauthorized response rather than expiring a new session", async () => {
  const read = deferred();
  const { store, calls } = setup({ load: () => read.promise });
  store.dispose();
  read.reject(Object.assign(new Error("expired"), { code: "UNAUTHENTICATED" }));
  await flush();
  assert.equal(calls.expired, 0);
});
test("authorization expiry clears the old data and stops later polling", async () => {
  const { store, calls, api } = setup();
  await flush();
  api.load = async () => {
    throw Object.assign(new Error("expired"), { code: "UNAUTHENTICATED" });
  };
  await store.refresh();
  store.poll();
  assert.equal(calls.expired, 1);
  assert.equal(store.getSnapshot().data, null);
  assert.equal(store.ready(), false);
});
test("offline reads retain a marked snapshot, block writes, and clear errors on recovery", async () => {
  const { store, calls, api } = setup();
  await flush();
  api.load = async () => {
    throw new Error("offline");
  };
  await store.refresh();
  assert.equal(store.getSnapshot().data.selected, SAMPLE_ORDER_ID);
  assert.equal(store.getSnapshot().stale, true);
  await store.replay("available", "merchant");
  assert.equal(calls.replay, 0);
  await flush();
  api.load = async () => snapshot();
  await store.refresh();
  assert.equal(store.getSnapshot().error, "");
  assert.equal(store.ready(), true);
  store.dispose();
});
test("fixed input is blocked on a different order/account and reports duplicate separately", async () => {
  const { store, calls, api } = setup();
  await flush();
  store.select("other");
  await flush();
  await store.replay("available", "merchant");
  store.select(SAMPLE_ORDER_ID);
  await flush();
  await store.replay("available", "other");
  assert.equal(calls.replay, 0);
  api.replay = async () => {
    calls.replay++;
    return true;
  };
  await store.replay("available", "merchant");
  assert.match(store.getSnapshot().notice, /已经处理过/);
  assert.equal(calls.replay, 1);
  store.dispose();
});
test("double click and selection during an unresolved mutation never dispatch a second write", async () => {
  const write = deferred();
  const { store, calls } = setup({
    replay: () => {
      calls.replay++;
      return write.promise;
    },
  });
  await flush();
  const first = store.replay("available", "merchant");
  await store.replay("available", "merchant");
  store.select("other");
  assert.equal(calls.replay, 1);
  assert.equal(store.getSnapshot().selected, SAMPLE_ORDER_ID);
  write.resolve(false);
  await first;
  assert.equal(store.getSnapshot().mutating, false);
  store.dispose();
});
test("unknown write outcome is not retried by background refresh", async () => {
  const { store, calls } = setup({
    replay: async () => {
      calls.replay++;
      throw new Error("结果暂无法确认");
    },
  });
  await flush();
  await store.replay("available", "merchant");
  assert.equal(store.getSnapshot().stale, true);
  await store.refresh();
  store.poll();
  await flush();
  assert.equal(calls.replay, 1);
  store.dispose();
});
test("a snapshot older than ten seconds requires a read before any write", async () => {
  let now = 1000;
  const { store, calls } = setup({}, () => now);
  await flush();
  now += 11000;
  await store.replay("available", "merchant");
  assert.equal(calls.replay, 0);
  await flush();
  store.dispose();
});
test("conflicting, invalidated and mismatched proposals cannot be confirmed", async () => {
  for (const change of [
    proposal({ conflict_ids: ["busy"] }),
    proposal({ status: "needs_review" }),
    proposal({ context_version: 3 }),
    proposal({ base_work_order_version: 2 }),
  ]) {
    assert.equal(canConfirm(change, 3, 4), false);
  }
  const { store, calls, api } = setup({
    load: async () => ({ ...snapshot(), changes: [proposal()] }),
  });
  await flush();
  await store.confirm("change");
  assert.equal(calls.confirm, 1);
  api.load = async () => ({
    ...snapshot(),
    changes: [proposal({ status: "confirmed" })],
  });
  await store.refresh();
  await store.confirm("change");
  assert.equal(calls.confirm, 1);
  store.dispose();
});
test("a version rejection reads the current proposal and never retries confirmation", async () => {
  const { store, calls } = setup({
    load: async () => ({ ...snapshot(), changes: [proposal()] }),
    confirm: async () => {
      calls.confirm++;
      throw Object.assign(new Error("请重新核对"), {
        code: "VERSION_CONFLICT",
      });
    },
  });
  await flush();
  await store.confirm("change");
  assert.equal(calls.confirm, 1);
  assert.equal(store.getSnapshot().stale, false);
  assert.match(store.getSnapshot().notice, /重新核对/);
  store.dispose();
});
test("confirmed and invalidated cards describe their completed or historical state", () => {
  assert.match(
    changePresentation(proposal({ status: "confirmed" }), false).text,
    /已同步/,
  );
  assert.match(
    changePresentation(proposal({ conflict_ids: ["busy"] }), false).label,
    /失效/,
  );
  assert.match(
    changePresentation(proposal({ conflict_ids: ["busy"] }), true).label,
    /冲突/,
  );
});
