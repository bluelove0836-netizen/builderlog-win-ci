# 빌더로그 설치 한 줄(Windows PowerShell):  irm {{ORIGIN}}/install.ps1 | iex
# English:  irm {{ORIGIN}}/en/install.ps1 | iex
# 빌더로그는 Windows 에서 WSL(우분투) 안에서 돌아요. 이 스크립트는 WSL 이 있는지만 보고,
# 있으면 우분투 안에서 macOS·리눅스와 같은 설치 한 줄을 실행해요. Windows 설정(레지스트리·실행 정책)은 바꾸지 않아요.
& {
  [Console]::OutputEncoding = [Text.Encoding]::UTF8
  $sh = 'curl -fsSL {{ORIGIN}}/install.sh | bash'
  # 안내 언어: 영어 주소(/en/install.ps1)면 서버가 {{LANG}} 을 en 으로 채운다. 우분투 안 설치 한 줄에도 같은 언어를 넘긴다(BUILDERLOG_LANG).
  $lang = "$env:BUILDERLOG_LANG".Trim().ToLower()
  if ($lang -ne 'en' -and $lang -ne 'ko') { $lang = '{{LANG}}' }
  if ($lang -eq 'en' -or $lang -eq 'ko') { $sh = $sh -replace '\| bash$', "| BUILDERLOG_LANG=$lang bash" }
  $en = $lang -eq 'en'
  # 윈도우 그대로(WSL 없이) — 지금은 BUILDERLOG_NATIVE=1 일 때만(팩별 윈도우 실측이 끝나면 기본으로). 파이썬 3.10+ → %USERPROFILE%\builderlog\get.py → 마법사.
  # 파이썬이 없으면 winget 으로 이 사용자에게만(관리자 권한 없이) 설치한다. 스토어 바로가기 python.exe 는 버전 확인으로 걸러진다.
  if ("$env:BUILDERLOG_NATIVE" -eq '1') {
    if ($en) {
      Write-Host 'Builderlog setup (Windows, no WSL): Python 3.10+ (installed for this user if missing) -> helper in %USERPROFILE%\builderlog -> connect your AI tools.'
    } else {
      Write-Host '빌더로그 설치(Windows 그대로, WSL 없이): 파이썬 3.10+ (없으면 이 사용자에게만 설치) → 도우미 %USERPROFILE%\builderlog → AI 도구 연결.'
    }
    $ok = { param($exe, $pre) try { (& $exe @pre -c "import sys;print(sys.version_info[:2]>=(3,10))" 2>$null) -eq 'True' } catch { $false } }
    $py = $null; $pre = @()
    if ((Get-Command py.exe -ErrorAction SilentlyContinue) -and (& $ok 'py.exe' @('-3'))) { $py = 'py.exe'; $pre = @('-3') }
    elseif ((Get-Command python.exe -ErrorAction SilentlyContinue) -and (& $ok 'python.exe' @())) { $py = 'python.exe' }
    if (-not $py) {
      if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
        if ($en) { Write-Host 'Python 3.10 or newer is needed. Install it from https://www.python.org/downloads/windows/ (tick "Add python.exe to PATH"), then paste this line again.' }
        else { Write-Host '파이썬 3.10 이상이 필요해요. https://www.python.org/downloads/windows/ 에서 설치("Add python.exe to PATH" 체크)한 뒤 이 한 줄을 다시 붙여 넣어 주세요.' }
        return
      }
      if ($en) { Write-Host 'Installing Python 3.12 for this user only (no admin needed)...' } else { Write-Host '파이썬 3.12 를 이 사용자에게만 설치해요(관리자 권한 필요 없음)…' }
      winget.exe install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements | Out-Null
      $cand = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
      if (Test-Path $cand) { $py = $cand } elseif (Get-Command py.exe -ErrorAction SilentlyContinue) { $py = 'py.exe'; $pre = @('-3') }
      if (-not $py) {
        if ($en) { Write-Host 'Python did not install. Close this window, open a new one and paste this line again.' } else { Write-Host '파이썬 설치가 끝나지 않았어요. 이 창을 닫고 새 창에서 이 한 줄을 다시 붙여 넣어 주세요.' }
        return
      }
    }
    $root = if ($env:BUILDERLOG_HOME) { $env:BUILDERLOG_HOME } else { Join-Path $env:USERPROFILE 'builderlog' }
    [IO.Directory]::CreateDirectory($root) | Out-Null  # 내 빌더로그 폴더만(설정은 안 바꿈)
    if ($lang -eq 'en' -or $lang -eq 'ko') { Set-Content -Path (Join-Path $root 'lang') -Value $lang -Encoding ascii }
    $base = if ($env:BUILDERLOG_SERVER) { $env:BUILDERLOG_SERVER.TrimEnd('/') } else { '{{ORIGIN}}' }
    Invoke-WebRequest -UseBasicParsing -Uri "$base/get.py" -OutFile (Join-Path $root 'get.py.new')
    Move-Item -Force (Join-Path $root 'get.py.new') (Join-Path $root 'get.py')
    $get = Join-Path $root 'get.py'
    # 사람이 붙였으면 대화형 마법사, AI 도구(Claude Code·Codex)가 실행하면 질문 없이 도우미 받기 + AI 도구 연결까지만(설치 한 줄 install.sh 와 같은 규칙)
    $ai = "$env:CLAUDECODE$env:CLAUDE_CODE_ENTRYPOINT$env:CODEX_SANDBOX$env:CODEX_MANAGED_BY_NPM"
    if ($env:BUILDERLOG_YES) { & $py @pre $get wizard --yes }
    elseif ($ai -or [Console]::IsInputRedirected -or [Console]::IsOutputRedirected) { & $py @pre $get wizard --connect-only }
    else { & $py @pre $get wizard }
    return
  }
  if ($en) {
    Write-Host 'Builderlog setup (Windows): here is the plan'
    Write-Host '  1. Check that WSL (Ubuntu) is installed (if not, you only get the steps to install it)'
    Write-Host "  2. If it is, run this inside Ubuntu: $sh"
    Write-Host '     (it shows the plan again and asks before going on; Windows settings are not changed)'
  } else {
    Write-Host '빌더로그 설치(Windows) — 이렇게 해요:'
    Write-Host '  1. WSL(우분투)이 있는지 확인해요(없으면 설치 방법만 알려 드려요)'
    Write-Host "  2. 있으면 우분투 안에서 실행: $sh"
    Write-Host '     (할 일을 다시 보여 주고 물어본 뒤 진행해요. Windows 설정은 바꾸지 않아요)'
  }
  # WSL 이 아예 없으면 wsl.exe 가 설치하라며 키를 기다릴 수 있어서, 등록된 배포판이 있을 때만(레지스트리는 읽기만) wsl -l -q 로 확인해요.
  # wsl -l -q 는 UTF-16 으로 나와서 NUL 을 지워요. docker-desktop 은 우분투가 아니라서 빼요.
  $distros = @()
  if ((Get-Command wsl.exe -ErrorAction SilentlyContinue) -and (Get-ChildItem HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss -ErrorAction SilentlyContinue)) {
    $list = (wsl.exe -l -q) -replace "`0", ''
    if ($LASTEXITCODE -eq 0) { $distros = @($list | Where-Object { $_.Trim() -and $_ -notmatch 'docker-desktop' }) }
  }
  if (-not $distros) {
    if ($en) {
      Write-Host "WSL (Ubuntu) is needed. Open PowerShell from the Start menu with 'Run as administrator', run  wsl --install -d Ubuntu , restart the computer, then paste this line again."
      Write-Host '  irm {{ORIGIN}}/en/install.ps1 | iex'
    } else {
      Write-Host "WSL(우분투)이 필요해요. 시작 메뉴에서 PowerShell 을 '관리자 권한으로 실행'한 뒤  wsl --install -d Ubuntu  를 실행하고, 컴퓨터를 다시 켠 다음 이 한 줄을 다시 붙여 넣어 주세요."
      Write-Host '  irm {{ORIGIN}}/install.ps1 | iex'
    }
    return
  }
  wsl.exe -e bash -lc "set -o pipefail; $sh"
  if ($LASTEXITCODE -eq 127) {
    if ($en) {
      Write-Host 'Ubuntu has no curl. Open Ubuntu from the Start menu, run  sudo apt update && sudo apt install -y curl , then paste this line again.'
    } else {
      Write-Host '우분투에 curl 이 없어요. 시작 메뉴에서 Ubuntu 를 열어  sudo apt update && sudo apt install -y curl  을 실행한 뒤 이 한 줄을 다시 붙여 넣어 주세요.'
    }
  } elseif ($LASTEXITCODE -ne 0) {
    if ($en) {
      Write-Host "Setup did not finish (code $LASTEXITCODE). Check the messages above, then paste this line again (it is safe to rerun). Help: hello@builderlog.net"
    } else {
      Write-Host "설치가 끝나지 않았어요(코드 $LASTEXITCODE). 위 안내를 확인한 뒤 이 한 줄을 다시 붙여 넣어 주세요(다시 해도 안전해요). 도움: hello@builderlog.net"
    }
  }
}
