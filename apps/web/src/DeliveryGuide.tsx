import {
  featureDescriptions,
  featureLink,
  loopReady,
  type Features,
} from "./features";
export function DeliveryGuide({
  features,
  error,
}: {
  features: Features;
  error: string;
}) {
  return (
    <section className="panel" aria-label="功能与使用说明">
      <p className="eyebrow">开始使用</p>
      <h1>每一步，都知道有没有完成。</h1>
      <ol className="getting-started">
        <li>在 WhatsApp 连接页扫码，选择并授权需要处理的聊天。</li>
        <li>在业务页核对已有工单与原文；服务支持时可从客户原文新建工单。</li>
        <li>核对顾客提议与顾客确认，明确同意后才更新正式安排。</li>
        <li>在回复审批页核对完整草稿。批准只保存决定，尚未自动发送。</li>
        <li>手动发消息需进入 WhatsApp 消息页，单独授权并核对发送目标。</li>
        <li>在日历查看预约和待办，导出已确认预约到自己的日历。</li>
      </ol>
      {error && (
        <p role="alert" className="notice stale">
          能力状态无法核对：{error}。相关操作保持关闭，请检查后端版本。
        </p>
      )}
      <h2>当前版本可以使用</h2>
      <p>
        登录、WhatsApp
        连接与会话授权、已有工单与来源核对、具体时间变更确认、回复草稿批准／拒绝／取消、日历与待办查看。独立手动发送取决于连接状态和单独发送授权，提供方接受不等于对方收到。
      </p>
      <h2>仍在等待接通的功能</h2>
      <div className="feature-list">
        {Object.entries(featureDescriptions).map(([key, item]) => {
          const enabled =
            features[key as keyof Features] &&
            (!["manual_assignment", "business_sending"].includes(key) ||
              loopReady(features));
          return (
            <article key={key}>
              <span className={`tag ${enabled ? "" : "warning"}`}>
                {enabled ? "接口已提供" : "暂不可用"}
              </span>
              <h3>{item.title}</h3>
              <p>
                {enabled
                  ? "可从对应页面使用，操作仍需核对归属、来源和当前版本。"
                  : item.reason}
              </p>
              <a
                href={featureLink(key as keyof Features)}
                target="_blank"
                rel="noreferrer"
              >
                查看团队进度
              </a>
            </article>
          );
        })}
      </div>
      <h2>遇到不确定结果</h2>
      <p>
        先恢复网络并读取最新状态。审批和发送保留原请求编号；只有在重新核对后，才明确重试原操作。不要通过反复点按钮、重新建单或重新发消息来试探是否成功。
      </p>
      <h2>登录、隐私和离线</h2>
      <p>
        使用维护者为你配置的 GigMate
        账号。网页不提供公开测试密码，也不保存密码。离线时不能确认、批准或发送；本版不缓存聊天供离线使用。退出会清空当前页面，尚待核对的原请求会按账号保留。
      </p>
      <h2>安装与桌面版</h2>
      <p>
        本版提供网页应用安装信息，支持的浏览器可“安装应用”或“添加到主屏幕”快捷打开，仍需联网。独立
        exe／macOS 安装包、后台运行和离线业务尚未交付；添加快捷方式不会把后端或
        WhatsApp 服务安装到手机。
      </p>
    </section>
  );
}
