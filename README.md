# Auto Advance

Double-click `Launch.command`, paste a Pitch editor or presentation link, and press **Open deck**. The controller opens the presentation in Chrome, or reuses its player if already open. Then press **Start**.

Use **Change deck** to choose another presentation. Opening a deck pauses the timer and gives the selected slide a full interval. There is no saved configuration or default deck. If Pitch requires sign-in, sign in in the opened window and press **Open deck** again.

Set **Seconds per slide** and press **Apply** to change the interval. It defaults to 20 seconds and accepts whole numbers from 1 to 3600. Applying an interval pauses and resets the current countdown. The chosen interval lasts until the server stops.

- Start or Resume advances slides at the chosen interval.
- Pause preserves the time left.
- Previous and Next give the current slide a full interval.
- First slide pauses and returns to slide 1.
- The timer stops after the last slide's interval.
- Manual slide changes while running also restart the countdown.
- The finish time includes the current slide's remaining time and one interval per later slide. While paused, it shows when you would finish if you started now.

Keep Pitch on the presentation screen and the controller on your laptop. It controls one Pitch tab without switching focus. Moving that tab to another Chrome window is supported. Keep the Terminal process running; closing the controller browser window does not stop the timer. Press Control-C in Terminal to stop the process.

This uses Python 3, macOS AppleScript, and Chrome's **View → Developer → Allow JavaScript from Apple Events** setting (already enabled on the tested Mac). It only listens on your computer. It prevents display and system sleep while running. If Pitch closes, leaves presentation mode, or fails to change slides, the timer pauses with an error. A system delay longer than three seconds also pauses it.

Start with `python3 server.py` and choose a deck in the UI. The only server options are `--port` to change the local port and `--no-open` to start without opening the control page. Deck selection and timing are handled in the UI.

The control page also accepts a `deck` query parameter. Build the link as `location.origin + '/?deck=' + encodeURIComponent(pitchUrl)`, using your full Pitch link for `pitchUrl`. Opening that link connects the deck automatically and leaves the timer paused. Reloading it while already connected to the same link preserves the current timer. You can bookmark the link without creating a settings file.

Reload the controller page after restarting the process.

Pitch's slide buttons and counter are read from its page. Changes to Pitch's interface may require updating `pitch.js`.
