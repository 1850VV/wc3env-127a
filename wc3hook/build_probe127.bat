@echo off
setlocal
if /i "%VSCMD_ARG_TGT_ARCH%"=="x86" goto compile
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" exit /b 1
for /f "usebackq tokens=*" %%i in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VS_DIR=%%i"
if not defined VS_DIR exit /b 1
call "%VS_DIR%\VC\Auxiliary\Build\vcvars32.bat" >nul || exit /b 1
:compile
cd /d "%~dp0"
if not exist out\probe127 mkdir out\probe127
cl /nologo /O2 /W3 /WX /LD /I minhook\include probe127.c probe127_objects.c objects127.c commands127.c instance.c clock.c minhook\src\buffer.c minhook\src\hook.c minhook\src\trampoline.c minhook\src\hde\hde32.c /Fo:out\probe127\ /Fe:out\probe127\wc3probe127.dll /link ole32.lib user32.lib || exit /b 1
echo Built research probe only; production package DLL unchanged.
