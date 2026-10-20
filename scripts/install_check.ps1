<#
.SYNOPSIS
Ставит CenturioSetup.exe, запускает установленное, обновляет и удаляет.

.DESCRIPTION
smoke.ps1 запускает каталог сборки, а пользователь получает установщик.
Здесь проверяется путь человека, скачавшего релиз:

  1. Тихая установка с автозапуском: код 0, запись в «Приложениях» с
     нужной версией, ярлыки в меню «Пуск» и в «Автозагрузке».
  2. Установленный Centurio запускается (smoke.ps1 на каталоге установки).
  3. Обновление поверх запущенного Centurio отказывается и ничего не
     трогает: программа живёт в трее, а сообщение о новой версии ведёт
     человека запускать установщик, пока она работает (AppMutex в
     centurio.iss).
  4. Обновление поверх закрытого проходит.
  5. Удаление убирает программу, запись и ярлыки, а библиотеку
     пользователя в %APPDATA%\Centurio оставляет.

Ставит в профиль текущего пользователя, поэтому на своей машине с
установленным Centurio лучше не запускать.

.PARAMETER Setup
Путь к CenturioSetup.exe.

.PARAMETER Version
Версия, которую установщик должен записать в «Приложения».
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Setup,
    [Parameter(Mandatory = $true)][string]$Version
)

$ErrorActionPreference = "Stop"
# Должно совпадать с MUTEX_NAME в app/platform/single_instance.py и с
# AppMutex в installer/centurio.iss (сверяет test_packaging).
$mutexName = "Local\CenturioSingleInstanceMutex"
$script:failed = $false

function Section([string]$text) {
    Write-Host ""
    Write-Host "---- $text"
}

function Check([bool]$condition, [string]$what) {
    if ($condition) {
        Write-Host "ok    $what"
    } else {
        Write-Host "::error::$what"
        $script:failed = $true
    }
}

function Run-Setup([string]$log) {
    # /SUPPRESSMSGBOXES обязателен: без него «Centurio запущен» — окно,
    # которое на раннере некому закрыть.
    $arguments = @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/TASKS=startup", "/LOG=`"$log`"")
    $p = Start-Process -FilePath $setupPath -ArgumentList $arguments -PassThru
    $null = $p.Handle
    if (-not $p.WaitForExit(300000)) {
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        throw "установщик не закончил за 5 минут"
    }
    return $p.ExitCode
}

function Uninstall-Entry {
    Get-ChildItem "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall" -ErrorAction SilentlyContinue |
        Where-Object { $_.PSChildName -like "*_is1" } |
        ForEach-Object { Get-ItemProperty -LiteralPath $_.PSPath } |
        Where-Object { $_.DisplayName -like "Centurio*" } |
        Select-Object -First 1
}

function Wait-Mutex([int]$seconds) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $deadline) {
        $m = $null
        if ([System.Threading.Mutex]::TryOpenExisting($mutexName, [ref]$m)) {
            $m.Dispose()
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Stop-Centurio {
    Get-Process -Name "centurio" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

$setupPath = (Resolve-Path -LiteralPath $Setup).Path
$tmp = [System.IO.Path]::GetTempPath()
$startup = [Environment]::GetFolderPath("Startup")
$programs = [Environment]::GetFolderPath("Programs")
$dataDir = Join-Path $env:APPDATA "Centurio"
$running = $null

try {
    Section "установка"
    $code = Run-Setup (Join-Path $tmp "centurio-install.log")
    Check ($code -eq 0) "установщик завершился с кодом 0 (получен $code)"
    $entry = Uninstall-Entry
    Check ($null -ne $entry) "Centurio появился в «Приложениях»"
    if (-not $entry) { throw "без записи об установке дальше проверять нечего" }
    $installDir = $entry.InstallLocation.TrimEnd("\")
    Write-Host "каталог: $installDir"
    Check ($entry.DisplayVersion -eq $Version) "версия в «Приложениях» — $Version (получена $($entry.DisplayVersion))"
    Check ($entry.URLInfoAbout -like "https://github.com/*") "у записи есть адрес проекта ($($entry.URLInfoAbout))"
    Check (Test-Path -LiteralPath (Join-Path $installDir "Centurio.exe")) "Centurio.exe на месте"
    $menu = @(Get-ChildItem -LiteralPath $programs -Recurse -Filter "Centurio.lnk" -ErrorAction SilentlyContinue)
    Check ($menu.Count -gt 0) "ярлык в меню «Пуск»"
    $autostart = Join-Path $startup "Centurio.lnk"
    Check (Test-Path -LiteralPath $autostart) "ярлык в «Автозагрузке» (задача startup)"
    if (Test-Path -LiteralPath $autostart) {
        $lnk = (New-Object -ComObject WScript.Shell).CreateShortcut($autostart)
        # 7 — «Окно: свёрнутое»: по нему autostart.started_minimized()
        # отправляет Centurio сразу в трей.
        Check ($lnk.WindowStyle -eq 7) "автозапуск открывает Centurio свёрнутым (WindowStyle $($lnk.WindowStyle))"
        Check ([string]::IsNullOrEmpty($lnk.Arguments)) "и без аргументов: собранный exe их не принимает"
    }

    Section "запуск установленного"
    & (Join-Path $PSScriptRoot "smoke.ps1") -BuildDir $installDir
    Check ($LASTEXITCODE -eq 0) "установленный Centurio запускается"
    Stop-Centurio

    Section "обновление поверх запущенного"
    $exe = Join-Path $installDir "Centurio.exe"
    $stamp = (Get-Item -LiteralPath $exe).LastWriteTimeUtc
    $env:CENTURIO_NO_DIALOG = "1"
    $running = Start-Process -FilePath $exe -WorkingDirectory $installDir -PassThru
    Check (Wait-Mutex 90) "запущенный Centurio держит $mutexName"
    $code = Run-Setup (Join-Path $tmp "centurio-upgrade-running.log")
    Check ($code -ne 0) "установщик отказался, пока Centurio запущен (код $code)"
    Check (-not $running.HasExited) "запущенный Centurio не тронут"
    Check ((Get-Item -LiteralPath $exe).LastWriteTimeUtc -eq $stamp) "и его файлы не перезаписаны"
    Stop-Centurio

    Section "обновление поверх закрытого"
    $code = Run-Setup (Join-Path $tmp "centurio-upgrade.log")
    Check ($code -eq 0) "повторная установка прошла (код $code)"
    Check (Test-Path -LiteralPath $exe) "Centurio.exe на месте"

    Section "удаление"
    $hadData = Test-Path -LiteralPath $dataDir
    $uninstaller = Join-Path $installDir "unins000.exe"
    $p = Start-Process -FilePath $uninstaller -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -PassThru
    $null = $p.Handle
    $p.WaitForExit(300000) | Out-Null
    # Первая фаза деинсталлятора ждёт вторую, но каталог Windows может
    # отпустить чуть позже.
    $deadline = (Get-Date).AddSeconds(60)
    while ((Test-Path -LiteralPath $exe) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 1 }
    Check ($p.ExitCode -eq 0) "деинсталлятор завершился с кодом 0 (получен $($p.ExitCode))"
    Check (-not (Test-Path -LiteralPath $exe)) "Centurio.exe удалён"
    Check ($null -eq (Uninstall-Entry)) "записи в «Приложениях» больше нет"
    Check (-not (Test-Path -LiteralPath $autostart)) "ярлыка в «Автозагрузке» нет"
    $menu = @(Get-ChildItem -LiteralPath $programs -Recurse -Filter "Centurio.lnk" -ErrorAction SilentlyContinue)
    Check ($menu.Count -eq 0) "ярлыка в меню «Пуск» нет"
    if ($hadData) {
        Check (Test-Path -LiteralPath $dataDir) "библиотека пользователя ($dataDir) осталась"
    }
}
catch {
    Write-Host "::error::$($_.Exception.Message)"
    $script:failed = $true
}
finally {
    Stop-Centurio
    foreach ($log in "centurio-install.log", "centurio-upgrade-running.log", "centurio-upgrade.log") {
        $path = Join-Path $tmp $log
        if ($script:failed -and (Test-Path -LiteralPath $path)) {
            Section "журнал установщика: $log (последние строки)"
            Get-Content -LiteralPath $path -Tail 40 | Write-Host
        }
    }
}

Section "итог"
if ($script:failed) {
    Write-Host "::error::установщик не прошёл проверку"
    exit 1
}
Write-Host "OK: установка, запуск, обновление и удаление"
exit 0
