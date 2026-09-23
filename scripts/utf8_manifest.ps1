<#
.SYNOPSIS
Переводит собранный Centurio.exe на кодовую страницу UTF-8 (манифест).

.DESCRIPTION
Встроенный Python в собранном exe запускает плагин serious_python. Пути
к интерпретатору и к программе он передаёт в переменные окружения
(PYTHONHOME, PYTHONPATH) узкими строками в UTF-8 — а Windows читает узкие
строки в «ANSI»-кодировке системы, у русской Windows это cp1251. Пока в
пути только латиница, разницы нет. Стоит в пути оказаться кириллице —
например, в имени пользователя: C:\Users\Роман\AppData\... — пути
превращаются в кракозябры, Python не находит собственную стандартную
библиотеку и закрывает процесс ещё до первой строки нашего кода. Снаружи
это выглядит как «запустил — сразу вылетает», без логов и без записей в
журнале Windows.

Элемент манифеста activeCodePage=UTF-8 (Windows 10 1903+) делает UTF-8
«ANSI»-кодировкой именно этого процесса — и те же байты читаются
правильно. Шаблон `flet build` своего манифеста не даёт настроить,
поэтому он правится в готовом exe штатным mt.exe из Windows SDK. Делать
это нужно ДО подписи: правка ресурса подпись ломает.

.PARAMETER Path
Собранный exe.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Path
)

$ErrorActionPreference = "Stop"

$exe = (Resolve-Path -LiteralPath $Path).Path
$kits = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
$mt = Get-ChildItem -LiteralPath $kits -Recurse -Filter "mt.exe" -ErrorAction SilentlyContinue |
    Where-Object { $_.Directory.Name -eq "x64" } |
    Sort-Object FullName -Descending | Select-Object -First 1
if (-not $mt) { throw "mt.exe не найден в $kits — нужен Windows SDK" }

$work = Join-Path ([System.IO.Path]::GetTempPath()) "centurio-manifest"
New-Item -ItemType Directory -Force -Path $work | Out-Null
$current = Join-Path $work "current.manifest"
$patched = Join-Path $work "patched.manifest"

& $mt.FullName -nologo "-inputresource:$exe;#1" "-out:$current"
if ($LASTEXITCODE -ne 0) { throw "mt.exe не смог прочитать манифест $exe (код $LASTEXITCODE)" }

$v1 = "urn:schemas-microsoft-com:asm.v1"
$v3 = "urn:schemas-microsoft-com:asm.v3"
$ws2019 = "http://schemas.microsoft.com/SMI/2019/WindowsSettings"

[xml]$doc = Get-Content -LiteralPath $current -Raw
$ns = New-Object System.Xml.XmlNamespaceManager($doc.NameTable)
$ns.AddNamespace("v1", $v1)
$ns.AddNamespace("v3", $v3)
$ns.AddNamespace("ws", $ws2019)

$settings = $doc.SelectSingleNode("/v1:assembly/v3:application/v3:windowsSettings", $ns)
if (-not $settings) {
    $application = $doc.SelectSingleNode("/v1:assembly/v3:application", $ns)
    if (-not $application) {
        $application = $doc.CreateElement("application", $v3)
        $doc.DocumentElement.AppendChild($application) | Out-Null
    }
    $settings = $doc.CreateElement("windowsSettings", $v3)
    $application.AppendChild($settings) | Out-Null
}

$acp = $settings.SelectSingleNode("ws:activeCodePage", $ns)
if (-not $acp) {
    $acp = $doc.CreateElement("activeCodePage", $ws2019)
    $settings.AppendChild($acp) | Out-Null
}
$acp.InnerText = "UTF-8"
$doc.Save($patched)

& $mt.FullName -nologo -manifest $patched "-outputresource:$exe;#1"
if ($LASTEXITCODE -ne 0) { throw "mt.exe не смог записать манифест в $exe (код $LASTEXITCODE)" }

# Проверка: читаем манифест обратно из exe, а не верим на слово.
Remove-Item -LiteralPath $current -Force
& $mt.FullName -nologo "-inputresource:$exe;#1" "-out:$current"
$check = Get-Content -LiteralPath $current -Raw
if ($check -notmatch "activeCodePage[^>]*>\s*UTF-8\s*<") {
    throw "манифест $exe после правки не содержит activeCodePage=UTF-8"
}
Write-Host "манифест ${exe}:"
Write-Host $check
