import { apiBase } from "./environment.ts";
import { WorkspaceError } from "./workspace-api.ts";
export async function calendarFile(
  id: string,
  fetcher = fetch,
  signal?: AbortSignal,
) {
  let response: Response;
  try {
    response = await fetcher(
      `${apiBase()}/calendar-events/${encodeURIComponent(id)}.ics`,
      {
        credentials: "same-origin",
        cache: "no-store",
        signal: signal
          ? AbortSignal.any([signal, AbortSignal.timeout(10000)])
          : AbortSignal.timeout(10000),
      },
    );
  } catch {
    throw new WorkspaceError("UNAVAILABLE", "无法下载日历，请恢复连接后重试。");
  }
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new WorkspaceError(
      response.status === 401
        ? "UNAUTHENTICATED"
        : (error?.error?.code ?? "UNAVAILABLE"),
      response.status === 401
        ? "登录已过期，请重新登录。"
        : "预约已变化、未确认或不可导出，请刷新核对。",
    );
  }
  if (
    !/^text\/calendar(?:;|$)/i.test(response.headers.get("content-type") ?? "")
  )
    throw new WorkspaceError(
      "INVALID_RESPONSE",
      "服务没有返回日历文件，请联系维护者。",
    );
  const blob = await response.blob();
  const text = await blob.text();
  if (
    blob.size > 1024 * 1024 ||
    !text.startsWith("BEGIN:VCALENDAR\r\n") ||
    !text.endsWith("END:VCALENDAR\r\n")
  )
    throw new WorkspaceError("INVALID_RESPONSE", "日历文件无效，未进行下载。");
  return blob;
}
export function saveCalendar(blob: Blob, id: string) {
  const url = URL.createObjectURL(blob),
    link = document.createElement("a");
  link.href = url;
  link.download = `gigmate-${id}.ics`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
