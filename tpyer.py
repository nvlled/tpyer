
from os import path
import sys
import time
from random import random
import pynput
from PyQt5.QtWidgets import *
from xdo import Xdo
from main_ui import Ui_MainWindow
from pynput.keyboard import Key, Controller, Listener as KeyListener
from quamash import QEventLoop, QThreadExecutor
import asyncio
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from watchdog.observers.api import ObservedWatch
from PyQt5.QtCore import pyqtSignal
from threading import Thread
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

ttsEngine = pyttsx3.init()
ttsEngine.setProperty("rate", 220)
ttsEngine.setProperty("voice", "whisper")

class Tpyer:

    winID = -1
    selfWinID = -1
    fileWatch = None
    loadingFile = False
    watchedFilename = ""
    playing = False
    keyListener = None

    def __init__(self):
        ui.textTypeSpeed.hide()
        ui.buttonReload.hide()

        ui.buttonSelectWin.clicked.connect(self.onSelectWin)
        ui.actionOpen_File.triggered.connect(self.onSelectFile)
        ui.buttonPlay.clicked.connect(self.onPlay)
        ui.buttonStop.clicked.connect(self.onStop)
        win.loadFileSignal.connect(self.loadFile)

        # stop typing when esc key is pressed
        def onKeypress(key):
            if key == Key.esc:
                print("esc pressed, stopping")
                self.onStop()

        self.keyListener =  KeyListener(on_press=onKeypress)
        t = Thread(target=lambda : self.keyListener.run())
        t.start()


    def show(self):
        win.show()
        self.selfWinID = xd.get_active_window()

    async def typeText(self, text, delay):
        id = self.winID
        ttsEngine.say(text)
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
            keyboard.press(k)
            keyboard.release(k)

            if ch == " ":
                await asyncio.sleep(0.01 + random() * delay*2)
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

    def onStop(self):
        ttsEngine.stop()
        self.playing = False

    def onPlay(self):
        id = self.winID
        if id == self.selfWinID or id < 0:
            self.showStatus("no valid window selected")
            return

        lines = [item.text() for item in ui.listLines.selectedItems()]

        if not lines:
            self.showStatus("select lines to type")
            return

        async def run():
            self.playing = True
            xd.raise_window(id)
            delay = 0.05

            self.showStatus("typing...")
            for line in lines:
                await self.typeText(line, delay)
                await asyncio.sleep(delay*2.5);
                if not self.playing:
                    break

            self.showStatus("done.")
            self.playing = False
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
    import signal
    # exit when ctrl-c'ed from the terminal
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    tp.show()
    fileObserver.start()
    Thread(target=lambda : ttsEngine.startLoop()).start()

    with loop:
        loop.run_forever()

    sys.exit(0)


