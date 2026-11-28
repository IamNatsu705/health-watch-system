[CmdletBinding()]
param(
    [string]$PiHost = "pi.local",
    [string]$PiUser = "pi",
    [string]$RemoteDir = "/home/pi/projects/health_watch"
)

$ErrorActionPreference = "Stop"

if ($PiHost -notmatch '^[A-Za-z0-9._-]+$') {
    throw "PiHost chỉ được chứa chữ, số, dấu chấm, gạch dưới hoặc gạch ngang."
}
if ($PiUser -notmatch '^[A-Za-z_][A-Za-z0-9_-]*$') {
    throw "PiUser không hợp lệ."
}
if ($RemoteDir -notmatch '^/[A-Za-z0-9._/-]+$' -or $RemoteDir -match '(^|/)\.\.(/|$)') {
    throw "RemoteDir phải là đường dẫn tuyệt đối an toàn trên Pi."
}

foreach ($command in @("ssh", "scp")) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "Không tìm thấy lệnh $command. Hãy bật OpenSSH Client trên Windows."
    }
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$sourceDir = Join-Path $repoRoot "health_watch"
$remoteTarget = "$PiUser@$PiHost"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"

$rootNames = @(
    "main.py",
    "config.py",
    "alerts.py",
    "screen.py",
    "telemetry.py",
    "mqtt_publisher.py",
    "user_profile.py",
    "storage.py",
    "clock.py",
    "record_imu.py",
    "check_i2c.py",
    "check_alerts.py",
    "check_mqtt.py",
    "requirements.txt",
    "README.md",
    ".env.example",
    "run.sh"
)
$directoryNames = @("sensors", "processing", "inference", "models", "tests", "deploy")
$sources = @()

foreach ($name in $rootNames) {
    $path = Join-Path $sourceDir $name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Thiếu file triển khai: $path"
    }
    $sources += $path
}
foreach ($name in $directoryNames) {
    $path = Join-Path $sourceDir $name
    if (-not (Test-Path -LiteralPath $path -PathType Container)) {
        throw "Thiếu thư mục triển khai: $path"
    }
    $sources += $path
}

function Invoke-NativeChecked {
    param(
        [Parameter(Mandatory)] [string]$FilePath,
        [Parameter(Mandatory)] [string[]]$Arguments
    )
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$FilePath thất bại với mã $LASTEXITCODE."
    }
}

Write-Host "1/3 Kết nối Pi và sao lưu source hiện tại..." -ForegroundColor Cyan
$temporaryBackup = "/tmp/health-watch-source-$timestamp.tar.gz"
$prepare = "set -eu; mkdir -p '$RemoteDir' '$RemoteDir/backups'; if [ -f '$RemoteDir/main.py' ]; then tar --exclude='./.venv' --exclude='./.env' --exclude='./backups' --exclude='./recordings' --exclude='*/__pycache__' -czf '$temporaryBackup' -C '$RemoteDir' .; mv '$temporaryBackup' '$RemoteDir/backups/source-$timestamp.tar.gz'; fi"
Invoke-NativeChecked -FilePath "ssh" -Arguments @($remoteTarget, $prepare)

Write-Host "2/3 Chép đúng các file chạy trên Pi; giữ nguyên .env và .venv..." -ForegroundColor Cyan
$scpArguments = @("-r") + $sources + @("${remoteTarget}:$RemoteDir/")
Invoke-NativeChecked -FilePath "scp" -Arguments $scpArguments

Write-Host "3/3 Đặt quyền chạy và tạo .env lần đầu nếu chưa có..." -ForegroundColor Cyan
$finish = "set -eu; cd '$RemoteDir'; chmod +x run.sh deploy/pi/setup.sh deploy/pi/install_service.sh; if [ ! -f .env ]; then cp .env.example .env; chmod 600 .env; echo CREATED_ENV=1; else chmod 600 .env; echo PRESERVED_ENV=1; fi"
Invoke-NativeChecked -FilePath "ssh" -Arguments @($remoteTarget, $finish)

Write-Host "Đã chép source tới ${remoteTarget}:$RemoteDir" -ForegroundColor Green
Write-Host "Tiếp theo SSH vào Pi, chạy:"
Write-Host "  cd $RemoteDir"
Write-Host "  bash deploy/pi/setup.sh"
Write-Host "  nano .env"
Write-Host "  ./run.sh"
Write-Host "Không xóa .venv, .env, state/ (số bước trong ngày, hồ sơ) hoặc recordings/ (dữ liệu ghi) trên Pi; script luôn giữ lại các mục đó."
