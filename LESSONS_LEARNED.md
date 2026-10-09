# agy-switch 故障分析与经验教训总结

## 1. 故障背景

在 Linux 环境下执行 `agy-switch add` 试图添加新的 Google 账号时，出现以下异常链路：
1. 未能拉起浏览器新账号登录页面，直接复用了旧账号（`hust.111qqz@gmail.com`）进入对话会话。
2. 退出会话后，终端提示：`未检测到新登录凭证`。
3. 随后运行 `agy-switch` 查询状态时，提示：`当前未检测到任何已登录的 Antigravity / Gemini 账号`。

---

## 2. 根因深度剖析

### 2.1 存储介质脱节：D-Bus SecretService vs 本地文件
* **宿主行为**：官方 `agy` 为 Go 编译的二进制，内置 `zalando/go-keyring`。在具备 D-Bus 会话的原生 Linux（或启用 systemd 的现代 WSL2）中，它将 OAuth 凭据保存在 **系统的 SecretService（GNOME Keyring / KWallet 等）** 中（`service="gemini", username="antigravity"`）。
* **工具盲区**：`agy-switch` 早期针对未配置 D-Bus 的 WSL 环境编写，本地启动器强制将活跃凭据定向到了磁盘文件 `~/.gemini/antigravity-cli/antigravity-oauth-token`。
* **连锁故障**：
  * `add` 命令调用清空逻辑时，仅删除了并不存在的本地文件，**系统 SecretService 中的真实凭据未受任何影响**。
  * 启动 `agy` 时，`agy` 直接读到了系统密钥环里的有效登录态，自然跳过了 OAuth 网页授权阶段。
  * `agy` 退出后，`agy-switch` 仅检查本地文件，因文件不存在而报错“未检测到新登录凭证”。

### 2.2 数据结构变更：缺失 `id_token` 导致邮箱解析失效
* `agy 1.1.27` 存入密钥环的数据结构去除了包含用户 Claims 的 JWT `id_token`，只保留了 `token`（含 `access_token`、`refresh_token`）和 `auth_method`。
* 旧版代码仅依赖 `parse_id_token` 获取邮箱，缺失 `id_token` 时直接退化为 `"未知邮箱"`。
* 导致后续的账号别名匹配、档案检索与切换校验全部因邮箱不匹配而中断。

---

## 3. 架构重构与解决方案

### 3.1 统一自适应密钥环架构（AdaptiveKeyring）
* 将本地临时适配器与主程序彻底合并，统一收敛至 `agy_switch.py` 内部。
* **自动环境感知**：实现 `detect_environment()`，在启动时动态探测 D-Bus 会话与 SecretService 连通性。
* **优雅降级（Graceful Degradation）**：
  * **标准环境（Linux / 现代 WSL2）**：优先读写系统 SecretService，并实时镜像一份至本地受保护文件。删除时双向彻底清理。
  * **无头环境（无 D-Bus 的传统 WSL / Docker / SSH）**：自动无缝降级为本地受保护文件模式（权限限制 `0600`）。
* **档案安全持久化**：账号档案（`gemini-accounts`）统一存放在私有档案库 `~/.gemini/agy-switch/credentials/`，解除对系统密钥环容量与桌面依赖。

### 3.2 多级邮箱解析保底机制（resolve_token_email）
构建多层解析管道，彻底解决凭证结构变动问题：
1. 内存/档案缓存中已有的 `email`。
2. JWT `id_token` claims（若存在）。
3. 携带 `access_token` 向 Google OAuth `tokeninfo` 端点请求解析真实的邮箱并写回缓存。
4. 若 `access_token` 已过期，调用内置的 OAuth 客户端自动刷新后再行解析。

### 3.3 环境诊断子命令（`agy-switch doctor`）
新增自检命令，一键输出当前运行环境、D-Bus 连通性、密钥环后端、活跃账号状态与后台运行进程。

---

## 4. 核心经验教训与最佳实践

### 4.1 能力探测（Capability Probing）优于环境猜测（Environment Guessing）
* **教训**：之前按“系统标签（WSL vs Linux）”硬编码存储模式。但实际上现代 WSL2 完全可以拥有完整的 D-Bus 和 systemd 支持，而原生 Linux 服务器也可能处于纯 SSH 无头模式。
* **准则**：不要猜测用户的环境类型，而应直接探测具体能力的可用性（如 D-Bus 连接是否通畅）。能用系统密钥环则用，不能用则平滑降级到文件。

### 4.2 外部受管工具（Upstream CLI）的端到端凭证一致性
* **教训**：外围管理工具必须与核心工具读写**同源、同物理存储介质**的凭证。
* **准则**：在涉及注入、清理第三方工具凭据时，必须严格比对第三方二进制所调用的底层系统调用（如 keyring 还是文件），不可单方面建立“平行副本”。

### 4.3 面向未来的防御式数据解析
* **教训**：第三方数据结构（如 token 字典）在版本迭代中可能会精简字段（例如移除 `id_token`）。
* **准则**：对于关键业务属性（如账号识别主键 `email`），必须有备用推导策略（如 API 反查或显式归档记录），避免因单一字段缺席引发雪崩。

### 4.4 可观测性与自愈诊断是运维工具的生命线
* 增加 `doctor` 诊断命令后，无论是用户自行排查还是开发维护，都可以秒级获取当前宿主状态，极大降低排障沟通成本。
