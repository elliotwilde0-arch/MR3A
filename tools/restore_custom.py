# -*- coding: utf-8 -*-
"""方案B：升级后恢复自定义任务「启动游戏2」。

在升级完成、启动 MR3A 之前运行：
    python tools/restore_custom.py

它会：
- 确保 interface.json 的 import 含自定义任务文件；
- 确保自定义任务/流水线/Agent 动作存在（缺失时从 tools/custom_payload 复制）；
- 确保 Agent 注册 SecureTextInput；
- 确保 config/account_secret.json 存在（从活动配置或备份恢复）；
- 确保活动配置里有「启动游戏2」任务和账号密码数据。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CUSTOM_TASK_REL = "resource/tasks/custom/账号登录.json"
PAYLOAD = ROOT / "tools" / "custom_payload"
SECRET = ROOT / "config" / "account_secret.json"
OPTION = "账号密码"
TASK = "启动游戏2"


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def dump(p: Path, data) -> None:
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
    tmp.replace(p)


def ensure_files() -> None:
    mapping = [
        (PAYLOAD / "tasks" / "账号登录.json", ROOT / CUSTOM_TASK_REL),
        (PAYLOAD / "pipeline" / "账号登录.json", ROOT / "resource" / "pipeline" / "账号登录.json"),
        (PAYLOAD / "action" / "secure_input.py", ROOT / "agent" / "custom" / "action" / "secure_input.py"),
    ]
    for src, dst in mapping:
        if not dst.exists() and src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            print(f"[恢复] {dst.relative_to(ROOT)}")
        elif not dst.exists():
            print(f"[警告] 缺少 {dst.relative_to(ROOT)}，且没有 payload 可复制")


def ensure_interface() -> None:
    p = ROOT / "interface.json"
    d = load(p)
    imports = d.setdefault("import", [])
    if CUSTOM_TASK_REL not in imports:
        imports.append(CUSTOM_TASK_REL)
        dump(p, d)
        print(f"[恢复] interface.json import += {CUSTOM_TASK_REL}")


def ensure_agent() -> None:
    p = ROOT / "agent" / "custom" / "action" / "__init__.py"
    s = p.read_text(encoding="utf-8")
    if "secure_input" not in s:
        anchor = "from .load_game_meta_override import LoadGameMetaOverride"
        if anchor not in s:
            anchor = "from .general import *"
        s = s.replace(anchor, anchor + "\nfrom .secure_input import SecureTextInput")
        s = s.replace('    "LoadGameMetaOverride",', '    "LoadGameMetaOverride",\n    "SecureTextInput",')
        p.write_text(s, encoding="utf-8")
        print("[恢复] agent 注册 SecureTextInput")


def read_creds_from_config() -> dict:
    appsettings = ROOT / "appsettings.json"
    active = None
    if appsettings.is_file():
        try:
            active = load(appsettings).get("Instances.LastActive")
        except Exception:
            active = None
    candidates = []
    if active:
        candidates.append(ROOT / "config" / "instances" / f"{active}.json")
    candidates.extend(sorted((ROOT / "config" / "instances").glob("*.json")))
    for p in candidates:
        if not p.is_file():
            continue
        try:
            d = load(p)
        except Exception:
            continue
        for it in (d.get("TaskItems") or []):
            for o in (it.get("option") or []):
                if o.get("name") == OPTION and o.get("data"):
                    return o["data"]
                for s in (o.get("sub_options") or []):
                    if s.get("name") == OPTION and s.get("data"):
                        return s["data"]
    return {}


def read_creds_from_backups() -> dict:
    for p in sorted((ROOT / "config" / "instances").glob("*.json*"), reverse=True):
        if p.suffix == ".tmp":
            continue
        try:
            d = load(p)
        except Exception:
            continue
        for it in (d.get("TaskItems") or []):
            for o in (it.get("option") or []):
                if o.get("name") == OPTION and o.get("data"):
                    return o["data"]
                for s in (o.get("sub_options") or []):
                    if s.get("name") == OPTION and s.get("data"):
                        return s["data"]
    return {}


def ensure_secret() -> dict:
    data = {}
    if SECRET.is_file():
        try:
            data = load(SECRET)
        except Exception:
            data = {}
    if not data:
        data = read_creds_from_config() or read_creds_from_backups()
        if data:
            SECRET.parent.mkdir(parents=True, exist_ok=True)
            SECRET.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"[恢复] config/account_secret.json（账号 {len(data.get('账号',''))} 位，密码 {len(data.get('密码',''))} 位）")
    return data


def ensure_config_task(creds: dict) -> None:
    appsettings = ROOT / "appsettings.json"
    active = None
    if appsettings.is_file():
        try:
            active = load(appsettings).get("Instances.LastActive")
        except Exception:
            active = None
    if not active:
        print("[警告] 找不到 Instances.LastActive，跳过活动配置")
        return
    p = ROOT / "config" / "instances" / f"{active}.json"
    if not p.is_file():
        print(f"[警告] 找不到 {p.name}")
        return
    d = load(p)
    items = d.setdefault("TaskItems", [])
    main = next((it for it in items if it.get("name") == "启动游戏"), None)
    if main is None:
        print("[警告] 活动配置里没有「启动游戏」，跳过")
        return
    for o in (main.get("option") or []):
        subs = o.get("sub_options") or []
        for s in list(subs):
            if s.get("name") == OPTION:
                subs.remove(s)
    s2 = next((it for it in items if it.get("name") == TASK), None)
    if s2 is None:
        s2 = json.loads(json.dumps(main))
        s2["name"] = TASK
        s2["entry"] = "启动游戏entry"
        s2["default_check"] = False
        s2["description"] = "个人构建：官服账号密码登录。"
        s2["group"] = ["daily"]
        s2["option"] = [o for o in (s2.get("option") or []) if o.get("name") != OPTION]
        if not any(o.get("name") == "请选择服务器" for o in s2["option"]):
            s2["option"].append({"name": "请选择服务器", "index": 0})
        if not any(o.get("name") == "请选择区服" for o in s2["option"]):
            s2["option"].append({"name": "请选择区服", "index": 0})
        s2["option"].append({"name": OPTION, "index": 0, "data": creds})
        items.insert(items.index(main) + 1, s2)
        print("[恢复] 活动配置新增「启动游戏2」")
    else:
        opts = [o for o in (s2.get("option") or []) if o.get("name") != OPTION]
        opts.append({"name": OPTION, "index": 0, "data": creds})
        s2["option"] = opts
    dump(p, d)


def main() -> int:
    print(f"根目录：{ROOT}")
    ensure_files()
    ensure_interface()
    ensure_agent()
    creds = ensure_secret()
    ensure_config_task(creds)
    print("\n[完成] 重新启动 MR3A，任务列表里应出现「启动游戏2」。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
