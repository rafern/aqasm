from interpreter import *
from glsubwindow import *
from OpenGL.GL.framebufferobjects import *
import _thread as thread

class GLDisplay(GLSubWindow):
    # I/O ports used by the display
    IO_PORT_KEYBOARD = 0
    IO_PORT_DISPLAY  = 1
    # IRQ number used by the keyboard
    IRQ_PORT_INPUT = 127

    def __init__(self, parent, cpu, gllock, size = DefaultSize):
        super(GLDisplay, self).__init__(parent, "Display", gllock, size)

        # AQASM interpreter used for pushing resize events
        self.cpu = cpu

        # Register I/O port
        self.cpu.ioRegister(self.IO_PORT_KEYBOARD, None)
        self.cpu.ioRegister(self.IO_PORT_DISPLAY, self.drawPixel)

        # Screen OpenGL framebuffer object and rendertexture
        self.fbo = None
        self.tid = None

        # Resolution. Using qqVGA (smallest 4:3 aspect ratio resolution)
        self.resolution = (160, 120)
        self.ratio = self.resolution[0] / self.resolution[1]
        self.calcRatio()

        # Draw queue and reset flag
        self.drawQueue = []
        self.resetFlag = False
        self.pixelLock = thread.allocate_lock()

        # Bind button presses
        self.canvas.Bind(EVT_CHAR, self.onKeydown)

    def reset(self):
        self.pixelLock.acquire()
        self.resetFlag = True
        self.drawQueue = []
        self.pixelLock.release()
        if self.IsShown():
            self.canvas.Refresh()

    def onKeydown(self, event):
        keycode = event.GetKeyCode()
        data = None

        # Process key events
        # Arrow keys are non-standard, but since the ASCII DC codes aren't used,
        # they could be used for arrows instead. Same thing for home, end,
        # page up and page down, replacing ASCII delimiter codes.
        if keycode == WXK_LEFT:
            data = 17
        elif keycode == WXK_RIGHT:
            data = 18
        elif keycode == WXK_UP:
            data = 19
        elif keycode == WXK_DOWN:
            data = 20
        elif keycode == WXK_HOME:
            data = 28
        elif keycode == WXK_END:
            data = 29
        elif keycode == WXK_PAGEUP:
            data = 30
        elif keycode == WXK_PAGEDOWN:
            data = 31
        elif keycode == WXK_DELETE:
            data = 127
        elif keycode == WXK_BACK:
            data = 8
        elif keycode == WXK_ESCAPE:
            data = 27
        elif keycode == WXK_RETURN:
            data = 10
        elif keycode == WXK_TAB:
            data = 9
        elif keycode >= 32 and keycode <= 126:
            data = keycode

        # Push data to keyboard device if the key could be processed
        if data != None:
            self.cpu.ioInputPush(self.IO_PORT_KEYBOARD, data)
            self.cpu.irq.append(self.IRQ_PORT_INPUT)

    def clearFBO(self):
        # Bind framebuffer
        glBindFramebuffer(GL_FRAMEBUFFER, self.fbo)

        # Clear texture
        glClear(GL_COLOR_BUFFER_BIT)

        # Unbind framebuffer
        glBindFramebuffer(GL_FRAMEBUFFER, 0)

    def initializeGL(self):
        if self.fbo == None:
            # Generate rendertexture
            self.tid = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, self.tid)

            # Using QQVGA resolution
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, self.resolution[0], self.resolution[1], 0, GL_RGB, GL_UNSIGNED_BYTE, None)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)

            # Done with texture generation, unbind it
            glBindTexture(GL_TEXTURE_2D, 0)

            # Generate framebuffer object
            self.fbo = glGenFramebuffers(1)
            glBindFramebuffer(GL_FRAMEBUFFER, self.fbo)

            # Attach texture to FBO
            glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, self.tid, 0)

            # Unbind framebuffer object
            glBindFramebuffer(GL_FRAMEBUFFER, 0)

            # Clear framebuffer
            glClearColor(0, 0, 0, 0)
            self.clearFBO()

            # Enable texturing
            glEnable(GL_TEXTURE_2D)

    def drawPixel(self, addr):
        # Get arguments from memory (x,y,r,g,b)
        if addr + 5 > self.cpu.memWords:
            self.cpu.irq.append(IRQ_GENERAL_PROTECTION_FAULT)
            return

        # Position
        x = oputil_ldr(self.cpu, addr)
        y = oputil_ldr(self.cpu, addr + 1)

        # Don't render if off-screen
        if x >= self.resolution[0] or y >= self.resolution[1]:
            return

        # Colour value (truncate to 8 bit value)
        r = oputil_ldr(self.cpu, addr + 2) % 256
        g = oputil_ldr(self.cpu, addr + 3) % 256
        b = oputil_ldr(self.cpu, addr + 4) % 256

        # Push pixel to queue
        self.pixelLock.acquire()
        self.drawQueue.append((x, y, r, g, b))
        self.pixelLock.release()

        # Add to render queue if the context can't be set to current
        # (due to window hidden, a limitation of wxPython)
        if self.IsShown():
            self.canvas.Refresh()

    def redrawCanvas(self):
        self.initializeGL()

        self.pixelLock.acquire()
        if self.resetFlag:
            self.resetFlag = False
            self.clearFBO()

        # Draw a pixel with colour (r,g,b) at (x,y) in framebuffer if in queue
        if len(self.drawQueue) > 0:
            # Bind framebuffer
            glBindFramebuffer(GL_FRAMEBUFFER, self.fbo)
            glViewport(0, 0, self.resolution[0], self.resolution[1])

            # Use FBO's orthographic projection's properties
            glMatrixMode(GL_PROJECTION)
            glLoadIdentity()
            glOrtho(0, self.resolution[0], self.resolution[1], 0, -1, 1)
            glMatrixMode(GL_MODELVIEW)

            # Start drawing
            glBegin(GL_POINTS)

            # Push pixels
            for p in self.drawQueue:
                glColor3ub(p[2], p[3], p[4])
                glVertex2i(p[0], p[1])

            self.drawQueue.clear()

            # End drawing
            glEnd()

            # Unbind framebuffer
            glBindFramebuffer(GL_FRAMEBUFFER, 0)

            # Use normal orthographic projection
            glViewport(0, 0, self.canvasSize.width, self.canvasSize.height)
            self.updateOrtho()
        self.pixelLock.release()

        # Clear screen for letterboxing
        glClear(GL_COLOR_BUFFER_BIT)

        # Bind texture
        glBindTexture(GL_TEXTURE_2D, self.tid)

        # Draw FBO texture
        glBegin(GL_QUADS)
        glColor3f(1, 1, 1)
        if self.winRatio > self.ratio:
            glTexCoord2f(0, 1)
            glVertex2f(self.letterStart, 0)
            glTexCoord2f(1, 1)
            glVertex2f(self.letterEnd, 0)
            glTexCoord2f(1, 0)
            glVertex2f(self.letterEnd, self.canvasSize[1])
            glTexCoord2f(0, 0)
            glVertex2f(self.letterStart, self.canvasSize[1])
        else:
            glTexCoord2f(0, 1)
            glVertex2f(0, self.letterStart)
            glTexCoord2f(1, 1)
            glVertex2f(self.canvasSize[0], self.letterStart)
            glTexCoord2f(1, 0)
            glVertex2f(self.canvasSize[0], self.letterEnd)
            glTexCoord2f(0, 0)
            glVertex2f(0, self.letterEnd)
        glEnd()

        # Unbind texture, as it is cleared if it is not unbound
        glBindTexture(GL_TEXTURE_2D, 0)

    def calcRatio(self):
        # Ratio calculations
        self.winRatio = self.canvasSize[0] / self.canvasSize[1]
        if self.winRatio > self.ratio:
            # Horizontal
            letterSize = self.canvasSize[1] * self.ratio
            self.letterStart = (self.canvasSize[0] - letterSize) // 2
        else:
            # Vertical
            letterSize = self.canvasSize[0] / self.ratio
            self.letterStart = (self.canvasSize[1] - letterSize) // 2
        self.letterEnd = self.letterStart + letterSize

    def resizeCanvas(self):
        self.initializeGL()
        self.calcRatio()
