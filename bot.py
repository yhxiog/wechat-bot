# -*- coding: utf-8 -*-
"""
微信 4.x 智能聊天机器人
================================

基于 wechatauto-replica（微信 4.x 本地自动化）+ DeepSeek / OpenAI 兼容 API。

工作方式：
  1. 只读读取本机微信客户端加密数据库，增量轮询新消息；
  2. 收到「别人发来的文本消息」后，调用 AI 生成回复；
  3. 通过微信窗口（UIA 优先 + OCR 兜底）把回复自动发回对应会话。

运行前提（缺一不可）：
  1. 本机已安装并登录微信(Weixin 4.x)，且微信保持运行、屏幕不要锁屏；
  2. config.json 中已填入 AI 的 api_key（DeepSeek 申请地址见 README）。

免责声明：本工具仅用于学习交流，请勿用于违法违规用途。个人微信自动化存在
账号被限制/封禁的风险，建议使用小号测试，后果自负。
"""

import os
import sys
import json
import time
import threading
from collections import defaultdict, deque

# ---------- 让 Python 找到 deps 里安装好的依赖 ----------
BASE = os.path.dirname(os.path.abspath(__file__))
for cand in (os.path.join(BASE, "deps"), os.path.join(BASE, "..", "deps")):
    cand = os.path.abspath(cand)
    if os.path.isdir(os.path.join(cand, "wechatauto")):
        if cand not in sys.path:
            sys.path.insert(0, cand)
        break

from wechatauto.db import WeChatDB, Listener  # noqa: E402
from wechatauto import WeChatGUI               # noqa: E402

# ---------- 路径 ----------
CONFIG_PATH = os.path.join(BASE, "config.json")
CONFIG_EXAMPLE_PATH = os.path.join(BASE, "config.example.json")
WATERMARK_PATH = os.path.join(BASE, "watermark.json")
LOG_PATH = os.path.join(BASE, "bot.log")

# ---------- 控制台编码（Windows 中文输出） ----------
try:
    os.system("chcp 65001 >nul 2>&1")
except Exception:
    pass
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ---------- 日志 ----------
_log_lock = threading.Lock()


def log(msg):
    line = "[%s] %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
    with _log_lock:
        try:
            print(line, flush=True)
        except Exception:
            pass
        try:
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass


# ---------- 配置 ----------
def load_config():
    raw = {}
    _cfg = CONFIG_PATH if os.path.isfile(CONFIG_PATH) else CONFIG_EXAMPLE_PATH
    if os.path.isfile(_cfg):
        try:
            with open(_cfg, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:
            log("[警告] 读取配置文件失败：%s，使用默认配置" % e)
    ai = raw.get("ai") or {}
    bot = raw.get("bot") or {}
    return {
        "api_key": str(ai.get("api_key") or "").strip(),
        "base_url": str(ai.get("base_url") or "https://api.deepseek.com").strip(),
        "model": str(ai.get("model") or "deepseek-v4-flash").strip(),
        "system_prompt": str(ai.get("system_prompt")
                             or "你是一个友好、简洁、乐于助人的微信聊天助手，请用中文回复。"),
        "max_tokens": int(ai.get("max_tokens", 1000)),
        "temperature": float(ai.get("temperature", 0.7)),
        "listen_interval": float(bot.get("listen_interval", 1.0)),
        "max_history": int(bot.get("max_history", 8)),
        "max_reply_len": int(bot.get("max_reply_len", 1500)),
        "allowed_chats": [str(x) for x in (bot.get("allowed_chats") or [])],
        "blocked_chats": [str(x) for x in (bot.get("blocked_chats") or [])],
        "no_api_key_reply": str(bot.get("no_api_key_reply")
                                or "🤖 机器人尚未配置 API Key，请编辑 config.json 填入 api_key 后重启。"),
    }


cfg = load_config()

# ---------- AI 客户端 ----------
ai_client = None
if cfg["api_key"]:
    try:
        from openai import OpenAI
        ai_client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])
        log("AI 已就绪：%s @ %s" % (cfg["model"], cfg["base_url"]))
    except Exception as e:
        log("[警告] AI 客户端初始化失败：%s" % e)
else:
    log("[提示] 未配置 api_key，机器人进入「提示模式」（收到消息时提示配置 key）。")

# ---------- 运行期状态 ----------
_db = None
histories = defaultdict(lambda: deque(maxlen=cfg["max_history"]))
_notified = set()          # 已提示过「未配置 key」的会话
_name_cache = {}
_name_cache_lock = threading.Lock()
_send_lock = threading.Lock()
_recent_seq = deque(maxlen=500)
_gui = None
_gui_lock = threading.Lock()


# ---------- 工具函数 ----------
def display_name(username):
    """会话 username -> 显示名（备注/昵称），用于发送时搜索。"""
    with _name_cache_lock:
        if username not in _name_cache:
            try:
                _name_cache[username] = _db.get_nickname(username) or username
            except Exception:
                _name_cache[username] = username
        return _name_cache[username]


def get_gui():
    global _gui
    with _gui_lock:
        if _gui is None:
            _gui = WeChatGUI()
        return _gui


def chat_allowed(username):
    if cfg["allowed_chats"] and username not in cfg["allowed_chats"]:
        return False
    if username in cfg["blocked_chats"]:
        return False
    return True


def generate_reply(username, text):
    """生成回复文本；未配置 key 时返回提示（每个会话只提示一次）。"""
    if ai_client is None:
        if username in _notified:
            return None
        _notified.add(username)
        return cfg["no_api_key_reply"]

    history = list(histories[username])
    messages = [{"role": "system", "content": cfg["system_prompt"]}]
    messages.extend(history)
    messages.append({"role": "user", "content": text})
    resp = ai_client.chat.completions.create(
        model=cfg["model"],
        messages=messages,
        max_tokens=cfg["max_tokens"],
        temperature=cfg["temperature"],
    )
    return (resp.choices[0].message.content or "").strip()


def send_reply(username, text):
    """把回复发回指定会话（发送为 GUI 操作，串行化避免窗口冲突）。"""
    text = (text or "").strip()
    if not text:
        return
    if len(text) > cfg["max_reply_len"]:
        text = text[:cfg["max_reply_len"]] + "…(截断)"
    who = display_name(username)
    with _send_lock:
        try:
            wx = get_gui()
            if not wx.desktop_available():
                log("[发送跳过] 桌面不可用（可能锁屏/微信未打开）")
                return
            resp = wx.send_msg(text, who, verify=False)
            ok = bool(getattr(resp, "is_success", False))
            log("[发送] -> %s  ok=%s  %s" % (who, ok, text[:30]))
        except Exception as e:
            log("[发送异常] -> %s: %s" % (who, e))


# ---------- 消息回调 ----------
def on_message(msg, listener):
    try:
        username = msg.get("username") or ""
        sender_id = msg.get("sender_id")
        mtype = msg.get("type")
        content = (msg.get("content") or "").strip()
        seq = msg.get("sort_seq")

        # 去重：防止同一消息被重复派发
        if seq is not None:
            if seq in _recent_seq:
                return
            _recent_seq.append(seq)

        if sender_id == 2:            # 自己发的，忽略，避免死循环
            return
        if mtype not in ("文本", "text"):   # 库返回的中文类型名是「文本」
            return
        # 群聊消息内容形如 "wxid_xxx:\n正文"，去掉发送者前缀
        if username.endswith("@chatroom"):
            prefix = str(sender_id) + ":\n"
            if content.startswith(prefix):
                content = content[len(prefix):].strip()
        if not content:
            return
        if not username or not chat_allowed(username):
            return

        log("[收到] %s(%s)：%s" % (display_name(username), sender_id, content[:40]))

        histories[username].append({"role": "user", "content": content})

        reply = generate_reply(username, content)
        if not reply:
            return

        histories[username].append({"role": "assistant", "content": reply})
        send_reply(username, reply)
    except Exception as e:
        log("[处理异常] %s" % e)


# ---------- 主流程 ----------
def main():
    global _db

    log("=" * 56)
    log("微信 4.x 智能聊天机器人 启动中 ...")

    # 1. 连接微信数据库（要求微信已登录且运行中）
    try:
        _db = WeChatDB()
    except Exception as e:
        log("[错误] 无法读取微信数据：%s" % e)
        log("请确认：1) 微信已安装并登录；2) 微信正在运行、未退出。")
        log("（若已登录但仍报错，请先手动打开一次微信客户端再重试。）")
        return 1

    try:
        info = _db.get_self_info()
        log("当前账号：%s" % (info.get("nick_name") or info.get("username")))
    except Exception as e:
        log("[警告] 读取账号信息失败：%s" % e)

    sessions = _db.get_sessions(limit=500)
    log("发现 %d 个会话，开始监听新消息 ..." % len(sessions))

    # 2. 加载水位（避免重启后重复回复）
    wm = {}
    if os.path.isfile(WATERMARK_PATH):
        try:
            with open(WATERMARK_PATH, "r", encoding="utf-8") as f:
                wm = json.load(f)
        except Exception:
            wm = {}

    lst = Listener(_db, interval=cfg["listen_interval"], watermark=wm)
    lst.add_all(on_message, discover=True)

    # 3. 定期保存水位
    stop_evt = threading.Event()

    def save_watermark():
        while not stop_evt.is_set():
            time.sleep(60)
            try:
                with open(WATERMARK_PATH, "w", encoding="utf-8") as f:
                    json.dump(lst.watermark, f)
            except Exception:
                pass

    saver = threading.Thread(target=save_watermark, daemon=True)
    saver.start()

    lst.start()
    log("监听已启动。按 Ctrl+C 停止。")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        lst.stop()
        stop_evt.set()
        try:
            with open(WATERMARK_PATH, "w", encoding="utf-8") as f:
                json.dump(lst.watermark, f)
        except Exception:
            pass
        log("已停止。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
