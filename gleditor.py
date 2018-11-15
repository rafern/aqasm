#!/bin/env python3
from interpreter import *
from hexfont import *
from wx import glcanvas
from wx import *
import _thread as thread
from array import array

class GLEditor(glcanvas.GLCanvas):
    def __init__(self, parent, font):
        super(GLEditor, self).__init__(parent, attribList = (
                                                   glcanvas.WX_GL_RGBA,
                                                   glcanvas.WX_GL_DOUBLEBUFFER,
                                                   glcanvas.WX_GL_DEPTH_SIZE,
                                                   24
                                               ))

        # Flag as editor context initialization and redraw needed
        self.initializeEditor = self.syntaxh = self.langext = True
        # Set used font
        self.font = font
        # Editor variables
        self.tabSize = 8
        self.cumulXScroll = self.cumulYScroll = 0

        # Bind paint events to editor's draw callback
        self.Bind(EVT_PAINT, self.onPaint)
        # Bind resize events to editor's resize callback
        self.Bind(EVT_SIZE, self.onResize)
        # Bind button presses
        self.Bind(EVT_CHAR, self.onKeydown)
        self.Bind(EVT_LEFT_DOWN, self.onMousedown)
        self.Bind(EVT_MOUSEWHEEL, self.onMousewheel)
        
        # For now the editor has no GL context. Call makeContext to get one
        # Must be called AFTER there is a shown window in the screen
        self.context = None

    def makeContext(self):
        self.context = glcanvas.GLContext(self)

    def resetEditor(self):
        # Reset buffer, real (counting tabsize) and screen coords
        self.x = self.y = self.rx = self.sx = self.sy = 0

    def lineEnd(self, i):
        # Get line end
        lend = self.buffersize
        if i + 1 < len(self.lines):
            lend = self.lines[i + 1]
        return lend

    def lineLength(self, i):
        return self.lineEnd(i) - self.lines[i]

    def updateCursor(self):
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

    def seekPos(self, x, y):
        lineCount = len(self.lines)
        # If too far down (after max line), go to end of file
        if y >= lineCount:
            self.y = lineCount - 1
            self.x = self.lineLength(self.y)
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
        self.tokens[l] = lex.lex_highlight(self.filebuffer[lstart:lend])

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
        self.updateTokens(self.y)
        self.updatePaneSize()

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
            self.delChar()

    def onPaint(self, event):
        # Redraw editor
        self.drawEditor()
        # Run default handler aswell
        event.Skip()

    def onResize(self, event):
        CallAfter(self.doResizeEvent)
        # Run default handler aswell
        event.Skip()

    def doResizeEvent(self):
        # Get new editor size
        self.editorSize = self.GetClientSize()
        # Use the editor's GL context
        self.SetCurrent(self.context)
        # Set viewport and orthographic projection to use new size
        glViewport(0, 0, self.editorSize.width, self.editorSize.height)
        # Update orthographic projection
        self.orthoEditor()
        # Update pre-calculated limits
        self.linePaneRight = self.font.width * self.linePaneSize
        self.statusY = self.editorSize.height // 16 - 1
        self.statusTop = self.statusY * 16
        self.statusCols = self.editorSize.width // self.font.width
        self.maxX = self.statusCols - self.linePaneSize + 1
        self.maxY = self.statusY - 1
        # Update cursor
        self.updateCursor()

    def moveDelta(self, dx, dy):
        update = False

        while dx < 0:
            dx += 1
            if self.x > 0:
                self.x -= 1
                update = True
            else:
                break

        if dx > 0:
            # Since lineLength return line length including LF, if not the last
            # line, remove 1 from the lineMaxX
            lineMaxX = self.lineLength(self.y)
            if self.y + 1 < len(self.lines):
                lineMaxX -= 1
            while dx > 0:
                dx -= 1
                if self.x < lineMaxX:
                    self.x += 1
                    update = True
                else:
                    break

        while dy < 0:
            dy += 1
            if self.y > 0:
                self.seekPos(self.rx, self.y - 1)
                update = True
            else:
                break

        if dy > 0:
            lineLimit = len(self.lines) - 1
            while dy > 0:
                dy -= 1
                if self.y < lineLimit:
                    self.seekPos(self.rx, self.y + 1)
                    update = True
                else:
                    break

        if update:
            self.updateCursor()
            self.Refresh()

    def onKeydown(self, event):
        keycode = event.GetKeyCode()
        update = False
        default = True
        # Process key events
        if keycode == WXK_LEFT:
            default = False
            # moveDelta redraws, so update doesn't have to be set to true
            self.moveDelta(-1, 0)
        elif keycode == WXK_RIGHT:
            default = False
            self.moveDelta(1, 0)
        elif keycode == WXK_UP:
            default = False
            self.moveDelta(0, -1)
        elif keycode == WXK_DOWN:
            default = False
            self.moveDelta(0, 1)
        elif keycode == WXK_DELETE:
            self.delChar()
            update = True
        elif keycode == WXK_BACK:
            self.backspaceChar()
            update = True
        elif keycode == WXK_RETURN:
            self.typeChar(10)
            update = True
        elif keycode == WXK_HOME:
            self.x = 0
            update = True
        elif keycode == WXK_END:
            self.x = self.lineLength(self.y)
            if self.y + 1 < len(self.lines):
                self.x -= 1
            update = True
        elif keycode == WXK_PAGEUP:
            self.moveDelta(0, -self.maxY // 2)
        elif keycode == WXK_PAGEDOWN:
            self.moveDelta(0, self.maxY // 2)
        elif (keycode >= 32 and keycode <= 126) or keycode == 9:
            if keycode == 9:
                default = False
            self.typeChar(keycode)
            update = True

        if update:
            # Update cursor
            self.updateCursor()
            # Redraw
            self.Refresh()
        if default:
            # Also run default handler
            event.Skip()

    def onMousedown(self, event):
        x, y = event.GetPosition()
        x -= self.linePaneRight
        # Abort if not in the editor's bounds
        if y >= self.statusTop:
            return
        elif x < 0:
            return
        self.seekPos(self.sx + (x // self.font.width), self.sy + (y // 16))
        # Update cursor and redraw
        self.updateCursor()
        self.Refresh()
        # Also run default handler
        event.Skip()

    def onMousewheel(self, event):
        threshold = event.GetWheelDelta()
        if event.GetWheelAxis() == MOUSE_WHEEL_HORIZONTAL:
            self.cumulXScroll += event.GetWheelRotation()
            moveX = self.cumulXScroll // threshold
            self.cumulXScroll = self.cumulXScroll % threshold
            self.moveDelta(moveX, 0)
        else:
            self.cumulYScroll -= event.GetWheelRotation()
            moveY = self.cumulYScroll // threshold
            self.cumulYScroll = self.cumulYScroll % threshold
            self.moveDelta(0, moveY)

    def orthoEditor(self):
        # Tell OpenGL that we are changing the projection matrix
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        # Setup orthographic projection for easier 2D coordinates
        # The coordinates go from top-left to bottom-right
        glOrtho(0, self.editorSize.width, self.editorSize.height, 0, -1, 1)
        # Switch back to model matrix
        glMatrixMode(GL_MODELVIEW)

    def drawEditor(self):
        # Tell wxPython that we are drawing while processing this event
        PaintDC(self)
        # Tell OpenGL to use the text editor context
        self.SetCurrent(self.context)
        # If not yet initialized, initialize it
        if self.initializeEditor:
            # Setup orthographic projection
            self.orthoEditor()
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
        glVertex2f(self.editorSize.width, self.statusTop)
        glVertex2f(self.editorSize.width, self.editorSize.height)
        glVertex2f(0, self.editorSize.height)
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
                        if thisToken == lex.token.comment:
                            glColor3f(0.5,0.5,0.5)
                        elif thisToken == lex.token.whitespace or thisToken == lex.token.separator or thisToken == lex.token.identifier:
                            glColor3f(1,1,1)
                        elif thisToken == lex.token.decimal:
                            glColor3f(0.8,0.4,0)
                        elif thisToken == lex.token.address:
                            glColor3f(0,0.6,0.9)
                        elif thisToken == lex.token.register:
                            glColor3f(0.7,0,0.7)
                        elif thisToken == lex.token.labelid or thisToken == lex.token.label:
                            glColor3f(0.1,0.6,0.1)
                        elif thisToken == lex.token.error:
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

        # Draw cursor quad
        glDisable(GL_TEXTURE_2D)
        glBlendFunc(GL_ONE_MINUS_DST_COLOR, GL_ZERO)
        glBegin(GL_QUADS)
        glColor3f(1,1,1)
        glVertex2f(self.linePaneRight + self.font.width * (self.rx - self.sx), 16 * (self.y - self.sy))
        glVertex2f(self.linePaneRight + self.font.width * (self.rx - self.sx) + 2, 16 * (self.y - self.sy))
        glVertex2f(self.linePaneRight + self.font.width * (self.rx - self.sx) + 2, 16 * (self.y - self.sy + 1))
        glVertex2f(self.linePaneRight + self.font.width * (self.rx - self.sx), 16 * (self.y - self.sy + 1))
        glEnd()
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glFlush()

        # Swap buffer to display
        self.SwapBuffers()

    def openFile(self, filename):
        self.recompile = True
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
                eof = False
                while not eof:
                    try:
                        self.filebuffer.fromfile(f, 1024)
                    except EOFError:
                        eof = True
                self.buffersize = len(self.filebuffer)

                # Parse file for newlines and save their positions
                for i in range(self.buffersize):
                    if self.filebuffer[i] == ord('\n'):
                        self.tokens.append(lex.lex_highlight(self.filebuffer[self.lines[-1]:i]))
                        self.lines.append(i + 1)
                self.tokens.append(lex.lex_highlight(self.filebuffer[self.lines[-1]:self.buffersize]))
        self.resetEditor()
        self.updatePaneSize()
        self.Refresh()

    def saveFile(self, filename):
        # Abort if filename is None. This shouldn't happen normally
        if filename == None:
            raise ValueError("Attempt to save file with filename as None")
        with open(filename, mode='wb') as f:
            self.modified = False
            self.filename = filename
            self.filebuffer.tofile(f)
