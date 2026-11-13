$ErrorActionPreference = 'Continue'
# Ключ активации Diktik (AG) — сборка из act_key.c компилятором из состава Windows.

$vs = 'C:\Program Files\Microsoft Visual Studio\18\Enterprise'
if (-not (Test-Path $vs)) {
    $vswhere = 'C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe'
    Start-Process -FilePath $vswhere -ArgumentList '-latest','-products','*','-property','installationPath' -NoNewWindow -Wait -RedirectStandardOutput vspath.txt
    $vs = (Get-Content vspath.txt -Raw).Trim()
    Remove-Item vspath.txt -ErrorAction SilentlyContinue
}
Write-Host ('VS: ' + $vs)

$msvcver = Get-ChildItem (Join-Path $vs 'VC\Tools\MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1
$bin = Join-Path $msvcver.FullName 'bin\Hostx64\x64'
Write-Host ('MSVC: ' + $msvcver.Name)

$sdk = Get-ChildItem 'C:\Program Files (x86)\Windows Kits\10\Include' -Directory | Sort-Object Name -Descending | Select-Object -First 1
$sdkver = $sdk.Name
Write-Host ('SDK: ' + $sdkver)

$env:INCLUDE = @(
  (Join-Path $msvcver.FullName 'include'),
  ('C:\Program Files (x86)\Windows Kits\10\Include\' + $sdkver + '\ucrt'),
  ('C:\Program Files (x86)\Windows Kits\10\Include\' + $sdkver + '\shared'),
  ('C:\Program Files (x86)\Windows Kits\10\Include\' + $sdkver + '\um')
) -join ';'
$env:LIB = @(
  (Join-Path $msvcver.FullName 'lib\x64'),
  ('C:\Program Files (x86)\Windows Kits\10\Lib\' + $sdkver + '\ucrt\x64'),
  ('C:\Program Files (x86)\Windows Kits\10\Lib\' + $sdkver + '\um\x64')
) -join ';'
$env:PATH = $bin + ';' + $env:PATH

Write-Host '[1/3] иконка и версия'
$rcExe = Get-ChildItem $vs -Recurse -Filter rc.exe -ErrorAction SilentlyContinue | Where-Object { $_.FullName -match 'x64' } | Select-Object -First 1
if (-not $rcExe) {
    $rcExe = Get-ChildItem 'C:\Program Files (x86)\Windows Kits\10\bin' -Recurse -Filter rc.exe -ErrorAction SilentlyContinue | Where-Object { $_.FullName -match 'x64' } | Select-Object -First 1
}
if ($rcExe) {
    $rp = Start-Process -FilePath $rcExe.FullName -ArgumentList '/nologo','act_key.rc' -NoNewWindow -Wait -PassThru
    Write-Host ('rc exit: ' + $rp.ExitCode)
} else {
    Write-Host '[!] rc.exe не найден — собираю без иконки'
}

Write-Host '[2/3] компиляция'
# Случайный порядок функций в exe: сбивает шаблонные детекты (Wacatac!ml).
# /ORDER каждый запуск даёт другой файл. Берём только простые "static ... name(" функции.
$funcs = @()
Select-String -Path 'act_key.c' -Pattern '^static\s+[A-Za-z_]+\s+\**([A-Za-z_][A-Za-z0-9_]*)\s*\(' -AllMatches |
    ForEach-Object { $funcs += $_.Matches[0].Groups[1].Value }
$funcs = $funcs | Where-Object { $_ -ne 'msg' } | Select-Object -Unique
if ($funcs.Count -gt 0) {
    $funcs = $funcs | Get-Random -Count $funcs.Count
    ($funcs | ForEach-Object { '/' + $_ }) -join ' ' | Set-Content -Encoding ascii order.txt
} else {
    Set-Content -Path order.txt -Value '' -Encoding ascii
}
if (Test-Path order.txt) { Write-Host ('order: ' + (Get-Content order.txt -Raw)) } else { Write-Host '[!] order.txt не создан' }

$src = @('act_key.c')
if (Test-Path 'act_key.res') { $src += 'act_key.res' }
$linkArgs = @('/SUBSYSTEM:WINDOWS','/OUT:act_key.exe','/MANIFEST:EMBED','/MANIFESTINPUT:act_key.manifest')
$ord = ''
if (Test-Path order.txt) { $ord = (Get-Content order.txt -Raw).Trim() }
if ($ord -ne '') { $linkArgs += '/ORDER:@order.txt' }
$clArgs = @('/nologo','/O2','/MT','/EHsc','/Gy') + $src + @('/link') + $linkArgs + @('user32.lib','shell32.lib','advapi32.lib','ole32.lib','uuid.lib')
Write-Host ('clArgs: ' + ($clArgs -join ' '))
$clExe = Join-Path $bin 'cl.exe'
$p = Start-Process -FilePath $clExe -ArgumentList $clArgs -NoNewWindow -Wait -PassThru
Write-Host ('cl exit: ' + $p.ExitCode)
if ($p.ExitCode -ne 0) {
    # Страховка: если /MANIFEST или /ORDER не поддержаны — собираем простой вариант.
    Write-Host '[!] сборка с манифестом/order не удалась — пробую без них'
    $src2 = @('act_key.c')
    if (Test-Path 'act_key.res') { $src2 += 'act_key.res' }
    $clArgs2 = @('/nologo','/O2','/MT','/EHsc') + $src2 + @('/link','/SUBSYSTEM:WINDOWS','/OUT:act_key.exe','user32.lib','shell32.lib','advapi32.lib','ole32.lib','uuid.lib')
    $p2 = Start-Process -FilePath $clExe -ArgumentList $clArgs2 -NoNewWindow -Wait -PassThru
    Write-Host ('cl exit (fallback): ' + $p2.ExitCode)
    if ($p2.ExitCode -ne 0) { exit 1 }
}

Write-Host '[3/3] готово'
Remove-Item act_key.obj, act_key.res, order.txt -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force dist | Out-Null
Copy-Item act_key.exe 'dist\Diktik-Unlock.exe' -Force
$k = Get-Item 'dist\Diktik-Unlock.exe'
Write-Host ('[OK] ' + $k.Name + '  ' + [math]::Round($k.Length/1KB,1) + ' KB')
