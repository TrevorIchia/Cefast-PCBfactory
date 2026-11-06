# PCBForge — instalador universal Windows (F5 — M11, Plano Mestre §17),
# espelho do install.sh. Idempotente: pula o que já existe; roda `doctor` no
# fim (0 🔴 = sucesso).
#
# Fatos oficiais (pesquisados 2026-10-28, docs V2 opencode.ai + winget-pkgs):
#   • OpenCode: gerenciador de pacotes NÃO suportado no Windows → binário
#     standalone https://opencode.ai/update/api/latest/cli/opencode/opencode-windows-x64.zip
#   • KiCad:    winget install -e --id KiCad.KiCad        (NSIS, /S)
#   • Java:     Zulu 25 (JRE) via MSI da API Azul (Freerouting 2.5 = classe 69)
#   • uv:       irm https://astral.sh/uv/install.ps1 | iex
#
# Uso (PowerShell 5.1+, no diretório do projeto):
#   powershell -ExecutionPolicy ByPass -File install.ps1 [-SomenteVerificar]

param(
    [switch]$SomenteVerificar
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$Root = $PSScriptRoot
if (-not (Test-Path "$Root\pcbforge\cli.py")) {
    Write-Host "  ⛔ instalador fora da raiz do PCBForge ($Root)" -ForegroundColor Red
    exit 1
}
Write-Host "  ✅ repositório em $Root"
Write-Host "== PCBForge instalador — Windows =="

$VenvPy = "$Root\.venv\Scripts\python.exe"
New-Item -ItemType Directory -Force -Path "$Root\tools" | Out-Null

function Ok([string]$m)   { Write-Host "  ✅ $m" -ForegroundColor Green }
function Skip([string]$m) { Write-Host "  ⏭  $m (já presente)" }
function Info([string]$m) { Write-Host "  … $m" }
function Fail([string]$m) { Write-Host "  ⛔ $m" -ForegroundColor Red }
# prosseguir? em --SomenteVerificar: reporta falta e devolve $false (pula passo)
function Baixa([string]$m) {
    if ($SomenteVerificar) { Fail "FALTA (só-verificar): $m"; return $false }
    Info "baixando $m…"
    return $true
}
function Add-UserPath([string]$dir) {
    if (-not ($dir -and (Test-Path $dir))) { return }
    $cur = [Environment]::GetEnvironmentVariable("Path", "User")
    if (-not (($cur + ";") -like "*$dir;*")) {
        [Environment]::SetEnvironmentVariable("Path", "$cur;$dir", "User")
    }
    if (-not ($env:Path -like "*$dir*")) { $env:Path = "$env:Path;$dir" }
}

# ————— 1. uv —————
if (Get-Command uv -ErrorAction SilentlyContinue) {
    Skip "uv $((uv --version) -replace 'uv ')"
}
elseif (Baixa "uv") {
    irm https://astral.sh/uv/install.ps1 | iex
    Add-UserPath "$env:USERPROFILE\.local\bin"
}

# ————— 2. Python 3.12 + venv do projeto —————
if ((Test-Path $VenvPy) -and ((& $VenvPy -c "import sys; print(sys.version_info >= (3, 12))") -eq "True")) {
    Skip "venv $(& $VenvPy --version)"
}
elseif (Baixa "venv Python 3.12 (uv)") {
    uv venv "$Root\.venv" --python 3.12
}

# ————— 3. Dependências do venv —————
if (Test-Path $VenvPy) {
    $deps = & $VenvPy -c "import kiutils, click, yaml, fastapi, uvicorn, easyeda2kicad" 2>$null
    if ($LASTEXITCODE -eq 0) { Skip "deps do venv" }
    elseif ((Test-Path "$Root\requirements.txt") -and (Get-Command uv -ErrorAction SilentlyContinue)) {
        if (Baixa "dependências (requirements.txt)") {
            uv pip install --python $VenvPy -r "$Root\requirements.txt"
        }
    }
    else { Fail "deps ausentes — rode: uv pip install --python $VenvPy -r requirements.txt" }
}

# ————— 4. OpenCode CLI (zip standalone oficial; sem winget/npm no Windows) —————
if (Get-Command opencode -ErrorAction SilentlyContinue) {
    Skip "opencode $((opencode --version) 2>$null)"
}
elseif (Baixa "OpenCode CLI (zip standalone x64)") {
    $zip = "$Root\tools\opencode-windows-x64.zip"
    Invoke-WebRequest "https://opencode.ai/update/api/latest/cli/opencode/opencode-windows-x64.zip" -OutFile $zip
    Expand-Archive $zip -DestinationPath "$Root\tools\opencode" -Force
    $exe = Get-ChildItem "$Root\tools\opencode" -Recurse -Filter opencode.exe | Select-Object -First 1
    if ($exe) {
        New-Item -ItemType Directory -Force -Path "$Root\tools\bin" | Out-Null
        Copy-Item $exe.FullName "$Root\tools\bin\opencode.exe" -Force
        Add-UserPath "$Root\tools\bin"
        Ok "opencode.exe em tools\bin (+ PATH do usuário)"
    } else { Fail "opencode.exe não achado dentro do zip — verifique tools\opencode" }
}

# ————— 5. Java ≥ 25 — local tools\ ou PATH, senão MSI Zulu (API Azul) —————
function Get-JavaMajor([string]$javabin) {
    try {
        $out = (& $javabin -version 2>&1 | Out-String)
        if ($out -match '"(\d+)\.') { return [int]$Matches[1] }
    } catch { }
    return -1
}
$javaEx = $null
if (Get-Command java -ErrorAction SilentlyContinue) { $javaEx = "java" }
else {
    $local = Get-ChildItem "$Root\tools" -Recurse -Filter java.exe -ErrorAction SilentlyContinue |
             Where-Object { $_.FullName -like "*bin*java.exe" } | Select-Object -First 1
    if ($local) { $javaEx = $local.FullName }
}
if ($javaEx -and ((Get-JavaMajor $javaEx) -ge 25)) {
    Skip "java $javaEx (≥25)"
}
elseif (Baixa "Java (Zulu 25 JRE, MSI)") {
    $meta = Invoke-RestMethod "https://api.azul.com/metadata/v1/zulu/packages/?java_version=25&os=windows&arch=x64&archive_kind=msi&page=1&page_size=1"
    $url = $meta[0].download_url
    if ($url) {
        $msi = "$Root\tools\zulu25.msi"
        Invoke-WebRequest $url -OutFile $msi
        $proc = Start-Process msiexec.exe -ArgumentList "/i `"$msi`" /quiet /norestart INSTALLDIR=`"$Root\tools\zulu25`"" -Wait -PassThru
        Remove-Item $msi -Force
        if ($proc.ExitCode -eq 0) {
            Ok "Zulu 25 em tools\zulu25"
            Add-UserPath "$Root\tools\zulu25\bin"
        } else { Fail "msiexec saiu $($proc.ExitCode) — MSI pode exigir admin; instale manualmente (§2.2)" }
    } else { Fail "API Azul sem resposta — baixe Zulu 25 manualmente em tools\ (§2.2)" }
}

# ————— 6. KiCad + bibliotecas (~4,8 GB, winget — §2.2 passo 4) —————
$kicadShare = Get-ChildItem "C:\Program Files\KiCad" -Directory -ErrorAction SilentlyContinue |
              Where-Object { Test-Path "$($_.FullName)\share\kicad\symbols" } | Select-Object -First 1
if ($kicadShare) {
    Skip "KiCad ($($kicadShare.FullName))"
}
elseif ($SomenteVerificar) {
    Fail "FALTA: KiCad (símbolos/footprints/3D ~4,8 GB)"
}
elseif (Get-Command winget -ErrorAction SilentlyContinue) {
    Info "instalando KiCad pelo winget (~4,8 GB, DEMORA)…"
    winget install -e --id KiCad.KiCad --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -eq 0) { Ok "KiCad instalado (winget)" }
    else { Fail "winget saiu $LASTEXITCODE — baixa manual: https://www.kicad.org/download/" }
}
else {
    Fail "winget indisponível — baixa manual: https://www.kicad.org/download/windows/"
}

# ————— 7. Freerouting jar —————
$fr = "$Root\tools\freerouting.jar"
if ((Test-Path $fr) -and ((Get-Item $fr).Length -gt 1MB)) {
    Skip "freerouting.jar ($([math]::Round((Get-Item $fr).Length / 1MB)) MB)"
}
elseif (Baixa "freerouting.jar") {
    Invoke-WebRequest "https://github.com/freerouting/freerouting/releases/latest/download/freerouting.jar" -OutFile $fr
    Ok "freerouting.jar baixado"
}

# ————— 8. catalogo.json (censo F1) —————
if ((Test-Path "$Root\pcbforge\config\catalogo.json") -and (Test-Path $VenvPy)) {
    Skip "catalogo.json ($(& $VenvPy -c 'from pcbforge.parts import catalogo; print(len(catalogo.carregar()))' 2>$null) footprints aptos)"
}
elseif ($SomenteVerificar) {
    Fail "FALTA: pcbforge\config\catalogo.json (censo F1)"
}
elseif (Test-Path $VenvPy) {
    Info "gerando catalogo.json (censo, ~1 min)…"
    & $VenvPy "$Root\scripts\censo_footprints.py" --regenerar
}

# ————— 9. Doctor final —————
Write-Host ""
Write-Host "== verificação final: doctor (0 🔴 = sucesso) =="
if (Test-Path $VenvPy) {
    $env:PCBFORGE_ROOT = $Root
    & $VenvPy "$Root\pcbforge\doctor.py"
    if ($LASTEXITCODE -ne 0) { Fail "doctor reprovou — veja itens 🔴 acima" }
} else {
    Fail "doctor indisponível (Python/venv ausente — veja passos acima)"
}

Write-Host ""
Write-Host "pronto: painel web = '$VenvPy -m pcbforge.cli serve' (M9, http://127.0.0.1:8000)"
exit 0
