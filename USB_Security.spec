# Build on Windows with:  py -m PyInstaller USB_Security.spec
a = Analysis(['USB_Security.py'], pathex=['.'], binaries=[], datas=[],
             hiddenimports=['usb_security.device.windows'],
             hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=['pytest'],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='USB_Security',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=True,
          console=False, disable_windowed_traceback=False, argv_emulation=False,
          target_arch=None, codesign_identity=None, entitlements_file=None)
