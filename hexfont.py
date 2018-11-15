#!/bin/env python3
from numpy import zeros, uint8
from OpenGL.GL import *

class HexFont:
    def __init__(self, filename):
        # Raw pixel data for visible ASCII range (33-126) [128 * width x 16 x 4]
        # Note that 128 vs 94 used because textures have power of two dimensions
        self.buffer = None
        # Glyph width
        self.width = stride = 0
        # GL Texture ID
        self.tid = None
        # Load .hex font, but only ASCII range
        with open(filename + ".hex", "r") as ins:
            for line in ins:
                try:
                    fields = line.split(":", 1)
                    num = int(fields[0], 16)
                    if num < 256:
                        fields[1] = fields[1].strip("\n")
                        if self.width == 0:
                            self.width = len(fields[1]) // 4
                            if not self.width in [8, 16]:
                                raise ValueError("Glyph width not 8 or 16")
                            stride = self.width // 4
                            self.buffer = zeros((16, 256 * self.width, 4), dtype=uint8)
                        elif self.width * 4 != len(fields[1]):
                            raise ValueError("Inconsistent glyph width")
                        # Iterate through each character row
                        for r in range(16):
                            # Get dec value of row
                            rdata = int(fields[1][r * stride:(r + 1) * stride], 16)
                            for c in range(self.width):
                                if rdata & (1 << c):
                                    self.buffer[r][num * self.width + self.width - c - 1][0] = 255
                                    self.buffer[r][num * self.width + self.width - c - 1][1] = 255
                                    self.buffer[r][num * self.width + self.width - c - 1][2] = 255
                                    self.buffer[r][num * self.width + self.width - c - 1][3] = 255
                except:
                    raise ValueError("Invalid format")
        if self.width == None:
            raise ValueError("No glyphs loaded")

    def genTexture(self):
        tid = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, tid)
        # Create texture
        glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, self.width * 256, 16, 0, GL_RGBA, GL_UNSIGNED_BYTE, self.buffer)
        # Set texture parameters
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)

    def bindTexture(self, tid):
        # XXX this is unused but may be used in the future. Remove me if I'm not used when the project is done
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, tid)

    def drawGlyph(self, c, col, row, offX = 0, offY = 0):
        # Draw a glyph [c] at column [col] and row [row], with an offset of
        # ([offX], [offY]), defaulting to no offset. Needs a set current context
        # and to be in GL_QUADS draw mode. No vertex arrays... FOR NOW (TODO???)
        glTexCoord2f((c * self.width) / (self.width * 256), 0)
        glVertex2f(col * self.width + offX, row * 16 + offY)
        glTexCoord2f(((c + 1) * self.width) / (self.width * 256), 0)
        glVertex2f((col + 1) * self.width + offX, row * 16 + offY)
        glTexCoord2f(((c + 1) * self.width) / (self.width * 256), 1)
        glVertex2f((col + 1) * self.width + offX, (row + 1) * 16 + offY)
        glTexCoord2f((c * self.width) / (self.width * 256), 1)
        glVertex2f(col * self.width + offX, (row + 1) * 16 + offY)
