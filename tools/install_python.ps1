# Python 3.11 을 현재 사용자 폴더에 설치한다 (관리자 권한 불필요, PATH 변경 없음).
#   1) python.org 공식 설치 파일(약 25MB)을 임시 폴더에 받는다
#   2) Authenticode 디지털 서명이 유효하고 서명자가 'Python Software Foundation' 인지 확인한다 — 아니면 실행하지 않고 중단
#   3) 조용히 설치한다
# -VerifyOnly : 내려받아 서명만 확인하고 설치하지 않는다(점검용)
param([switch]$VerifyOnly)

$ErrorActionPreference = 'Stop'
$url = 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe'
$dst = Join-Path $env:TEMP 'gamesfx-python-3.11.9-amd64.exe'
$target = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311'

try {
    Write-Host "Downloading Python 3.11.9 installer from python.org (about 25 MB)..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $url -OutFile $dst -UseBasicParsing

    $sig = Get-AuthenticodeSignature -LiteralPath $dst
    $subject = "$($sig.SignerCertificate.Subject)"
    if ($sig.Status -ne 'Valid' -or $subject -notmatch 'Python Software Foundation') {
        Remove-Item -LiteralPath $dst -Force -ErrorAction SilentlyContinue
        Write-Host "ERROR: the installer's digital signature is not valid ($($sig.Status)). Nothing was installed."
        exit 2
    }
    Write-Host "Signature OK: $subject"
    if ($VerifyOnly) { Remove-Item -LiteralPath $dst -Force; Write-Host "Verify-only: not installing."; exit 0 }

    Write-Host "Installing Python 3.11 for the current user: $target"
    $p = Start-Process -FilePath $dst -Wait -PassThru -ArgumentList @(
        '/quiet', 'InstallAllUsers=0', 'PrependPath=0', 'Include_launcher=0', 'Include_test=0', 'Include_doc=0',
        'Shortcuts=0', "TargetDir=$target")
    Remove-Item -LiteralPath $dst -Force -ErrorAction SilentlyContinue
    if ($p.ExitCode -ne 0 -or -not (Test-Path (Join-Path $target 'python.exe'))) {
        Write-Host "ERROR: Python installer failed (exit code $($p.ExitCode))."
        exit 3
    }
    Write-Host "Python installed."
    exit 0
} catch {
    Write-Host "ERROR: $($_.Exception.Message)"
    exit 1
}
