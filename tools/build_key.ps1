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
$src = @('act_key.c')
if (Test-Path 'act_key.res') { $src += 'act_key.res' }
$clArgs = @('/nologo','/O2','/MT','/EHsc') + $src + @('/link','/SUBSYSTEM:WINDOWS','/OUT:act_key.exe','user32.lib','shell32.lib','advapi32.lib','ole32.lib','uuid.lib')
$clExe = Join-Path $bin 'cl.exe'
$p = Start-Process -FilePath $clExe -ArgumentList $clArgs -NoNewWindow -Wait -PassThru
Write-Host ('cl exit: ' + $p.ExitCode)
if ($p.ExitCode -ne 0) { exit 1 }

Write-Host '[3/3] готово'
Remove-Item act_key.obj, act_key.res -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force dist | Out-Null
Copy-Item act_key.exe 'dist\Diktik-Unlock.exe' -Force
$k = Get-Item 'dist\Diktik-Unlock.exe'
Write-Host ('[OK] ' + $k.Name + '  ' + [math]::Round($k.Length/1KB,1) + ' KB')
