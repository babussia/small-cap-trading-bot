#Requires AutoHotkey v2.0
#SingleInstance Force
#Warn

dir := A_ScriptDir
tradeFile := dir "\trade.txt"

; Create file if it doesn't exist
if !FileExist(tradeFile)
    FileAppend("", tradeFile)

lastSymbol := ""
lastSymbolSent := ""

Loop {
    try symbol := Trim(FileRead(tradeFile, "UTF-8"))
    catch
        continue

    ; Only react if symbol is non-empty and different from the last one read
    if (symbol != "" && symbol != lastSymbol) {
        lastSymbol := symbol
        TrayTip "Зміна файлу виявлена", "Символ: " symbol, 5

        ; Only send to TradeZero if it's different from last sent
        if (symbol != lastSymbolSent) {
            ; Find TradeZero window by process
            hwnd := ""
            windows := WinGetList()
            for w in windows {
                if WinGetProcessName(w) = "ZeroPro.exe" {
                    hwnd := w
                    break
                }
            }

            if !hwnd {
                ; Optionally, you can launch TradeZero here if needed
                ; Run "C:\Path\To\ZeroPro.exe"
                continue
            }

            ; Activate TradeZero window
            WinActivate(hwnd)
            Sleep 200

            CoordMode "Mouse", "Window"
            Click 6, 61  ; Replace with your Market Depth X,Y
            Sleep 100
            SendText symbol
            Sleep 50
            Send "{Enter}"

            ; Remember last symbol sent to avoid duplicates
            lastSymbolSent := symbol
        }
    }

    Sleep 500  ; check 2 times per second
}