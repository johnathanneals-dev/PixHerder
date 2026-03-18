Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Projects\Duped"
WshShell.Run """C:\Program Files\Python313\python.exe"" ""C:\Projects\Duped\dupefinder_app.py""", 0, False
WScript.Sleep 2000
WshShell.Run "http://127.0.0.1:8787", 1, False
