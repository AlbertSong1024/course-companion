<div align="center">

# 🎬 Course Companion · 看课小帮手

**把「看视频课程」里最磨人的重复点击，交给一个懂事的浏览器。**

[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Playwright](https://img.shields.io/badge/Powered_by-Playwright-2EAD33?logo=playwright&logoColor=white)](https://playwright.dev/python/)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-0078D6?logo=windows11&logoColor=white)](https://www.microsoft.com/windows)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

*你负责把窗口放在前台，它负责剩下的一切。*

[中文](#-它能做什么) · [English](README_EN.md)

</div>

---

## 🎯 它能做什么

想象一下：一门 30 学时的在线课程，32 个视频，每个都要点播放、等弹弹题、答题、点下一节……**你只剩下一件事可做：把浏览器窗口留在屏幕上。**

| 🎁 能力 | ✨ 体验 |
|---------|---------|
| 🔐 **自动登录** | 账号密码自动填入；验证码图片自动弹出，你瞄一眼输 4 个数字，剩下交给它 |
| ▶️ **保持播放** | 视频暂停？自动续播。「加载出错」？自动刷新。进度在服务端，一秒不丢 |
| 💬 **课中应答** | 随堂问题弹出的瞬间，读取页面自带的参考答案并作答（**不依赖 LLM**）；解析不到就等你，绝不瞎选 |
| 📝 **考核自动交卷** | LLM **实时读题作答**后自动交卷（每个账号考题可能不同）；没配 LLM 就停下提示你配，详见[考核规则](#-考核环节怎么答必须配置-llm) |
| ✅ **交卷核对** | 交卷后自动到学习进度页核对完成项数、进度百分比、考核成绩与及格线 |
| ⏭️ **课时推进** | 时长一到自动进入下一节；已完成的节「已读跳过」，绝不回头 |
| 🎯 **直达定位** | 不逐节翻找——从学习进度页一步跳到第一个未完成的课时 |
| 🔄 **会话续期** | Cookie 定期续存，挂一下午几乎不掉线；真掉线了自动重连 |

## 📦 下载即用（推荐）

不想配 Python 环境？两个 Release 附件任选：

| 版本 | 适合谁 | 说明 |
|------|--------|------|
| 🚀 **便携版 zip**（375 MB） | **首选** | [下载](https://github.com/AlbertSong1024/course-companion/releases/tag/v1.0.0) → 解压 → 双击 `course_companion\course_companion.exe`；**浏览器内核已内置，首跑 0 下载**直接进登录窗 |
| 📄 单文件 exe（68 MB） | 想要单个文件 | [下载](https://github.com/AlbertSong1024/course-companion/releases/tag/v1.0.0) → 双击；首跑自动走 **npmmirror 国内镜像**下载内核（约 1-2 分钟，进度显示在窗口「运行日志」区，弱网自动重试 3 次并清残留锁；3 次仍失败删掉程序旁 `ms-playwright` 重跑，或设 `PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.playwright.dev` 换官方源） |

- **macOS / Linux**：在对应平台用 `python build_exe.py` 自行构建（产物平台 = 构建机平台）。
- 两个包都**不含任何凭据/会话文件**；运行日志 = 窗口「运行日志」区 + 程序目录 `run.log`。
- 首次弹窗录入账号/密码（之后免登录）；窗口内 **「⚙ LLM 设置」随时可点**（登录前后皆常驻），保存即生效。

### ⚠️ 浏览器提示「exe 存在风险」怎么办

**未签名 exe 的正常现象，不代表文件有问题。** 本项目未购买代码签名证书，浏览器/SmartScreen/杀软会把新发布的 PyInstaller 单文件标记为「不常见」；信誉积累后自动消退。

判断文件有没有被篡改，**看哈希不看提示**（Release 内附 `course_companion.exe.sha256`）：

```bat
certutil -hashfile course_companion.exe SHA256
```

应与 `.sha256` 文件一致（v1.0.0 当前为 `acd244bc936d4c63ae81d9eb53f4c1cc9deb927a777767c0273dcaf25d337ce7`），一致即可放心运行。

| 提示位置 | 操作 |
|---------|------|
| Edge 下载栏 | 点 `⋯` → **仍要保留** |
| Chrome 下载内容 | 该文件 → **保留** |
| 运行时 SmartScreen | **更多信息 → 仍要运行** |
| 运行时「已访问不安全文件」 | exe 右键 → 属性 → 勾选 **解除锁定(Unblock)** → 确定 |
| 国产杀软误报 | 加入白名单/信任区（PyInstaller 自解压行为易被启发式误报） |

> 源码运行不受签名提示影响；介意就克隆仓库自行 `python build_exe.py` 构建。

## 🚀 源码运行（需 Python）

```bash
# ① 安装依赖（国内镜像加速）
pip install playwright pillow -i https://pypi.tuna.tsinghua.edu.cn/simple
python -m playwright install chromium

# ② 运行
python course_companion.py

# ③ 弹窗里填账号和密码（仅此一次），然后去干别的事
```

## ⚙️ 它是怎么工作的

```text
自动登录
  ↓
🎯 进度页直达 → 第一个未完成课时
  ↓
🔁 每 20 秒巡检（循环）
  ├─ 弹题      → 📖 读页面参考答案，真实鼠标点击作答 → 继续巡检
  ├─ 视频暂停  → ▶️ 自动续播                          → 继续巡检
  ├─ 加载出错  → 🔄 自动刷新（进度存服务端，刷新不丢） → 继续巡检
  └─ 时长达标  → ⏭️ 下一课时 → 回到「进度页直达」
  ↓
📝 考核环节（页面出现考核表单 · 仅此处需要 LLM）
  ├─ 已配 LLM → 实时抓题 → 逐题作答 → 自动交卷 ─┐
  └─ 未配 LLM → 不作答不交卷，提示配置/等人工（10 分钟） ┤
                                              ↓
                          ✅ 学习进度页核对：完成项 / 进度 / 成绩
                                              ↓
                                        🎓 课程结束
```

- **真实浏览器事件**：Playwright 有头模式驱动 Chromium，每次点击都是完整的鼠标按下-释放序列，与真人无异
- **多级答案解析**：页面内嵌脚本的参考答案经过特殊字符处理，脚本用三级锚点策略稳定提取
- **会话持久化**：通过 `storage_state` 保存 Cookie，每个课时完成后自动续存
- **课程收尾**：交卷后自动核对学习进度页的完成项数、进度百分比与考核成绩，并对照及格线（进度 100% 且考核 ≥ 60 分）给出结论

## 📝 考核环节怎么答（必须配置 LLM）

> ⚠️ **只有考核需要 LLM**——看视频、课中弹题全程不依赖 LLM。每人考题不同，未配置则考核**不作答、不交卷**（日志会提示，保存配置后自动接管）。

**为什么必须 LLM**：每个账号的考核题目可能不同，固定答案表不能跨卷套用，所以到考核页后**当场抓取**本卷题干+选项发给 LLM 作答（抓取失败才回退本地 `questions.json` 并告警）。

- **已配置 LLM**：逐题作答，**全部答出才自动交卷**；LLM 某题答不出 → 留空等待/重试，绝不拿别的卷的答案乱填；
- **未配置 LLM**：**不作答、不交卷**——每 20 秒轮询，你在窗口里点「⚙ LLM 设置」保存后**自动接管**（无需重启），或你在浏览器人工完成也能接上；上限 10 分钟；
- **`answers.json`** 是「LLM 答题记录」：每次作答自动写回本卷答案（题号 → `ChoiceX` 列表），供交卷后人工复核，**不是**作答依据。格式：`{题号: [ChoiceX, ...]}`，Choice0=A、Choice1=B、…，判断题 Correct/Incorrect。

### 🔧 两种配置方式（共用 `llm.local.json`，实时生效、互相通用）

- **方式一（exe / GUI，推荐）**：登录窗常驻 **「⚙ LLM 设置」**——弹窗填 base_url / model / api_key，点保存立即生效；「清除 LLM 配置」回到未配置。状态栏实时显示「LLM 答题：已启用 / 未启用」。
- **方式二（源码 `course_companion.py`）**：每次启动弹「是否配置 LLM 自动答题？」——纯看视频直接点跳过（不写文件）；要过考核就点确定逐项录入（留空=保持默认）。

不想弹窗就直接编辑 `llm.local.json`：

```json
{
  "base_url": "https://api.deepseek.com",
  "api_key":  "sk-xxxxxxxx",
  "model":    "deepseek-chat"
}
```

- 零新增依赖：纯 `urllib`，兼容任何 OpenAI 格式 `/chat/completions`（DeepSeek、本地 vLLM/Ollama 等，改 `base_url` 即可）；
- 占位符 key（含 `PASTE`）视为未配置，不会静默调用。

> ⚠️ LLM 答案仍可能错：交卷后会自动到「学习进度」页核对考核成绩，不及格时请人工复核 `answers.json` 里 LLM 记录的答案。

## 📌 使用须知

1. 🖥️ **窗口保持前台**——可以缩小，别最小化。部分平台会暂停后台标签的计时（这是平台规则，不是 bug）
2. 🚫 **别多开**——同一账号多设备同时观看，平台只记录其一，两边都白挂
3. 🔢 **验证码**——只在掉线重连时出现，看图输数字约 10 秒；会话续期让它很少来打扰
4. 🪪 **绑定通行证**——账号未绑定统一通行证时，平台会弹窗拦截；程序检测到会提示「请先绑定通行证，之后再使用本工具」并停止（截图存 `passport_required.png`），绑定后重跑即可
5. 🤖 **考核前配好 LLM**——见上方[考核规则](#-考核环节怎么答必须配置-llm)；`answers.json` / `run.log` 等运行时文件由程序自动生成
6. 💡 **换电脑 / 改密码**——拷走项目 → 删掉 `credentials.local.json` → 重新运行配置即可

## 🛠️ 构建可执行文件（给分发者）

```bash
pip install pyinstaller playwright pillow   # 构建机依赖
python build_exe.py                         # 生成 dist/course_companion[.exe]（约 68 MB，不含内核）
```

- PyInstaller **onefile** + `--noconsole`：双击无黑窗，日志进 GUI 日志区与 `run.log`；
- `course_companion_gui.py` 是一键入口：内核自检/下载 → GUI 登录窗 → 全流程；
- 构建产物随附 `questions.json`（考核题面回退源；`answers.json` 是使用者记录，不分发）；
- 三平台分发：三台构建机各跑一次，产物与 SHA256 一并挂到 GitHub Release 即可。

## 📄 免责声明

本项目仅供**学习交流与个人效率提升**。使用前请阅读并遵守你所使用平台的服务条款；因使用本项目产生的一切账号风险由使用者自行承担。请勿将其用于商业代学等用途。

## 📜 License

[MIT](LICENSE) © 2026
