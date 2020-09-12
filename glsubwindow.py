from OpenGL.GL import *
from wx import glcanvas
from wx import *

class GLSubWindow(Frame):
    def __init__(self, parent, title, gllock, size = DefaultSize):
        super(GLSubWindow, self).__init__(parent, size = size)

        # OpenGL mutex lock
        self.gllock = gllock

        # OpenGL canvas
        self.canvas = glcanvas.GLCanvas(self, attribList = (
            glcanvas.WX_GL_RGBA,
            glcanvas.WX_GL_DOUBLEBUFFER,
            glcanvas.WX_GL_DEPTH_SIZE,
            0
            ), size = size)
        # No GL context for now. Must be created after window is shown
        self.context = None

        # Binds
        # Close bypass
        self.Bind(EVT_CLOSE, self.onClose)
        # GL canvas binds
        self.canvas.Bind(EVT_PAINT, self.onPaint)
        self.canvas.Bind(EVT_SIZE, self.onResize)

        # Set title
        self.SetTitle(title)

        # Set minimum size
        self.SetMinSize(self.GetSize())

        # Save size
        self.canvasSize = self.canvas.GetClientSize()

    def makeContext(self):
        self.context = glcanvas.GLContext(self.canvas)

    def onClose(self, event):
        # Don't close the GL window, just hide it instead. The parent window
        # does the cleanup, not this, so this instance is only destroyed when
        # the parent window is destroyed. This is done automatically
        self.Hide()

    def onPaint(self, event):
        #self.gllock.acquire()
        # Tell wxPython that we are drawing while processing this event
        PaintDC(self.canvas)
        # Use the viewer's GL context
        self.canvas.SetCurrent(self.context)
        # Redraw canvas. This must be defined by the daughter class
        self.redrawCanvas()
        # Swap buffers to display
        glFinish()
        self.canvas.SwapBuffers()
        #self.gllock.release()
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
        #self.gllock.acquire()
        self.canvas.SetCurrent(self.context)
        # Use new size and update orthographic projection
        self.updateOrtho()
        # Resize canvas. This must be defined by the daughter class
        self.resizeCanvas()
        glFinish()
        #self.gllock.release()

    def updateOrtho(self):
        # Use orthographic projection
        glViewport(0, 0, self.canvasSize.width, self.canvasSize.height)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(0, self.canvasSize.width, self.canvasSize.height, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW)

    def redrawCanvas(self):
        raise NotImplementedError

    def resizeCanvas(self):
        raise NotImplementedError
