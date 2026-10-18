import { localized } from "./i18n.ts";
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
  { title: string; reason: string }
> = localized({
  business_loop_reviewed: {
    title: "业务扩展与安全验收",
    reason: "本版已接通归单、延期、需求、工作时间、摘要、交付检查和归档。",
  },
  calendar_export: {
    title: "导出手机日历",
    reason: "需要本版后端提供只读日历下载接口。",
  },
  create_order: {
    title: "从会话新建工单",
    reason: "本版支持从已授权会话建单；需要引用客户原文并明确确认。",
  },
  order_status: {
    title: "开始、等待客户、完成和取消工单",
    reason: "本版支持状态操作；完成或取消会处理自动待办与未发送草稿。",
  },
  address_confirmation: {
    title: "确认地址和补齐缺项",
    reason: "本版支持确认时间和地址提议；仍未获客户确认的值会保持待确认。",
  },
  manual_assignment: {
    title: "人工归单与延期跟进",
    reason: "已接通当前消息归单、忽略及延期跟进；更改会重新核对来源和版本。",
  },
  business_sending: {
    title: "业务审批后发送及关联回执",
    reason:
      "已接通准确的审批与发送记录；需单独授权对应聊天，未知结果先核查，不自动重发。",
  },
  automatic_understanding: {
    title: "AI 文字理解",
    reason:
      "文字模型须由维护者在服务端配置、授权并核对费用。模型只提建议；媒体识别与独立现场验收另列，不代表自动建单。",
  },
});
export function loopReady(features: Features) {
  return features.business_loop_reviewed === true;
}
