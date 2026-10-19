# PyInstaller spec for USN. Build with: pyinstaller usn.spec
# Data files are bundled next to the modules that read them (see theme.py, brandable.py, platform_rules.py).
block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("assets", "assets"),
        ("app/i18n/en.json", "app/i18n"),
        ("app/i18n/ar.json", "app/i18n"),
        ("app/core/platform_rules.json", "app/core"),
    ],
    hiddenimports=["pyttsx3", "PIL.ImageTk", "PIL._tkinter_finder"],
    excludes=["pytest"],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="USN",
    console=False,
    windowed=True,
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="USN")
