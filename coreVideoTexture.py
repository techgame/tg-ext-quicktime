##~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~##
##~ Copyright (C) 2002-2007  TechGame Networks, LLC.              ##
##~                                                               ##
##~ This library is free software; you can redistribute it        ##
##~ and/or modify it under the terms of the BSD style License as  ##
##~ found in the LICENSE file included with this distribution.    ##
##~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~##

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#~ Imports 
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

import weakref
from functools import partial

import ctypes, ctypes.util
from ctypes import c_void_p, byref

import numpy

from TG.ext.openGL.raw import gl, glext
from TG.ext.openGL.data.texture import Texture

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#~ Constants / Variiables / Etc. 
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

if hasattr(ctypes, 'windll'):
    libCoreVideoPath = ctypes.util.find_library("QTMLClient.dll")
    libCoreVideo = ctypes.cdll.LoadLibrary(libCoreVideoPath)
    libCoreVideo.InitializeQTML()
else:
    libCoreVideoPath = ctypes.util.find_library("CoreVideo")
    libCoreVideo = ctypes.cdll.LoadLibrary(libCoreVideoPath)

    libQuickTimePath = ctypes.util.find_library("QuickTime")
    libQuickTime = ctypes.cdll.LoadLibrary(libQuickTimePath)

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#~ Definitions 
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class OpenGLTexture(object):
    texture_id = 0
    target = None
    size = None
    texCoords = None

    def __init__(self):
        self.texCoords = numpy.zeros((4,2), 'f')

    def bind(self):
        gl.glBindTexture(self.target, self.texture_id)
    def unbind(self):
        gl.glBindTexture(self.target, 0)

    def enable(self):
        gl.glEnable(self.target)
    def disable(self):
        gl.glDisable(self.target)

    def select(self):
        self.bind()
        self.enable()
        return self

    def deselect(self):
        self.disable()
        self.unbind()
        return self

    def update(self, force=False):
        return False

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class CVOpenGLTexture(OpenGLTexture):
    def __init__(self):
        OpenGLTexture.__init__(self)
        self._texCoordsAddresses = [tc.ctypes.data for tc in self.texCoords]
        self._cvTextureRef = c_void_p(0)

    def __del__(self):
        self.destroy()

    def isNewImageAvailable(self):
        raise NotImplementedError('Subclass Responsibility: %r' % (self,))

    def updateCVTexture(self, cvTextureRef):
        raise NotImplementedError('Subclass Responsibility: %r' % (self,))

    def destroy(self):
        if not self._cvTextureRef: return
        libCoreVideo.CVOpenGLTextureRelease(self._cvTextureRef)
        self._cvTextureRef = c_void_p(0)

    def update(self, force=False):
        if not force and not self.isNewImageAvailable():
            return False

        libCoreVideo.CVOpenGLTextureRelease(self._cvTextureRef)
        cvTextureRef = c_void_p(0)
        self._cvTextureRef = cvTextureRef

        self.updateCVTexture(cvTextureRef)

        self.target = libCoreVideo.CVOpenGLTextureGetTarget(cvTextureRef)
        self.texture_id = libCoreVideo.CVOpenGLTextureGetName(cvTextureRef)

        libCoreVideo.CVOpenGLTextureGetCleanTexCoords(cvTextureRef, *self._texCoordsAddresses)
        self.size = abs(self.texCoords[2]-self.texCoords[0])
        return True

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class QTCVTexture(CVOpenGLTexture):
    def __init__(self, visualContext):
        CVOpenGLTexture.__init__(self)
        self.visualContext = visualContext

    def isNewImageAvailable(self):
        return libQuickTime.QTVisualContextIsNewImageAvailable(self.visualContext, None)
    def updateCVTexture(self, cvTextureRef):
        libQuickTime.QTVisualContextCopyImageForTime(self.visualContext, None, None, byref(cvTextureRef))

class QTGWorldTexture(OpenGLTexture):
    target = gl.GL_TEXTURE_2D
    #target = glext.GL_TEXTURE_RECTANGLE_ARB
    texture_id = 0

    def __init__(self, gworldContext):
        OpenGLTexture.__init__(self)
        self._data_ptr = gworldContext.data.ctypes._as_parameter_
        self.size = gworldContext.size

        self.target = Texture.validTargets(['rect', '2d']).next()
        if self.target == gl.GL_TEXTURE_2D:
            self.texSize = tuple(map(Texture.nextPowerOf2, self.size))
            self.texCoords[:] = self.size
            self.texCoords /= self.texSize
        else:
            self.texCoords[:] = self.size
            self.texSize = self.size
        self.texCoords *= [[0,1], [1,1], [1,0], [0,0]]

        self.initTexture()

    def __del__(self):
        self.destroy()

    def destroy(self):
        pass

    def initTexture(self):
        texture_id = gl.GLenum(0)
        gl.glGenTextures(1, byref(texture_id))

        def delGLTexture(wr, texture_id=texture_id.value):
            texture_id = gl.GLenum(texture_id)
            gl.glDeleteTextures(1, byref(texture_id))
        texture_id.wr = weakref.ref(texture_id, delGLTexture)

        self.texture_id = texture_id
        self.bind()

        gl.glTexParameteri(self.target, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
        gl.glTexParameteri(self.target, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)

        dataFormat = gl.GL_RGBA
        dataType = gl.GL_UNSIGNED_INT_8_8_8_8
        gl.glTexImage2D(self.target, 0, gl.GL_RGBA8, 
            self.texSize[0], self.texSize[1], False, 
            dataFormat, dataType, None)
        self._pushToTexture = partial(gl.glTexSubImage2D, self.target, 0, 
                0, 0, self.size[0], self.size[1], 
                dataFormat, dataType, self._data_ptr)

    _pushToTexture = None
    def update(self, force=False):
        self.bind()
        self._pushToTexture()
        return True

