from interpreter import *
from hexfont import *
from gldefaultcanvas import *
from array import array

class GLEditor(GLDefaultCanvas):
    def __init__(self, parent, cpu, gllock, font):
        super(GLEditor, self).__init__(parent, gllock)

        # AQASM interpreter used for getting word range
        self.cpu = cpu
        # Flag as editor context initialization and redraw needed
        self.initializeEditor = self.syntaxh = self.langext = True
        # Set used font
        self.font = font
        # Editor variables
        self.tabSize = 8
        self.cumulXScroll = self.cumulYScroll = 0

        # Bind button presses
        self.Bind(EVT_CHAR, self.onKeydown)
        self.Bind(EVT_MOTION, self.onMousemove)
        self.Bind(EVT_LEFT_DOWN, self.onMousedown)
        self.Bind(EVT_MOUSEWHEEL, self.onMousewheel)

    def resetEditor(self):
        # Reset buffer, drag origin, real (counting tabsize) and screen coords
        self.x = self.y = self.dox = self.doy = self.rx = self.rdox = self.sx = self.sy = 0

    def lineEnd(self, i):
        # Get line end
        lend = self.buffersize
        if i + 1 < len(self.lines):
            lend = self.lines[i + 1]
        return lend

    def lineLength(self, i):
        return self.lineEnd(i) - self.lines[i]

    def updateCursor(self, updateDragOrigin):
        # Update real cursor coords
        self.rx = 0
        offset = self.lines[self.y]
        for x in range(self.x):
            if self.filebuffer[offset + x] == 9: # Horizontal tab
                self.rx = (self.rx // self.tabSize + 1) * self.tabSize
            elif self.filebuffer[offset + x] == 10: # Line feed
                pass
            else:
                self.rx += 1

        # Update real drag origin coords
        if updateDragOrigin:
            self.rdox = 0
            offset = self.lines[self.doy]
            for x in range(self.dox):
                if self.filebuffer[offset + x] == 9: # Horizontal tab
                    self.rdox = (self.rdox // self.tabSize + 1) * self.tabSize
                elif self.filebuffer[offset + x] == 10: # Line feed
                    pass
                else:
                    self.rdox += 1

        # Update screen coords
        # X
        if self.rx - self.sx < 4:
            self.sx = self.rx - 4
        elif self.rx - self.sx > self.maxX - 4:
            self.sx = self.rx + 4 - self.maxX
        if self.sx < 0:
            self.sx = 0
        # Y
        if self.y - self.sy < 4:
            self.sy = self.y - 4
        elif self.y - self.sy > self.maxY - 4:
            self.sy = self.y + 4 - self.maxY
        lineCount = len(self.lines)
        if self.sy + self.maxY >= lineCount:
            self.sy = lineCount - self.maxY - 1
        if self.sy < 0:
            self.sy = 0

    def seekPos(self, x, y, drag):
        lineCount = len(self.lines)

        # If too far down (after max line), go to end of file
        if y >= lineCount:
            self.y = lineCount - 1
            self.x = self.lineLength(self.y)

            # If not a drag, then set the drag origin
            if not drag:
                self.doy = self.y
                self.dox = self.x
            return

        self.y = y
        offset = self.lines[self.y]
        self.x = seekX = 0
        lineLength = self.lineLength(self.y)

        # Special case if last line, since the last line doesn't finish with
        # a line feed, resulting in an early seek
        if y + 1 == lineCount:
            lineLength += 1
        for self.x in range(lineLength):
            # Stop on overseek
            if seekX >= x:
                break

            bufPos = offset + self.x
            # Horizontal tab
            if bufPos != self.buffersize and self.filebuffer[bufPos] == 9:
                seekX = (seekX // self.tabSize + 1) * self.tabSize
                # Special case: pick the tab's character instead of after it if
                # x never reaches the next character (inbetween tab and char.)
                if x < seekX:
                    break
            else:
                seekX += 1

        # If not a drag, then set the drag origin
        if not drag:
            self.doy = self.y
            self.dox = self.x

    def shiftLineEnds(self, pivot, shift):
        for l in range(pivot + 1, len(self.lines)):
            self.lines[l] += shift
        self.buffersize += shift

    def updatePaneSize(self):
        self.linePaneSize = len(str(len(self.lines))) + 1
        self.linePaneRight = self.font.width * self.linePaneSize

    def updateTokens(self, l):
        lstart = self.lines[l]
        lend = self.lineEnd(l)
        self.tokens[l] = compiler.compiler_lexical_analysis(self.filebuffer[lstart:lend].tobytes().decode("ascii"), self.cpu.intMin, self.cpu.intMax, self.cpu.memWords - 1, self.cpu.bytesPerWord, self.langext)[1]

    def updateAllTokens(self):
        for l in range(len(self.lines)):
            self.updateTokens(l)

    def typeChar(self, char):
        self.modified = True
        self.recompile = True
        offset = self.lines[self.y]
        self.filebuffer.insert(offset + self.x, char)
        self.shiftLineEnds(self.y, 1)
        if char == 10:
            self.lines.insert(self.y + 1, offset + self.x + 1)
            self.tokens.insert(self.y, None)
            self.updateTokens(self.y)
            self.x = 0
            self.y += 1
        else:
            self.x += 1
        self.doy = self.y
        self.dox = self.x
        self.updateTokens(self.y)
        self.updatePaneSize()

    def delSelection(self):
        self.modified = True
        self.recompile = True

        # Get selection's pivot (side closest to (0,0))
        pivX = pivY = endX = endY = 0
        if self.y == self.doy:
            pivY = endY = self.y
            pivX = min(self.x, self.dox)
            endX = max(self.x, self.dox)
        elif self.y < self.doy:
            pivX = self.x
            pivY = self.y
            endX = self.dox
            endY = self.doy
        else:
            pivX = self.dox
            pivY = self.doy
            endX = self.x
            endY = self.y

        # Delete characters in range
        pivPos = self.lines[pivY] + pivX
        endPos = self.lines[endY] + endX

        del self.filebuffer[pivPos:endPos]

        # Delete lines
        if endY > pivY:
            del self.lines[pivY + 1:endY + 1]

        # Shift line ends
        self.shiftLineEnds(pivY, pivPos - endPos)

        # Move cursor to pivot
        self.x = self.dox = pivX
        self.y = self.doy = pivY
        self.updateCursor(True)

        # Update tokens
        self.updateAllTokens()

    def delChar(self):
        self.modified = True
        self.recompile = True
        bufPos = self.lines[self.y] + self.x
        if bufPos < self.buffersize:
            if self.filebuffer[bufPos] == 10: # If an LF, merge lines
                self.lines.pop(self.y + 1)
                self.tokens.pop(self.y + 1)
            self.filebuffer.pop(bufPos)
            self.shiftLineEnds(self.y, -1)
            self.updatePaneSize()
            self.updateTokens(self.y)

    def backspaceChar(self):
        bufPos = self.lines[self.y] + self.x
        if bufPos > 0:
            if self.x == 0:
                self.y -= 1
                self.x = bufPos - 1 - self.lines[self.y]
            else:
                self.x -= 1
            self.doy = self.y
            self.dox = self.x
            self.delChar()

    def resizeCanvas(self):
        # Update pre-calculated limits
        self.linePaneRight = self.font.width * self.linePaneSize
        self.statusY = self.canvasSize.height // 16 - 1
        self.statusTop = self.statusY * 16
        self.statusCols = self.canvasSize.width // self.font.width
        self.maxX = self.statusCols - self.linePaneSize + 1
        self.maxY = self.statusY - 1
        # Update cursor
        self.updateCursor(False)

    def moveDelta(self, dx, dy, drag):
        if dx != 0:
            # Since lineLength return line length including LF, if not the last
            # line, remove 1 from the lineMaxX
            lineMaxX = self.lineLength(self.y)
            if self.y + 1 < len(self.lines):
                lineMaxX -= 1
            self.x += dx
            if self.x < 0:
                self.x = 0
            elif self.x > lineMaxX:
                self.x = lineMaxX

        while dy < 0:
            dy += 1
            if self.y > 0:
                self.seekPos(self.rx, self.y - 1, drag)
            else:
                break

        if dy > 0:
            lineLimit = len(self.lines) - 1
            while dy > 0:
                dy -= 1
                if self.y < lineLimit:
                    self.seekPos(self.rx, self.y + 1, drag)
                else:
                    break

        if not drag:
            self.dox = self.x
            self.doy = self.y

        self.updateCursor(not drag)
        self.Refresh()

    def moveToSelPivot(self):
        # Get selection's pivot (side closest to (0,0))
        pivX = pivY = endX = endY = 0
        if self.y == self.doy:
            pivY = endY = self.y
            pivX = min(self.x, self.dox)
            endX = max(self.x, self.dox)
        elif self.y < self.doy:
            pivX = self.x
            pivY = self.y
            endX = self.dox
            endY = self.doy
        else:
            pivX = self.dox
            pivY = self.doy
            endX = self.x
            endY = self.y

        # Move cursor to pivot
        self.x = self.dox = pivX
        self.y = self.doy = pivY

        # Update
        self.updateCursor(True)
        self.Refresh()

    def copySelection(self):
        # Get selection's pivot (side closest to (0,0)) and end
        pivX = pivY = endX = endY = 0
        if self.y == self.doy:
            pivY = endY = self.y
            pivX = min(self.x, self.dox)
            endX = max(self.x, self.dox)
        elif self.y < self.doy:
            pivX = self.x
            pivY = self.y
            endX = self.dox
            endY = self.doy
        else:
            pivX = self.dox
            pivY = self.doy
            endX = self.x
            endY = self.y

        # Get selection's pivot and end in buffer
        pivPos = self.lines[pivY] + pivX
        endPos = self.lines[endY] + endX

        if not TheClipboard.IsOpened():
            data = TextDataObject()
            data.SetText(self.filebuffer[pivPos:endPos].tobytes())
            TheClipboard.Open()
            TheClipboard.SetData(data)
            TheClipboard.Close()

    def textCut(self):
        if self.dox != self.x or self.doy != self.y:
            self.copySelection()
            self.delSelection()
            self.Refresh()

    def textCopy(self):
        self.copySelection()
        self.moveToSelPivot()

    def textPaste(self):
        if not TheClipboard.IsOpened():
            data = TextDataObject()
            TheClipboard.Open()
            success = TheClipboard.GetData(data)
            TheClipboard.Close()
            if success:
                try:
                    text = data.GetText().encode('ascii')
                except:
                    with MessageDialog(None,
                            "Clipboard text is not valid ASCII",
                            "Could not paste text",
                            OK | ICON_INFORMATION) as dialog:
                        dialog.ShowModal()
                else:
                    if self.dox != self.x or self.doy != self.y:
                        self.delSelection()

                    # Filter out carriage returns due to Windows line endings
                    text = array('B', [c for c in text if c != 13])

                    # Insert text in buffer
                    pos = self.lines[self.y] + self.x
                    pasteSize = len(text)
                    self.filebuffer[pos:pos] = text
                    self.shiftLineEnds(self.y, pasteSize)

                    # Insert lines into line list, move cursor and update tokens
                    for i in range(pos, pos + pasteSize):
                        # Add line when the character is a line feed
                        if self.filebuffer[i] == 10:
                            self.lines.insert(self.y + 1, i + 1)
                            self.tokens.insert(self.y + 1, None)
                            self.updateTokens(self.y)
                            self.y += 1
                            self.x = 0
                        else:
                            self.x += 1

                    # Also update tokens on last line
                    self.updateTokens(self.y)

                    # Update drag origin
                    self.dox = self.x
                    self.doy = self.y

                    # Update
                    self.modified = True
                    self.recompile = True
                    self.updateCursor(True)
                    self.Refresh()

    def textSelectAll(self):
        # Set drag origin to 0, 0 and cursor to end of file
        self.doy = self.dox = 0
        self.y = len(self.lines) - 1
        self.x = self.buffersize - self.lines[self.y]

        # Update
        self.updateCursor(True)
        self.Refresh()

    def onKeydown(self, event):
        keycode = event.GetKeyCode()
        update = False
        default = True
        drag = False
        selecting = self.dox != self.x or self.doy != self.y
        # Process key events
        if keycode == WXK_LEFT:
            drag = event.ShiftDown()
            default = False
            # moveDelta redraws, so update doesn't have to be set to true
            self.moveDelta(-1, 0, drag)
        elif keycode == WXK_RIGHT:
            drag = event.ShiftDown()
            default = False
            self.moveDelta(1, 0, drag)
        elif keycode == WXK_UP:
            drag = event.ShiftDown()
            default = False
            self.moveDelta(0, -1, drag)
        elif keycode == WXK_DOWN:
            drag = event.ShiftDown()
            default = False
            self.moveDelta(0, 1, drag)
        elif keycode == WXK_DELETE:
            if selecting:
                self.delSelection()
            else:
                self.delChar()
            drag = False
            update = True
        elif keycode == WXK_BACK:
            if selecting:
                self.delSelection()
            else:
                self.backspaceChar()
            drag = False
            update = True
        elif keycode == WXK_HOME:
            drag = event.ShiftDown()
            self.x = 0
            if not drag:
                self.dox = 0
            update = True
        elif keycode == WXK_END:
            drag = event.ShiftDown()
            self.x = self.lineLength(self.y)
            if self.y + 1 < len(self.lines):
                self.x -= 1
            if not drag:
                self.dox = self.x
            update = True
        elif keycode == WXK_PAGEUP:
            drag = event.ShiftDown()
            self.moveDelta(0, -self.maxY // 2, drag)
        elif keycode == WXK_PAGEDOWN:
            drag = event.ShiftDown()
            self.moveDelta(0, self.maxY // 2, drag)
        elif (keycode >= 32 and keycode <= 126) or keycode == WXK_TAB or keycode == WXK_RETURN:
            if keycode == WXK_TAB:
                keycode = 9
                default = False
            elif keycode == WXK_RETURN:
                keycode = 10
            if selecting:
                self.delSelection()
            self.typeChar(keycode)
            update = True

        if update:
            # Update cursor
            self.updateCursor(not drag)
            # Redraw
            self.Refresh()
        if default:
            # Also run default handler
            event.Skip()

    def onMouseGeneric(self, event, drag):
        x, y = event.GetPosition()
        x -= self.linePaneRight

        # Move if in the editor's bounds
        if y < self.statusTop and x >= 0 and y >= 0:
            # Set the drag start and move the cursor
            newX = self.sx + (x // self.font.width)
            newY = self.sy + (y // 16)
            self.seekPos(newX, newY, drag)

            # Update cursor and redraw
            self.updateCursor(not drag)
            self.Refresh()

        # Also run default handler
        event.Skip()

    def onMousemove(self, event):
        # Move the cursor only if dragging
        if event.Dragging():
            self.onMouseGeneric(event, True)

    def onMousedown(self, event):
        self.onMouseGeneric(event, False)

    def onMousewheel(self, event):
        threshold = event.GetWheelDelta()
        drag = event.ShiftDown()
        if event.GetWheelAxis() == MOUSE_WHEEL_HORIZONTAL:
            self.cumulXScroll += event.GetWheelRotation()
            moveX = self.cumulXScroll // threshold
            self.cumulXScroll = self.cumulXScroll % threshold
            self.moveDelta(moveX, 0, drag)
        else:
            self.cumulYScroll -= event.GetWheelRotation()
            moveY = self.cumulYScroll // threshold
            self.cumulYScroll = self.cumulYScroll % threshold
            self.moveDelta(0, moveY, drag)

    def redrawCanvas(self):
        # If not yet initialized, initialize it
        if self.initializeEditor:
            # Setup orthographic projection
            self.updateOrtho()
            # Setup font texture and bind it
            self.font.genTexture()
            # Enable alpha blending
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            # Set clear color
            glClearColor(0.15,0.15,0.15,1)
            # Flag as initialized
            self.initializeEditor = False

        # Clear buffer
        glClear(GL_COLOR_BUFFER_BIT)

        # Begin drawing panes
        glBegin(GL_QUADS)
        # Draw line number pane
        glColor3f(0.2,0.2,0.2)
        glVertex2f(0, 0)
        glVertex2f(self.linePaneRight, 0)
        glVertex2f(self.linePaneRight, self.statusTop)
        glVertex2f(0, self.statusTop)
        glColor3f(0.85,0.8,0.8)
        glVertex2f(0, self.statusTop)
        glVertex2f(self.canvasSize.width, self.statusTop)
        glVertex2f(self.canvasSize.width, self.canvasSize.height)
        glVertex2f(0, self.canvasSize.height)
        glColor3f(1,1,1)
        # Draw footer pane
        glEnd()

        glEnable(GL_TEXTURE_2D)
        glBegin(GL_QUADS)
        # Draw each line
        clearHigh = False
        for l in range(self.sy, min(self.sy + self.maxY + 1, len(self.lines))):
            # If highlighting triggered, reset gl color
            if clearHigh:
                glColor3f(1,1,1)
                clearHigh = False

            # Write line number in pane
            lineNumStr = str(l + 1)
            for c in range(len(lineNumStr)):
                self.font.drawGlyph(ord(lineNumStr[c]), c, l - self.sy)

            if l > self.sy + self.maxY:
                break

            # Get line end
            lend = self.lineEnd(l)

            # Syntax highlighting flags
            tokenCount = len(self.tokens[l])
            lastToken = 0

            # Print line
            x = self.linePaneSize
            lstart = self.lines[l]
            for i in range(lstart, lend):
                c = self.filebuffer[i]

                # Syntax highlighting triggers
                if self.syntaxh and lastToken < tokenCount:
                    if i - lstart >= self.tokens[l][lastToken][0]:
                        thisToken = self.tokens[l][lastToken][1]
                        if thisToken == compiler.token.comment:
                            glColor3f(0.5,0.5,0.5)
                        elif thisToken == compiler.token.whitespace or thisToken == compiler.token.separator or thisToken == compiler.token.identifier:
                            glColor3f(1,1,1)
                        elif thisToken == compiler.token.decimal:
                            glColor3f(0.9,0.9,0.4)
                        elif thisToken == compiler.token.floating:
                            glColor3f(1,0.5,0.75)
                        elif thisToken == compiler.token.address:
                            glColor3f(0,0.6,0.9)
                        elif thisToken == compiler.token.register:
                            glColor3f(0.7,0,0.7)
                        elif thisToken == compiler.token.labelid or thisToken == compiler.token.label:
                            glColor3f(0.1,0.6,0.1)
                        elif thisToken == compiler.token.error:
                            glColor3f(0.9,0,0)
                        clearHigh = True
                        lastToken += 1

                if x > self.sx + self.maxX + 1:
                    break
                elif c == 9: # ASCII horizontal tab
                    x = ((x - self.linePaneSize) // self.tabSize + 1) * self.tabSize + self.linePaneSize
                    continue
                elif c == 10: # ASCII line feed
                    break

                if x >= self.sx + self.linePaneSize:
                    self.font.drawGlyph(c, x - self.sx, l - self.sy)
                x += 1

        # Begin drawing status bar text
        glColor3f(0.15,0.15,0.15)
        # Generate status bar text
        statusText = self.filename
        # Show vim-style [No Name] when a new file is created
        if statusText == None:
            statusText = "[No Name]"
        # Show vim-style plus flag when modified
        if self.modified:
            statusText += " [+]"

        # Generate and show vim-style position indicator
        posText = str(self.y + 1) + "," + str(self.x + 1) + " "
        if self.maxY >= len(self.lines) - 1:
            # Show All when you can see the whole file in the screen
            posText += "All"
        elif self.sy == 0:
            # Show Top when on the top of the file
            posText += "Top"
        else:
            posPercent = int((self.sy / (len(self.lines) - self.maxY - 1)) * 100)
            if posPercent == 100:
                # Show Bot when on the bottom of the file
                posText += "Bot"
            else:
                # Show a percentage when not any of the cases above
                if posPercent < 10:
                    posText += " "
                posText += str(posPercent) + "%"

        # Trim status text depending on screen size and positional indicator
        statusTextEdge = self.statusCols - len(posText) - 1
        if len(statusText) > statusTextEdge:
            # Trim when the status text is too big
            statusText = "..." + statusText[-statusTextEdge + 3:]

        # Draw status text
        x = 0
        for c in statusText:
            # Print even special characters to make it clear that they are part
            # of the file name
            self.font.drawGlyph(ord(c), x, 0, 0, self.statusTop)
            x += 1
        # Draw positional indicator
        x = 0
        xOffset = (self.statusCols - len(posText)) * self.font.width
        for c in posText:
            self.font.drawGlyph(ord(c), x, 0, xOffset, self.statusTop)
            x += 1

        # End drawing glyph quads
        glEnd()

        # Start drawing cursor
        glDisable(GL_TEXTURE_2D)
        glBlendFunc(GL_ONE_MINUS_DST_COLOR, GL_ZERO)
        glBegin(GL_QUADS)
        glColor3f(1,1,1)

        # Draw cursor
        if self.y == self.doy:
            quadTop = 16 * (self.y - self.sy)
            quadBot = quadTop + 16
            quadLeft = quadRight = 0

            if self.x == self.dox:
                # Not a selection, set up cursor
                quadLeft = self.linePaneRight + self.font.width * (self.rx - self.sx)
                quadRight = quadLeft + 2
            else:
                # Single line selection, set up selection area
                quadLeft = self.linePaneRight + self.font.width * (min(self.rx, self.rdox) - self.sx)
                quadRight = self.linePaneRight + self.font.width * (max(self.rx, self.rdox) - self.sx)

                # If the selection is left to right, then add 2 extra pixels
                # to the right to indicate the direction of the selection
                if self.x > self.dox:
                    quadRight += 2

                # Clamp if selection goes off-screen
                if quadLeft < self.linePaneRight:
                    quadLeft = self.linePaneRight
                if quadRight > self.canvasSize.width:
                    quadRight = self.canvasSize.width

            glVertex2f(quadLeft, quadTop)
            glVertex2f(quadRight, quadTop)
            glVertex2f(quadRight, quadBot)
            glVertex2f(quadLeft, quadBot)
        else:
            # Pick the top and bottom selection area
            minSX = minSY = maxSX = maxSY = 0
            maxCur = False
            if self.y < self.doy:
                minSX = self.rx - self.sx
                minSY = self.y - self.sy
                maxSX = self.rdox - self.sx
                maxSY = self.doy - self.sy
            else:
                minSX = self.rdox - self.sx
                minSY = self.doy - self.sy
                maxSX = self.rx - self.sx
                maxSY = self.y - self.sy

                # If the cursor comes after the origin, then the bottom slice
                # ends at the cursor
                maxCur = True

            # Top, right-going slice
            if minSX < self.maxX and minSY >= 0:
                quadTopTS = 16 * minSY
                quadBotTS = quadTopTS + 16
                quadLeftTS = self.linePaneRight + self.font.width * minSX
                quadRightTS = self.canvasSize.width

                # Clamp if selection's left edge not visible
                if quadLeftTS < self.linePaneRight:
                    quadLeftTS = self.linePaneRight

                glVertex2f(quadLeftTS, quadTopTS)
                glVertex2f(quadRightTS, quadTopTS)
                glVertex2f(quadRightTS, quadBotTS)
                glVertex2f(quadLeftTS, quadBotTS)

            # Middle, full-lines slice
            if maxSY - minSY > 1:
                quadTopMS = 16 * (minSY + 1)
                quadBotMS = 16 * maxSY
                quadLeftMS = self.linePaneRight
                quadRightMS = self.canvasSize.width

                # Clamp if selection's horizontal edges go off-screen
                if quadTopMS < 0:
                    quadTopMS = 0
                if quadBotMS > self.statusTop:
                    quadBotMS = self.statusTop

                glVertex2f(quadLeftMS, quadTopMS)
                glVertex2f(quadRightMS, quadTopMS)
                glVertex2f(quadRightMS, quadBotMS)
                glVertex2f(quadLeftMS, quadBotMS)

            # Bottom, left-going slice
            if maxSX >= self.sx and maxSY < self.maxY:
                quadTopBS = 16 * maxSY
                quadBotBS = quadTopBS + 16
                quadLeftBS = self.linePaneRight
                quadRightBS = self.linePaneRight + self.font.width * maxSX

                # Add extra 2 pixels to the right if at the cursor
                if maxCur:
                    quadRightBS += 2

                # Clamp if selection's right edge is not visible
                if quadRightBS > self.canvasSize.width:
                    quadRightBS = self.canvasSize.width

                glVertex2f(quadLeftBS, quadTopBS)
                glVertex2f(quadRightBS, quadTopBS)
                glVertex2f(quadRightBS, quadBotBS)
                glVertex2f(quadLeftBS, quadBotBS)

        # End drawing cursor
        glEnd()
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glFlush()

    def openFile(self, filename):
        self.recompile = True
        showLineDialog = False
        if filename == None:
            self.modified = False
            self.filename = None
            self.filebuffer = array('B')
            self.lines = [0]
            self.tokens = [[]]
            self.buffersize = 0
        else:
            with open(filename, mode='rb') as f:
                self.modified = False
                self.filename = filename
                self.filebuffer = array('B')
                self.lines = [0]
                self.tokens = list()

                # Read file in 1 KiB blocks until EOF
                while True:
                    try:
                        self.filebuffer.fromfile(f, 1024)
                    except EOFError:
                        break

                # Filter out carriage returns to convert to unix line ends.
                # Using list comprehension, where 13 is the ascii value for CR.
                # Also keeps track of the initial size to determine wether there
                # was a line ending conversion
                initialSize = len(self.filebuffer)
                self.filebuffer = array('B', [c for c in self.filebuffer if c != 13])

                # Get buffer size
                self.buffersize = len(self.filebuffer)

                # If the size changed, then line endings were converted.
                # Inform the user
                if self.buffersize != initialSize:
                    showLineDialog = True

                # Parse file for newlines and save their positions
                for i in range(self.buffersize):
                    if self.filebuffer[i] == ord('\n'):
                        self.tokens.append(compiler.compiler_lexical_analysis(self.filebuffer[self.lines[-1]:i].tobytes().decode("ascii"), self.cpu.intMin, self.cpu.intMax, self.cpu.memWords - 1, self.cpu.bytesPerWord, self.langext)[1])
                        self.lines.append(i + 1)
                self.tokens.append(compiler.compiler_lexical_analysis(self.filebuffer[self.lines[-1]:self.buffersize].tobytes().decode("ascii"), self.cpu.intMin, self.cpu.intMax, self.cpu.memWords - 1, self.cpu.bytesPerWord, self.langext)[1])
        self.resetEditor()
        self.updatePaneSize()
        self.Refresh()

        # Dialogs are asynchronous and cause a refresh when shown, so they must
        # be shown after fully loading the file so that data races do not occur.
        # Specifically, showing the dialog while loading the file corrupts the
        # token list and editor properties
        if showLineDialog:
            with MessageDialog(None,
                    "Windows line endings were converted to Unix line endings",
                    "Line endings converted",
                    OK | ICON_INFORMATION) as dialog:
                dialog.ShowModal()

    def saveFile(self, filename):
        # Abort if filename is None. This shouldn't happen normally
        if filename == None:
            raise ValueError("Attempt to save file with filename as None")
        with open(filename, mode='wb') as f:
            self.modified = False
            self.filename = filename
            self.filebuffer.tofile(f)
        self.Refresh()
