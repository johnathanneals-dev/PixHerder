Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Projects\Duped"
WshShell.Run """C:\Program Files\Python313\python.exe"" ""C:\Projects\Duped\dupefinder_app.py""", 7, False
