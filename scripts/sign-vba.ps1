<#
.SYNOPSIS
    Sign an Office macro file (.xlsm, .docm, etc.) with a code-signing PFX certificate.

.DESCRIPTION
    This script signs a VBA macro file using Set-AuthenticodeSignature so that
    the digital signature is embedded in the VBA project and visible under
    Alt+F11 -> Tools -> Digital Signature in Excel/Word.

    The PFX certificate can be generated using:
        python -m cli.macro_sign_cli generate-pfx
    Or downloaded from the service:
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

.EXAMPLE
    .\sign-vba.ps1 -File "macros.docm" -PfxFile "certs\default.pfx" -HashAlgorithm SHA512
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
    $TargetFile = $OutputFile
} else {
    $TargetFile = $File
}

Write-Host "Macro Sign Service - VBA Project Signing" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

# Load the PFX certificate
Write-Host "Loading certificate from: $PfxFile"
$securePassword = ConvertTo-SecureString -String $PfxPassword -AsPlainText -Force
$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2(
    (Resolve-Path $PfxFile).Path,
    $securePassword,
    [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::Exportable
)

# Display certificate info
Write-Host ""
Write-Host "Certificate Details:" -ForegroundColor Green
Write-Host "  Subject:     $($cert.Subject)"
Write-Host "  Issuer:      $($cert.Issuer)"
Write-Host "  Thumbprint:  $($cert.Thumbprint)"
Write-Host "  Valid From:  $($cert.NotBefore)"
Write-Host "  Valid Until: $($cert.NotAfter)"
Write-Host "  Has Private Key: $($cert.HasPrivateKey)"
Write-Host ""

# Verify the certificate has a private key
if (-not $cert.HasPrivateKey) {
    Write-Error "Certificate does not have a private key. Cannot sign."
    exit 1
}

# Check for Code Signing EKU
$codeSigningOid = "1.3.6.1.5.5.7.3.3"
$hasCodeSigning = $false
foreach ($ext in $cert.Extensions) {
    if ($ext -is [System.Security.Cryptography.X509Certificates.X509EnhancedKeyUsageExtension]) {
        foreach ($eku in $ext.EnhancedKeyUsages) {
            if ($eku.Value -eq $codeSigningOid) {
                $hasCodeSigning = $true
                break
            }
        }
    }
}

if ($hasCodeSigning) {
    Write-Host "  Code Signing EKU: Present" -ForegroundColor Green
} else {
    Write-Host "  Code Signing EKU: NOT FOUND (signing may fail)" -ForegroundColor Yellow
}
Write-Host ""

# Sign the file
Write-Host "Signing file: $TargetFile"
Write-Host "Algorithm: $HashAlgorithm"
Write-Host ""

$result = Set-AuthenticodeSignature `
    -FilePath (Resolve-Path $TargetFile).Path `
    -Certificate $cert `
    -HashAlgorithm $HashAlgorithm

# Check result
Write-Host "Signing Result:" -ForegroundColor Cyan
Write-Host "  Status:        $($result.Status)"
Write-Host "  Status Message: $($result.StatusMessage)"

if ($result.Status -eq "Valid") {
    Write-Host ""
    Write-Host "SUCCESS: File signed successfully!" -ForegroundColor Green
    Write-Host "  Signed file: $TargetFile" -ForegroundColor Green
    Write-Host ""
    Write-Host "To verify in Excel/Word:" -ForegroundColor Yellow
    Write-Host "  1. Open the file"
    Write-Host "  2. Press Alt+F11 to open VBA Editor"
    Write-Host "  3. Go to Tools -> Digital Signature"
    Write-Host "  4. The certificate should be displayed"
    Write-Host ""

    # Show signature details
    $sig = Get-AuthenticodeSignature -FilePath (Resolve-Path $TargetFile).Path
    Write-Host "Signature Verification:" -ForegroundColor Cyan
    Write-Host "  Signer: $($sig.SignerCertificate.Subject)"
    Write-Host "  Thumbprint: $($sig.SignerCertificate.Thumbprint)"
    Write-Host "  Valid: $($sig.Status -eq 'Valid')"

    exit 0
} else {
    Write-Host ""
    Write-Host "FAILED: Signing was not successful." -ForegroundColor Red
    Write-Host "  Error: $($result.StatusMessage)" -ForegroundColor Red
    exit 1
}
