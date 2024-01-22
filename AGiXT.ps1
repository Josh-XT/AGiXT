if (!(Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Docker is not installed, please install Docker and try again. https://docs.docker.com/desktop/"
    exit
}
Write-Host "    ___   _______ _  ________"
Write-Host "   /   | / ____(_) |/ /_  __/"
Write-Host "  / /| |/ / __/ /|   / / /   "
Write-Host " / ___ / /_/ / //   | / /    "
Write-Host "/_/  |_\____/_//_/|_|/_/     "
Write-Host "                              "
Write-Host "-------------------------------"
Write-Host "Visit our documentation at https://AGiXT.com"

if( !(Test-Path "$(Get-Location)\.env") ) {
    Write-Host "Welcome to the AGiXT Environment Setup!"
    $env:AGIXT_AUTO_UPDATE = Read-Host "Would you like AGiXT to auto update? (y/n - default: y)"
    $env:AGIXT_API_KEY = Read-Host "Would you like to set an API Key for AGiXT? Enter it if so, otherwise press enter to proceed. (default is blank)"
    $env:UVICORN_WORKERS = Read-Host "Enter the number of AGiXT workers to run (default: 10)"
    $env:AGIXT_AUTO_UPDATE = $env:AGIXT_AUTO_UPDATE.ToLower()
    if ([string]::IsNullOrEmpty($env:AGIXT_AUTO_UPDATE) -or $env:AGIXT_AUTO_UPDATE -eq "y" -or $env:AGIXT_AUTO_UPDATE -eq "yes") { $env:AGIXT_AUTO_UPDATE = "true" } else { $env:AGIXT_AUTO_UPDATE = "false" }  
    if ([string]::IsNullOrEmpty($env:AGIXT_URI)) { $env:AGIXT_URI = "http://localhost:7437" }
    if ([string]::IsNullOrEmpty($env:UVICORN_WORKERS)) { $env:UVICORN_WORKERS = "10" }
    if ([string]::IsNullOrEmpty($env:WORKING_DIRECTORY)) { $env:WORKING_DIRECTORY = "$(Get-Location)\agixt\WORKSPACE" }
    Set-Content -Path "$(Get-Location)\.env" -Value "AGIXT_AUTO_UPDATE=$env:AGIXT_AUTO_UPDATE`nAGIXT_API_KEY=$env:AGIXT_API_KEY`nAGIXT_URI=$env:AGIXT_URI`nUVICORN_WORKERS=$env:UVICORN_WORKERS`nWORKING_DIRECTORY=$env:WORKING_DIRECTORY"
}

Write-Host "Welcome to AGiXT!"
Write-Host "Please select an option:"
Write-Host "1. Run AGiXT (Stable - Recommended!)"
Write-Host "2. Run AGiXT (Development)"
Write-Host "3. Run AGiXT (Development w/CUDA)"
Write-Host "4. Run Backend Only (Development)"
Write-Host "9. Exit"
$choice = Read-Host "Enter your choice"

switch($choice) {
    "1" {
        $file = "docker-compose.yml"
    }
    "2" {
        $file = "docker-compose-dev.yml"
    }
    "3" {
        $file = "docker-compose-dev-cuda.yml"
    }
    "4" {
        $file = "backend.yml"
    }
    default {
        exit
    }
}
docker-compose -f $file down
if ($env:AGIXT_AUTO_UPDATE -eq "true" -or $null -eq $env:AGIXT_AUTO_UPDATE) {
    Write-Host "Updating AGiXT..."
    docker-compose -f $file pull
}
Write-Host "Starting AGiXT..."
docker-compose -f $file up