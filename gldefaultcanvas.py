from OpenGL.GL import *
from wx import glcanvas
from wx import *

class GLDefaultCanvas(glcanvas.GLCanvas):
    def __init__(self, parent, gllock, size = DefaultSize):
        super(GLDefaultCanvas, self).__init__(parent, attribList = (
            glcanvas.WX_GL_RGBA,
            glcanvas.WX_GL_DOUBLEBUFFER,
            glcanvas.WX_GL_DEPTH_SIZE,
            0
            ), size = size)

        # OpenGL mutex lock
        self.gllock = gllock

        # No GL context for now. Must be created after window is shown
        self.context = None

        # Save size
        self.canvasSize = self.GetClientSize()

        # Binds
        # GL canvas binds
        self.Bind(EVT_PAINT, self.onPaint)
        self.Bind(EVT_SIZE, self.onResize)

    def makeContext(self):
        self.context = glcanvas.GLContext(self)

    def onPaint(self, event):
        #self.gllock.acquire()
        # Tell wxPython that we are drawing while processing this event
        PaintDC(self)
        # Use the viewer's GL context
        self.SetCurrent(self.context)
        # Redraw canvas. This must be defined by the daughter class
        self.redrawCanvas()
        # Swap buffers to display
        glFinish()
        self.SwapBuffers()
        #self.gllock.release()
        # Run default handler aswell
        event.Skip()

    def onResize(self, event):
        CallAfter(self.doResizeEvent)
        # Run default handler aswell
        event.Skip()

    def doResizeEvent(self):
        # Get new memory viewer size
        self.canvasSize = self.GetClientSize()
        # Use the viewer's GL context
        #self.gllock.acquire()
        self.SetCurrent(self.context)
        # Use new size and update orthographic projection
        glViewport(0, 0, self.canvasSize.width, self.canvasSize.height)
        self.updateOrtho()
        # Resize canvas. This must be defined by the daughter class
        self.resizeCanvas()
        glFinish()
        #self.gllock.release()

    def updateOrtho(self):
        # Use orthographic projection
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(0, self.canvasSize.width, self.canvasSize.height, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW)

    def redrawCanvas(self):
        raise NotImplementedError

    def resizeCanvas(self):
        raise NotImplementedError
