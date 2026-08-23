# 微信 4.x 智能聊天机器人

一个基于 [wechatauto-replica](https://github.com/fanyuantaier/wechatauto-replica)（微信 4.x 本地自动化）
+ DeepSeek / 任意 OpenAI 兼容 API 的个人微信聊天机器人。

- ✅ 支持新版微信 **4.1.12+**（`Weixin.exe`）
- ✅ 只读本地加密数据库接收消息，无需网页协议
- ✅ 自动回复**别人发来的文本消息**，AI 生成内容
- ✅ 每个会话独立上下文（多轮对话记忆）
- ✅ 回复精简、口语化、有"真人感"（人设可在 config 里自定义）

---

## 一、环境要求

| 项目 | 要求 |
|---|---|
| 系统 | Windows 10 / 11 |
| 微信 | 微信 4.x（`Weixin.exe`），已登录、保持运行、**不要锁屏** |
| Python | 3.9 ~ 3.12 |

---

## 二、快速开始

### 1. 安装依赖

```bat
pip install -r requirements.txt
```

> 想装到项目本地目录（不污染系统环境）可改用：
> `pip install --target deps -r requirements.txt`

### 2. 申请 DeepSeek API Key

打开 https://platform.deepseek.com 注册并创建 Key（形如 `sk-xxxx`）。

### 3. 配置

复制模板并填入你的 Key：

```bat
copy config.example.json config.json
```

然后编辑 `config.json`，把 `ai.api_key` 填上即可。

> 想用别的模型（OpenAI / 通义 / Kimi 等），改 `ai.base_url` 和 `ai.model`，只要对方提供 OpenAI 兼容接口即可。

### 4. 启动

登录微信并保持运行、不要锁屏，双击 **`启动机器人.bat`**（或 `python bot.py`）。

看到 `监听已启动` 后，用**另一个微信号**发条文本消息，机器人就会自动回复。

---

## 三、配置说明（config.json）

| 字段 | 说明 |
|---|---|
| `ai.api_key` | DeepSeek 的 API Key（必填，否则进入提示模式） |
| `ai.base_url` | 接口地址，DeepSeek 默认 `https://api.deepseek.com` |
| `ai.model` | 模型名：`deepseek-v4-flash`（快/省，默认）/ `deepseek-v4-pro`（推理型，更强但慢） |
| `ai.system_prompt` | 人设 / 说话风格（默认是"精简有感情的普通人"） |
| `ai.temperature` | 0~2，越大越随性 |
| `bot.max_history` | 每个会话保留的上下文轮数 |
| `bot.allowed_chats` | 白名单（会话 username），空 = 全部；填入则只回这些会话 |
| `bot.blocked_chats` | 黑名单，这些会话不回复 |

---

## 四、常见问题

- **提示"未检测到 Weixin.exe"**：微信没登录/没运行，先打开并登录微信再启动。
- **收到消息不回复**：① 是否锁屏或最小化？发送需要微信窗口可见；② 是否未填 Key？③ 消息必须是**文本**。
- **回复慢**：发送走窗口自动化（UIA+OCR），每条约几秒，属正常。
- **想全部重来**：删掉 `watermark.json`。

---

## ⚠️ 风险与免责声明

个人微信**没有官方机器人接口**，本工具通过本地自动化实现，属于微信用户协议未明确允许的行为，存在**账号被限制或封禁**的风险。请用小号测试、勿高频群发、勿骚扰他人，仅供学习交流，使用后果自负。

## License

[MIT](./LICENSE)
