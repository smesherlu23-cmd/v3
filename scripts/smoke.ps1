<#
.SYNOPSIS
Запускает собранный Centurio.exe и проверяет, что он действительно стартует.

.DESCRIPTION
Сборка, которая компилируется, но не запускается, уже уезжала к
пользователю: «установил, запустил — сразу вылетает». Тесты такого не
видят: они гоняют Python-код напрямую, а ломается склейка Flutter и
встроенного Python, которая существует только в собранном exe.

Скрипт запускает exe, ждёт и собирает всё, что тот успел оставить:

  - журнал запуска centurio-crash.log (его пишет корневой main.py);
  - обычный лог centurio.log (в отладочном режиме, CENTURIO_DEBUG=1);
  - console.log встроенного Python — туда Flet пишет трассировку, если
    упал сам запуск модуля;
  - код выхода и ошибки из журнала приложений Windows.

Запуск считается успешным, если через -Seconds секунд процесс жив,
корневой main.py успел отметиться в журнале запуска и нигде нет
трассировки.

.PARAMETER BuildDir
Каталог сборки (build\windows).

.PARAMETER Seconds
Сколько ждать, прежде чем судить.

.PARAMETER NonAsciiProfile
Сыграть пользователя с кириллицей в имени профиля — у него и AppData, и
каталог установки (%LOCALAPPDATA%\Programs) лежат под C:\Users\<Имя>.
Сборка копируется в каталог с русским именем, а AppData и LocalAppData
перенаправляются туда же — через тот же ключ реестра, по которому их
находит Windows (и Flutter, и Python читают пути оттуда).

Ключ реестра меняется на время прогона и возвращается в finally. На
своей машине этот режим лучше не запускать: пока идёт прогон, другие
программы увидят подменённые папки.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$BuildDir,
    [int]$Seconds = 30,
    [switch]$NonAsciiProfile
)

$ErrorActionPreference = "Stop"

function Section([string]$text) {
    Write-Host ""
    Write-Host "---- $text"
}

# Файл целиком, даже если его держит открытым работающий Centurio
# (faulthandler не отпускает журнал запуска до выхода): File.ReadAllBytes
# просит монопольную запись и падает на таком файле.
function Read-Shared([string]$path) {
    $stream = [System.IO.FileStream]::new($path, [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete)
    try {
        $buffer = [System.IO.MemoryStream]::new()
        $stream.CopyTo($buffer)
        # Запятая: иначе PowerShell развернёт массив байтов в поток объектов.
        return ,$buffer.ToArray()
    } finally {
        $stream.Dispose()
    }
}

# Текст, дописанный в файл после отметки $offset (размера до запуска).
function Read-NewText([string]$path, [long]$offset) {
    if (-not (Test-Path -LiteralPath $path)) { return "" }
    $bytes = Read-Shared $path
    if ($bytes.Length -le $offset) { return "" }
    return [System.Text.Encoding]::UTF8.GetString($bytes, [int]$offset, $bytes.Length - [int]$offset)
}

function Size-Of([string]$path) {
    if (Test-Path -LiteralPath $path) { return (Get-Item -LiteralPath $path).Length }
    return 0
}

$source = (Resolve-Path -LiteralPath $BuildDir).Path
$saved = @{}
$savedEnv = @{
    APPDATA            = $env:APPDATA
    LOCALAPPDATA       = $env:LOCALAPPDATA
    CENTURIO_NO_DIALOG = $env:CENTURIO_NO_DIALOG
    CENTURIO_DEBUG     = $env:CENTURIO_DEBUG
    PYTHONUTF8         = $env:PYTHONUTF8
    PYTHONIOENCODING   = $env:PYTHONIOENCODING
}
$shellFolders = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
$proc = $null
$startedAt = $null
$script:verdict = 1

try {
    $runDir = $source
    if ($NonAsciiProfile) {
        # «Проверка» собрана из кодов символов: скрипт не должен зависеть от
        # того, в какой кодировке его прочтёт PowerShell.
        $cyrillic = -join [char[]](0x41F, 0x440, 0x43E, 0x432, 0x435, 0x440, 0x43A, 0x430)
        $root = Join-Path $env:SystemDrive "$cyrillic Centurio"
        Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
        $runDir = Join-Path $root "Programs\Centurio"
        $roaming = Join-Path $root "AppData\Roaming"
        $local = Join-Path $root "AppData\Local"
        New-Item -ItemType Directory -Force -Path $runDir, $roaming, $local | Out-Null
        Copy-Item -Path (Join-Path $source "*") -Destination $runDir -Recurse -Force

        $key = Get-Item -Path $shellFolders
        foreach ($pair in @(@("AppData", $roaming), @("Local AppData", $local))) {
            # Сырое значение (%USERPROFILE%\...), а не развёрнутое — его и вернём.
            $saved[$pair[0]] = $key.GetValue($pair[0], $null, "DoNotExpandEnvironmentNames")
            Set-ItemProperty -Path $shellFolders -Name $pair[0] -Value $pair[1] -Type ExpandString
        }
        $env:APPDATA = $roaming
        $env:LOCALAPPDATA = $local
    }

    # Без этого сообщение о сбое ушло бы в модальное окно, которое на
    # раннере некому закрыть. С ним — в console.log, где его и читаем.
    $env:CENTURIO_NO_DIALOG = "1"
    $env:CENTURIO_DEBUG = "1"
    # Сборочные переменные раннера (release.yml) до пользователя не доезжают —
    # не должны они и прятать от проверки его поведение.
    Remove-Item -Path Env:PYTHONUTF8, Env:PYTHONIOENCODING -ErrorAction SilentlyContinue

    $exe = Get-ChildItem -LiteralPath $runDir -Filter "centurio.exe" | Select-Object -First 1
    if (-not $exe) { throw "в $runDir нет centurio.exe" }

    $dataDir = Join-Path $env:APPDATA "Centurio"
    $crashLog = Join-Path $dataDir "centurio-crash.log"
    $appLog = Join-Path $dataDir "centurio.log"
    $crashOffset = Size-Of $crashLog
    $appOffset = Size-Of $appLog

    Section "запуск"
    Write-Host "exe:          $($exe.FullName)"
    Write-Host "APPDATA:      $env:APPDATA"
    Write-Host "LOCALAPPDATA: $env:LOCALAPPDATA"

    $startedAt = Get-Date
    $proc = Start-Process -FilePath $exe.FullName -WorkingDirectory $runDir -PassThru
    # Без обращения к Handle сразу после старта PowerShell теряет код выхода.
    $null = $proc.Handle

    $deadline = $startedAt.AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline -and -not $proc.HasExited) {
        Start-Sleep -Milliseconds 500
    }
    $alive = -not $proc.HasExited
    $elapsed = [int]((Get-Date) - $startedAt).TotalSeconds
    if ($alive) {
        $proc.Refresh()
        Write-Host "процесс жив через $elapsed с, окно: '$($proc.MainWindowTitle)'"
    } else {
        $proc.WaitForExit()
        Write-Host "процесс ЗАВЕРШИЛСЯ через $elapsed с, код выхода: $($proc.ExitCode)"
    }

    $crashText = Read-NewText $crashLog $crashOffset
    $appText = Read-NewText $appLog $appOffset

    Section "centurio-crash.log ($crashLog)"
    if ($crashText) { Write-Host $crashText } else { Write-Host "(ничего не записано)" }

    Section "centurio.log ($appLog), последние строки"
    if ($appText) { ($appText -split "`n" | Select-Object -Last 60) -join "`n" | Write-Host }
    else { Write-Host "(ничего не записано)" }

    # console.log лежит в «кэше приложения» Flutter: LocalAppData\<компания>\<продукт>.
    $consoleText = ""
    Section "console.log встроенного Python"
    $consoles = @(Get-ChildItem -LiteralPath (Join-Path $env:LOCALAPPDATA "Centurio"), $dataDir `
            -Recurse -Filter "console.log" -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -ge $startedAt.AddSeconds(-2) })
    if ($consoles.Count -eq 0) { Write-Host "(не найден — Python не дошёл до запуска модуля)" }
    foreach ($c in $consoles) {
        Write-Host "[$($c.FullName)]"
        $text = [System.Text.Encoding]::UTF8.GetString((Read-Shared $c.FullName))
        $consoleText += $text
        ($text -split "`n" | Select-Object -Last 80) -join "`n" | Write-Host
    }

    # Сюда оболочка распаковывает app.zip. Служебным каталогам репозитория
    # в нём не место: .git сборки на раннере несёт в .git/config токен
    # actions/checkout, а tests и кэши — просто лишний вес и лишний повод для
    # эвристик антивирусов. Список исключений — [tool.flet.app] в pyproject.
    Section "распакованное приложение Flet"
    $leaked = @()
    $flet = Get-ChildItem -LiteralPath $dataDir -Recurse -Directory -Filter "flet" -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($flet) {
        $app = Join-Path $flet.FullName "app"
        Write-Host $app
        Get-ChildItem -LiteralPath $app -Force -ErrorAction SilentlyContinue |
            ForEach-Object { Write-Host "  $($_.Name)" }
        $leaked = @(".git", ".github", "tests", "installer", "scripts", ".pytest_cache", ".ruff_cache" |
            Where-Object { Test-Path -LiteralPath (Join-Path $app $_) })
        if ($leaked.Count) { Write-Host "в пакет попали служебные каталоги: $($leaked -join ', ')" }
    } else {
        Write-Host "(не распаковано)"
    }

    Section "журнал приложений Windows"
    $events = @(Get-WinEvent -FilterHashtable @{ LogName = "Application"; StartTime = $startedAt } `
            -ErrorAction SilentlyContinue | Where-Object { $_.Message -match "centurio" })
    if ($events.Count -eq 0) { Write-Host "(нет записей о centurio)" }
    foreach ($e in $events) { Write-Host "$($e.TimeCreated) [$($e.ProviderName) $($e.Id)] $($e.Message)" }

    $booted = $crashText -match "Centurio boot"
    $failure = ($crashText + "`n" + $appText + "`n" + $consoleText) -match "Traceback|Fatal Python error|не удалось запустить"

    Section "итог"
    Write-Host "процесс жив:              $alive"
    Write-Host "main.py отметился:        $booted"
    Write-Host "трассировка/ошибка:       $failure"
    Write-Host "лишнее в пакете:          $($leaked.Count -gt 0)"
    if ($alive -and $booted -and -not $failure -and $leaked.Count -eq 0) {
        Write-Host "OK: Centurio запускается"
        $script:verdict = 0
    } else {
        Write-Host "::error::Centurio не запускается$(if ($NonAsciiProfile) { ' (профиль с кириллицей)' })"
        $script:verdict = 1
    }
}
finally {
    if ($proc -and -not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
    # Добиваем по имени всё, что запустилось за время проверки, — но не
    # чужой Centurio, открытый до неё (на своей машине он может работать).
    if ($startedAt) {
        Get-Process -Name "centurio" -ErrorAction SilentlyContinue |
            Where-Object { $_.StartTime -ge $startedAt } |
            Stop-Process -Force -ErrorAction SilentlyContinue
    }
    foreach ($name in $saved.Keys) {
        Set-ItemProperty -Path $shellFolders -Name $name -Value $saved[$name] -Type ExpandString
    }
    foreach ($name in $savedEnv.Keys) {
        if ($null -eq $savedEnv[$name]) {
            Remove-Item -Path "Env:$name" -ErrorAction SilentlyContinue
        } else {
            Set-Item -Path "Env:$name" -Value $savedEnv[$name]
        }
    }
}

exit $script:verdict
