import type { components } from "./generated/api";
export type Features = {
  [K in keyof components["schemas"]["WorkspaceCapabilities"]]: boolean;
};
export const unavailableFeatures: Features = {
  calendar_export: false,
  create_order: false,
  order_status: false,
  address_confirmation: false,
  manual_assignment: false,
  business_sending: false,
  automatic_understanding: false,
  business_loop_reviewed: false,
};
export const featureDescriptions: Record<
  keyof Features,
  { title: string; reason: string; issue: string }
> = {
  business_loop_reviewed: {
    title: "业务扩展与安全验收",
    reason: "PR32 页面已准备，后端交付并完成安全验收后才会出现操作入口。",
    issue: "29",
  },
  calendar_export: {
    title: "导出手机日历",
    reason: "需要本版后端提供只读日历下载接口。",
    issue: "12",
  },
  create_order: {
    title: "从会话新建工单",
    reason: "本版支持从已授权会话建单；需要引用客户原文并明确确认。",
    issue: "26",
  },
  order_status: {
    title: "开始、等待客户、完成和取消工单",
    reason: "本版支持状态操作；完成或取消会处理自动待办与未发送草稿。",
    issue: "27",
  },
  address_confirmation: {
    title: "确认地址和补齐缺项",
    reason: "本版支持确认时间和地址提议；仍未获客户确认的值会保持待确认。",
    issue: "29",
  },
  manual_assignment: {
    title: "人工归单与延期跟进",
    reason: "可查看原文和已有工单；归单、延期与跟进保存接口尚未交付。",
    issue: "29",
  },
  business_sending: {
    title: "业务审批后发送及关联回执",
    reason: "审批记录已可保存；C 业务审批与 A 的 WhatsApp 发送尚未接通。",
    issue: "29",
  },
  automatic_understanding: {
    title: "AI 自动理解、建单和真实 OCR／语音识别",
    reason: "B 的真实文字和媒体模型仍未启用；不能把没有提议当成已经理解。",
    issue: "29",
  },
};
export function featureLink(key: keyof Features) {
  const item = featureDescriptions[key];
  return `https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/${["26", "27"].includes(item.issue) ? "pull" : "issues"}/${item.issue}`;
}

export function loopReady(features: Features) {
  return features.business_loop_reviewed === true;
}
