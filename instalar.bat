@echo off
rem Instalador de RSI Monitor para Windows: hagan doble clic en este archivo.
rem Todo el trabajo lo hace instalar.ps1 (ver ahi que hace cada paso).
rem Este archivo va sin tildes y con fin de linea CRLF, para que cmd lo lea bien.
title Instalando RSI Monitor
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar.ps1" %*
if errorlevel 1 pause
