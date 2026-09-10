@echo off
setlocal
cd /d "%~dp0..\..\.."
set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
set "LOG_FILE=%~dp0minimax_controlnet_diagnostic.log"
if not exist "%PYTHON_EXE%" (
    echo Python environment not found: %PYTHON_EXE%
    pause
    exit /b 1
)
echo Starting ComfyUI with the model compiler disabled.
echo When the server is ready, open http://127.0.0.1:8188 and run minimax_controlnet.json.
echo Live output below is also saved to: %LOG_FILE%
powershell.exe -NoProfile -Command "& $env:PYTHON_EXE -u -X faulthandler main.py --fast-disk --preview-method latent2rgb --use-sage-attention --disable-comfy-compiler 2>&1 | Tee-Object -FilePath $env:LOG_FILE; exit $LASTEXITCODE"
set "EXIT_CODE=%ERRORLEVEL%"
echo ComfyUI exited with code %EXIT_CODE%.
pause
exit /b %EXIT_CODE%
