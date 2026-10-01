#!/usr/bin/env python3
"""Local Pitch timer. Chrome automation targets one tab and never types keys."""

import argparse
import json
import secrets
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
DEFAULT_INTERVAL = 20


def validate_interval(value):
    if type(value) is not int or not 1 <= value <= 3600:
        raise ValueError('Choose a whole number from 1 to 3600 seconds.')
    return value


def parse_deck(value):
    url = urlparse(value.strip())
    parts = url.path.strip('/').split('/')
    if url.scheme != 'https' or url.netloc != 'app.pitch.com' or len(parts) < 4 or parts[0] != 'app' or parts[1] not in ('presentation', 'player'):
        raise ValueError('Paste a full Pitch editor or presentation link.')
    try:
        workspace, deck = str(uuid.UUID(parts[2])), str(uuid.UUID(parts[3]))
        slide = '/' + str(uuid.UUID(parts[4])) if len(parts) > 4 else ''
    except ValueError as exc:
        raise ValueError('Paste a full Pitch editor or presentation link.') from exc
    return deck, f'https://app.pitch.com/app/player/{workspace}/{deck}{slide}'


def find_player(deck, tab=None, required=True, mode='player'):
    script = '''tell application "Google Chrome"
set matches to ""
repeat with w in windows
repeat with t in tabs of w
if URL of t contains "/app/''' + mode + '''/" and URL of t contains "''' + deck + '''" then
set matches to matches & (id of w as text) & " " & (id of t as text) & linefeed
end if
end repeat
end repeat
return matches
end tell'''
    result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=5)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    matches = [tuple(map(int, line.split())) for line in result.stdout.splitlines() if line.strip()]
    if tab is not None:
        matches = [pair for pair in matches if pair[1] == tab]
    if not matches:
        if not required:
            return None
        raise RuntimeError('The presentation tab was closed. Use Open deck to reopen it.')
    return matches[0]


def open_player(url, target=None):
    select = f'set w to window id {target[0]}\nset t to tab id {target[1]} of w' if target else 'set w to make new window\nset t to active tab of w'
    script = f'''tell application "Google Chrome"
{select}
if URL of t is not {json.dumps(url)} then set URL of t to {json.dumps(url)}
return (id of w as text) & " " & (id of t as text)
end tell'''
    result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=5)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return tuple(map(int, result.stdout.split()))


class Controller:
    def __init__(self):
        self.window, self.tab = None, None
        self.deck, self.deck_url = '', ''
        self.lock = threading.RLock()
        self.running = False
        self.interval = DEFAULT_INTERVAL
        self.remaining = self.interval
        self.deadline = 0
        self.info = {}
        self.message = 'Ready.'
        self.error = ''
        self.closed = False

    def set_interval(self, value):
        with self.lock:
            try:
                interval = validate_interval(value)
                self.pause()
                self.interval = interval
                self.remaining = interval
                self.error = ''
            except ValueError as exc:
                self.error = str(exc)
            return self.snapshot()

    def connect(self, value):
        with self.lock:
            self.pause()
            self.error = ''
            try:
                deck, url = parse_deck(value)
                self.info = {}
                self.deck, self.deck_url = deck, url
                match = find_player(deck, required=False) or find_player(deck, required=False, mode='presentation')
                if match and len(urlparse(url).path.strip('/').split('/')) == 4:
                    self.window, self.tab = match
                else:
                    self.window, self.tab = open_player(url, match)
                limit = time.monotonic() + 20
                while True:
                    try:
                        info = self.browser('prepare')
                        if info.get('ready') is False:
                            raise RuntimeError('Waiting for Pitch presentation mode')
                        self.info = info
                        break
                    except (RuntimeError, subprocess.TimeoutExpired):
                        if time.monotonic() >= limit:
                            raise RuntimeError('Pitch is not ready. Sign in or check access in the opened tab, then press Open deck again.')
                        time.sleep(.25)
                self.remaining = self.interval
            except Exception as exc:
                self.error = str(exc)
            return self.snapshot()

    def browser(self, action):
        if not self.window or not self.tab:
            raise RuntimeError('Paste a Pitch link and press Open deck.')
        js = '(() => { try { const DECK_ID = ' + json.dumps(self.deck) + '; const ACTION = ' + json.dumps(action) + '; return ' + (ROOT / 'pitch.js').read_text() + '; } catch (error) { return JSON.stringify({error: error.message}); } })()'
        script = f'tell application "Google Chrome" to execute tab id {self.tab} of window id {self.window} javascript {json.dumps(js)}'
        result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=5)
        if result.returncode:
            # A tab can move to another Chrome window during a presentation.
            window, _ = find_player(self.deck, self.tab)
            if window == self.window:
                raise RuntimeError(result.stderr.strip())
            self.window = window
            return self.browser(action)
        try:
            info = json.loads(result.stdout)
        except ValueError as exc:
            raise RuntimeError('Cannot read Pitch. Keep the target tab open in presentation mode.') from exc
        if info.get('error'):
            raise RuntimeError(info['error'])
        return info

    def pause(self, message='Paused. Resume keeps the remaining time.'):
        if self.running:
            self.remaining = max(0, self.deadline - time.monotonic())
        self.running = False
        self.message = message

    def move(self, action):
        before = self.browser(action)
        boundary = before['slide'] == (before['total'] if action == 'next' else 1)
        for _ in range(15):
            after = self.browser('read')
            if boundary or after['url'] != before['url']:
                self.info = after
                self.remaining = self.interval
                self.deadline = time.monotonic() + self.interval
                return
            time.sleep(.1)
        raise RuntimeError('Pitch did not change slides. Timer paused.')

    def action(self, action):
        with self.lock:
            self.error = ''
            try:
                if not self.info:
                    raise RuntimeError('Paste a Pitch link and press Open deck.')
                if action == 'pause':
                    self.pause()
                elif action == 'resume':
                    info = self.browser('read')
                    if info.get('url') != self.info.get('url') or self.remaining <= 0:
                        self.remaining = self.interval
                    self.info = info
                    self.deadline = time.monotonic() + self.remaining
                    self.running = True
                    self.message = f'Running. Each slide gets {self.interval} seconds.'
                elif action == 'reset':
                    self.remaining = self.interval
                    self.deadline = time.monotonic() + self.interval
                    self.message = f'Current slide reset to {self.interval} seconds.'
                elif action in ('next', 'previous'):
                    self.move(action)
                    self.message = f'Slide changed. Timer reset to {self.interval} seconds.'
                elif action == 'first':
                    self.pause()
                    self.info = self.browser('read')
                    for _ in range(self.info['total']):
                        if self.info['slide'] == 1:
                            break
                        self.move('previous')
                    self.remaining = self.interval
                    self.message = 'First slide ready. Press Start / Resume.'
                else:
                    raise ValueError('Unknown action')
            except Exception as exc:
                self.pause('Paused because Pitch could not be controlled.')
                self.error = str(exc)
            return self.snapshot()

    def snapshot(self):
        with self.lock:
            return {**self.info, 'running': self.running,
                    'interval': self.interval,
                    'connected': bool(self.info), 'deckUrl': self.deck_url,
                    'remaining': max(0, self.deadline - time.monotonic()) if self.running else self.remaining,
                    'deadlineMs': (time.time() + self.deadline - time.monotonic()) * 1000 if self.running else None,
                    'message': self.message, 'error': self.error}

    def run(self):
        last_tick = time.monotonic()
        last_read = 0
        while not self.closed:
            time.sleep(.05)
            with self.lock:
                now = time.monotonic()
                gap, last_tick = now - last_tick, now
                if not self.running:
                    if self.info and now - last_read >= 1:
                        try:
                            info = self.browser('read')
                            if info['url'] != self.info['url']:
                                self.remaining = self.interval
                            self.info = info
                        except Exception as exc:
                            self.info = {}
                            self.error = str(exc)
                        last_read = time.monotonic()
                    continue
                try:
                    if gap > 3:
                        self.pause('Paused after a system delay. Resume when ready.')
                        continue
                    if now >= self.deadline:
                        info = self.browser('read')
                        if info['url'] != self.info['url']:
                            self.info = info
                            self.deadline = time.monotonic() + self.interval
                        elif info['slide'] >= info['total']:
                            self.remaining = 0
                            self.running = False
                            self.message = 'Finished. The last slide stays on screen.'
                        else:
                            scheduled_deadline = self.deadline
                            self.move('next')
                            self.deadline = scheduled_deadline + self.interval
                        last_read = time.monotonic()
                    elif now - last_read >= .5:
                        info = self.browser('read')
                        if info['url'] != self.info['url']:
                            self.deadline = time.monotonic() + self.interval
                        self.info = info
                        last_read = time.monotonic()
                except Exception as exc:
                    self.pause('Paused because Pitch could not be controlled.')
                    self.error = str(exc)


def main():
    parser = argparse.ArgumentParser(description='Auto Advance: control Pitch slide timing from your browser.')
    parser.add_argument('--port', type=int, default=8765, help='Local server port (default: 8765)')
    parser.add_argument('--no-open', action='store_true', help='Start without opening the control page')
    args = parser.parse_args()
    controller = Controller()
    token = secrets.token_urlsafe(32)
    origin = f'http://127.0.0.1:{args.port}'

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, body, content_type='application/json'):
            data = body.encode() if isinstance(body, str) else body
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Frame-Options', 'DENY')
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.headers.get('Host') != f'127.0.0.1:{args.port}':
                self.reply(403, '{}')
            elif urlparse(self.path).path == '/':
                self.reply(200, (ROOT / 'index.html').read_text().replace('__TOKEN__', token), 'text/html; charset=utf-8')
            elif self.path == '/state' and self.headers.get('X-Pitch-Token') == token:
                self.reply(200, json.dumps(controller.snapshot()))
            else:
                self.reply(404, '{}')

        def do_POST(self):
            if self.headers.get('Origin') != origin or self.headers.get('X-Pitch-Token') != token:
                self.reply(403, '{}')
                return
            if self.path in ('/connect', '/interval'):
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 4096:
                        raise ValueError('Invalid request length')
                    field = 'deck' if self.path == '/connect' else 'interval'
                    value = json.loads(self.rfile.read(length))[field]
                    if field == 'deck' and not isinstance(value, str):
                        raise ValueError('Invalid deck')
                except (ValueError, KeyError, TypeError):
                    self.reply(400, '{}')
                    return
                state = controller.connect(value) if field == 'deck' else controller.set_interval(value)
                self.reply(200, json.dumps(state))
                return
            actions = {'resume', 'pause', 'reset', 'next', 'previous', 'first'}
            action = self.path.removeprefix('/')
            if action not in actions:
                self.reply(404, '{}')
                return
            self.reply(200, json.dumps(controller.action(action)))

    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    threading.Thread(target=controller.run, daemon=True).start()
    # Prevent sleep while this controller is open, including when it is paused.
    awake = subprocess.Popen(['caffeinate', '-di'])
    if not args.no_open:
        subprocess.run(['osascript', '-e', f'tell application "Google Chrome"\nset w to make new window\nset URL of active tab of w to "{origin}"\nset bounds of w to {{60, 80, 600, 850}}\nactivate\nend tell'], check=True)
    print(f'Pitch controller ready at {origin}', flush=True)
    try:
        server.serve_forever()
    finally:
        controller.closed = True
        awake.terminate()
        server.server_close()


if __name__ == '__main__':
    main()
