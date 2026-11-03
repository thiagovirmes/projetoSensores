@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0apresentar.ps1"
if errorlevel 1 echo Falha na apresentacao. Leia a mensagem acima.
pause
