from __future__ import annotations

import json
import ntpath
import os
import re
import subprocess
import sys

from ...infra import log
from .. import win_icons

_JUNK_TOKENS = ("uninstall", "удал", "readme", "read me", "help", "документац",
                "documentation", "release notes", "website", "на сайт", "лиценз",
                "license", "manual", "руководств", "support", "поддержк")

_WIN_NAME_JUNK = ("node.js", "command prompt", "командная строка", "stack builder",
                  "recovery drive", "диск восстановлен", "verifier", "debugger",
                  "redistributable", "runtime", "hotfix", "update for", "sdk ",
                  "web platform", "webview")

_JUNK_NAME_WORDS = frozenset((
    "sdk", "runtime", "redistributable", "redist", "hotfix", "framework",
    "verifier", "debugger", "webview", "webview2", "driver", "drivers",
    "prerequisites", "bootstrapper",
))


_JUNK_DIRS = (
    "\\package cache\\",
    "\\common files\\",
    "\\windows mail\\",
    "\\windowsapps\\",
    "\\microsoft shared\\",
    "\\installer\\",
    "\\assembly\\",
    "\\$recycle.bin\\",
)


_OFFICE_APPS = frozenset((
    "winword.exe", "excel.exe", "powerpnt.exe", "outlook.exe", "msaccess.exe",
    "onenote.exe", "mspub.exe", "visio.exe", "winproj.exe", "lync.exe",
    "teams.exe", "msteams.exe", "groove.exe",
))

_JUNK_EXE_PREFIXES = ("unins", "uninstall", "setup", "install", "remove", "repair")

_JUNK_EXE_PARTS = ("uninstall", "installer", "crashhandler", "crashreport",
                   "crashpad", "vcredist", "vc_redist", "dxsetup", "redist",
                   "prereq", "bootstrap", "elevate", "updater")


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-zа-яё0-9.+]+", (text or "").lower()))


def _looks_like_junk(name: str) -> bool:
    n = name.lower()
    if any(tok in n for tok in _JUNK_TOKENS):
        return True
    return bool(_words(name) & _JUNK_NAME_WORDS)


def _is_junk_target(path: str) -> bool:
    p = (path or "").lower().replace("/", "\\")
    if not p:
        return False
    if any(d in p for d in _JUNK_DIRS):
        return True
    if "\\microsoft office\\" in p and ntpath.basename(p) not in _OFFICE_APPS:
        return True
    base = ntpath.basename(p)
    stem = base[:-4] if base.endswith(".exe") else base
    if stem.startswith(_JUNK_EXE_PREFIXES):
        return True
    return any(part in stem for part in _JUNK_EXE_PARTS)


def _is_windows_system(name: str, path: str) -> bool:
    p = (path or "").lower().replace("/", "\\")
    if "\\windows\\" in f"\\{p}" or p.startswith(os.environ.get("SystemRoot", "c:\\windows").lower()):
        return True
    if _is_junk_target(path):
        return True
    n = (name or "").lower()
    if _looks_like_junk(name) or any(t in n for t in _WIN_NAME_JUNK):
        return True
    return False


# Каталоги, которые для Best-Exe не каталоги установки: искать в них .exe
# бессмысленно и опасно (весь Program Files, весь Windows).
_ROOTISH = frozenset((
    "", "\\", "c:\\", "c:\\program files", "c:\\program files (x86)",
    "c:\\windows", "c:\\users",
))


def _under_windows(exe: str) -> bool:
    return "\\windows\\" in ("\\" + (exe or "").lower().replace("/", "\\"))


def _exes_in(directory: str, depth: int) -> list[str]:
    found: list[str] = []
    try:
        with os.scandir(directory) as it:
            for entry in it:
                try:
                    if entry.is_file() and entry.name.lower().endswith(".exe"):
                        found.append(entry.path)
                    elif depth > 0 and entry.is_dir():
                        found.extend(_exes_in(entry.path, depth - 1))
                except OSError:
                    continue
    except OSError:
        return []
    return found


def _best_exe(directory: str | None, name: str) -> str | None:
    """Самый подходящий .exe в каталоге установки под именем программы.

    Портирует функцию Best-Exe из прежнего PowerShell-скрипта: у записи в
    реестре обычно есть каталог, но не путь к исполняемому файлу. Крупнейший
    .exe, чьё имя перекликается с названием программы; если совпадений нет —
    просто крупнейший. Реестр и localapps теперь обходятся здесь, на Python,
    а не в скрытом процессе PowerShell — перебор Uninstall/App Paths это один
    из recon-признаков, по которым антивирусы придираются к Centurio.
    """
    if not directory:
        return None
    d = directory.strip().strip('"').rstrip("\\")
    if d.lower() in _ROOTISH or not os.path.isdir(d):
        return None
    exes = _exes_in(d, 0) or _exes_in(d, 1)
    if not exes:
        return None

    def _size(path: str) -> int:
        try:
            return os.path.getsize(path)
        except OSError:
            return 0

    ranked = sorted(exes, key=_size, reverse=True)
    toks = [t for t in re.findall(r"[a-z0-9]+", (name or "").lower()) if len(t) >= 3]
    for exe in ranked:
        stem = os.path.splitext(os.path.basename(exe))[0].lower()
        if any(t in stem for t in toks):
            return exe
    return ranked[0]


def _registry_app(display_name, display_icon, install_location) -> dict | None:
    """Запись реестра → карточка программы (или None, если exe не нашёлся)."""
    name = (display_name or "").strip()
    if not name:
        return None
    exe = None
    if display_icon:
        cand = str(display_icon).split(",")[0].strip().strip('"')
        if cand.lower().endswith(".exe") and os.path.isfile(cand):
            exe = cand
    if not exe:
        exe = _best_exe(install_location, name)
    if not exe or _under_windows(exe):
        return None
    return {"name": name, "path": exe, "icon": None, "src": "registry"}


_UNINSTALL_KEYS = (
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
)
_APP_PATHS_KEYS = (
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths",
)


def _registry_entries() -> list[dict]:
    """Программы из Uninstall и App Paths — напрямую через winreg.

    То же, что делал раздел `$uks`/`$aps` старого PowerShell-скрипта, только
    без запуска powershell.exe. `winreg` уже используется в `autostart.py` и
    `steam_paths.py`, так что это штатный путь, а не новая зависимость.
    """
    try:
        import winreg
    except Exception:
        return []

    hives = ((winreg.HKEY_LOCAL_MACHINE, _UNINSTALL_KEYS),
             (winreg.HKEY_CURRENT_USER, (_UNINSTALL_KEYS[0],)))
    out: list[dict] = []
    seen: set[str] = set()

    def _add(rec: dict | None) -> None:
        if rec and rec["path"].lower() not in seen:
            seen.add(rec["path"].lower())
            out.append(rec)

    def _val(key, name):
        try:
            return winreg.QueryValueEx(key, name)[0]
        except OSError:
            return None

    for hive, subkeys in hives:
        for subkey in subkeys:
            try:
                root = winreg.OpenKey(hive, subkey)
            except OSError:
                continue
            with root:
                for i in range(_subkey_count(winreg, root)):
                    try:
                        child = winreg.OpenKey(root, winreg.EnumKey(root, i))
                    except OSError:
                        continue
                    with child:
                        if _val(child, "SystemComponent") == 1:
                            continue
                        _add(_registry_app(_val(child, "DisplayName"),
                                           _val(child, "DisplayIcon"),
                                           _val(child, "InstallLocation")))

    app_hives = ((winreg.HKEY_LOCAL_MACHINE, _APP_PATHS_KEYS),
                 (winreg.HKEY_CURRENT_USER, (_APP_PATHS_KEYS[0],)))
    for hive, subkeys in app_hives:
        for subkey in subkeys:
            try:
                root = winreg.OpenKey(hive, subkey)
            except OSError:
                continue
            with root:
                for i in range(_subkey_count(winreg, root)):
                    try:
                        child = winreg.OpenKey(root, winreg.EnumKey(root, i))
                    except OSError:
                        continue
                    with child:
                        exe = _val(child, "")  # значение по умолчанию — путь к exe
                    if not isinstance(exe, str):
                        continue
                    exe = exe.strip().strip('"')
                    if (exe.lower().endswith(".exe") and os.path.isfile(exe)
                            and not _under_windows(exe)):
                        _add({"name": os.path.splitext(os.path.basename(exe))[0],
                              "path": exe, "icon": None, "src": "registry"})
    return out


def _subkey_count(winreg, key) -> int:
    try:
        return winreg.QueryInfoKey(key)[0]
    except OSError:
        return 0


def _localapps_entries() -> list[dict]:
    """Программы из %LOCALAPPDATA%\\Programs — обход папок, без PowerShell."""
    local = os.environ.get("LOCALAPPDATA")
    base = os.path.join(local, "Programs") if local else ""
    if not base or not os.path.isdir(base):
        return []
    out: list[dict] = []
    try:
        entries = list(os.scandir(base))
    except OSError:
        return []
    for entry in entries:
        try:
            if not entry.is_dir():
                continue
        except OSError:
            continue
        exe = _best_exe(entry.path, entry.name)
        if exe and not _under_windows(exe):
            out.append({"name": entry.name, "path": exe, "icon": None, "src": "localapps"})
    return out

# Здесь больше нет ни `Add-Type -TypeDefinition`, ни `DllImport`: значки из
# exe достаёт `platform/win_icons.py` тем же `PrivateExtractIcons`, только из
# Python через ctypes. Компиляция C# в рантайме с P/Invoke — классика
# offensive tooling, попадающая под AMSI, и один из самых тяжёлых признаков,
# по которым антивирусы принимают Centurio за infostealer. За PowerShell
# осталось то, для чего он действительно нужен: ярлыки меню «Пуск», реестр и
# Get-AppxPackage.
_PS_PRELUDE = r'''
$ErrorActionPreference='SilentlyContinue'
try{[Console]::OutputEncoding=[System.Text.Encoding]::UTF8}catch{}
$OutputEncoding=[System.Text.Encoding]::UTF8
$cache=__CACHE__
function Md5($s){ $m=[System.Security.Cryptography.MD5]::Create(); (($m.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($s.ToLower())))|ForEach-Object{$_.ToString('x2')}) -join '' }
'''

# Запасной путь для одиночного файла — только штатная сборка System.Drawing,
# без компиляции чего-либо. Иконка выйдет мельче, чем даёт PrivateExtractIcons,
# но сюда попадают лишь случаи, когда ctypes-извлечение не отработало.
_PS_FALLBACK_ICON = r'''
Add-Type -AssemblyName System.Drawing
function Save-Icon($exe){
  if(-not $cache){ return $null }
  if(-not (Test-Path -LiteralPath $exe)){ return $null }
  $f=Join-Path $cache ((Md5 $exe)+'_256.png')
  if(Test-Path -LiteralPath $f){ return $f }
  $bmp=$null
  try{ $ic=[System.Drawing.Icon]::ExtractAssociatedIcon($exe); if($ic){ $bmp=$ic.ToBitmap() } }catch{ $bmp=$null }
  if($bmp){ try{ $bmp.Save($f,[System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose(); return $f }catch{} }
  return $null
}
'''

_PS_STORE_FUNCS = r'''
function Resolve-StoreAsset($dir,$rel){
  $full=Join-Path $dir $rel
  if(Test-Path -LiteralPath $full){ return $full }
  $folder=Split-Path $full -Parent
  if(-not (Test-Path -LiteralPath $folder)){ return $null }
  $stem=[System.IO.Path]::GetFileNameWithoutExtension($rel)
  $ext=[System.IO.Path]::GetExtension($rel)
  $found=@(Get-ChildItem -LiteralPath $folder -Filter "$stem*$ext" -File 2>$null)
  if($found.Count -eq 0){ return $null }

  $unplated=@($found | Where-Object { $_.Name -match 'unplated' })
  $pool=if($unplated.Count -gt 0){ $unplated } else { $found }
  $best=$pool | Sort-Object Length -Descending | Select-Object -First 1
  return $best.FullName
}

function Get-LogoAttr($text,$attr){
  $m=[regex]::Match($text,"$attr\s*=\s*`"([^`"]+)`"")
  if($m.Success){ return $m.Groups[1].Value }
  return $null
}
try{ Import-Module Appx -ErrorAction SilentlyContinue -Verbose:$false } catch {}
$script:AllPkgs=$null
function Get-Pkg($family){
  if($null -eq $script:AllPkgs){
    $list=@()
    try{ $list=@(Get-AppxPackage -ErrorAction SilentlyContinue) }catch{ $list=@() }
    if($list.Count -eq 0){
      try{ $list=@(Get-AppxPackage -AllUsers -ErrorAction SilentlyContinue) }catch{ $list=@() }
    }
    $script:AllPkgs=$list
  }
  return $script:AllPkgs | Where-Object { $_.PackageFamilyName -eq $family } | Select-Object -First 1
}
function Save-StoreIcon($family,$appId){
  if(-not $cache -or -not $family){ return [PSCustomObject]@{icon=$null;err='no cache dir'} }
  $f=Join-Path $cache ((Md5 "store:$family!$appId")+'_store.png')
  if(Test-Path -LiteralPath $f){ return [PSCustomObject]@{icon=$f;err=$null} }
  try{
    $pkg=Get-Pkg $family
    if(-not $pkg -or -not $pkg.InstallLocation){
      return [PSCustomObject]@{icon=$null;err='Get-AppxPackage вернул пусто'}
    }
    $manifestPath=Join-Path $pkg.InstallLocation 'AppxManifest.xml'
    if(-not (Test-Path -LiteralPath $manifestPath)){
      return [PSCustomObject]@{icon=$null;err="нет доступа к $manifestPath"}
    }
    $text=Get-Content -LiteralPath $manifestPath -Raw
    $logoRel=$null
    if($appId){
      $esc=[regex]::Escape($appId)
      $block=[regex]::Match($text,"<Application[^>]*Id=`"$esc`"[^>]*>.*?</Application>",
                            [System.Text.RegularExpressions.RegexOptions]::Singleline -bor
                            [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
      if($block.Success){
        $logoRel=Get-LogoAttr $block.Value 'Square150x150Logo'
        if(-not $logoRel){ $logoRel=Get-LogoAttr $block.Value 'Square44x44Logo' }
      }
    }
    if(-not $logoRel){ $logoRel=Get-LogoAttr $text 'Square150x150Logo' }
    if(-not $logoRel){ $logoRel=Get-LogoAttr $text 'Square44x44Logo' }
    if(-not $logoRel){
      $m=[regex]::Match($text,'<Logo>([^<]+)</Logo>')
      if($m.Success){ $logoRel=$m.Groups[1].Value }
    }
    if(-not $logoRel){ return [PSCustomObject]@{icon=$null;err='манифест без Logo/Square*Logo'} }
    $src=Resolve-StoreAsset $pkg.InstallLocation $logoRel
    if(-not $src){ return [PSCustomObject]@{icon=$null;err="не нашёл файл ассета для $logoRel"} }
    Copy-Item -LiteralPath $src -Destination $f -Force
    return [PSCustomObject]@{icon=$f;err=$null}
  }catch{ return [PSCustomObject]@{icon=$null;err=$_.Exception.Message} }
}
'''

_WIN_PS = _PS_PRELUDE + _PS_STORE_FUNCS + r'''
$sh=New-Object -ComObject WScript.Shell
$out=New-Object System.Collections.ArrayList
function Add-App($n,$p,$s){ if(-not $n -or -not $p){ return }; if($p.ToLower() -like '*\windows\*'){ return }; [void]$out.Add([PSCustomObject]@{name="$n";path="$p";icon=$null;src="$s"}) }
function Add-Store($n,$id){
  if(-not $n -or -not $id){ return }
  $parts=$id -split '!',2
  $family=$parts[0]
  $appId=if($parts.Count -gt 1){ $parts[1] } else { 'App' }
  $r=Save-StoreIcon $family $appId
  [void]$out.Add([PSCustomObject]@{name="$n";path="shell:AppsFolder\$id";icon=$r.icon;src='store';icon_err=$r.err})
}

# Реестр (Uninstall, App Paths) и %LOCALAPPDATA%\Programs обходит Python —
# см. _registry_entries/_localapps_entries. Здесь остаётся только то, чему
# нет чистого нативного пути: ярлыки меню «Пуск» и Store через Get-StartApps.
$menus=@(__DIRS__)
foreach($d in $menus){
  Get-ChildItem -LiteralPath $d -Recurse -Filter *.lnk 2>$null | ForEach-Object {
    $t=$sh.CreateShortcut($_.FullName); $p=$t.TargetPath
    if($p -and $p.ToLower().EndsWith('.exe') -and (Test-Path -LiteralPath $p)){ Add-App $_.BaseName $p 'startmenu' }
  }
}

$sysapp=@('microsoft.windows.','microsoftwindows.','windows.immersivecontrolpanel',
          'microsoft.aad','microsoft.account','microsoft.creddialoghost','microsoft.ecapp',
          'microsoft.lockapp','microsoft.bioenrollment','microsoft.asynctextservice',
          'microsoft.xboxgamecallableui','microsoft.sechealthui')
try{
  Get-StartApps 2>$null | ForEach-Object {
    $id=$_.AppID
    if($id -and $id.Contains('!')){
      $low=$id.ToLower()
      $skip=$false
      foreach($s in $sysapp){ if($low.StartsWith($s)){ $skip=$true } }
      if(-not $skip){ Add-Store $_.Name $id }
    } elseif($id -and $id.ToLower().EndsWith('.lnk') -and (Test-Path -LiteralPath $id)){
      $t=$sh.CreateShortcut($id); $p=$t.TargetPath
      if($p -and $p.ToLower().EndsWith('.exe') -and (Test-Path -LiteralPath $p)){ Add-App $_.Name $p 'startmenu' }
    } elseif($id -and $id.ToLower().EndsWith('.exe') -and (Test-Path -LiteralPath $id)){
      Add-App $_.Name $id 'startmenu'
    }
  }
}catch{}
$out | ConvertTo-Json -Compress
'''

_WIN_ICON_ONE_PS = _PS_PRELUDE + _PS_FALLBACK_ICON + r'''
$r=Save-Icon __EXE__
if($r){ Write-Output $r }
'''

_WIN_STORE_ICON_ONE_PS = _PS_PRELUDE + _PS_STORE_FUNCS + r'''
$r=Save-StoreIcon __FAMILY__ __APPID__
if($r.icon){ Write-Output $r.icon }
'''

_STORE_PATH_RE = re.compile(r"^shell:appsfolder\\([^!]+)(?:!(.*))?$", re.IGNORECASE)

def _powershell_exe() -> str:
    """Полный путь к powershell.exe, а не имя для поиска по PATH.

    Имя резолвится через PATH, и если раньше системного каталога там стоит
    директория, куда пишет непривилегированный процесс (типовая ошибка
    установки инструментов разработчика), подменяется исполняемый файл.

    32-битный процесс на 64-битной Windows видит System32 через
    файловую перенаправку как SysWOW64, поэтому для него нужен `Sysnative`.
    """
    if os.name != "nt":
        return "powershell"
    windir = os.environ.get("windir") or r"C:\Windows"
    tail = ("WindowsPowerShell", "v1.0", "powershell.exe")
    roots = ["System32"] if sys.maxsize > 2**32 else ["Sysnative", "System32"]
    for root in roots:
        candidate = os.path.join(windir, root, *tail)
        if os.path.isfile(candidate):
            return candidate
    return "powershell"


def _run_powershell(script: str, timeout: int = 60):
    return subprocess.run([_powershell_exe(), "-NoProfile", "-NonInteractive", "-Command", script],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, creationflags=0x08000000)

def _ps_literal(value: str | None) -> str:
    if not value:
        return "$null"
    return "'" + value.replace("'", "''") + "'"

def _windows_menu_dirs() -> list[str]:
    prog_data = os.environ.get("ProgramData", r"C:\ProgramData")
    appdata = os.environ.get("APPDATA", "")
    dirs = [os.path.join(prog_data, r"Microsoft\Windows\Start Menu\Programs")]
    if appdata:
        dirs.append(os.path.join(appdata, r"Microsoft\Windows\Start Menu\Programs"))
    return [d for d in dirs if os.path.isdir(d)]


def raw_windows_entries(icon_cache: str | None) -> tuple[list[dict], str, int]:
    dir_list = ",".join(_ps_literal(d) for d in _windows_menu_dirs())
    ps = _WIN_PS.replace("__DIRS__", dir_list).replace("__CACHE__", _ps_literal(icon_cache))
    res = _run_powershell(ps, timeout=90)
    stderr = (res.stderr or "").strip()
    out = (res.stdout or "").strip()
    if not out:
        return [], stderr, res.returncode
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return [], out, res.returncode
    return (data if isinstance(data, list) else [data]), stderr, res.returncode


def trim_transparent_padding(path: str, min_content_ratio: float = 0.85) -> None:
    try:
        from PIL import Image
    except Exception:
        return
    try:
        with Image.open(path) as im:
            im = im.convert("RGBA")
            w, h = im.size
            if not w or not h:
                return
            bbox = im.split()[-1].getbbox()
            if not bbox:
                return
            x0, y0, x1, y1 = bbox
            if (x1 - x0) >= w * min_content_ratio and (y1 - y0) >= h * min_content_ratio:
                return
            pad_x = max(2, round((x1 - x0) * 0.08))
            pad_y = max(2, round((y1 - y0) * 0.08))
            x0, y0 = max(0, x0 - pad_x), max(0, y0 - pad_y)
            x1, y1 = min(w, x1 + pad_x), min(h, y1 + pad_y)
            side = max(x1 - x0, y1 - y0)
            cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
            half = side // 2 + 1
            nx0, ny0 = max(0, cx - half), max(0, cy - half)
            nx1, ny1 = min(w, cx + half), min(h, cy + half)
            im.crop((nx0, ny0, nx1, ny1)).save(path, "PNG")
    except Exception:
        log.exception("не удалось обрезать прозрачные поля у иконки %s", path)


def _discover_windows(icon_cache: str | None) -> list[dict]:
    data, stderr, code = raw_windows_entries(icon_cache)
    if not data and (code != 0 or stderr):
        log.warning("обнаружение программ Windows: пустой вывод PowerShell "
                   "(код %s): %s", code, stderr[:2000])

    # Реестр и папку Programs обходим на Python (winreg + файловая система),
    # а не внутри PowerShell: перебор Uninstall/App Paths — recon-признак,
    # по которому эвристики антивирусов придираются к скрытому процессу. За
    # PowerShell осталось лишь то, чему нет чистого нативного пути: ярлыки
    # меню «Пуск» и Store-приложения (Get-StartApps/Get-AppxPackage). Всё
    # сливается и дедуплицируется по пути в discovery.__init__._dedupe.
    if os.name == "nt":
        data = list(data) + _registry_entries() + _localapps_entries()

    apps = []
    for x in data:
        name, path = x.get("name"), x.get("path")
        if not name or not path or _is_windows_system(name, path):
            continue
        src = (x.get("src") if x.get("src") in ("startmenu", "registry", "store", "localapps")
               else "registry")
        icon = x.get("icon")
        if src == "store":
            if icon:
                trim_transparent_padding(icon)
        elif icon_cache and not icon:
            # Значки достаются здесь, а не внутри PowerShell. Помимо ухода от
            # компиляции C# в рантайме это ещё и меньше работы: до сюда
            # доходят только записи, пережившие отсев мусора, а скрипт
            # извлекал иконку каждой найденной, включая выброшенные следом.
            icon = _win_extract_one(path, icon_cache)
        apps.append({"name": name, "path": path, "icon": icon,
                     "icon_fit": "contain", "source": src,
                     "sub": "Microsoft Store" if src == "store" else ""})
    return apps

def _win_extract_one(path: str, icon_cache: str) -> str | None:
    """Иконка одного файла.

    Через этот вызов идут все одиночные извлечения — Epic, Steam и
    дозаполнение значков, — и раньше каждое поднимало свой процесс PowerShell.
    Холодный старт PowerShell 0.3–1.5 с, так что библиотека из 50 игр без кэша
    давала минуту фоновой работы и 50 порождённых процессов. Теперь тот же
    `PrivateExtractIcons` зовётся из Python через `ctypes`; PowerShell остаётся
    запасным путём на случай, если Win32 или Pillow почему-то не отработали.
    """
    if not path or not icon_cache:
        return None
    out = win_icons.cache_path(path, icon_cache)
    if os.path.exists(out):
        return out
    if win_icons.extract_png(path, out):
        return out

    ps = _WIN_ICON_ONE_PS.replace("__CACHE__", _ps_literal(icon_cache)).replace(
        "__EXE__", _ps_literal(path))
    try:
        res = _run_powershell(ps, timeout=25)
    except Exception:
        log.exception("_win_extract_one powershell fail %s", path)
        return None
    out = (res.stdout or "").strip().splitlines()
    out = out[-1].strip() if out else ""
    return out if out and os.path.exists(out) else None


def store_parts(path: str) -> tuple[str, str] | None:
    m = _STORE_PATH_RE.match((path or "").strip())
    if not m:
        return None
    return m.group(1), (m.group(2) or "App")


def _win_extract_store_one(path: str, icon_cache: str) -> str | None:
    parts = store_parts(path)
    if parts is None:
        return None
    family, app_id = parts
    ps = (_WIN_STORE_ICON_ONE_PS.replace("__CACHE__", _ps_literal(icon_cache))
         .replace("__FAMILY__", _ps_literal(family)).replace("__APPID__", _ps_literal(app_id)))
    try:
        res = _run_powershell(ps, timeout=25)
    except Exception:
        log.exception("_win_extract_store_one powershell fail %s", path)
        return None
    out = (res.stdout or "").strip().splitlines()
    out = out[-1].strip() if out else ""
    return out if out and os.path.exists(out) else None
