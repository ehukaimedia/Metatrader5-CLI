@echo off
setlocal
REM Edit this path if MetaEditor is installed elsewhere.
set METAEDITOR=%ProgramFiles%\MetaTrader 5\MetaEditor64.exe

if not exist "%METAEDITOR%" (
  echo MetaEditor64.exe not found at: %METAEDITOR%
  echo Edit METAEDITOR in this file or compile manually in MetaEditor.
  exit /b 1
)

set ROOT=%~dp0
"%METAEDITOR%" /compile:"%ROOT%MQL5\Indicators\Advanced_OrderFlow_Proxy_Confluence.mq5" /log:"%ROOT%compile_orderflow_proxy.log"
"%METAEDITOR%" /compile:"%ROOT%MQL5\Indicators\Advanced_Wavelet_Entry_Signal.mq5" /log:"%ROOT%compile_indicator.log"
"%METAEDITOR%" /compile:"%ROOT%MQL5\Experts\Advanced_Wavelet_Entry_ResearchEA.mq5" /log:"%ROOT%compile_ea.log"

echo Compile commands finished. Review compile_orderflow_proxy.log, compile_indicator.log and compile_ea.log.
endlocal
