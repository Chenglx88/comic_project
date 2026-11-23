# KNOWN_ISSUES

已知问题事实源。现象、影响、触发条件、临时规避、状态、登记日期缺一不可。TODO 只在决定修复时登记指针，不重述现象。

| 编号 | 现象 | 影响 | 触发条件 | 临时规避 | 状态 | 登记日期 |
|:--|:--|:--|:--|:--|:--|:--|
| P-01 | 方案 §6 命名示例与 §4 的 `<major_en>` 写法不完全一致 | 产物文件名可能各写各的 | 人工按方案示例创建产物 | 以 `00_schema/storyboard_headers.json` 与 `guard_paths.py` 正则为准 | 开放 | 2026-11-21 |
| P-02 | 方案 §4.6 写 `character_sheet.md`，实际落地为 `character_lock.json` | 按旧文档找不到锁文件 | 阅读方案后直接找 `character_sheet.md` | 以 `04_prompts/_shared/character_lock.json` 为唯一事实源 | 已规避 | 2026-11-21 |
| P-03 | 仓库 `git init` 后曾无任何提交 | 无历史可回滚，误删无法恢复 | 执行破坏性操作前 | 已创建首个 commit 并推送 `origin/main`（021acd7）；后续按闸门提交 | 已解决 | 2026-11-21 |
| P-04 | PostToolUse 在文件落盘后才执行，无法撤销坏写入 | 校验失败的文件已存在 | 写入不合规产物 | hook 回灌前 3 条错误；随后人工或代理修正并重跑 `validate.py` | 开放（平台限制） | 2026-11-21 |
| P-05 | 方案附录 A 的模型名、上下文窗口、价格为 2026 公开信息 | 按旧信息选型会产出漂移或超预算 | 直接照抄方案模型 ID | 运行时查厂商最新模型卡并 pin 明确 ID | 开放 | 2026-11-21 |
| P-06 | `07_pipeline/` 无代码 | L1-L6 只能手工执行，无法批量与复现 | 需要跑产品流水线 | 先用代理按层手工生产 EP01 | 开放 | 2026-11-21 |
| P-07 | 主角未定选，`protagonist.json` 为 `undecided` | 角色锁前缀与 seed 校验处于弱模式 | 生成提示词 | 提示词保持 `undecided`+`sha256:pending`；定选后重跑 | 开放 | 2026-11-21 |
| P-08 | Edit 的 `old_string` 不在磁盘内容中时，hook 无法重建前瞻内容 | 该次 Edit 的角色锁校验被跳过 | 并发修改或 `old_string` 写错 | 写入后跑 `validate.py prompts` 兜底；hook 记 allow 日志 | 开放（fail-open） | 2026-11-21 |
| P-09 | `pytest` / `ruff` / `mypy` 未安装 | 代码质量门禁无法执行 | 运行对应命令 | 日一用 `compileall` + `validate.py` + selftest；安装后再启用 | 开放 | 2026-11-21 |
| P-10 | `.state/` 被 `.gitignore` 忽略 | 进度与恢复点不进入版本历史 | 换机器或清工作区 | 需要迁移时手动打包 `.state/` | 已接受 | 2026-11-21 |
| P-11 | 方案 §5 写关键帧用 NovelAI/ComfyUI；本期改用即梦/Seedream（火山方舟） | 按方案找不到 NovelAI 配置 | 按方案执行图像层 | 以 `07_pipeline/config/env.example` 的 `SEEDREAM_*` 与 `ARK_*` 为准 | 已接受（用户决定） | 2026-11-22 |
| P-12 | 可灵新版用单 `KLING_API_KEY`；火山 TTS 新版用 `VOLC_TTS_API_KEY` + `VOLC_TTS_CLUSTER`，无 APPID/旧 TOKEN | 按旧双凭据配置会认证失败 | 按旧文档配置媒体层 | 以 `07_pipeline/config/env.example` 为准 | 已接受（用户确认） | 2026-11-22 |
| P-13 | 腾讯混元旧 CAM 接口模型已下线；`hy4-flash` 等旧模型不可用 | 旧 `TENCENTCLOUD_SECRET_ID/SECRET_KEY` 方案无法完成 L1 | 按旧方案配置 L1 | 迁移 TokenHub：`TOKENHUB_API_KEY` + `hy4` + `web_search_options` | 部分解决：API 可用，联网搜索未开通（见 P-18） | 2026-11-22 |
| P-14 | DashScope 模型 ID 区分大小写；`Qwen3.6-Plus` 返回 404 | L2 无法启动 | 按展示名填写模型 ID | 使用 `qwen3.6-plus-2026-04-02` 或 `qwen3.6-plus` | 已解决（2026-11-22 实测 200） | 2026-11-22 |
| P-15 | Seedream 5.5 直连模型 ID 返回 403 AccessDenied；旧 endpoint 不是图像模型 | L5 关键帧无法生成 | 用未开通的模型或错误 endpoint 调图像接口 | 新建 Seedream 图像接入点后可生成；实测 1248x832 JPEG | 已解决（2026-11-22） | 2026-11-22 |
| P-16 | 火山 TTS 用 `/api/v3/tts/unidirectional/sse` 返回 code=45000030「[resource_id=volc.seedtts.default] requested resource not granted」；同一 Key 改走不带 `/sse` 的标准路径成功 | 易误判为资源未授权，阻塞 L5 配音 | 用 SSE 路径调 TTS | 使用 `https://openspeech.bytedance.com/api/v3/tts/unidirectional`（无 `/sse`）+ `X-Api-Resource-Id: seed-tts-2.0`；实测 3.456s / 24kHz 单声道 MP3 | 已解决（2026-11-22 实测） | 2026-11-22 |
| P-17 | TokenHub `hy4`、Qwen3.6、GLM-5.3 均为 reasoning 模型 | max_tokens 过小会只返回推理、content 为空 | 按普通模型给 max_tokens | 实测短答：L1 completion 1963（reasoning 1922）、L2 198（192）、L4 164（161）；L1 建议 ≥4096，结构化输出 ≥8192 | 开放（设计约束） | 2026-11-22 |
| P-18 | TokenHub 联网搜索未生效：`hy4` 与 `deepseek-v4.1-flash-1017` 用 `web_search_options`（含 `forced_search`）和 `/v1/responses` + `tools:[web_search]` 均返回 200，但 `search_results` 为空、无 `usage.tool_usage.web_search_call`，模型自称无法联网 | L1 只能返回训练数据或 BLOCKED，无法产出带可核验 `source_url/year` 的专业数据，端到端阻塞 | 账号未领取「联网搜索免费资源包」或未开通后付费；或当前模型不支持联网 | 在 TokenHub 控制台「平台配置 > 工具管理」或「启用管理 > 应用工具」领取资源包/开通后付费；确认 `hy4` 在该能力支持列表，不支持则经用户批准改用支持的模型 | 已解决（2026-11-22 用户开通；hy4 另有兼容问题见 P-19） | 2026-11-22 |
| P-19 | `hy4` 在 TokenHub 联网搜索下把搜索注入的引用规则当成任务本身，`content` 输出「Need list with bullet points?」等内部草稿；加系统约束仍复现。`hy3` 与 `deepseek-v4.1-flash-1017` 正常返回最终答案与 `[n]` 引用 | L1 无法用 `hy4` 产出干净的结构化数据 | `model=hy4` + `web_search_options` 且发生 `web_search_call` | L1 在 `routing.json` pin `deepseek-v4.1-flash-1017`；不依赖 `.env` 的 `HUNYUAN_MODEL_ID` | 已规避（2026-11-22） | 2026-11-22 |
| P-20 | `validate.py all` 扫描结果为 0 artifacts，未覆盖 `01_data` | L1 数据只能靠 `l1.validate_l1`，总门禁会误报通过 | 运行 `validate.py all` | 以 `cli.py l1 --resume` 的 `l1.validate_l1` 作为 L1 门禁；后续补 validator | 开放 | 2026-11-22 |
