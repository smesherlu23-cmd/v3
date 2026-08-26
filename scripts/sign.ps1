<#
.SYNOPSIS
Подписывает файл сертификатом Authenticode, если подпись настроена.

.DESCRIPTION
Единственное, что по-настоящему лечит срабатывания антивирусов на
Centurio, — подпись кода: приложение по составу системных вызовов
(глобальные горячие клавиши, автозапуск, перечисление процессов, работа
с чужими окнами) неизбежно похоже на infostealer, и без подписи эвристики
срабатывают гарантированно. Самые тяжёлые сигналы уже сняты в коде —
клавиатурный хук заменён на RegisterHotKey, автозапуск ушёл на ярлык
«Автозагрузки», извлечение значков и перебор реестра больше не поднимают
скрытый PowerShell, — но суть утилиты (горячие клавиши, автозапуск,
перечисление процессов и окон) остаётся, и её закрывает только подпись.

Пока подпись не оформлена, скрипт печатает предупреждение и завершается
успешно, чтобы сборка оставалась рабочей. Как только появятся секреты,
он начнёт подписывать — менять release.yml для этого не нужно.

С 2023 года по правилам CA/Browser Forum приватный ключ обязан лежать на
аппаратном токене или в облачном HSM, поэтому положить .pfx в секреты
GitHub нельзя. Облачные сервисы подписи (Azure Trusted Signing, SSL.com
eSigner, DigiCert KeyLocker) дают для signtool библиотеку-диспетчер:
signtool вызывает её вместо локального хранилища ключей. Отсюда два
секрета:

  SIGNING_DLIB      путь к этой библиотеке (или команда её установки —
                    см. документацию вашего сервиса)
  SIGNING_METADATA  путь к JSON с параметрами учётной записи подписи

Подписывать нужно и Centurio.exe, и CenturioSetup.exe: скачанный из
браузера неподписанный установщик получает Mark-of-the-Web и отдельный
экран SmartScreen.

.PARAMETER Path
Файл, который нужно подписать.

.PARAMETER TimestampUrl
Сервер меток времени. Метка нужна, чтобы подпись оставалась
действительной после истечения срока самого сертификата.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Path,
    [string]$TimestampUrl = "http://timestamp.acs.microsoft.com"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $Path)) {
    throw "нечего подписывать: $Path не найден"
}

$dlib = $env:SIGNING_DLIB
$metadata = $env:SIGNING_METADATA

if ([string]::IsNullOrWhiteSpace($dlib) -or [string]::IsNullOrWhiteSpace($metadata)) {
    Write-Warning ("подпись не настроена (нет SIGNING_DLIB/SIGNING_METADATA) — " +
                   "$Path остаётся неподписанным, антивирусы и SmartScreen будут ругаться")
    exit 0
}

$signtool = Get-ChildItem -Path "${env:ProgramFiles(x86)}\Windows Kits\10\bin" `
    -Filter signtool.exe -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -like "*\x64\*" } |
    Sort-Object FullName -Descending | Select-Object -First 1

if (-not $signtool) {
    throw "signtool.exe не найден — нужен Windows SDK"
}

& $signtool.FullName sign /v /fd SHA256 /td SHA256 /tr $TimestampUrl `
    /dlib $dlib /dmdf $metadata $Path
if ($LASTEXITCODE -ne 0) {
    throw "signtool завершился с кодом $LASTEXITCODE"
}

& $signtool.FullName verify /pa /v $Path
if ($LASTEXITCODE -ne 0) {
    throw "подпись не прошла проверку"
}
