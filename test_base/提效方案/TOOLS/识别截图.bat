<# :
@echo off
setlocal
set "TA_SELF=%~f0"
set "TA_ARGS=%*"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$s=[IO.File]::ReadAllText($env:TA_SELF,[Text.Encoding]::UTF8); Invoke-Expression ('& {' + $s + [char]10 + '}')"
echo.
if not defined TA_OCR_QUIET pause
exit /b
#>
# =====================================================================
#  识别截图（测试分析助手配套工具）
#  用 Windows 自带的文字识别（OCR）读出截图上的文字，不用安装任何软件，截图不会离开本机。
#  平时不用手动运行：测试分析助手导入报告后会自动调用本工具。
#  手动使用：把测试报告文件（.html / .mhtml）或截图文件夹拖到本文件上；也可以双击后把文件拖进窗口，按回车。
#        报告里直接嵌在网页中的截图（另存为单个 html 文件时）、同名 _files 文件夹里的截图都能识别。
#  结果：在报告旁边（或文件夹里）生成「截图识别结果.ocr.json」。
#  供程序调用：设置环境变量 TA_OCR_QUIET=1（结束时不暂停）、TA_OCR_OUT=<结果文件完整路径>。
# =====================================================================
$ErrorActionPreference = 'Stop'
try { $Host.UI.RawUI.WindowTitle = '识别截图' } catch {}
Write-Host ''
Write-Host '  识别截图：Windows 自带文字识别，截图不会离开本机' -ForegroundColor Cyan
Write-Host ''

function Split-Args([string]$s) {
  $out = @()
  foreach ($m in [regex]::Matches([string]$s, '"([^"]+)"|(\S+)')) {
    $v = if ($m.Groups[1].Success) { $m.Groups[1].Value } else { $m.Groups[2].Value }
    if ($v) { $out += $v.Trim() }
  }
  return $out
}
$paths = @(Split-Args $env:TA_ARGS)
if (-not $paths.Count -and -not $env:TA_OCR_QUIET) {
  Write-Host '  请把测试报告文件（.mhtml / .html）或截图文件夹拖到这个窗口里，然后按回车：'
  $paths = @(Split-Args (Read-Host '  '))
}
$paths = @($paths | Where-Object { Test-Path -LiteralPath $_ })
if (-not $paths.Count) { Write-Host '  没有找到文件或文件夹。' -ForegroundColor Red; return }

# ---------- 准备 Windows 文字识别 ----------
try {
  Add-Type -AssemblyName System.Runtime.WindowsRuntime
  $null = [Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
  $null = [Windows.Storage.Streams.IRandomAccessStream,Windows.Storage.Streams,ContentType=WindowsRuntime]
  $null = [Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics,ContentType=WindowsRuntime]
  $null = [Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]
  $null = [Windows.Globalization.Language,Windows.Globalization,ContentType=WindowsRuntime]
} catch {
  Write-Host '  这台电脑无法使用 Windows 自带的文字识别（需要 Windows 10 / 11）。' -ForegroundColor Red
  Write-Host ('  原因：' + $_.Exception.Message)
  return
}
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [Type]$t) { $task = $asTask.MakeGenericMethod($t).Invoke($null, @($op)); $null = $task.Wait(-1); return $task.Result }

$all = @([Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages)
$pick = @()
$en = $all | Where-Object { $_.LanguageTag -like 'en*' } | Select-Object -First 1
if ($en) { $pick += $en }
$zh = $all | Where-Object { $_.LanguageTag -match '^zh-(Hant|TW|HK|MO)' } | Select-Object -First 1
if (-not $zh) { $zh = $all | Where-Object { $_.LanguageTag -like 'zh*' } | Select-Object -First 1 }
if ($zh) { $pick += $zh }
if (-not $pick.Count -and $all.Count) { $pick += $all[0] }
$engines = @($pick | ForEach-Object { $e = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($_); if ($e) { [pscustomobject]@{ tag = $_.LanguageTag; eng = $e } } })
if (-not $engines.Count) { Write-Host '  系统里没有可用的识别语言，请在 设置 → 时间和语言 → 语言 里添加英文或中文。' -ForegroundColor Red; return }
Write-Host ('  识别语言：' + (($engines | ForEach-Object { $_.tag }) -join '、'))
if (-not $zh) { Write-Host '  （没有中文识别语言，截图上的中文会识别不出来；英文不受影响）' -ForegroundColor Yellow }
$maxDim = [Windows.Media.Ocr.OcrEngine]::MaxImageDimension

# ---------- 收集截图 ----------
$tmp = Join-Path $env:TEMP ('ta_ocr_' + [guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $tmp
$imgs = New-Object System.Collections.ArrayList
$seen = @{}
$cnt = @{ n = 0 }
$sha = [System.Security.Cryptography.SHA256]::Create()
function Hex($bytes) { return (($sha.ComputeHash($bytes) | ForEach-Object { $_.ToString('x2') }) -join '') }
function Add-Img([string]$path, [string]$name, [byte[]]$bytes) {
  if (-not $bytes) { $bytes = [IO.File]::ReadAllBytes($path) }
  $h = Hex $bytes
  if ($seen.ContainsKey($h)) { return }
  $seen[$h] = 1
  [void]$imgs.Add([pscustomobject]@{ path = $path; name = $name; sha = $h })
}
$imgExt = '\.(png|jpe?g|bmp|gif)$'
function Add-Mhtml([string]$p) {
  $text = [IO.File]::ReadAllText($p)
  $m = [regex]::Match($text, 'boundary="?([^";\r\n]+)"?', 'IgnoreCase')
  if (-not $m.Success) { Write-Host ('  ' + [IO.Path]::GetFileName($p) + '：不是有效的 MHTML 文件') -ForegroundColor Yellow; return }
  $n = 0
  foreach ($part in $text.Split([string[]]@('--' + $m.Groups[1].Value), [StringSplitOptions]::None)) {
    $sp = [regex]::Match($part, '\r?\n\r?\n')
    if (-not $sp.Success) { continue }
    $head = $part.Substring(0, $sp.Index)
    if ($head -notmatch '(?im)^Content-Type:\s*image/([a-z+]+)') { continue }
    $ext = $Matches[1] -replace 'jpeg', 'jpg'
    if ($ext -notmatch '^(png|jpg|gif|bmp)$') { continue }
    if ($head -notmatch '(?im)^Content-Transfer-Encoding:\s*base64') { continue }
    $loc = if ($head -match '(?im)^Content-Location:\s*(.+)$') { $Matches[1].Trim() } else { '' }
    try { $bytes = [Convert]::FromBase64String(($part.Substring($sp.Index) -replace '\s', '')) } catch { continue }
    $n++
    $name = ($loc -split '[\\/?#]' | Where-Object { $_ } | Select-Object -Last 1)
    if (-not $name -or $name -notmatch $imgExt) { $name = 'image_' + $n + '.' + $ext }
    $f = Join-Path $tmp ('m' + $n + '.' + $ext)
    [IO.File]::WriteAllBytes($f, $bytes)
    Add-Img $f $name $bytes
  }
}
function Add-Html([string]$p) {
  $dir = Split-Path -Parent $p
  $base = [IO.Path]::GetFileNameWithoutExtension($p)
  foreach ($d in @((Join-Path $dir ($base + '_files')), (Join-Path $dir ($base + '.files')))) {
    if (Test-Path -LiteralPath $d) { Get-ChildItem -LiteralPath $d -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -match $imgExt } | ForEach-Object { Add-Img $_.FullName $_.Name $null } }
  }
  $html = [IO.File]::ReadAllText($p)
  # 直接嵌在网页里的截图（src="data:image/png;base64,..."）：另存为单个 html 文件时截图在这里
  $n = 0
  foreach ($m in [regex]::Matches($html, 'data:image/(png|jpe?g|gif|bmp);base64,([A-Za-z0-9+/=\s]+)', 'IgnoreCase')) {
    try { $bytes = [Convert]::FromBase64String(($m.Groups[2].Value -replace '\s', '')) } catch { continue }
    if ($bytes.Length -lt 200) { continue }   # 图标、占位小图不识别
    $n++; $cnt.n++
    $ext = $m.Groups[1].Value.ToLower() -replace 'jpeg', 'jpg'
    $f = Join-Path $tmp ('h' + $cnt.n + '.' + $ext)
    [IO.File]::WriteAllBytes($f, $bytes)
    Add-Img $f ($base + '_截图' + $n + '.' + $ext) $bytes
  }
  foreach ($m in [regex]::Matches($html, '(?:src|href)\s*=\s*"([^"]+\.(?:png|jpe?g|bmp|gif))"', 'IgnoreCase')) {
    $rel = [uri]::UnescapeDataString($m.Groups[1].Value)
    if ($rel -match '^(https?|data):') { continue }
    $rel = $rel -replace '^file:///', ''
    $full = if ([IO.Path]::IsPathRooted($rel)) { $rel } else { Join-Path $dir $rel }
    if (Test-Path -LiteralPath $full) { Add-Img (Resolve-Path -LiteralPath $full).Path ([IO.Path]::GetFileName($full)) $null }
  }
}
foreach ($p in $paths) {
  $item = Get-Item -LiteralPath $p
  if ($item.PSIsContainer) {
    Get-ChildItem -LiteralPath $item.FullName -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -match $imgExt } | ForEach-Object { Add-Img $_.FullName $_.Name $null }
    Get-ChildItem -LiteralPath $item.FullName -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '\.(mhtml|mht)$' } | ForEach-Object { Add-Mhtml $_.FullName }
  } elseif ($item.Name -match '\.(mhtml|mht)$') { Add-Mhtml $item.FullName }
  elseif ($item.Name -match '\.html?$') { Add-Html $item.FullName }
  elseif ($item.Name -match $imgExt) { Add-Img $item.FullName $item.Name $null }
}
if (-not $imgs.Count) {
  Write-Host '  没有找到截图。' -ForegroundColor Red
  Write-Host '  报告是 .html 文件时，截图要么直接嵌在网页里，要么在同名的“_files”文件夹里，请确认文件夹和报告放在一起；'
  Write-Host '  报告里的截图需要点开才显示的，保存前要先点开，否则保存下来的文件里没有截图。'
  return
}
Write-Host ('  找到 ' + $imgs.Count + ' 张截图，开始识别……')
Write-Host ''

# ---------- 逐张识别（结果直接写成 JSON 文本，避免 ConvertTo-Json 改变数组结构） ----------
function JS([string]$s) {
  $sb = New-Object System.Text.StringBuilder
  [void]$sb.Append('"')
  foreach ($ch in $s.ToCharArray()) {
    $c = [int]$ch
    if ($ch -eq '"') { [void]$sb.Append('\"') } elseif ($ch -eq '\') { [void]$sb.Append('\\') }
    elseif ($c -lt 32) { [void]$sb.Append('\u' + $c.ToString('x4')) } else { [void]$sb.Append($ch) }
  }
  [void]$sb.Append('"')
  return $sb.ToString()
}
$parts = New-Object System.Collections.ArrayList
$i = 0; $okN = 0
foreach ($im in $imgs) {
  $i++
  $head = '{"sha256":' + (JS $im.sha) + ',"name":' + (JS $im.name)
  try {
    $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($im.path)) ([Windows.Storage.StorageFile])
    $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $dec = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bmp = Await ($dec.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $stream.Dispose()
    if ($bmp.BitmapPixelFormat -ne [Windows.Graphics.Imaging.BitmapPixelFormat]::Bgra8 -and $bmp.BitmapPixelFormat -ne [Windows.Graphics.Imaging.BitmapPixelFormat]::Gray8) { $bmp = [Windows.Graphics.Imaging.SoftwareBitmap]::Convert($bmp, [Windows.Graphics.Imaging.BitmapPixelFormat]::Bgra8) }
    if ($bmp.PixelWidth -gt $maxDim -or $bmp.PixelHeight -gt $maxDim) { throw ('图片太大（' + $bmp.PixelWidth + '×' + $bmp.PixelHeight + '），超过系统识别上限 ' + $maxDim) }
    $langJ = @(); $lineN = 0
    foreach ($e in $engines) {
      $res = Await ($e.eng.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])
      $lineJ = @()
      foreach ($ln in $res.Lines) {
        $wJ = @(); $x1 = [double]::MaxValue; $y1 = [double]::MaxValue; $x2 = 0; $y2 = 0
        foreach ($w in $ln.Words) {
          $r = $w.BoundingRect
          $wJ += '[' + (JS $w.Text) + ',' + [int]$r.X + ',' + [int]$r.Y + ',' + [int]$r.Width + ',' + [int]$r.Height + ']'
          if ($r.X -lt $x1) { $x1 = $r.X }; if ($r.Y -lt $y1) { $y1 = $r.Y }
          if ($r.X + $r.Width -gt $x2) { $x2 = $r.X + $r.Width }; if ($r.Y + $r.Height -gt $y2) { $y2 = $r.Y + $r.Height }
        }
        if (-not $wJ.Count) { continue }
        $lineJ += '{"t":' + (JS $ln.Text) + ',"b":[' + [int]$x1 + ',' + [int]$y1 + ',' + [int]($x2 - $x1) + ',' + [int]($y2 - $y1) + '],"w":[' + ($wJ -join ',') + ']}'
      }
      if ($lineJ.Count -gt $lineN) { $lineN = $lineJ.Count }
      $langJ += '{"lang":' + (JS $e.tag) + ',"lines":[' + ($lineJ -join ',') + ']}'
    }
    [void]$parts.Add($head + ',"w":' + $bmp.PixelWidth + ',"h":' + $bmp.PixelHeight + ',"langs":[' + ($langJ -join ',') + ']}')
    $okN++
    Write-Host ('  [' + $i + '/' + $imgs.Count + '] ' + $im.name + '：' + $lineN + ' 行文字')
  } catch {
    [void]$parts.Add($head + ',"error":' + (JS $_.Exception.Message) + '}')
    Write-Host ('  [' + $i + '/' + $imgs.Count + '] ' + $im.name + '：识别失败（' + $_.Exception.Message + '）') -ForegroundColor Yellow
  }
}
Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue

# ---------- 保存结果 ----------
$first = Get-Item -LiteralPath $paths[0]
$dir = if ($first.PSIsContainer) { $first.FullName } else { $first.DirectoryName }
$target = if ($env:TA_OCR_OUT) { $env:TA_OCR_OUT } else { Join-Path $dir '截图识别结果.ocr.json' }
$json = '{"tool":"ta-ocr","v":1,"created":' + (JS (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')) + ',"engine":"Windows.Media.Ocr","langs":[' + ((@($engines | ForEach-Object { JS $_.tag })) -join ',') + '],"source":[' + ((@($paths | ForEach-Object { JS ([IO.Path]::GetFileName($_)) })) -join ',') + '],"images":[' + ($parts -join ",`n") + ']}'
try { [IO.File]::WriteAllText($target, $json, (New-Object System.Text.UTF8Encoding($false))) }
catch {
  $target = Join-Path ([Environment]::GetFolderPath('Desktop')) '截图识别结果.ocr.json'
  [IO.File]::WriteAllText($target, $json, (New-Object System.Text.UTF8Encoding($false)))
}
Write-Host ''
Write-Host ('  完成：识别 ' + $okN + ' / ' + $imgs.Count + ' 张。') -ForegroundColor Green
Write-Host ('  结果文件：' + $target)
Write-Host '  测试分析助手导入报告时会自动识别截图，一般不需要手动运行本工具；手动生成的结果文件，可以和报告一起拖进导入页。'
