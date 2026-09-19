#!/usr/bin/env python3
"""
gemini-switch / agy-switch
Multi-account manager & switcher for Google Antigravity CLI (agy), IDE, and Gemini.
"""

import sys
import os
import json
import base64
import argparse
import subprocess
from datetime import datetime
from pathlib import Path

try:
    import keyring
except ImportError:
    print("\033[91m错误: 未找到 keyring 模块。请先运行 `pip install keyring`。\033[0m")
    sys.exit(1)

SERVICE_NAME = "gemini"
ACTIVE_USERNAME = "antigravity"
PROFILE_SERVICE = "gemini-accounts"

CONFIG_DIR = Path.home() / ".gemini"
OLD_ACCOUNTS_DIR = CONFIG_DIR / "accounts"
META_FILE = CONFIG_DIR / "accounts_meta.json"

# ANSI Colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def parse_id_token(id_token: str) -> dict:
    if not id_token:
        return {}
    try:
        parts = id_token.split(".")
        if len(parts) >= 2:
            payload = parts[1]
            payload += "=" * (-len(payload) % 4)
            return json.loads(base64.urlsafe_b64decode(payload.encode("utf-8")))
    except Exception:
        pass
    return {}


def get_current_keyring_token():
    try:
        raw_str = keyring.get_password(SERVICE_NAME, ACTIVE_USERNAME)
        if raw_str:
            return json.loads(raw_str)
    except Exception as e:
        print(f"{YELLOW}读取系统钥匙串时出错: {e}{RESET}")
    return None


def set_current_keyring_token(data: dict):
    raw_str = json.dumps(data)
    keyring.set_password(SERVICE_NAME, ACTIVE_USERNAME, raw_str)


def delete_current_keyring_token():
    try:
        if keyring.get_password(SERVICE_NAME, ACTIVE_USERNAME):
            keyring.delete_password(SERVICE_NAME, ACTIVE_USERNAME)
    except keyring.errors.PasswordDeleteError:
        pass


def load_meta() -> dict:
    if not META_FILE.exists():
        return {}
    try:
        with open(META_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_meta(meta: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(META_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    os.chmod(META_FILE, 0o600)


def save_profile(name: str, email: str, data: dict):
    # 1. Save metadata (no sensitive tokens)
    meta = load_meta()
    meta[name] = {
        "email": email,
        "saved_at": datetime.now().isoformat()
    }
    save_meta(meta)
    
    # 2. Save actual token to keyring
    keyring.set_password(PROFILE_SERVICE, email, json.dumps(data))


def get_profile_payload(email: str) -> dict:
    raw_str = keyring.get_password(PROFILE_SERVICE, email)
    if raw_str:
        return json.loads(raw_str)
    return None


def delete_profile(name: str):
    meta = load_meta()
    if name in meta:
        email = meta[name]["email"]
        del meta[name]
        save_meta(meta)
        try:
            if keyring.get_password(PROFILE_SERVICE, email):
                keyring.delete_password(PROFILE_SERVICE, email)
        except keyring.errors.PasswordDeleteError:
            pass


def get_token_summary(data: dict):
    if not data:
        return None
    claims = parse_id_token(data.get("id_token", ""))
    email = claims.get("email") or "未知邮箱"
    exp = data.get("token", {}).get("expiry", "无过期时间")
    has_refresh = bool(data.get("token", {}).get("refresh_token"))
    return {
        "email": email,
        "expiry": exp,
        "has_refresh": has_refresh,
        "auth_method": data.get("auth_method", "consumer")
    }


def migrate_old_accounts():
    """Migrate plain text accounts to Keyring and metadata file."""
    if not OLD_ACCOUNTS_DIR.exists():
        return
    
    json_files = list(OLD_ACCOUNTS_DIR.glob("*.json"))
    if not json_files:
        return
        
    print(f"{YELLOW}检测到旧版本明文保存的账号档案，正在执行安全迁移...{RESET}")
    migrated_count = 0
    meta = load_meta()
    
    for file in json_files:
        try:
            with open(file, "r", encoding="utf-8") as f:
                content = json.load(f)
            
            name = file.stem
            email = content.get("email")
            payload = content.get("payload")
            saved_at = content.get("saved_at", datetime.now().isoformat())
            
            if email and payload:
                # 1. Save to keyring
                keyring.set_password(PROFILE_SERVICE, email, json.dumps(payload))
                # 2. Update meta
                meta[name] = {"email": email, "saved_at": saved_at}
                migrated_count += 1
                
            # Rename file to prevent re-migration
            file.rename(file.with_suffix(".json.bak"))
        except Exception as e:
            print(f"{RED}迁移档案 {file.name} 失败: {e}{RESET}")
            
    save_meta(meta)
    if migrated_count > 0:
        print(f"{GREEN}✓ 成功将 {migrated_count} 个账号安全迁移到系统密钥环！旧文件已重命名为 .bak 备份。{RESET}")


def cmd_current(args):
    cur_data = get_current_keyring_token()
    if not cur_data:
        print(f"{YELLOW}当前未检测到任何已登录的 Antigravity / Gemini 账号。{RESET}")
        print(f"请运行 {BOLD}agy{RESET} 进行初次登录。")
        return

    summary = get_token_summary(cur_data)
    meta = load_meta()
    
    matched_profile = None
    for name, info in meta.items():
        if info.get("email") == summary["email"]:
            matched_profile = name
            break

    print(f"\n{BOLD}=== 当前活跃账号 ==={RESET}")
    print(f"  {CYAN}邮箱:{RESET}         {BOLD}{summary['email']}{RESET}")
    if matched_profile:
        print(f"  {CYAN}配置档案别名:{RESET} {GREEN}{matched_profile}{RESET}")
    else:
        print(f"  {CYAN}配置档案别名:{RESET} {YELLOW}(尚未保存为别名，建议运行 `agy-switch save` 保存){RESET}")
    print(f"  {CYAN}Token 到期时间:{RESET} {summary['expiry']}")
    print(f"  {CYAN}拥有刷新凭证:{RESET} {'是' if summary['has_refresh'] else '否'}")
    print(f"  {CYAN}认证类型:{RESET}     {summary['auth_method']}\n")


def cmd_list(args):
    cur_data = get_current_keyring_token()
    cur_summary = get_token_summary(cur_data) if cur_data else None
    cur_email = cur_summary["email"] if cur_summary else None

    meta = load_meta()

    print(f"\n{BOLD}=== 已保存的 Gemini / Antigravity 账号列表 ==={RESET}")
    if not meta:
        print(f"  {DIM}(当前尚无保存的账号档案){RESET}")
    else:
        print(f"  {'状态':<6} {'档案别名 (Alias)':<20} {'邮箱 (Email)':<32} {'保存时间':<20}")
        print(f"  {'-'*6} {'-'*20} {'-'*32} {'-'*20}")
        for name, info in sorted(meta.items()):
            is_active = (cur_email and info.get("email") == cur_email)
            marker = f"{GREEN}* 活跃{RESET}" if is_active else f"{DIM}  空闲{RESET}"
            email = info.get("email", "unknown")
            saved_at = info.get("saved_at", "")[:19].replace("T", " ")
            print(f"  {marker:<15} {BOLD}{name:<20}{RESET} {email:<32} {saved_at:<20}")

    if cur_email and not any(info.get("email") == cur_email for info in meta.values()):
        print(f"\n{YELLOW}提示: 当前活跃账号 {cur_email} 尚未保存档案，可运行 `agy-switch save` 将其保存。{RESET}")
    print()


def cmd_save(args):
    cur_data = get_current_keyring_token()
    if not cur_data:
        print(f"{RED}错误: 当前没有检测到已登录的账号，无法保存。{RESET}")
        return

    summary = get_token_summary(cur_data)
    email = summary["email"]
    name = args.name or email

    save_profile(name, email, cur_data)
    print(f"{GREEN}✓ 成功将账号 [{email}] 保存为配置档案: {BOLD}{name}{RESET}")


def cmd_switch(args):
    target = args.target
    meta = load_meta()

    selected_name = None
    target_email = None

    # Exact match by name
    if target in meta:
        selected_name = target
        target_email = meta[target]["email"]
    else:
        # Match by email
        for name, info in meta.items():
            if info.get("email") == target:
                selected_name = name
                target_email = info.get("email")
                break

    if not target_email:
        print(f"{RED}错误: 未找到名为或邮箱为 [{target}] 的账号档案。{RESET}")
        print(f"请使用 `agy-switch list` 查看所有可用档案。")
        return

    # Fetch token from keyring
    payload = get_profile_payload(target_email)
    if not payload:
        print(f"{RED}错误: 无法在密钥环中读取到账号 [{target_email}] 的凭据。可能是被手动删除或未成功迁移。{RESET}")
        return

    # Check if already active
    cur_data = get_current_keyring_token()
    cur_summary = get_token_summary(cur_data) if cur_data else None
    if cur_summary and cur_summary["email"] == target_email:
        print(f"{YELLOW}提示: 当前已经在使用账号 [{target_email}] (档案: {selected_name})。{RESET}")
        return

    # Auto-save current account if unsaved
    if cur_data and cur_summary:
        cur_email = cur_summary["email"]
        if not any(info.get("email") == cur_email for info in meta.values()):
            print(f"{YELLOW}检测到当前活跃账号 [{cur_email}] 尚未备份，正在自动保存为档案...{RESET}")
            save_profile(cur_email, cur_email, cur_data)

    print(f"正在切换到账号: {BOLD}{target_email}{RESET} (档案: {selected_name})...")
    set_current_keyring_token(payload)
    print(f"{GREEN}✓ 成功切换到账号 [{target_email}]！{RESET}")
    print(f"{DIM}提示: 下次启动 `agy` 或开启新任务时将自动使用此账号。若 IDE 正在运行，重载窗口即可生效。{RESET}")


def cmd_add(args):
    cur_data = get_current_keyring_token()
    cur_summary = get_token_summary(cur_data) if cur_data else None

    # Step 1: Ensure current is saved
    if cur_data and cur_summary:
        cur_email = cur_summary["email"]
        meta = load_meta()
        if not any(info.get("email") == cur_email for info in meta.values()):
            auto_name = cur_email
            print(f"{YELLOW}为防止当前账号凭证丢失，正在先将当前账号 [{cur_email}] 备份为档案 [{auto_name}]...{RESET}")
            save_profile(auto_name, cur_email, cur_data)
            print(f"{GREEN}✓ 当前账号已备份。{RESET}")

    # Step 2: Clear keyring token
    print(f"\n{CYAN}准备添加新账号:{RESET}")
    print(f"1. 即将清空系统钥匙串中的活跃登录态（旧凭据已安全保存在本地档案中）。")
    print(f"2. 请在弹出的浏览器中登录您的【新 Google / Gemini 账号】并授权。")
    input(f"{BOLD}请按回车键继续...{RESET}")

    delete_current_keyring_token()
    print(f"{YELLOW}已清除活跃登录态。正在启动 agy 触发登录流程...{RESET}\n")

    try:
        # Launch agy in interactive login mode
        subprocess.run(["agy"], check=False)
    except FileNotFoundError:
        print(f"{RED}未在 PATH 中找到 agy 命令。请手动运行 agy 完成新账号登录。{RESET}")
        return

    # Step 3: Check if new login succeeded
    new_data = get_current_keyring_token()
    if not new_data:
        print(f"\n{RED}未检测到新登录凭证。如果尚未完成登录，可稍后运行 `agy` 登录，随后使用 `agy-switch save [别名]` 保存。{RESET}")
        return

    new_summary = get_token_summary(new_data)
    new_email = new_summary["email"]
    name = args.name or new_email
    save_profile(name, new_email, new_data)

    print(f"\n{GREEN}✓ 新账号 [{new_email}] 登录并保存成功！档案别名: {BOLD}{name}{RESET}")
    print(f"您随时可以使用 {BOLD}agy-switch switch {name}{RESET} 切换回此账号。")


def cmd_remove(args):
    name = args.name
    meta = load_meta()
    if name not in meta:
        print(f"{RED}错误: 档案 [{name}] 不存在。{RESET}")
        return

    confirm = input(f"确认删除账号档案 [{name}] 吗？(y/N): ").strip().lower()
    if confirm == "y":
        delete_profile(name)
        print(f"{GREEN}✓ 已删除档案 [{name}]。{RESET}")
    else:
        print("操作已取消。")


def main():
    # Attempt migration if needed
    try:
        migrate_old_accounts()
    except Exception:
        pass

    parser = argparse.ArgumentParser(
        prog="gemini-switch",
        description="Google Antigravity CLI (agy) & Gemini 多账号一键管理与切换工具"
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="子命令")

    # list
    p_list = subparsers.add_parser("list", aliases=["ls"], help="列出所有已保存账号及当前激活账号")
    p_list.set_defaults(func=cmd_list)

    # current
    p_cur = subparsers.add_parser("current", aliases=["status", "whoami"], help="查看当前活跃账号详情")
    p_cur.set_defaults(func=cmd_current)

    # save
    p_save = subparsers.add_parser("save", help="将当前系统活跃账号保存为档案")
    p_save.add_argument("name", nargs="?", default=None, help="配置别名 (留空默认使用邮箱)")
    p_save.set_defaults(func=cmd_save)

    # switch
    p_switch = subparsers.add_parser("switch", aliases=["use"], help="切换到指定账号档案 (按别名或邮箱)")
    p_switch.add_argument("target", help="目标档案别名或邮箱")
    p_switch.set_defaults(func=cmd_switch)

    # add
    p_add = subparsers.add_parser("add", help="添加并登录一个全新的 Google 账号")
    p_add.add_argument("name", nargs="?", default=None, help="新账号的别名 (留空默认使用邮箱)")
    p_add.set_defaults(func=cmd_add)

    # remove
    p_rm = subparsers.add_parser("remove", aliases=["rm"], help="删除指定的账号档案")
    p_rm.add_argument("name", help="要删除的档案别名")
    p_rm.set_defaults(func=cmd_remove)

    if len(sys.argv) == 1:
        cmd_current(None)
        cmd_list(None)
        print(f"{DIM}运行 `gemini-switch --help` 查看所有切换与管理命令。{RESET}")
        return

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
