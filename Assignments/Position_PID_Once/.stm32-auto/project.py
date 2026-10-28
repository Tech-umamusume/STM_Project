"""STM32 F103 tutorial project adapter. Requires EIDE's bundled Python + PyYAML."""
import argparse
import copy
import datetime
import fnmatch
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid
import yaml

EXTS = {'.c', '.cpp', '.cc', '.cxx', '.s', '.asm', '.o', '.obj', '.a', '.lib'}
GUARD = 'STM32 AutoProject preflight'

def read(path):
    with open(str(path), encoding='utf-8-sig') as f:
        text = f.read()
        try:
            return json.loads(text)
        except ValueError:
            return yaml.safe_load(text)

def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.auto-tmp')
    with open(str(tmp), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write('\n')
    os.replace(str(tmp), str(path))

def inside(root, rel):
    p = (root / rel).resolve()
    try:
        p.relative_to(root)
    except ValueError:
        raise ValueError('Path escapes project: ' + str(rel))
    if not p.exists():
        raise ValueError('Missing file/directory: ' + str(rel))
    return p

def model(root):
    text = (root / 'Makefile').read_text(encoding='utf-8-sig')
    text = re.sub(r'\\\r?\n', ' ', text)
    variables = dict(re.findall(r'^([A-Z_]+)[ \t]*=[ \t]*([^\r\n]*)', text, re.M))
    for k in ('TARGET', 'CPU', 'C_SOURCES', 'ASM_SOURCES', 'C_INCLUDES', 'C_DEFS', 'LDSCRIPT'):
        if k not in variables:
            raise ValueError('Unsupported Makefile; missing ' + k)
    if variables['CPU'].strip() != '-mcpu=cortex-m3':
        raise ValueError('Only STM32F103 / Cortex-M3 is supported.')
    name = variables['TARGET'].strip()
    if not re.match(r'^[A-Za-z][A-Za-z0-9_]{0,63}$', name):
        raise ValueError('Unsupported TARGET: ' + name)
    src = []
    for k in ('C_SOURCES', 'ASM_SOURCES', 'ASMM_SOURCES'):
        src.extend(variables.get(k, '').split())
    inc = [x[2:] for x in variables['C_INCLUDES'].split() if x.startswith('-I')]
    defs = [x[2:] for x in variables['C_DEFS'].split() if x.startswith('-D')]
    if not any(x.startswith('STM32F103') for x in defs):
        raise ValueError('Expected STM32F103 device define.')
    ld = variables['LDSCRIPT'].strip()
    for p in src + inc + [ld]:
        if '$' in p:
            raise ValueError('Unsupported Makefile expression: ' + p)
        inside(root, p)
    return dict(name=name, sources=src, includes=inc, defines=defs, linker=ld)

def norm(p):
    return str(p).replace('\\', '/').rstrip('/')

def extension():
    base = Path(os.environ['USERPROFILE']) / '.vscode/extensions'
    candidates = []
    for p in base.glob('cl.eide-*'):
        if (p / 'res/tools/win32/unify_builder/unify_builder.exe').is_file():
            version = read(p / 'package.json')['version']
            candidates.append((tuple(int(n) for n in re.findall(r'\d+', version)), p))
    if not candidates:
        raise ValueError('EIDE extension not found. Install/initialize EIDE first.')
    return max(candidates)[1]

def virtual(folder):
    result = [x['path'] for x in folder.get('files', [])]
    for child in folder.get('folders', []):
        result.extend(virtual(child))
    return result

def excluded(path, rules):
    path = norm(path)
    for rule in rules:
        rule = norm(rule)
        if rule.startswith('<virtual_root>'):
            raise ValueError('Virtual-folder exclusions need EIDE-native build; use physical path exclusions with this adapter.')
        if path == rule or path.startswith(rule + '/') or fnmatch.fnmatchcase(path, rule):
            return True
    return False

def collect(root, e, m):
    t = e['targets']['Debug']
    if t['toolchain'] != 'GCC' or e['type'] != 'ARM':
        raise ValueError('Expected ARM / GCC Debug target.')
    if e.get('dependenceList') or e.get('packDir'):
        raise ValueError('Pack/dependency projects require EIDE-native configuration; unsupported by this tutorial adapter.')
    sources = set()
    headers = set()
    rules = t.get('excludeList', [])
    for folder in e.get('srcDirs', []):
        parent = inside(root, folder)
        for p in parent.rglob('*'):
            if p.is_symlink():
                raise ValueError('Symlink not supported: ' + str(p))
            if not p.is_file():
                continue
            inside(root, p.relative_to(root))
            rel = p.relative_to(root).as_posix()
            if excluded(rel, rules):
                continue
            if p.suffix.lower() in EXTS:
                sources.add(rel)
            if p.suffix.lower() in ('.h', '.hpp'):
                headers.add(p.parent.relative_to(root).as_posix())
    for rel in virtual(e['virtualFolder']):
        p = inside(root, rel)
        if p.suffix.lower() in EXTS and not excluded(rel, rules):
            sources.add(norm(rel))
    missing = sorted(set(m['sources']) - sources)
    if missing:
        raise ValueError('Generated sources missing/excluded from EIDE: ' + ', '.join(missing))
    # Full copied CMSIS/HAL test libraries caused the original classroom failure.
    extras = sorted(p for p in sources if p.startswith('Drivers/') and p not in m['sources'])
    if extras:
        raise ValueError('Unexpected driver/test sources (not in CubeMX Makefile): ' + ', '.join(extras[:8]) + '. Keep Copy only necessary libraries; back up/clean residual libraries explicitly.')
    a = t['cppPreprocessAttrs']
    if not set(m['defines']).issubset(set(a['defineList'])):
        raise ValueError('CubeMX device defines changed; run menu 2 to refresh.')
    g = t['toolchainConfigMap']['GCC']
    if g['cpuType'] != 'Cortex-M3' or norm(g['scatterFilePath']) != norm(m['linker']):
        raise ValueError('CPU/linker configuration differs from CubeMX; run menu 2.')
    includes = list(dict.fromkeys(a['incList'] + m['includes'] + sorted(headers)))
    for p in includes:
        inside(root, p)
    return sorted(sources), includes

def configure(root, package, settings, check=False):
    m = model(root)
    old = root / '.eide/eide.yml'
    state = root / '.stm32-auto/state.json'
    if old.exists() and not state.exists():
        raise ValueError('Existing non-script EIDE project: automatic takeover is disabled.')
    e = read(old if old.exists() else package / 'templates/eide.json')
    if set(e['targets']) != {'Debug'}:
        raise ValueError('Multiple targets: merge manually; no configuration was changed.')
    e['name'] = m['name']
    e['miscInfo']['uid'] = (e['miscInfo'].get('uid') if old.exists() else None) or uuid.uuid4().hex
    e['srcDirs'] = list(dict.fromkeys(e.get('srcDirs', []) + ['Core', 'Drivers']))
    # Remove obsolete snapshot entries covered by physical directories, keep user extras.
    def prune(folder):
        folder['files'] = [x for x in folder.get('files', []) if not norm(x['path']).startswith(('Core/', 'Drivers/'))]
        for sub in folder.get('folders', []):
            prune(sub)
    prune(e['virtualFolder'])
    known = virtual(e['virtualFolder'])
    for p in m['sources']:
        if not p.startswith(('Core/', 'Drivers/')) and p not in known:
            e['virtualFolder']['files'].append({'path': p})
    t = e['targets']['Debug']
    a = t['cppPreprocessAttrs']
    a['defineList'] = list(dict.fromkeys(a['defineList'] + m['defines']))
    a['incList'] = list(dict.fromkeys(a['incList'] + m['includes']))
    g = t['toolchainConfigMap']['GCC']
    g['scatterFilePath'] = m['linker']
    g['options']['beforeBuildTasks'] = [x for x in g['options'].get('beforeBuildTasks', []) if x.get('name') != GUARD]
    guard = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "${ProjectRoot}/.stm32-auto/Build.ps1" -ProjectPath "${ProjectRoot}" -Check'
    g['options']['beforeBuildTasks'].insert(0, dict(name=GUARD, command=guard, stopBuildAfterFailed=True))
    if not old.exists() and settings.get('FloatPrintf'):
        g['options']['linker']['LD_FLAGS'] = '-u _printf_float'
    sources, _ = collect(root, e, m)
    files = {'.eide/eide.yml': e}
    wpath = root / (m['name'] + '.code-workspace')
    w = read(wpath) if wpath.exists() else {'folders': [{'path': '.'}], 'settings': {}}
    w.setdefault('settings', {}).update({
        'EIDE.ARM.GCC.InstallDirectory': str(Path(settings['Gcc']).parent.parent),
        'EIDE.ARM.GCC.Prefix': 'arm-none-eabi-',
        'EIDE.SourceTree.AutoSearchIncludePath': True,
        'EIDE.SourceTree.AutoSearchObjFile': True,
        'C_Cpp.default.configurationProvider': 'cl.eide',
        'git.path': settings['Git'], 'debug.onTaskErrors': 'abort'})
    files[wpath.name] = w
    def merge_list(path, key, new, identity):
        p = root / path
        obj = read(p) if p.exists() else {'version': '0.2.0' if key == 'configurations' else '2.0.0', key: []}
        items = obj.setdefault(key, [])
        index = next((i for i, x in enumerate(items) if x.get(identity) == new[identity]), None)
        if index is None:
            items.append(new)
        else:
            items[index].update(new)
        files[path] = obj
    merge_list('.vscode/tasks.json', 'tasks', {
        'label': 'STM32: Build', 'type': 'process', 'command': 'powershell.exe',
        'args': ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', '${workspaceFolder}/.stm32-auto/Build.ps1', '-ProjectPath', '${workspaceFolder}'],
        'group': {'kind': 'build', 'isDefault': True}, 'problemMatcher': ['$gcc']}, 'label')
    merge_list('.vscode/launch.json', 'configurations', {
        'name': 'STM32: STLink + OpenOCD', 'type': 'cortex-debug', 'request': 'launch',
        'cwd': '${workspaceFolder}', 'executable': '${workspaceFolder}/build/Debug/' + m['name'] + '.elf',
        'servertype': 'openocd', 'configFiles': ['interface/stlink.cfg', 'target/stm32f1x.cfg'],
        'serverpath': settings['OpenOCD'], 'armToolchainPath': str(Path(settings['Gcc']).parent),
        'toolchainPrefix': 'arm-none-eabi', 'runToEntryPoint': 'main', 'preLaunchTask': 'STM32: Build'}, 'name')
    files['.stm32-auto/manifest.json'] = {'Version': 2, 'Gcc': settings['Gcc'], 'Name': m['name']}
    files['.stm32-auto/state.json'] = {'Version': 2, 'Uid': e['miscInfo']['uid']}
    print('PLAN: physical Core + Drivers, {} sources, existing options preserved'.format(len(sources)))
    if check:
        print('CHECK ONLY: no files changed.')
        return
    backup = root / '.stm32-auto/backups' / datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    for rel in list(files) + ['.stm32-auto/Build.ps1', '.stm32-auto/project.py']:
        p = root / rel
        if p.exists():
            dest = backup / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(p), str(dest))
    for rel, obj in files.items():
        write(root / rel, obj)
    for name in ('Build.ps1', 'project.py'):
        shutil.copy2(str(package / name), str(root / '.stm32-auto' / name))
    if not (root / '.gitignore').exists():
        (root / '.gitignore').write_text('/build/\n/.stm32-auto/backups/\n/.stm32-auto/*.log\n', encoding='utf-8')
    if settings.get('InitGit') and not (root / '.git').exists():
        subprocess.check_call([settings['Git'], '-C', str(root), 'init', '--initial-branch=main'])
    print('CONFIGURED. Reopen the .code-workspace after this one-time migration.')

def build(root, check=False):
    m = model(root)
    e = read(root / '.eide/eide.yml')
    sources, includes = collect(root, e, m)
    if check:
        print('PREFLIGHT OK: {} sources, current CubeMX configuration'.format(len(sources)))
        return 0
    config = read(root / '.stm32-auto/manifest.json')
    ext = extension()
    t = e['targets']['Debug']
    g = t['toolchainConfigMap']['GCC']
    if e.get('outDir', 'build') != 'build':
        raise ValueError('Custom output directory requires updating debug configuration; unsupported here.')
    # Explicitly reject per-file flags instead of silently ignoring them.
    perfile = root / '.eide/files.options.yml'
    if perfile.exists():
        fo = read(perfile) or {}
        if any(v for k, v in fo.items() if k != 'version'):
            # EIDE writes empty target sections by default.
            def nonempty(x):
                if isinstance(x, dict): return any(nonempty(v) for v in x.values())
                if isinstance(x, list): return any(nonempty(v) for v in x)
                return bool(x)
            if nonempty({k:v for k,v in fo.items() if k != 'version'}):
                raise ValueError('Per-file compiler options present: use EIDE-native build, or remove these overrides for the F5 adapter.')
    options = copy.deepcopy(g['options'])
    options['beforeBuildTasks'] = [x for x in options.get('beforeBuildTasks', []) if x.get('name') != GUARD]
    options.setdefault('global', {}).update({'toolPrefix': 'arm-none-eabi-', 'microcontroller-cpu': 'cortex-m3', 'microcontroller-fpu': 'cortex-m3', 'microcontroller-float': 'cortex-m3', '$arch-extensions': '', '$clang-arch-extensions': '', '$armlink-arch-extensions': ''})
    options['linker']['link-scatter'] = ['"' + inside(root, g['scatterFilePath']).as_posix() + '"']
    if options['linker'].get('$toolName', 'auto') == 'auto':
        options['linker']['$toolName'] = 'gcc'
    out = root / 'build/Debug'
    out.mkdir(parents=True, exist_ok=True)
    tools = Path(os.environ['USERPROFILE']) / '.eide/bin'
    gcc = Path(config['Gcc'])
    if not gcc.is_file():
        raise ValueError('GCC not found; run menu 2 with updated settings.json.')
    params = dict(name=m['name'], target='Debug', toolchain='GCC', toolchainLocation=str(gcc.parent.parent),
        toolchainCfgFile=str(ext / 'res/data/models/arm.gcc.model.json'), buildMode='fast|multhread',
        showRepathOnLog=True, threadNum=min(os.cpu_count() or 2, 8), rootDir=str(root),
        dumpPath='build/Debug', outDir='build/Debug', incDirs=includes,
        libDirs=t['cppPreprocessAttrs'].get('libList', []), defines=t['cppPreprocessAttrs']['defineList'],
        sourceList=sources, alwaysInBuildSources=[], sourceParams={}, options=options, sysPaths=[])
    params['env'] = dict(workspaceFolder=str(root), workspaceFolderBasename=root.name,
        OutDir=str(out), OutDirRoot='build', OutDirBase='build/Debug', ProjectName=m['name'],
        ConfigName='Debug', ProjectRoot=str(root), ExecutableName=str(out / m['name']), ChipPackDir='', ChipName='',
        SYS_Platform='win32', SYS_DirSep='\\', SYS_DirSeparator='\\', SYS_PathSep=';', SYS_PathSeparator=';', SYS_EOL='\r\n',
        EIDE_BUILDER_DIR=str(ext / 'res/tools/win32/unify_builder'),
        EIDE_MSYS=str(tools / 'builder/msys/bin'), EIDE_PY3_CMD=sys.executable, ToolchainRoot=str(gcc.parent.parent))
    p = out / 'auto-builder.params'
    write(p, params)
    # Both frontends now invoke EIDE's actual compiler engine with EIDE GCC options.
    return subprocess.call([str(ext / 'res/tools/win32/unify_builder/unify_builder.exe'), '-p', str(p), '--no-color'], cwd=str(root))

def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['setup', 'check-setup', 'build', 'check'])
    p.add_argument('root')
    p.add_argument('--package')
    p.add_argument('--settings')
    a = p.parse_args()
    root = Path(a.root).resolve()
    if a.action in ('setup', 'check-setup'):
        configure(root, Path(a.package).resolve(), read(Path(a.settings)), a.action == 'check-setup')
        return 0
    return build(root, a.action == 'check')

if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        sys.exit(1)
