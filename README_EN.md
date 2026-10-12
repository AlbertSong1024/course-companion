# Course Companion

> A Playwright-based auto-study assistant for online video courses: automatic login, keep videos playing, answer in-video questions, and advance through lessons automatically.
>
> 中文文档：[README.md](README.md)

## What is this

A desktop assistant that hands the repetitive parts of watching online video courses to a program. It drives a real (headed) browser window and mimics human interaction:

- **Auto login** — credentials are filled automatically; the CAPTCHA image pops up automatically, you just type the digits you see, and the script fills it in and submits
- **Keep playing** — resumes paused videos automatically; auto-reloads on "video load error" (progress is stored server-side, nothing is lost)
- **In-video questions** — when a quiz pops up mid-video, the built-in reference answer is read from the page itself and submitted with real mouse events; if no answer can be parsed, it waits for you instead of guessing
- **Lesson advancing** — automatically moves to the next lesson once the required watch time is reached; completed lessons are skipped
- **Jump to first unfinished** — locates the first unfinished lesson directly from the progress page, no need to click through completed ones
- **Session renewal** — cookies are refreshed and saved periodically, so the session rarely expires during long runs

The assistant stops automatically when it reaches exams or assessments that must be completed by the user.

## Requirements

- Windows 10/11 (uses `os.startfile` to open the CAPTCHA image)
- Python 3.9+

## Installation

```bash
pip install playwright
python -m playwright install chromium
```

## Quick start

```bash
python course_companion.py
```

On the first run, 4 dialog boxes appear (one-time only):

| # | Field | Example |
|---|-------|---------|
| 1 | Login account | phone number / student ID |
| 2 | Login password | your password |
| 3 | Platform home URL | `https://xxx.edu.cn/home` |
| 4 | Course list URL | `https://xxx.edu.cn/courses` |

The configuration is saved to `credentials.local.json` (Base64 encoded). Subsequent runs skip login entirely.

## Configuration files

| File | Purpose | Committed |
|------|---------|-----------|
| `credentials.local.json` | account / password / platform URLs (Base64) | ❌ excluded via `.gitignore` |
| `credentials.local.json.example` | template with example values | ✅ |
| `auth.json` | login session cookies (auto-generated) | ❌ excluded via `.gitignore` |

- Changed password or account: delete `credentials.local.json` and run again
- New computer: copy the project, delete `credentials.local.json`, reconfigure

## Notes

1. **Keep the window in the foreground** — some platforms pause timers on background tabs; you may resize the window but do not minimize it
2. **Do not run multiple instances** — most platforms count only one watch session per account
3. **CAPTCHA** — only needed after a session expires (type 4 digits, ~10 seconds); session renewal keeps this rare
4. **Exams** — the assistant stops and hands over to you

## How it works

- Playwright drives Chromium in headed mode; every click is a full, trusted mouse-event sequence
- In-video quiz answers are extracted from the page's own embedded script via a multi-strategy parser
- Page state (progress text / playback state / dialogs) is polled every 20 seconds
- The session persists via Playwright `storage_state`, renewed after each completed lesson

## Disclaimer

This project is for learning and personal productivity only. Read and follow the terms of service of the platform you use; you are responsible for your own account. Do not use it for commercial proxy-learning services.

## License

MIT
