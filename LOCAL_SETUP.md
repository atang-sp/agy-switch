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
agy-switch switch --default
agy-switch switch --global 2027
```

`add` 需要在终端交互登录。切换全局账号或添加账号前必须先退出所有正在运行的 agy；
旧进程会缓存启动账号，并在每小时刷新 token 时把全局凭据覆盖回旧账号。
工具现在会检测这种情况并拒绝不安全的切换。切换成功后再重新启动 agy。
本地适配范围是这台 WSL 的 agy CLI，不代表 Windows IDE 同步切换。

## 按项目使用不同账号

在各项目目录分别运行 `agy-switch switch <别名>`，随后直接运行 `agy`。
Git 仓库内的子目录共用一个绑定；非 Git 目录按当前目录绑定。
`agy-switch current` 显示本目录的账号；`agy-switch switch --default`
取消项目绑定，恢复使用全局账号。`agy-switch switch --global <别名>`
仅在需要修改全局默认账号时使用。
`agy-switch list --no-quota` 会在每个账号下显示绑定的项目，以及对应项目中
正在运行的 `agy` 数量；“本目录”表示从当前目录新启动时会选中的账号。
项目绑定保存在 `~/.gemini/agy-switch/projects.json`，每个项目和账号组合的
登录文件保存在 `~/.gemini/agy-switch/project-homes/` 下，权限限制为当前用户。
项目绑定不修改全局登录文件，因此不同项目可以同时运行不同账号。
本机 `~/.local/bin/agy` 是项目账号启动器，原始程序保存在
`~/.local/bin/agy-real`。启动器先读取当前目录的绑定，再以独立 `HOME`
运行原始程序。Bash、Fish 和直接执行 `agy` 都使用同一入口。

本机 `~/.bashrc` 也保留了 `agy` 包装函数：

```bash
agy() { /home/atang/.local/bin/agy-switch --launch-agy "$@"; }
```

Fish 使用 `~/.config/fish/functions/agy.fish` 中的同名函数。旧终端即使
尚未加载函数，只要通过 `~/.local/bin/agy` 启动，也会读取项目绑定。
已运行的 `agy` 会话仍保留启动时的账号，需退出后在对应项目目录重启。

项目启动时 `HOME` 指向项目独立目录。原 HOME 的其他顶层条目会以符号链接
保留，`.gemini` 登录状态则独立；`~` 本身会指向项目目录。

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
