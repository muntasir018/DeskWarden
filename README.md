# 🛡️ DeskWarden — Windows Application Locker

**DeskWarden** is a background application for Windows that works like a phone app lock — any app you choose will require a password before it opens.

---

## ✨ Features

- 🔒 **Password-protect any app** — lock any `.exe` on your PC
- 🖥️ **Fullscreen lock screen** — appears instantly when a locked app is opened
- 🔁 **Three lock modes** per app:
  - **Ask Always** — asks for password every time the app opens
  - **Session Once** — asks once per session, then remembers until restart
  - **Permanent Block** — always blocks the app, no password option
- 🚫 **Wrong password = app killed** — no way around it
- 🔐 **SHA-256 password hashing** — password never stored in plain text
- ⏱️ **Brute-force protection** — lockout after 3 wrong attempts
- 🔄 **Auto-update** — checks GitHub for new versions automatically
- 💾 **Backup & Restore** — export/import your settings
- 📋 **Security Log** — records every unlock attempt and failed password
- 🚀 **Auto-start on login** — runs silently in the background from startup
- 🖱️ **System tray icon** — lives in the taskbar tray, not the taskbar itself

---

## 🖥️ Requirements

- Windows 10 or 11
- Python 3.12+ (installer handles this automatically)

**Python packages** (installed automatically):
```
psutil
pywin32
Pillow
PyQt6
```

---

## 📦 Installation

1. Download the latest release from the [Releases](https://github.com/muntasir018/DeskWarden/releases) page
2. Extract all files to the same folder
3. Right-click `install_deskwarden.bat` → **Run as administrator**
4. The installer will handle everything automatically:
   - Installs Python if not found
   - Installs all required packages
   - Copies files to `C:\Program Files\DeskWarden`
   - Creates Desktop and Start Menu shortcuts
   - Registers auto-start on login
   - Launches DeskWarden

---

## 🗑️ Uninstallation

1. Right-click `uninstall_deskwarden.bat` → **Run as administrator**
2. Follow the on-screen steps
3. Optionally keep or remove your settings and locked app list

---

## 🚀 How to Use

1. After installation, DeskWarden runs silently in the **system tray** (bottom-right corner)
2. **Right-click** the tray icon → open **Control Panel**
3. Set a master password on first run
4. Click **"Add App"** to add any `.exe` you want to lock
5. Choose a lock mode for each app
6. That's it — DeskWarden monitors all apps in the background

---

## 📁 File Locations

| File | Location |
|------|----------|
| Settings | `%APPDATA%\DeskWarden\config.json` |
| Security Log | `%APPDATA%\DeskWarden\security_log.json` |
| Diagnostic Log | `%APPDATA%\DeskWarden\diagnostic_log.txt` |
| Crash Log | `%APPDATA%\DeskWarden\crash_log.txt` |

---

## ⚠️ Known Limitations

- Games with **anti-cheat** (EAC, BattlEye) may not be interceptable
- Some **UWP / Microsoft Store** apps use different process structures and may not work correctly

---

## 🔄 Auto-Update

DeskWarden checks GitHub for new versions every time you open the Control Panel. If an update is available, a notification will appear with a link to the release page. You can also manually check via **Control Panel → Settings → Check for Update**.

---

## 📄 License

This project is licensed under the **MIT License**.

If you like DeskWarden and want to use it, modify it, or build something new on top of it — go ahead! All I ask is a small credit back to the original author. Just keep my name somewhere in your project, that's it. 🙂

> Built with ❤️ by [muntasir018](https://github.com/muntasir018)
