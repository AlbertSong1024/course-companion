<div align="center">

# 🎬 Course Companion

**Hand the most tedious clicking of online video courses to a browser that actually behaves.**

[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Playwright](https://img.shields.io/badge/Powered_by-Playwright-2EAD33?logo=playwright&logoColor=white)](https://playwright.dev/python/)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-0078D6?logo=windows11&logoColor=white)](https://www.microsoft.com/windows)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

*You keep the window in the foreground. It handles everything else.*

[中文文档](README.md) · [English](#-features)

</div>

---

## 🎯 Features

A 30-credit online course means 32 videos of: press play, wait for the pop-up quiz, answer it, click next… **With this companion, the only thing left for you is keeping the browser window on screen.**

| 🎁 Capability | ✨ Experience |
|---------------|---------------|
| 🔐 **Auto login** | Credentials filled automatically; the CAPTCHA image pops up — just type 4 digits and it submits for you |
| ▶️ **Keep playing** | Paused? Auto-resumed. "Load error"? Auto-reloaded. Progress lives server-side, nothing lost |
| 💬 **In-video questions** | The moment a quiz pops up, the page's built-in reference answer is read and submitted (**no LLM needed**); if parsing fails it waits for you — never guesses |
| 📝 **Final assessment** | Answered by an **LLM reading the live paper** then auto-submitted (papers differ per account); without an LLM configured the run pauses and tells you — see [Assessment rules](#-assessment-rules-llm-required) |
| ✅ **Post-submit check** | After submitting, the progress page is verified: completed activities, progress %, score vs. pass line |
| ⏭️ **Lesson advancing** | Auto-jumps to the next lesson when time is met; completed lessons are skipped instantly |
| 🎯 **Jump to first unfinished** | No clicking through lessons — lands directly on the first unfinished one via the progress page |
| 🔄 **Session renewal** | Cookies refreshed periodically; long runs almost never expire — and if they do, auto re-login kicks in |

## 🚀 Download & run (recommended)

No Python environment needed — pick either asset from [Releases · v1.0.0](https://github.com/AlbertSong1024/course-companion/releases/tag/v1.0.0):

| Build | Who it's for | What to do |
|-------|--------------|------------|
| 🚀 **Portable zip** (375 MB) | **Preferred** | Unzip anywhere → double-click `course_companion\course_companion.exe`; **browser kernel is bundled — no first-run download**, straight to the login window |
| 📄 Single exe (68 MB) | Wants one file | Double-click; first run downloads the Chromium kernel automatically (~1-2 min, progress shown in the in-app log pane, auto-retries 3× on weak networks) |

- First run prompts once for account/password (saved locally, no re-login afterwards); **"⚙ LLM settings"** in the window is always available — see [Assessment rules](#-assessment-rules-llm-required).
- **No credentials/session files** are shipped in either package. Logs: in-app pane + `run.log` next to the program.
- Windows is the primary platform; build for macOS/Linux yourself with `python build_exe.py` on that platform.

### ⚠️ Browser warns the exe "may be risky"

**Normal for an unsigned exe — it doesn't mean the file is bad.** This project has no code-signing certificate, so browsers/SmartScreen/AV mark a fresh PyInstaller onefile build as "uncommon"; the warning fades as reputation builds.

To check integrity, **compare the hash, not the warning** (a `course_companion.exe.sha256` ships with the release):

```bat
certutil -hashfile course_companion.exe SHA256
```

It must match the `.sha256` file (v1.0.0 current: `acd244bc936d4c63ae81d9eb53f4c1cc9deb927a777767c0273dcaf25d337ce7`).

| Where it's blocked | What to do |
|--------------------|------------|
| Edge download bar | `⋯` → **Keep** |
| Chrome downloads | the file → **Keep** |
| SmartScreen on launch | **More info → Run anyway** |
| "blocked as unsafe" | exe → right-click → Properties → check **Unblock** → OK |
| AV heuristic flag | Add to whitelist/exceptions (PyInstaller self-extraction trips heuristics) |

> Running from source avoids signing warnings entirely; or clone and build with `python build_exe.py`.

## ⚙️ How it works

```text
Auto login
  ↓
🎯 Progress page → jump to first unfinished lesson
  ↓
🔁 Poll every 20s (loop)
  ├─ Quiz pops    → 📖 read built-in answer, real mouse clicks → keep polling
  ├─ Video paused → ▶️ resume playing                          → keep polling
  ├─ Load error   → 🔄 reload (progress is server-side)        → keep polling
  └─ Time met     → ⏭️ next lesson → back to "jump to first"
  ↓
📝 Final assessment (only place an LLM is required)
  ├─ LLM configured → extract live paper → answer each → auto-submit ┐
  └─ No LLM         → pause, prompt to configure / wait (10 min)      │
                                              ↓
                    ✅ Progress page check: completed / progress / score
                                              ↓
                                        🎓 Course finished
```

- **Real browser events** — Playwright drives Chromium in headed mode; every click is a full mouse press-release sequence, indistinguishable from a human
- **Multi-strategy answer parsing** — the page's embedded script obfuscates some characters; three anchor strategies extract answers reliably
- **Session persistence** — cookies saved via Playwright `storage_state`, renewed after every completed lesson
- **Course wrap-up** — after submitting, the progress page is checked against the pass line (100% progress & score ≥ 60)

## 📝 Assessment rules (LLM required)

> ⚠️ **Only the final assessment needs an LLM** — watching videos and in-video quizzes never touch it. Papers differ per account, so without an LLM the assessment **does not answer and does not submit** (the log tells you; saving a config takes over automatically).

**Why:** each account's paper may differ, so a static answer sheet can't be reused. On reaching the assessment page the tool **extracts this paper's stems + options live** and sends them to the LLM (falls back to local `questions.json` with a warning only if extraction fails).

- **LLM configured:** answers every question and submits **only when all are answered**; if the LLM is unsure on a question it leaves it blank and retries — never borrows answers from another paper.
- **No LLM:** no answering, no submitting — polls every 20s; click **"⚙ LLM settings"** in the window and save, and it takes over (no restart), or finish manually in the browser; cap 10 minutes.
- **`answers.json`** is the *answer record* for this paper (auto-written after answering, for your review) — not the answering source.

### 🔧 Two ways to configure (shared `llm.local.json`, live effect)

- **GUI (recommended):** the ever-present **"⚙ LLM settings"** button — fill base_url / model / api_key, save, effective immediately; "Clear" reverts to not-configured. The status bar shows enabled/disabled live.
- **Source mode (`course_companion.py`):** on every start it asks whether to configure — skip freely for plain watching.

Or edit `llm.local.json` directly:

```json
{
  "base_url": "https://api.deepseek.com",
  "api_key":  "sk-xxxxxxxx",
  "model":    "deepseek-chat"
}
```

- Zero extra dependencies: plain `urllib`, works with any OpenAI-compatible `/chat/completions` (DeepSeek, local vLLM/Ollama, …).
- Placeholder keys (containing `PASTE`) count as unconfigured.

> ⚠️ LLM answers can still be wrong: after submitting the tool checks the score on the progress page — if failed, review `answers.json` manually.

## 📌 Notes

1. 🖥️ **Keep the window foreground** — resizing is fine, minimizing is not. Some platforms pause timers on background tabs
2. 🚫 **No multiple instances** — most platforms count only one watch session per account
3. 🔢 **CAPTCHA** — only appears after a session expires (~10 seconds of typing); session renewal keeps it rare
4. 🪪 **Unified passport** — if the account hasn't bound the unified passport, the platform shows a blocking dialog; the tool logs "bind the passport first, then use this tool" and stops (screenshot saved as `passport_required.png`)
5. 🤖 **Configure an LLM before the assessment** — see above; runtime files (`answers.json`, `run.log`, …) are generated automatically

## 🛠️ Building (for distributors)

```bash
pip install pyinstaller playwright pillow   # build machine deps
python build_exe.py                         # dist/course_companion[.exe] (~68 MB, kernel not included)
```

- PyInstaller **onefile** + `--noconsole`: no black console, logs go to the in-app pane and `run.log`;
- Entry point `course_companion_gui.py`: kernel self-check/download → GUI login window → full flow;
- `questions.json` ships with builds (assessment fallback source; `answers.json` is each user's record and is not distributed);
- Three platforms: run the build once per machine and attach artifacts + SHA256 to the GitHub Release.

## 📄 Disclaimer

This project is for **learning and personal productivity** only. Read and follow the terms of service of the platform you use; you are responsible for your own account. Do not use it for commercial proxy-learning services.

## 📜 License

[MIT](LICENSE) © 2026
