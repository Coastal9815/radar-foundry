' Run MRW Lightning pipeline hidden (no console window). Launched from Startup.
' Brief delay so session is fully initialized before NexStorm/relay start.
WScript.Sleep 10000
CreateObject("WScript.Shell").Run "cmd /c C:\MRW\lightning\start_lightning_pipeline.bat", 0, False
