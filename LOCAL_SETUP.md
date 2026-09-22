# 本机安装说明

来源：https://github.com/atang-sp/agy-switch

源码位于 `/home/atang/agy-switch`，依赖安装在 `.venv`。
`~/.local/bin/agy-switch` 和 `gemini-switch` 通过 `agy_switch_local.py` 启动上游程序。

## WSL 兼容配置

本机没有 Secret Service，现有 agy 使用
`~/.gemini/antigravity-cli/antigravity-oauth-token`。
本地适配器让新版账号管理器读写这一文件，确保切换对现有 agy 生效。
`agy_switch.py` 已增加逐账号实时额度查询。

账号档案存在 `~/.gemini/agy-switch/credentials/`，元数据存在
`~/.gemini/accounts_meta.json`。凭据文件权限为 600，档案目录权限为 700。
此配置使用本地明文文件，并非 README 所述的加密系统密钥环。

已迁移旧账号 2025、2027，并用当前凭据更新对应档案；安装期间当前登录文件保持原样。

## 命令

```sh
agy-switch list
agy-switch current
agy-switch list --no-quota
agy-switch switch 2025
agy-switch switch 2027
agy-switch save 别名
agy-switch alias [旧别名或邮箱] 新别名
agy-switch add 别名
```

`add` 需要在终端交互登录。切换或添加前必须先退出所有正在运行的 agy；
旧进程会缓存启动账号，并在每小时刷新 token 时把全局凭据覆盖回旧账号。
工具现在会检测这种情况并拒绝不安全的切换。切换成功后再重新启动 agy。
本地适配范围是这台 WSL 的 agy CLI，不代表 Windows IDE 同步切换。

默认列表会分别显示 Gemini 和 Claude/GPT-OSS 共享池的 5 小时、每周剩余额度（同时显示已用比例），
以及各自的本地重置时间和倒计时。`current` 同样显示当前账号额度。
查询时会临时刷新过期凭证，但不会改写登录文件或档案。
`--no-quota` 可跳过联网查询。
额度查询只使用 `daily-cloudcode-pa.googleapis.com`；该接口失败时直接报错，
不会回退到可能返回全 100% 的 `cloudcode-pa.googleapis.com`。

## 备份与回退

旧脚本及原始凭据：
`~/.local/state/agy-switch/backups/20260920-000515/`

仅恢复旧命令（保留当前登录状态）：

```sh
install -m 755 ~/.local/state/agy-switch/backups/20260920-000515/agy-switch ~/.local/bin/agy-switch
```

旧脚本的账号目录 `~/.gemini/antigravity-cli/tokens/` 仍保留。

## 验证

已用隔离临时 HOME 验证保存、列表、当前账号、按别名及邮箱切换、删除和文件权限；
已验证真实账号迁移后的凭据一致性，以及安装前后当前登录文件未变化。
未发起新的 Google 登录或模型请求。
