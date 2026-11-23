---
name: acceptance-readonly-boundaries
description: 验收 Phase-1 管线时不要运行 l1/l2/l3 生成子命令，密钥扫描只报 path:line+keyword
type: trap
trigger: 验收 07_pipeline 或任何带生成子命令的 CLI 时
scope: [acceptance, secret-scan, readonly]
severity: high
symptom: 运行 cli.py l2/l3 被权限分类器拒绝；打印 grep 命中行被拒
root_cause: 生成子命令会写/覆盖定稿产物，超出“只读验收”边界；密钥扫描打印原文可能泄露
avoidance: 只跑 preflight/compileall/unittest/validate；失败路径用单测覆盖；密钥扫描仅输出 path:line 与 keyword，绝不打印行内容或值
evidence: 2026-11-22 EP01-PIPE-PHASE1-TEST 两次 denials
verified: 2026-11-22
---

# 验收只读边界

- 生成子命令（`l1/l2/l3`）会落盘并可能覆盖定稿，验收默认不跑；改用离线单测覆盖校验/失败分支。
- `grep ... api_key|secret|token` 只报 `path:line` + 命中 keyword；不输出行文本。
- `preflight --json` 可安全重复执行（已验证两次输出一致，rc=0）。
