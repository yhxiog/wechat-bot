@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 微信聊天机器人
echo.
echo ================================================
echo   微信 4.x 智能聊天机器人
echo ================================================
echo.
python bot.py
echo.
echo [机器人已退出]
pause
