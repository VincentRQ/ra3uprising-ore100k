@echo off
rem Ore100K launcher for C&C Red Alert 3: Uprising (Steam)
rem 1) borderless fullscreen helper (alt-tab safe, no D3D9 device loss)
rem 2) Ore100KPatcher: ore node cap 30000 -> 100000 (all mines, all players)
setlocal

set SHORT=C:\Users\VQuim\DOCUME~1\DEFAUL~1
set PATCH=C:\Users\VQuim\AppData\Local\RA3Ore100K
set GAME_EXE=D:\SteamLibrary\steamapps\common\Command and Conquer Red Alert 3 Uprising\RA3EP1.exe

start "" powershell -NoProfile -ExecutionPolicy Bypass -File "%SHORT%\borderless-helper.ps1" -ProcessName "ra3ep1_1.1.game"
start "" "%PATCH%\Ore100KPatcher.exe" "ra3ep1_1.1.game" 25 240
start "" "%GAME_EXE%" -win
