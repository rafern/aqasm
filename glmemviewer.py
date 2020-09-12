from interpreter import *
from hexfont import *
from glsubwindow import *
from math import floor, ceil

class GLMemViewer(GLSubWindow):
    def __init__(self, parent, cpu, gllock, font, size = DefaultSize):
        super(GLMemViewer, self).__init__(parent, "Memory viewer", gllock, (67 * font.width, 384))

        # AQASM interpreter used for fetching memory
        self.cpu = cpu
        # Memory viewer internal variables
        self.selOffset = self.selRegister = self.screenOffset = 0
        # Flags
        self.initializeViewer = self.showOffsets = self.showDots = self.showHex = self.showStatus = True
        # Set used font
        self.font = font

        # Menu bar
        menu = MenuBar()
        # Tools menu
        toolsmenu = Menu()
        gotoitem = toolsmenu.Append(ID_ANY, "Go to...")
        menu.Append(toolsmenu, "&Tools")
        # View menu
        viewmenu = Menu()
        self.showOffsetsItem = viewmenu.Append(ID_ANY, "Show offsets pane", kind=ITEM_CHECK)
        self.showHexItem = viewmenu.Append(ID_ANY, "Show hexadecimal pane", kind=ITEM_CHECK)
        self.showDotsItem = viewmenu.Append(ID_ANY, "Show unprintable ASCII as dots", kind=ITEM_CHECK)
        self.showStatusItem = viewmenu.Append(ID_ANY, "Show status pane", kind=ITEM_CHECK)
        viewmenu.Check(self.showOffsetsItem.GetId(), True)
        viewmenu.Check(self.showHexItem.GetId(), True)
        viewmenu.Check(self.showDotsItem.GetId(), True)
        viewmenu.Check(self.showStatusItem.GetId(), True)
        menu.Append(viewmenu, "&View")
        # Menu bar - end
        self.SetMenuBar(menu)

        # Binds
        # Menu callbacks
        self.Bind(EVT_MENU, self.onGoTo, gotoitem)
        # Bind checkboxes
        self.Bind(EVT_MENU, self.toggleOffsets, self.showOffsetsItem)
        self.Bind(EVT_MENU, self.toggleHex, self.showHexItem)
        self.Bind(EVT_MENU, self.toggleDots, self.showDotsItem)
        self.Bind(EVT_MENU, self.toggleStatus, self.showStatusItem)
        # Bind button presses
        self.canvas.Bind(EVT_CHAR, self.onKeydown)
        self.canvas.Bind(EVT_LEFT_DOWN, self.onMousedown)

    def resizeCanvas(self):
        # Update pre-calculated limits
        if self.canvasSize != None:
            self.addrLen = self.cpu.wordLength // 4
            self.hexFormat = '{:0' + str(self.addrLen) + 'x}'
            self.cols = self.canvasSize[0] // self.font.width
            self.rows = self.canvasSize[1] // 16
            if self.showStatus:
                self.registerValueWidth = 5 + self.addrLen
                self.registersPerRow = floor(self.cols / self.registerValueWidth)
                self.registerRows = ceil(13 / self.registersPerRow)
                self.rows = self.rows - 4 - self.registerRows
                self.statusOffset = self.rows * 16
            self.recalcColOffsets()
            self.updateCursor()

    def updateCursor(self):
        if self.selOffset < 0:
            self.selOffset = 0
        elif self.selOffset >= self.cpu.memWords:
            self.selOffset = self.cpu.memWords - 1
        if self.screenOffset > self.selOffset // self.wordsPerLine:
            self.screenOffset = self.selOffset // self.wordsPerLine
        elif self.screenOffset + self.rows - 1 <= self.selOffset // self.wordsPerLine:
            self.screenOffset = self.selOffset // self.wordsPerLine - self.rows + 1

    def moveDelta(self, dx, dy):
        update = False

        if dx < 0 and self.selOffset > 0:
            self.selOffset += dx
            update = True
        elif dx > 0 and self.selOffset < self.cpu.memWords - 1:
            self.selOffset += dx
            update = True

        if dy < 0 and self.selOffset > 0:
            self.selOffset += self.wordsPerLine * dy
            update = True
        elif dy > 0 and self.selOffset < self.cpu.memWords - 1:
            self.selOffset += self.wordsPerLine * dy
            update = True

        if update:
            self.updateCursor()
            self.canvas.Refresh()

    def onKeydown(self, event):
        keycode = event.GetKeyCode()
        update = False
        default = False
        # Process key events
        if keycode == WXK_LEFT:
            self.moveDelta(-1, 0)
        elif keycode == WXK_RIGHT:
            self.moveDelta(1, 0)
        elif keycode == WXK_UP:
            self.moveDelta(0, -1)
        elif keycode == WXK_DOWN:
            self.moveDelta(0, 1)
        elif keycode == WXK_PAGEUP:
            self.moveDelta(0, -self.rows)
        elif keycode == WXK_PAGEDOWN:
            self.moveDelta(0, +self.rows)
        elif keycode == WXK_HOME:
            self.selOffset = (self.selOffset // self.wordsPerLine) * self.wordsPerLine
            update = True
        elif keycode == WXK_END:
            self.selOffset = (self.selOffset // self.wordsPerLine + 1) * self.wordsPerLine - 1
            if self.selOffset >= self.cpu.memWords:
                self.selOffset = self.cpu.memWords - 1
            update = True
        else:
            default = True

        if update:
            # Redraw
            self.canvas.Refresh()
        if default:
            # Also run default handler
            event.Skip()

    def onMousedown(self, event):
        x, y = event.GetPosition()
        xOff = 0

        # Try register selection if in status bar and if it shown
        if self.showStatus and y >= self.statusOffset:
            # Abort if cursor is outside the register list area
            if x >= self.registersPerRow * self.registerValueWidth * self.font.width:
                return
            elif y < self.statusOffset + 64:
                return
            elif y >= self.statusOffset + 64 + self.registerRows * 16:
                return

            # Get register selection
            row = (y - self.statusOffset) // 16 - 4
            col = (x // self.font.width) // self.registerValueWidth
            reg = row * self.registersPerRow + col
            if reg < 13:
                self.selRegister = reg
                # Also redraw viewer
                self.Refresh()
        else:
            # Abort if cursor is too to the right
            if x >= (self.asciiColOffset + self.wordsPerLine * self.cpu.bytesPerWord * self.font.width):
                return

            # Check wether hex pane is shown or not
            if self.showHex:
                # Abort if in offset pane
                if x < self.hexColOffset:
                    return

                # Check if in hex or ascii pane
                if x < self.asciiColOffset:
                    xOff = (x - self.hexColOffset) // ((self.addrLen + 1) * self.font.width)
                else:
                    xOff = (x - self.asciiColOffset) // (self.font.width * self.cpu.bytesPerWord)
            else:
                # Abort if in offset pane
                if x < self.asciiColOffset:
                    return

                xOff = (x - self.asciiColOffset) // (self.font.width * self.cpu.bytesPerWord)

            # Get y offset
            yOff = y // 16 + self.screenOffset
            self.selOffset = yOff * self.wordsPerLine + xOff

            # Update cursor position
            self.updateCursor()
            self.Refresh()

    def recalcColOffsets(self):
        # Update column offsets depending on what views are enabled
        colsAvailable = self.cols
        curOffset = 0

        # Partially calculate offsets if the offset view is enabled
        if self.showOffsets:
            curOffset = 1 + self.addrLen
            colsAvailable -= curOffset
        # ... if hex view is enabled
        if self.showHex:
            self.hexCol = curOffset
            self.hexColOffset = self.hexCol * self.font.width
            self.wordsPerLine = colsAvailable // (self.addrLen + 1 + self.cpu.bytesPerWord)
            # Ratio between hex view to ASCII view is (addrLen + 1):(bytesPerWord), so...
            self.asciiCol = curOffset + self.wordsPerLine * (self.addrLen + 1)
            self.asciiColOffset = self.asciiCol * self.font.width
        else:
            self.wordsPerLine = colsAvailable
            self.asciiCol = curOffset
            self.asciiColOffset = self.asciiCol * self.font.width

    def drawWord(self, word, x, y, xOff = 0, yOff = 0):
        # Make hex string from word
        hexStr = self.hexFormat.format(word)
        # Draw hex string
        self.font.drawString(hexStr, x, y, xOff, yOff)

    def redrawCanvas(self):
        # If not yet initialized, initialize it
        if self.initializeViewer:
            # Setup orthographic projection
            self.updateOrtho()
            # Enable alpha blending
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            # Set clear color
            glClearColor(0.15,0.15,0.15,1)
            # Flag as initialized
            self.initializeViewer = False
            self.font.genTexture()

        # Clear buffer
        glClear(GL_COLOR_BUFFER_BIT)

        # Draw panes
        glBegin(GL_QUADS)
        # The second pane always has a light background and dark text. Determine
        # which pane is the second pane depending on which panes are hidden
        renderLightPane = True
        lightPaneLeft = 0
        lightPaneRight = self.canvasSize[0]
        if self.showOffsets:
            if self.showHex:
                # Hex pane is light
                lightPaneLeft = self.hexColOffset
                lightPaneRight = self.asciiColOffset
            else:
                # Ascii pane is light
                lightPaneLeft = self.asciiColOffset
        else:
            if self.showHex:
                # Ascii pane is light
                lightPaneLeft = self.asciiColOffset
            else:
                # Else no pane is light
                renderLightPane = False

        # Draw light pane
        glColor3f(0.85,0.8,0.8)
        if renderLightPane:
            glVertex2f(lightPaneLeft, 0)
            glVertex2f(lightPaneRight, 0)
            glVertex2f(lightPaneRight, self.canvasSize[1])
            glVertex2f(lightPaneLeft, self.canvasSize[1])

        # Draw status pane
        if self.showStatus:
            glVertex2f(0, self.statusOffset)
            glVertex2f(self.canvasSize[0], self.statusOffset)
            glVertex2f(self.canvasSize[0], self.canvasSize[1])
            glVertex2f(0, self.canvasSize[1])

        glColor3f(1,1,1)
        glEnd()

        # Draw ascii and hex values
        glEnable(GL_TEXTURE_2D)
        glBegin(GL_QUADS)

        # Draw offset pane
        if self.showOffsets:
            for y in range(0, self.rows):
                yOffset = (y + self.screenOffset) * self.wordsPerLine
                if yOffset >= self.cpu.memWords:
                    break
                self.drawWord(yOffset, 0, y)

        # Draw hex pane
        if self.showHex:
            # Set color to contrast with background if hex pane is light
            if self.showOffsets:
                glColor3f(0.15,0.15,0.15)

            # Draw hex words
            breakOutOfRows = False
            for y in range(0, self.rows):
                lineOffset = (y + self.screenOffset) * self.wordsPerLine
                for w in range(0, self.wordsPerLine):
                    # Find offset of this position
                    thisOffset = lineOffset + w
                    # Stop if exceeded words limit
                    if thisOffset >= self.cpu.memWords:
                        breakOutOfRows = True
                        break
                    # Print word
                    self.drawWord(oputil_ldr(self.cpu, thisOffset), w * (self.addrLen + 1), y, self.hexColOffset)
                if breakOutOfRows:
                    break

        # Draw ASCII pane
        # Set color to contrast with background if hex pane is light
        if (self.showOffsets and not self.showHex) or (not self.showOffsets and self.showHex):
            glColor3f(0.15,0.15,0.15)
        else:
            glColor3f(1,1,1)

        # Draw ASCII chars
        breakOutOfRows = False
        for y in range(0, self.rows):
            lineOffset = (y + self.screenOffset) * self.wordsPerLine * self.cpu.bytesPerWord
            for b in range(0, self.wordsPerLine * self.cpu.bytesPerWord):
                thisOffset = lineOffset + b
                if thisOffset >= self.cpu.memBytes:
                    breakOutOfRows = True
                    break
                thisChar = self.cpu.mem[thisOffset]
                if self.showDots and ((thisChar < 32) or (thisChar > 126)):
                    # Draw dot when hexDots are enabled
                    self.font.drawGlyph(46, b, y, self.asciiColOffset)
                else:
                    self.font.drawGlyph(thisChar, b, y, self.asciiColOffset)
            if breakOutOfRows:
                break

        # Draw status pane chars
        if self.showStatus:
            glColor3f(0.15, 0.15, 0.15)
            offsetVal = oputil_ldr(self.cpu, self.selOffset)
            intValText = "Integer value: " + str(aqasmutil_int2str(self.cpu, offsetVal))
            floatValText = "Float value: " + str(aqasmutil_float2str(self.cpu, offsetVal))
            regIntValText = "Register integer value: " + str(aqasmutil_int2str(self.cpu, self.cpu.reg[self.selRegister]))
            regFloatValText = "Register float value: " + str(aqasmutil_float2str(self.cpu, self.cpu.reg[self.selRegister]))
            self.font.drawString(intValText, 0, 0, 0, self.statusOffset)
            self.font.drawString(floatValText, 0, 1, 0, self.statusOffset)
            self.font.drawString(regIntValText, 0, 2, 0, self.statusOffset)
            self.font.drawString(regFloatValText, 0, 3, 0, self.statusOffset)

            # Draw register values
            regX = regY = 0
            for r in range(0, 13):
                # Render register and hex value
                self.font.drawString('R{:02d}:'.format(r), regX * self.registerValueWidth, 4 + regY, 0, self.statusOffset)
                self.drawWord(self.cpu.reg[r], 4 + regX * self.registerValueWidth, 4 + regY, 0, self.statusOffset)

                # Move right and to next row if neccessary
                regX += 1
                if regX == self.registersPerRow:
                    regX = 0
                    regY += 1

        glEnd()
        glDisable(GL_TEXTURE_2D)

        # Draw cursor
        glBlendFunc(GL_ONE_MINUS_DST_COLOR, GL_ZERO)
        glBegin(GL_QUADS)
        glColor3f(1,1,1)

        # Status pane cursor
        if self.showStatus:
            statusQuadTop = ((self.selRegister // self.registersPerRow) + 4) * 16 + self.statusOffset
            statusQuadBottom = statusQuadTop + 16
            statusQuadLeft = (self.selRegister % self.registersPerRow) * self.font.width * self.registerValueWidth
            statusQuadRight = statusQuadLeft + self.registerValueWidth * self.font.width
            glVertex2f(statusQuadLeft, statusQuadTop)
            glVertex2f(statusQuadRight, statusQuadTop)
            glVertex2f(statusQuadRight, statusQuadBottom)
            glVertex2f(statusQuadLeft, statusQuadBottom)

        # ASCII pane cursor
        hOffset = self.selOffset % self.wordsPerLine
        quadTop = ((self.selOffset // self.wordsPerLine) - self.screenOffset) * 16
        quadBottom = quadTop + 16
        asciiQuadLeft = self.asciiColOffset + hOffset * self.cpu.bytesPerWord * self.font.width
        asciiQuadRight = asciiQuadLeft + self.font.width * self.cpu.bytesPerWord
        glVertex2f(asciiQuadLeft, quadTop)
        glVertex2f(asciiQuadRight, quadTop)
        glVertex2f(asciiQuadRight, quadBottom)
        glVertex2f(asciiQuadLeft, quadBottom)

        # Hex pane cursor
        if self.showHex:
            hexQuadLeft = self.hexColOffset + hOffset * (self.addrLen + 1) * self.font.width
            hexQuadRight = hexQuadLeft + self.font.width * (self.addrLen + 1)
            glVertex2f(hexQuadLeft, quadTop)
            glVertex2f(hexQuadRight, quadTop)
            glVertex2f(hexQuadRight, quadBottom)
            glVertex2f(hexQuadLeft, quadBottom)

        glEnd()
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glFlush()

    def onGoTo(self, event):
        newOffset = GetNumberFromUser("Enter offset:", "Decimal", "Go to...", 0, 0, self.cpu.memWords, self)
        if newOffset != -1:
            self.selOffset = newOffset
            self.updateCursor()
            self.Refresh()

    def toggleOffsets(self, event):
        self.showOffsets = self.showOffsetsItem.IsChecked()
        self.resizeCanvas()
        self.Refresh()

    def toggleHex(self, event):
        self.showHex = self.showHexItem.IsChecked()
        self.resizeCanvas()
        self.Refresh()

    def toggleDots(self, event):
        self.showDots = self.showDotsItem.IsChecked()
        self.resizeCanvas()
        self.Refresh()

    def toggleStatus(self, event):
        self.showStatus = self.showStatusItem.IsChecked()
        self.resizeCanvas()
        self.Refresh()
