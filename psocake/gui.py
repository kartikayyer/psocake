import os
if 'PSOCAKE_FACILITY' not in os.environ: os.environ['PSOCAKE_FACILITY'] = 'LCLS' # Default facility
if 'LCLS' in os.environ['PSOCAKE_FACILITY'].upper():
    pass
elif 'CFEL' in os.environ['PSOCAKE_FACILITY'].upper():
    pass
elif 'PAL' in os.environ['PSOCAKE_FACILITY'].upper():
    pass
else:
    print "Unknown facility name: ", os.environ['PSOCAKE_FACILITY']
    exit()
# Import the rest of the packages
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui
import pyqtgraph.console
import numpy as np
from pyqtgraph.dockarea import *

import argparse
import _colorScheme as color
from _version import __version__
from pyqtgraph.dockarea.Dock import DockLabel
import sys

# Panel modules
import MousePanel, ImagePanel, ImageStackPanel
import ExperimentPanel, DiffractionGeometryPanel, RoiPanel
import PeakFindingPanel, CrystalIndexingPanel, MaskPanel
import SmallDataPanel, ImageControlPanel
import HitFinderPanel

parser = argparse.ArgumentParser()
parser.add_argument('expRun', nargs='?', default=None, help="Psana-style experiment/run string in the format (e.g. exp=cxi06216:run=22). This option trumps -e and -r options.")
parser.add_argument("-e","--exp", help="Experiment name (e.g. cxis0813 ). This option is ignored if expRun option is used.", default="", type=str)
parser.add_argument("-r","--run", help="Run number. This option is ignored if expRun option is used.",default=0, type=int)
parser.add_argument("-d","--det", help="Detector alias or DAQ name (e.g. DscCsPad or CxiDs1.0:Cspad.0), default=''",default="", type=str)
parser.add_argument("-n","--evt", help="Event number (e.g. 1), default=0",default=0, type=int)
parser.add_argument("--localCalib", help="Use local calib directory. A calib directory must exist in your current working directory.", action='store_true')
parser.add_argument("-o","--outDir", help="Use this directory for output instead.", default=None, type=str)
parser.add_argument("-v", help="verbosity level, default=0",default=0, type=int)
parser.add_argument('--version', action='version',
                    version='%(prog)s {version}'.format(version=__version__))
parser.add_argument("-m","--mode", help="Mode sets the combination of panels available on the GUI, options: {lite,sfx,spi,all}",default="lite", type=str)
# LCLS specific
parser.add_argument("-a","--access", help="Set data node access: {ana,ffb}",default="ana", type=str)
parser.add_argument("--noInfiniband", help="Do not use infiniband.", action='store_true')
# PAL specific
parser.add_argument("--debug", help="Debug mode of PAL at LCLS.", action='store_true')
args = parser.parse_args()

class Window(QtGui.QMainWindow):
    global ex

    def previewEvent(self, eventNumber):
        ex.eventNumber = eventNumber
        ex.calib, ex.data = ex.img.getDetImage(ex.eventNumber)
        ex.img.win.setImage(ex.data, autoRange=False, autoLevels=False, autoHistogramRange=False)
        ex.exp.p.param(ex.exp.exp_grp, ex.exp.exp_evt_str).setValue(ex.eventNumber)

    def keyPressEvent(self, event):
        super(Window, self).keyPressEvent(event)
        if args.mode == "all":
            if type(event) == QtGui.QKeyEvent:
                path = ["", ""]
                if event.key() == QtCore.Qt.Key_1:
                    path[1] = "Single"
                    data = True
                    if ex.evtLabels.labelA == True : data = False
                    ex.evtLabels.paramUpdate(path, data)
                elif event.key() == QtCore.Qt.Key_2:
                    path[1] = "Multi"
                    data = True
                    if ex.evtLabels.labelB == True : data = False
                    ex.evtLabels.paramUpdate(path, data)
                elif event.key() == QtCore.Qt.Key_3:
                    path[1] = "Dunno"
                    data = True
                    if ex.evtLabels.labelC == True : data = False
                    ex.evtLabels.paramUpdate(path, data)
                elif event.key() == QtCore.Qt.Key_Period:
                    if ex.small.w9.getPlotItem().listDataItems() != []:
                        idx = -1
                        array = np.where(ex.small.quantifierEvent >= ex.eventNumber)
                        if array[0].size != 0:
                            idx = array[0][0]
                            if ex.small.quantifierEvent[idx] == ex.eventNumber: idx += 1
                            if idx < (ex.small.quantifierEvent.size): self.previewEvent(ex.small.quantifierEvent[idx])
                elif event.key() == QtCore.Qt.Key_N:
                    if ex.eventNumber < (ex.exp.eventTotal - 1): self.previewEvent(ex.eventNumber+1)
                elif event.key() == QtCore.Qt.Key_Comma:
                    if ex.small.w9.getPlotItem().listDataItems() != []:
                        idx = -1
                        array = np.where(ex.small.quantifierEvent <= ex.eventNumber)
                        if array[0].size != 0:
                            idx = array[0][array[0].size - 1]
                            if ex.small.quantifierEvent[idx] == ex.eventNumber: idx -= 1
                            if ex.small.quantifierEvent[idx] != 0: self.previewEvent(ex.small.quantifierEvent[idx])
                elif event.key() == QtCore.Qt.Key_P:
                    if ex.eventNumber != 0: self.previewEvent(ex.eventNumber-1)
                ex.evtLabels.refresh()

class MainFrame(QtGui.QWidget):
    """
    The main frame of the application
    """
    def __init__(self, arg_list):
        super(MainFrame, self).__init__()
        self.args = args
        self.area = DockArea()

        # Get username
        self.username = self.getUsername()

        # Set up tolerance
        self.eps = np.finfo("float64").eps
        self.firstUpdate = True
        self.operationModeChoices = ['none', 'masking']
        self.operationMode =  self.operationModeChoices[0] # Masking mode, Peak finding mode

        # Supported facilities keywords
        self.facilityLCLS = 'LCLS'
        self.facilityPAL = 'PAL'
        if 'CFEL' in os.environ['PSOCAKE_FACILITY'].upper():
            self.facility = self.facilityLCLS
            self.dir = '/gpfs/cfel/cxi/common/slac/reg/d/psdm'
            if args.outDir is None:
                args.outDir = '/gpfs/cfel/cxi/scratch/user/'+self.username+'/psocake'
        elif 'LCLS' in os.environ['PSOCAKE_FACILITY'].upper():
            self.facility = self.facilityLCLS
            self.dir = '/reg/d/psdm'
        elif 'PAL' in os.environ['PSOCAKE_FACILITY'].upper():
            self.facility = self.facilityPAL
            if args.debug:
                self.dir = '/reg/d/psdm/cxi/cxitut13/res/yoon82/pohang/kihyun'
            else:
                self.dir = '/home/eh2adm/sfx' # FIXME: TEMPORARY

        # Init experiment parameters from args
        if args.expRun is not None and ':run=' in args.expRun:
            self.experimentName = args.expRun.split('exp=')[-1].split(':')[0]
            self.runNumber = int(args.expRun.split('run=')[-1])
        else:
            self.experimentName = args.exp
            self.runNumber = int(args.run)
        self.detInfo = args.det
        self.detAlias = None
        self.eventNumber = int(args.evt)

        # Directories
        self.psocakeDir = None
        self.psocakeRunDir = None
        self.elogDir = None
        self.rootDir = None
        self.writeAccess = True
        self.access = args.access.lower()
        if 'ffb' in self.access:
            print "################################################################"
            print "Remember only psfeh(hi)prioq/psneh(hi)prioq can access FFB nodes"
            print "FFB node is here: /reg/d/ffb/"
            print "################################################################"


        # Init variables
        self.det = None
        self.detnames = None
        self.detInfoList = None
        self.evt = None
        self.eventID = ""
        self.hasExperimentName = False
        self.hasRunNumber = False
        self.hasDetInfo = False
        self.pixelIndAssem = None

        self.doneExpSetup = False
        self.doneRunSetup = False
        self.doneDetSetup = False
        self.doneEvtSetup = False
        self.doneInit = False

        # Init diffraction geometry parameters
        self.coffset = 0.0
        self.clen = 0.0
        self.clenEpics = 0.0
        self.epics = None
        self.detectorDistance = 0.0
        self.photonEnergy = None
        self.wavelength = None
        self.pixelSize = None
        self.resolutionRingsOn = False
        self.resolution = None
        self.resolutionUnits = 0

        # Init variables
        self.calib = None  # ndarray detector image
        self.data = None  # assembled detector image
        self.cx = 0  # detector centre x
        self.cy = 0  # detector centre y

        ## Switch to using white background and black foreground
        pg.setConfigOption('background', color.background)
        pg.setConfigOption('foreground', color.foreground)
        ########################################
        # Instantiate panels
        ########################################
        self.mouse = MousePanel.Mouse(self)
        self.img = ImagePanel.ImageViewer(self)
        self.stack = ImageStackPanel.ImageStack(self)
        self.exp = ExperimentPanel.ExperimentInfo(self)
        self.geom = DiffractionGeometryPanel.DiffractionGeometry(self)
        self.roi = RoiPanel.RoiHistogram(self)
        self.pk = PeakFindingPanel.PeakFinding(self)
        self.index = CrystalIndexingPanel.CrystalIndexing(self)
        self.mk = MaskPanel.MaskMaker(self)
        self.small = SmallDataPanel.SmallData(self)
        self.control = ImageControlPanel.ImageControl(self)
        self.hf = HitFinderPanel.HitFinder(self)

        self.initUI()

    def getUsername(self):
        return os.environ['USER']
        #process = subprocess.Popen('whoami', stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        #out, err = process.communicate()
        #self.username = out.strip()

    def initUI(self):
        # Set the color scheme
        def updateStyle(self):
            r = '2px'
            if self.dim:
                fg = color.unselectedFG
                bg = color.unselectedBG
                border = color.unselectedBorder
            else:
                fg = color.selectedFG
                bg = color.selectedBG
                border = color.selectedBorder

            if self.orientation == 'vertical':
                self.vStyle = """DockLabel {
                    background-color : %s;
                    color : %s;
                    border-top-right-radius: 0px;
                    border-top-left-radius: %s;
                    border-bottom-right-radius: 0px;
                    border-bottom-left-radius: %s;
                    border-top: 1px solid %s;
                    border-left: 1px solid %s;
                    border-right: 1px solid %s;
                    border-width: 1px;
                    border-right: 2px solid %s;
                    padding-top: 3px;
                    padding-bottom: 3px;
                    font-size: 18px;
                }""" % (bg, fg, r, r, border, fg, fg, fg)
                self.setStyleSheet(self.vStyle)
            else:
                if self.dim:  # unselected, decrease font size
                    self.hStyle = """DockLabel {
                        background-color : %s;
                        color : %s;
                        border-top-right-radius: %s;
                        border-top-left-radius: %s;
                        border-bottom-right-radius: 0px;
                        border-bottom-left-radius: 0px;
                        border-width: 1px;
                        border-bottom: 2px solid %s;
                        border-top: 1px solid %s;
                        border-left: 1px solid %s;
                        border-right: 1px solid %s;
                        padding-left: 13px;
                        padding-right: 13px;
                        font-size: 16px
                    }""" % (bg, fg, r, r, border, fg, fg, fg)
                else:  # selected
                    self.hStyle = """DockLabel {
                        background-color : %s;
                        color : %s;
                        border-top-right-radius: %s;
                        border-top-left-radius: %s;
                        border-bottom-right-radius: 0px;
                        border-bottom-left-radius: 0px;
                        border-width: 1px;
                        border-bottom: 2px solid %s;
                        border-top: 1px solid %s;
                        border-left: 1px solid %s;
                        border-right: 1px solid %s;
                        padding-left: 13px;
                        padding-right: 13px;
                        font-size: 18px
                    }""" % (bg, fg, r, r, border, fg, fg, fg)
                self.setStyleSheet(self.hStyle)
        DockLabel.updateStyle = updateStyle

        if args.mode == 'sfx':
            self.area.addDock(self.mouse.dock, 'left')
            self.area.addDock(self.img.dock, 'bottom', self.mouse.dock)
            self.area.addDock(self.stack.dock, 'bottom', self.mouse.dock)
            self.area.moveDock(self.img.dock, 'above', self.stack.dock)  ## move imagePanel on top of imageStack

            self.area.addDock(self.exp.dock, 'right')
            self.area.addDock(self.geom.dock, 'right')
            self.area.addDock(self.roi.dock, 'right')
            self.area.moveDock(self.geom.dock, 'above', self.roi.dock)   ## move d6 to stack on top of d4
            self.area.moveDock(self.exp.dock, 'above', self.geom.dock)

            self.area.addDock(self.pk.dock, 'bottom', self.exp.dock)
            self.area.addDock(self.index.dock, 'bottom', self.exp.dock)
            self.area.addDock(self.mk.dock, 'bottom', self.exp.dock)
            self.area.moveDock(self.index.dock, 'above', self.mk.dock)   ## move d6 to stack on top of d4
            self.area.moveDock(self.pk.dock, 'above', self.index.dock)

            self.area.addDock(self.small.dock, 'right')
            self.area.addDock(self.control.dock, 'right')
            self.area.moveDock(self.small.dock, 'top', self.control.dock)
        elif args.mode == 'spi':
            self.area.addDock(self.mouse.dock, 'left')
            self.area.addDock(self.img.dock, 'bottom', self.mouse.dock)
            self.area.addDock(self.stack.dock, 'bottom', self.mouse.dock)
            self.area.moveDock(self.img.dock, 'above', self.stack.dock)  ## move imagePanel on top of imageStack

            self.area.addDock(self.exp.dock, 'right')
            self.area.addDock(self.geom.dock, 'right')
            self.area.addDock(self.roi.dock, 'right')
            self.area.moveDock(self.geom.dock, 'above', self.roi.dock)  ## move d6 to stack on top of d4
            self.area.moveDock(self.exp.dock, 'above', self.geom.dock)

            self.area.addDock(self.hf.dock, 'bottom', self.exp.dock)
            self.area.addDock(self.mk.dock, 'bottom', self.exp.dock)
            self.area.moveDock(self.hf.dock, 'above', self.mk.dock)     ## move hf to stack on top of mk

            self.area.addDock(self.small.dock, 'right')
            self.area.addDock(self.control.dock, 'right')
            self.area.moveDock(self.small.dock, 'top', self.control.dock)
        elif args.mode == 'all':
            self.area.addDock(self.mouse.dock, 'left')
            self.area.addDock(self.img.dock, 'bottom', self.mouse.dock)
            self.area.addDock(self.stack.dock, 'bottom', self.mouse.dock)
            self.area.moveDock(self.img.dock, 'above', self.stack.dock)  ## move imagePanel on top of imageStack

            self.area.addDock(self.exp.dock, 'right')
            self.area.addDock(self.geom.dock, 'right')
            self.area.addDock(self.roi.dock, 'right')
            self.area.moveDock(self.geom.dock, 'above', self.roi.dock)  ## move d6 to stack on top of d4
            self.area.moveDock(self.exp.dock, 'above', self.geom.dock)

            self.area.addDock(self.hf.dock, 'bottom', self.exp.dock)
            self.area.addDock(self.pk.dock, 'bottom', self.exp.dock)
            self.area.addDock(self.index.dock, 'bottom', self.exp.dock)
            self.area.addDock(self.mk.dock, 'bottom', self.exp.dock)
            self.area.moveDock(self.index.dock, 'above', self.mk.dock)  ## move d6 to stack on top of d4
            self.area.moveDock(self.pk.dock, 'above', self.index.dock)
            self.area.moveDock(self.hf.dock, 'above', self.pk.dock)

            self.area.addDock(self.small.dock, 'right')
            self.area.addDock(self.control.dock, 'right')
            self.area.moveDock(self.small.dock, 'top', self.control.dock)
        else:
            self.area.addDock(self.mouse.dock, 'left')
            self.area.addDock(self.img.dock, 'bottom', self.mouse.dock)
            self.area.addDock(self.stack.dock, 'bottom', self.mouse.dock)
            self.area.addDock(self.control.dock, 'left')
            self.area.moveDock(self.control.dock, 'bottom', self.stack.dock)
            self.area.moveDock(self.img.dock, 'above', self.stack.dock)  ## move imagePanel on top of imageStack

            self.area.addDock(self.exp.dock, 'right')
            self.area.addDock(self.roi.dock, 'right')
            self.area.moveDock(self.exp.dock, 'above', self.roi.dock)  ## move d6 to stack on top of d4

            self.area.addDock(self.pk.dock, 'bottom', self.exp.dock)
            self.area.addDock(self.mk.dock, 'bottom', self.exp.dock)
            self.area.moveDock(self.pk.dock, 'above', self.mk.dock)  ## move d6 to stack on top of d4

        ###############
        ### Threads ###
        ###############
        # Making powder patterns
        self.thread = []
        self.threadCounter = 0

        # Initial setup of input parameters
        if self.experimentName is not "":
            self.exp.p.param(self.exp.exp_grp, self.exp.exp_name_str).setValue(self.experimentName)
            self.exp.updateExpName(self.experimentName)
        if self.runNumber is not 0:
            self.exp.p.param(self.exp.exp_grp, self.exp.exp_run_str).setValue(self.runNumber)
            self.exp.updateRunNumber(self.runNumber)
        if self.detInfo is not "":
            self.exp.p.param(self.exp.exp_grp, self.exp.exp_detInfo_str).setValue(self.detInfo)
            self.exp.updateDetInfo(self.detInfo)
        self.exp.p.param(self.exp.exp_grp, self.exp.exp_evt_str).setValue(self.eventNumber)
        self.exp.updateEventNumber(self.eventNumber)

        if self.exp.hasExpRunInfo():
            # Setup elog
            self.exp.setupRunTable()
            self.exp.getDatasource()
            self.exp.setupRunDir()
            self.exp.setupTotalEvents()
            self.exp.printDetectorNames()
            # Update paths in all the panels
            self.exp.updatePanels()
            self.exp.setupPsocake()
            # Update hidden CrystFEL files
            self.exp.updateHiddenCrystfelFiles(self.facility)
            # Optionally use local calib directory
            self.exp.setupLocalCalib()
            # Launch e-log crawler
            self.exp.setupCrawler()
        if self.exp.hasExpRunDetInfo():
            self.exp.setupDetGeom()
            self.img.updateDetectorCentre(self.facility)
            self.exp.getEventAndDisplay()

        # Indicate centre of detector
        self.geom.drawCentre()

        self.doneInit = True

        # Try mouse over crosshair
        self.xhair = self.img.win.getView()
        self.vLine = pg.InfiniteLine(angle=90, movable=False)
        self.hLine = pg.InfiniteLine(angle=0, movable=False)
        self.xhair.addItem(self.vLine, ignoreBounds=True)
        self.xhair.addItem(self.hLine, ignoreBounds=True)
        self.vb = self.xhair.vb
        self.label = pg.LabelItem()
        self.mouse.win.addItem(self.label)

        def mouseMoved(evt):
            pos = evt[0]  ## using signal proxy turns original arguments into a tuple
            if self.xhair.sceneBoundingRect().contains(pos):
                mousePoint = self.vb.mapSceneToView(pos)
                indexX = int(mousePoint.x())
                indexY = int(mousePoint.y())

                # update crosshair position
                self.vLine.setPos(mousePoint.x())
                self.hLine.setPos(mousePoint.y())
                # get pixel value, if data exists
                if self.data is not None:
                    if indexX >= 0 and indexX < self.data.shape[0] \
                            and indexY >= 0 and indexY < self.data.shape[1]:
                        if self.mk.maskingMode > 0:
                            modeInfo = self.mk.masking_mode_message
                        else:
                            modeInfo = ""
                        pixelInfo = "<span style='color: " + color.pixelInfo + "; font-size: 24pt;'>x=%0.1f y=%0.1f I=%0.1f </span>"
                        self.label.setText(
                            modeInfo + pixelInfo % (mousePoint.x(), mousePoint.y(), self.data[indexX, indexY]))

        def mouseClicked(evt):
            mousePoint = self.vb.mapSceneToView(evt[0].scenePos())
            indexX = int(mousePoint.x())
            indexY = int(mousePoint.y())

            if self.data is not None:
                # Mouse click
                if indexX >= 0 and indexX < self.data.shape[0] \
                        and indexY >= 0 and indexY < self.data.shape[1]:
                    print "mouse clicked: ", mousePoint.x(), mousePoint.y(), self.data[indexX, indexY]
                    if self.mk.maskingMode > 0:
                        self.initMask()
                        if self.mk.maskingMode == 1:
                            # masking mode
                            self.mk.userMaskAssem[indexX, indexY] = 0
                        elif self.mk.maskingMode == 2:
                            # unmasking mode
                            self.mk.userMaskAssem[indexX, indexY] = 1
                        elif self.mk.maskingMode == 3:
                            # toggle mode
                            self.mk.userMaskAssem[indexX, indexY] = (1 - self.mk.userMaskAssem[indexX, indexY])
                        self.displayMask()

                        self.mk.userMask = self.det.ndarray_from_image(self.evt, self.mk.userMaskAssem,
                                                                       pix_scale_size_um=None, xy0_off_pix=None)
                        self.algInitDone = False
                        self.parent.pk.updateClassification()

        # Signal proxy
        self.proxy_move = pg.SignalProxy(self.xhair.scene().sigMouseMoved, rateLimit=30, slot=mouseMoved)
        self.proxy_click = pg.SignalProxy(self.xhair.scene().sigMouseClicked, slot=mouseClicked)

def main():
    global ex
#    import sys
    app = QtGui.QApplication(sys.argv)#([])
    win = Window()
    ex = MainFrame(sys.argv)
    win.setCentralWidget(ex.area)
    win.resize(1400,700)
    win.setWindowTitle('PSOCAKE')
    win.show()
    sys.exit(app.exec_())

## Start Qt event loop unless running in interactive mode or using pyside.
if __name__ == '__main__':
#    import sys
#    if (sys.flags.interactive != 1) or not hasattr(QtCore, 'PYQT_VERSION'):
#        QtGui.QApplication.instance().exec_()
    main()
