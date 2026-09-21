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
import math
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib import request, parse, error

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

# The regular cloudcode-pa host can return an availability-style all-100 Gemini
# response for these accounts. agy uses the daily host for account quota; do not
# fall back to a different host and risk displaying misleading data.
QUOTA_URL = "https://daily-cloudcode-pa.googleapis.com/v1internal:retrieveUserQuotaSummary"
OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
_OAUTH_CLIENTS = None


class QuotaError(Exception):
    pass


def oauth_clients():
    """Discover agy's installed OAuth client without storing it in source control."""
    global _OAUTH_CLIENTS
    if _OAUTH_CLIENTS is not None:
        return _OAUTH_CLIENTS

    candidates = []
    env_id = os.environ.get("AGY_OAUTH_CLIENT_ID")
    env_secret = os.environ.get("AGY_OAUTH_CLIENT_SECRET")
    if env_id and env_secret:
        candidates.append((env_id, env_secret))

    binary = os.environ.get("AGY_BIN") or shutil.which("agy")
    if binary:
        try:
            content = Path(binary).read_bytes()
            client_ids = list(dict.fromkeys(match.decode("ascii") for match in re.findall(
                rb"[0-9]+-[a-z0-9]+\.apps\.googleusercontent\.com", content)))
            client_secrets = list(dict.fromkeys(match.decode("ascii") for match in re.findall(
                rb"GOCSPX-[A-Za-z0-9_-]{28}", content)))
            for client_id in client_ids:
                for client_secret in client_secrets:
                    pair = (client_id, client_secret)
                    if pair not in candidates:
                        candidates.append(pair)
        except (OSError, ValueError):
            pass

    _OAUTH_CLIENTS = candidates
    return candidates


def parse_time(value):
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.astimezone()
    except (ValueError, TypeError, AttributeError):
        return None


def format_reset(value):
    dt = parse_time(value)
    if dt is None:
        return "重置时间未知"
    minutes = math.ceil((dt - datetime.now(timezone.utc)).total_seconds() / 60)
    if minutes <= 0:
        return "已到期"
    if minutes < 60:
        return f"{minutes} 分钟后"
    if minutes < 1440:
        return f"{minutes // 60} 小时 {minutes % 60} 分钟后"
    return f"{minutes // 1440} 天 {minutes % 1440 // 60} 小时后"


def quota_bar(fraction, width=14):
    filled = max(0, min(width, round(fraction * width)))
    if fraction >= 0.5:
        color = GREEN
    elif fraction >= 0.2:
        color = YELLOW
    else:
        color = RED
    return f"{color}{'█' * filled}{DIM}{'░' * (width - filled)}{RESET}"


def post_json(url, body, headers):
    req = request.Request(url, data=body, headers=headers, method="POST")
    with request.urlopen(req, timeout=12) as response:
        result = json.load(response)
    if not isinstance(result, dict):
        raise QuotaError("额度接口返回格式异常")
    return result


def refresh_quota_token(data):
    token = data.get("token", {})
    if not token.get("refresh_token"):
        raise QuotaError("登录已过期且无刷新凭证，请重新登录")
    if data.get("auth_method", "consumer") != "consumer":
        raise QuotaError("此认证类型暂不支持自动刷新，请通过 agy 更新登录")
    clients = oauth_clients()
    if not clients:
        raise QuotaError("未找到 agy 的 OAuth 客户端配置，请通过 agy 重新登录")
    last_error = None
    for client_id, client_secret in clients:
        body = parse.urlencode({
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": token["refresh_token"],
            "grant_type": "refresh_token",
        }).encode()
        try:
            result = post_json(OAUTH_TOKEN_URL, body,
                               {"Content-Type": "application/x-www-form-urlencoded"})
        except error.HTTPError as exc:
            last_error = exc.code
            continue
        if result.get("access_token"):
            # Query with a temporary token; never replace another process's login state.
            return result["access_token"]
        last_error = "invalid response"
    if isinstance(last_error, int):
        raise QuotaError(f"刷新登录失败 (HTTP {last_error})，请通过 agy 重新登录")
    raise QuotaError("刷新登录未返回访问凭证，请通过 agy 重新登录")


def fetch_quota(data):
    """Read each account independently; errors never expose response bodies/tokens."""
    try:
        if not isinstance(data, dict) or not isinstance(data.get("token"), dict):
            raise QuotaError("未找到有效的账号凭证")
        token = data["token"]
        access = token.get("access_token")
        expiry = parse_time(token.get("expiry"))
        refreshed = not access or (expiry and expiry <= datetime.now(timezone.utc))
        if refreshed:
            access = refresh_quota_token(data)
        def query():
            return post_json(QUOTA_URL, b"{}", {
                "Authorization": "Bearer " + access,
                "Content-Type": "application/json", "User-Agent": "antigravity",
            })
        try:
            result = query()
        except error.HTTPError as exc:
            if exc.code != 401 or refreshed:
                raise
            access = refresh_quota_token(data)
            result = query()
        groups = result.get("groups", [])
        if not groups and result.get("buckets"):
            groups = [{"displayName": "模型额度", "buckets": result["buckets"]}]
        if not isinstance(groups, list) or any(
            not isinstance(g, dict) or not isinstance(g.get("buckets", []), list)
            or any(not isinstance(b, dict) for b in g.get("buckets", [])) for g in groups
        ):
            raise QuotaError("额度接口返回格式异常")
        return {"groups": groups}
    except QuotaError as exc:
        return {"error": str(exc)}
    except error.HTTPError as exc:
        return {"error": f"额度查询失败 (HTTP {exc.code})"}
    except (error.URLError, TimeoutError, OSError):
        return {"error": "额度查询超时或网络不可用"}
    except (ValueError, TypeError):
        return {"error": "额度接口返回格式异常"}


def format_bucket(bucket):
    if not bucket:
        return "未提供"
    fraction = bucket.get("remainingFraction")
    if isinstance(fraction, (float, int)) and not isinstance(fraction, bool) and math.isfinite(fraction) and 0 <= fraction <= 1:
        remaining = fraction * 100
        percentage = f"{quota_bar(fraction)} {remaining:.1f}% 剩余"
        if bucket.get("disabled"):
            return f"{percentage}  · 当前不适用"
    else:
        percentage = "未提供"
        if bucket.get("disabled"):
            return "当前不适用"
    return f"{percentage}  · 重置 {format_reset(bucket.get('resetTime'))}"


def print_quota(result, indent="    "):
    if result.get("error"):
        print(f"{indent}{YELLOW}{result['error']}{RESET}")
        return
    if not result.get("groups"):
        print(f"{indent}5h / 一周额度: 接口未提供")
    for group in result.get("groups", []):
        label = group.get("displayName", "模型额度")
        if label == "Gemini Models":
            label = "Gemini"
        elif label == "Claude and GPT models":
            label = "Claude / GPT-OSS"
        print(f"{indent}{CYAN}{label} 共享额度{RESET}")
        buckets = group.get("buckets", [])
        for window, title in [("5h", "5h"), ("weekly", "一周")]:
            bucket = next((b for b in buckets if b.get("window") == window), None)
            print(f"{indent}  {title:<4} {format_bucket(bucket)}")


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
    # Remove any existing alias for this email to prevent duplicates
    for old_name, info in list(meta.items()):
        if info.get("email") == email and old_name != name:
            del meta[old_name]

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
        # Only delete token from keyring if no remaining profile uses this email
        if not any(info.get("email") == email for info in meta.values()):
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
            if name != summary["email"]:
                break

    print(f"\n{BOLD}=== 当前账号 ==={RESET}")
    if matched_profile and matched_profile != summary["email"]:
        print(f"  {GREEN}●{RESET}  {BOLD}{matched_profile}{RESET}  {summary['email']}")
    elif matched_profile:
        print(f"  {GREEN}●{RESET}  {summary['email']}  {DIM}(默认邮箱别名){RESET}")
    else:
        print(f"  {YELLOW}●{RESET}  {summary['email']}  {DIM}(未保存别名){RESET}")
    if not getattr(args, "no_quota", False):
        print()
        print_quota(fetch_quota(cur_data), "  ")
        print()


def cmd_list(args):
    cur_data = get_current_keyring_token()
    cur_summary = get_token_summary(cur_data) if cur_data else None
    cur_email = cur_summary["email"] if cur_summary else None

    meta = load_meta()

    print(f"\n{BOLD}=== 账号额度 ==={RESET}")
    if not meta:
        print(f"  {DIM}(当前尚无保存的账号档案){RESET}")
    else:
        profiles = []
        for name, info in sorted(meta.items()):
            try:
                data = cur_data if info.get("email") == cur_email else get_profile_payload(info.get("email"))
            except Exception:
                data = None
            profiles.append((name, info, data))
        show_quota = not getattr(args, "no_quota", False)
        if show_quota:
            print(f"  {DIM}正在刷新额度 · 进度条和百分比均表示剩余{RESET}", flush=True)
            with ThreadPoolExecutor(max_workers=min(4, len(profiles))) as pool:
                quotas = list(pool.map(fetch_quota, [p[2] for p in profiles]))
        else:
            quotas = [None] * len(profiles)
        for (name, info, data), quota in zip(profiles, quotas):
            is_active = (cur_email and info.get("email") == cur_email)
            marker = f"{GREEN}● 当前{RESET}" if is_active else f"{DIM}○ 空闲{RESET}"
            email = info.get("email", "unknown")
            alias_display = f"{BOLD}{name}{RESET}" if name != email else f"{DIM}{name}{RESET} {YELLOW}(默认邮箱别名){RESET}"
            print(f"\n  {marker}  {alias_display}  {email}")
            if quota is not None:
                print_quota(quota)

    if cur_email:
        has_custom = any(info.get("email") == cur_email and name != cur_email for name, info in meta.items())
        if not has_custom:
            print(f"\n{YELLOW}提示: 当前活跃账号 {cur_email} 尚未设置别名，可运行 `agy-switch alias <别名>` 或 `agy-switch save <别名>`。{RESET}")
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
        # Match by email (prefer custom alias if multiple exist)
        for name, info in meta.items():
            if info.get("email") == target:
                selected_name = name
                target_email = info.get("email")
                if name != target:
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

    # Step 1: Check if current account is already logged in but unsaved
    if cur_data and cur_summary:
        cur_email = cur_summary["email"]
        meta = load_meta()
        custom_aliases = [name for name, info in meta.items() if info.get("email") == cur_email and name != cur_email]
        if not custom_aliases:
            target_name = args.name or cur_email
            print(f"\n{YELLOW}检测到当前已有活跃登录账号: [{cur_email}]{RESET}")
            if target_name != cur_email:
                print(f"您指定了别名: {BOLD}{target_name}{RESET}")
            try:
                choice = input(f"是否直接将当前账号保存为档案别名 [{BOLD}{target_name}{RESET}]？(Y/n): ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                print("\n操作已取消。")
                return
            if choice in ("", "y", "yes"):
                save_profile(target_name, cur_email, cur_data)
                print(f"{GREEN}✓ 成功将当前账号 [{cur_email}] 保存为配置档案: {BOLD}{target_name}{RESET}")
                return
            else:
                # User chose 'n' - wants to log into a different account
                if not any(info.get("email") == cur_email for info in meta.values()):
                    save_profile(cur_email, cur_email, cur_data)
                    print(f"{GREEN}✓ 当前账号已临时备份为 [{cur_email}]。{RESET}")
        else:
            if not any(info.get("email") == cur_email for info in meta.values()):
                save_profile(cur_email, cur_email, cur_data)

    # Step 2: Clear keyring token and launch agy for new login
    print(f"\n{CYAN}准备添加并登录新账号:{RESET}")
    print(f"1. 即将临时清空当前活跃登录态（旧凭据已安全保存在本地档案中）。")
    print(f"2. 启动 agy 后，请在弹出的浏览器中登录您的【新 Google 账号】并授权。")
    print(f"3. 登录成功后，若进入了 agy 对话界面，按 {BOLD}Ctrl+C{RESET} 退出即可完成保存。\n")
    try:
        input(f"{BOLD}请按回车键继续 (或 Ctrl+C 取消)...{RESET}")
    except (KeyboardInterrupt, EOFError):
        print("\n操作已取消。")
        return

    delete_current_keyring_token()
    print(f"{YELLOW}已清除活跃登录态。正在启动 agy 触发登录流程...{RESET}\n")

    try:
        subprocess.run(["agy"], check=False)
    except KeyboardInterrupt:
        print()
    except FileNotFoundError:
        print(f"{RED}未在 PATH 中找到 agy 命令。请手动运行 agy 完成新账号登录。{RESET}")
        if cur_data:
            set_current_keyring_token(cur_data)
        return

    # Step 3: Check if new login succeeded
    new_data = get_current_keyring_token()
    if not new_data:
        print(f"\n{RED}未检测到新登录凭证。{RESET}")
        if cur_data:
            set_current_keyring_token(cur_data)
            print(f"{GREEN}✓ 已恢复之前的账号登录状态。{RESET}")
        print(f"提示: 您可以稍后运行 `agy` 登录，随后使用 `agy-switch save [别名]` 保存。")
        return

    new_summary = get_token_summary(new_data)
    new_email = new_summary["email"]
    name = args.name or new_email
    save_profile(name, new_email, new_data)

    print(f"\n{GREEN}✓ 新账号 [{new_email}] 登录并保存成功！档案别名: {BOLD}{name}{RESET}")
    print(f"您随时可以使用 {BOLD}agy-switch switch {name}{RESET} 切换回此账号。")


def cmd_rename(args):
    positionals = args.names
    meta = load_meta()
    
    if len(positionals) == 1:
        new_name = positionals[0]
        cur_data = get_current_keyring_token()
        cur_summary = get_token_summary(cur_data) if cur_data else None
        if not cur_summary:
            print(f"{RED}错误: 未指定目标账号，且当前未检测到活跃账号。{RESET}")
            print(f"用法: `agy-switch alias [账号邮箱或旧别名] <新别名>` 或 `agy-switch alias <新别名>` (针对当前账号)")
            return
        cur_email = cur_summary["email"]
        selected_name = None
        for name, info in meta.items():
            if info.get("email") == cur_email:
                selected_name = name
                break
        if not selected_name:
            save_profile(new_name, cur_email, cur_data)
            print(f"{GREEN}✓ 成功将当前账号 [{cur_email}] 保存为配置档案: {BOLD}{new_name}{RESET}")
            return
    elif len(positionals) == 2:
        target, new_name = positionals[0], positionals[1]
        selected_name = None
        if target in meta:
            selected_name = target
        else:
            for name, info in meta.items():
                if info.get("email") == target:
                    selected_name = name
                    break
        if not selected_name:
            print(f"{RED}错误: 未找到名为或邮箱为 [{target}] 的账号档案。{RESET}")
            print(f"请使用 `agy-switch list` 查看所有可用档案。")
            return
    else:
        print(f"{RED}错误: 参数数量不正确。{RESET}")
        print(f"用法: `agy-switch alias [旧别名或邮箱] <新别名>` 或针对当前账号 `agy-switch alias <新别名>`")
        return

    if selected_name == new_name:
        print(f"{YELLOW}档案别名已经是 [{new_name}]，无需修改。{RESET}")
        return

    if new_name in meta and meta[new_name].get("email") != meta[selected_name].get("email"):
        print(f"{RED}错误: 别名 [{new_name}] 已被其他账号 ({meta[new_name].get('email')}) 使用。{RESET}")
        return

    email = meta[selected_name]["email"]
    info = meta.pop(selected_name)
    info["saved_at"] = datetime.now().isoformat()
    
    # Remove any other duplicate entries for this email
    for old_name, old_info in list(meta.items()):
        if old_info.get("email") == email:
            del meta[old_name]

    meta[new_name] = info
    save_meta(meta)
    print(f"{GREEN}✓ 成功将账号 [{email}] 的别名修改为: {BOLD}{new_name}{RESET}")


def cmd_remove(args):
    name = args.name
    meta = load_meta()
    target_name = None
    if name in meta:
        target_name = name
    else:
        for n, info in meta.items():
            if info.get("email") == name:
                target_name = n
                break

    if not target_name:
        print(f"{RED}错误: 档案 [{name}] 不存在。{RESET}")
        return

    email = meta[target_name]["email"]
    try:
        confirm = input(f"确认删除账号档案 [{target_name}] ({email}) 吗？(y/N): ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print("\n操作已取消。")
        return
    if confirm == "y":
        delete_profile(target_name)
        print(f"{GREEN}✓ 已删除档案 [{target_name}]。{RESET}")
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
    p_list.add_argument("--no-quota", action="store_true", help="仅查看本地账号信息，不联网查询额度")
    p_list.set_defaults(func=cmd_list)

    # current
    p_cur = subparsers.add_parser("current", aliases=["status", "whoami"], help="查看当前活跃账号详情")
    p_cur.add_argument("--no-quota", action="store_true", help="仅查看本地账号信息，不联网查询额度")
    p_cur.set_defaults(func=cmd_current)

    # save
    p_save = subparsers.add_parser("save", help="将当前系统活跃账号保存为档案")
    p_save.add_argument("name", nargs="?", default=None, help="配置别名 (留空默认使用邮箱)")
    p_save.set_defaults(func=cmd_save)

    # alias / rename
    p_alias = subparsers.add_parser("alias", aliases=["rename", "set-alias"], help="修改或设置账号别名")
    p_alias.add_argument("names", nargs="+", help="[旧别名或邮箱] <新别名>，若仅提供一个参数则修改当前账号别名")
    p_alias.set_defaults(func=cmd_rename)

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
    p_rm.add_argument("name", help="要删除的档案别名或邮箱")
    p_rm.set_defaults(func=cmd_remove)

    if len(sys.argv) == 1:
        current = get_token_summary(get_current_keyring_token())
        listed = current and any(info.get("email") == current["email"] for info in load_meta().values())
        cmd_current(argparse.Namespace(no_quota=bool(listed)))
        cmd_list(argparse.Namespace(no_quota=False))
        print(f"{DIM}运行 `agy-switch --help` 查看所有切换与管理命令。{RESET}")
        return

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
