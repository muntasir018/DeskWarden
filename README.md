# 🛡️ DeskWarden — Take Control of Your PC

![DeskWarden Logo](https://github.com/user-attachments/assets/db1db07c-080c-440a-acd7-feea60f4e218)

> Copyright © 2026 Tahasinur Rahman Muntasir. Licensed under the [MIT License](LICENSE).

> **Your PC. Your rules.**
> Lock any app with a password — just like your phone, but for Windows.

DeskWarden runs silently in the background and intercepts any app you choose the moment it opens — before it even has a chance to load.

No subscriptions. No account. No cloud. Just install and it works.

---

## 📸 Interface Preview

## 📸 Interface Preview

### Control Panel
![Control Panel](https://github.com/user-attachments/assets/66247d91-8c2a-4860-849e-74bde6510603)

### Password Protection
![Lock Screen](https://github.com/user-attachments/assets/60b6d622-0cae-4155-970b-1d7a6de9e56b)

### Access Denied
![Block Notice](https://github.com/user-attachments/assets/8db6e44e-920b-46fe-a564-087c5e95f53b)

---

## 💡 Why DeskWarden?

Ever wished you could lock Chrome, a game, or any app on your PC — the same way you lock apps on your phone?

Windows doesn't have this built-in. Most solutions are either paid, require technical setup, or just hide the window instead of truly blocking the app.

**DeskWarden actually freezes the process** at the kernel level. The app cannot open, cannot run, and cannot be bypassed — until the correct password is entered.

- ✅ Free and open source
- ✅ No technical knowledge needed — one double-click to install
- ✅ Works on any `.exe` — browsers, games, tools, anything
- ✅ Lightweight — no Electron, no heavy runtime, no background bloat

---

## ✨ What It Can Do

- 🔒 **Lock any app with a password** — the app freezes instantly on launch
- 🖥️ **Fullscreen lock screen** — clean, unbypassable, appears in under a second
- 🔁 **Four lock modes** per app — full flexibility:
  - **Ask Always** — password required every single time
  - **Session Once** — ask once, remember until PC restart
  - **Always Block** — permanently blocked, no password option
  - **None** — tracked but unrestricted, switch modes anytime
- 🚫 **Wrong password = app killed** — no way around it
- 🔐 **SHA-256 password hashing** — your password is never stored in plain text
- ⏱️ **Brute-force protection** — locked out after 3 wrong attempts
- 🔄 **Auto-update** — checks for new versions automatically
- 💾 **Backup & Restore** — export and import your entire setup
- 📋 **Security Log** — full history of every unlock and failed attempt
- 🚀 **Starts with Windows** — always running, always protecting

---

## 📦 Installation

> No Python knowledge required. The installer handles everything.

1. Go to the [Releases](https://github.com/muntasir018/DeskWarden/releases) page and download the latest version
2. Extract the zip file anywhere
3. Right-click `install_deskwarden.bat` → **Run as administrator**
4. Done — DeskWarden installs itself, creates shortcuts, and starts automatically

**What the installer does behind the scenes:**
- Detects and installs Python automatically if not found
- Downloads and installs all required packages with a real-time progress bar
- Copies everything to `C:\Program Files\DeskWarden`
- Creates Desktop and Start Menu shortcuts
- Registers itself to start on Windows login
- Launches DeskWarden immediately

---

## 🚀 Getting Started

1. After installation, find the **DeskWarden icon in your system tray** (bottom-right corner)
2. Double-click the desktop shortcut or right-click the tray icon → **Control Panel**
3. Set your master password on first run
4. Click **"Add App"** → select any `.exe` you want to lock
5. Choose a lock mode — that's it

From this point on, DeskWarden runs invisibly and protects your chosen apps every time they open.

---

## 🗑️ Uninstallation

1. Right-click `uninstall_deskwarden.bat` → **Run as administrator**
2. Follow the steps — optionally keep or delete your settings

---

## ⚠️ Known Limitations

- Games with **kernel-level anti-cheat** (EAC, BattlEye) may resist process suspension
- Some **UWP / Microsoft Store** apps have non-standard process structures and may not work correctly

---

## 📁 File Locations

| File | Location |
|------|----------|
| Settings | `%APPDATA%\DeskWarden\config.json` |
| Security Log | `%APPDATA%\DeskWarden\security_log.json` |
| Diagnostic Log | `%APPDATA%\DeskWarden\diagnostic_log.txt` |
| Crash Log | `%APPDATA%\DeskWarden\crash_log.txt` |

---

## 🔧 Requirements

- Windows 10 or 11 (64-bit)
- Python 3.10+ *(installer handles this automatically)*

---

## 📄 License

This project is licensed under the MIT License.
You are free to use, modify, and distribute this software.
Attribution to the original author must be preserved in all copies.

> Built with ❤️ by [muntasir018](https://github.com/muntasir018)
