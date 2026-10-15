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
};
export const featureDescriptions: Record<
  keyof Features,
  { title: string; reason: string; issue: string }
> = {
  calendar_export: {
    title: "导出手机日历",
    reason: "需要本版后端提供只读日历下载接口。",
    issue: "12",
  },
  create_order: {
    title: "从会话新建工单",
    reason: "等待 C 修复并交付建单接口；目前可填写核对，不能保存。",
    issue: "26",
  },
  order_status: {
    title: "开始、等待客户、完成和取消工单",
    reason: "等待 C 的状态接口与建单修复一起验收。",
    issue: "27",
  },
  address_confirmation: {
    title: "确认地址和补齐缺项",
    reason: "当前正式确认接口只支持时间；地址和关键项规则等待 C 交付。",
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
