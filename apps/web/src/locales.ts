const conversationEnglish: Record<string, string> = {
  发送授权: "Sending permission",
  回复来源与附件类型: "Reply origin and attachment type",
  "固定内容政策（高级选项）": "Fixed-content policy (advanced)",
  "送达状态：": "Delivery status: ",
  客户会话: "Customer chats",
  "会话请求未完成，请恢复连接后核对原记录。":
    "Chat request could not be confirmed. Restore connectivity and check the original record.",
  "当前后端尚未提供此会话功能，请联系维护者升级。":
    "This backend does not provide this chat feature yet. Ask the maintainer to upgrade it.",
  "会话范围或分页响应无效，已停止显示。":
    "Chat scope or pagination is invalid. Display has been stopped.",
  "关联工单与 AI 建议": "Linked orders and AI suggestions",
  "一个聊天可以有多张工单，请明确选择本次业务。":
    "A chat can contain several orders. Select the job you are handling.",
  "仅展示本次有界查询结果，列表可能不完整。":
    "Only this bounded query is shown. The list may be incomplete.",
  刷新工单与建议: "Refresh orders and suggestions",
  选择关联工单: "Select a linked order",
  请选择本次工单: "Select the order for this task",
  "本次未找到关联工单。可先选择客户消息，再核对新建工单。":
    "No linked order was found in this query. Select customer messages to review a new order.",
  定位客户原话: "Locate customer source",
  查找原文并核对版本: "Find source and check its revision",
  打开工单处理: "Open order to handle it",
  "已有 AI 建议回复": "Existing AI reply suggestions",
  "这里只采用后端已有的有效模型建议；重新生成与自动润色尚未接通。":
    "Use existing valid model suggestions from the backend. Fresh generation and automatic polishing are not connected yet.",
  "先刷新核对建议；旧版后端可能尚未提供草稿接口。":
    "Refresh to check suggestions. Older backends may not provide the draft API.",
  "暂无可采用的有效 AI 建议，仍可手动回复。":
    "No valid AI suggestion is available. You can still reply manually.",
  核对建议回复: "Review suggested reply",
  "建议绑定当前工单和聊天，采用后仍需核对收件人与正文并批准发送。":
    "This suggestion is bound to the order and chat. Review the recipient and full body, then approve sending separately.",
  "采用到输入框（不发送）": "Use in composer (does not send)",
  "采用结果待核对，不会自动重复消费或发送。请查看原草稿记录。":
    "Adoption needs review. It will not consume again or send automatically. Check the original draft.",
  "采用建议会替换当前文字输入，但不会发送。继续吗？":
    "Using this suggestion replaces the current text without sending it. Continue?",
  "请先核对原发送记录，再采用新的回复。":
    "Check the original send record before using another reply.",
  "关联会话未授权或旧后端缺少映射，请核对连接与后端版本。":
    "The linked chat is not authorised, or this older backend lacks its mapping. Check the connection and version.",
  "消息更新超过本次显示上限，请核对近期消息；未声称历史完整。":
    "Updates exceed this window limit. Review recent messages; history is not claimed to be complete.",
  "原依据已修改或撤回，当前气泡不是原版本的有效确认依据。":
    "The source was edited or revoked. This bubble is not valid confirmation of the original revision.",
  "正在有界查找较早来源；历史快照不能代替客户确认。":
    "Searching a bounded window for earlier sources. Historical snapshots do not establish customer confirmation.",
  "本次窗口未找到该来源，请到工单核对记录或明确导入近期历史。":
    "Source not found in this window. Check the order record or explicitly import recent history.",
  "对话、回复与工单，在同一处。": "Chats, replies and orders in one place.",
  "仅显示已授权会话；新消息通常每 3 秒检查，历史可能不完整。":
    "Only authorised chats are shown. New messages are usually checked every 3 seconds; history may be incomplete.",
  连接与会话授权: "Connection and chat permissions",
  "当前安装没有可用连接，请先配置并授权工作会话。":
    "This installation has no available connection. Configure and authorise work chats first.",
  当前连接: "Current connection",
  搜索客户会话: "Search customer chats",
  个人聊天: "Direct chat",
  "没有已授权工作会话，请先选择并保存处理授权。":
    "No work chat is authorised. Select chats and save processing permission first.",
  尚无可显示消息: "No message available yet",
  "GigMate 内有新消息": "New messages in GigMate",
  "新消息标记仅属于 GigMate；查看不会自动发送 WhatsApp 已读回执。":
    "New-message markers belong to GigMate only. Viewing does not automatically send WhatsApp read receipts.",
  "选择客户，开始处理对话": "Choose a customer to handle the chat",
  "左侧选择已授权聊天，即可读取近期消息并准备回复。":
    "Select an authorised chat on the left to read recent messages and prepare a reply.",
  返回会话列表: "Back to chats",
  收起工单侧栏: "Hide order panel",
  显示工单侧栏: "Show order panel",
  刷新会话: "Refresh chat",
  "同步状态待核对，发送保持关闭。":
    "Sync status needs checking. Sending remains disabled.",
  "已同步至 {0}": "Synced at {0}",
  "当前连接未就绪，仍可核对已允许读取的记录。":
    "The connection is not ready. You can review records you are still permitted to read.",
  当前聊天消息: "Current chat messages",
  "已达本次窗口上限，请在连接页明确导入或核对更早记录。":
    "Window limit reached. Explicitly import or review earlier records on the connection page.",
  "尚无可显示消息；未接收的旧聊天不会自动补齐。":
    "No messages are available yet. Older chats not received here are not imported automatically.",
  "引用消息不在本次窗口内，请先加载更早消息。":
    "The quoted message is outside this window. Load earlier messages first.",
  查看引用消息: "View quoted message",
  附件预览与识别: "Attachment preview and extraction",
  引用回复: "Quote in reply",
  选作工单来源: "Select as order source",
  "查看 {0} 条新消息": "View {0} new messages",
  "已选 {0} 条有效客户来源": "Selected {0} valid customer sources",
  从所选消息核对新建工单: "Review a new order from selected messages",
  准备回复与核对发送: "Prepare reply and review sending",
  "当前后端缺少会话映射，工单关联保持关闭；仍可读取消息。":
    "This backend lacks the conversation mapping. Order linking remains disabled; messages can still be read.",
  在客户会话中查看原话: "View source in customer chat",
  返回客户会话: "Back to customer chat",
  "已带入会话和所选来源提示；请逐项核对，不会自动确认时间或地址。":
    "The chat and selected source hints are carried over. Review each field; no time or address is confirmed automatically.",
  从客户会话选中的原文: "Source selected in customer chat",
};

const conversationCantonese: Record<string, string> = {
  发送授权: "發送授權",
  回复来源与附件类型: "回覆來源同附件類型",
  "固定内容政策（高级选项）": "固定內容政策（進階選項）",
  "送达状态：": "送達狀態：",
  客户会话: "客人對話",
  "会话请求未完成，请恢复连接后核对原记录。":
    "對話請求未能確認，恢復連線後請核對原本記錄。",
  "当前后端尚未提供此会话功能，请联系维护者升级。":
    "目前後端未提供呢項對話功能，請聯絡維護者升級。",
  "会话范围或分页响应无效，已停止显示。":
    "對話範圍或者分頁回應無效，已停止顯示。",
  "关联工单与 AI 建议": "相關工單同 AI 建議",
  "一个聊天可以有多张工单，请明确选择本次业务。":
    "一個對話可以有幾張工單，請選清楚今次處理邊張。",
  "仅展示本次有界查询结果，列表可能不完整。":
    "只顯示今次有限範圍查詢結果，清單可能唔完整。",
  刷新工单与建议: "更新工單同建議",
  选择关联工单: "選擇相關工單",
  请选择本次工单: "請選擇今次工單",
  "本次未找到关联工单。可先选择客户消息，再核对新建工单。":
    "今次搵唔到相關工單，可以先揀客人訊息，再核對開新工單。",
  定位客户原话: "定位客人原話",
  查找原文并核对版本: "搵原文同核對版本",
  打开工单处理: "打開工單處理",
  "已有 AI 建议回复": "已有 AI 建議回覆",
  "这里只采用后端已有的有效模型建议；重新生成与自动润色尚未接通。":
    "呢度只採用後端已有嘅有效模型建議，重新生成同自動潤色仲未接通。",
  "先刷新核对建议；旧版后端可能尚未提供草稿接口。":
    "請先更新核對建議，舊版後端可能仲未提供草稿介面。",
  "暂无可采用的有效 AI 建议，仍可手动回复。":
    "暫時冇可用嘅有效 AI 建議，仍然可以手動回覆。",
  核对建议回复: "核對建議回覆",
  "建议绑定当前工单和聊天，采用后仍需核对收件人与正文并批准发送。":
    "建議綁定目前工單同對話，採用後仍要核對收件人同全文，再批准發送。",
  "采用到输入框（不发送）": "放入輸入框（唔發送）",
  "采用结果待核对，不会自动重复消费或发送。请查看原草稿记录。":
    "採用結果要核對，唔會自動重複採用或者發送，請查看原草稿記錄。",
  "采用建议会替换当前文字输入，但不会发送。继续吗？":
    "採用建議會取代目前輸入文字，但唔會發送。繼續嗎？",
  "请先核对原发送记录，再采用新的回复。":
    "請先核對原本發送記錄，再採用新回覆。",
  "关联会话未授权或旧后端缺少映射，请核对连接与后端版本。":
    "相關對話未授權，或者舊後端缺少對應資料，請核對連線同後端版本。",
  "消息更新超过本次显示上限，请核对近期消息；未声称历史完整。":
    "訊息更新超過今次顯示上限，請核對近期訊息；唔代表完整歷史。",
  "原依据已修改或撤回，当前气泡不是原版本的有效确认依据。":
    "原本依據已修改或者撤回，目前訊息唔係原版本嘅有效確認依據。",
  "正在有界查找较早来源；历史快照不能代替客户确认。":
    "正喺有限範圍搵較早來源，歷史快照唔可以代替客人確認。",
  "本次窗口未找到该来源，请到工单核对记录或明确导入近期历史。":
    "今次視窗搵唔到該來源，請到工單核對記錄，或者明確匯入近期歷史。",
  "对话、回复与工单，在同一处。": "對話、回覆同工單，喺同一處。",
  "仅显示已授权会话；新消息通常每 3 秒检查，历史可能不完整。":
    "只顯示已授權對話；通常每 3 秒檢查新訊息，歷史可能唔完整。",
  连接与会话授权: "連線同對話授權",
  "当前安装没有可用连接，请先配置并授权工作会话。":
    "目前安裝冇可用連線，請先設定同授權工作對話。",
  当前连接: "目前連線",
  搜索客户会话: "搜尋客人對話",
  个人聊天: "個人對話",
  "没有已授权工作会话，请先选择并保存处理授权。":
    "冇已授權工作對話，請先選擇同儲存處理授權。",
  尚无可显示消息: "暫時冇可顯示訊息",
  "GigMate 内有新消息": "GigMate 有新訊息",
  "新消息标记仅属于 GigMate；查看不会自动发送 WhatsApp 已读回执。":
    "新訊息標記只屬於 GigMate；查看唔會自動發送 WhatsApp 已讀回執。",
  "选择客户，开始处理对话": "選擇客人，開始處理對話",
  "左侧选择已授权聊天，即可读取近期消息并准备回复。":
    "喺左邊選擇已授權對話，就可以睇近期訊息同準備回覆。",
  返回会话列表: "返回對話清單",
  收起工单侧栏: "收起工單側欄",
  显示工单侧栏: "顯示工單側欄",
  刷新会话: "更新對話",
  "同步状态待核对，发送保持关闭。": "同步狀態有待核對，發送保持關閉。",
  "已同步至 {0}": "已同步至 {0}",
  "当前连接未就绪，仍可核对已允许读取的记录。":
    "目前連線未準備好，仍可核對獲准讀取嘅記錄。",
  当前聊天消息: "目前對話訊息",
  "已达本次窗口上限，请在连接页明确导入或核对更早记录。":
    "已到今次視窗上限，請喺連線頁明確匯入或者核對較早記錄。",
  "尚无可显示消息；未接收的旧聊天不会自动补齐。":
    "暫時冇可顯示訊息；未接收嘅舊對話唔會自動補齊。",
  "引用消息不在本次窗口内，请先加载更早消息。":
    "引用訊息唔喺今次視窗內，請先載入較早訊息。",
  查看引用消息: "查看引用訊息",
  附件预览与识别: "附件預覽同識別",
  引用回复: "引用回覆",
  选作工单来源: "選作工單來源",
  "查看 {0} 条新消息": "查看 {0} 條新訊息",
  "已选 {0} 条有效客户来源": "已揀 {0} 條有效客人來源",
  从所选消息核对新建工单: "由所選訊息核對開新工單",
  准备回复与核对发送: "準備回覆同核對發送",
  "当前后端缺少会话映射，工单关联保持关闭；仍可读取消息。":
    "目前後端缺少對話對應資料，工單關聯保持關閉；仍可讀取訊息。",
  在客户会话中查看原话: "喺客人對話查看原話",
  返回客户会话: "返回客人對話",
  "已带入会话和所选来源提示；请逐项核对，不会自动确认时间或地址。":
    "已帶入對話同所選來源提示；請逐項核對，唔會自動確認時間或者地址。",
  从客户会话选中的原文: "喺客人對話揀嘅原文",
};

// UI copy only. Customer content and approved payloads are never translated.
export const english: Record<string, string> = {
  ...conversationEnglish,

  "读取期间登录、授权或数据发生变化，请刷新并核对会话授权。":
    "Your session, permissions, or data changed during this read. Refresh and check conversation permissions.",
  "聊天、授权或工单已变化，这条旧提议不能直接确认。":
    "The conversation, permissions, or order changed. This old proposal cannot be confirmed directly.",

  功能状态与操作入口: "Feature status and shortcuts",
  现在可以使用: "Available now",
  状态未核实: "Status unverified",
  当前服务未启用: "Not enabled on this service",
  打开此功能: "Open feature",
  "这条会话没有开放工单。新需求可以从这里手动建单。":
    "This conversation has no open orders. You can create an order for a new request here.",
  为这条会话新建工单: "Create an order for this conversation",
  处理这条消息: "Resolve this message",
  "归单会重新生成待核对提议；忽略只表示这条消息无需处理。手动建单不会自动清除此复核事项。":
    "Assigning queues this message for new proposals to review. Dismissing marks it as requiring no action. Manual order creation does not automatically resolve this review item.",
  "这条记录不是当前可处理轮次，或原文尚未核实。请刷新并处理最新记录。":
    "This record is not currently actionable, or its source has not been verified. Refresh and use the latest record.",
  "模型调用结果未知，只能核查原请求或明确忽略，不能重新归单调用。":
    "The model result is unknown. Check the original request or explicitly dismiss; do not assign it for another model call.",

  "时间尚不完整或格式需核对。请补充结束时间或时长，再生成可确认的日历提议。":
    "The time is incomplete or needs review. Provide an end time or duration before creating a calendar proposal you can confirm.",
  "跟进时间无效，请输入完整有效的香港日期和时间。":
    "Invalid follow-up time. Enter a complete, valid Hong Kong date and time.",
  "当前后端版本未提供此功能。":
    "This backend version does not provide this feature.",
  业务工作台: "Workspace",
  新建工单: "New order",
  回复审批: "Reply approvals",
  日历与待办: "Calendar & tasks",
  人工复核: "Review queue",
  "WhatsApp 连接": "WhatsApp connection",
  功能与使用说明: "Features & help",
  业务管理: "Business management",
  "登录已过期，请重新登录。": "Your session expired. Please sign in again.",
  "后端能力状态不完整，请联系维护者更新服务。":
    "The server's feature information is incomplete. Ask the maintainer to update it.",
  无法读取功能状态: "Cannot read feature availability.",
  "登录失败，请重试。": "Sign-in failed. Please try again.",
  "已退出。": "Signed out.",
  "已退出，请重新登录。": "Signed out. Please sign in again.",
  "暂时无法退出，请重试。": "Cannot sign out yet. Please try again.",
  旧入口已停用: "This old entry is no longer available",
  "本版只连接维护者配置的业务服务。为避免旧地址意外切换数据，请确认服务地址后再打开工作台。旧操作记录不会自动搬运。":
    "This version connects to the configured business service. Verify the address before opening the workspace. Old operation records are not transferred automatically.",
  打开当前工作台: "Open the current workspace",
  跳到主要内容: "Skip to main content",
  跟單: "跟單",
  把业务安排清楚: "Keep your work in order",
  退出: "Sign out",
  为独立工作者整理每一次约定: "Every agreement, organised for independent work",
  "从聊天里的约定，": "From promises in a chat,",
  "到日历上的安排。": "to plans in your calendar.",
  "核对客户原文、管理工单和回复审批，让下一步清楚可见。":
    "Review customer messages, manage orders and approve replies. Know your next step.",
  "登录后可查看功能状态；未接通的能力会明确标注。":
    "Sign in to see availability. Features that are not connected are clearly marked.",
  "登录 GigMate": "Sign in to GigMate",
  "使用维护者为你配置的账号。": "Use the account provided by your maintainer.",
  账号: "Username",
  密码: "Password",
  "正在登录…": "Signing in…",
  进入工作台: "Open workspace",
  "这是 GigMate 的账号，不是 WhatsApp 手机账号。没有账号或忘记密码时，请联系维护者。":
    "This is your GigMate account, separate from your WhatsApp phone account. Contact the maintainer if you need an account or password help.",
  工作台页面: "Workspace pages",
  我的工作空间: "My workspace",
  收起: "Less",
  更多: "More",
  "每一份约定，清楚有序。": "Every agreement, clearly organised.",
  "暂时无法核对后端功能状态，依赖功能保持关闭。请在功能说明页查看详情。":
    "Cannot verify server features. Dependent operations remain unavailable. See the help page.",
  "安排好，下一步。": "Ready for your next step.",
  "从客户原文到正式安排，每一步都由你确认。":
    "From the customer's words to a formal arrangement, you confirm each step.",
  "批准后，请到业务管理核对准确正文并提交发送。需先在连接页单独授权对应聊天；批准和提交都不代表客户已收到。":
    "After approval, review the exact text in Business management and submit it for sending. Authorise that chat separately on the connection page. Approval and submission do not prove receipt.",
  "手动发送网关已提供，需要单独发送授权。AI 润色、业务审批直发与自由生成自动回复尚未接通。":
    "Manual sending requires separate permission. AI polishing and freely generated automatic replies are not available.",
  "你的聊天由你授权；正式安排需要确认。批准、发送与客户确认是不同步骤。":
    "You authorise chat access and confirm formal arrangements. Approval, sending and customer confirmation are separate steps.",
  "暂时无法读取审批列表，请刷新。": "Cannot read approvals. Please refresh.",
  "草稿、工单或原文已更新，请重新核对。":
    "The draft, order or source changed. Please review it again.",
  "请先读取草稿。": "Read the draft first.",
  "批准已保存；消息尚未提交发送。":
    "Approval saved. The message has not been submitted for sending.",
  "新的待审批草稿已生成，需要再次核对批准。":
    "A new draft is ready and needs a fresh review and approval.",
  "操作结果已确认，正在重新读取当前状态。":
    "The operation result is verified. Reading the current state.",
  "操作结果暂未确认，请核对原请求。":
    "The result is not verified yet. Check the original request.",
  回复审批工作台: "Reply approval workspace",
  "先核对收件会话和正文，再批准。":
    "Review the recipient and full text before approving.",
  "这里保存你的批准决定。当前尚未接通 WhatsApp 发送；批准不等于已发送。":
    "This page records your approval. Submit the approved reply separately in Business management; approval does not mean sent.",
  "正在读取审批数据…": "Reading approvals…",
  "没有你的明确批准，草稿不会执行。":
    "Drafts require your explicit approval before execution.",
  "下面是上次读取的数据，当前不能提交操作。":
    "Showing the last read. Operations are unavailable until current state is verified.",
  有一笔原请求等待核对: "An original request needs checking",
  "刷新只读取状态，不会再次批准。核对这份草稿后，可用原请求、原版本和原编号核对结果；不会创建另一笔请求。":
    "Refresh only reads status; it does not approve again. Review the original draft and check with the same request, version and ID. No new request is created.",
  查看待核对原请求: "View the original request",
  "内容更新于：{0}": "Content updated: {0}",
  尚未读取: "Not read yet",
  刷新审批: "Refresh approvals",
  草稿与历史: "Drafts & history",
  审批筛选: "Filter approvals",
  全部历史: "All history",
  "当前选择不在筛选结果中，右侧仍保留该草稿。":
    "The selected draft is outside this filter and remains open on the right.",
  "此筛选下没有草稿。": "No drafts match this filter.",
  "等待审批列表。": "Waiting for the approval list.",
  "新的回复草稿会显示在这里，请稍后刷新；没有草稿不代表已经发送。":
    "New drafts appear here. Refresh later. No draft does not mean a message was sent.",
  所属工单未载入: "Order not loaded",
  有效至: "Valid until",
  "选择一份草稿，查看收件会话、正文和原文依据。":
    "Select a draft to see its recipient, text and source evidence.",
  当前工单: "Current order",
  为什么需要回复: "Why a reply is needed",
  "收件会话（系统编号）": "Recipient conversation (internal ID)",
  "这是当前工单关联的会话；实际 WhatsApp 收件人映射和发送桥接尚未接通。":
    "This conversation belongs to the order. The server resolves the exact WhatsApp chat when submitting in Business management.",
  草稿正文: "Draft text",
  有效期: "Expiry",
  "（已到期）": "(expired)",
  版本核对: "Check versions",
  草稿第: "Draft revision",
  "版；工单": "; order",
  "→ 当前": "→ current",
  未知: "Unknown",
  "；聊天": "; conversation",
  不可读取: "Unavailable",
  "关闭原因：": "Closed because:",
  "后端已关闭此草稿，请核对当前业务。":
    "The server closed this draft. Review the current order.",
  "你记录的原因：": "Your recorded reason:",
  "批准时间：": "Approved at:",
  原文依据: "Source evidence",
  消息: "Message",
  "· 第": "· revision",
  "版 ·": "·",
  该版本不可读取: "This revision is unavailable",
  "原文已撤回，不能据此批准。":
    "The source was revoked and cannot support approval.",
  原文未提供文字: "No text was provided",
  "没有可核对的原文，不补造内容。":
    "No readable source is available. Missing content is not invented.",
  核对这份草稿: "Review this draft",
  本次核对: "This review",
  "接收会话：": "Recipient conversation:",
  "我已核对收件会话、完整正文、原文与版本。":
    "I reviewed the recipient, full text, sources and versions.",
  "拒绝／取消原因": "Reason for rejection / cancellation",
  "例如：需要先和客户确认其他时间":
    "For example: confirm another time with the customer first",
  核对后重试原请求: "Check the original request again",
  批准这份草稿: "Approve this draft",
  拒绝草稿: "Reject draft",
  取消待执行草稿: "Cancel pending draft",
  重新生成待审批问题: "Generate a new question draft",
  "拒绝和取消只关闭本机尚未执行的草稿；执行中的发送不能假装撤回。重新提问会生成新草稿，不会直接发送。":
    "Reject or cancel only closes a draft that has not executed locally. An in-flight send cannot be recalled this way. A new question creates a draft and does not send it.",
  "执行结果由后端核对。此页面不会重新发送消息。":
    "The server checks execution results. This page does not resend messages.",
  草稿归属无法核对: "Cannot verify draft ownership",
  来源范围无法核对: "Cannot verify source scope",
  连接归属无法核对: "Cannot verify connection ownership",
  "所选连接没有唯一对应的已授权聊天，请回连接页核对。":
    "This connection has no unique authorised chat for the conversation. Check it on the connection page.",
  "发送记录归属或正文不一致，不能使用此关联":
    "The linked send has a different owner or text and cannot be used.",
  归单与业务回复: "Assignment & business replies",
  读取当前归单与回复: "Read current assignments and replies",
  人工归单: "Assign messages",
  待复核消息: "Message awaiting review",
  选择一条: "Select one",
  会话: "Conversation",
  当前原文: "Current source messages",
  已撤回: "Revoked",
  归入工单: "Assign to order",
  选择已有开放工单: "Select an existing open order",
  核对归单: "Review assignment",
  "将当前会话 v{0} 的这条消息归入“{1}”，仅记录归属，不自动确认业务字段。":
    "Assign this message from conversation v{0} to “{1}”. This records assignment only and does not confirm order fields.",
  标记无需归单: "Mark as no assignment needed",
  "将当前会话 v{0} 的这条消息标记为无需归单，不创建工单，不发送回复。":
    "Mark this message from conversation v{0} as not requiring assignment. No order is created and no reply is sent.",
  修改回复与发送记录: "Edit replies & check sending",
  业务草稿: "Business draft",
  选择草稿: "Select a draft",
  收件会话: "Recipient conversation",
  "· 有效至": "· valid until",
  修改正文: "Edit text",
  核对修改草稿: "Review draft changes",
  "修改发给会话 {0} 的第 {1} 版草稿，新正文：“{2}”。保存后生成新版本，仍需另行批准，不会发送。":
    "Edit revision {1} for conversation {0}. New text: “{2}”. Saving creates a new revision that still needs approval; it does not send.",
  发送连接: "Sending connection",
  选择已授权连接: "Select an authorised connection",
  "需先在 WhatsApp 连接页授权此会话发送；这里不会扩大授权范围。":
    "Authorise sending for this chat on the WhatsApp page first. This page does not expand permission.",
  核对并提交业务发送: "Review and submit business reply",
  "把已批准草稿 r{0} 交给连接 {1}，收件会话 {2}，完整正文：“{3}”。连接 v{4}／发送授权 v{5}。提交不代表客户收到；结果未知时先核对，禁止另建发送。":
    "Submit approved draft r{0} to connection {1}, recipient conversation {2}. Full text: “{3}”. Connection v{4} / sending permission v{5}. Submission does not prove receipt. Check unknown outcomes; do not create another send.",
  "已通过当前账号核对关联回执：": "Linked receipt verified for this account:",
  "。取消、对账或人工核查请到 WhatsApp 消息页选择此记录":
    ". For cancellation, reconciliation or manual checking, select this record on the WhatsApp messages page:",
  操作无法核对: "Cannot verify this operation",
  "保存结果已确认，正在读取当前状态。":
    "Saved result verified. Reading current state.",
  工单归属无法核对: "Cannot verify order ownership",
  掌握每一步: "Know every step",
  "今日事项、工作时间、客户需求和交付核对。":
    "Today's work, working hours, customer requirements and delivery checks.",
  刷新业务管理: "Refresh business management",
  今日概览: "Today at a glance",
  今天要做: "To do today",
  等待客户: "Waiting for customers",
  即将到期: "Due soon",
  需要决定: "Needs a decision",
  查看工单: "Open order",
  暂无事项: "Nothing here yet",
  工作时间与排期设置: "Working hours & scheduling",
  时区: "Time zone",
  开始时间: "Start time",
  结束时间: "End time",
  默认预约分钟: "Default appointment minutes",
  预约间隔分钟: "Gap between appointments (minutes)",
  准备提前分钟: "Preparation lead time (minutes)",
  工作日: "Working days",
  一: "Mon",
  二: "Tue",
  三: "Wed",
  四: "Thu",
  五: "Fri",
  六: "Sat",
  日: "Sun",
  周: "Weekday",
  休息时段: "Breaks",
  "休息开始 {0}": "Break starts {0}",
  "休息结束 {0}": "Break ends {0}",
  移除: "Remove",
  添加休息时段: "Add break",
  核对排期设置: "Review schedule settings",
  "更新排期 v{0}：{1}，周{2}，{3}–{4}，休息 {5}；预约 {6} 分钟、间隔 {7} 分钟、提前准备 {8} 分钟。":
    "Update schedule v{0}: {1}, days {2}, {3}–{4}, breaks {5}; appointments {6} min, gaps {7} min, preparation {8} min ahead.",
  工单需求与交付: "Requirements & delivery",
  选择工单: "Select order",
  请选择: "Please select",
  排期核对: "Schedule check",
  "当前没有检测到排期风险。": "No scheduling risks detected.",
  "候选时间，仍须与客户核实":
    "Candidate times: confirm with the customer first",
  交付检查: "Delivery checklist",
  待完成: "Unfinished",
  已核对: "Reviewed",
  "目前检查项齐全。": "All checklist items are currently covered.",
  "请先处理未完成事项；确需结束时必须明确确认。":
    "Resolve unfinished items first. Closing anyway requires explicit acknowledgement.",
  "本次客户原文依据（主会话）":
    "Customer source for this operation (primary conversation)",
  业务操作原文: "Source for business operation",
  先选择当前客户消息: "Select a current customer message first",
  无文字: "No text",
  客户稍后确认: "Customer will confirm later",
  待确认项目: "Item awaiting confirmation",
  地址: "Address",
  时间: "Time",
  "跟进时间（香港时间；留空则按后端默认）":
    "Follow-up time (Hong Kong time; leave blank for server default)",
  核对延期跟进: "Review deferred follow-up",
  "工单 v{0}：客户稍后确认{1}，{2} 跟进；依据“{3}”。保留缺项，暂停对此项的追问。":
    "Order v{0}: the customer will confirm {1} later. Follow up {2}; source: “{3}”. Keep the field missing and pause questions about it.",
  "添加资料、承诺或问题": "Add material, commitment or question",
  类型: "Type",
  所需资料: "Required material",
  双方承诺: "Commitments",
  未决问题: "Open question",
  由谁完成: "Who is responsible",
  客户: "Customer",
  商户: "Merchant",
  内容: "Content",
  "期限（可留空）": "Deadline (optional)",
  核对新增条目: "Review new item",
  "工单 v{0}：{1}负责“{2}”，期限 {3}。依据“{4}”；资料与承诺将按规则生成待办。":
    "Order v{0}: {1} is responsible for “{2}”, due {3}. Source: “{4}”. Materials and commitments may generate tasks under the rules.",
  未完成: "Open",
  已完成: "Completed",
  已取消: "Cancelled",
  标记已完成: "Mark completed",
  取消此条目: "Cancel this item",
  "工单 v{0}：将“{1}”标记为{2}，关联待办同步收尾。":
    "Order v{0}: mark “{1}” as {2}. Update its linked task too.",
  拒绝提议的原因: "Reason for rejecting the proposal",
  提议: "Proposed",
  已确认: "Confirmed",
  仍待核实: "Still needs verification",
  "· 工单 v": "· order v",
  接受此提议: "Accept proposal",
  "工单 v{0}／会话 v{1}：接受{2}“{3}”。客户未确认的值仍保持待核实。":
    "Order v{0} / conversation v{1}: accept {2} “{3}”. Information not confirmed by the customer remains pending.",
  拒绝此提议: "Reject proposal",
  "工单 v{0}：拒绝{1}提议，原因“{2}”。保留原安排及历史。":
    "Order v{0}: reject the {1} proposal because “{2}”. Keep the original arrangement and history.",
  检查后结束工单: "Finish order after checking",
  "完成“{0}” v{1}。{2} 自动待办收尾、释放时段，保留历史。":
    "Complete “{0}” v{1}. {2} Close generated tasks, release the time slot and keep history.",
  归档此工单: "Archive this order",
  "归档已结束的“{0}” v{1}，保留历史，不删除数据。":
    "Archive closed order “{0}” v{1}. Keep history; do not delete data.",
  "日历文件已下载，请在自己的日历中确认导入。改期后需重新导入或手动更新。":
    "Calendar file downloaded. Confirm import in your own calendar. Rescheduling requires reimporting or manually updating it.",
  导出失败: "Export failed",
  个人安排: "Personal schedule",
  "所有时刻按香港时间显示；只有日期的安排保留原日期与时区。":
    "Times are shown in Hong Kong time. Date-only arrangements keep their original date and time zone.",
  刷新安排: "Refresh schedule",
  日历显示方式: "Calendar view",
  月历: "Month",
  全部安排: "All appointments",
  "显示已完成／取消工单的日历历史":
    "Show calendar history for completed / cancelled orders",
  上个月: "Previous month",
  " 年 ": " / ",
  月: "month",
  下个月: "Next month",
  今天: "Today",
  "选择日期，可用方向键移动，Home／End 跳到本周首尾":
    "Select a date. Use arrow keys to move, or Home / End for the start / end of the week.",
  "{0}，{1} 项安排": "{0}, {1} appointments",
  项安排: "appointments",
  "{0} 的安排": "Schedule for {0}",
  "正在核对最新安排…": "Checking the latest schedule…",
  "该范围没有安排，可切换日期或查看历史。":
    "No appointments in this range. Change the date or show history.",
  "还没有日历安排。正式确认工单时间后会出现在这里。":
    "No calendar entries yet. They appear when you confirm an order's schedule.",
  暂定: "Tentative",
  正式: "Formal",
  工单不可用: "Order unavailable",
  待核对: "Needs review",
  "· 缓冲": "· buffer",
  分钟: "minutes",
  "地点：": "Location:",
  "正在下载…": "Downloading…",
  "加入我的日历 (.ics)": "Add to my calendar (.ics)",
  "当前后端尚未提供日历下载接口。":
    "This server does not provide calendar downloads yet.",
  "导出会下载包含业务标题、时间和已确认地址的文件。请妥善保存。手机／Google／Outlook 日历由你自行导入，改期不会自动同步；重复导入可能产生重复安排。":
    "The export contains the title, time and confirmed address. Store it privately. Import it into your phone / Google / Outlook calendar yourself. Rescheduling does not sync automatically and repeated imports may create duplicates.",
  全部工单待办: "Tasks across orders",
  待办范围: "Task filter",
  待处理与受阻: "Pending & blocked",
  关联工单不可用: "Linked order unavailable",
  "截止：": "Due:",
  "依赖：": "Depends on:",
  未载入的待办: "Task not loaded",
  无: "None",
  查看相关工单: "Open related order",
  "该范围暂无待办。": "No tasks match this filter.",
  "待办会随已确认安排更新。手动完成／编辑待办的后端接口尚未提供，本版只读。":
    "Tasks follow confirmed arrangements. Complete or cancel them in Business management; customer confirmation remains separate.",
  搜索已载入会话: "Search loaded chats",
  会话名称或号码: "Chat name or number",
  会话类型: "Chat type",
  全部: "All",
  个人聊天: "Direct chats",
  群聊: "Groups",
  已授权: "Authorised",
  类型未提供: "Type unavailable",
  "名称和类型由接入服务提供；仅提供号码时不会猜测昵称。可重新发现会话刷新名称。":
    "Names and types come from the connector. A number is not treated as a guessed nickname. Discover chats again to refresh names.",
  显示: "Showing",
  "个结果 · 已载入": "results · loaded",
  "个会话 · 已勾选": "chats · selected",
  "个（含其他页）": "(including other pages)",
  "{0} · {1} · 会话 {2}": "{0} · {1} · chat {2}",
  群: "Group",
  人: "Person",
  已保存授权: "Authorisation saved",
  尚未授权: "Not authorised",
  " · 未提供昵称": " · No nickname",
  " · 选项已过期": " · Option expired",
  "没有符合筛选条件的已载入会话。修改筛选，或载入更多会话；已勾选项仍保留。":
    "No loaded chats match this filter. Change the filter or load more. Your selections remain saved.",
  会话列表分页: "Chat list pages",
  每页: "Per page",
  "8 个": "8",
  "16 个": "16",
  "24 个": "24",
  第: "Page",
  页: " ",
  上一页: "Previous",
  下一页: "Next",
  状态未知: "Status unknown",
  已连接: "Connected",
  正在连接: "Connecting",
  已断开: "Disconnected",
  连接失败: "Connection failed",
  等待扫码: "Waiting for scan",
  连接未启动: "Connection not started",
  需要在手机确认: "Confirm on your phone",
  "授权或连接已在其他窗口更新，请重新载入后核对。":
    "Connection or permission changed in another window. Reload and review it.",
  "聊天选项已过期，请重新发现会话后核对选择。":
    "Chat choices expired. Discover chats again and review your selection.",
  "连接操作结果未知，请明确核对；不要重复重连。":
    "Connection result unknown. Check it explicitly; do not reconnect repeatedly.",
  "请求结果待确认，请刷新状态或使用原请求重试。":
    "Request result unverified. Refresh status or check with the original request.",
  "服务响应未能完整读取，请刷新并核对状态。":
    "The response was incomplete. Refresh and check status.",
  "消息接收已暂停，可撤销已有授权；恢复后再发现新会话。":
    "Reception is paused. Existing permission can be revoked. Resume before discovering new chats.",
  "上次会话发现未完成，核对后可重新发现最近会话。":
    "The last discovery did not finish. Review it before discovering recent chats again.",
  "已有操作正在处理，请刷新状态，暂勿重复提交。":
    "An operation is already processing. Refresh status; do not submit again.",
  "操作仍在处理中，请刷新状态，暂勿重复提交。":
    "The operation is still processing. Refresh status; do not submit again.",
  "操作已取消，请刷新并核对后再决定下一步。":
    "The operation was cancelled. Refresh and check before deciding the next step.",
  "操作未完成，请检查接入服务并核对状态。":
    "The operation did not finish. Check the connector and current state.",
  "接入后端未配置，请先准备本地接入服务。":
    "The connector backend is not configured. Set up the local service first.",
  "接入配置不匹配，请检查后端私有配置。":
    "Connector settings do not match. Check the server's private configuration.",
  "扫码服务尚未配置，请联系维护者。":
    "QR service is not configured. Contact the maintainer.",
  "连接配置与账号不匹配，请联系接入负责人检查。":
    "The connection does not belong to this account's configuration. Contact the integration maintainer.",
  "WhatsApp 会话尚未创建，请先准备本机服务后刷新。":
    "The WhatsApp session has not been created. Set up the local service and refresh.",
  "WhatsApp 服务暂不可用，请检查服务后刷新。":
    "WhatsApp is temporarily unavailable. Check the service and refresh.",
  "本机会话未启动或服务引擎信息不匹配，请联系接入负责人恢复服务后刷新。":
    "The local session is stopped or the engine information differs. Ask the maintainer to restore it, then refresh.",
  "二维码已失效或扫码完成，请刷新状态。":
    "The QR code expired or pairing finished. Refresh status.",
  "WhatsApp 尚未连接，连接后才能发现新会话。":
    "Connect WhatsApp before discovering new chats.",
  "授权已在其他窗口更新。请重新载入并核对，再保存。":
    "Permission changed in another window. Reload and review before saving.",
  "会话选项已过期。请重新载入并核对，再保存。":
    "Chat choices expired. Reload and review before saving.",
  "登录已过期，请退出后重新登录。":
    "Your session expired. Sign out and sign in again.",
  "无法读取本机扫码服务，请检查 Docker 和本地环境后刷新。":
    "Cannot read the local QR service. Check Docker and the local setup, then refresh.",
  "正在获取本机二维码，请稍后刷新。":
    "Getting a local QR code. Refresh shortly.",
  "当前连接与本机配置不匹配，请联系接入负责人检查。":
    "This connection differs from the local configuration. Contact the integration maintainer.",
  "扫码服务尚未准备好，请联系维护者后刷新。":
    "The QR service is not ready. Contact the maintainer and refresh.",
  "连接授权已暂停，二维码已隐藏。":
    "Connection permission is paused. The QR code is hidden.",
  "未找到项目 Python 环境，请按本地启动指南准备 .venv。":
    "Project Python environment missing. Set up .venv using the local guide.",
  "项目 Python 依赖缺失，请按本地启动指南安装锁定依赖。":
    "Project Python dependencies missing. Install the locked dependencies using the guide.",
  "本机操作验证失败，请退出后重新登录。":
    "Local operation validation failed. Sign out and sign in again.",
  "重连结果尚不确定。请刷新状态核对，不要重复重连；仍无法确认时请联系接入负责人。":
    "Reconnection result is uncertain. Refresh and check; do not reconnect again. Contact the maintainer if it stays unclear.",
  "操作结果尚不确定，请刷新状态核对，暂勿重复操作。":
    "Operation result uncertain. Refresh and check; do not repeat it yet.",
  "会话状态已变化，无需重连。请刷新状态。":
    "The session changed and does not need reconnection. Refresh status.",
  "刚刚已请求重连，请等待至少 30 秒并刷新状态。":
    "Reconnection was just requested. Wait at least 30 seconds and refresh status.",
  "所选故障尚未恢复，不能清除。请刷新后检查。":
    "The selected incidents have not recovered and cannot be cleared. Refresh and check.",
  "请先核对故障时段，并确认无需导入历史消息。":
    "Review the interruption period and confirm that no history import is needed first.",
  "此故障已有其他核对结论，请刷新后检查，不能覆盖原结论。":
    "Another decision already exists for this incident. Refresh and check; the original decision cannot be overwritten.",
  监测中断时段: "Monitoring interruption",
  "WhatsApp 服务不可用": "WhatsApp unavailable",
  接入服务不可用: "Connector unavailable",
  消息处理服务不可用: "Message worker unavailable",
  连接: "Connect",
  重连: "Reconnect",
  状态核对: "Check status",
  会话发现: "Discover chats",
  已排队: "Queued",
  正在处理: "Processing",
  正在核对: "Checking",
  失败: "Failed",
  结果未知: "Result unknown",
  "无法连接后端，请检查本机服务后重试。":
    "Cannot reach the backend. Check the local service and retry.",
  "连接状态查询已恢复。": "Connection status reads have recovered.",
  "扫码状态已变化，已重新核对连接。":
    "Pairing status changed. The connection was checked again.",
  "已请求重连。二维码准备好后会自动显示，请稍候。":
    "Reconnection requested. A QR code will appear when ready. Please wait.",
  "已清除 {0} 项已恢复故障的待核对标记；历史记录保留，未恢复故障仍需处理。":
    "Cleared {0} reviewed recovered incidents. History is preserved; unresolved incidents still need attention.",
  "已载入已保存的授权；取消勾选后保存即可撤销。":
    "Saved permission loaded. Uncheck and save to revoke access.",
  "已发现最近会话，请勾选并保存处理授权。每批最多读取 100 个会话，可载入更多；列表可能不完整。新选项按服务端原到期时间失效。":
    "Recent chats found. Select and save processing permission. Each batch reads up to 100 chats; load more if needed. The list may be incomplete. New choices retain their original server expiry.",
  "已保存 {0} 个会话授权，自动回复未开启。":
    "Saved permission for {0} chats. Automatic replies remain off.",
  "已撤销全部会话授权，后端将拒绝这些会话的后续消息。":
    "All chat permission revoked. Future messages from those chats will be rejected.",
  "WhatsApp 连接与会话授权": "WhatsApp connection & chat permission",
  "WhatsApp · 连接与授权": "WhatsApp · Connection & permission",
  "让工作消息，进入你的工作台。": "Bring work messages into your workspace.",
  "先连接 WhatsApp，再选择允许处理的会话。选择权始终在你手里。":
    "Connect WhatsApp, then choose the chats it may process. You stay in control.",
  "你的 WhatsApp 连接": "Your WhatsApp connection",
  "连接 WhatsApp": "Connect WhatsApp",
  选择工作会话: "Choose work chats",
  保存处理授权: "Save processing permission",
  "连接后载入聊天并明确保存处理授权；自动回复不会开启。":
    "Connect, load chats and explicitly save permission to process them. Automatic replies stay off.",
  "当前可查看连接状态；扫码和会话授权功能待接入。":
    "Connection status is available. Pairing and chat permission are not connected yet.",
  选择连接: "Choose connection",
  连接状态读取失败: "Could not read connection status",
  正在读取连接状态: "Reading connection status",
  还没有本机连接: "No local connection yet",
  "当前账号暂无连接记录。接入负责人配置完成后，刷新即可查看状态。请联系接入负责人检查当前账号的配置。":
    "This account has no connection record. Refresh after the integration maintainer finishes setup. Ask them to check the account configuration.",
  "正在向本地服务查询。连接失败时可刷新重试。":
    "Checking the local service. Refresh to retry after a failure.",
  刷新连接: "Refresh connection",
  接收已暂停: "Reception paused",
  状态待确认: "Status needs checking",
  "本机接入配置不可用，请联系接入负责人检查。仍可载入已有授权并撤销。":
    "Local connector setup is unavailable. Contact the maintainer. Existing permission can still be read and revoked.",
  最近: "Latest",
  "操作：": "Operation:",
  " · {0}": " · {0}",
  "错误编号：": "Error code:",
  "上次请求响应丢失，暂不创建新的连接操作。使用原请求核对会保留原版本和请求键。":
    "The previous response was lost. No new connection operation will be created. Checking the original request keeps its version and request key.",
  扫码登录待接入: "Pairing is not connected yet",
  "可查看已有连接状态。启动连接及获取二维码暂不可用。":
    "Existing connection status is available. Starting it and getting QR codes are unavailable.",
  "WhatsApp 已连接": "WhatsApp connected",
  "无需再次扫码，可选择工作会话。":
    "No need to scan again. You can choose work chats.",
  "无需再次扫码，可载入并选择工作会话。":
    "No need to scan again. Load and choose work chats.",
  "使用手机 WhatsApp 关联设备扫描此二维码":
    "Scan this code using WhatsApp's Linked devices on your phone",
  "二维码显示失败，请刷新重试。":
    "The QR image could not be displayed. Refresh and retry.",
  获取于: "Fetched",
  "秒前 · 自动更新中": "seconds ago · updating automatically",
  消息接收已暂停: "Message reception paused",
  请先确认连接状态: "Check the connection first",
  "连接已断开，需要重新连接": "Disconnected: reconnection required",
  等待获取二维码: "Waiting for QR code",
  "恢复消息接收后再检查连接；暂停期间不显示二维码。":
    "Resume message reception before checking the connection. QR codes stay hidden while paused.",
  "刷新状态后再获取二维码，避免使用旧的扫码信息。":
    "Refresh status before getting a new QR code, to avoid using stale pairing information.",
  "点击下方「重新连接并获取二维码」，无需运行命令。":
    "Choose “Reconnect and get QR code” below. No terminal command is needed.",
  "正在加载本机二维码，也可点击「获取二维码」重试":
    "Loading the local QR code. You may also choose “Get QR code” to retry.",
  "等待本机服务准备扫码，请刷新状态":
    "Waiting for the local pairing service. Refresh status.",
  "手机打开 WhatsApp → 关联设备":
    "Open WhatsApp on your phone → Linked devices",
  "选择「关联设备」，扫描这里的二维码":
    "Choose “Link a device” and scan this code",
  开始连接: "Start connection",
  "核对未知操作（不重发）": "Check unknown operation (no resubmission)",
  使用原请求核对: "Check with the original request",
  暂停消息接收: "Pause reception",
  恢复消息接收: "Resume reception",
  "正在重连…": "Reconnecting…",
  重新连接并获取二维码: "Reconnect and get QR code",
  刷新二维码: "Refresh QR code",
  获取二维码: "Get QR code",
  刷新状态: "Refresh status",
  "一键重连需要有效登录和已配置的接入后端。":
    "One-click reconnection requires a valid login and configured connector backend.",
  连接与处理状态: "Connection & processing status",
  "WhatsApp 会话": "WhatsApp session",
  未连接或待确认: "Disconnected or unverified",
  处理链路: "Processing pipeline",
  待重新确认: "Needs rechecking",
  采样就绪: "Sample ready",
  尚未就绪: "Not ready",
  状态新鲜度: "Status freshness",
  "刷新失败，显示上次采样": "Refresh failed; showing previous sample",
  "已过期，需重新检查": "Expired: check again",
  当前采样有效: "Current sample valid",
  尚无采样: "No sample yet",
  最近采样: "Latest sample",
  暂无: "None yet",
  接收授权: "Reception permission",
  已启用: "Enabled",
  已暂停: "Paused",
  故障核对: "Incident review",
  "查询失败，需刷新": "Read failed: refresh required",
  正在查询: "Reading",
  "{0} 项待核对": "{0} need review",
  "已恢复，等待核对": "Recovered, awaiting review",
  "尚未恢复，暂不能清除": "Not recovered: cannot clear yet",
  项: "items",
  "开始：": "Started:",
  "恢复：": "Recovered:",
  "我已核对上述已恢复时段，确认无需导入历史消息。":
    "I reviewed the recovered periods above and confirm no historical import is needed.",
  "清除已恢复故障（": "Clear recovered incidents (",
  "仅清除已核对项的待处理标记，保留历史记录。未恢复故障不能清除；不会补拉或删除消息。":
    "Only clears reviewed pending markers and keeps history. Unresolved incidents cannot be cleared. No messages are imported or deleted.",
  "每次最多核对 100 项。": "Review up to 100 incidents at once.",
  "故障核对需要有效登录及明确确认。":
    "Incident review requires a valid login and explicit confirmation.",
  "勾选后保存，才会授权后端处理消息。":
    "Select chats and save to authorise message processing.",
  "{0} 已勾选": "{0} selected",
  授权待查询: "Permission not read yet",
  放弃勾选并重新载入: "Discard selection and reload",
  重新载入会话: "Reload chats",
  载入会话与授权: "Load chats & permissions",
  发现最近会话: "Discover recent chats",
  授权版本: "Permission version",
  个已授权: "authorised",
  "已有授权可在断线、暂停或接入配置不可用时读取及撤销。发现新会话需要有效连接，每批最多读取 100 个会话，可载入更多。下方分页用于浏览已载入会话。":
    "Existing permission can be read or revoked while disconnected, paused or misconfigured. New discovery needs a valid connection and reads up to 100 chats per batch. Pagination below browses chats already loaded.",
  "授权版本已变化、读取失败或保存结果待确认。请重新载入并核对后再保存；不会自动重试。":
    "Permission changed, reading failed or the save result is unverified. Reload and review before saving. No automatic retry.",
  "勾选的新会话已过期。请放弃勾选并重新发现，再核对后保存。":
    "New chat choices expired. Discard the selection, discover again and review before saving.",
  你的会话由你选择: "You choose your chats",
  会话选择待接入: "Chat selection is not connected yet",
  "先载入已有授权。连接后点击「发现最近会话」，勾选后明确保存。":
    "Load existing permission first. Once connected, discover recent chats, select and explicitly save.",
  "目前无法查询或更改会话授权。请重新登录并检查接入服务。":
    "Cannot read or change chat permission. Sign in again and check the connector.",
  保存会话授权: "Save chat permission",
  撤销全部授权: "Revoke all chat permission",
  暂无会话: "No chats yet",
  "可在手机创建测试聊天后重新发现最近会话。":
    "Create a chat on your phone, then discover recent chats again.",
  "当前没有已授权会话。接入配置恢复后可发现新会话。":
    "No authorised chats. Discover new chats after connector setup is restored.",
  "尚未发现会话，请点击「发现最近会话」。":
    "No chats discovered yet. Choose “Discover recent chats”.",
  "尚未连接；当前没有已授权会话。": "Disconnected; no authorised chats.",
  "载入更多会话（每批最多 100 个）": "Load more chats (up to 100 per batch)",
  有尚未保存的更改: "Unsaved changes",
  授权已保存: "Permission saved",
  "授权仅用于读取和处理选中会话。不授权自动回复，不改变正式工单。":
    "Permission only covers reading and processing selected chats. It does not authorise automatic replies or change formal orders.",
  "处理中…": "Processing…",
  "已放弃未保存的更改。": "Unsaved changes discarded.",
  放弃更改: "Discard changes",
  开始使用: "Get started",
  "每一步，都知道有没有完成。": "Know what is finished, at every step.",
  "在 WhatsApp 连接页扫码，选择并授权需要处理的聊天。":
    "Scan the code on the WhatsApp connection page, then select and authorise work chats.",
  "在业务页核对已有工单与原文；服务支持时可从客户原文新建工单。":
    "Review orders and source messages. Create orders from customer messages when the server supports it.",
  "核对顾客提议与顾客确认，明确同意后才更新正式安排。":
    "Review customer proposals and confirmations. Formal arrangements change only with your explicit acceptance.",
  "在回复审批页核对完整草稿。批准只保存决定，尚未自动发送。":
    "Review the complete draft on the approvals page. Approval records your decision; submit it for sending separately.",
  "手动发消息需进入 WhatsApp 消息页，单独授权并核对发送目标。":
    "For manual sending, open WhatsApp messages, authorise sending separately and check the recipient.",
  "在日历查看预约和待办，导出已确认预约到自己的日历。":
    "View appointments and tasks in Calendar. Export confirmed appointments to your own calendar.",
  "能力状态无法核对：": "Cannot verify feature availability:",
  "。相关操作保持关闭，请检查后端版本。":
    ". Related operations remain unavailable. Check the server version.",
  当前版本可以使用: "Available in this version",
  "登录、WhatsApp 连接与会话授权、已有工单与来源核对、具体时间变更确认、回复草稿批准／拒绝／取消、日历与待办查看。独立手动发送取决于连接状态和单独发送授权，提供方接受不等于对方收到。":
    "Login, WhatsApp connection and chat permission, order and source review, schedule confirmation, draft approval / rejection / cancellation, calendar and task views. Manual sending needs a valid connection and separate permission. Provider acceptance does not prove delivery.",
  仍在等待接通的功能: "Feature availability",
  接口已提供: "API available",
  暂不可用: "Unavailable",
  "可从对应页面使用，操作仍需核对归属、来源和当前版本。":
    "Use the corresponding page. Operations still require ownership, source and version checks.",
  查看团队进度: "View team progress",
  遇到不确定结果: "When a result is uncertain",
  "先恢复网络并读取最新状态。审批和发送保留原请求编号；只有在重新核对后，才明确重试原操作。不要通过反复点按钮、重新建单或重新发消息来试探是否成功。":
    "Restore the connection and read current state. Keep the original approval or sending request ID. Explicitly check the original operation after review. Do not test success by repeatedly clicking, creating another order or sending another message.",
  "登录、隐私和离线": "Login, privacy & offline use",
  "使用维护者为你配置的 GigMate 账号。网页不提供公开测试密码，也不保存密码。离线时不能确认、批准或发送；本版不缓存聊天供离线使用。退出会清空当前页面，尚待核对的原请求会按账号保留。":
    "Use your configured GigMate account. No public test password is provided or password stored. Offline confirmation, approval and sending are unavailable. Chats are not cached for offline use. Signing out clears the screen; unresolved original requests remain scoped to the account.",
  安装与桌面版: "Installation & desktop edition",
  "本版提供网页应用安装信息，支持的浏览器可“安装应用”或“添加到主屏幕”快捷打开，仍需联网。独立 exe／macOS 安装包、后台运行和离线业务尚未交付；添加快捷方式不会把后端或 WhatsApp 服务安装到手机。":
    "Supported browsers may offer Install app or Add to home screen for quick access. A connection is still required. Standalone exe / macOS packages, background operation and offline business are not delivered. A shortcut does not install the backend or WhatsApp service on your phone.",
  "也可以只读核对服务端的原操作保存记录。此检查不会执行、重发或撤销操作；未找到记录时仍需保留原编号。":
    "You can also check the original saved server result without writing. This does not execute, resend or cancel anything. Keep the original ID even if no record is found.",
  只读核对已保存结果: "Read saved result",
  "服务端已保存：「": "Server saved: “",
  "」 · 当时版本 v": "” · version at that time: v",
  "。结束后会刷新当前业务数据。":
    ". Current business data refreshes after closing this record.",
  "我已核对保存结果，结束这条原记录；这不会撤销或重新执行操作。":
    "I checked the saved result and will close this local record. This does not undo or execute the operation again.",
  结束已核对的原记录: "Close reviewed original record",
  操作复核: "Operation review",
  核对后保存: "Review before saving",
  "我已核对内容、来源及当前版本，确认本次操作。":
    "I checked the content, sources and current version and confirm this operation.",
  确认保存: "Confirm save",
  返回修改: "Back to editing",
  原业务操作核对: "Original business operation",
  有一笔原操作等待核对: "An original operation needs checking",
  原编号: "Original ID",
  "先用页面刷新读取当前状态，再核对原内容。不会自动重发，也不会换编号提交新操作；排期设置仅查询保存结果。":
    "Refresh to read current state, then review the original content. No automatic resend or new operation ID. Schedule settings recovery only reads the saved result.",
  "我已读取当前状态并核对原操作，确认按原编号核查":
    "I read current state and reviewed the original operation. Check using its original ID.",
  核对原业务操作: "Check original business operation",
  "读取失败，请刷新。": "Reading failed. Please refresh.",
  "会话归属无法核对，不能建单。":
    "Cannot verify conversation ownership. Order creation is unavailable.",
  "正在核对会话与来源。": "Checking conversation and sources.",
  "请选择可用的已授权会话。": "Choose an available authorised conversation.",
  "请填写 1–120 字的业务摘要。":
    "Enter a business summary of 1–120 characters.",
  "有时间时，必须选择客户说明时间的原文。":
    "A time requires selecting the customer's source message stating it.",
  "请选择日期。": "Choose a date.",
  "请填写未来的开始时间和更晚的结束时间。":
    "Enter a future start and a later end time.",
  "地址不能只有空格。": "The address cannot contain only spaces.",
  "有地址时，必须选择客户说明地址的原文。":
    "An address requires selecting the customer's source message stating it.",
  "已有未结束工单；另开一单需要明确确认。":
    "An open order already exists. Creating another requires explicit confirmation.",
  从会话新建工单: "Create an order from a conversation",
  新客户到第一张工单: "From a new customer to the first order",
  "只引用客户原文；不知道的时间和地址保持未提供，不自动编造。":
    "Use the customer's original words. Keep unknown time and address missing; do not invent them.",
  刷新会话与原文: "Refresh conversations & sources",
  "当前连接的后端未开放建单功能。下面可以填写和核对，提交按钮保持关闭。":
    "This server has not enabled order creation. You can fill in and review, but submission stays unavailable.",
  有尚待核对的原操作: "An original operation needs checking:",
  "，不能另开新请求。请到业务工作台核对原操作。":
    ". A new request cannot be created. Check the original operation in the business workspace.",
  "AI 新单建议": "AI new-order suggestions",
  "建议不会自动建单。选择后只预填摘要；时间、地址仍需逐项核对客户原文并明确填写。":
    "Suggestions do not create orders automatically. Selecting one only fills the summary. Review the customer sources and explicitly enter time and address yourself.",
  "目前没有待核对的新单建议；你可以直接手动建单。":
    "No new-order suggestions await review. You can create an order manually.",
  核对这份新单建议: "Review this new-order suggestion",
  已选择建议: "Selected suggestion",
  "；提交时会重新核对来源与版本。":
    "; sources and versions will be checked again on submission.",
  已授权会话: "Authorised conversation",
  请选择会话: "Choose a conversation",
  "· 已关联": "· linked to",
  张工单: "orders",
  "暂无已授权会话，请先在 WhatsApp 连接页选择聊天。":
    "No authorised conversations. Choose chats on the WhatsApp connection page first.",
  "该会话已有未结束工单：": "This conversation already has open orders:",
  查看已有工单: "View existing order",
  "这是另一项业务，我确认另开一张工单":
    "This is a separate job. I confirm creating another order.",
  业务摘要: "Business summary",
  客户称呼和具体工作: "Customer name and specific work",
  时间信息: "Time information",
  尚未提供: "Not provided yet",
  "只知道日期，时间待确认": "Date only; time awaits confirmation",
  具体开始和结束时间: "Specific start and end times",
  日期: "Date",
  "开始（香港时间）": "Start (Hong Kong time)",
  "结束（香港时间）": "End (Hong Kong time)",
  "客户提供的地址（可留空）": "Customer-provided address (optional)",
  "仅日期仍属暂定。填了时间或地址，也必须核对客户在哪条消息中说明；商户自己的消息不能代替客户确认。":
    "A date alone remains tentative. Any time or address must refer to the customer's source message. The merchant's own message cannot replace customer confirmation.",
  核对新工单: "Review new order",
  新工单复核: "New-order review",
  核对后再保存: "Review, then save",
  "时间：": "Time:",
  "地址：": "Address:",
  "未提供，等待客户说明": "Missing; waiting for the customer",
  "来源会话 v": "Source conversation v",
  "· 时间原文": "· time sources:",
  "条 · 地址原文": "· address sources:",
  条: "messages",
  "内容或来源已变化，请重新核对。": "Content or sources changed. Review again.",
  "我已核对摘要、时间、地址和客户来源；缺项保持待确认":
    "I reviewed the summary, time, address and customer sources. Missing information stays pending.",
  保存新工单: "Save new order",
  选择客户原文依据: "Choose customer source evidence",
  "只显示本会话最新、未撤回且有文字的客户消息。历史快照和商户回显不能当成客户确认。":
    "Only current, unrevoked customer messages with text from this conversation are shown. Historical snapshots and merchant echoes cannot count as customer confirmation.",
  "正在读取…": "Reading…",
  "客户 · r": "Customer · r",
  作为时间依据: "Use as time evidence",
  作为地址依据: "Use as address evidence",
  "没有可用客户原文。可先留空时间／地址，等待客户补充；不能猜测确认。":
    "No usable customer source. Keep time / address blank and wait for more information. Do not guess a confirmation.",
  工单进度操作: "Order progress operations",
  工单进度: "Order progress",
  "此工单已结束，保留历史，不能再更改状态。":
    "This order is closed. History is kept and its status cannot change.",
  "暂不可保存：等待 C 的工单状态接口（#27）完成修复并验收。可以先查看每个操作的影响。":
    "This server does not support saving the selected status. Review the impact below.",
  "结束后释放预约时段，收尾自动待办、未发送草稿和待核对提议；保留历史。已派发的 WhatsApp 请求不会因此撤回。":
    "Closing releases the time slot and closes generated tasks, unsent drafts and pending proposals. History is kept. A dispatched WhatsApp request is not recalled.",
  "只更新业务进度，不发送消息，也不代表客户确认了新安排。":
    "Only updates work progress. It does not send a message or mean the customer confirmed a new arrangement.",
  "本次核对工单 v": "Reviewed order v",
  "；当前 v": "; current v",
  "工单已变化，请关闭并重新选择操作。":
    "The order changed. Close this review and choose the operation again.",
  我已核对目标状态及影响: "I checked the target status and its effects",
  保存工单状态: "Save order status",
  关闭状态复核: "Close status review",
  快速问工作台: "Ask the workspace",
  "从当前账号的记录查询安排。只支持下方四类问题，不会修改工单或发送消息。":
    "Query this account's records. Only the four question types below are supported. No orders are changed or messages sent.",
  今天有什么安排: "What is on today",
  明天有什么安排: "What is on tomorrow",
  哪些在等客户: "What is waiting for customers",
  有什么待决定: "What needs my decision",
  你的问题: "Your question",
  查询记录: "Search records",
  "暂时只支持上面四类问题，请选择一个。不会猜测答案。":
    "Only the four question types above are supported. Choose one; answers are not guessed.",
  "· 查询完成；结果是业务记录，不代表 AI 已确认。":
    "· Search complete. These are business records, not AI confirmations.",
  "这类记录暂时为空。": "No records in this category yet.",
  处理待办: "Handle tasks",
  "完成待办只记录你的处理决定，不代表客户确认了时间或地址。关联需求条目会一起更新。":
    "Completing a task records your decision. It does not confirm a customer's time or address. Linked requirement items update together.",
  工单范围: "Order scope",
  全部开放工单: "All open orders",
  "来源：": "Sources:",
  核对完成待办: "Review task completion",
  核对取消待办: "Review task cancellation",
  "工单“{0}” v{1}，待办“{2}”：{3}。请核对原文来源和依赖任务；不会确认客户的约定。":
    "Order “{0}” v{1}, task “{2}”: {3}. Check source messages and prerequisite tasks. This does not confirm a customer agreement.",
  "当前没有待处理的待办。": "No tasks currently need handling.",
  真实消息理解尚未启用: "Live message understanding is not enabled",
  "模型未能确定业务含义，需要人工核对":
    "The model could not determine the business meaning. Human review needed.",
  无法确定属于哪张工单: "Cannot determine which order this belongs to",
  "处理失败，需要核对原文": "Processing failed. Review the source message.",
  "多次处理未完成，需要人工核对":
    "Repeated processing did not finish. Human review needed.",
  复核数据暂不可用: "Review data temporarily unavailable",
  "来源会话无法核对。": "Cannot verify the source conversation.",
  原文无法读取: "Source message unavailable",
  需要你判断: "Your decision is needed",
  "把没有理解、没有归单和来源失效的问题摆出来。不会自动接受、重发或改写工单。":
    "Review misunderstood, unassigned or stale-source items. This does not automatically accept, resend or rewrite an order.",
  刷新复核事项: "Refresh review items",
  "正在读取复核事项…": "Reading review items…",
  消息处理待核对: "Message processing needs review",
  "这是处理记录，可能包含旧轮次；查看最新原文后再判断，不能把旧诊断当成当前失败。":
    "This log may include earlier rounds. Check the latest source before deciding. Old diagnostics do not prove a current failure.",
  "处理暂未完成，系统正在自动重试":
    "Processing is unfinished; an automatic retry is pending",
  需要人工核对: "Human review needed",
  "· 记录 v": "· recorded v",
  "/ 当前 v": "/ current v",
  " · 历史轮次": " · Earlier round",
  查看这条会话原文: "View conversation source",
  "目前没有记录到需复核的处理事项。这不表示 AI 已理解所有聊天。":
    "No processing items currently need review. This does not prove AI understood every chat.",
  来源会话: "Source conversation",
  " · 触发消息": " · Triggering message",
  "已撤回，不可用于确认": "Revoked; cannot support confirmation",
  "无可读取文字，请核对附件": "No readable text. Check attachments.",
  "尚无可读取原文。": "No readable source yet.",
  该会话已有工单: "Orders already in this conversation",
  工单缺项与含糊回复: "Missing information & ambiguous replies",
  等待客户提供: "Waiting for the customer to provide information",
  原文或含义需要复核: "Source or meaning needs review",
  等待客户核实和商户确认:
    "Waiting for customer verification and merchant confirmation",
  "客户回复含糊，不能默认同意":
    "Customer reply is ambiguous. Do not assume agreement.",
  "客户已确认，等待商户核对": "Customer confirmed; awaiting merchant review",
  客户尚未明确确认: "Customer has not explicitly confirmed",
  核对工单和来源: "Review order & sources",
  附件与部分结果: "Attachments & partial results",
  "到 WhatsApp 消息页查看附件、部分文字、来源版本和人工确认。处理失败或结果未知不会自动重发；扫描 PDF 的文字识别和真实语音理解仍未交付。":
    "Use WhatsApp messages to review attachments, partial text, source versions and human acknowledgement. Failed or unknown processing is not automatically resubmitted. Scanned-PDF recognition and live speech understanding are not delivered.",
  前往消息与附件: "Open messages & attachments",
  等待处理: "Pending",
  处理中: "Processing",
  等待重试: "Waiting to retry",
  本次任务完成: "Task completed",
  模型结果待核对: "Model result needs checking",
  附件下载: "Download attachment",
  "B 提取与理解": "Extraction & understanding",
  只读核对模型结果: "Read-only model result check",
  "后台服务暂不支持附件操作，请联系维护者更新。":
    "The backend does not support attachment operations yet. Ask the maintainer to update it.",
  "附件存储尚未启用，请联系维护者。":
    "Attachment storage is not enabled. Contact the maintainer.",
  "B 的 OCR / 转写 / 解析 / GenAI 处理器尚未配置。原文件可先预览。":
    "OCR / transcription / parsing / GenAI is not configured. You may preview the original file first.",
  "B 返回的结构或来源不符合协议，需要修正处理器。":
    "The processor returned an invalid structure or provenance. It needs correction.",
  "模型可能已处理，请核对原任务，不自动重复调用。":
    "The model may already have processed this. Check the original job; do not call it again automatically.",
  "此附件已有任务，请先核对原任务。":
    "This attachment already has a job. Check that job first.",
  "来源或上下文已变化，请重新载入核对。":
    "The source or context changed. Reload and review.",
  "连接暂时失败，下面保留上次读取的内容，暂不提交新操作。":
    "Connection failed. The previous read remains visible, but new operations are unavailable.",
  连接暂时失败: "Connection failed",
  "\n\n[预览仅展示前 100000 字符，请下载原文件核对全文。]":
    "[Preview shows only the first 100,000 characters. Download the original to review the full file.]",
  附件读取与核对: "Read & review attachment",
  " · 收起": " · Collapse",
  "只读取这条已授权附件，最大 20 MB。提取和模型建议不等于工单确认。":
    "Read only this authorised attachment, up to 20 MB. Extraction and model suggestions do not confirm an order.",
  "本批不支持此文件类型。": "This file type is unsupported in this version.",
  "本次解释日期的时区（可留空）": "Time zone for interpreting dates (optional)",
  "例如 Asia/Hong_Kong": "For example: Asia/Hong_Kong",
  "请填写适用的 IANA 时区，不会根据手机号或电脑猜测；缺少时间依据时应交由人工核对。":
    "Enter the applicable IANA time zone. It is not guessed from phone numbers or your computer. Missing time evidence requires human review.",
  同意下载此附件到本机私有存储并预览:
    "I agree to download this attachment into private local storage and preview it",
  "另行同意将此附件交给 B 配置的提取与 GenAI 服务":
    "I separately agree to send this attachment to the configured extraction and GenAI service",
  读取附件: "Read attachment",
  "使用原请求核对（保留原下载和模型同意选项）":
    "Check original request (keep original download and model consent)",
  取消此任务: "Cancel this job",
  "只读核对模型结果（不重发）":
    "Read-only model result check (no resubmission)",
  "原消息时间：": "Original message time:",
  "· 日期解释时区：": "· Date interpretation time zone:",
  未指定: "Not specified",
  "（商户本次选择）": "(selected by the merchant for this request)",
  "日期依据不完整：“明天”等相对日期需要人工确认，观察时间不能代替发送时间。":
    "Date grounding is incomplete. Relative dates such as “tomorrow” need human confirmation. Observation time cannot replace send time.",
  附件版本: "Attachment version",
  "字节 · 来源指纹": "bytes · source fingerprint",
  预览原附件: "Preview original attachment",
  下载原附件: "Download original attachment",
  已授权附件预览: "Authorised attachment preview",
  "已授权 PDF 预览": "Authorised PDF preview",
  提取文字与来源: "Extracted text & sources",
  "结果任务：": "Result job:",
  " · 显示上次已完成的结果，请核对最近任务状态":
    " · Showing the last completed result. Check the latest job status.",
  "提取范围：": "Extraction scope:",
  来源片段: "Source segment",
  " · 第 {0} 页": " · page {0}",
  "GenAI 建议，尚未确认": "GenAI suggestions: not confirmed",
  "（片段": "(segment",
  片段: "Segment",
  "待核对：": "Needs review:",
  核对备注: "Review note",
  "标记已核对来源（不确认工单）":
    "Acknowledge sources (does not confirm order)",
  "来源已核对 ·": "Sources acknowledged ·",
  "查看业务交接资料（不写入工单）":
    "View business handoff (does not write to order)",
  "来源已核对，业务仍需单独确认。C 使用这些来源标识前必须重新检查权限、版本和有效期。":
    "Source acknowledgement does not confirm the business agreement. Permission, versions and expiry must be checked again before using these references.",
  附件: "Attachment",
  "· 上下文": "· context",
  "· 来源任务": "· source job",
  "有效期：": "Valid until:",
  已处理: "Processed",
  已发出: "Sent",
  已送达: "Delivered",
  已读: "Read",
  排队中: "Queued",
  查询中: "Looking up",
  查询完成: "Lookup completed",
  已读完本次可获取记录: "All currently available records read",
  已达查询上限: "Read limit reached",
  仍有未确认记录: "Unverified records remain",
  进行中: "In progress",
  待查询来源: "Source lookup pending",
  "找到快照，修订仍待核对": "Snapshot found; revision still needs review",
  来源不可获取: "Source unavailable",
  查询失败: "Lookup failed",
  "同步已排队。历史快照不会自动创建工单或发送消息。":
    "Sync queued. Historical snapshots do not automatically create orders or send messages.",
  消息时间线与同步: "Messages & synchronisation",
  "查看已授权聊天的消息，或明确导入近期可获取记录。附件可在单独授权后读取；真实文字理解、语音识别和图片识别尚未启用，部分结果需要人工核对。":
    "View authorised chats or explicitly import available recent history. Attachments require separate permission. Text models require server configuration; live speech and image recognition remain unavailable. Review partial results yourself.",
  已授权聊天: "Authorised chat",
  "群聊 · ": "Group ·",
  载入消息时间线: "Load message timeline",
  刷新同步状态: "Refresh sync status",
  历史快照: "Historical snapshot",
  实时接入: "Live ingress",
  "修订 {0}": "Revision {0}",
  非完整修订证据: "Incomplete revision evidence",
  收到: "Received",
  自己发送: "Sent by you",
  此消息已撤回: "This message was revoked",
  无文字内容: "No text content",
  类型待确认: "Type unverified",
  "· 原文件通过下方授权入口读取":
    "· Read the original file through the authorised entry below",
  "群成员标识：": "Group participant ID:",
  "· 引用已接入消息": "· Reply to an ingested message",
  "· 处理状态：": "· Processing status:",
  "· 送达状态：": "· Delivery status:",
  加载更早消息: "Load earlier messages",
  当前会话: "Current conversation",
  近期历史导入: "Import recent history",
  时间范围: "Time range",
  近: "Past",
  天: "days",
  查询记录上限: "Maximum records",
  我同意查询所选聊天在该范围内的记录:
    "I agree to query this chat's records within the selected range",
  重试原同步请求: "Retry original sync request",
  开始历史同步: "Start history sync",
  "接收已暂停，同步也已暂停；已有消息仍可查看。":
    "Reception and synchronisation are paused. Existing messages remain readable.",
  "只同步 WAHA 当前可提供的记录，不保证完整历史。已记录的暂停/撤权时段会跳过，失败和缺口不会自动清除。":
    "Only records currently supplied by WAHA can be synced; complete history is not guaranteed. Recorded paused / revoked periods are skipped. Failures and gaps are not silently cleared.",
  同步任务: "Sync jobs",
  暂无任务: "No jobs yet",
  "· 写入": "· written",
  "· 已有": "· existing",
  "· 跳过": "· skipped",
  读取此任务状态: "Read this job's status",
  重试此范围: "Retry this range",
  取消同步: "Cancel sync",
  缺口补查: "Check gaps",
  "补查仅增加可获取快照，结果仍需本人核对。":
    "Gap lookup only adds available snapshots. Review results yourself.",
  补查: "Look up",
  的故障时段: "interruption period",
  缺失来源: "Missing source",
  "查询来源快照，不重建修订":
    "Look up source snapshot without reconstructing revisions",
  "文字 / 链接": "Text / link",
  图片: "Image",
  文件: "File",
  普通音频附件: "Audio attachment",
  "语音消息（Ogg/Opus）": "Voice note (Ogg/Opus)",
  "视频（MP4）": "Video (MP4)",
  "贴纸（WebP）": "Sticker (WebP)",
  位置: "Location",
  联系人: "Contact",
  投票: "Poll",
  表情回应: "Reaction",
  待核对草稿: "Draft awaiting review",
  "已批准，排队中": "Approved and queued",
  连接检查中: "Checking connection",
  "提交中，不能取消": "Submitting: cannot cancel",
  "WAHA 已接受": "Accepted by WAHA",
  未提交成功: "Submission failed",
  "结果未知，禁止重发": "Result unknown: do not resend",
  尚未提交: "Not submitted",
  已发送: "Sent",
  请先上传并核对附件: "Upload and review the attachment first",
  请填写坐标: "Enter coordinates",
  请先核对原请求: "Check the original request first",
  "已核对原请求，没有重新提交。":
    "Original request checked. Nothing was resubmitted.",
  "本会话有待核对请求，请先核对原记录。":
    "This chat has an unverified request. Check its original record first.",
  "已按批准的固定内容政策排队。":
    "Queued under the approved exact-content policy.",
  "草稿已保存，请核对下方最终内容再批准发送。":
    "Draft saved. Review the final content below, then approve sending.",
  "WhatsApp 发送": "WhatsApp sending",
  "向「": "Send to “",
  "」发送 WhatsApp 消息": "” on WhatsApp",
  "读取聊天授权与发送授权分开。草稿、已批准、已接受和已送达是不同状态。":
    "Chat reading permission and sending permission are separate. Draft, approved, accepted and delivered are different states.",
  "发送功能暂不可用，请联系接入负责人确认服务配置。":
    "Sending is unavailable. Ask the integration maintainer to check service configuration.",
  刷新发送记录: "Refresh sending records",
  "我允许本会话发送消息，授权有效期 24 小时":
    "I allow messages to be sent to this chat for 24 hours",
  保存发送授权: "Save sending permission",
  撤销全部发送授权: "Revoke all sending permission",
  "准备消息（尚未发送）": "Prepare message (not sent yet)",
  内容来源: "Content source",
  用户手动输入: "Manually entered by user",
  "Agent 建议稿，人工核对": "Agent suggestion, reviewed by a person",
  "自动润色暂不可用。可粘贴建议稿，修改并核对后发送。":
    "Automatic polishing is unavailable. Paste, edit and review a suggested draft before sending.",
  消息类型: "Message type",
  文字: "Text",
  "文件类型（高级选项，可留空自动识别）":
    "File MIME type (advanced; leave blank to detect)",
  上传发送附件: "Upload sending attachment",
  "附件最大 20 MiB": "Maximum attachment size: 20 MiB",
  "字节 · SHA256": "bytes · SHA256",
  待发送图片: "Image to send",
  "查看 / 下载待发送文件": "View / download file to send",
  说明文字: "Caption",
  纬度: "Latitude",
  经度: "Longitude",
  地点名称: "Location name",
  联系人姓名: "Contact name",
  "电话号码（含 + 国家码）": "Phone number (including + country code)",
  投票问题: "Poll question",
  "选项（每行一个，2–12 项）": "Options (one per line, 2–12 options)",
  允许多选: "Allow multiple answers",
  回应目标消息: "Target message for reaction",
  "引用回复（可选，先载入时间线）":
    "Reply reference (optional; load the timeline first)",
  "表情（留空移除）": "Emoji (leave blank to remove)",
  保存待审核草稿: "Save draft for review",
  "预先允许 Agent 在本会话使用下方相同内容，24 小时内最多 5 次；正文和附件不能改变":
    "I authorise the Agent to use exactly this content in this chat up to 5 times within 24 hours. Text and attachments cannot change.",
  "固定内容政策已保存，尚未发送消息。":
    "Exact-content policy saved. No message has been sent.",
  批准固定内容自动政策: "Approve exact-content automatic policy",
  "草稿保存结果待确认。": "Draft save result unverified.",
  核对原草稿请求: "Check original draft request",
  "原任务已进入发送，无法取消；请核对下方记录，不要重发。":
    "The original task has entered sending and cannot be cancelled. Check its record below; do not resend.",
  "原请求已取消；晚到的相同请求也不会创建发送任务。":
    "Original request cancelled. A late identical request cannot create a sending task.",
  取消原请求并核对: "Cancel and check original request",
  "最终发送快照 ·": "Final sending snapshot ·",
  "· 上下文版本": "· context version",
  "关联工单版本（不自动确认业务）：":
    "Linked order version (does not confirm business):",
  " · 本条明确关联 {0}": " · This message explicitly links to {0}",
  "附件：": "Attachment:",
  核对这条草稿绑定的附件: "Check this draft's bound attachment",
  截止: "Due",
  确认上述内容并发送: "Confirm this content and send",
  只读核对发送结果: "Read-only sending result check",
  人工核对说明: "Manual review note",
  "我已核对手机，理解本条可能已发出；保留未知状态，不重发本条，只允许后续独立任务继续":
    "I checked my phone and understand this may already have been sent. Keep its unknown state and do not resend it; allow only later independent tasks to continue.",
  记录核对并解除后续阻塞: "Record review and unblock later tasks",
  "已记录当时未知状态的人工核对；当前状态以上方结果为准，本条不会重发。":
    "The manual review of the then-unknown result is recorded. The latest state is shown above. This message will not be resent.",
  已批准的自动政策: "Approved automatic policies",
  "自动触发尚未接入。目前只能由你明确触发已批准的固定内容；这不是 AI 自由生成的自动回复。":
    "Automatic business triggers are not connected. You may explicitly trigger the approved exact content. This is not freely generated AI automatic replying.",
  有效: "Valid",
  已撤销: "Revoked",
  "· 已预留": "· reserved",
  "次 · 截止": "uses · expires",
  按已授权政策提交: "Submit under authorised policy",
  撤销此政策: "Revoke this policy",
  加载更多政策: "Load more policies",
  发送记录: "Sending records",
  加载更多发送记录: "Load more sending records",
  "结果未知时不会自动重发，同一会话后续发送暂停。没有 WAHA 返回的消息 ID 时，无法自动证明某条相同文字就是本次发送；需人工核对。":
    "Unknown outcomes are never automatically resent and later sends in this chat pause. Without a WAHA message ID, identical text cannot prove which send it was. Manual checking is required.",
  未提供原文依据: "No source evidence provided",
  "{0}（该版本未载入，需复核）": "{0} (revision not loaded; review required)",
  核对原操作: "Review original operation",
  有一项原操作尚待核对: "An original operation needs checking",
  修改工单状态: "Change order status",
  "确认{0}": "Confirm {0}",
  "· 请求编号": "· request ID",
  "业务：": "Business:",
  未提供: "Not provided",
  "；时间原文": "; time sources:",
  "条；地址原文": "; address sources:",
  "原工单版本 v": "Original order version v",
  "原工单 v": "Original order v",
  "；原会话 v": "; original conversation v",
  原文编号: "Source IDs",
  "读取、刷新和重新登录不会重发。只有明确核对后，才使用相同编号、原内容与原版本核对操作；服务端仍会拒绝旧来源或版本。":
    "Reading, refreshing and signing in again do not resend. Only explicit review permits checking with the same ID, original content and versions. The server still rejects stale sources or versions.",
  "我已核对原内容和当前状态，继续核对原编号操作":
    "I checked the original content and current state. Continue checking the original-ID operation.",
  核对失败: "Check failed",
  核对原编号操作: "Check original-ID operation",
  "顾客提议、顾客确认和商户确认分别显示。未知地址保持未提供。":
    "Customer proposals, customer confirmations and merchant confirmations are shown separately. Unknown addresses remain missing.",
  "下面是上次读取的数据，当前不能据此确认。":
    "Showing the previous read. It cannot support a new confirmation.",
  "正在读取最新数据…": "Reading latest data…",
  尚未读取数据: "No data read yet",
  刷新业务数据: "Refresh business data",
  工单列表: "Orders",
  搜索业务: "Search orders",
  工单状态: "Order status",
  全部状态: "All statuses",
  "筛选隐藏了当前工单；右侧仍显示「":
    "The filter hides the selected order. The right side still shows “",
  版本: "Version",
  个关联会话: "linked conversations",
  "没有匹配的工单，调整搜索或状态筛选。":
    "No matching orders. Adjust the search or status filter.",
  "当前还没有工单。先在「WhatsApp 连接」中授权会话，再到「新建工单」引用客户原文建单；自动建单尚未开放。":
    "No orders yet. Authorise a conversation in WhatsApp connection, then create an order using customer sources. Orders are not created automatically.",
  "正在读取工单…": "Reading orders…",
  "读取失败，请检查服务后刷新。":
    "Reading failed. Check the service and refresh.",
  工单详情: "Order details",
  "有工单后，可在此查看详情与来源消息。":
    "Order details and source messages will appear here.",
  "正在核对选中工单，完成前不能确认。":
    "Checking the selected order. Confirmation is unavailable until finished.",
  "· 版本": "· version",
  "· 更新于": "· updated",
  "解释：": "Interpretation:",
  操作失败: "Operation failed",
  "{0}：{1}": "{0}: {1}",
  "当前已记录时间和地址的确认；请继续核对变更来源。":
    "Time and address confirmations are recorded. Continue reviewing change sources.",
  "当前后端未开放地址提议确认。":
    "This server has not enabled address proposal confirmation.",
  "需求、延期和交付检查请到业务管理。":
    "Use Business management for requirements, deferrals and delivery checks.",
  "人工归单与延期保存仍未开放。":
    "Manual assignment and deferral saving are not enabled on this server.",
  待核对变更: "Changes awaiting review",
  项提议: "proposals",
  项待确认: "awaiting confirmation",
  "共 {0} 项": "{0} in total",
  开始处理: "Start work",
  标记等待客户: "Mark waiting for customer",
  完成工单: "Complete order",
  取消工单: "Cancel order",
  "暂无需要核对的变更。新的变更会显示在这里。":
    "No changes currently await review. New changes appear here.",
  变更: "Change",
  "原值：": "Original:",
  "提议值：": "Proposed:",
  顾客提出: "Proposed by customer",
  商户提出: "Proposed by merchant",
  "· 工单基于 v": "· based on order v",
  "/ 会话 v": "/ conversation v",
  "冲突安排：": "Conflicting appointment:",
  "来源版本或归属无法完整核对，保持待复核。":
    "Source revision or ownership cannot be fully verified. Keep this under review.",
  "当前接口仅支持时间和地址确认，此字段保持待核对。":
    "Review other fields in Business management. This view confirms time and address.",
  核对并确认地址: "Review & confirm address",
  核对并确认安排: "Review & confirm schedule",
  确认安排复核: "Schedule confirmation review",
  复核本次业务更新: "Review this business update",
  "工单 v": "Order v",
  "· 来源会话 v": "· source conversation v",
  "提议、工单或来源已变化，本次复核失效。关闭后重新核对。":
    "The proposal, order or source changed. This review is invalid. Close it and review again.",
  "我已核对原文，接受本次提议。仍未获客户确认的信息保持待确认；日历与准备待办按确认状态处理。":
    "I reviewed the source and accept this proposal. Information not confirmed by the customer stays pending. Calendar entries and preparation tasks follow the confirmation state.",
  确认并同步安排: "Confirm & update schedule",
  关闭复核: "Close review",
  关联会话与来源时间线: "Linked conversations & sources",
  显示会话: "Show conversation",
  "全部关联会话（": "All linked conversations (",
  顾客: "Customer",
  "· 会话": "· conversation",
  "消息已撤回，相关内容需复核":
    "Message revoked; related information needs review",
  没有可读取文字: "No readable text",
  "该范围暂无来源消息。": "No source messages in this range.",
  "来源链接可能指向隐藏会话；选择全部关联会话查看。":
    "Source links may point to a hidden conversation. Select all linked conversations to view them.",
  个人日历: "Personal calendar",
  "账号全部安排；时刻按香港时区显示，全天日期保留原时区。":
    "Appointments across this account. Times use Hong Kong time; date-only entries keep their original time zone.",
  查看日期: "View date",
  查看全部安排: "View all appointments",
  其他工单: "Other order",
  未提供工单标题: "Order title unavailable",
  "该范围暂无日历安排。": "No calendar entries in this range.",
  当前工单待办: "Tasks for this order",
  "全部（含历史）": "All (including history)",
  "{0}（未载入）": "{0} (not loaded)",
  "当前工单在该范围暂无待办。": "No tasks for this order match the filter.",
  "新建工单请到“新建工单”；支持的状态操作在工单详情核对。回复草稿请到“回复审批”，":
    "Use New order to create an order, and order details for supported status operations. Use Reply approvals for drafts.",
  "已批准草稿可在业务管理核对后提交发送。":
    "Review approved drafts in Business management and submit them for sending.",
  "业务审批尚未接通 WhatsApp 发送。":
    "Business approvals are not connected to WhatsApp sending on this server.",
  草稿未提交: "Draft not submitted",
  待核对批准: "Awaiting approval review",
  "已批准，尚未发送": "Approved, not sent yet",
  正在执行: "Executing",
  执行完成: "Execution completed",
  执行失败: "Execution failed",
  执行结果待核对: "Execution result unverified",
  已关闭: "Closed",
  已过期: "Expired",
  尚未提交发送: "Not submitted for sending",
  发送服务已接收: "Accepted by sending service",
  对方已读: "Read by recipient",
  送达结果未知: "Delivery unknown",
  "缺项已补齐，不再需要此问题":
    "Missing information resolved; this question is no longer needed",
  工单已完成: "Order completed",
  工单已取消: "Order cancelled",
  新消息使旧草稿失效: "New message invalidated the old draft",
  原文已编辑或撤回: "Source edited or revoked",
  "已有可用时间，不再需要此问题":
    "A suitable time is available; this question is no longer needed",
  超过有效期: "Expired",
  你拒绝了此草稿: "You rejected this draft",
  你取消了此草稿: "You cancelled this draft",
  工单已变化: "Order changed",
  会话授权已撤回: "Conversation permission revoked",
  "只有待核对的草稿可以批准。": "Only a draft awaiting review can be approved.",
  "这份草稿已过期，请刷新查看。": "This draft expired. Refresh to check.",
  "收件会话或原文依据无法核对，不能批准。":
    "Cannot verify the recipient or source evidence. Approval unavailable.",
  "当前工单已结束，不能批准。": "The order is closed. Approval unavailable.",
  "工单或聊天已变化，请刷新后核对新草稿。":
    "Order or chat changed. Refresh and review the new draft.",
  "当前草稿不允许重新提问。": "This draft cannot be regenerated.",
  "当前来源、授权或工单状态不允许重新提问。":
    "Current sources, permission or order state prevent a new question.",
  "这一轮聊天已经重新提问过。等待新消息后再核对，避免重复请求。":
    "A new question was already generated for this conversation round. Wait for a new message to avoid duplicate requests.",
  客户提出的时间与已有安排冲突:
    "The customer's proposed time conflicts with an existing appointment",
  等待客户提供日期和时间: "Waiting for customer date and time",
  等待客户核实日期和时间: "Waiting for customer verification of date and time",
  "只有日期，等待客户说明几点": "Date only; waiting for a specific time",
  等待客户提供地址: "Waiting for customer address",
  等待客户核实地址: "Waiting for customer address verification",
  "工单还有未确认的信息，请核对完整正文和来源":
    "The order has unconfirmed information. Review the full text and sources.",
  "需要人工核对业务含义；请对照完整正文和来源":
    "Human review of the business meaning is needed. Check full text and sources.",
  "审批数据不完整，请刷新；当前不能批准。":
    "Approval data incomplete. Refresh; approval is unavailable.",
  "浏览器不允许保存原请求记录；可以查看审批，但当前不能提交操作。请恢复存储后重新打开页面，不能推断旧请求未提交。":
    "Browser storage cannot preserve the original request. Reading is available; submission is blocked. Restore storage and reopen. Do not assume an old request was never submitted.",
  "旧入口还有待核对的审批操作；记录已保留，不能搬运到当前服务重试。请让维护者先核对旧请求。":
    "An approval operation from the old service still needs checking. Its record is kept and cannot be moved to this service for retry. Ask the maintainer to check it.",
  "原请求记录无法读取；可以查看审批，但当前不能提交操作。请恢复存储后重新核对旧请求。":
    "Cannot read the original request record. Reading approvals is available, but submission is blocked. Restore storage and check old requests.",
  "原请求记录无法读取，请联系维护者核对；为避免重复批准，当前不能提交新操作。":
    "Cannot read the original request record. Contact the maintainer. New submissions are blocked to prevent duplicate approval.",
  "无法保存原请求记录；本次操作尚未提交，当前不能提交新操作。请恢复存储后重新打开审批页。":
    "Cannot save the original request. This operation was not submitted. Restore storage and reopen approvals before submitting anything new.",
  "原请求记录已被另一页面更新，本页不会删除它。操作响应已返回，请重新打开审批页核对。":
    "Another page changed the original request record; this page will not delete it. A response arrived. Reopen approvals to check.",
  "操作响应已返回，但原请求记录无法清理；记录仍保留，当前不能提交新操作。请恢复存储后重新打开审批页核对。":
    "A response arrived but the original record could not be cleared. It is kept and new submissions are blocked. Restore storage and reopen approvals.",
  "结果暂未确认。不要重新批准；刷新后核对，必要时使用原请求核对。":
    "Result unverified. Do not approve again. Refresh and check; use the original request if needed.",
  "结果暂未确认，请保留原请求并核对，不能直接重发。":
    "Result unverified. Keep and check the original request; do not resend directly.",
  "登录已过期，请重新登录；原记录仍按账号与环境保存。":
    "Session expired. Sign in again. Original records remain scoped to account and service.",
  "后端拒绝了这次操作。请刷新后重新核对版本、来源、授权和当前状态。":
    "The server rejected this operation. Refresh and review versions, sources, permission and current state.",
  "响应不完整，暂时不能确认操作结果，请核对原请求。":
    "Response incomplete. The outcome is unverified. Check the original request.",
  "操作响应不匹配，保留原请求等待核对。":
    "Response does not match the operation. Keep the original request for checking.",
  "结果状态或快照不匹配，原请求仍待核对。":
    "Result state or snapshot differs. The original request still needs checking.",
  "原文当前不可读取。可以拒绝／取消草稿，但不能批准或重新提问。":
    "Source unavailable. You may reject or cancel the draft, but cannot approve or regenerate it.",
  "先核对原请求，再提交新操作。":
    "Check the original request before submitting a new operation.",
  "请填写 1 至 500 字的拒绝／取消原因。":
    "Enter a rejection / cancellation reason of 1–500 characters.",
  "另一个页面已记录原请求，请重新打开审批页核对。":
    "Another page recorded an original request. Reopen approvals and check it.",
  "无法核对浏览器原请求记录；本次操作尚未提交，当前不能提交新操作。请恢复存储后重新打开页面。":
    "Cannot verify browser request storage. This operation was not submitted. Restore storage and reopen before submitting anything new.",
  "没有可核对的原请求。": "No original request to check.",
  "无法安全保存原操作，请恢复浏览器存储后再操作。":
    "Cannot safely save the original operation. Restore browser storage first.",
  "后端尚未完成此功能的交付与安全验收。":
    "This server has not enabled the feature and its security acceptance.",
  "原记录已变化，请重新打开并核对。":
    "The original record changed. Reopen and review.",
  "无法读取原操作记录，本次未提交。":
    "Cannot read the original operation record. This request was not submitted.",
  "工作时间保存结果仍无法核对；保留原记录，联系维护者核查，不自动重写。":
    "The working-hours save result cannot be verified. Keep the record and ask the maintainer to investigate. No automatic rewrite.",
  "操作尚未核对完成，原记录保留；请读取当前状态后明确核对原请求。":
    "The operation is unverified. Its original record is kept. Read current state and explicitly check the original request.",
  "结果归属无法核对，原记录保留。":
    "Cannot verify result ownership. The original record is kept.",
  "响应与原操作的归属或版本不符，原记录保留。":
    "Response ownership or version differs from the original operation. Its record is kept.",
  "连接中断，原内容与编号已保留，没有自动重发。":
    "Connection lost. The original content and ID are kept. No automatic resend.",
  "先核对已有原操作。": "Check the existing original operation first.",
  "操作内容无效。": "Invalid operation content.",
  "本次未提交，无法保存原操作。":
    "Not submitted: the original operation could not be saved.",
  "数据读取失败，请刷新重试。": "Data read failed. Refresh and retry.",
  "请先刷新并核对最新数据，再执行操作。":
    "Refresh and verify current data before operating.",
  "请重新核对当前提议。": "Review the current proposal again.",
  "已保存本次提议；仍需客户核实的信息保持待确认，日历与待办按确认状态更新。":
    "Proposal saved. Information needing customer verification stays pending; calendar and tasks follow the confirmation state.",
  "商户已接受此提议；日历与待办按工单的当前确认状态更新。":
    "Merchant accepted the proposal. Calendar and tasks follow the order's current confirmation state.",
  "商户已接受此值，仍等待客户核实；这不代表客户已经确认。":
    "Merchant accepted the value; customer verification is still pending. This is not customer confirmation.",
  "已失效，需复核": "Invalidated: review required",
  "业务或来源消息已经变化。这条历史提议不能再确认，请核对当前有效提议。":
    "Business or source messages changed. This historical proposal cannot be confirmed. Review the current valid proposal.",
  时间冲突: "Time conflict",
  "该时段与另一项已确认预约重叠，不能确认。":
    "This slot overlaps another confirmed appointment and cannot be confirmed.",
  待商户确认: "Awaiting merchant confirmation",
  "商户接受后会保存此值；仍需客户核实的内容保持待确认，日历与准备待办按确认状态处理。":
    "Merchant acceptance saves the value. Information needing customer verification stays pending. Calendar and preparation tasks follow the confirmation state.",
  "无法下载日历，请恢复连接后重试。":
    "Cannot download the calendar. Restore the connection and retry.",
  "预约的来源消息已变化、撤回或无法核对，暂不能导出；请先核对原文。原预约仍保留。":
    "Appointment sources changed, were revoked or cannot be checked. Review sources before exporting. The original appointment is kept.",
  "预约已变化、未确认或不可导出，请刷新核对。":
    "The appointment changed, is unconfirmed or cannot be exported. Refresh and review.",
  "服务没有返回日历文件，请联系维护者。":
    "The service did not return a calendar file. Contact the maintainer.",
  "日历文件无效，未进行下载。":
    "Invalid calendar file. Nothing was downloaded.",
  "无法核对关联工单。": "Cannot verify the linked order.",
  "已结束工单仅保留历史，不能导出。":
    "Closed orders keep history but cannot be exported.",
  "预约与工单版本不一致，请刷新核对。":
    "Appointment and order versions differ. Refresh and review.",
  "暂定或未确认预约不能导出。":
    "Tentative or unconfirmed appointments cannot be exported.",
  "已授权{0}": "Authorised {0}",
  "未命名{0}": "Unnamed {0}",
  接收授权已暂停: "Reception permission paused",
  "点击「恢复消息接收」重新启用已选会话的接收授权。":
    "Choose Resume reception to restore access for selected chats.",
  "⚠ 消息可能没有同步：暂时无法确认连接状态":
    "⚠ Messages may not be synced: connection status is unverified",
  "上次状态已过期或查询失败。请先刷新状态，确认后再操作。":
    "The last status expired or reading failed. Refresh and verify before operating.",
  "✓ WhatsApp 已连接": "✓ WhatsApp connected",
  "无需再次扫码。消息处理是否就绪，请查看下方处理链路。":
    "No need to scan again. Check the processing pipeline below for message readiness.",
  "⚠ 消息暂时无法同步：WhatsApp 已断开":
    "⚠ Messages cannot sync: WhatsApp disconnected",
  "重新连接本机 WhatsApp 会话，获取新二维码后用手机扫码。":
    "Reconnect the local WhatsApp session, get a new QR code and scan it with your phone.",
  "扫描二维码，连接 WhatsApp": "Scan to connect WhatsApp",
  "请在手机 WhatsApp 的「关联设备」中扫码；二维码会自动更新。":
    "Use Linked devices in WhatsApp on your phone. The QR code updates automatically.",
  "正在确认 WhatsApp 连接": "Checking WhatsApp connection",
  "服务正在准备连接。请刷新状态，暂时无需重复重连。":
    "The service is preparing the connection. Refresh status; no repeated reconnection is needed.",
  业务扩展与安全验收: "Business features & security review",
  "本版已接通归单、延期、需求、工作时间、摘要、交付检查和归档。":
    "Assignment, deferral, requirements, working hours, summaries, delivery checks and archiving are connected in this version.",
  导出手机日历: "Export to phone calendar",
  "需要本版后端提供只读日历下载接口。":
    "Requires this backend's read-only calendar download API.",
  "本版支持从已授权会话建单；需要引用客户原文并明确确认。":
    "Create from an authorised conversation using customer source messages and explicit confirmation.",
  "开始、等待客户、完成和取消工单":
    "Start, wait for customer, complete or cancel an order",
  "本版支持状态操作；完成或取消会处理自动待办与未发送草稿。":
    "Status operations are available. Completion or cancellation closes generated tasks and unsent drafts.",
  确认地址和补齐缺项: "Confirm address & resolve missing information",
  "本版支持确认时间和地址提议；仍未获客户确认的值会保持待确认。":
    "Review time and address proposals. Values not confirmed by the customer remain pending.",
  人工归单与延期跟进: "Manual assignment & deferred follow-up",
  "已接通当前消息归单、忽略及延期跟进；更改会重新核对来源和版本。":
    "Current-message assignment, dismissal and deferred follow-up are connected. Sources and versions are rechecked on changes.",
  业务审批后发送及关联回执: "Business sending & linked receipts",
  "已接通准确的审批与发送记录；需单独授权对应聊天，未知结果先核查，不自动重发。":
    "Approval is linked to an exact sending record. Authorise the chat separately. Check unknown results; no automatic resend.",
  "AI 文字理解": "AI text understanding",
  "文字模型须由维护者在服务端配置、授权并核对费用。模型只提建议；媒体识别与独立现场验收另列，不代表自动建单。":
    "The maintainer must configure, authorise and price the text model on the server. Models only suggest. Media and independent live acceptance are separate; this does not mean automatic order creation.",
  "浏览器无法保存或读取原操作。可以查看数据，暂不能提交；恢复存储后重新打开并核对。":
    "Browser storage cannot save or read the original operation. Viewing is available but submission is blocked. Restore storage, reopen and check.",
  "原操作记录不可用或已被另一页面改变，请恢复后重新打开核对。":
    "The original operation record is unavailable or changed in another page. Restore storage and reopen to check.",
  "操作响应已核对，但原记录清理失败。禁止新提交，请恢复存储后核对原编号。":
    "The response was verified but its original record could not be cleared. New submission is blocked. Restore storage and check the original ID.",
  "该会话已有未结束工单，请刷新查看；另开一单需要再次明确确认。":
    "This conversation already has an open order. Refresh to view it. Another order requires fresh explicit confirmation.",
  "时间与已有预约冲突，请核对日历后修改。":
    "This time conflicts with an existing appointment. Review the calendar and edit it.",
  "登录已过期；原操作记录保留，请重新登录核对。":
    "Session expired. The original operation record is kept. Sign in again to check.",
  "操作未确认完成，请刷新；若保留了原编号，只能明确核对该原操作。":
    "Operation not verified as complete. Refresh. If an original ID is kept, explicitly check that operation only.",
  "响应无法完整核对，原请求保留；请勿重复创建或确认。":
    "Response cannot be fully verified. Original request kept. Do not create or confirm repeatedly.",
  "连接中断，无法确定是否已保存。原请求已保留，请恢复服务后核对，勿重复提交。":
    "Connection lost; cannot tell whether saving completed. Original request kept. Restore the service and check; do not submit again.",
  "先核对已有原操作，不能提交新操作。":
    "Check the existing original operation before submitting a new one.",
  "操作内容无效，请重新核对。": "Invalid operation content. Review again.",
  "原操作无法安全保存，本次未提交。":
    "Original operation could not be safely stored. Nothing was submitted.",
  "没有可核对的原操作。": "No original operation to check.",
  "尚未核对到原操作的已保存结果；记录保留。这不代表未执行，不能另开重复请求。":
    "No saved result verified yet. The record is kept. This does not prove non-execution; do not create a duplicate request.",
  "保存结果的归属或版本无法核对，原记录保留。":
    "Cannot verify the saved result's owner or version. Original record kept.",
  "暂时无法只读核对原操作；记录保留，没有重发。":
    "Read-only checking is unavailable. The original record is kept. Nothing was resent.",
  "先只读核对到原操作的已保存结果，再结束记录。":
    "Verify the original saved result with a read-only check before closing its record.",
  "暂时无法读取，请刷新。": "Reading unavailable. Please refresh.",
  "请求结果待确认，请刷新状态；不要另建请求重试。":
    "Request result unverified. Refresh status; do not create another request to retry.",
  请求失败: "Request failed",
  "响应未能完整读取，请重新核对状态；不要另建请求重试。":
    "Response incomplete. Check status; do not create another request to retry.",
  "操作尚未完成，请刷新状态或明确核对；不要重复提交。":
    "Operation unfinished. Refresh or explicitly check it; do not submit again.",
  "上次请求结果待确认，请使用原请求核对。":
    "The previous request needs checking. Use its original request identity.",
  "未能读取操作编号，请使用原请求核对。":
    "Cannot read the operation ID. Check with the original request.",
  "列表数据无效，请刷新后重试。": "Invalid list data. Refresh and retry.",
  "列表分页异常，请刷新后重试。": "Invalid pagination. Refresh and retry.",
  "没有待核对的原请求。": "No original request needs checking.",
  "没有待核对操作。": "No operation needs checking.",
  "二维码图片无效。": "Invalid QR image.",
  "请求未能确认，请刷新核对；不要另建模型请求。 ":
    "Request unverified. Refresh and check; do not create another model request.",
  "附件暂不可用，请核对授权、来源和处理状态。":
    "Attachment unavailable. Check permission, sources and processing state.",
  "响应未能完整读取，请核对已有任务。":
    "Response incomplete. Check the existing job.",
  "请保留原读取范围与同意选项核对原请求。":
    "Keep the original read range and consent choices when checking the original request.",
  "任务响应无效，请保留原请求核对。":
    "Invalid job response. Keep and check the original request.",
  "请先核对当前结果来源。": "Review the current result's sources first.",
  "请求结果待核对，请刷新已有记录，不要另建发送任务。":
    "Request result unverified. Refresh existing records; do not create another sending task.",
  "发送操作未完成，请核对权限和已有记录。":
    "Sending operation unfinished. Check permission and existing records.",
  "响应不完整，请核对已有记录。":
    "Response incomplete. Check existing records.",
  "发送响应无法核对，请读取原请求记录。":
    "Cannot verify sending response. Read the original request record.",
  "查询失败，请刷新；同步请求重试须保留原请求。":
    "Lookup failed. Refresh. A sync retry must keep its original request.",
  "同步接口尚不可用，请先完成本批次后端迁移并重建服务。":
    "Sync API unavailable. Complete this backend migration and rebuild the service first.",
  "原同步请求尚待核对，请保留原参数后重试。":
    "Original sync request unverified. Keep the original parameters for checking.",
  待归类: "Unclassified",
  待确认: "Awaiting confirmation",
  等待顾客: "Waiting for customer",
  待复核: "Needs review",
  尚未询问: "Not asked yet",
  等待顾客确认: "Awaiting customer confirmation",
  顾客已确认: "Customer confirmed",
  "回复含糊，待核对": "Ambiguous reply: review needed",
  待处理: "Pending",
  受阻: "Blocked",
  时间安排: "Schedule",
  数量: "Quantity",
  规格: "Specification",
  截止时间: "Deadline",
  "{0} 全天（{1}）": "{0} all day ({1})",
  "{0}（香港时间）": "{0} (Hong Kong time)",
  "{0} → {1}（香港时间；原时区 {2}）":
    "{0} → {1} (Hong Kong time; original zone {2})",
  "未提供标题（日历 {0}）": "Title unavailable (calendar {0})",
  "暂时无法连接本地服务，请检查服务后刷新。":
    "Cannot reach the local service. Check it and refresh.",
  "暂时无法确认操作结果。请恢复服务并刷新核对，避免反复提交。":
    "Cannot verify the operation result. Restore service and refresh before submitting again.",
  "账号或密码不正确，请重新输入。":
    "Incorrect username or password. Please try again.",
  "业务或消息已更新，请刷新并重新核对当前提议。":
    "Business or messages changed. Refresh and review the current proposal.",
  "来源消息已变化，请刷新并重新核对。":
    "Source message changed. Refresh and review.",
  "该时段与其他预约冲突，不能确认，请刷新查看。":
    "This time conflicts with another appointment. Refresh to check; confirmation unavailable.",
  "当前处理授权已暂停，请联系接入负责人核对。":
    "Processing permission is paused. Contact the integration maintainer to check.",
  "当前环境尚未允许此网页地址登录，请联系负责配置的队友确认。":
    "This service does not allow login from the current web address. Ask the configuration maintainer.",
  "登录验证已变化，请退出后重新登录。":
    "Login validation changed. Sign out and sign in again.",
  "当前工单或会话不可用，请刷新并检查当前账号和会话授权。":
    "Current order or conversation unavailable. Refresh and check the account and chat permission.",
  "暂时无法读取数据，请检查本地服务后刷新。":
    "Data temporarily unavailable. Check the local service and refresh.",
  "操作未能完成或结果暂无法确认，请刷新核对后再操作。":
    "Operation unfinished or outcome unverified. Refresh and check before acting again.",
  "服务响应无效，请刷新核对当前状态。":
    "Invalid service response. Refresh and check current state.",
  "列表数据无效，请刷新重试。": "Invalid list data. Refresh and retry.",
  "分页数据未能完整读取，请刷新重试。":
    "Pagination was not read completely. Refresh and retry.",
  "当前工单没有可核对的对话，请联系后端负责人。":
    "This order has no verifiable conversation. Contact the backend maintainer.",
  "工单没有可核对的对话。": "This order has no verifiable conversation.",
  "对话范围或版本无效，请刷新核对。":
    "Invalid conversation scope or version. Refresh and check.",
  "业务已切换，请刷新并重新核对。":
    "The selected business changed. Refresh and review again.",
  "当前只能确认时间或地址提议。":
    "Only time or address proposals can be confirmed here.",
  "来源对话或消息版本无法核对，请刷新并重新审核。":
    "Cannot verify the source conversation or message revision. Refresh and review again.",
  "手动与业务审批发送均需单独授权。AI 润色和自由生成自动回复尚未接通。":
    "Manual sending requires separate permission. AI polishing and freely generated automatic replies are not available.",
  "这里保存你的批准决定；到业务管理另行核对并提交发送。批准不等于已发送。":
    "This page records your approval. Submit the approved reply separately in Business management; approval does not mean sent.",
  "这是当前工单关联的会话；业务管理提交时由服务端核对准确的 WhatsApp 聊天。":
    "This conversation belongs to the order. The server resolves the exact WhatsApp chat when submitting in Business management.",
  "待办随已确认安排更新。可到业务管理完成或取消待办；客户确认仍需单独核对。":
    "Tasks follow confirmed arrangements. Complete or cancel them in Business management; customer confirmation remains separate.",
  "当前服务未开放此状态操作。可先查看操作影响，联系维护者确认版本。":
    "This server does not support saving the selected status. Review the impact below.",
  "其他字段请到业务管理核对；此处确认时间和地址。":
    "Review other fields in Business management. This view confirms time and address.",
  "在回复审批页核对完整草稿并批准，再到业务管理核对后提交发送。":
    "Review the complete draft on the approvals page. Approval records your decision; submit it for sending separately.",
  "查看已授权聊天，或明确导入近期记录。文字模型需服务端单独配置；语音与图片识别尚未启用，附件可单独授权预览。":
    "View authorised chats or explicitly import available recent history. Attachments require separate permission. Text models require server configuration; live speech and image recognition remain unavailable. Review partial results yourself.",
  界面语言: "Interface language",
  尚未交付的扩展: "Extensions not delivered yet",
  "真实语音与图片识别、媒体结果转工单、自由 Agent 自动回复、外部日历持续同步和独立桌面安装包尚未交付。当前文字业务可手动处理；真实服务配置与手机验收仍须由团队完成。":
    "Live speech/image recognition, media-to-order promotion, freely generated Agent auto-replies, continuous external calendar sync and standalone desktop packages are not delivered. Manual text workflows work. The team must still configure real services and perform phone acceptance.",
  "模型调用结果未知。保留原编号供维护者核查，不重新归单调用；可核对原文后手动处理或标记忽略。":
    "Model call result unknown. Keep the original ID for the maintainer. Do not reassign to invoke it again. Review sources and handle manually or dismiss.",
  "模型调用结果未知，保留原编号，不能自动重试":
    "Model result unknown: keep the original ID; no automatic retry",
  完成: "Complete",
  取消: "Cancel",
  按默认日期: "at the default date",
  "全部事项已核对。": "All items reviewed.",
  "我已知悉尚未完成的事项，仍明确结束本工单。":
    "I acknowledge the unfinished items and explicitly choose to close this order.",
  使用后端默认日期: "using the server default date",
  未定: "Undecided",
  "检查项已齐全。": "All checklist items covered.",
  "仍未完成：": "Still unfinished: ",
  "。确认仍要结束。": ". Explicitly close anyway.",
  "请核对服务后刷新。": "Check the service, then refresh.",
  来源或含义需复核: "Source or meaning needs review",
  等待客户核实与商户确认:
    "Awaiting customer verification and merchant confirmation",
  "仍有未完成检查项。请先处理，或明确核对后确认仍要结束工单。":
    "Unfinished checklist items remain. Resolve them first, or explicitly review and acknowledge closing anyway.",
  "前置待办尚未完成，请先处理依赖事项。":
    "Prerequisite tasks are unfinished. Complete them first.",
  "后端已明确拒绝本次操作，没有保存。请刷新并核对条件后重新操作。":
    "The server definitely rejected this operation; nothing was saved. Refresh and review the conditions before trying a new operation.",
  "选一张工单，按「下一步」处理就好。":
    'Pick a job and follow its "Next step".',
  商户选择不发送这条回复: "Merchant chose not to send this reply",
  "已批准。下一步：回到工单点「发送给客人」。":
    'Approved. Next: go back to the job and tap "Send to client".',
  "所有等你批准的回复都在这里。批准后再点「发送」才会发给客人。":
    'All replies waiting for your approval are here. After approving, tap "Send" to deliver.',
  刷新: "Refresh",
  "网络不稳，下面是上次读到的内容，暂时不能操作。":
    "Connection is unstable; showing the last loaded content, actions paused.",
  为什么要回复: "Why reply",
  发给: "To",
  "「{0}」的客人 · WhatsApp": 'Client of "{0}" · WhatsApp',
  回复内容: "Reply",
  有效到: "Valid until",
  "这条回复已关闭。": "This reply is closed.",
  客人原话: "Client's words",
  客人: "Client",
  "这条消息暂时读不到。": "This message can't be loaded right now.",
  重试上次操作: "Retry last action",
  批准这条回复: "Approve this reply",
  不发这条: "Don't send",
  回到工单去发送: "Back to job to send",
  重新生成回复: "Regenerate reply",
  技术信息: "Technical details",
  聊天编号: "Chat ID",
  发送已批准的回复: "Send approved replies",
  "选择要用的 WhatsApp": "Choose WhatsApp number",
  发送给客人: "Send to client",
  确认发送: "Confirm send",
  "这个时间你已有安排，建议先问客人换个时间：":
    "You're already booked then. Suggest asking the client for another time:",
  "还有信息没齐，建议这样问客人：":
    "Some details are missing. Suggested question:",
  "建议这样回复客人：": "Suggested reply:",
  "暂时读不到回复草稿，稍后会自动重试。":
    "Can't load the reply draft; will retry automatically.",
  "已批准。下一步：发送给客人。": "Approved. Next: send it to the client.",
  "这条回复不会发出。": "This reply won't be sent.",
  "操作没有完成，请稍后再试。": "That didn't go through. Please try again.",
  回复客人: "Reply to client",
  "发给：「{0}」的客人 · WhatsApp": 'To: client of "{0}" · WhatsApp',
  发送进度: "Sending progress",
  你批准: "You approve",
  发送: "Send",
  客人收到: "Client receives",
  "上一次操作还没确认结果，请到「回复审批」处理。":
    "The last action hasn't been confirmed yet; please check it in Reply approvals.",
  去处理: "Go",
  "正在保存…": "Saving…",
  "批准后再点「发送」才会发给客人；想改字可到「回复审批」。":
    'After approving, tap "Send" to deliver. To edit the text, use Reply approvals.',
  "还没连接 WhatsApp，连上后才能真正发出。":
    "WhatsApp isn't connected yet; connect it to actually send.",
  "去连接 WhatsApp": "Connect WhatsApp",
  正在确认发送结果: "Checking delivery",
  "（没有文字）": "(no text)",
  "依据：": "Based on:",
  已撤回的消息: "a deleted message",
  "客人说「{0}」": 'client said "{0}"',
  "网络不稳，下面是上次读到的内容，暂时不能确认。":
    "Connection is unstable; showing the last loaded content, confirming paused.",
  我的工单: "My jobs",
  搜索: "Search",
  客人或工作: "Client or job",
  状态: "Status",
  时间未定: "Time not set",
  "没有符合条件的工单。": "No matching jobs.",
  "还没有工单。先到「WhatsApp 连接」选好要处理的聊天，再点「新建工单」。":
    "No jobs yet. Choose chats under WhatsApp connection, then tap New job.",
  "暂时读不到工单，请稍后刷新。":
    "Can't load jobs right now; please refresh later.",
  "在左边选一张工单。": "Pick a job on the left.",
  "正在打开工单…": "Opening job…",
  下一步: "Next step",
  "这张工单已经结束。": "This job is closed.",
  "还缺：{0}": "Still missing: {0}",
  "都安排好了，没有要你处理的事。": "All set — nothing for you to do.",
  "客人想改时间，但和「{0}」撞了":
    'Client wants a new time, but it clashes with "{0}"',
  "客人提了新的{0}": "Client suggested a new {0}",
  确认新地址: "Confirm new address",
  确认新时间: "Confirm new time",
  "聊天里有新消息，这条提议已过时。":
    "There are newer messages; this suggestion is out of date.",
  "工单已结束，不能再改。": "This job is closed and can't be changed.",
  "地址确认功能还没开放。": "Address confirmation isn't available yet.",
  "请稍等，正在同步最新内容。": "One moment, syncing the latest content.",
  "这类内容请到「业务管理」的需求与交付里确认。":
    "Confirm this under Business management → Requirements & delivery.",
  "确认后，「{0}」改为 {1}。日历和准备待办会一起更新。":
    '"{0}" will move to {1}. Your calendar and prep to-dos update too.',
  "客人还没明确答应，会先记成「暂定」，等客人确认后再变正式。":
    "The client hasn't clearly agreed yet, so it's saved as tentative until they confirm.",
  "内容刚更新了，请重新看一眼再确认。":
    "This just changed; please take another look before confirming.",
  确认: "Confirm",
  先不: "Not now",
  安排: "Details",
  等客人确认: "Waiting for client",
  需要你看一下: "Please check",
  还没有: "Not yet given",
  "改动记录（{0}）": "Change history ({0})",
  已过时: "Out of date",
  聊天记录: "Chat history",
  显示聊天: "Show chat",
  "聊天 {0}": "Chat {0}",
  我: "Me",
  "（这条消息已撤回）": "(message deleted)",
  "还没有聊天记录。": "No chat history yet.",
  "更多操作（开始、完成、取消工单）": "More actions (start, complete, cancel)",
  我的日程: "My schedule",
  未命名工单: "Untitled job",
  "还没有安排。": "Nothing scheduled yet.",
  这张工单要做的事: "To-dos for this job",
  "截止 {0}": "Due {0}",
  要等前一件事做完: "waiting on an earlier step",
  "暂时没有要做的事。": "Nothing to do for now.",
  "（按 {0} 时间）": " ({0} time)",
  "{0}全天": "{0} all day",
  "依据的消息暂时读不到，先别确认。":
    "The source message can't be loaded; hold off confirming.",
  "客人说了时间，但还不完整": "The client gave a time, but it's incomplete",
  "客人提到的{0}需要你看一下": "Please check the {0} the client mentioned",
  "还不知道几点结束（或要多久），先问客人，问清楚后才能放进日历。":
    "The end time (or duration) is unknown. Ask the client first; it goes on the calendar once that's clear.",
  "意思不够明确，先和客人确认一下。":
    "It's not clear enough yet; check with the client first.",
  "{0} 开始": "starts {0}",
};
export const cantonese: Record<string, string> = {
  ...conversationCantonese,

  "读取期间登录、授权或数据发生变化，请刷新并核对会话授权。":
    "讀取期間登入、授權或者資料有變，請重新整理同核對對話授權。",
  "聊天、授权或工单已变化，这条旧提议不能直接确认。":
    "對話、授權或者工單有變，呢條舊提議唔可以直接確認。",

  功能状态与操作入口: "功能狀態同操作入口",
  现在可以使用: "而家可以用",
  状态未核实: "狀態未核實",
  当前服务未启用: "目前服務未啟用",
  打开此功能: "開啟功能",
  "这条会话没有开放工单。新需求可以从这里手动建单。":
    "呢段對話冇未結束嘅工單。新需求可以喺呢度手動建單。",
  为这条会话新建工单: "為呢段對話新建工單",
  处理这条消息: "處理呢條訊息",
  "归单会重新生成待核对提议；忽略只表示这条消息无需处理。手动建单不会自动清除此复核事项。":
    "歸單會重新產生待核對提議；忽略只代表呢條訊息唔使處理。手動建單唔會自動清除呢項覆核。",
  "这条记录不是当前可处理轮次，或原文尚未核实。请刷新并处理最新记录。":
    "呢條記錄唔係而家可處理嘅輪次，或者原文未核實。請重新整理並處理最新記錄。",
  "模型调用结果未知，只能核查原请求或明确忽略，不能重新归单调用。":
    "模型結果未知，只可以核查原請求或者明確忽略，唔可以重新歸單再叫模型。",

  "时间尚不完整或格式需核对。请补充结束时间或时长，再生成可确认的日历提议。":
    "時間未齊或者格式要核對。請補充結束時間或者時長，再產生可以確認嘅日曆提議。",
  "跟进时间无效，请输入完整有效的香港日期和时间。":
    "跟進時間唔正確，請輸入完整有效嘅香港日期同時間。",
  "当前后端版本未提供此功能。": "目前後端版本未提供呢個功能。",
  业务工作台: "工作台",
  新建工单: "開工作單",
  回复审批: "批核回覆",
  日历与待办: "日曆同待辦",
  人工复核: "人手核對",
  "WhatsApp 连接": "WhatsApp 連線",
  功能与使用说明: "功能同用法",
  业务管理: "工作管理",
  "登录已过期，请重新登录。": "登入已過期，請重新登入。",
  "后端能力状态不完整，请联系维护者更新服务。":
    "後端能力狀態不完整，請聯繫維護者更新服務。",
  无法读取功能状态: "無法讀取功能狀態",
  "登录失败，请重试。": "登入失敗，請重試。",
  "已退出。": "已退出。",
  "已退出，请重新登录。": "已退出，請重新登入。",
  "暂时无法退出，请重试。": "暫時未能退出，請重試。",
  旧入口已停用: "舊入口已停用",
  "本版只连接维护者配置的业务服务。为避免旧地址意外切换数据，请确认服务地址后再打开工作台。旧操作记录不会自动搬运。":
    "本版只連接維護者配置的業務服務。為避免舊地址意外切換數據，請確認服務地址後再打開工作台。舊操作記錄不會自動搬運。",
  打开当前工作台: "開目前工作台",
  跳到主要内容: "跳去主要內容",
  跟單: "跟單",
  把业务安排清楚: "將工作安排清楚",
  退出: "登出",
  为独立工作者整理每一次约定: "幫自由工作者整理每次約定",
  "从聊天里的约定，": "由對話入面嘅約定，",
  "到日历上的安排。": "到日曆上嘅安排。",
  "核对客户原文、管理工单和回复审批，让下一步清楚可见。":
    "核對客人原文、管理工作單和回覆審批，讓下一步清楚可見。",
  "登录后可查看功能状态；未接通的能力会明确标注。":
    "登入後可查看功能狀態；未接通的能力會明確標注。",
  "登录 GigMate": "登入 GigMate",
  "使用维护者为你配置的账号。": "使用維護者為你配置的帳戶。",
  账号: "帳戶",
  密码: "密碼",
  "正在登录…": "登入緊…",
  进入工作台: "入工作台",
  "这是 GigMate 的账号，不是 WhatsApp 手机账号。没有账号或忘记密码时，请联系维护者。":
    "這是 GigMate 的帳戶，不是 WhatsApp 手機帳戶。沒有帳戶或忘記密碼時，請聯繫維護者。",
  工作台页面: "工作台頁面",
  我的工作空间: "我嘅工作空間",
  收起: "收埋",
  更多: "更多",
  "每一份约定，清楚有序。": "每一份約定，都清清楚楚。",
  "暂时无法核对后端功能状态，依赖功能保持关闭。请在功能说明页查看详情。":
    "暫時未能核對後端功能狀態，依賴功能保持關閉。請在功能說明頁查看詳情。",
  "安排好，下一步。": "安排好，行下一步。",
  "从客户原文到正式安排，每一步都由你确认。":
    "由客人原文到正式安排，每一步都由你確認。",
  "批准后，请到业务管理核对准确正文并提交发送。需先在连接页单独授权对应聊天；批准和提交都不代表客户已收到。":
    "批准後，請到業務管理核對準確正文並提交發送。需先在連接頁單獨授權對應對話；批准和提交都不代表客人已收到。",
  "手动发送网关已提供，需要单独发送授权。AI 润色、业务审批直发与自由生成自动回复尚未接通。":
    "手動發送網關已提供，需要單獨發送授權。AI 潤色、業務審批直發與自由生成自動回覆未接通。",
  "你的聊天由你授权；正式安排需要确认。批准、发送与客户确认是不同步骤。":
    "你的對話由你授權；正式安排需要確認。批准、發送與客人確認是不同步驟。",
  "暂时无法读取审批列表，请刷新。": "暫時未能讀取審批列表，請刷新。",
  "草稿、工单或原文已更新，请重新核对。":
    "草稿、工作單或原文已更新，請重新核對。",
  "请先读取草稿。": "請先讀取草稿。",
  "批准已保存；消息尚未提交发送。": "批准已保存；消息未提交發送。",
  "新的待审批草稿已生成，需要再次核对批准。":
    "新的待審批草稿已生成，需要再次核對批准。",
  "操作结果已确认，正在重新读取当前状态。":
    "操作結果已確認，正在重新讀取當前狀態。",
  "操作结果暂未确认，请核对原请求。": "操作結果暫未確認，請核對原請求。",
  回复审批工作台: "回覆審批工作台",
  "先核对收件会话和正文，再批准。": "先核對收件會話和正文，再批准。",
  "这里保存你的批准决定。当前尚未接通 WhatsApp 发送；批准不等于已发送。":
    "這裡保存你的批准決定。當前未接通 WhatsApp 發送；批准不等於已發送。",
  "正在读取审批数据…": "正在讀取審批數據…",
  "没有你的明确批准，草稿不会执行。": "未經你明確批准，草稿唔會執行。",
  "下面是上次读取的数据，当前不能提交操作。":
    "下面是上次讀取的數據，當前不能提交操作。",
  有一笔原请求等待核对: "有一筆原請求等待核對",
  "刷新只读取状态，不会再次批准。核对这份草稿后，可用原请求、原版本和原编号核对结果；不会创建另一笔请求。":
    "刷新只讀取狀態，不會再次批准。核對這份草稿後，可用原請求、原版本和原編號核對結果；不會創建另一筆請求。",
  查看待核对原请求: "查看待核對原請求",
  "内容更新于：{0}": "內容更新時間：{0}",
  尚未读取: "未讀取",
  刷新审批: "刷新審批",
  草稿与历史: "草稿與歷史",
  审批筛选: "審批篩選",
  全部历史: "全部歷史",
  "当前选择不在筛选结果中，右侧仍保留该草稿。":
    "當前選擇不在篩選結果中，右側仍保留該草稿。",
  "此筛选下没有草稿。": "此篩選下沒有草稿。",
  "等待审批列表。": "等待審批列表。",
  "新的回复草稿会显示在这里，请稍后刷新；没有草稿不代表已经发送。":
    "新的回覆草稿會顯示在這裡，請稍後刷新；沒有草稿不代表已經發送。",
  所属工单未载入: "所屬工作單未載入",
  有效至: "有效至",
  "选择一份草稿，查看收件会话、正文和原文依据。":
    "選擇一份草稿，查看收件會話、正文和原文依據。",
  当前工单: "呢張工作單",
  为什么需要回复: "為什麼需要回覆",
  "收件会话（系统编号）": "收件會話（系統編號）",
  "这是当前工单关联的会话；实际 WhatsApp 收件人映射和发送桥接尚未接通。":
    "這是當前工作單關聯的會話；實際 WhatsApp 收件人映射和發送橋接未接通。",
  草稿正文: "草稿全文",
  有效期: "有效期",
  "（已到期）": "（已到期）",
  版本核对: "版本核對",
  草稿第: "草稿第",
  "版；工单": "版；工作單",
  "→ 当前": "→ 當前",
  未知: "未知",
  "；聊天": "；對話",
  不可读取: "不可讀取",
  "关闭原因：": "關閉原因：",
  "后端已关闭此草稿，请核对当前业务。": "後端已關閉此草稿，請核對當前業務。",
  "你记录的原因：": "你記錄的原因：",
  "批准时间：": "批準時間：",
  原文依据: "原文出處",
  消息: "消息",
  "· 第": "· 第",
  "版 ·": "版 ·",
  该版本不可读取: "該版本不可讀取",
  "原文已撤回，不能据此批准。": "原文已撤回，不能據此批准。",
  原文未提供文字: "原文未提供文字",
  "没有可核对的原文，不补造内容。": "沒有可核對的原文，不補造內容。",
  核对这份草稿: "核對呢份草稿",
  本次核对: "本次核對",
  "接收会话：": "接收會話：",
  "我已核对收件会话、完整正文、原文与版本。":
    "我對過收件對話、完整正文、原文同版本。",
  "拒绝／取消原因": "拒絕／取消原因",
  "例如：需要先和客户确认其他时间": "例如：需要先和客人確認其他時間",
  核对后重试原请求: "核對後重試原請求",
  批准这份草稿: "批准呢份草稿",
  拒绝草稿: "拒絕草稿",
  取消待执行草稿: "取消待執行草稿",
  重新生成待审批问题: "重新生成待審批問題",
  "拒绝和取消只关闭本机尚未执行的草稿；执行中的发送不能假装撤回。重新提问会生成新草稿，不会直接发送。":
    "拒絕和取消只關閉本機未執行的草稿；執行中的發送不能假裝撤回。重新提問會生成新草稿，不會直接發送。",
  "执行结果由后端核对。此页面不会重新发送消息。":
    "執行結果由後端核對。此頁面不會重新發送消息。",
  草稿归属无法核对: "草稿歸屬無法核對",
  来源范围无法核对: "來源範圍無法核對",
  连接归属无法核对: "連接歸屬無法核對",
  "所选连接没有唯一对应的已授权聊天，请回连接页核对。":
    "所選連接沒有唯一對應的已授權對話，請回連接頁核對。",
  "发送记录归属或正文不一致，不能使用此关联":
    "發送記錄歸屬或正文不一致，不能使用此關聯",
  归单与业务回复: "歸單與業務回覆",
  读取当前归单与回复: "讀取當前歸單與回覆",
  人工归单: "人工歸單",
  待复核消息: "待復核消息",
  选择一条: "選擇一條",
  会话: "會話",
  当前原文: "目前原文",
  已撤回: "已撤回",
  归入工单: "歸入工作單",
  选择已有开放工单: "選擇已有開放工作單",
  核对归单: "核對歸單",
  "将当前会话 v{0} 的这条消息归入“{1}”，仅记录归属，不自动确认业务字段。":
    "將當前會話 v{0} 的這條消息歸入“{1}”，僅記錄歸屬，不自動確認業務字段。",
  标记无需归单: "標記無需歸單",
  "将当前会话 v{0} 的这条消息标记为无需归单，不创建工单，不发送回复。":
    "將當前會話 v{0} 的這條消息標記為無需歸單，不創建工作單，不發送回覆。",
  修改回复与发送记录: "修改回覆與發送記錄",
  业务草稿: "業務草稿",
  选择草稿: "揀草稿",
  收件会话: "收件會話",
  "· 有效至": "· 有效至",
  修改正文: "修改全文",
  核对修改草稿: "核對修改草稿",
  "修改发给会话 {0} 的第 {1} 版草稿，新正文：“{2}”。保存后生成新版本，仍需另行批准，不会发送。":
    "修改發給會話 {0} 的第 {1} 版草稿，新正文：“{2}”。保存後生成新版本，仍需另行批准，不會發送。",
  发送连接: "發送連接",
  选择已授权连接: "選擇已授權連接",
  "需先在 WhatsApp 连接页授权此会话发送；这里不会扩大授权范围。":
    "需先在 WhatsApp 連接頁授權此會話發送；這裡不會擴大授權範圍。",
  核对并提交业务发送: "核對後提交回覆",
  "把已批准草稿 r{0} 交给连接 {1}，收件会话 {2}，完整正文：“{3}”。连接 v{4}／发送授权 v{5}。提交不代表客户收到；结果未知时先核对，禁止另建发送。":
    "把已批准草稿 r{0} 交給連接 {1}，收件會話 {2}，完整正文：“{3}”。連接 v{4}／發送授權 v{5}。提交不代表客人收到；結果未知時先核對，禁止另建發送。",
  "已通过当前账号核对关联回执：": "已通過當前帳戶核對關聯回執：",
  "。取消、对账或人工核查请到 WhatsApp 消息页选择此记录":
    "。取消、對賬或人工核查請到 WhatsApp 消息頁選擇此記錄",
  操作无法核对: "操作無法核對",
  "保存结果已确认，正在读取当前状态。": "保存結果已確認，正在讀取當前狀態。",
  工单归属无法核对: "工作單歸屬無法核對",
  掌握每一步: "掌握每一步",
  "今日事项、工作时间、客户需求和交付核对。":
    "今日事項、工作時間、客人需求和交付核對。",
  刷新业务管理: "刷新業務管理",
  今日概览: "今日一覽",
  今天要做: "今日要做",
  等待客户: "等緊客人",
  即将到期: "就快到期",
  需要决定: "要你決定",
  查看工单: "睇工作單",
  暂无事项: "暫時冇事項",
  工作时间与排期设置: "工作時間與排期設置",
  时区: "時區",
  开始时间: "開始時間",
  结束时间: "結束時間",
  默认预约分钟: "默認預約分鐘",
  预约间隔分钟: "預約間隔分鐘",
  准备提前分钟: "準備提前分鐘",
  工作日: "工作日",
  一: "一",
  二: "二",
  三: "三",
  四: "四",
  五: "五",
  六: "六",
  日: "日",
  周: "周",
  休息时段: "休息時段",
  "休息开始 {0}": "休息開始 {0}",
  "休息结束 {0}": "休息結束 {0}",
  移除: "移除",
  添加休息时段: "添加休息時段",
  核对排期设置: "核對排期設置",
  "更新排期 v{0}：{1}，周{2}，{3}–{4}，休息 {5}；预约 {6} 分钟、间隔 {7} 分钟、提前准备 {8} 分钟。":
    "更新排期 v{0}：{1}，周{2}，{3}–{4}，休息 {5}；預約 {6} 分鐘、間隔 {7} 分鐘、提前準備 {8} 分鐘。",
  工单需求与交付: "工作需求同交付",
  选择工单: "揀工作單",
  请选择: "請揀選",
  排期核对: "排期核對",
  "当前没有检测到排期风险。": "當前沒有檢測到排期風險。",
  "候选时间，仍须与客户核实": "候選時間，仍須與客人覈實",
  交付检查: "交付檢查",
  待完成: "未做完",
  已核对: "核對咗",
  "目前检查项齐全。": "目前檢查項齊全。",
  "请先处理未完成事项；确需结束时必须明确确认。":
    "請先處理未完成事項；確需結束時必須明確確認。",
  "本次客户原文依据（主会话）": "本次客人原文依據（主會話）",
  业务操作原文: "業務操作原文",
  先选择当前客户消息: "先選擇當前客人消息",
  无文字: "無文字",
  客户稍后确认: "客人遲啲先確認",
  待确认项目: "待確認項目",
  地址: "地址",
  时间: "時間",
  "跟进时间（香港时间；留空则按后端默认）":
    "跟進時間（香港時間；留空則按後端默認）",
  核对延期跟进: "核對稍後跟進",
  "工单 v{0}：客户稍后确认{1}，{2} 跟进；依据“{3}”。保留缺项，暂停对此项的追问。":
    "工作單 v{0}：客人稍後確認{1}，{2} 跟進；依據“{3}”。保留缺項，暫停對此項的追問。",
  "添加资料、承诺或问题": "添加資料、承諾或問題",
  类型: "類型",
  所需资料: "所需資料",
  双方承诺: "雙方承諾",
  未决问题: "未決問題",
  由谁完成: "由誰完成",
  客户: "客人",
  商户: "你／商戶",
  内容: "內容",
  "期限（可留空）": "期限（可留空）",
  核对新增条目: "核對新增條目",
  "工单 v{0}：{1}负责“{2}”，期限 {3}。依据“{4}”；资料与承诺将按规则生成待办。":
    "工作單 v{0}：{1}負責“{2}”，期限 {3}。依據“{4}”；資料與承諾將按規則生成待辦。",
  未完成: "未做完",
  已完成: "做完",
  已取消: "已取消",
  标记已完成: "標記已完成",
  取消此条目: "取消此條目",
  "工单 v{0}：将“{1}”标记为{2}，关联待办同步收尾。":
    "工作單 v{0}：將“{1}”標記為{2}，關聯待辦同步收尾。",
  拒绝提议的原因: "拒絕提議的原因",
  提议: "提議",
  已确认: "已確認",
  仍待核实: "仍待覈實",
  "· 工单 v": "· 工作單 v",
  接受此提议: "接受此提議",
  "工单 v{0}／会话 v{1}：接受{2}“{3}”。客户未确认的值仍保持待核实。":
    "工作單 v{0}／會話 v{1}：接受{2}“{3}”。客人未確認的值仍保持待覈實。",
  拒绝此提议: "拒絕此提議",
  "工单 v{0}：拒绝{1}提议，原因“{2}”。保留原安排及历史。":
    "工作單 v{0}：拒絕{1}提議，原因“{2}”。保留原安排及歷史。",
  检查后结束工单: "檢查後結束工作單",
  "完成“{0}” v{1}。{2} 自动待办收尾、释放时段，保留历史。":
    "完成“{0}” v{1}。{2} 自動待辦收尾、釋放時段，保留歷史。",
  归档此工单: "封存呢張工作單",
  "归档已结束的“{0}” v{1}，保留历史，不删除数据。":
    "歸檔已結束的“{0}” v{1}，保留歷史，不刪除數據。",
  "日历文件已下载，请在自己的日历中确认导入。改期后需重新导入或手动更新。":
    "日曆文件已下載，請在自己的日曆中確認導入。改期後需重新導入或手動更新。",
  导出失败: "導出失敗",
  个人安排: "我嘅安排",
  "所有时刻按香港时间显示；只有日期的安排保留原日期与时区。":
    "時間全部用香港時間顯示；淨係得日期嘅安排會保留原日期同時區。",
  刷新安排: "更新安排",
  日历显示方式: "日曆顯示方式",
  月历: "月曆",
  全部安排: "全部安排",
  "显示已完成／取消工单的日历历史": "顯示已完成／取消工作單的日曆歷史",
  上个月: "上個月",
  " 年 ": " 年 ",
  月: "月",
  下个月: "下個月",
  今天: "今日",
  "选择日期，可用方向键移动，Home／End 跳到本周首尾":
    "選擇日期，可用方向鍵移動，Home／End 跳到本週首尾",
  "{0}，{1} 项安排": "{0}，{1} 項安排",
  项安排: "項安排",
  "{0} 的安排": "{0} 的安排",
  "正在核对最新安排…": "正在核對最新安排…",
  "该范围没有安排，可切换日期或查看历史。":
    "該範圍沒有安排，可切換日期或查看歷史。",
  "还没有日历安排。正式确认工单时间后会出现在这里。":
    "還沒有日曆安排。正式確認工作單時間後會出現在這裡。",
  暂定: "暫定",
  正式: "正式",
  工单不可用: "工作單不可用",
  待核对: "待核對",
  "· 缓冲": "· 緩衝",
  分钟: "分鐘",
  "地点：": "地點：",
  "正在下载…": "下載緊…",
  "加入我的日历 (.ics)": "加到我嘅日曆 (.ics)",
  "当前后端尚未提供日历下载接口。": "當前後端未提供日曆下載接口。",
  "导出会下载包含业务标题、时间和已确认地址的文件。请妥善保存。手机／Google／Outlook 日历由你自行导入，改期不会自动同步；重复导入可能产生重复安排。":
    "導出會下載包含業務標題、時間和已確認地址的文件。請妥善保存。手機／Google／Outlook 日曆由你自行導入，改期不會自動同步；重復導入可能產生重復安排。",
  全部工单待办: "全部工作單待辦",
  待办范围: "待辦範圍",
  待处理与受阻: "待處理與受阻",
  关联工单不可用: "關聯工作單不可用",
  "截止：": "截止：",
  "依赖：": "依賴：",
  未载入的待办: "未載入的待辦",
  无: "冇",
  查看相关工单: "查看相關工作單",
  "该范围暂无待办。": "該範圍暫無待辦。",
  "待办会随已确认安排更新。手动完成／编辑待办的后端接口尚未提供，本版只读。":
    "待辦會隨已確認安排更新。手動完成／編輯待辦的後端接口未提供，本版只讀。",
  搜索已载入会话: "搜索已載入會話",
  会话名称或号码: "會話名稱或號碼",
  会话类型: "會話類型",
  全部: "全部",
  个人聊天: "個人對話",
  群聊: "群聊",
  已授权: "已授權",
  类型未提供: "類型未提供",
  "名称和类型由接入服务提供；仅提供号码时不会猜测昵称。可重新发现会话刷新名称。":
    "名稱和類型由接入服務提供；僅提供號碼時不會猜測暱稱。可重新發現會話刷新名稱。",
  显示: "顯示",
  "个结果 · 已载入": "個結果 · 已載入",
  "个会话 · 已勾选": "個會話 · 已勾選",
  "个（含其他页）": "個（含其他頁）",
  "{0} · {1} · 会话 {2}": "{0} · {1} · 會話 {2}",
  群: "群",
  人: "人",
  已保存授权: "授權已儲存",
  尚未授权: "未授權",
  " · 未提供昵称": " · 未提供暱稱",
  " · 选项已过期": " · 選項已過期",
  "没有符合筛选条件的已载入会话。修改筛选，或载入更多会话；已勾选项仍保留。":
    "沒有符合篩選條件的已載入會話。修改篩選，或載入更多會話；已勾選項仍保留。",
  会话列表分页: "會話列表分頁",
  每页: "每頁",
  "8 个": "8 個",
  "16 个": "16 個",
  "24 个": "24 個",
  第: "第",
  页: "頁",
  上一页: "上一頁",
  下一页: "下一頁",
  状态未知: "狀態未知",
  已连接: "連線咗",
  正在连接: "正在連接",
  已断开: "斷線咗",
  连接失败: "連接失敗",
  等待扫码: "等待掃碼",
  连接未启动: "連接未啓動",
  需要在手机确认: "需要在手機確認",
  "授权或连接已在其他窗口更新，请重新载入后核对。":
    "授權或連接已在其他窗口更新，請重新載入後核對。",
  "聊天选项已过期，请重新发现会话后核对选择。":
    "對話選項已過期，請重新發現會話後核對選擇。",
  "连接操作结果未知，请明确核对；不要重复重连。":
    "連接操作結果未知，請明確核對；不要重復重連。",
  "请求结果待确认，请刷新状态或使用原请求重试。":
    "請求結果待確認，請刷新狀態或使用原請求重試。",
  "服务响应未能完整读取，请刷新并核对状态。":
    "服務響應未能完整讀取，請刷新並核對狀態。",
  "消息接收已暂停，可撤销已有授权；恢复后再发现新会话。":
    "消息接收已暫停，可撤銷已有授權；恢復後再發現新會話。",
  "上次会话发现未完成，核对后可重新发现最近会话。":
    "上次會話發現未完成，核對後可重新發現最近會話。",
  "已有操作正在处理，请刷新状态，暂勿重复提交。":
    "已有操作正在處理，請刷新狀態，暫勿重復提交。",
  "操作仍在处理中，请刷新状态，暂勿重复提交。":
    "操作仍在處理中，請刷新狀態，暫勿重復提交。",
  "操作已取消，请刷新并核对后再决定下一步。":
    "操作已取消，請刷新並核對後再決定下一步。",
  "操作未完成，请检查接入服务并核对状态。":
    "操作未完成，請檢查接入服務並核對狀態。",
  "接入后端未配置，请先准备本地接入服务。":
    "接入後端未配置，請先準備本地接入服務。",
  "接入配置不匹配，请检查后端私有配置。":
    "接入配置不匹配，請檢查後端私有配置。",
  "扫码服务尚未配置，请联系维护者。": "掃碼服務未配置，請聯繫維護者。",
  "连接配置与账号不匹配，请联系接入负责人检查。":
    "連接配置與帳戶不匹配，請聯繫接入負責人檢查。",
  "WhatsApp 会话尚未创建，请先准备本机服务后刷新。":
    "WhatsApp 會話未創建，請先準備本機服務後刷新。",
  "WhatsApp 服务暂不可用，请检查服务后刷新。":
    "WhatsApp 服務暫不可用，請檢查服務後刷新。",
  "本机会话未启动或服务引擎信息不匹配，请联系接入负责人恢复服务后刷新。":
    "本機會話未啓動或服務引擎信息不匹配，請聯繫接入負責人恢復服務後刷新。",
  "二维码已失效或扫码完成，请刷新状态。":
    "QR code已失效或掃碼完成，請刷新狀態。",
  "WhatsApp 尚未连接，连接后才能发现新会话。":
    "WhatsApp 未連接，連接後才能發現新會話。",
  "授权已在其他窗口更新。请重新载入并核对，再保存。":
    "授權已在其他窗口更新。請重新載入並核對，再保存。",
  "会话选项已过期。请重新载入并核对，再保存。":
    "會話選項已過期。請重新載入並核對，再保存。",
  "登录已过期，请退出后重新登录。": "登入已過期，請退出後重新登入。",
  "无法读取本机扫码服务，请检查 Docker 和本地环境后刷新。":
    "無法讀取本機掃碼服務，請檢查 Docker 和本地環境後刷新。",
  "正在获取本机二维码，请稍后刷新。": "正在獲取本機QR code，請稍後刷新。",
  "当前连接与本机配置不匹配，请联系接入负责人检查。":
    "當前連接與本機配置不匹配，請聯繫接入負責人檢查。",
  "扫码服务尚未准备好，请联系维护者后刷新。":
    "掃碼服務未準備好，請聯繫維護者後刷新。",
  "连接授权已暂停，二维码已隐藏。": "連接授權已暫停，QR code已隱藏。",
  "未找到项目 Python 环境，请按本地启动指南准备 .venv。":
    "未找到項目 Python 環境，請按本地啓動指南準備 .venv。",
  "项目 Python 依赖缺失，请按本地启动指南安装锁定依赖。":
    "項目 Python 依賴缺失，請按本地啓動指南安裝鎖定依賴。",
  "本机操作验证失败，请退出后重新登录。":
    "本機操作驗證失敗，請退出後重新登入。",
  "重连结果尚不确定。请刷新状态核对，不要重复重连；仍无法确认时请联系接入负责人。":
    "重連結果尚不確定。請刷新狀態核對，不要重復重連；仍無法確認時請聯繫接入負責人。",
  "操作结果尚不确定，请刷新状态核对，暂勿重复操作。":
    "操作結果尚不確定，請刷新狀態核對，暫勿重復操作。",
  "会话状态已变化，无需重连。请刷新状态。":
    "會話狀態已變化，無需重連。請刷新狀態。",
  "刚刚已请求重连，请等待至少 30 秒并刷新状态。":
    "剛剛已請求重連，請等待至少 30 秒並刷新狀態。",
  "所选故障尚未恢复，不能清除。请刷新后检查。":
    "所選故障未恢復，不能清除。請刷新後檢查。",
  "请先核对故障时段，并确认无需导入历史消息。":
    "請先核對故障時段，並確認無需導入歷史消息。",
  "此故障已有其他核对结论，请刷新后检查，不能覆盖原结论。":
    "此故障已有其他核對結論，請刷新後檢查，不能覆蓋原結論。",
  监测中断时段: "監測中斷時段",
  "WhatsApp 服务不可用": "WhatsApp 服務不可用",
  接入服务不可用: "接入服務不可用",
  消息处理服务不可用: "消息處理服務不可用",
  连接: "連接",
  重连: "重連",
  状态核对: "狀態核對",
  会话发现: "會話發現",
  已排队: "已排隊",
  正在处理: "正在處理",
  正在核对: "正在核對",
  失败: "失敗",
  结果未知: "結果未確定",
  "无法连接后端，请检查本机服务后重试。":
    "無法連接後端，請檢查本機服務後重試。",
  "连接状态查询已恢复。": "連接狀態查詢已恢復。",
  "扫码状态已变化，已重新核对连接。": "掃碼狀態已變化，已重新核對連接。",
  "已请求重连。二维码准备好后会自动显示，请稍候。":
    "已請求重連。QR code準備好後會自動顯示，請稍候。",
  "已清除 {0} 项已恢复故障的待核对标记；历史记录保留，未恢复故障仍需处理。":
    "已清除 {0} 項已恢復故障的待核對標記；歷史記錄保留，未恢復故障仍需處理。",
  "已载入已保存的授权；取消勾选后保存即可撤销。":
    "已載入已保存的授權；取消勾選後保存即可撤銷。",
  "已发现最近会话，请勾选并保存处理授权。每批最多读取 100 个会话，可载入更多；列表可能不完整。新选项按服务端原到期时间失效。":
    "已發現最近會話，請勾選並保存處理授權。每批最多讀取 100 個會話，可載入更多；列表可能不完整。新選項按服務端原到期時間失效。",
  "已保存 {0} 个会话授权，自动回复未开启。":
    "已保存 {0} 個會話授權，自動回覆未開啓。",
  "已撤销全部会话授权，后端将拒绝这些会话的后续消息。":
    "已撤銷全部會話授權，後端將拒絕這些會話的後續消息。",
  "WhatsApp 连接与会话授权": "WhatsApp 連接與會話授權",
  "WhatsApp · 连接与授权": "WhatsApp · 連接與授權",
  "让工作消息，进入你的工作台。": "讓工作消息，進入你的工作台。",
  "先连接 WhatsApp，再选择允许处理的会话。选择权始终在你手里。":
    "先連接 WhatsApp，再選擇允許處理的會話。選擇權始終在你手裡。",
  "你的 WhatsApp 连接": "你的 WhatsApp 連接",
  "连接 WhatsApp": "連接 WhatsApp",
  选择工作会话: "選擇工作會話",
  保存处理授权: "保存處理授權",
  "连接后载入聊天并明确保存处理授权；自动回复不会开启。":
    "連接後載入對話並明確保存處理授權；自動回覆不會開啓。",
  "当前可查看连接状态；扫码和会话授权功能待接入。":
    "當前可查看連接狀態；掃碼和會話授權功能待接入。",
  选择连接: "選擇連接",
  连接状态读取失败: "連接狀態讀取失敗",
  正在读取连接状态: "正在讀取連接狀態",
  还没有本机连接: "還沒有本機連接",
  "当前账号暂无连接记录。接入负责人配置完成后，刷新即可查看状态。请联系接入负责人检查当前账号的配置。":
    "當前帳戶暫無連接記錄。接入負責人配置完成後，刷新即可查看狀態。請聯繫接入負責人檢查當前帳戶的配置。",
  "正在向本地服务查询。连接失败时可刷新重试。":
    "正在向本地服務查詢。連接失敗時可刷新重試。",
  刷新连接: "刷新連接",
  接收已暂停: "接收已暫停",
  状态待确认: "狀態待確認",
  "本机接入配置不可用，请联系接入负责人检查。仍可载入已有授权并撤销。":
    "本機接入配置不可用，請聯繫接入負責人檢查。仍可載入已有授權並撤銷。",
  最近: "最近",
  "操作：": "操作：",
  " · {0}": " · {0}",
  "错误编号：": "錯誤編號：",
  "上次请求响应丢失，暂不创建新的连接操作。使用原请求核对会保留原版本和请求键。":
    "上次請求響應丟失，暫不創建新的連接操作。使用原請求核對會保留原版本和請求鍵。",
  扫码登录待接入: "掃碼登入待接入",
  "可查看已有连接状态。启动连接及获取二维码暂不可用。":
    "可查看已有連接狀態。啓動連接及獲取QR code暫不可用。",
  "WhatsApp 已连接": "WhatsApp 已連接",
  "无需再次扫码，可选择工作会话。": "無需再次掃碼，可選擇工作會話。",
  "无需再次扫码，可载入并选择工作会话。":
    "無需再次掃碼，可載入並選擇工作會話。",
  "使用手机 WhatsApp 关联设备扫描此二维码":
    "使用手機 WhatsApp 關聯設備掃描此QR code",
  "二维码显示失败，请刷新重试。": "QR code顯示失敗，請刷新重試。",
  获取于: "獲取於",
  "秒前 · 自动更新中": "秒前 · 自動更新中",
  消息接收已暂停: "消息接收已暫停",
  请先确认连接状态: "請先確認連接狀態",
  "连接已断开，需要重新连接": "連接已斷開，需要重新連接",
  等待获取二维码: "等待獲取QR code",
  "恢复消息接收后再检查连接；暂停期间不显示二维码。":
    "恢復消息接收後再檢查連接；暫停期間不顯示QR code。",
  "刷新状态后再获取二维码，避免使用旧的扫码信息。":
    "刷新狀態後再獲取QR code，避免使用舊的掃碼信息。",
  "点击下方「重新连接并获取二维码」，无需运行命令。":
    "點擊下方「重新連接並獲取QR code」，無需運行命令。",
  "正在加载本机二维码，也可点击「获取二维码」重试":
    "正在加載本機QR code，也可點擊「獲取QR code」重試",
  "等待本机服务准备扫码，请刷新状态": "等待本機服務準備掃碼，請刷新狀態",
  "手机打开 WhatsApp → 关联设备": "手機打開 WhatsApp → 關聯設備",
  "选择「关联设备」，扫描这里的二维码": "選擇「關聯設備」，掃描這裡的QR code",
  开始连接: "開始連接",
  "核对未知操作（不重发）": "核對未知操作（不重發）",
  使用原请求核对: "使用原請求核對",
  暂停消息接收: "暫停消息接收",
  恢复消息接收: "恢復消息接收",
  "正在重连…": "重新連線緊…",
  重新连接并获取二维码: "重新連線並取得 QR code",
  刷新二维码: "刷新QR code",
  获取二维码: "取得 QR code",
  刷新状态: "更新狀態",
  "一键重连需要有效登录和已配置的接入后端。":
    "一鍵重連需要有效登入和已配置的接入後端。",
  连接与处理状态: "連接與處理狀態",
  "WhatsApp 会话": "WhatsApp 會話",
  未连接或待确认: "未連線或者未確認",
  处理链路: "處理鏈路",
  待重新确认: "待重新確認",
  采样就绪: "採樣就緒",
  尚未就绪: "未就緒",
  状态新鲜度: "狀態新鮮度",
  "刷新失败，显示上次采样": "刷新失敗，顯示上次採樣",
  "已过期，需重新检查": "已過期，需重新檢查",
  当前采样有效: "當前採樣有效",
  尚无采样: "尚無採樣",
  最近采样: "最近採樣",
  暂无: "暫時未有",
  接收授权: "接收授權",
  已启用: "已啓用",
  已暂停: "已暫停",
  故障核对: "故障核對",
  "查询失败，需刷新": "查詢失敗，需刷新",
  正在查询: "正在查詢",
  "{0} 项待核对": "{0} 項待核對",
  "已恢复，等待核对": "已恢復，等待核對",
  "尚未恢复，暂不能清除": "未恢復，暫不能清除",
  项: "項",
  "开始：": "開始：",
  "恢复：": "恢復：",
  "我已核对上述已恢复时段，确认无需导入历史消息。":
    "我已核對上述已恢復時段，確認無需導入歷史消息。",
  "清除已恢复故障（": "清除已恢復故障（",
  "仅清除已核对项的待处理标记，保留历史记录。未恢复故障不能清除；不会补拉或删除消息。":
    "僅清除已核對項的待處理標記，保留歷史記錄。未恢復故障不能清除；不會補拉或刪除消息。",
  "每次最多核对 100 项。": "每次最多核對 100 項。",
  "故障核对需要有效登录及明确确认。": "故障核對需要有效登入及明確確認。",
  "勾选后保存，才会授权后端处理消息。": "勾選後保存，才會授權後端處理消息。",
  "{0} 已勾选": "{0} 已勾選",
  授权待查询: "授權待查詢",
  放弃勾选并重新载入: "放棄勾選並重新載入",
  重新载入会话: "重新載入會話",
  载入会话与授权: "載入對話同授權",
  发现最近会话: "發現最近會話",
  授权版本: "授權版本",
  个已授权: "個已授權",
  "已有授权可在断线、暂停或接入配置不可用时读取及撤销。发现新会话需要有效连接，每批最多读取 100 个会话，可载入更多。下方分页用于浏览已载入会话。":
    "已有授權可在斷線、暫停或接入配置不可用時讀取及撤銷。發現新會話需要有效連接，每批最多讀取 100 個會話，可載入更多。下方分頁用於瀏覽已載入會話。",
  "授权版本已变化、读取失败或保存结果待确认。请重新载入并核对后再保存；不会自动重试。":
    "授權版本已變化、讀取失敗或保存結果待確認。請重新載入並核對後再保存；不會自動重試。",
  "勾选的新会话已过期。请放弃勾选并重新发现，再核对后保存。":
    "勾選的新會話已過期。請放棄勾選並重新發現，再核對後保存。",
  你的会话由你选择: "你的會話由你選擇",
  会话选择待接入: "會話選擇待接入",
  "先载入已有授权。连接后点击「发现最近会话」，勾选后明确保存。":
    "先載入已有授權。連接後點擊「發現最近會話」，勾選後明確保存。",
  "目前无法查询或更改会话授权。请重新登录并检查接入服务。":
    "目前無法查詢或更改會話授權。請重新登入並檢查接入服務。",
  保存会话授权: "儲存對話授權",
  撤销全部授权: "撤銷全部授權",
  暂无会话: "暫無會話",
  "可在手机创建测试聊天后重新发现最近会话。":
    "可在手機創建測試對話後重新發現最近會話。",
  "当前没有已授权会话。接入配置恢复后可发现新会话。":
    "當前沒有已授權會話。接入配置恢復後可發現新會話。",
  "尚未发现会话，请点击「发现最近会话」。":
    "未發現會話，請點擊「發現最近會話」。",
  "尚未连接；当前没有已授权会话。": "未連接；當前沒有已授權會話。",
  "载入更多会话（每批最多 100 个）": "載入更多會話（每批最多 100 個）",
  有尚未保存的更改: "有未保存的更改",
  授权已保存: "授權已保存",
  "授权仅用于读取和处理选中会话。不授权自动回复，不改变正式工单。":
    "授權僅用於讀取和處理選中會話。不授權自動回覆，不改變正式工作單。",
  "处理中…": "處理緊…",
  "已放弃未保存的更改。": "已放棄未保存的更改。",
  放弃更改: "放棄更改",
  开始使用: "開始使用",
  "每一步，都知道有没有完成。": "每一步，都知做完未。",
  "在 WhatsApp 连接页扫码，选择并授权需要处理的聊天。":
    "在 WhatsApp 連接頁掃碼，選擇並授權需要處理的對話。",
  "在业务页核对已有工单与原文；服务支持时可从客户原文新建工单。":
    "在業務頁核對已有工作單與原文；服務支持時可從客人原文新建工作單。",
  "核对顾客提议与顾客确认，明确同意后才更新正式安排。":
    "核對客人提議與客人確認，明確同意後才更新正式安排。",
  "在回复审批页核对完整草稿。批准只保存决定，尚未自动发送。":
    "在回覆審批頁核對完整草稿。批准只保存決定，未自動發送。",
  "手动发消息需进入 WhatsApp 消息页，单独授权并核对发送目标。":
    "手動發消息需進入 WhatsApp 消息頁，單獨授權並核對發送目標。",
  "在日历查看预约和待办，导出已确认预约到自己的日历。":
    "在日曆查看預約和待辦，導出已確認預約到自己的日曆。",
  "能力状态无法核对：": "能力狀態無法核對：",
  "。相关操作保持关闭，请检查后端版本。":
    "。相關操作保持關閉，請檢查後端版本。",
  当前版本可以使用: "當前版本可以使用",
  "登录、WhatsApp 连接与会话授权、已有工单与来源核对、具体时间变更确认、回复草稿批准／拒绝／取消、日历与待办查看。独立手动发送取决于连接状态和单独发送授权，提供方接受不等于对方收到。":
    "登入、WhatsApp 連接與會話授權、已有工作單與來源核對、具體時間變更確認、回覆草稿批准／拒絕／取消、日曆與待辦查看。獨立手動發送取決於連接狀態和單獨發送授權，提供方接受不等於對方收到。",
  仍在等待接通的功能: "仍在等待接通的功能",
  接口已提供: "接口已提供",
  暂不可用: "暫不可用",
  "可从对应页面使用，操作仍需核对归属、来源和当前版本。":
    "可從對應頁面使用，操作仍需核對歸屬、來源和當前版本。",
  查看团队进度: "查看團隊進度",
  遇到不确定结果: "遇到不確定結果",
  "先恢复网络并读取最新状态。审批和发送保留原请求编号；只有在重新核对后，才明确重试原操作。不要通过反复点按钮、重新建单或重新发消息来试探是否成功。":
    "先恢復網絡並讀取最新狀態。審批和發送保留原請求編號；只有在重新核對後，才明確重試原操作。不要通過反復點按鈕、重新建單或重新發消息來試探是否成功。",
  "登录、隐私和离线": "登入、隱私和離線",
  "使用维护者为你配置的 GigMate 账号。网页不提供公开测试密码，也不保存密码。离线时不能确认、批准或发送；本版不缓存聊天供离线使用。退出会清空当前页面，尚待核对的原请求会按账号保留。":
    "使用維護者為你配置的 GigMate 帳戶。網頁不提供公開測試密碼，也不保存密碼。離線時不能確認、批准或發送；本版不緩存對話供離線使用。退出會清空當前頁面，尚待核對的原請求會按帳戶保留。",
  安装与桌面版: "安裝與桌面版",
  "本版提供网页应用安装信息，支持的浏览器可“安装应用”或“添加到主屏幕”快捷打开，仍需联网。独立 exe／macOS 安装包、后台运行和离线业务尚未交付；添加快捷方式不会把后端或 WhatsApp 服务安装到手机。":
    "本版提供網頁應用安裝信息，支持的瀏覽器可“安裝應用”或“添加到主屏幕”快捷打開，仍需聯網。獨立 exe／macOS 安裝包、後台運行和離線業務未交付；添加快捷方式不會把後端或 WhatsApp 服務安裝到手機。",
  "也可以只读核对服务端的原操作保存记录。此检查不会执行、重发或撤销操作；未找到记录时仍需保留原编号。":
    "也可以只讀核對服務端的原操作保存記錄。此檢查不會執行、重發或撤銷操作；未找到記錄時仍需保留原編號。",
  只读核对已保存结果: "只讀核對已保存結果",
  "服务端已保存：「": "服務端已保存：「",
  "」 · 当时版本 v": "」 · 當時版本 v",
  "。结束后会刷新当前业务数据。": "。結束後會刷新當前業務數據。",
  "我已核对保存结果，结束这条原记录；这不会撤销或重新执行操作。":
    "我已核對保存結果，結束這條原記錄；這不會撤銷或重新執行操作。",
  结束已核对的原记录: "結束已核對的原記錄",
  操作复核: "操作復核",
  核对后保存: "核對清楚先儲存",
  "我已核对内容、来源及当前版本，确认本次操作。":
    "我對過內容、原文同目前版本，確認今次操作。",
  确认保存: "確認儲存",
  返回修改: "返去修改",
  原业务操作核对: "原業務操作核對",
  有一笔原操作等待核对: "有一筆原操作等待核對",
  原编号: "原編號",
  "先用页面刷新读取当前状态，再核对原内容。不会自动重发，也不会换编号提交新操作；排期设置仅查询保存结果。":
    "先用頁面刷新讀取當前狀態，再核對原內容。不會自動重發，也不會換編號提交新操作；排期設置僅查詢保存結果。",
  "我已读取当前状态并核对原操作，确认按原编号核查":
    "我已讀取當前狀態並核對原操作，確認按原編號核查",
  核对原业务操作: "核對原業務操作",
  "读取失败，请刷新。": "讀取失敗，請刷新。",
  "会话归属无法核对，不能建单。": "會話歸屬無法核對，不能建單。",
  "正在核对会话与来源。": "正在核對會話與來源。",
  "请选择可用的已授权会话。": "請選擇可用的已授權會話。",
  "请填写 1–120 字的业务摘要。": "請填寫 1–120 字的業務摘要。",
  "有时间时，必须选择客户说明时间的原文。":
    "填咗時間，就要揀返客人講時間嗰條原文。",
  "请选择日期。": "請選擇日期。",
  "请填写未来的开始时间和更晚的结束时间。":
    "請填寫未來的開始時間和更晚的結束時間。",
  "地址不能只有空格。": "地址不能只有空格。",
  "有地址时，必须选择客户说明地址的原文。":
    "填咗地址，就要揀返客人講地址嗰條原文。",
  "已有未结束工单；另开一单需要明确确认。":
    "已有未結束工作單；另開一單需要明確確認。",
  从会话新建工单: "從會話新建工作單",
  新客户到第一张工单: "由新客人到第一張工作單",
  "只引用客户原文；不知道的时间和地址保持未提供，不自动编造。":
    "只用客人原文；唔知嘅時間同地址就留空，唔會亂估。",
  刷新会话与原文: "刷新會話與原文",
  "当前连接的后端未开放建单功能。下面可以填写和核对，提交按钮保持关闭。":
    "當前連接的後端未開放建單功能。下面可以填寫和核對，提交按鈕保持關閉。",
  有尚待核对的原操作: "有尚待核對的原操作",
  "，不能另开新请求。请到业务工作台核对原操作。":
    "，不能另開新請求。請到業務工作台核對原操作。",
  "AI 新单建议": "AI 開單建議",
  "建议不会自动建单。选择后只预填摘要；时间、地址仍需逐项核对客户原文并明确填写。":
    "建議唔會自動開單。揀咗只會幫你填摘要；時間同地址仍要對返客人原文，再由你填寫。",
  "目前没有待核对的新单建议；你可以直接手动建单。":
    "暫時冇要核對嘅開單建議；你可以自己填資料開單。",
  核对这份新单建议: "核對呢份開單建議",
  已选择建议: "已選擇建議",
  "；提交时会重新核对来源与版本。": "；提交時會重新核對來源與版本。",
  已授权会话: "已授權會話",
  请选择会话: "揀一個已授權對話",
  "· 已关联": "· 已關聯",
  张工单: "張工作單",
  "暂无已授权会话，请先在 WhatsApp 连接页选择聊天。":
    "暫無已授權會話，請先在 WhatsApp 連接頁選擇對話。",
  "该会话已有未结束工单：": "該會話已有未結束工作單：",
  查看已有工单: "查看已有工作單",
  "这是另一项业务，我确认另开一张工单": "呢個係另一份工作，我確認要另外開單",
  业务摘要: "工作摘要",
  客户称呼和具体工作: "客人稱呼和具體工作",
  时间信息: "時間資料",
  尚未提供: "未提供",
  "只知道日期，时间待确认": "淨係知日期，時間要再確認",
  具体开始和结束时间: "確實開始同結束時間",
  日期: "日期",
  "开始（香港时间）": "開始（香港時間）",
  "结束（香港时间）": "結束（香港時間）",
  "客户提供的地址（可留空）": "客人提供的地址（可留空）",
  "仅日期仍属暂定。填了时间或地址，也必须核对客户在哪条消息中说明；商户自己的消息不能代替客户确认。":
    "僅日期仍屬暫定。填了時間或地址，也必須核對客人在哪條消息中說明；商戶自己的消息不能代替客人確認。",
  核对新工单: "核對新工作單",
  新工单复核: "核對新工作單",
  核对后再保存: "核對清楚先儲存",
  "时间：": "時間：",
  "地址：": "地址：",
  "未提供，等待客户说明": "未提供，等待客人說明",
  "来源会话 v": "來源會話 v",
  "· 时间原文": "· 時間原文",
  "条 · 地址原文": "條 · 地址原文",
  条: "條",
  "内容或来源已变化，请重新核对。": "內容或來源已變化，請重新核對。",
  "我已核对摘要、时间、地址和客户来源；缺项保持待确认":
    "我對過摘要、時間、地址同客人原文；未有資料嘅項目繼續等確認",
  保存新工单: "儲存新工作單",
  选择客户原文依据: "選擇客人原文依據",
  "只显示本会话最新、未撤回且有文字的客户消息。历史快照和商户回显不能当成客户确认。":
    "只顯示本會話最新、未撤回且有文字的客人消息。歷史快照和商戶回顯不能當成客人確認。",
  "正在读取…": "讀取緊…",
  "客户 · r": "客人 · r",
  作为时间依据: "作為時間依據",
  作为地址依据: "作為地址依據",
  "没有可用客户原文。可先留空时间／地址，等待客户补充；不能猜测确认。":
    "冇可用嘅客人原文。時間同地址可以先留空，等客人補充，唔可以估咗當確認。",
  工单进度操作: "工作單進度操作",
  工单进度: "工作進度",
  "此工单已结束，保留历史，不能再更改状态。":
    "此工作單已結束，保留歷史，不能再更改狀態。",
  "暂不可保存：等待 C 的工单状态接口（#27）完成修复并验收。可以先查看每个操作的影响。":
    "暫不可保存：等待 C 的工作單狀態接口（#27）完成修復並驗收。可以先查看每個操作的影響。",
  "结束后释放预约时段，收尾自动待办、未发送草稿和待核对提议；保留历史。已派发的 WhatsApp 请求不会因此撤回。":
    "結束後釋放預約時段，收尾自動待辦、未發送草稿和待核對提議；保留歷史。已派發的 WhatsApp 請求不會因此撤回。",
  "只更新业务进度，不发送消息，也不代表客户确认了新安排。":
    "只更新業務進度，不發送消息，也不代表客人確認了新安排。",
  "本次核对工单 v": "本次核對工作單 v",
  "；当前 v": "；當前 v",
  "工单已变化，请关闭并重新选择操作。": "工作單已變化，請關閉並重新選擇操作。",
  我已核对目标状态及影响: "我已核對目標狀態及影響",
  保存工单状态: "保存工作單狀態",
  关闭状态复核: "關閉狀態復核",
  快速问工作台: "快問工作台",
  "从当前账号的记录查询安排。只支持下方四类问题，不会修改工单或发送消息。":
    "從當前帳戶的記錄查詢安排。只支持下方四類問題，不會修改工作單或發送消息。",
  今天有什么安排: "今日有咩安排",
  明天有什么安排: "聽日有咩安排",
  哪些在等客户: "邊啲等緊客人",
  有什么待决定: "有咩要我決定",
  你的问题: "你嘅問題",
  查询记录: "搵記錄",
  "暂时只支持上面四类问题，请选择一个。不会猜测答案。":
    "暫時只支持上面四類問題，請選擇一個。不會猜測答案。",
  "· 查询完成；结果是业务记录，不代表 AI 已确认。":
    "· 查詢完成；結果是業務記錄，不代表 AI 已確認。",
  "这类记录暂时为空。": "呢類記錄暫時未有。",
  处理待办: "處理待辦",
  "完成待办只记录你的处理决定，不代表客户确认了时间或地址。关联需求条目会一起更新。":
    "完成待辦只係記低你處理咗，唔代表客人確認咗時間或者地址。相關需求會一齊更新。",
  工单范围: "工作單範圍",
  全部开放工单: "全部開放工作單",
  "来源：": "原文出處：",
  核对完成待办: "核對完成待辦",
  核对取消待办: "核對取消待辦",
  "工单“{0}” v{1}，待办“{2}”：{3}。请核对原文来源和依赖任务；不会确认客户的约定。":
    "工作單“{0}” v{1}，待辦“{2}”：{3}。請核對原文來源和依賴任務；不會確認客人的約定。",
  "当前没有待处理的待办。": "暫時冇待處理嘅事項。",
  真实消息理解尚未启用: "真實消息理解未啓用",
  "模型未能确定业务含义，需要人工核对": "模型未能確定業務含義，需要人工核對",
  无法确定属于哪张工单: "無法確定屬於哪張工作單",
  "处理失败，需要核对原文": "處理失敗，需要核對原文",
  "多次处理未完成，需要人工核对": "多次處理未完成，需要人工核對",
  复核数据暂不可用: "復核數據暫不可用",
  "来源会话无法核对。": "來源會話無法核對。",
  原文无法读取: "原文無法讀取",
  需要你判断: "要你判斷",
  "把没有理解、没有归单和来源失效的问题摆出来。不会自动接受、重发或改写工单。":
    "把沒有理解、沒有歸單和來源失效的問題擺出來。不會自動接受、重發或改寫工作單。",
  刷新复核事项: "刷新復核事項",
  "正在读取复核事项…": "正在讀取復核事項…",
  消息处理待核对: "消息處理待核對",
  "这是处理记录，可能包含旧轮次；查看最新原文后再判断，不能把旧诊断当成当前失败。":
    "這是處理記錄，可能包含舊輪次；查看最新原文後再判斷，不能把舊診斷當成當前失敗。",
  "处理暂未完成，系统正在自动重试": "處理暫未完成，系統正在自動重試",
  需要人工核对: "需要人工核對",
  "· 记录 v": "· 記錄 v",
  "/ 当前 v": "/ 當前 v",
  " · 历史轮次": " · 歷史輪次",
  查看这条会话原文: "查看這條會話原文",
  "目前没有记录到需复核的处理事项。这不表示 AI 已理解所有聊天。":
    "目前沒有記錄到需復核的處理事項。這不表示 AI 已理解所有對話。",
  来源会话: "來源會話",
  " · 触发消息": " · 觸發消息",
  "已撤回，不可用于确认": "已撤回，不可用於確認",
  "无可读取文字，请核对附件": "無可讀取文字，請核對附件",
  "尚无可读取原文。": "尚無可讀取原文。",
  该会话已有工单: "該會話已有工作單",
  工单缺项与含糊回复: "工作單缺項與含糊回覆",
  等待客户提供: "等客人提供",
  原文或含义需要复核: "原文或含義需要復核",
  等待客户核实和商户确认: "等客人核實，再由你確認",
  "客户回复含糊，不能默认同意": "客人覆得唔清楚，唔可以當同意",
  "客户已确认，等待商户核对": "客人確認咗，等你核對",
  客户尚未明确确认: "客人未明確確認",
  核对工单和来源: "核對工作單同原文",
  附件与部分结果: "附件與部分結果",
  "到 WhatsApp 消息页查看附件、部分文字、来源版本和人工确认。处理失败或结果未知不会自动重发；扫描 PDF 的文字识别和真实语音理解仍未交付。":
    "到 WhatsApp 消息頁查看附件、部分文字、來源版本和人工確認。處理失敗或結果未知不會自動重發；掃描 PDF 的文字識別和真實語音理解仍未交付。",
  前往消息与附件: "前往消息與附件",
  等待处理: "等待處理",
  处理中: "處理中",
  等待重试: "等待重試",
  本次任务完成: "本次任務完成",
  模型结果待核对: "模型結果待核對",
  附件下载: "附件下載",
  "B 提取与理解": "B 提取與理解",
  只读核对模型结果: "只讀核對模型結果",
  "后台服务暂不支持附件操作，请联系维护者更新。":
    "後台服務暫不支持附件操作，請聯繫維護者更新。",
  "附件存储尚未启用，请联系维护者。": "附件存儲未啓用，請聯繫維護者。",
  "B 的 OCR / 转写 / 解析 / GenAI 处理器尚未配置。原文件可先预览。":
    "B 的 OCR / 轉寫 / 解析 / GenAI 處理器未配置。原文件可先預覽。",
  "B 返回的结构或来源不符合协议，需要修正处理器。":
    "B 返回的結構或來源不符合協議，需要修正處理器。",
  "模型可能已处理，请核对原任务，不自动重复调用。":
    "模型可能已處理，請核對原任務，不自動重復調用。",
  "此附件已有任务，请先核对原任务。": "此附件已有任務，請先核對原任務。",
  "来源或上下文已变化，请重新载入核对。":
    "來源或上下文已變化，請重新載入核對。",
  "连接暂时失败，下面保留上次读取的内容，暂不提交新操作。":
    "連接暫時失敗，下面保留上次讀取的內容，暫不提交新操作。",
  连接暂时失败: "連接暫時失敗",
  "\n\n[预览仅展示前 100000 字符，请下载原文件核对全文。]":
    "\n\n[預覽僅展示前 100000 字符，請下載原文件核對全文。]",
  附件读取与核对: "附件讀取與核對",
  " · 收起": " · 收起",
  "只读取这条已授权附件，最大 20 MB。提取和模型建议不等于工单确认。":
    "只讀取這條已授權附件，最大 20 MB。提取和模型建議不等於工作單確認。",
  "本批不支持此文件类型。": "本批不支持此文件類型。",
  "本次解释日期的时区（可留空）": "本次解釋日期的時區（可留空）",
  "例如 Asia/Hong_Kong": "例如 Asia/Hong_Kong",
  "请填写适用的 IANA 时区，不会根据手机号或电脑猜测；缺少时间依据时应交由人工核对。":
    "請填寫適用的 IANA 時區，不會根據手機號或電腦猜測；缺少時間依據時應交由人工核對。",
  同意下载此附件到本机私有存储并预览: "同意下載此附件到本機私有存儲並預覽",
  "另行同意将此附件交给 B 配置的提取与 GenAI 服务":
    "另行同意將此附件交給 B 配置的提取與 GenAI 服務",
  读取附件: "讀取附件",
  "使用原请求核对（保留原下载和模型同意选项）":
    "使用原請求核對（保留原下載和模型同意選項）",
  取消此任务: "取消此任務",
  "只读核对模型结果（不重发）": "只讀核對模型結果（不重發）",
  "原消息时间：": "原消息時間：",
  "· 日期解释时区：": "· 日期解釋時區：",
  未指定: "未指定",
  "（商户本次选择）": "（商戶本次選擇）",
  "日期依据不完整：“明天”等相对日期需要人工确认，观察时间不能代替发送时间。":
    "日期依據不完整：“明天”等相對日期需要人工確認，觀察時間不能代替發送時間。",
  附件版本: "附件版本",
  "字节 · 来源指纹": "字節 · 來源指紋",
  预览原附件: "預覽原附件",
  下载原附件: "下載原附件",
  已授权附件预览: "已授權附件預覽",
  "已授权 PDF 预览": "已授權 PDF 預覽",
  提取文字与来源: "提取文字與來源",
  "结果任务：": "結果任務：",
  " · 显示上次已完成的结果，请核对最近任务状态":
    " · 顯示上次已完成的結果，請核對最近任務狀態",
  "提取范围：": "提取範圍：",
  来源片段: "來源片段",
  " · 第 {0} 页": " · 第 {0} 頁",
  "GenAI 建议，尚未确认": "GenAI 建議，未確認",
  "（片段": "（片段",
  片段: "片段",
  "待核对：": "待核對：",
  核对备注: "核對備注",
  "标记已核对来源（不确认工单）": "標記已核對來源（不確認工作單）",
  "来源已核对 ·": "來源已核對 ·",
  "查看业务交接资料（不写入工单）": "查看業務交接資料（不寫入工作單）",
  "来源已核对，业务仍需单独确认。C 使用这些来源标识前必须重新检查权限、版本和有效期。":
    "來源已核對，業務仍需單獨確認。C 使用這些來源標識前必須重新檢查權限、版本和有效期。",
  附件: "附件",
  "· 上下文": "· 上下文",
  "· 来源任务": "· 來源任務",
  "有效期：": "有效期：",
  已处理: "已處理",
  已发出: "已發出",
  已送达: "已送達",
  已读: "已讀",
  排队中: "排隊中",
  查询中: "查詢中",
  查询完成: "查詢完成",
  已读完本次可获取记录: "已讀完本次可獲取記錄",
  已达查询上限: "已達查詢上限",
  仍有未确认记录: "仍有未確認記錄",
  进行中: "做緊",
  待查询来源: "待查詢來源",
  "找到快照，修订仍待核对": "找到快照，修訂仍待核對",
  来源不可获取: "來源不可獲取",
  查询失败: "查詢失敗",
  "同步已排队。历史快照不会自动创建工单或发送消息。":
    "同步已排隊。歷史快照不會自動創建工作單或發送消息。",
  消息时间线与同步: "消息時間線與同步",
  "查看已授权聊天的消息，或明确导入近期可获取记录。附件可在单独授权后读取；真实文字理解、语音识别和图片识别尚未启用，部分结果需要人工核对。":
    "查看已授權對話的消息，或明確導入近期可獲取記錄。附件可在單獨授權後讀取；真實文字理解、語音識別和圖片識別未啓用，部分結果需要人工核對。",
  已授权聊天: "已授權對話",
  "群聊 · ": "群聊 · ",
  载入消息时间线: "載入消息時間線",
  刷新同步状态: "刷新同步狀態",
  历史快照: "歷史快照",
  实时接入: "實時接入",
  "修订 {0}": "修訂 {0}",
  非完整修订证据: "非完整修訂證據",
  收到: "收到",
  自己发送: "自己發送",
  此消息已撤回: "此消息已撤回",
  无文字内容: "無文字內容",
  类型待确认: "類型待確認",
  "· 原文件通过下方授权入口读取": "· 原文件通過下方授權入口讀取",
  "群成员标识：": "群成員標識：",
  "· 引用已接入消息": "· 引用已接入消息",
  "· 处理状态：": "· 處理狀態：",
  "· 送达状态：": "· 送達狀態：",
  加载更早消息: "加載更早消息",
  当前会话: "當前會話",
  近期历史导入: "近期歷史導入",
  时间范围: "時間範圍",
  近: "近",
  天: "天",
  查询记录上限: "查詢記錄上限",
  我同意查询所选聊天在该范围内的记录: "我同意查詢所選對話在該範圍內的記錄",
  重试原同步请求: "重試原同步請求",
  开始历史同步: "開始歷史同步",
  "接收已暂停，同步也已暂停；已有消息仍可查看。":
    "接收已暫停，同步也已暫停；已有消息仍可查看。",
  "只同步 WAHA 当前可提供的记录，不保证完整历史。已记录的暂停/撤权时段会跳过，失败和缺口不会自动清除。":
    "只同步 WAHA 當前可提供的記錄，不保證完整歷史。已記錄的暫停/撤權時段會跳過，失敗和缺口不會自動清除。",
  同步任务: "同步任務",
  暂无任务: "暫無任務",
  "· 写入": "· 寫入",
  "· 已有": "· 已有",
  "· 跳过": "· 跳過",
  读取此任务状态: "讀取此任務狀態",
  重试此范围: "重試此範圍",
  取消同步: "取消同步",
  缺口补查: "缺口補查",
  "补查仅增加可获取快照，结果仍需本人核对。":
    "補查僅增加可獲取快照，結果仍需本人核對。",
  补查: "補查",
  的故障时段: "的故障時段",
  缺失来源: "缺失來源",
  "查询来源快照，不重建修订": "查詢來源快照，不重建修訂",
  "文字 / 链接": "文字 / 鏈接",
  图片: "圖片",
  文件: "文件",
  普通音频附件: "普通音頻附件",
  "语音消息（Ogg/Opus）": "語音消息（Ogg/Opus）",
  "视频（MP4）": "視頻（MP4）",
  "贴纸（WebP）": "貼紙（WebP）",
  位置: "位置",
  联系人: "聯繫人",
  投票: "投票",
  表情回应: "表情回應",
  待核对草稿: "待核對草稿",
  "已批准，排队中": "已批准，排隊中",
  连接检查中: "連接檢查中",
  "提交中，不能取消": "提交中，不能取消",
  "WAHA 已接受": "WAHA 已接受",
  未提交成功: "未提交成功",
  "结果未知，禁止重发": "結果未確定，唔好重發",
  尚未提交: "未提交",
  已发送: "已發送",
  请先上传并核对附件: "請先上傳並核對附件",
  请填写坐标: "請填寫坐標",
  请先核对原请求: "請先核對原請求",
  "已核对原请求，没有重新提交。": "已核對原請求，沒有重新提交。",
  "本会话有待核对请求，请先核对原记录。":
    "本會話有待核對請求，請先核對原記錄。",
  "已按批准的固定内容政策排队。": "已按批准的固定內容政策排隊。",
  "草稿已保存，请核对下方最终内容再批准发送。":
    "草稿已保存，請核對下方最終內容再批准發送。",
  "WhatsApp 发送": "WhatsApp 發送",
  "向「": "向「",
  "」发送 WhatsApp 消息": "」發送 WhatsApp 消息",
  "读取聊天授权与发送授权分开。草稿、已批准、已接受和已送达是不同状态。":
    "讀取對話授權與發送授權分開。草稿、已批准、已接受和已送達是不同狀態。",
  "发送功能暂不可用，请联系接入负责人确认服务配置。":
    "發送功能暫不可用，請聯繫接入負責人確認服務配置。",
  刷新发送记录: "刷新發送記錄",
  "我允许本会话发送消息，授权有效期 24 小时":
    "我允許本會話發送消息，授權有效期 24 小時",
  保存发送授权: "儲存發送授權",
  撤销全部发送授权: "撤銷全部發送授權",
  "准备消息（尚未发送）": "準備消息（未發送）",
  内容来源: "內容來源",
  用户手动输入: "用戶手動輸入",
  "Agent 建议稿，人工核对": "Agent 建議稿，人工核對",
  "自动润色暂不可用。可粘贴建议稿，修改并核对后发送。":
    "自動潤色暫不可用。可粘貼建議稿，修改並核對後發送。",
  消息类型: "消息類型",
  文字: "文字",
  "文件类型（高级选项，可留空自动识别）":
    "文件類型（高級選項，可留空自動識別）",
  上传发送附件: "上傳發送附件",
  "附件最大 20 MiB": "附件最大 20 MiB",
  "字节 · SHA256": "字節 · SHA256",
  待发送图片: "待發送圖片",
  "查看 / 下载待发送文件": "查看 / 下載待發送文件",
  说明文字: "說明文字",
  纬度: "緯度",
  经度: "經度",
  地点名称: "地點名稱",
  联系人姓名: "聯繫人姓名",
  "电话号码（含 + 国家码）": "電話號碼（含 + 國家碼）",
  投票问题: "投票問題",
  "选项（每行一个，2–12 项）": "選項（每行一個，2–12 項）",
  允许多选: "允許多選",
  回应目标消息: "回應目標消息",
  "引用回复（可选，先载入时间线）": "引用回覆（可選，先載入時間線）",
  "表情（留空移除）": "表情（留空移除）",
  保存待审核草稿: "保存待審核草稿",
  "预先允许 Agent 在本会话使用下方相同内容，24 小时内最多 5 次；正文和附件不能改变":
    "預先允許 Agent 在本會話使用下方相同內容，24 小時內最多 5 次；正文和附件不能改變",
  "固定内容政策已保存，尚未发送消息。": "固定內容政策已保存，未發送消息。",
  批准固定内容自动政策: "批准固定內容自動政策",
  "草稿保存结果待确认。": "草稿保存結果待確認。",
  核对原草稿请求: "核對原草稿請求",
  "原任务已进入发送，无法取消；请核对下方记录，不要重发。":
    "原任務已進入發送，無法取消；請核對下方記錄，不要重發。",
  "原请求已取消；晚到的相同请求也不会创建发送任务。":
    "原請求已取消；晚到的相同請求也不會創建發送任務。",
  取消原请求并核对: "取消原請求並核對",
  "最终发送快照 ·": "最終發送快照 ·",
  "· 上下文版本": "· 上下文版本",
  "关联工单版本（不自动确认业务）：": "關聯工作單版本（不自動確認業務）：",
  " · 本条明确关联 {0}": " · 本條明確關聯 {0}",
  "附件：": "附件：",
  核对这条草稿绑定的附件: "核對這條草稿綁定的附件",
  截止: "截止",
  确认上述内容并发送: "確認以上內容並發送",
  只读核对发送结果: "只讀核對發送結果",
  人工核对说明: "人工核對說明",
  "我已核对手机，理解本条可能已发出；保留未知状态，不重发本条，只允许后续独立任务继续":
    "我已核對手機，理解本條可能已發出；保留未知狀態，不重發本條，只允許後續獨立任務繼續",
  记录核对并解除后续阻塞: "記錄核對並解除後續阻塞",
  "已记录当时未知状态的人工核对；当前状态以上方结果为准，本条不会重发。":
    "已記錄當時未知狀態的人工核對；當前狀態以上方結果為準，本條不會重發。",
  已批准的自动政策: "已批准的自動政策",
  "自动触发尚未接入。目前只能由你明确触发已批准的固定内容；这不是 AI 自由生成的自动回复。":
    "自動觸發未接入。目前只能由你明確觸發已批准的固定內容；這不是 AI 自由生成的自動回覆。",
  有效: "有效",
  已撤销: "已撤銷",
  "· 已预留": "· 已預留",
  "次 · 截止": "次 · 截止",
  按已授权政策提交: "按已授權政策提交",
  撤销此政策: "撤銷此政策",
  加载更多政策: "加載更多政策",
  发送记录: "發送記錄",
  加载更多发送记录: "加載更多發送記錄",
  "结果未知时不会自动重发，同一会话后续发送暂停。没有 WAHA 返回的消息 ID 时，无法自动证明某条相同文字就是本次发送；需人工核对。":
    "結果未知時不會自動重發，同一會話後續發送暫停。沒有 WAHA 返回的消息 ID 時，無法自動證明某條相同文字就是本次發送；需人工核對。",
  未提供原文依据: "未有原文出處",
  "{0}（该版本未载入，需复核）": "{0}（該版本未載入，需復核）",
  核对原操作: "核對原操作",
  有一项原操作尚待核对: "有一項原操作尚待核對",
  修改工单状态: "修改工作單狀態",
  "确认{0}": "確認{0}",
  "· 请求编号": "· 請求編號",
  "业务：": "業務：",
  未提供: "未有資料",
  "；时间原文": "；時間原文",
  "条；地址原文": "條；地址原文",
  "原工单版本 v": "原工作單版本 v",
  "原工单 v": "原工作單 v",
  "；原会话 v": "；原會話 v",
  原文编号: "原文編號",
  "读取、刷新和重新登录不会重发。只有明确核对后，才使用相同编号、原内容与原版本核对操作；服务端仍会拒绝旧来源或版本。":
    "讀取、刷新和重新登入不會重發。只有明確核對後，才使用相同編號、原內容與原版本核對操作；服務端仍會拒絕舊來源或版本。",
  "我已核对原内容和当前状态，继续核对原编号操作":
    "我已核對原內容和當前狀態，繼續核對原編號操作",
  核对失败: "核對失敗",
  核对原编号操作: "核對原編號操作",
  "顾客提议、顾客确认和商户确认分别显示。未知地址保持未提供。":
    "客人提議、客人確認和商戶確認分別顯示。未知地址保持未提供。",
  "下面是上次读取的数据，当前不能据此确认。":
    "下面是上次讀取的數據，當前不能據此確認。",
  "正在读取最新数据…": "正在讀取最新數據…",
  尚未读取数据: "未讀取數據",
  刷新业务数据: "更新工作資料",
  工单列表: "工作單一覽",
  搜索业务: "搵工作單",
  工单状态: "工作進度",
  全部状态: "全部進度",
  "筛选隐藏了当前工单；右侧仍显示「": "篩選隱藏了當前工作單；右側仍顯示「",
  版本: "版本",
  个关联会话: "個關聯會話",
  "没有匹配的工单，调整搜索或状态筛选。":
    "沒有匹配的工作單，調整搜索或狀態篩選。",
  "当前还没有工单。先在「WhatsApp 连接」中授权会话，再到「新建工单」引用客户原文建单；自动建单尚未开放。":
    "當前還沒有工作單。先在「WhatsApp 連接」中授權會話，再到「新建工作單」引用客人原文建單；自動建單未開放。",
  "正在读取工单…": "正在讀取工作單…",
  "读取失败，请检查服务后刷新。": "讀取失敗，請檢查服務後刷新。",
  工单详情: "工作單詳情",
  "有工单后，可在此查看详情与来源消息。":
    "有工作單後，可在此查看詳情與來源消息。",
  "正在核对选中工单，完成前不能确认。": "正在核對選中工作單，完成前不能確認。",
  "· 版本": "· 版本",
  "· 更新于": "· 更新於",
  "解释：": "解釋：",
  操作失败: "操作失敗",
  "{0}：{1}": "{0}：{1}",
  "当前已记录时间和地址的确认；请继续核对变更来源。":
    "當前已記錄時間和地址的確認；請繼續核對變更來源。",
  "当前后端未开放地址提议确认。": "當前後端未開放地址提議確認。",
  "需求、延期和交付检查请到业务管理。": "需求、延期和交付檢查請到業務管理。",
  "人工归单与延期保存仍未开放。": "人工歸單與延期保存仍未開放。",
  待核对变更: "待核對變更",
  项提议: "項提議",
  项待确认: "項等確認",
  "共 {0} 项": "共 {0} 項",
  开始处理: "開始做",
  标记等待客户: "標記等緊客人",
  完成工单: "完成張單",
  取消工单: "取消張單",
  "暂无需要核对的变更。新的变更会显示在这里。":
    "暫無需要核對的變更。新的變更會顯示在這裡。",
  变更: "變更",
  "原值：": "原值：",
  "提议值：": "提議值：",
  顾客提出: "客人提出",
  商户提出: "商戶提出",
  "· 工单基于 v": "· 工作單基於 v",
  "/ 会话 v": "/ 會話 v",
  "冲突安排：": "衝突安排：",
  "来源版本或归属无法完整核对，保持待复核。":
    "來源版本或歸屬無法完整核對，保持待復核。",
  "当前接口仅支持时间和地址确认，此字段保持待核对。":
    "當前接口僅支持時間和地址確認，此字段保持待核對。",
  核对并确认地址: "核對並確認地址",
  核对并确认安排: "核對並確認安排",
  确认安排复核: "確認安排復核",
  复核本次业务更新: "復核本次業務更新",
  "工单 v": "工作單 v",
  "· 来源会话 v": "· 來源會話 v",
  "提议、工单或来源已变化，本次复核失效。关闭后重新核对。":
    "提議、工作單或來源已變化，本次復核失效。關閉後重新核對。",
  "我已核对原文，接受本次提议。仍未获客户确认的信息保持待确认；日历与准备待办按确认状态处理。":
    "我已核對原文，接受本次提議。仍未獲客人確認的信息保持待確認；日曆與準備待辦按確認狀態處理。",
  确认并同步安排: "確認並同步安排",
  关闭复核: "關閉復核",
  关联会话与来源时间线: "關聯會話與來源時間線",
  显示会话: "顯示會話",
  "全部关联会话（": "全部關聯會話（",
  顾客: "客人",
  "· 会话": "· 會話",
  "消息已撤回，相关内容需复核": "消息已撤回，相關內容需復核",
  没有可读取文字: "沒有可讀取文字",
  "该范围暂无来源消息。": "該範圍暫無來源消息。",
  "来源链接可能指向隐藏会话；选择全部关联会话查看。":
    "來源鏈接可能指向隱藏會話；選擇全部關聯會話查看。",
  个人日历: "我嘅日曆",
  "账号全部安排；时刻按香港时区显示，全天日期保留原时区。":
    "帳戶全部安排；時刻按香港時區顯示，全天日期保留原時區。",
  查看日期: "揀日子",
  查看全部安排: "查看全部安排",
  其他工单: "其他工作單",
  未提供工单标题: "未提供工作單標題",
  "该范围暂无日历安排。": "該範圍暫無日曆安排。",
  当前工单待办: "當前工作單待辦",
  "全部（含历史）": "全部（含歷史）",
  "{0}（未载入）": "{0}（未載入）",
  "当前工单在该范围暂无待办。": "當前工作單在該範圍暫無待辦。",
  "新建工单请到“新建工单”；支持的状态操作在工单详情核对。回复草稿请到“回复审批”，":
    "新建工作單請到“新建工作單”；支持的狀態操作在工作單詳情核對。回覆草稿請到“回覆審批”，",
  "已批准草稿可在业务管理核对后提交发送。":
    "已批准草稿可在業務管理核對後提交發送。",
  "业务审批尚未接通 WhatsApp 发送。": "業務審批未接通 WhatsApp 發送。",
  草稿未提交: "草稿未提交",
  待核对批准: "等你核對批准",
  "已批准，尚未发送": "批准咗，未發送",
  正在执行: "正在執行",
  执行完成: "執行完成",
  执行失败: "執行失敗",
  执行结果待核对: "執行結果待核對",
  已关闭: "已關閉",
  已过期: "已過期",
  尚未提交发送: "未提交發送",
  发送服务已接收: "發送服務已接收",
  对方已读: "對方已讀",
  送达结果未知: "送達結果未知",
  "缺项已补齐，不再需要此问题": "缺項已補齊，不再需要此問題",
  工单已完成: "工作單已完成",
  工单已取消: "工作單已取消",
  新消息使旧草稿失效: "新消息使舊草稿失效",
  原文已编辑或撤回: "原文已編輯或撤回",
  "已有可用时间，不再需要此问题": "已有可用時間，不再需要此問題",
  超过有效期: "超過有效期",
  你拒绝了此草稿: "你拒絕了此草稿",
  你取消了此草稿: "你取消了此草稿",
  工单已变化: "工作單已變化",
  会话授权已撤回: "會話授權已撤回",
  "只有待核对的草稿可以批准。": "只有待核對的草稿可以批准。",
  "这份草稿已过期，请刷新查看。": "這份草稿已過期，請刷新查看。",
  "收件会话或原文依据无法核对，不能批准。":
    "收件會話或原文依據無法核對，不能批准。",
  "当前工单已结束，不能批准。": "當前工作單已結束，不能批准。",
  "工单或聊天已变化，请刷新后核对新草稿。":
    "工作單或對話已變化，請刷新後核對新草稿。",
  "当前草稿不允许重新提问。": "當前草稿不允許重新提問。",
  "当前来源、授权或工单状态不允许重新提问。":
    "當前來源、授權或工作單狀態不允許重新提問。",
  "这一轮聊天已经重新提问过。等待新消息后再核对，避免重复请求。":
    "這一輪對話已經重新提問過。等待新消息後再核對，避免重復請求。",
  客户提出的时间与已有安排冲突: "客人提出的時間與已有安排衝突",
  等待客户提供日期和时间: "等待客人提供日期和時間",
  等待客户核实日期和时间: "等待客人覈實日期和時間",
  "只有日期，等待客户说明几点": "只有日期，等待客人說明幾點",
  等待客户提供地址: "等待客人提供地址",
  等待客户核实地址: "等待客人覈實地址",
  "工单还有未确认的信息，请核对完整正文和来源":
    "工作單還有未確認的信息，請核對完整正文和來源",
  "需要人工核对业务含义；请对照完整正文和来源":
    "需要人工核對業務含義；請對照完整正文和來源",
  "审批数据不完整，请刷新；当前不能批准。":
    "審批數據不完整，請刷新；當前不能批准。",
  "浏览器不允许保存原请求记录；可以查看审批，但当前不能提交操作。请恢复存储后重新打开页面，不能推断旧请求未提交。":
    "瀏覽器不允許保存原請求記錄；可以查看審批，但當前不能提交操作。請恢復存儲後重新打開頁面，不能推斷舊請求未提交。",
  "旧入口还有待核对的审批操作；记录已保留，不能搬运到当前服务重试。请让维护者先核对旧请求。":
    "舊入口還有待核對的審批操作；記錄已保留，不能搬運到當前服務重試。請讓維護者先核對舊請求。",
  "原请求记录无法读取；可以查看审批，但当前不能提交操作。请恢复存储后重新核对旧请求。":
    "原請求記錄無法讀取；可以查看審批，但當前不能提交操作。請恢復存儲後重新核對舊請求。",
  "原请求记录无法读取，请联系维护者核对；为避免重复批准，当前不能提交新操作。":
    "原請求記錄無法讀取，請聯繫維護者核對；為避免重復批准，當前不能提交新操作。",
  "无法保存原请求记录；本次操作尚未提交，当前不能提交新操作。请恢复存储后重新打开审批页。":
    "無法保存原請求記錄；本次操作未提交，當前不能提交新操作。請恢復存儲後重新打開審批頁。",
  "原请求记录已被另一页面更新，本页不会删除它。操作响应已返回，请重新打开审批页核对。":
    "原請求記錄已被另一頁面更新，本頁不會刪除它。操作響應已返回，請重新打開審批頁核對。",
  "操作响应已返回，但原请求记录无法清理；记录仍保留，当前不能提交新操作。请恢复存储后重新打开审批页核对。":
    "操作響應已返回，但原請求記錄無法清理；記錄仍保留，當前不能提交新操作。請恢復存儲後重新打開審批頁核對。",
  "结果暂未确认。不要重新批准；刷新后核对，必要时使用原请求核对。":
    "結果暫未確認。不要重新批准；刷新後核對，必要時使用原請求核對。",
  "结果暂未确认，请保留原请求并核对，不能直接重发。":
    "結果暫未確認，請保留原請求並核對，不能直接重發。",
  "登录已过期，请重新登录；原记录仍按账号与环境保存。":
    "登入已過期，請重新登入；原記錄仍按帳戶與環境保存。",
  "后端拒绝了这次操作。请刷新后重新核对版本、来源、授权和当前状态。":
    "後端拒絕了這次操作。請刷新後重新核對版本、來源、授權和當前狀態。",
  "响应不完整，暂时不能确认操作结果，请核对原请求。":
    "響應不完整，暫時不能確認操作結果，請核對原請求。",
  "操作响应不匹配，保留原请求等待核对。":
    "操作響應不匹配，保留原請求等待核對。",
  "结果状态或快照不匹配，原请求仍待核对。":
    "結果狀態或快照不匹配，原請求仍待核對。",
  "原文当前不可读取。可以拒绝／取消草稿，但不能批准或重新提问。":
    "原文當前不可讀取。可以拒絕／取消草稿，但不能批准或重新提問。",
  "先核对原请求，再提交新操作。": "先核對原請求，再提交新操作。",
  "请填写 1 至 500 字的拒绝／取消原因。":
    "請填寫 1 至 500 字的拒絕／取消原因。",
  "另一个页面已记录原请求，请重新打开审批页核对。":
    "另一個頁面已記錄原請求，請重新打開審批頁核對。",
  "无法核对浏览器原请求记录；本次操作尚未提交，当前不能提交新操作。请恢复存储后重新打开页面。":
    "無法核對瀏覽器原請求記錄；本次操作未提交，當前不能提交新操作。請恢復存儲後重新打開頁面。",
  "没有可核对的原请求。": "沒有可核對的原請求。",
  "无法安全保存原操作，请恢复浏览器存储后再操作。":
    "無法安全保存原操作，請恢復瀏覽器存儲後再操作。",
  "后端尚未完成此功能的交付与安全验收。": "後端未完成此功能的交付與安全驗收。",
  "原记录已变化，请重新打开并核对。": "原記錄已變化，請重新打開並核對。",
  "无法读取原操作记录，本次未提交。": "無法讀取原操作記錄，本次未提交。",
  "工作时间保存结果仍无法核对；保留原记录，联系维护者核查，不自动重写。":
    "工作時間保存結果仍無法核對；保留原記錄，聯繫維護者核查，不自動重寫。",
  "操作尚未核对完成，原记录保留；请读取当前状态后明确核对原请求。":
    "操作未核對完成，原記錄保留；請讀取當前狀態後明確核對原請求。",
  "结果归属无法核对，原记录保留。": "結果歸屬無法核對，原記錄保留。",
  "响应与原操作的归属或版本不符，原记录保留。":
    "響應與原操作的歸屬或版本不符，原記錄保留。",
  "连接中断，原内容与编号已保留，没有自动重发。":
    "連接中斷，原內容與編號已保留，沒有自動重發。",
  "先核对已有原操作。": "先核對已有原操作。",
  "操作内容无效。": "操作內容無效。",
  "本次未提交，无法保存原操作。": "本次未提交，無法保存原操作。",
  "数据读取失败，请刷新重试。": "數據讀取失敗，請刷新重試。",
  "请先刷新并核对最新数据，再执行操作。":
    "請先刷新並核對最新數據，再執行操作。",
  "请重新核对当前提议。": "請重新核對當前提議。",
  "已保存本次提议；仍需客户核实的信息保持待确认，日历与待办按确认状态更新。":
    "已保存本次提議；仍需客人覈實的信息保持待確認，日曆與待辦按確認狀態更新。",
  "商户已接受此提议；日历与待办按工单的当前确认状态更新。":
    "商戶已接受此提議；日曆與待辦按工作單的當前確認狀態更新。",
  "商户已接受此值，仍等待客户核实；这不代表客户已经确认。":
    "商戶已接受此值，仍等待客人覈實；這不代表客人已經確認。",
  "已失效，需复核": "已失效，需復核",
  "业务或来源消息已经变化。这条历史提议不能再确认，请核对当前有效提议。":
    "業務或來源消息已經變化。這條歷史提議不能再確認，請核對當前有效提議。",
  时间冲突: "時間衝突",
  "该时段与另一项已确认预约重叠，不能确认。":
    "該時段與另一項已確認預約重疊，不能確認。",
  待商户确认: "待商戶確認",
  "商户接受后会保存此值；仍需客户核实的内容保持待确认，日历与准备待办按确认状态处理。":
    "商戶接受後會保存此值；仍需客人覈實的內容保持待確認，日曆與準備待辦按確認狀態處理。",
  "无法下载日历，请恢复连接后重试。": "無法下載日曆，請恢復連接後重試。",
  "预约的来源消息已变化、撤回或无法核对，暂不能导出；请先核对原文。原预约仍保留。":
    "預約的來源消息已變化、撤回或無法核對，暫不能導出；請先核對原文。原預約仍保留。",
  "预约已变化、未确认或不可导出，请刷新核对。":
    "預約已變化、未確認或不可導出，請刷新核對。",
  "服务没有返回日历文件，请联系维护者。":
    "服務沒有返回日曆文件，請聯繫維護者。",
  "日历文件无效，未进行下载。": "日曆文件無效，未進行下載。",
  "无法核对关联工单。": "無法核對關聯工作單。",
  "已结束工单仅保留历史，不能导出。": "已結束工作單僅保留歷史，不能導出。",
  "预约与工单版本不一致，请刷新核对。": "預約與工作單版本不一致，請刷新核對。",
  "暂定或未确认预约不能导出。": "暫定或未確認預約不能導出。",
  "已授权{0}": "已授權{0}",
  "未命名{0}": "未命名{0}",
  接收授权已暂停: "接收授權暫停咗",
  "点击「恢复消息接收」重新启用已选会话的接收授权。":
    "點擊「恢復消息接收」重新啓用已選會話的接收授權。",
  "⚠ 消息可能没有同步：暂时无法确认连接状态":
    "⚠ 消息可能沒有同步：暫時未能確認連接狀態",
  "上次状态已过期或查询失败。请先刷新状态，确认后再操作。":
    "上次狀態已過期或查詢失敗。請先刷新狀態，確認後再操作。",
  "✓ WhatsApp 已连接": "✓ WhatsApp 已連接",
  "无需再次扫码。消息处理是否就绪，请查看下方处理链路。":
    "無需再次掃碼。消息處理是否就緒，請查看下方處理鏈路。",
  "⚠ 消息暂时无法同步：WhatsApp 已断开": "⚠ 消息暫時未能同步：WhatsApp 已斷開",
  "重新连接本机 WhatsApp 会话，获取新二维码后用手机扫码。":
    "重新連接本機 WhatsApp 會話，獲取新QR code後用手機掃碼。",
  "扫描二维码，连接 WhatsApp": "掃描QR code，連接 WhatsApp",
  "请在手机 WhatsApp 的「关联设备」中扫码；二维码会自动更新。":
    "請在手機 WhatsApp 的「關聯設備」中掃碼；QR code會自動更新。",
  "正在确认 WhatsApp 连接": "正在確認 WhatsApp 連接",
  "服务正在准备连接。请刷新状态，暂时无需重复重连。":
    "服務正在準備連接。請刷新狀態，暫時無需重復重連。",
  业务扩展与安全验收: "業務擴展與安全驗收",
  "本版已接通归单、延期、需求、工作时间、摘要、交付检查和归档。":
    "本版已接通歸單、延期、需求、工作時間、摘要、交付檢查和歸檔。",
  导出手机日历: "導出手機日曆",
  "需要本版后端提供只读日历下载接口。": "需要本版後端提供只讀日曆下載接口。",
  "本版支持从已授权会话建单；需要引用客户原文并明确确认。":
    "本版支持從已授權會話建單；需要引用客人原文並明確確認。",
  "开始、等待客户、完成和取消工单": "開始、等待客人、完成和取消工作單",
  "本版支持状态操作；完成或取消会处理自动待办与未发送草稿。":
    "本版支持狀態操作；完成或取消會處理自動待辦與未發送草稿。",
  确认地址和补齐缺项: "確認地址和補齊缺項",
  "本版支持确认时间和地址提议；仍未获客户确认的值会保持待确认。":
    "本版支持確認時間和地址提議；仍未獲客人確認的值會保持待確認。",
  人工归单与延期跟进: "人工歸單與延期跟進",
  "已接通当前消息归单、忽略及延期跟进；更改会重新核对来源和版本。":
    "已接通當前消息歸單、忽略及延期跟進；更改會重新核對來源和版本。",
  业务审批后发送及关联回执: "業務審批後發送及關聯回執",
  "已接通准确的审批与发送记录；需单独授权对应聊天，未知结果先核查，不自动重发。":
    "已接通準確的審批與發送記錄；需單獨授權對應對話，未知結果先核查，不自動重發。",
  "AI 文字理解": "AI 文字理解",
  "文字模型须由维护者在服务端配置、授权并核对费用。模型只提建议；媒体识别与独立现场验收另列，不代表自动建单。":
    "文字模型須由維護者在服務端配置、授權並核對費用。模型只提建議；媒體識別與獨立現場驗收另列，不代表自動建單。",
  "浏览器无法保存或读取原操作。可以查看数据，暂不能提交；恢复存储后重新打开并核对。":
    "瀏覽器無法保存或讀取原操作。可以查看數據，暫不能提交；恢復存儲後重新打開並核對。",
  "原操作记录不可用或已被另一页面改变，请恢复后重新打开核对。":
    "原操作記錄不可用或已被另一頁面改變，請恢復後重新打開核對。",
  "操作响应已核对，但原记录清理失败。禁止新提交，请恢复存储后核对原编号。":
    "操作響應已核對，但原記錄清理失敗。禁止新提交，請恢復存儲後核對原編號。",
  "该会话已有未结束工单，请刷新查看；另开一单需要再次明确确认。":
    "該會話已有未結束工作單，請刷新查看；另開一單需要再次明確確認。",
  "时间与已有预约冲突，请核对日历后修改。":
    "時間與已有預約衝突，請核對日曆後修改。",
  "登录已过期；原操作记录保留，请重新登录核对。":
    "登入已過期；原操作記錄保留，請重新登入核對。",
  "操作未确认完成，请刷新；若保留了原编号，只能明确核对该原操作。":
    "操作未確認完成，請刷新；若保留了原編號，只能明確核對該原操作。",
  "响应无法完整核对，原请求保留；请勿重复创建或确认。":
    "響應無法完整核對，原請求保留；請勿重復創建或確認。",
  "连接中断，无法确定是否已保存。原请求已保留，请恢复服务后核对，勿重复提交。":
    "連接中斷，無法確定是否已保存。原請求已保留，請恢復服務後核對，勿重復提交。",
  "先核对已有原操作，不能提交新操作。": "先核對已有原操作，不能提交新操作。",
  "操作内容无效，请重新核对。": "操作內容無效，請重新核對。",
  "原操作无法安全保存，本次未提交。": "原操作無法安全保存，本次未提交。",
  "没有可核对的原操作。": "沒有可核對的原操作。",
  "尚未核对到原操作的已保存结果；记录保留。这不代表未执行，不能另开重复请求。":
    "未核對到原操作的已保存結果；記錄保留。這不代表未執行，不能另開重復請求。",
  "保存结果的归属或版本无法核对，原记录保留。":
    "保存結果的歸屬或版本無法核對，原記錄保留。",
  "暂时无法只读核对原操作；记录保留，没有重发。":
    "暫時未能只讀核對原操作；記錄保留，沒有重發。",
  "先只读核对到原操作的已保存结果，再结束记录。":
    "先只讀核對到原操作的已保存結果，再結束記錄。",
  "暂时无法读取，请刷新。": "暫時未能讀取，請刷新。",
  "请求结果待确认，请刷新状态；不要另建请求重试。":
    "請求結果待確認，請刷新狀態；不要另建請求重試。",
  请求失败: "請求失敗",
  "响应未能完整读取，请重新核对状态；不要另建请求重试。":
    "響應未能完整讀取，請重新核對狀態；不要另建請求重試。",
  "操作尚未完成，请刷新状态或明确核对；不要重复提交。":
    "操作未完成，請刷新狀態或明確核對；不要重復提交。",
  "上次请求结果待确认，请使用原请求核对。":
    "上次請求結果待確認，請使用原請求核對。",
  "未能读取操作编号，请使用原请求核对。":
    "未能讀取操作編號，請使用原請求核對。",
  "列表数据无效，请刷新后重试。": "列表數據無效，請刷新後重試。",
  "列表分页异常，请刷新后重试。": "列表分頁異常，請刷新後重試。",
  "没有待核对的原请求。": "沒有待核對的原請求。",
  "没有待核对操作。": "沒有待核對操作。",
  "二维码图片无效。": "QR code圖片無效。",
  "请求未能确认，请刷新核对；不要另建模型请求。 ":
    "請求未能確認，請刷新核對；不要另建模型請求。 ",
  "附件暂不可用，请核对授权、来源和处理状态。":
    "附件暫不可用，請核對授權、來源和處理狀態。",
  "响应未能完整读取，请核对已有任务。": "響應未能完整讀取，請核對已有任務。",
  "请保留原读取范围与同意选项核对原请求。":
    "請保留原讀取範圍與同意選項核對原請求。",
  "任务响应无效，请保留原请求核对。": "任務響應無效，請保留原請求核對。",
  "请先核对当前结果来源。": "請先核對當前結果來源。",
  "请求结果待核对，请刷新已有记录，不要另建发送任务。":
    "請求結果待核對，請刷新已有記錄，不要另建發送任務。",
  "发送操作未完成，请核对权限和已有记录。":
    "發送操作未完成，請核對權限和已有記錄。",
  "响应不完整，请核对已有记录。": "響應不完整，請核對已有記錄。",
  "发送响应无法核对，请读取原请求记录。":
    "發送響應無法核對，請讀取原請求記錄。",
  "查询失败，请刷新；同步请求重试须保留原请求。":
    "查詢失敗，請刷新；同步請求重試須保留原請求。",
  "同步接口尚不可用，请先完成本批次后端迁移并重建服务。":
    "同步接口尚不可用，請先完成本批次後端遷移並重建服務。",
  "原同步请求尚待核对，请保留原参数后重试。":
    "原同步請求尚待核對，請保留原參數後重試。",
  待归类: "未歸類",
  待确认: "等確認",
  等待顾客: "等緊客人",
  待复核: "等核對",
  尚未询问: "未詢問",
  等待顾客确认: "等緊客人確認",
  顾客已确认: "客人已確認",
  "回复含糊，待核对": "覆得唔清楚，要核對",
  待处理: "未處理",
  受阻: "有阻滯",
  时间安排: "時間安排",
  数量: "數量",
  规格: "規格",
  截止时间: "截止時間",
  "{0} 全天（{1}）": "{0} 全天（{1}）",
  "{0}（香港时间）": "{0}（香港時間）",
  "{0} → {1}（香港时间；原时区 {2}）": "{0} → {1}（香港時間；原時區 {2}）",
  "未提供标题（日历 {0}）": "未提供標題（日曆 {0}）",
  "暂时无法连接本地服务，请检查服务后刷新。":
    "暫時未能連接本地服務，請檢查服務後刷新。",
  "暂时无法确认操作结果。请恢复服务并刷新核对，避免反复提交。":
    "暫時未能確認操作結果。請恢復服務並刷新核對，避免反復提交。",
  "账号或密码不正确，请重新输入。": "帳戶或密碼不正確，請重新輸入。",
  "业务或消息已更新，请刷新并重新核对当前提议。":
    "業務或消息已更新，請刷新並重新核對當前提議。",
  "来源消息已变化，请刷新并重新核对。": "來源消息已變化，請刷新並重新核對。",
  "该时段与其他预约冲突，不能确认，请刷新查看。":
    "該時段與其他預約衝突，不能確認，請刷新查看。",
  "当前处理授权已暂停，请联系接入负责人核对。":
    "當前處理授權已暫停，請聯繫接入負責人核對。",
  "当前环境尚未允许此网页地址登录，请联系负责配置的队友确认。":
    "當前環境未允許此網頁地址登入，請聯繫負責配置的隊友確認。",
  "登录验证已变化，请退出后重新登录。": "登入驗證已變化，請退出後重新登入。",
  "当前工单或会话不可用，请刷新并检查当前账号和会话授权。":
    "當前工作單或會話不可用，請刷新並檢查當前帳戶和會話授權。",
  "暂时无法读取数据，请检查本地服务后刷新。":
    "暫時未能讀取數據，請檢查本地服務後刷新。",
  "操作未能完成或结果暂无法确认，请刷新核对后再操作。":
    "操作未能完成或結果暫無法確認，請刷新核對後再操作。",
  "服务响应无效，请刷新核对当前状态。": "服務響應無效，請刷新核對當前狀態。",
  "列表数据无效，请刷新重试。": "列表數據無效，請刷新重試。",
  "分页数据未能完整读取，请刷新重试。": "分頁數據未能完整讀取，請刷新重試。",
  "当前工单没有可核对的对话，请联系后端负责人。":
    "當前工作單沒有可核對的對話，請聯繫後端負責人。",
  "工单没有可核对的对话。": "工作單沒有可核對的對話。",
  "对话范围或版本无效，请刷新核对。": "對話範圍或版本無效，請刷新核對。",
  "业务已切换，请刷新并重新核对。": "業務已切換，請刷新並重新核對。",
  "当前只能确认时间或地址提议。": "當前只能確認時間或地址提議。",
  "来源对话或消息版本无法核对，请刷新并重新审核。":
    "來源對話或消息版本無法核對，請刷新並重新審核。",
  "手动与业务审批发送均需单独授权。AI 润色和自由生成自动回复尚未接通。":
    "手動與業務審批發送均需單獨授權。AI 潤色和自由生成自動回覆未接通。",
  "这里保存你的批准决定；到业务管理另行核对并提交发送。批准不等于已发送。":
    "這裡保存你的批准決定；到業務管理另行核對並提交發送。批准不等於已發送。",
  "这是当前工单关联的会话；业务管理提交时由服务端核对准确的 WhatsApp 聊天。":
    "這是當前工作單關聯的會話；業務管理提交時由服務端核對準確的 WhatsApp 對話。",
  "待办随已确认安排更新。可到业务管理完成或取消待办；客户确认仍需单独核对。":
    "待辦隨已確認安排更新。可到業務管理完成或取消待辦；客人確認仍需單獨核對。",
  "当前服务未开放此状态操作。可先查看操作影响，联系维护者确认版本。":
    "當前服務未開放此狀態操作。可先查看操作影響，聯繫維護者確認版本。",
  "其他字段请到业务管理核对；此处确认时间和地址。":
    "其他字段請到業務管理核對；此處確認時間和地址。",
  "在回复审批页核对完整草稿并批准，再到业务管理核对后提交发送。":
    "在回覆審批頁核對完整草稿並批准，再到業務管理核對後提交發送。",
  "查看已授权聊天，或明确导入近期记录。文字模型需服务端单独配置；语音与图片识别尚未启用，附件可单独授权预览。":
    "查看已授權對話，或明確導入近期記錄。文字模型需服務端單獨配置；語音與圖片識別未啓用，附件可單獨授權預覽。",
  界面语言: "介面語言",
  尚未交付的扩展: "未交付的擴展",
  "真实语音与图片识别、媒体结果转工单、自由 Agent 自动回复、外部日历持续同步和独立桌面安装包尚未交付。当前文字业务可手动处理；真实服务配置与手机验收仍须由团队完成。":
    "真實語音與圖片識別、媒體結果轉工作單、自由 Agent 自動回覆、外部日曆持續同步和獨立桌面安裝包未交付。當前文字業務可手動處理；真實服務配置與手機驗收仍須由團隊完成。",
  "模型调用结果未知。保留原编号供维护者核查，不重新归单调用；可核对原文后手动处理或标记忽略。":
    "模型結果未確定。留低原編號俾維護者核查，唔好重新歸單再叫模型；可以對返原文後人手處理或者忽略。",
  "模型调用结果未知，保留原编号，不能自动重试":
    "模型結果未確定，留低原編號，唔可以自動再試",
  完成: "完成",
  取消: "取消",
  按默认日期: "按預設日期",
  "全部事项已核对。": "全部事項核對咗。",
  "我已知悉尚未完成的事项，仍明确结束本工单。":
    "我清楚有事項未做完，仍然確認結束呢張工作單。",
  使用后端默认日期: "用伺服器預設日期",
  未定: "未定",
  "检查项已齐全。": "檢查項目齊晒。",
  "仍未完成：": "仲未完成：",
  "。确认仍要结束。": "。確認仍然要結束。",
  "请核对服务后刷新。": "對清楚服務再更新。",
  来源或含义需复核: "原文或者意思要再核對",
  等待客户核实与商户确认: "等客人核實，再由你確認",
  "仍有未完成检查项。请先处理，或明确核对后确认仍要结束工单。":
    "仲有檢查項目未完成。請先處理，或者核對後明確確認仍然要結束。",
  "前置待办尚未完成，请先处理依赖事项。": "前置待辦未做完，請先處理依賴事項。",
  "后端已明确拒绝本次操作，没有保存。请刷新并核对条件后重新操作。":
    "伺服器明確拒絕咗今次操作，冇儲存。更新並核對條件後先再操作。",
  "选一张工单，按「下一步」处理就好。": "揀一張工單，跟住「下一步」做就得。",
  商户选择不发送这条回复: "商戶揀咗唔發呢個回覆",
  "已批准。下一步：回到工单点「发送给客人」。":
    "批准咗。下一步：返去工單撳「發俾客人」。",
  "所有等你批准的回复都在这里。批准后再点「发送」才会发给客人。":
    "所有等你批准嘅回覆都喺度。批准之後再撳「發送」先會發俾客人。",
  刷新: "更新",
  "网络不稳，下面是上次读到的内容，暂时不能操作。":
    "網絡唔穩定，以下係上次讀到嘅內容，暫時唔可以操作。",
  为什么要回复: "點解要回覆",
  发给: "發俾",
  "「{0}」的客人 · WhatsApp": "「{0}」嘅客人 · WhatsApp",
  回复内容: "回覆內容",
  有效到: "有效到",
  "这条回复已关闭。": "呢個回覆已經關閉。",
  客人原话: "客人原話",
  客人: "客人",
  "这条消息暂时读不到。": "暫時讀唔到呢條訊息。",
  重试上次操作: "重試上次操作",
  批准这条回复: "批准呢個回覆",
  不发这条: "唔發呢個",
  回到工单去发送: "返去工單發送",
  重新生成回复: "重新生成回覆",
  技术信息: "技術資料",
  聊天编号: "對話編號",
  发送已批准的回复: "發送已批准嘅回覆",
  "选择要用的 WhatsApp": "揀要用嘅 WhatsApp",
  发送给客人: "發俾客人",
  确认发送: "確認發送",
  "这个时间你已有安排，建议先问客人换个时间：":
    "呢個時間你已經有安排，建議先問客人改第二個時間：",
  "还有信息没齐，建议这样问客人：": "仲有資料未齊，建議咁問客人：",
  "建议这样回复客人：": "建議咁回覆客人：",
  "暂时读不到回复草稿，稍后会自动重试。":
    "暫時讀唔到回覆草稿，稍後會自動重試。",
  "已批准。下一步：发送给客人。": "批准咗。下一步：發俾客人。",
  "这条回复不会发出。": "呢個回覆唔會發出。",
  "操作没有完成，请稍后再试。": "操作未完成，請稍後再試。",
  回复客人: "回覆客人",
  "发给：「{0}」的客人 · WhatsApp": "發俾：「{0}」嘅客人 · WhatsApp",
  发送进度: "發送進度",
  你批准: "你批准",
  发送: "發送",
  客人收到: "客人收到",
  "上一次操作还没确认结果，请到「回复审批」处理。":
    "上次操作未確認結果，請去「回覆審批」處理。",
  去处理: "去處理",
  "正在保存…": "儲存緊…",
  "批准后再点「发送」才会发给客人；想改字可到「回复审批」。":
    "批准之後再撳「發送」先會發俾客人；想改字可以去「回覆審批」。",
  "还没连接 WhatsApp，连上后才能真正发出。":
    "未連接 WhatsApp，連接咗先可以真正發出。",
  "去连接 WhatsApp": "去連接 WhatsApp",
  正在确认发送结果: "確認緊發送結果",
  "（没有文字）": "（冇文字）",
  "依据：": "根據：",
  已撤回的消息: "已收回嘅訊息",
  "客人说「{0}」": "客人話「{0}」",
  "网络不稳，下面是上次读到的内容，暂时不能确认。":
    "網絡唔穩定，以下係上次讀到嘅內容，暫時唔可以確認。",
  我的工单: "我嘅工單",
  搜索: "搜尋",
  客人或工作: "客人或者工作",
  状态: "狀態",
  时间未定: "時間未定",
  "没有符合条件的工单。": "冇符合條件嘅工單。",
  "还没有工单。先到「WhatsApp 连接」选好要处理的聊天，再点「新建工单」。":
    "未有工單。先去「WhatsApp 連接」揀好要處理嘅對話，再撳「新增工單」。",
  "暂时读不到工单，请稍后刷新。": "暫時讀唔到工單，請稍後再更新。",
  "在左边选一张工单。": "喺左邊揀一張工單。",
  "正在打开工单…": "打開緊工單…",
  下一步: "下一步",
  "这张工单已经结束。": "呢張工單已經完結。",
  "还缺：{0}": "仲欠：{0}",
  "都安排好了，没有要你处理的事。": "全部安排好，冇嘢要你處理。",
  "客人想改时间，但和「{0}」撞了": "客人想改時間，但同「{0}」撞咗",
  "客人提了新的{0}": "客人提出新嘅{0}",
  确认新地址: "確認新地址",
  确认新时间: "確認新時間",
  "聊天里有新消息，这条提议已过时。": "對話有新訊息，呢個提議已經過時。",
  "工单已结束，不能再改。": "工單已經完結，唔可以再改。",
  "地址确认功能还没开放。": "地址確認功能未開放。",
  "请稍等，正在同步最新内容。": "請等等，同步緊最新內容。",
  "这类内容请到「业务管理」的需求与交付里确认。":
    "呢類內容請去「業務管理」嘅需求同交付度確認。",
  "确认后，「{0}」改为 {1}。日历和准备待办会一起更新。":
    "確認之後，「{0}」改為 {1}。日曆同準備待辦會一齊更新。",
  "客人还没明确答应，会先记成「暂定」，等客人确认后再变正式。":
    "客人未明確答應，會先記做「暫定」，等客人確認先變正式。",
  "内容刚更新了，请重新看一眼再确认。": "內容啱啱更新咗，請再睇一次先確認。",
  确认: "確認",
  先不: "住先",
  安排: "安排",
  等客人确认: "等客人確認",
  需要你看一下: "要你睇一睇",
  还没有: "仲未有",
  "改动记录（{0}）": "改動記錄（{0}）",
  已过时: "已過時",
  聊天记录: "對話記錄",
  显示聊天: "顯示對話",
  "聊天 {0}": "對話 {0}",
  我: "我",
  "（这条消息已撤回）": "（呢條訊息已收回）",
  "还没有聊天记录。": "未有對話記錄。",
  "更多操作（开始、完成、取消工单）": "更多操作（開始、完成、取消工單）",
  我的日程: "我嘅日程",
  未命名工单: "未命名工單",
  "还没有安排。": "未有安排。",
  这张工单要做的事: "呢張工單要做嘅嘢",
  "截止 {0}": "限期 {0}",
  要等前一件事做完: "要等上一樣嘢做完",
  "暂时没有要做的事。": "暫時冇嘢要做。",
  "（按 {0} 时间）": "（按 {0} 時間）",
  "{0}全天": "{0}全日",
  "依据的消息暂时读不到，先别确认。": "暫時讀唔到根據嘅訊息，住先唔好確認。",
  "客人说了时间，但还不完整": "客人講咗時間，但未齊",
  "客人提到的{0}需要你看一下": "客人提到嘅{0}要你睇一睇",
  "还不知道几点结束（或要多久），先问客人，问清楚后才能放进日历。":
    "仲未知幾點完（或者要幾耐），先問客人，問清楚先可以入日曆。",
  "意思不够明确，先和客人确认一下。": "意思唔夠清楚，先同客人確認一下。",
  "{0} 开始": "{0} 開始",
};
