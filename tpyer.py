
from os import path, _exit
import sys
import time
import signal
from random import random
import pynput
from PyQt5.QtWidgets import *
from xdo import Xdo
from main_ui import Ui_MainWindow
from pynput.keyboard import KeyCode, Key, Controller, Listener as KeyListener
from quamash import QEventLoop, QThreadExecutor
import asyncio
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from watchdog.observers.api import ObservedWatch
from PyQt5.QtCore import pyqtSignal, pyqtProperty, Qt
from PyQt5.QtGui import QColor
from threading import Thread
from concurrent.futures import ThreadPoolExecutor
import pyttsx3

class MainWindow(QMainWindow):
    loadFileSignal = pyqtSignal(object)

app = QApplication(sys.argv)
loop = QEventLoop(app)
asyncio.set_event_loop(loop)
win = MainWindow()
ui = Ui_MainWindow()
ui.setupUi(win)
xd = Xdo()
keyboard = Controller()
fileObserver = Observer()

voices = [
    "m1",
    "f1",
    "m4",
    "m7",
    "f5",
    "croak",
    "klatt1",
    "klatt4",
    "whisper",
    "whisperf",
]
ttsEngine = pyttsx3.init()

# map [0, 100] to [1, 0.001]
def typeSpeedToMs(x): return 1 - x/100*(1-0.001)

# map [0, 100] to [0, 240]
def speechSpeedToRate(x): return int(x/100 * 240)

class Tpyer:
    winID = -1
    selfWinID = -1
    fileWatch = None
    loadingFile = False
    watchedFilename = ""
    playing = False
    keyListener = None

    initSpeechSpeed = 60
    initTypeSpeed   = 80

    def __init__(self):
        ui.numType.setRange(0, 100)
        ui.numSpeech.setRange(0, 100)
        ui.buttonSelectWin.clicked.connect(self.onSelectWin)
        ui.actionOpen_File.triggered.connect(self.onSelectFile)
        ui.buttonTypeSpeak.clicked.connect(lambda : self.onPlay(canType=True, canSpeak=True))
        ui.buttonType.clicked.connect(lambda : self.onPlay(canType=True, canSpeak=False))
        ui.buttonSpeak.clicked.connect(lambda : self.onPlay(canType=False, canSpeak=True))
        ui.buttonStop.clicked.connect(self.onStop)
        ui.numSpeech.valueChanged.connect(self.onNumSpeechChange)
        win.loadFileSignal.connect(self.loadFile)

        ui.cmbVoice.clear()
        ui.cmbVoice.addItems(voices)
        ui.cmbVoice.currentTextChanged.connect(self.onCmbVoiceChange)

        ui.numSpeech.setValue(self.initSpeechSpeed)
        ui.numType.setValue(self.initTypeSpeed)

        # stop playing when esc key is pressed
        def onKeypress(key):
            if key == Key.esc:
                print("esc pressed, stopping")
                self.onStop()

        self.keyListener =  KeyListener(on_press=onKeypress)

    def show(self):
        win.show()
        self.selfWinID = xd.get_active_window()

    async def typeText(self, text, delay):
        id = self.winID
        for ch in text:
            k = ch
            if ch == "\n":
                k = Key.enter
            elif ch == "\t":
                k = Key.tab

            try:
                xd.activate_window(id)
            except:
                continue

            try:
                keyboard.press(k)
                keyboard.release(k)
            except:
                print("untypable key: {}".format(ch))

            if ch == " ":
                await asyncio.sleep(0.01 + random() * delay*1.3)
            else:
                await asyncio.sleep(0.01 + random() * delay)

            if not self.playing:
                return

    def onSelectFile(self):
        filename, _ = QFileDialog.getOpenFileName(win)
        if not filename:
            return
        self.loadFile(filename)

    def loadFile(self, filename):
        if self.loadingFile:
            return

        print("loading file: " + filename)
        async def run():
            self.loadingFile = True
            ui.listLines.clear()
            with open(filename, "r") as f:
                for line in f.readlines():
                    item = QListWidgetItem()
                    item.setText(line)
                    ui.listLines.addItem(item)

            if self.fileWatch and self.watchedFilename != filename:
                print("uncheduling watch on :" + filename)
                fileObserver.unschedule(self.fileWatch)
                self.fileWatch = None
                handler = self.FSUpdateHandler(self, filename)
                self.fileWatch = fileObserver.schedule(handler, path.dirname(filename))
            elif not self.fileWatch:
                handler = self.FSUpdateHandler(self, filename)
                self.fileWatch = fileObserver.schedule(handler, path.dirname(filename))

            self.watchedFilename = filename
            self.loadingFile = False
        loop.create_task(run())

    def setPlaying(self, val):
        ui.buttonTypeSpeak.setEnabled(not val)
        ui.buttonType.setEnabled(not val)
        ui.buttonSpeak.setEnabled(not val)
        ui.buttonStop.setEnabled(val)
        self.playing = val

    def onStop(self):
        self.setPlaying(False)
        ttsEngine.stop()

    def getDelay(self):
        return typeSpeedToMs(ui.numType.value())

    def onNumSpeechChange(self, val):
        rate = speechSpeedToRate(val)
        print("change speech rate: {} => {}".format(val, rate))
        ttsEngine.setProperty("rate", rate)

    def onCmbVoiceChange(self, val):
        print("change voice: {}".format(val))
        ttsEngine.setProperty("voice", val)

    def onPlay(self, canSpeak=True, canType=True):
        if self.playing:
            return

        id = self.winID
        if canType and (id == self.selfWinID or id < 0):
            self.showStatus("select a window to type text on")
            return

        lines = [item.text() for item in ui.listLines.selectedItems()]

        if not lines:
            self.showStatus("select lines to type or speak")
            return

        self.setPlaying(True)
        async def run():
            if canType:
                xd.raise_window(id)

            delay = self.getDelay()
            self.showStatus("playing... press esc to stop")
            for line in lines:
                if not self.playing:
                    break
                if canSpeak:
                    ttsEngine.say(line)
                if canType:
                    await self.typeText(line, delay)
                while ttsEngine.isBusy():
                    await asyncio.sleep(0.15);

            self.showStatus("done.")
            self.setPlaying(False)
        loop.create_task(run())

    def onSelectWin(self):
        ui.buttonSelectWin.setEnabled(False)
        async def run():
            id = xd.select_window_with_click()

            if id == self.selfWinID:
                ui.buttonSelectWin.setEnabled(True)
                return;

            self.winID = id;
            winname = str(xd.get_window_name(self.winID))
            self.showStatus("selected window: id={}   name={} ".format(id, winname))
            ui.buttonSelectWin.setEnabled(True)
        loop.create_task(run())

    def showStatus(self, msg):
        win.statusBar().showMessage(msg)
        print(msg)

    class FSUpdateHandler(FileSystemEventHandler):
        def __init__(self, tp, filename):
            self.tp = tp
            self.filename = filename

        def on_modified(self, event):
            if event.src_path == self.filename:
                print("reloading...")
                win.loadFileSignal.emit(self.filename)

tp = Tpyer()

if __name__ == "__main__":
    # exit when ctrl-c'ed from the terminal
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    tp.show()
    fileObserver.start()

    executor = ThreadPoolExecutor(max_workers=10)
    executor.submit(ttsEngine.startLoop)
    executor.submit(tp.keyListener.run)

    with loop:
        loop.run_forever()

    # Without explicit exit, the main thread just
    # indefinitely blocks and wait for other
    # threads to stop, which doesn't happen.
    # I actualy tried stopping each one of them,
    # but it still has a 1/3 chance of hanging up.
    # Of course, I'm probably doing something wrong,
    # but this serves as a nice duct tape.
    _exit(0)

