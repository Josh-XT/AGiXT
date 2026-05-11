param(
    [Parameter(Mandatory = $true)]
    [string[]] $Path,
    [switch] $Required
)

$ErrorActionPreference = "Stop"

function Test-Truthy {
    param([string] $Value)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $false
    }
    return $Value.Trim().ToLowerInvariant() -notin @("0", "false", "no", "off")
}

function Get-FirstEnv {
    param([string[]] $Names)
    foreach ($name in $Names) {
        $value = [Environment]::GetEnvironmentVariable($name)
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            return $value.Trim()
        }
    }
    return ""
}

function Get-SignableFiles {
    param([string[]] $InputPaths)
    $files = New-Object System.Collections.Generic.List[string]
    foreach ($inputPath in $InputPaths) {
        if (-not (Test-Path -LiteralPath $inputPath)) {
            throw "Signing path does not exist: $inputPath"
        }
        $item = Get-Item -LiteralPath $inputPath
        if ($item.PSIsContainer) {
            Get-ChildItem -LiteralPath $item.FullName -Recurse -File |
                Where-Object { $_.Extension.ToLowerInvariant() -in @(".exe", ".msi", ".dll") } |
                ForEach-Object { [void] $files.Add($_.FullName) }
        } else {
            [void] $files.Add($item.FullName)
        }
    }
    return $files | Sort-Object -Unique
}

function Find-SignTool {
    $command = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $roots = @(
        "${env:ProgramFiles(x86)}\Windows Kits\10\bin",
        "${env:ProgramFiles(x86)}\Windows Kits\10\App Certification Kit"
    )
    foreach ($root in $roots) {
        if (-not (Test-Path -LiteralPath $root)) {
            continue
        }
        $candidate = Get-ChildItem -LiteralPath $root -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match "\\x64\\signtool\.exe$" -or $_.DirectoryName -like "*App Certification Kit*" } |
            Sort-Object FullName -Descending |
            Select-Object -First 1
        if ($candidate) {
            return $candidate.FullName
        }
    }
    throw "signtool.exe was not found. Install the Windows SDK or use Azure Artifact Signing."
}

function Assert-ValidSignature {
    param([string[]] $Files)
    foreach ($file in $Files) {
        $signature = Get-AuthenticodeSignature -LiteralPath $file
        if ($signature.Status -ne "Valid") {
            $message = "Signature verification failed for $file. Status: $($signature.Status). $($signature.StatusMessage)"
            if ($script:SigningRequired) {
                throw $message
            }
            Write-Warning $message
        } else {
            $subject = $signature.SignerCertificate.Subject
            Write-Host "Verified Authenticode signature for $file ($subject)"
        }
    }
}

function Invoke-ArtifactSigning {
    param([string[]] $Files)

    $endpoint = Get-FirstEnv @("AGIXT_WINDOWS_ARTIFACT_SIGNING_ENDPOINT", "AZURE_TRUSTED_SIGNING_ENDPOINT")
    $account = Get-FirstEnv @("AGIXT_WINDOWS_ARTIFACT_SIGNING_ACCOUNT", "AZURE_TRUSTED_SIGNING_ACCOUNT_NAME")
    $profile = Get-FirstEnv @("AGIXT_WINDOWS_ARTIFACT_SIGNING_CERTIFICATE_PROFILE", "AZURE_TRUSTED_SIGNING_CERTIFICATE_PROFILE")
    if ([string]::IsNullOrWhiteSpace($endpoint) -or [string]::IsNullOrWhiteSpace($account) -or [string]::IsNullOrWhiteSpace($profile)) {
        return $false
    }

    if (-not (Get-Module -ListAvailable -Name TrustedSigning | Where-Object { $_.Version -ge [version]"0.5.8" })) {
        if (-not (Get-PackageProvider -Name NuGet -ErrorAction SilentlyContinue)) {
            Install-PackageProvider -Name NuGet -Scope CurrentUser -Force | Out-Null
        }
        Set-PSRepository -Name PSGallery -InstallationPolicy Trusted -ErrorAction SilentlyContinue
        Install-Module -Name TrustedSigning -MinimumVersion 0.5.8 -Scope CurrentUser -Force -AllowClobber
    }

    Import-Module TrustedSigning -MinimumVersion 0.5.8
    $timestamp = Get-FirstEnv @("AGIXT_WINDOWS_CODESIGN_TIMESTAMP_URL", "WINDOWS_CODESIGN_TIMESTAMP_URL")
    if ([string]::IsNullOrWhiteSpace($timestamp)) {
        $timestamp = "http://timestamp.acs.microsoft.com"
    }

    $params = @{
        Endpoint = $endpoint
        CodeSigningAccountName = $account
        CertificateProfileName = $profile
        Files = ($Files -join [Environment]::NewLine)
        FileDigest = "SHA256"
        TimestampRfc3161 = $timestamp
        TimestampDigest = "SHA256"
    }

    Write-Host "Signing $($Files.Count) file(s) with Azure Artifact Signing..."
    Invoke-TrustedSigning @params
    return $true
}

function Invoke-SignToolSigning {
    param([string[]] $Files)

    $certBase64 = Get-FirstEnv @("WINDOWS_CERTIFICATE_BASE64", "WINDOWS_CODESIGN_PFX_BASE64")
    $certPath = Get-FirstEnv @("WINDOWS_CERTIFICATE_PATH", "WINDOWS_CODESIGN_PFX")
    $thumbprint = Get-FirstEnv @("WINDOWS_CERTIFICATE_THUMBPRINT", "WINDOWS_CODESIGN_THUMBPRINT")
    if ([string]::IsNullOrWhiteSpace($certBase64) -and [string]::IsNullOrWhiteSpace($certPath) -and [string]::IsNullOrWhiteSpace($thumbprint)) {
        return $false
    }

    $signtool = Find-SignTool
    $timestamp = Get-FirstEnv @("AGIXT_WINDOWS_CODESIGN_TIMESTAMP_URL", "WINDOWS_CODESIGN_TIMESTAMP_URL")
    if ([string]::IsNullOrWhiteSpace($timestamp)) {
        $timestamp = "http://timestamp.acs.microsoft.com"
    }
    $description = Get-FirstEnv @("AGIXT_WINDOWS_CODESIGN_DESCRIPTION", "WINDOWS_CODESIGN_DESCRIPTION")
    if ([string]::IsNullOrWhiteSpace($description)) {
        $description = "AGiXT Desktop"
    }
    $descriptionUrl = Get-FirstEnv @("AGIXT_WINDOWS_CODESIGN_URL", "WINDOWS_CODESIGN_URL")
    if ([string]::IsNullOrWhiteSpace($descriptionUrl)) {
        $descriptionUrl = "https://xt.systems"
    }

    $tempPfx = $null
    try {
        if (-not [string]::IsNullOrWhiteSpace($certBase64)) {
            $tempPfx = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), "agixt-windows-codesign-$([guid]::NewGuid()).pfx")
            [System.IO.File]::WriteAllBytes($tempPfx, [Convert]::FromBase64String(($certBase64 -replace "\s", "")))
            $certPath = $tempPfx
        }

        foreach ($file in $Files) {
            $args = @("sign", "/fd", "SHA256", "/tr", $timestamp, "/td", "SHA256", "/d", $description, "/du", $descriptionUrl)
            if (-not [string]::IsNullOrWhiteSpace($certPath)) {
                $password = Get-FirstEnv @("WINDOWS_CERTIFICATE_PASSWORD", "WINDOWS_CODESIGN_PFX_PASSWORD")
                $args += @("/f", $certPath)
                if (-not [string]::IsNullOrWhiteSpace($password)) {
                    $args += @("/p", $password)
                }
            } else {
                $args += @("/sha1", ($thumbprint -replace "\s", ""))
                if ((Get-FirstEnv @("WINDOWS_CERTIFICATE_STORE_LOCATION", "WINDOWS_CODESIGN_STORE_LOCATION")).ToLowerInvariant() -eq "localmachine") {
                    $args += "/sm"
                }
            }
            $args += $file
            Write-Host "Signing $file with signtool..."
            & $signtool @args
            if ($LASTEXITCODE -ne 0) {
                throw "signtool failed for $file with exit code $LASTEXITCODE"
            }
        }
    } finally {
        if ($tempPfx -and (Test-Path -LiteralPath $tempPfx)) {
            Remove-Item -LiteralPath $tempPfx -Force
        }
    }
    return $true
}

$script:SigningRequired = $Required.IsPresent -or (Test-Truthy $env:AGIXT_WINDOWS_SIGNING_REQUIRED)
$files = @(Get-SignableFiles -InputPaths $Path)
if ($files.Count -eq 0) {
    Write-Warning "No Windows binaries or installers found to sign."
    exit 0
}

$signed = $false
try {
    $signed = Invoke-ArtifactSigning -Files $files
} catch {
    if ($script:SigningRequired) {
        throw
    }
    Write-Warning "Azure Artifact Signing failed, continuing without a signature because signing is optional: $($_.Exception.Message)"
}

if (-not $signed) {
    try {
        $signed = Invoke-SignToolSigning -Files $files
    } catch {
        if ($script:SigningRequired) {
            throw
        }
        Write-Warning "signtool signing failed, continuing without a signature because signing is optional: $($_.Exception.Message)"
    }
}

if (-not $signed) {
    $message = "No Windows code-signing configuration was provided. Configure Azure Artifact Signing or WINDOWS_CERTIFICATE_* secrets."
    if ($script:SigningRequired) {
        throw $message
    }
    Write-Warning $message
    exit 0
}

Assert-ValidSignature -Files $files
