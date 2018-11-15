#!/bin/env python3
from interpreter import *
from hexfont import *
from wx import glcanvas
from wx import *
import wx.lib.newevent as wxNE
from math import ceil

class GLMemViewer(Frame):
    def __init__(self, parent, cpu, font):
        super(GLMemViewer, self).__init__(parent)

        # AQASM interpreter used for fetching memory
        self.cpu = cpu
        # Memory viewer internal variables
        self.selOffset = self.screenOffset = 0
        # Flags
        self.initializeViewer = self.showOffsets = self.showDots = self.showHex = True
        # Set used font
        self.font = font

        # OpenGL canvas
        self.canvas = glcanvas.GLCanvas(self, attribList = (
                                                  glcanvas.WX_GL_RGBA,
                                                  glcanvas.WX_GL_DOUBLEBUFFER,
                                                  glcanvas.WX_GL_DEPTH_SIZE,
                                                  24
                                              ))
        # No GL context for now. Must be created after window is shown
        self.context = None

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
        viewmenu.Check(self.showOffsetsItem.GetId(), True)
        viewmenu.Check(self.showHexItem.GetId(), True)
        viewmenu.Check(self.showDotsItem.GetId(), True)
        menu.Append(viewmenu, "&View")
        # Menu bar - end
        self.SetMenuBar(menu)

        # Binds
        # Close bypass
        self.Bind(EVT_CLOSE, self.onClose)
        # Menu callbacks
        self.Bind(EVT_MENU, self.onGoTo, gotoitem)
        # Bind checkboxes
        self.Bind(EVT_MENU, self.toggleOffsets, self.showOffsetsItem)
        self.Bind(EVT_MENU, self.toggleHex, self.showHexItem)
        self.Bind(EVT_MENU, self.toggleDots, self.showDotsItem)
        # GL canvas binds
        self.canvas.Bind(EVT_PAINT, self.onPaint)
        self.canvas.Bind(EVT_SIZE, self.onResize)
        # Bind button presses
        self.canvas.Bind(EVT_CHAR, self.onKeydown)

        # Set title
        self.SetTitle("Memory viewer")

    def makeContext(self):
        self.context = glcanvas.GLContext(self.canvas)

    def onClose(self, event):
        # Don't close the memory viewer, just hide it instead.
        # The parent window does the cleanup, not this, so this instance is
        # only destroyed when the parent window is destroyed. This is done
        # automatically
        self.Hide()

    def onPaint(self, event):
        # Redraw canvas
        self.drawViewer()
        # Run default handler aswell
        event.Skip()

    def onResize(self, event):
        CallAfter(self.doResizeEvent)
        # Run default handler aswell
        event.Skip()

    def doResizeEvent(self):
        # Get new memory viewer size
        self.canvasSize = self.canvas.GetClientSize()
        # Use the viewer's GL context
        self.canvas.SetCurrent(self.context)
        # Use new size and update orthographic projection
        glViewport(0, 0, self.canvasSize.width, self.canvasSize.height)
        self.updateOrtho()
        # Update pre-calculated limits
        self.addrLen = self.cpu.wordLength // 4
        self.hexFormat = '{:0' + str(self.addrLen) + 'x}'
        self.cols = self.canvasSize[0] // self.font.width
        self.rows = self.canvasSize[1] // 16
        self.recalcColOffsets()

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
            self.moveDelta(0, -(self.canvasSize[1] // 16))
        elif keycode == WXK_PAGEDOWN:
            self.moveDelta(0, +(self.canvasSize[1] // 16))
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

    def updateOrtho(self):
        # Use orthographic projection
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(0, self.canvasSize.width, self.canvasSize.height, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW)

    def drawWord(self, word, x, y, xOff = 0, yOff = 0):
        # Make hex string from word
        hexStr = self.hexFormat.format(word)
        # Draw hex string
        curX = x
        for c in hexStr:
            self.font.drawGlyph(ord(c), curX, y, xOff, yOff)
            curX += 1

    def drawViewer(self):
        # Tell wxPython that we are drawing while processing this event
        PaintDC(self.canvas)
        # Use the viewer's GL context
        self.canvas.SetCurrent(self.context)
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

        if renderLightPane:
            glColor3f(0.85,0.8,0.8)
            glVertex2f(lightPaneLeft, 0)
            glVertex2f(lightPaneRight, 0)
            glVertex2f(lightPaneRight, self.canvasSize[1])
            glVertex2f(lightPaneLeft, self.canvasSize[1])
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
                if thisOffset >= self.cpu.memWords:
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

        glEnd()
        glDisable(GL_TEXTURE_2D)

        # Draw cursor quads
        glBlendFunc(GL_ONE_MINUS_DST_COLOR, GL_ZERO)
        glBegin(GL_QUADS)
        glColor3f(1,1,1)
        hOffset = self.selOffset % self.wordsPerLine
        quadTop = ((self.selOffset // self.wordsPerLine) - self.screenOffset) * 16
        quadBottom = quadTop + 16
        # Hex pane quad
        if self.showHex:
            hexQuadLeft = self.hexColOffset + hOffset * (self.addrLen + 1) * self.font.width
            hexQuadRight = hexQuadLeft + self.font.width * (self.addrLen + 1)
            glVertex2f(hexQuadLeft, quadTop)
            glVertex2f(hexQuadRight, quadTop)
            glVertex2f(hexQuadRight, quadBottom)
            glVertex2f(hexQuadLeft, quadBottom)
        # ASCII pane quad
        asciiQuadLeft = self.asciiColOffset + hOffset * self.font.width
        asciiQuadRight = asciiQuadLeft + self.font.width * self.cpu.bytesPerWord
        glVertex2f(asciiQuadLeft, quadTop)
        glVertex2f(asciiQuadRight, quadTop)
        glVertex2f(asciiQuadRight, quadBottom)
        glVertex2f(asciiQuadLeft, quadBottom)
        glEnd()
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glFlush()

        # Swap buffers to display
        self.canvas.SwapBuffers()

    def onGoTo(self, event):
        newOffset = GetNumberFromUser("Enter offset:", "Decimal", "Go to...", 0, 0, self.cpu.memWords, self)
        if newOffset != -1:
            self.selOffset = newOffset
            self.updateCursor()
            self.Refresh()

    def toggleOffsets(self, event):
        self.showOffsets = self.showOffsetsItem.IsChecked()
        self.doResizeEvent()
        self.Refresh()

    def toggleHex(self, event):
        self.showHex = self.showHexItem.IsChecked()
        self.doResizeEvent()
        self.Refresh()

    def toggleDots(self, event):
        self.showDots = self.showDotsItem.IsChecked()
        self.doResizeEvent()
        self.Refresh()
