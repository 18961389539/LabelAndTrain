# -*- mode: python -*-
# vim: ft=python

import os
import re

def _resolve_root_dir():
    env_root = os.environ.get('JLLABELING_ROOT')
    if env_root:
        return os.path.abspath(env_root)

    spec_path = globals().get('SPEC')
    if isinstance(spec_path, str) and spec_path:
        return os.path.abspath(os.path.join(os.path.dirname(spec_path), '..', '..', '..'))

    return os.path.abspath(os.getcwd())

ROOT_DIR = _resolve_root_dir()

def _p(*parts):
    return os.path.join(ROOT_DIR, *parts)

def _load_version():
    app_info_path = _p('jllabeling', 'app_info.py')
    with open(app_info_path, 'r', encoding='utf-8') as f:
        content = f.read()
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
    if not match:
        raise RuntimeError(f"Failed to read __version__ from: {app_info_path}")
    return match.group(1)

__version__ = _load_version()

a = Analysis(
    [_p('jllabeling', 'app.py')],
    pathex=[_p('jllabeling')],
    binaries=[],
    datas=[
        (_p('jllabeling', 'configs', 'auto_labeling', '*.yaml'), 'jllabeling/configs/auto_labeling'),
        (_p('jllabeling', 'configs', '*.yaml'), 'jllabeling/configs'),
        (_p('jllabeling', 'views', 'labeling', 'widgets', 'auto_labeling', 'auto_labeling.ui'), 'jllabeling/views/labeling/widgets/auto_labeling'),
        (_p('jllabeling', 'services', 'auto_labeling', 'configs', 'clip', '*'), 'jllabeling/services/auto_labeling/configs/clip')
    ],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
)
pyz = PYZ(a.pure, a.zipped_data)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name=f'JLLabelingAndTrain-{__version__}-macOS',
    debug=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    icon=_p('jllabeling', 'resources', 'images', 'icon.icns'),
)
app = BUNDLE(
    exe,
    name=f'JLLabelingAndTrain-v{__version__}-macOS.app',
    icon=_p('jllabeling', 'resources', 'images', 'icon.icns'),
    bundle_identifier=None,
    info_plist={'NSHighResolutionCapable': 'True'},
)
