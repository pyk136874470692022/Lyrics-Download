$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONIOENCODING = "utf-8"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

Write-Host "检查 Python 与依赖..."
python -c "import sys, requests, PyInstaller; print(sys.version); print('requests', requests.__version__); print('PyInstaller', PyInstaller.__version__)"

Write-Host "运行核心单元测试..."
python -m unittest discover -s tests -v

Write-Host "开始打包（单文件，运行库解压到 LocalAppData）..."
python -m PyInstaller --noconfirm --clean LyricsFetcher.spec

$exe = Join-Path $here "dist\歌词下载器.exe"
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    throw "打包失败：未找到 $exe"
}

# 清理 1.0.1 留下的目录版，避免和单文件版混淆。
$oldAppDir = Join-Path $here "dist\歌词下载器"
if (Test-Path -LiteralPath $oldAppDir -PathType Container) {
    Remove-Item -LiteralPath $oldAppDir -Recurse -Force
}

$isccCandidates = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe",
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
)
$iscc = $isccCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $iscc) {
    throw "未找到 Inno Setup 6（ISCC.exe），请先安装后再生成安装包。"
}

Write-Host "生成免管理员安装包..."
& $iscc "installer.iss"
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup 编译失败（退出码 $LASTEXITCODE）"
}

$setup = Join-Path $here "dist\歌词下载器安装包.exe"
if (-not (Test-Path -LiteralPath $setup -PathType Leaf)) {
    throw "打包失败：未找到 $setup"
}

$exeInfo = Get-Item -LiteralPath $exe
$setupInfo = Get-Item -LiteralPath $setup
Write-Host ""
Write-Host ("单文件程序：{0}" -f $exeInfo.FullName)
Write-Host ("程序大小：  {0:N1} MB" -f ($exeInfo.Length / 1MB))
Write-Host ("安装包：    {0}" -f $setupInfo.FullName)
Write-Host ("安装包大小：{0:N1} MB" -f ($setupInfo.Length / 1MB))
