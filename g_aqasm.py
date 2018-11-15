#!/usr/bin/env python3
from gleditor import *
from glmemviewer import *
from time import time, sleep

class AQASMFrame(Frame):
    # Toolbar item IDs
    TB_ID_STEP = NewIdRef()
    TB_ID_RUN = NewIdRef()
    TB_ID_STOP = NewIdRef()
    TB_ID_RESET = NewIdRef()
    TB_ID_CLEARLOG = NewIdRef()
    # Bottom pane item IDs
    BP_CLOCKSPEED = NewIdRef()
    # CPU update events
    CPUUpdateEvent, EVT_CPU_UPDATE = wxNE.NewEvent()
    CPUStopEvent, EVT_CPU_STOP = wxNE.NewEvent()
    CPULogEvent, EVT_CPU_LOG = wxNE.NewEvent()

    def __init__(self, font, filename = None, size = (640, 480)):
        super(AQASMFrame, self).__init__(None, size = size)

        # Internals
        # Initialize interpreter
        self.cpu = aqasm("", False, 8, 256)
        # Mutex locks
        self.cpuLock = thread.allocate_lock()
        # Is code running
        self.runningCode = False
        # Clock speed variables
        self.clockspeed = 1000
        self.cycletime = 1 / self.clockspeed

        # Initialize and setup widgets
        # Splitter window
        splitter = SplitterWindow(self)
        leftPanel = Panel(splitter)
        rightPanel = Panel(splitter)
        splitter.SplitVertically(leftPanel, rightPanel, -300)
        splitter.SetSashGravity(1.0)
        splitter.SetMinimumPaneSize(300)
        # Menu bar
        menu = MenuBar()
        # File menu
        filemenu = Menu()
        newitem = filemenu.Append(ID_NEW, "New")
        openitem = filemenu.Append(ID_OPEN, "Open")
        saveitem = filemenu.Append(ID_SAVE, "Save")
        saveasitem = filemenu.Append(ID_SAVEAS, "Save as")
        filemenu.AppendSeparator()
        quititem = filemenu.Append(ID_EXIT, "Quit")
        menu.Append(filemenu, "&File")

        # Options menu
        optmenu = Menu()
        self.syntaxhitem = optmenu.Append(ID_ANY, "Syntax highlighting", kind=ITEM_CHECK)
        self.langextitem = optmenu.Append(ID_ANY, "Language extensions", kind=ITEM_CHECK)
        optmenu.Check(self.syntaxhitem.GetId(), True)
        optmenu.Check(self.langextitem.GetId(), True)
        menu.Append(optmenu, "&Options")

        # Windows menu
        winmenu = Menu()
        memwinitem = winmenu.Append(ID_ANY, "Show memory viewer")
        menu.Append(winmenu, "&Windows")
        # Menu bar - end
        self.SetMenuBar(menu)

        # Toolbar
        self.ToolBar = ToolBar(self, style=TB_HORIZONTAL | TB_TEXT | TB_NOICONS)
        self.ToolBar.AddTool(self.TB_ID_STEP, "Step", NullBitmap, "Step through code")
        self.ToolBar.AddTool(self.TB_ID_RUN, "Run", NullBitmap, "Run code")
        self.ToolBar.AddTool(self.TB_ID_STOP, "Stop", NullBitmap, "Stop running code")
        self.ToolBar.AddTool(self.TB_ID_RESET, "Reset", NullBitmap, "Reset interpreter")
        self.ToolBar.AddStretchableSpace()
        self.ToolBar.AddTool(self.TB_ID_CLEARLOG, "Clear", NullBitmap, "Clear interpreter log")
        self.ToolBar.EnableTool(self.TB_ID_STOP, False)
        self.ToolBar.Realize()
        # Bind toolbar button clicks
        self.ToolBar.Bind(EVT_TOOL, self.onToolbarClick)

        # Body
        # Editor canvas
        self.gleditor = GLEditor(leftPanel, font)
        # Expand editor canvas' pane
        leftSizer = BoxSizer(VERTICAL)
        leftSizer.Add(self.gleditor, 1, EXPAND, 0)
        leftPanel.SetSizer(leftSizer)

        # Logbox
        self.logbox = TextCtrl(rightPanel, -1,
                               style = TE_MULTILINE | TE_READONLY | TE_RICH)
        # Expand logbox's pane
        rightSizer = BoxSizer(VERTICAL)
        rightSizer.Add(self.logbox, 1, EXPAND, 0)
        rightPanel.SetSizer(rightSizer)

        # Special purpose registers bottom pane (and clock speed controller)
        pclabel = StaticText(self, label = "PC:")
        self.pcentry = TextCtrl(self, ID_ANY, "0", style = TE_RIGHT)
        self.signcheck = CheckBox(self, label = "Sign flag:", style = ALIGN_RIGHT)
        self.zerocheck = CheckBox(self, label = "Zero flag:", style = ALIGN_RIGHT)
        self.haltcheck = CheckBox(self, label = "Halt flag:", style = ALIGN_RIGHT)
        clockspeedlabel = StaticText(self, label = "Clock speed max. (Hz):")
        self.clockspeedentry = TextCtrl(self, self.BP_CLOCKSPEED, str(self.clockspeed), style = TE_RIGHT | TE_PROCESS_ENTER)
        # Bind checkbox checks and text updates
        self.clockspeedentry.Bind(EVT_TEXT_ENTER, self.onUpdateClockspeed)
        # Expand registers' bottom pane
        bottomSizer = BoxSizer(HORIZONTAL)
        bottomSizer.AddSpacer(5)
        bottomSizer.Add(pclabel, 0, ALIGN_CENTER_VERTICAL)
        bottomSizer.AddSpacer(5)
        bottomSizer.Add(self.pcentry, 0, ALIGN_CENTER_VERTICAL)
        bottomSizer.Add(self.signcheck, 0, ALIGN_CENTER_VERTICAL)
        bottomSizer.Add(self.zerocheck, 0, ALIGN_CENTER_VERTICAL)
        bottomSizer.Add(self.haltcheck, 0, ALIGN_CENTER_VERTICAL)
        bottomSizer.AddSpacer(5)
        bottomSizer.Add(clockspeedlabel, 0, ALIGN_CENTER_VERTICAL)
        bottomSizer.AddSpacer(5)
        bottomSizer.Add(self.clockspeedentry, 0, ALIGN_CENTER_VERTICAL)

        # Whole window
        windowSizer = BoxSizer(VERTICAL)
        windowSizer.Add(splitter, 1, EXPAND)
        windowSizer.Add(bottomSizer, 0, EXPAND)
        self.SetSizer(windowSizer)

        # Setup frame events
        self.Bind(EVT_MENU, self.onNewFile, newitem)
        self.Bind(EVT_MENU, self.onOpenFile, openitem)
        self.Bind(EVT_MENU, self.onSaveFile, saveitem)
        self.Bind(EVT_MENU, self.onSaveAsFile, saveasitem)
        self.Bind(EVT_MENU, self.onQuit, quititem)
        self.Bind(EVT_MENU, self.toggleSyntaxH, self.syntaxhitem)
        self.Bind(EVT_MENU, self.toggleLangExt, self.langextitem)
        self.Bind(EVT_MENU, self.showMemViewer, memwinitem)
        self.Bind(EVT_CLOSE, self.onClose)
        self.Bind(self.EVT_CPU_UPDATE, self.onCPUUpdate)
        self.Bind(self.EVT_CPU_STOP, self.onCPUStop)
        self.Bind(self.EVT_CPU_LOG, self.onCPULog)

        # Open file
        self.gleditor.openFile(filename)
        if filename == None:
            self.SetTitle("AQASM - New file")
        else:
            self.SetTitle("AQASM - " + filename)

        # Create memory viewer, but don't show it
        self.memviewer = GLMemViewer(self, self.cpu, font)

        # Set minimum size
        self.SetMinSize(size)
        # Show window and create GL contexts
        self.Show(True)
        self.gleditor.makeContext()
        self.memviewer.makeContext()

    def showMemViewer(self, event):
        self.memviewer.Show()
        self.memviewer.Raise()

    def modifiedWarning(self):
        # Ask for user confirmation
        if self.gleditor.modified:
            if MessageBox("Changes will not be saved! Proceed?",
                          "Confirmation required",
                          ICON_QUESTION | YES_NO, self
                          ) == NO:
                return True
        return False

    def onNewFile(self, event):
        if self.modifiedWarning():
            return

        # Create a new empty file
        self.gleditor.openFile(None)
        self.SetTitle("AQASM - New file")

    def onOpenFile(self, event):
        if self.modifiedWarning():
            return

        # Open file dialog
        with FileDialog(self, "Open AQASM file",
                        wildcard="AQASM files (*.aqasm)|*.aqasm",
                        style=FD_OPEN | FD_FILE_MUST_EXIST
                        ) as fileDialog:
            if fileDialog.ShowModal() == ID_CANCEL:
                return
            # Try opening the file
            self.gleditor.openFile(fileDialog.GetPath())
            self.SetTitle("AQASM - " + fileDialog.GetPath())

    def onSaveAsFile(self, event):
        # Save file dialog
        with FileDialog(self, "Save AQASM file",
                        wildcard="AQASM files (*.aqasm)|*.aqasm",
                        style=FD_SAVE | FD_OVERWRITE_PROMPT
                        ) as fileDialog:
            if fileDialog.ShowModal() == ID_CANCEL:
                return
            # Get save path
            newFilepath = fileDialog.GetPath()
            # If the file doesn't have the .aqasm extension, append it
            if len(newFilepath) < 7 or not newFilepath[-6:].lower().endswith(".aqasm"):
                newFilepath += ".aqasm"
            # Try saving the file
            self.gleditor.saveFile(newFilepath)
            self.SetTitle("AQASM - " + newFilepath)

    def onSaveFile(self, event):
        # If filename is None, do a save as, otherwise do a normal save
        if self.gleditor.filename == None:
            self.onSaveAsFile(event)
        else:
            self.gleditor.saveFile(self.gleditor.filename)
            self.SetTitle("AQASM - " + self.gleditor.filename)

    def onQuit(self, event):
        self.Close()

    def onClose(self, event):
        if self.modifiedWarning():
            return

        # Close CPU thread if it is running
        if self.runningCode:
            self.runningCode = False
            cyclesWaited = 0
            # Wait for it to die. If it doesnt die in 5 seconds, just close
            while self.cpuThreadRunning:
                if cyclesWaited >= 50:
                    break
                cyclesWaited += 1
                sleep(0.1)

        event.Skip()

    def log(self, *argv):
        for arg in argv:
            self.logbox.write(str(arg))
        self.logbox.write("\n")

    def compileIfNeeded(self):
        if self.gleditor.recompile:
            self.gleditor.recompile = False
            try:
                tstart = time()
                self.cpuLock.acquire()
                try:
                    self.cpu.compile_code(self.gleditor.filebuffer.tobytes().decode('ascii'), self.gleditor.langext, 8, 256)
                except Exception as e:
                    self.log(e)
                    self.gleditor.recompile = True
                else:
                    self.log('Info: Compiled successfuly in ', round(1000 * (time() - tstart), 4), ' milliseconds')
                finally:
                    self.cpuLock.release()
            except Exception as e:
                self.log("An exception occurred while compiling:\n", e)
                self.gleditor.recompile = True

    def runCodeLoop(self):
        self.cpuThreadRunning = True
        usingLock = False
        lastCycleTime = time()
        try:
            PostEvent(self, self.CPULogEvent(msg = ("CPU started", )))
            while self.runningCode:
                # Run CPU instruction cycle
                self.cpuLock.acquire()
                usingLock = True
                self.cpu.step()
                self.cpuLock.release()
                usingLock = False

                # Sleep to simulate clock speed. Does not lock CPU
                sleep(self.cycletime)

                # Stop CPU when halted
                if self.cpu.halt:
                    break

                # Send a CPU update event to change the UI 20 times a second.
                # If CPU update events are set too often, the UI freezes
                cycleTime = time()
                if cycleTime - lastCycleTime >= 0.05:
                    lastCycleTime = cycleTime
                    self.cpuLock.acquire()
                    usingLock = True
                    PostEvent(self, self.CPUUpdateEvent(zero = self.cpu.zero, sign = self.cpu.sign, halt = self.cpu.halt, pc = self.cpu.pc))
                    self.cpuLock.release()
                    usingLock = False
        except Exception as e:
            PostEvent(self, self.CPULogEvent(msg = ("An exception occured while running:\n", e)))
        else:
            PostEvent(self, self.CPULogEvent(msg = ("CPU stopped", )))
        finally:
            if usingLock:
                self.cpuLock.release()
            self.runningCode = False
            PostEvent(self, self.CPUStopEvent(zero = self.cpu.zero, sign = self.cpu.sign, halt = self.cpu.halt, pc = self.cpu.pc))
        self.cpuThreadRunning = False

    def onCPUUpdate(self, event):
        self.zerocheck.SetValue(event.zero)
        self.signcheck.SetValue(event.sign)
        self.haltcheck.SetValue(event.halt)
        self.pcentry.SetValue(str(event.pc))
        self.memviewer.canvas.Refresh()

    def onCPUStop(self, event):
        #self.zerocheck.SetValue(event.zero)
        #self.signcheck.SetValue(event.sign)
        #self.haltcheck.SetValue(event.halt)
        #self.pcentry.SetValue(str(event.pc))
        self.onCPUUpdate(event)
        self.ToolBar.EnableTool(self.TB_ID_STOP, False)
        self.ToolBar.EnableTool(self.TB_ID_RESET, True)

    def onCPULog(self, event):
        self.log(*event.msg)

    def onToolbarClick(self, event):
        button = event.GetId()
        if button == self.TB_ID_STEP:
            if not self.runningCode and self.gleditor.buffersize > 0:
                self.compileIfNeeded()
                if self.cpu.halt:
                    self.log("CPU is halted")
                elif not self.gleditor.recompile:
                    self.log("Stepping through line ", self.cpu.pc, ":")
                    self.log(self.cpu.code[self.cpu.pc])
                    self.cpu.step()
                    self.zerocheck.SetValue(self.cpu.zero)
                    self.signcheck.SetValue(self.cpu.sign)
                    self.haltcheck.SetValue(self.cpu.halt)
                    self.pcentry.SetValue(str(self.cpu.pc))
        elif button == self.TB_ID_RUN:
            if not self.runningCode and self.gleditor.buffersize > 0:
                self.compileIfNeeded()
                if not self.gleditor.recompile:
                    self.ToolBar.EnableTool(self.TB_ID_STOP, True)
                    self.ToolBar.EnableTool(self.TB_ID_RESET, False)
                    self.runningCode = True
                    thread.start_new_thread(self.runCodeLoop, ())
        elif button == self.TB_ID_STOP:
            if self.runningCode:
                self.runningCode = False
        elif button == self.TB_ID_RESET:
            if not self.runningCode:
                self.cpuLock.acquire()
                try:
                    self.cpu.reset()
                except Exception as e:
                    self.log("An exception occured while resetting: ", e)
                self.cpuLock.release()
                self.zerocheck.SetValue(self.cpu.zero)
                self.signcheck.SetValue(self.cpu.sign)
                self.haltcheck.SetValue(self.cpu.halt)
                self.pcentry.SetValue(str(self.cpu.pc))
                self.log("CPU reset")
                self.memviewer.canvas.Refresh()
        elif button == self.TB_ID_CLEARLOG:
            self.logbox.Clear()

    def onUpdateClockspeed(self, event):
        try:
            newclockspeed = int(self.clockspeedentry.GetValue())
            if newclockspeed > 0:
                self.clockspeed = newclockspeed
                self.cycletime = 1 / newclockspeed
                self.log("Updated max clock speed to ", self.clockspeed, "Hz")
                return
        except:
            pass
        self.log("New clock speed is not valid")
        self.clockspeedentry.SetValue(str(self.clockspeed))

    def toggleSyntaxH(self, event):
        self.gleditor.syntaxh = self.syntaxhitem.IsChecked()
        self.Refresh()

    def toggleLangExt(self, event):
        self.gleditor.recompile = True
        self.gleditor.langext = self.langextitem.IsChecked()

class AQASMApp(App):
    # Deriving from App. This method is superior to creating an App instance as
    # it makes sure that all widgets are initialised after showing the window.
    # This prevents the initial flicker from the normal way of doing this.
    def __init__(self, fontfile = "unscii-16", redirect = False, filename = None, useBestVisual = False, clearSigInt = True):
        # App calls OnInit... on __init__... Yeah. This means you must set all
        # variables before you call App's __init__, since OnInit depends on this
        # variable
        self.fontfile = fontfile

        # Initialise base class
        super(AQASMApp, self).__init__(redirect, filename, useBestVisual, clearSigInt)

    def OnInit(self):
        unscii = HexFont(self.fontfile)
        frame = AQASMFrame(unscii)
        self.SetTopWindow(frame)
        return True

if __name__ == "__main__":
    AQASMApp().MainLoop()
