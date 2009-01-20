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

from struct import pack, unpack
import ctypes, ctypes.util
from ctypes import byref, c_void_p

import numpy

try:
    from TG.openGL.raw import aglUtils
except ImportError:
    aglUtils = None

from TG.quicktime.coreVideoTexture import QTGWorldTexture, CVOpenGLTexture, QTCVTexture

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#~ Libraries
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

if hasattr(ctypes, 'windll'):
    libQuickTimePath = ctypes.util.find_library("QTMLClient.dll")
    libQuickTime = ctypes.cdll.LoadLibrary(libQuickTimePath)
    libQuickTime.InitializeQTML()
else:
    libQuickTimePath = ctypes.util.find_library("QuickTime")
    libQuickTime = ctypes.cdll.LoadLibrary(libQuickTimePath)

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#~ QuickTime Stuff
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class QTMovieDisplayContext(object):
    TextureFactory = None

    @classmethod
    def isContextSupported(klass):
        return False
    
    def getMovieProperties(self):
        return []

    _qtTexture = None
    def getQTTexture(self):
        tex = self._qtTexture
        if tex is None:
            tex = self.TextureFactory(self)
            self._qtTexture = tex
        return tex
    def delQTTexture(self):
        if self._qtTexture is None:
            return
        self._qtTexture.destroy()
        self._qtTexture = None

    def reset(self):
        pass

    def process(self):
        pass

    def updateForMovie(self, movie):
        return True

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class QTOpenGLVisualContext(QTMovieDisplayContext):
    TextureFactory = QTCVTexture
    _as_parameter_ = None

    def __init__(self):
        self.create()

    def __del__(self):
        self.destroy()

    def destroy(self):
        if not self._as_parameter_: return
        self.delQTTexture()
        libQuickTime.QTVisualContextRelease(self)
        self._as_parameter_ = None

    @classmethod
    def isContextSupported(klass):
        if not hasattr(aglUtils, 'getCGLContextAndFormat'):
            return False
        if not hasattr(libQuickTime, 'QTOpenGLTextureContextCreate'):
            return False
        return True

    def create(self):
        if self._as_parameter_:
            return self

        cglCtx, cglPix = aglUtils.getCGLContextAndFormat()
        self._as_parameter_ = c_void_p()
        errqt = libQuickTime.QTOpenGLTextureContextCreate(None, cglCtx, cglPix, None, byref(self._as_parameter_))
        return self

    def getMovieProperties(self):
        return [('ctxt', 'visu', self)]

    def process(self):
        libQuickTime.QTVisualContextTask(self)

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class QTGWorldContext(QTMovieDisplayContext):
    _as_parameter_ = None
    #k32ARGBPixelFormat = 0x00000020
    k32RGBAPixelFormat = 0x41424752
    k32ABGRPixelFormat = 0x52474241
    TextureFactory = QTGWorldTexture

    @classmethod
    def isContextSupported(klass):
        if not hasattr(libQuickTime, 'NewGWorldFromPtr'):
            return False
        return True

    def __del__(self):
        self.destroy()

    def destroy(self):
        if not self._as_parameter_: return
        self.delQTTexture()
        libQuickTime.DisposeGWorld(self)
        self._as_parameter_ = None

    def reset(self):
        self.delQTTexture()

    def process(self):
        pass

    def updateForMovie(self, movie):
        rect = (ctypes.c_short*4)()
        libQuickTime.GetMovieBox(movie, byref(rect))
        if rect[0] != 0 or rect[1] != 0:
            # move the movie to 0,0
            rect[2] -= rect[0]; rect[0] = 0
            rect[3] -= rect[1]; rect[1] = 0
            libQuickTime.SetMovieBox(movie, byref(rect))

        self.size = (rect[3], rect[2])
        self.data = numpy.zeros((rect[2], rect[3], 4), 'B')
        self._as_parameter_ = c_void_p()
        if not self.data.size:
            return False

        errqt = libQuickTime.NewGWorldFromPtr(
                byref(self._as_parameter_), 
                self.k32RGBAPixelFormat,
                byref(rect),
                None,
                None,
                0,
                self.data.ctypes, 
                self.size[0]*4)

        if errqt:
            #darn... that's too bad... try it anyway
            pass

        libQuickTime.SetMovieGWorld(movie, self, None)
        return True

