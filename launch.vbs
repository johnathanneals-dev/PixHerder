Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Projects\Duped"
WshShell.Run """C:\Program Files\Python313\pythonw.exe"" ""C:\Projects\Duped\dupefinder_app.py""", 1, False
