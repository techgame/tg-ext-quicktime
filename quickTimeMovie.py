##~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~##
##~ Copyright (C) 2002-2006  TechGame Networks, LLC.              ##
##~                                                               ##
##~ This library is free software; you can redistribute it        ##
##~ and/or modify it under the terms of the BSD style License as  ##
##~ found in the LICENSE file included with this distribution.    ##
##~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~##

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#~ Imports 
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

import weakref

import ctypes, ctypes.util
from ctypes import cast, byref, c_void_p, c_short

from .movieDisplayContext import QTGWorldContext, QTOpenGLVisualContext
from .coreFoundationUtils import asCFString, asCFURL, c_appleid, fromAppleId, toAppleId, booleanTrue, booleanFalse

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

libQuickTime.GetMovieVolume.argtypes = [c_void_p]
libQuickTime.GetMovieVolume.restype = c_short
libQuickTime.SetMovieVolume.argtypes = [c_void_p, c_short]

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#~ QuickTime Stuff
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class TimeRecord(ctypes.Structure):
    _fields_ = [
        ('value', ctypes.c_long),
        ('scale', ctypes.c_long),
        ('base', ctypes.c_void_p),
        ]

class QTNewMoviePropertyElement(ctypes.Structure):
    _fields_ = [
        ('propClass', c_appleid),
        ('propID', c_appleid),
        ('propValueSize', (ctypes.c_uint32)),
        ('propValueAddress', ctypes.c_void_p),
        ('propStatus', (ctypes.c_int32)),
        ]
    
    @classmethod
    def new(klass, cid, pid, value):
        if hasattr(value, '_as_parameter_'):
            value = value._as_parameter_
        valueSize = ctypes.sizeof(type(value))
        p_value = cast(byref(value), c_void_p)
        return klass(
                fromAppleId(cid), 
                fromAppleId(pid), 
                valueSize,
                p_value, 0)

    @classmethod
    def fromProperties(klass, *properties):
        return klass.fromPropertyList(properties)

    @classmethod
    def fromPropertyList(klass, *propLists):
        propList = [klass.new(*p) for propList in propLists for p in propList]
        return (klass*len(propList))(*propList)

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#~ Definitions 
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

def qtEnterMovies():
    libQuickTime.EnterMovies()
def qtExitMovies():
    libQuickTime.ExitMovies()

def qtVersion():
    r = ctypes.c_long(0)
    libQuickTime.Gestalt(fromAppleId('qtim'), byref(r))
    return r.value

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class QTMovie(object):
    _as_parameter_ = None

    def __init__(self, path=None):
        qtEnterMovies() 
        self.createContext()
        if path is not None:
            self.loadPath(path)

    def __del__(self):
        try:
            self.destroy()
        except Exception:
            import traceback
            traceback.print_exc()

    def destroy(self):
        self.destroyMovie()
        self.destroyContext()

    def destroyMovie(self):
        if not self._as_parameter_: return
        libQuickTime.StopMovie(self)
        libQuickTime.DisposeMovie(self)
        self._as_parameter_ = None

    def loadPath(self, path):
        if '://' in path:
            return self.loadURL(path)
        else:
            return self.loadFilePath(path)

    def loadURL(self, urlPath):
        return self.loadFromProperties([('dloc', 'cfur', asCFURL(urlPath))])

    def loadFilePath(self, filePath):
        return self.loadFromProperties([('dloc', 'cfnp', asCFString(filePath))])

    defaultMovieProperties=[
        ('mprp', 'actv', booleanTrue), # set movie active after loading
        ('mprp', 'intn', booleanTrue), # don't interact with user
        ('mins', 'aurn', booleanTrue), # don't ask user help for unresolved references
        ('mins', 'asok', booleanTrue), # load asynchronously
        ]
    def loadFromProperties(self, movieProperties):
        self.destroyMovie()
        self.displayContext.reset()

        movieProperties = QTNewMoviePropertyElement.fromPropertyList(
                                movieProperties, 
                                self.defaultMovieProperties, 
                                self.displayContext.getMovieProperties(),
                                )

        self._as_parameter_ = c_void_p()
        errqt = libQuickTime.NewMovieFromProperties(len(movieProperties), movieProperties, 0, None, byref(self._as_parameter_))

        if errqt:
            print
            print 'Movies Error:', libQuickTime.GetMoviesError()
            print 'Movie Properties::'
            for prop in movieProperties:
                print '   ', toAppleId(prop.propClass), toAppleId(prop.propID), prop.propStatus
            print
            print 
            raise RuntimeError("Failed to initialize QuickTime movie from properties")
        elif 0:
            print 'Movie Properties::'
            for prop in movieProperties:
                print '   ', toAppleId(prop.propClass), toAppleId(prop.propID), prop.propStatus
            print
            self.printTracks()

        self.displayContext.updateForMovie(self)
        return True

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    _movieDisplayContexts = [
        QTOpenGLVisualContext,
        QTGWorldContext,
        ]
    def createContext(self):
        for displayContext in self._movieDisplayContexts:
            if displayContext.isContextSupported():
                self.displayContext = displayContext()
                break
        else:
            raise RuntimeError("No suitable display context could be found")
    def destroyContext(self):
        self.displayContext.destroy()
        self.displayContext = None

    def getQTTexture(self):
        if self.hasVisuals():
            return self.displayContext.getQTTexture()
    qtTexture = property(getQTTexture)
        
    def process(self, seconds=0):
        if self.displayContext:
            self.displayContext.process()
        self.processMovieTask(seconds)

    def processMovieTask(self, seconds=0):
        return libQuickTime.MoviesTask(self, int(seconds*1000))

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def getLoadState(self):
        return libQuickTime.GetMovieLoadState(self)

    def setLooping(self, looping=1):
        libQuickTime.GoToBeginningOfMovie(self)
        timeBase = libQuickTime.GetMovieTimeBase(self)
        libQuickTime.SetTimeBaseFlags(timeBase, looping) # loopTimeBase

        hintsLoop = 0x2
        libQuickTime.SetMoviePlayHints(self, hintsLoop, hintsLoop)

    def printTracks(self):
        print 'Movie Tracks::'
        trackMediaType = c_appleid()
        for trackIdx in xrange(libQuickTime.GetMovieTrackCount(self)):
            track = libQuickTime.GetMovieIndTrack(self, trackIdx)
            print '  track:', trackIdx, track
            if track:
                trackMedia = libQuickTime.GetTrackMedia(track)
                print '    media:', trackMedia,
                if trackMedia:
                    libQuickTime.GetMediaHandlerDescription(trackMedia, byref(trackMediaType), 0, 0)
                    print toAppleId(trackMediaType)
                    #if trackMediaType[:] not in ('vide', 'soun'):
                    #    libQuickTime.SetTrackEnabled(track, False)
                    #    print 'disabled'
                    #else:
                    #    print 'enabled'
                else:
                    print "<unset>"
        print

    def getBox(self):
        rect = (c_short*4)()
        libQuickTime.GetMovieBox(self, byref(rect))
        return list(rect)

    def hasVisuals(self):
        return sum(self.getBox()[2:]) > 0 # do we have a size?

    def getRate(self):
        return libQuickTime.GetMovieRate(self)
    def setRate(self, rate):
        return libQuickTime.SetMovieRate(self, rate)

    def getTime(self):
        # Sending a value of None to this method will only return the current time
        # value, versus the time value and the pointer to the time structure
        return libQuickTime.GetMovieTime(self, None)
    def setTime(self, pos):
        timeRecord = TimeRecord()
        libQuickTime.GetMovieTime(self, byref(timeRecord))
        timeRecord.value = pos
        libQuickTime.SetMovieTime(self, byref(timeRecord))

    def getDuration(self):
        return libQuickTime.GetMovieDuration(self)
    def getTimeScale(self):
        return libQuickTime.GetMovieTimeScale(self)

    def getVolume(self):
        # volume is converted from a floating point number to an 8.8 fixed point number
        volume = libQuickTime.GetMovieVolume(self)
        volume = volume / 256.0
        return volume
    def setVolume(self, volume):
        # volume is converted from a floating point number to an 8.8 fixed point number
        volume = int(volume * 256) & 0xffff
        return libQuickTime.SetMovieVolume(self, volume)
    def mute(self, toggle=False):
        volume = self.getVolume()
        if toggle or volume >= 0.0:
            self.setVolume(-volume)
    def unmute(self):
        volume = self.getVolume()
        if volume < 0.0:
            self.setVolume(-volume)
        elif volume == 0.0:
            self.setVolume(0.1)

    def start(self):
        libQuickTime.StartMovie(self)
    def stop(self):
        libQuickTime.StopMovie(self)
    def pause(self):
        self.setRate(0)
    def goToBeginning(self):
        libQuickTime.GoToBeginningOfMovie(self)

    def isActive(self):
        return bool(libQuickTime.GetMovieActive(self))
    def isDone(self):
        return bool(libQuickTime.IsMovieDone(self))

    def ptInMovie(self):
        return libQuickTime.PtInMovie(self)

