Add-Type -AssemblyName System.Drawing
$root = Split-Path -Parent $PSScriptRoot
$outDir = Join-Path $root 'assets'
New-Item -ItemType Directory -Force $outDir | Out-Null
$sizes = @(16, 24, 32, 48, 64, 128, 256)
$pngs = @()

foreach ($size in $sizes) {
    $scale = 4
    $px = $size * $scale
    $big = New-Object System.Drawing.Bitmap $px, $px
    $g = [System.Drawing.Graphics]::FromImage($big)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.Clear([System.Drawing.Color]::Transparent)

    $pad = [int]($px * 0.04)
    $rect = New-Object System.Drawing.Rectangle $pad, $pad, ($px - 2 * $pad), ($px - 2 * $pad)
    $radius = [int]($px * 0.25)
    $path = New-Object System.Drawing.Drawing2D.GraphicsPath
    $d = $radius * 2
    $path.AddArc($rect.X, $rect.Y, $d, $d, 180, 90)
    $path.AddArc($rect.Right - $d, $rect.Y, $d, $d, 270, 90)
    $path.AddArc($rect.Right - $d, $rect.Bottom - $d, $d, $d, 0, 90)
    $path.AddArc($rect.X, $rect.Bottom - $d, $d, $d, 90, 90)
    $path.CloseFigure()
    $brush = New-Object System.Drawing.Drawing2D.LinearGradientBrush $rect, ([System.Drawing.Color]::FromArgb(255, 37, 99, 235)), ([System.Drawing.Color]::FromArgb(255, 15, 23, 42)), 45
    $g.FillPath($brush, $path)

    $shine = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(26, 255, 255, 255))
    $g.FillEllipse($shine, [int]($px * 0.55), [int]($px * -0.05), [int]($px * 0.6), [int]($px * 0.6))

    $white = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::White)
    $headX = $px * 0.32
    $headY = $px * 0.57
    $headW = $px * 0.27
    $headH = $px * 0.20
    $g.FillEllipse($white, [int]$headX, [int]$headY, [int]$headW, [int]$headH)

    $stemX = $px * 0.56
    $stemTop = $px * 0.25
    $stemBottom = $px * 0.64
    $pen = New-Object System.Drawing.Pen ([System.Drawing.Color]::White), ([single]($px * 0.065))
    $pen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
    $pen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
    $g.DrawLine($pen, [int]$stemX, [int]$stemBottom, [int]$stemX, [int]$stemTop)
    $flagPen = New-Object System.Drawing.Pen ([System.Drawing.Color]::White), ([single]($px * 0.055))
    $flagPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
    $flagPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
    $g.DrawLine($flagPen, [int]$stemX, [int]$stemTop, [int]($px * 0.73), [int]($px * 0.34))

    $small = New-Object System.Drawing.Bitmap $size, $size
    $g2 = [System.Drawing.Graphics]::FromImage($small)
    $g2.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g2.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $g2.DrawImage($big, 0, 0, $size, $size)

    $file = Join-Path $outDir ("icon_{0}.png" -f $size)
    $small.Save($file, [System.Drawing.Imaging.ImageFormat]::Png)
    $pngs += ,@($size, $file)

    $g.Dispose(); $g2.Dispose(); $big.Dispose(); $small.Dispose()
    $brush.Dispose(); $path.Dispose(); $white.Dispose(); $shine.Dispose()
    $pen.Dispose(); $flagPen.Dispose()
}

$entries = @()
foreach ($p in $pngs) {
    $bytes = [System.IO.File]::ReadAllBytes($p[1])
    $entries += ,@($p[0], $bytes)
}

$ms = New-Object System.IO.MemoryStream
$bw = New-Object System.IO.BinaryWriter $ms
$bw.Write([UInt16]0)
$bw.Write([UInt16]1)
$bw.Write([UInt16]$entries.Count)
$offset = 6 + 16 * $entries.Count
foreach ($entry in $entries) {
    $w = $entry[0]
    if ($w -eq 256) { $w = 0 }
    $bw.Write([byte]$w)
    $bw.Write([byte]$w)
    $bw.Write([byte]0)
    $bw.Write([byte]0)
    $bw.Write([UInt16]1)
    $bw.Write([UInt16]32)
    $bw.Write([UInt32]$entry[1].Length)
    $bw.Write([UInt32]$offset)
    $offset += $entry[1].Length
}
foreach ($entry in $entries) {
    $bw.Write($entry[1])
}
$bw.Flush()
$icoPath = Join-Path $outDir 'app.ico'
[System.IO.File]::WriteAllBytes($icoPath, $ms.ToArray())
$bw.Dispose()
$ms.Dispose()

Get-ChildItem $outDir | Select-Object Name, Length
