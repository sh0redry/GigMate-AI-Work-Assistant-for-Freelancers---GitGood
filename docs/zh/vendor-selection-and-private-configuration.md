# 供应商选择与私密凭据配置（ADR 0008 中文版）

- **状态**：已接受（2026-10-17）
- **决定**：接缝对接哪家供应商／模型，以及凭据如何私密配置
- **关联**：issue #29（B 第 2、4 项）、ADR 0002（契约权威）、ADR 0003（审批与执行）

## 决定

1. **文字与视觉供应商：DeepSeek `deepseek-chat`。** 运营方持有该 key，接口能满足提取契约形态，且实测该端点对本账号处理图像输入（纯绿／纯红 64×64 PNG 分别回答 “Green” / “Red”，各 202 prompt tokens）。但视觉仍由 `GIGMATE_MEDIA_VISION_VENDORS=deepseek` 把关：这是账号路由层面的观察，不是供应商能力承诺。
2. **语音没有供应商。** ASR 需要自己的 OpenAI 兼容 `/v1/audio/transcriptions` 端点；DeepSeek 用于音频时被明确拒绝，因为把对话密钥发到默认 ASR 端点属于静默的凭据误用。在选定音频供应商之前，`asr` 以 `MEDIA_AUDIO_VENDOR_REQUIRED` 拒绝。
3. **凭据以文件配置，而非值。** `GIGMATE_LLM_API_KEY_FILE` / `GIGMATE_MEDIA_API_KEY_FILE`（或等价的 secret 挂载）优先于值变量；文件被指定但不可读时是硬失败 `SecretUnreadable`，不会退化成"未配置"。本地开发仍可用值。
4. **启用是清单，不是单一开关。** live 开关、预算、价格、token 上限、时间依据、媒体接缝、模态、视觉供应商、ASR 供应商彼此独立；`scripts/check_model_config.py` 只报存在性，不打印值。

## 理由

issue #29 把供应商选择与私密配置交给维护者，而代码不能替他悄悄决定。凭据放在文件里，就不会出现在 `docker inspect`、进程列表、shell 历史或镜像层中；音频宁可拒绝也不复用对话密钥，避免"有一个 key"变成"什么都用这个 key"。未选定音频供应商作为未决事项记录，而不是用默认值掩盖。

## 后果

- 只有所有闸门都配置好，部署才是 live；否则接缝保持关闭，不完整的配置既不会意外调用也不会花钱。
- 真实价格、预算与 token 上限必须由维护者填写，并在供应商调价后复查 —— 配置本身不替代这项复核，`check_model_config.py` 也明确写出这一点。
- **仍未解决**：没有采购音频供应商，生产凭据也未部署。两者都是运营动作而非代码变更，因此 issue #29 第 2、4 项在完成前保持未勾选。

## 启用清单

1. `umask 077 && printf '%s' "$KEY" > /run/secrets/deepseek`
2. `GIGMATE_LLM_API_KEY_FILE=/run/secrets/deepseek`
3. `GIGMATE_EXTRACTION_PROVIDER=reviewed_llm`、`GIGMATE_LLM_PROVIDER=deepseek`、`GIGMATE_LLM_MODEL=deepseek-chat`
4. 按供应商公布价格填 `GIGMATE_LLM_COST_INPUT_USD_PER_1K` / `GIGMATE_LLM_COST_OUTPUT_USD_PER_1K`（记录核对日期）
5. `GIGMATE_LLM_COST_BUDGET_USD`、`GIGMATE_LLM_MAX_INPUT_TOKENS`、`GIGMATE_LLM_MAX_OUTPUT_TOKENS`（单次调用的限制；本批没有实现模型每日调用／token 配额或模型账号白名单）
6. `GIGMATE_WORKSPACE_TIMEZONE`（相对日期按它解析）
7. `GIGMATE_LLM_LIVE=1` 与 `GIGMATE_LLM_ALLOW_LIVE_ORIGIN=1`
8. 需要媒体时：`GIGMATE_MEDIA_ENABLED=1`、`GIGMATE_MEDIA_MODALITIES=ocr,pdf,text`、`GIGMATE_MEDIA_VISION_VENDORS=deepseek`
9. `python scripts/check_model_config.py` —— 检查所选 reviewed 入口、开关、人工核对的价格、凭据存在性和时区，不调用供应商，不打印密钥。退出码 0 表示文字模型配置完整；历史 `llm`、固定规则／禁用入口或配置缺失均退出 1。媒体配置单独展示，不会因这项检查通过而获准调用。这只是配置核对，不是供应商实测验收。
