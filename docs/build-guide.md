# Hướng dẫn Build ứng dụng thành EXE

## Phương án 1: PyInstaller (Khuyến nghị)

### Cài đặt

```bash
pip install pyinstaller==6.10.0
```

### Build Portable (thư mục)

```bash
pyinstaller --name "AI-Ebook-Reader" ^
    --windowed ^
    --icon=resources/icon.ico ^
    --add-data "src/presentation/qml;src/presentation/qml" ^
    --add-data "migrations;migrations" ^
    --add-data "alembic.ini;." ^
    --hidden-import PySide6.QtWebEngineQuick ^
    --hidden-import PySide6.QtWebEngineCore ^
    --hidden-import PySide6.QtWebChannel ^
    --collect-all PySide6 ^
    --noconfirm ^
    src/main.py
```

```powershell
pyinstaller `
    --name "AI-Ebook-Reader" `
    --clean `
    --windowed `
    --noconfirm `
    --icon="resources/pdf.ico" `
    --add-data "src/presentation/qml;presentation/qml" `
    --add-data "migrations;migrations" `
    --add-data "alembic.ini;." `
    --collect-all PySide6 `
    --hidden-import PySide6.QtWebEngineQuick `
    --hidden-import PySide6.QtWebEngineCore `
    --hidden-import PySide6.QtWebChannel `
    --hidden-import sqlalchemy.dialects.sqlite `
    --hidden-import logging `
    --hidden-import logging.config `
    --exclude-module tkinter `
    --exclude-module matplotlib `
    --exclude-module numpy `
    src/main.py
```

Output: `dist/AI-Ebook-Reader/` (thư mục portable, chạy `AI-Ebook-Reader.exe`)

### Build Single EXE (Installer-ready)

```bash
pyinstaller --name "AI-Ebook-Reader" ^
    --onefile ^
    --windowed ^
    --icon=resources/icon.ico ^
    --add-data "src/presentation/qml;src/presentation/qml" ^
    --add-data "migrations;migrations" ^
    --add-data "alembic.ini;." ^
    --hidden-import PySide6.QtWebEngineQuick ^
    --hidden-import PySide6.QtWebEngineCore ^
    --hidden-import PySide6.QtWebChannel ^
    --collect-all PySide6 ^
    --noconfirm ^
    src/main.py
```

Output: `dist/AI-Ebook-Reader.exe` (single file ~150-300MB)

> **Lưu ý:** `--onefile` cho PySide6 + WebEngine thường rất lớn (300MB+). Khuyên dùng `--onedir` cho portable.

### PyInstaller Spec file (nâng cao)

Tạo file `ai-ebook-reader.spec`:

```python
# ai-ebook-reader.spec
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# Collect PySide6 data
pyside6_datas, pyside6_binaries, pyside6_hiddenimports = collect_all('PySide6')

a = Analysis(
    ['src/main.py'],
    pathex=['.'],
    binaries=pyside6_binaries,
    datas=[
        ('src/presentation/qml', 'src/presentation/qml'),
        ('migrations', 'migrations'),
        ('alembic.ini', '.'),
    ] + pyside6_datas,
    hiddenimports=[
        'PySide6.QtWebEngineQuick',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebChannel',
        'PySide6.QtQuick',
        'PySide6.QtQml',
    ] + pyside6_hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy'],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AI-Ebook-Reader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window
    icon='resources/icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name='AI-Ebook-Reader',
)
```

Build với spec:
```bash
pyinstaller ai-ebook-reader.spec --noconfirm
```

## Phương án 2: Nuitka (Performance tốt hơn)

```bash
pip install nuitka ordered-set

python -m nuitka ^
    --standalone ^
    --enable-plugin=pyside6 ^
    --windows-disable-console ^
    --windows-icon-from-ico=resources/icon.ico ^
    --include-data-dir=src/presentation/qml=src/presentation/qml ^
    --include-data-dir=migrations=migrations ^
    --include-data-files=alembic.ini=alembic.ini ^
    --output-dir=build ^
    src/main.py
```

## Tạo Installer (Windows)

### Inno Setup (miễn phí)

1. Download Inno Setup: https://jrsoftware.org/isinfo.php
2. Tạo file `installer.iss`:

```iss
[Setup]
AppName=AI Ebook Reader
AppVersion=0.1.0
DefaultDirName={autopf}\AI Ebook Reader
DefaultGroupName=AI Ebook Reader
OutputDir=installer_output
OutputBaseFilename=AI-Ebook-Reader-Setup
Compression=lzma2
SolidCompression=yes
SetupIconFile=resources\icon.ico

[Files]
Source: "dist\AI-Ebook-Reader\*"; DestDir: "{app}"; Flags: recursesubdirs

[Icons]
Name: "{group}\AI Ebook Reader"; Filename: "{app}\AI-Ebook-Reader.exe"
Name: "{commondesktop}\AI Ebook Reader"; Filename: "{app}\AI-Ebook-Reader.exe"

[Run]
Filename: "{app}\AI-Ebook-Reader.exe"; Description: "Launch AI Ebook Reader"; Flags: postinstall nowait
```

3. Build installer:
```bash
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
```

Output: `installer_output/AI-Ebook-Reader-Setup.exe`

## Portable ZIP

```bash
# After PyInstaller build
cd dist
powershell Compress-Archive -Path "AI-Ebook-Reader" -DestinationPath "AI-Ebook-Reader-portable.zip"
```

## Troubleshooting Build

### Missing QtWebEngine

```
ModuleNotFoundError: No module named 'PySide6.QtWebEngineQuick'
```
**Fix:** Thêm `--collect-all PySide6` hoặc explicit hidden imports.

### QML files not found at runtime

```
Failed to load QML — exiting
```
**Fix:** Đảm bảo `--add-data "src/presentation/qml;src/presentation/qml"` đúng path. Trong code, dùng:
```python
import sys
if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
else:
    base_path = os.path.dirname(os.path.abspath(__file__))
```

### EXE quá lớn

- Exclude modules không dùng: `--exclude-module tkinter --exclude-module matplotlib`
- Dùng UPX compression: `--upx-dir=path/to/upx`
- PySide6 WebEngine tự nó ~100-150MB, không thể giảm nhiều

### Anti-virus false positive

PyInstaller exe thường bị AV flag. Solutions:
1. Sign exe với code signing certificate
2. Submit false positive report cho AV vendor
3. Dùng Nuitka thay (ít bị flag hơn)

## CI/CD Build Script

```yaml
# .github/workflows/build.yml
name: Build
on: push
jobs:
  build-windows:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -e . && pip install pyinstaller
      - run: pyinstaller ai-ebook-reader.spec --noconfirm
      - uses: actions/upload-artifact@v4
        with:
          name: AI-Ebook-Reader-Windows
          path: dist/AI-Ebook-Reader/
```

## Kích thước ước tính

| Build type | Kích thước |
|---|---|
| Portable folder | ~250-400MB |
| Single EXE (onefile) | ~300-500MB |
| ZIP compressed | ~100-150MB |
| Installer (Inno Setup) | ~120-160MB |

PySide6 + WebEngine chiếm phần lớn dung lượng. Không có cách giảm đáng kể ngoài UPX compression.
