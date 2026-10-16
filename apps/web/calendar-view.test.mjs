import assert from "node:assert/strict";
import { test } from "node:test";
import {
  monthDays,
  shiftDay,
  shiftMonth,
  todayInHongKong,
  eventsForDay,
  exportProblem,
} from "./src/calendar-view.ts";
import { calendarFile } from "./src/calendar-api.ts";
import { triggerDescription } from "./src/approval-view.ts";
test("month keyboard movement covers leap days, year boundaries and Hong Kong midnight", () => {
  assert.equal(monthDays("2028-02").length, 42);
  assert.ok(monthDays("2028-02").includes("2028-02-29"));
  assert.equal(shiftDay("2028-02-28", 1), "2028-02-29");
  assert.equal(shiftMonth("2026-12", 1), "2027-01");
  assert.equal(shiftMonth("2027-01", -1), "2026-12");
  assert.equal(todayInHongKong(new Date("2026-10-15T16:05:00Z")), "2026-10-16");
});
test("cross-midnight appointments appear on both days with exclusive end, and date-only stays its original day", () => {
  const events = [
    {
      id: "1",
      schedule: {
        kind: "timed",
        start_at: "2026-10-15T15:30:00Z",
        end_at: "2026-10-15T17:00:00Z",
      },
    },
    {
      id: "2",
      schedule: {
        kind: "timed",
        start_at: "2026-10-15T14:00:00Z",
        end_at: "2026-10-15T16:00:00Z",
      },
    },
    {
      id: "3",
      schedule: {
        kind: "date_only",
        date: "2026-10-16",
        timezone: "America/New_York",
      },
    },
  ];
  assert.deepEqual(
    eventsForDay(events, "2026-10-15").map((e) => e.id),
    ["2", "1"],
  );
  assert.deepEqual(
    eventsForDay(events, "2026-10-16").map((e) => e.id),
    ["1", "3"],
  );
});
test("only current formal appointments on active orders can export", () => {
  const schedule = {
      kind: "timed",
      start_at: "2026-11-01T00:00:00Z",
      end_at: "2026-11-01T01:00:00Z",
      timezone: "Asia/Hong_Kong",
    },
    order = {
      version: 3,
      status: "confirmed",
      fields: {
        schedule: { status: "confirmed", value: schedule, sources: [] },
      },
    },
    event = {
      id: "e",
      work_order_version: 3,
      tentative: false,
      schedule,
      sources: [],
    };
  assert.equal(exportProblem(event, order), "");
  for (const changed of [
    { ...order, version: 2 },
    { ...order, status: "cancelled" },
    { ...order, status: "completed" },
  ])
    assert.ok(exportProblem(event, changed));
  assert.ok(exportProblem({ ...event, tentative: true }, order));
  assert.ok(exportProblem(event));
  assert.equal(
    exportProblem(event, { ...order, version: 4, status: "in_progress" }),
    "",
  );
  assert.ok(
    exportProblem(event, {
      ...order,
      fields: {
        schedule: {
          ...order.fields.schedule,
          sources: [{ message_id: "changed", message_revision: 2 }],
        },
      },
    }),
  );
});
test("calendar download uses authenticated same-origin read and rejects JSON/HTML/denied results", async () => {
  let request;
  const file = await calendarFile("synthetic-id", async (url, opts) => {
    request = { url, opts };
    return new Response("BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n", {
      headers: { "content-type": "text/calendar; charset=utf-8" },
    });
  });
  assert.ok(file.size);
  assert.equal(request.url, "/api/v1/calendar-events/synthetic-id.ics");
  assert.equal(request.opts.credentials, "same-origin");
  assert.equal(request.opts.cache, "no-store");
  for (const response of [
    new Response("<html>", { headers: { "content-type": "text/html" } }),
    Response.json({ error: { code: "VERSION_CONFLICT" } }, { status: 409 }),
  ])
    await assert.rejects(calendarFile("id", async () => response));
  await assert.rejects(
    calendarFile("id", async () => new Response("", { status: 401 })),
    { code: "UNAUTHENTICATED" },
  );
});
test("open-item reasons are explicit and malformed/extended triggers have a safe fallback", () => {
  assert.match(
    triggerDescription("open_items", ["missing_time", "verify_address"]),
    /只有日期.*等待客户核实地址/,
  );
  assert.match(
    triggerDescription("open_items:order:v3:missing_schedule,verify_address"),
    /等待客户提供日期和时间；等待客户核实地址/,
  );
  assert.match(triggerDescription("open_items:future"), /未确认的信息/);
  assert.match(triggerDescription("unknown"), /人工核对/);
});
