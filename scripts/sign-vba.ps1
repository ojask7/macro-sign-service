<#
.SYNOPSIS
    Sign an Office macro file (.xlsm, .docm, etc.) using signtool.exe + Office SIP.

.DESCRIPTION
    This script signs a VBA macro file using Microsoft signtool.exe.  When
    Microsoft Office is installed, its SIP (Subject Interface Package) DLLs
    are registered with Windows CryptoAPI, which tells signtool how to embed
    a digital signature inside the VBA project of Office files.

    This is the ONLY method that produces a signature visible under:
      Alt+F11 -> Tools -> Digital Signature in Excel/Word.

    Neither Set-AuthenticodeSignature nor osslsigncode can produce valid
    VBA project signatures - they create Authenticode envelope signatures
    which Office ignores for VBA macro trust decisions.

    Prerequisites:
      - Windows with Microsoft Office installed (provides msosip.dll)
      - Windows SDK (provides signtool.exe)
      - A code-signing PFX certificate

    Generate a PFX certificate:
        python -m cli.macro_sign_cli generate-pfx
    Or download from the service:
        GET /api/v1/snow/certs/{name}/pfx

.PARAMETER File
    Path to the Office macro file to sign (.xlsm, .docm, .pptm, etc.)

.PARAMETER PfxFile
    Path to the PFX/PKCS12 certificate file (.pfx)

.PARAMETER PfxPassword
    Password for the PFX file (empty string if no password)

.PARAMETER HashAlgorithm
    Hash algorithm to use (SHA256, SHA384, SHA512). Default: SHA256

.PARAMETER OutputFile
    Optional output path. If not specified, the file is signed in-place.

.EXAMPLE
    .\sign-vba.ps1 -File "report.xlsm" -PfxFile "certs\default.pfx"

.EXAMPLE
    .\sign-vba.ps1 -File "report.xlsm" -PfxFile "certs\default.pfx" -OutputFile "report_signed.xlsm"
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$File,

    [Parameter(Mandatory = $true)]
    [string]$PfxFile,

    [string]$PfxPassword = "",

    [ValidateSet("SHA256", "SHA384", "SHA512")]
    [string]$HashAlgorithm = "SHA256",

    [string]$OutputFile = ""
)

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Prerequisite checks
# ---------------------------------------------------------------------------

Write-Host "Macro Sign Service - VBA Project Signing (signtool + Office SIP)" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host ""

# Check signtool
$signtool = $null
$signtoolPath = Get-Command signtool -ErrorAction SilentlyContinue
if ($signtoolPath) {
    $signtool = $signtoolPath.Source
} else {
    # Search Windows SDK paths
    $sdkPaths = @(
        "C:\Program Files (x86)\Windows Kits\10\bin",
        "C:\Program Files\Windows Kits\10\bin"
    )
    foreach ($sdkBase in $sdkPaths) {
        if (Test-Path $sdkBase) {
            $versions = Get-ChildItem $sdkBase -Directory | Sort-Object Name -Descending
            foreach ($ver in $versions) {
                $candidate = Join-Path $ver.FullName "x64\signtool.exe"
                if (Test-Path $candidate) {
                    $signtool = $candidate
                    break
                }
            }
            if ($signtool) { break }
        }
    }
}

if (-not $signtool) {
    Write-Error "signtool.exe not found. Install Windows SDK: https://developer.microsoft.com/en-us/windows/downloads/windows-sdk/"
    exit 1
}
Write-Host "signtool: $signtool" -ForegroundColor Green

# Check Office SIP DLL
$sipFound = $false
$sipPaths = @(
    "C:\Program Files\Microsoft Office\root\Office16\msosip.dll",
    "C:\Program Files (x86)\Microsoft Office\root\Office16\msosip.dll",
    "C:\Program Files\Microsoft Office\Office16\msosip.dll",
    "C:\Program Files (x86)\Microsoft Office\Office16\msosip.dll"
)
foreach ($sp in $sipPaths) {
    if (Test-Path $sp) {
        Write-Host "Office SIP: $sp" -ForegroundColor Green
        $sipFound = $true
        break
    }
}
if (-not $sipFound) {
    # Check registry
    try {
        $regDll = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Cryptography\OID\EncodingType 0\CryptSIPDllVerifyIndirectData\{000C10F1-0000-0000-C000-000000000046}" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Dll
        if ($regDll) {
            Write-Host "Office SIP (registry): $regDll" -ForegroundColor Green
            $sipFound = $true
        }
    } catch {}

    if (-not $sipFound) {
        Write-Host "WARNING: Office SIP DLLs not found. signtool may not produce valid VBA signatures." -ForegroundColor Yellow
        Write-Host "Install Microsoft Office to register the Office SIP DLLs." -ForegroundColor Yellow
    }
}
Write-Host ""

# Validate inputs
if (-not (Test-Path $File)) {
    Write-Error "File not found: $File"
    exit 1
}
if (-not (Test-Path $PfxFile)) {
    Write-Error "PFX certificate not found: $PfxFile"
    exit 1
}

# If output file specified, copy the input file first
if ($OutputFile -and $OutputFile -ne $File) {
    Copy-Item -Path $File -Destination $OutputFile -Force
    $TargetFile = (Resolve-Path $OutputFile).Path
} else {
    $TargetFile = (Resolve-Path $File).Path
}

# ---------------------------------------------------------------------------
# Show certificate details
# ---------------------------------------------------------------------------

$securePassword = ConvertTo-SecureString -String $PfxPassword -AsPlainText -Force
$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2(
    (Resolve-Path $PfxFile).Path,
    $securePassword,
    [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::Exportable
)

Write-Host "Certificate Details:" -ForegroundColor Green
Write-Host "  Subject:     $($cert.Subject)"
Write-Host "  Issuer:      $($cert.Issuer)"
Write-Host "  Thumbprint:  $($cert.Thumbprint)"
Write-Host "  Valid From:  $($cert.NotBefore)"
Write-Host "  Valid Until: $($cert.NotAfter)"
Write-Host "  Has Key:     $($cert.HasPrivateKey)"

# Check Code Signing EKU
$codeSigningOid = "1.3.6.1.5.5.7.3.3"
$hasCodeSigning = $false
foreach ($ext in $cert.Extensions) {
    if ($ext -is [System.Security.Cryptography.X509Certificates.X509EnhancedKeyUsageExtension]) {
        foreach ($eku in $ext.EnhancedKeyUsages) {
            if ($eku.Value -eq $codeSigningOid) { $hasCodeSigning = $true; break }
        }
    }
}
if ($hasCodeSigning) {
    Write-Host "  Code Signing: YES" -ForegroundColor Green
} else {
    Write-Host "  Code Signing: NO (may fail)" -ForegroundColor Yellow
}
Write-Host ""

# ---------------------------------------------------------------------------
# Sign with signtool
# ---------------------------------------------------------------------------

Write-Host "Signing: $TargetFile" -ForegroundColor Cyan
Write-Host "Algorithm: $HashAlgorithm"
Write-Host ""

$signArgs = @("sign", "/f", (Resolve-Path $PfxFile).Path, "/fd", $HashAlgorithm, "/v")
if ($PfxPassword) {
    $signArgs += @("/p", $PfxPassword)
}
$signArgs += $TargetFile

Write-Host "Running: signtool $($signArgs[0..3] -join ' ') ... $([System.IO.Path]::GetFileName($TargetFile))"
Write-Host ""

$process = Start-Process -FilePath $signtool -ArgumentList $signArgs -NoNewWindow -Wait -PassThru -RedirectStandardOutput "$env:TEMP\signtool_out.txt" -RedirectStandardError "$env:TEMP\signtool_err.txt"

$stdout = Get-Content "$env:TEMP\signtool_out.txt" -Raw -ErrorAction SilentlyContinue
$stderr = Get-Content "$env:TEMP\signtool_err.txt" -Raw -ErrorAction SilentlyContinue

if ($stdout) { Write-Host $stdout }
if ($stderr) { Write-Host $stderr -ForegroundColor Red }

if ($process.ExitCode -eq 0) {
    Write-Host ""
    Write-Host "SUCCESS: File signed with signtool + Office SIP!" -ForegroundColor Green
    Write-Host "  Signed file: $TargetFile" -ForegroundColor Green
    Write-Host ""

    # Verify
    Write-Host "Verifying signature..." -ForegroundColor Cyan
    $verifyArgs = @("verify", "/pa", "/v", $TargetFile)
    $verifyProcess = Start-Process -FilePath $signtool -ArgumentList $verifyArgs -NoNewWindow -Wait -PassThru -RedirectStandardOutput "$env:TEMP\signtool_verify.txt" -RedirectStandardError "$env:TEMP\signtool_verify_err.txt"
    $verifyOut = Get-Content "$env:TEMP\signtool_verify.txt" -Raw -ErrorAction SilentlyContinue
    if ($verifyOut) { Write-Host $verifyOut }

    if ($verifyProcess.ExitCode -eq 0) {
        Write-Host "Verification: PASSED" -ForegroundColor Green
    } else {
        Write-Host "Verification: FAILED (signature may not be recognized by Office)" -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "To verify in Excel/Word:" -ForegroundColor Yellow
    Write-Host "  1. Open the file in Excel/Word"
    Write-Host "  2. Press Alt+F11 to open VBA Editor"
    Write-Host "  3. Go to Tools -> Digital Signature"
    Write-Host "  4. The certificate '$($cert.Subject)' should be displayed"

    exit 0
} else {
    Write-Host ""
    Write-Host "FAILED: signtool exited with code $($process.ExitCode)" -ForegroundColor Red
    if (-not $sipFound) {
        Write-Host ""
        Write-Host "LIKELY CAUSE: Office SIP DLLs are not registered." -ForegroundColor Yellow
        Write-Host "Install Microsoft Office to enable VBA project signing." -ForegroundColor Yellow
    }
    exit 1
}
