# Pitch's missing auto advance controller

```sh
python3 server.py
```

This uses Python 3, macOS AppleScript, and Chrome's **View → Developer → Allow JavaScript from Apple Events** setting. It only listens on your computer. It prevents display and system sleep while running. If Pitch closes, leaves presentation mode, or fails to change slides, the timer pauses with an error. A system delay longer than three seconds also pauses it.
