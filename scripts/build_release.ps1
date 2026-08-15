<#
.SYNOPSIS
Собирает Centurio.exe и установщик локально, на Windows.

.DESCRIPTION
Тот же порядок, что и у .github/workflows/release.yml, только на своей
машине: сверить версии, прогнать линтер и тесты, собрать приложение,
подписать его (если подпись настроена), собрать установщик, подписать и
его, посчитать SHA-256.

Проверки идут до сборки намеренно: версия хранится в трёх файлах
(app/__init__.py, pyproject.toml — двумя ключами, installer/centurio.iss),
и разъехавшаяся версия попадает в свойства exe и в запись программы в
реестре, откуда её уже не поправить.

Результат:
  build\windows\Centurio.exe            приложение и его DLL
  installer\Output\CenturioSetup.exe    установщик
  installer\Output\SHA256SUMS.txt       контрольная сумма установщика

Раздавать пользователям следует установщик: `flet build` кладёт рядом с
exe набор библиотек, без которых он не запустится.

.PARAMETER SkipTests
Не запускать ruff и pytest. Для повторной сборки, когда проверки только
что проходили.

.PARAMETER SkipInstaller
Собрать только приложение, без Inno Setup.

.PARAMETER NoClean
Не удалять каталог прошлой сборки. Быстрее, но остатки прошлой сборки
могут доехать до установщика.

.EXAMPLE
.\scripts\build_release.ps1

.EXAMPLE
.\scripts\build_release.ps1 -SkipTests -SkipInstaller
#>
[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$SkipInstaller,
    [switch]$NoClean
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root

function Step([string]$text) {
    Write-Host ""
    Write-Host "==> $text" -ForegroundColor Cyan
}

function Run([string]$what, [scriptblock]$body) {
    & $body
    if ($LASTEXITCODE -ne 0) {
        throw "$what завершился с кодом $LASTEXITCODE"
    }
}

try {
    if (-not $IsWindows -and $env:OS -ne "Windows_NT") {
        throw "сборка возможна только на Windows"
    }

    $version = (python -c "from app import __version__; print(__version__)").Trim()
    Step "Centurio $version"

    if (-not $SkipTests) {
        Step "линтер"
        Run "ruff" { python -m ruff check . }

        # Согласованность версий по трём файлам проверяет
        # test_packaging_metadata — отдельной сверки здесь не нужно.
        Step "тесты"
        $env:CI = "1"
        Run "pytest" { python -m pytest -q }
    }

    if (-not $NoClean) {
        Step "чистка прошлой сборки"
        Remove-Item -Recurse -Force build, installer\Output -ErrorAction SilentlyContinue
    }

    Step "сборка приложения"
    Run "flet build windows" { flet build windows }

    Step "подпись приложения"
    & "$PSScriptRoot\sign.ps1" -Path "build\windows\Centurio.exe"

    if ($SkipInstaller) {
        Step "готово: build\windows\Centurio.exe"
        return
    }

    $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    if (-not (Test-Path $iscc)) {
        Write-Warning "Inno Setup 6 не найден ($iscc) — установщик не собран"
        return
    }

    Step "сборка установщика"
    Run "ISCC" { & $iscc installer\centurio.iss }

    Step "подпись установщика"
    & "$PSScriptRoot\sign.ps1" -Path "installer\Output\CenturioSetup.exe"

    Step "контрольная сумма"
    Get-FileHash installer\Output\CenturioSetup.exe -Algorithm SHA256 |
        ForEach-Object { "$($_.Hash.ToLower())  CenturioSetup.exe" } |
        Tee-Object installer\Output\SHA256SUMS.txt

    Step "готово: installer\Output\CenturioSetup.exe"
}
finally {
    Pop-Location
}
