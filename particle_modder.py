from typing import Any
import struct
import os
from math import ceil
from itertools import takewhile
import ast

from PySide6.QtCore import QSize, Qt, Signal, QMargins, QSortFilterProxyModel, QItemSelection, QItemSelectionModel
from PySide6.QtWidgets import QApplication, QMainWindow, QTreeView, QFileSystemModel, QMenu, QHBoxLayout, QVBoxLayout, QAbstractItemView, QSizePolicy, QWidget, QSplitter, QListView, QPushButton, QSpacerItem, QFileDialog, QLabel, QTabWidget, QColorDialog, QTableView
from PySide6.QtGui import QStandardItem, QStandardItemModel, QPalette, QColor, QAction

class MemoryStream:
    '''
    Modified from https://github.com/kboykboy2/io_scene_helldivers2 with permission from kboykboy
    '''
    def __init__(self, Data=b"", io_mode = "read"):
        self.location = 0
        self.data = bytearray(Data)
        self.io_mode = io_mode
        self.endian = "<"

    def open(self, Data, io_mode = "read"): # Open Stream
        self.data = bytearray(Data)
        self.io_mode = io_mode

    def set_read_mode(self):
        self.io_mode = "read"

    def set_write_mode(self):
        self.io_mode = "write"

    def is_reading(self):
        return self.io_mode == "read"

    def is_writing(self):
        return self.io_mode == "write"

    def seek(self, location): # Go To Position In Stream
        self.location = location
        if self.location > len(self.data):
            missing_bytes = self.location - len(self.data)
            self.data += bytearray(missing_bytes)

    def tell(self): # Get Position In Stream
        return self.location

    def read(self, length=-1): # read Bytes From Stream
        if length == -1:
            length = len(self.data) - self.location
        if self.location + length > len(self.data):
            raise Exception("reading past end of stream")

        newData = self.data[self.location:self.location+length]
        self.location += length
        return bytearray(newData)
        
    def advance(self, offset):
        self.location += offset
        if self.location < 0:
            self.location = 0
        if self.location > len(self.data):
            missing_bytes = self.location - len(self.data)
            self.data += bytearray(missing_bytes)

    def write(self, bytes): # Write Bytes To Stream
        length = len(bytes)
        if self.location + length > len(self.data):
            missing_bytes = (self.location + length) - len(self.data)
            self.data += bytearray(missing_bytes)
        self.data[self.location:self.location+length] = bytearray(bytes)
        self.location += length

    def read_format(self, format, size):
        format = self.endian+format
        return struct.unpack(format, self.read(size))[0]
        
    def bytes(self, value, size = -1):
        if size == -1:
            size = len(value)
        if len(value) != size:
            value = bytearray(size)

        if self.is_reading():
            return bytearray(self.read(size))
        elif self.is_writing():
            self.write(value)
            return bytearray(value)
        return value
        
    def int8_read(self):
        return self.read_format('b', 1)

    def uint8_read(self):
        return self.read_format('B', 1)

    def int16_read(self):
        return self.read_format('h', 2)

    def uint16_read(self):
        return self.read_format('H', 2)

    def int32_read(self):
        return self.read_format('i', 4)

    def uint32_read(self):
        return self.read_format('I', 4)

    def int64_read(self):
        return self.read_format('q', 8)

    def uint64_read(self):
        return self.read_format('Q', 8)
        
class OpacityGradient:
    
    def __init__(self):
        self.fileOffset = 0
        self.opacities = []
        
    @classmethod
    def fromBytes(cls, data):
        g = OpacityGradient()
        for n in range(10):
            g.opacities.append([data[n*4:(n+1)*4], data[40+n*4:40+(n+1)*4]])
        return g
            
    def setOffset(self, offset):
        self.fileOffset = offset
        
    def getOffset(self):
        return self.fileOffset
        
class Size:
    
    def __init__(self):
        self.fileOffset = 0
        self.sizes = []
        
    @classmethod
    def fromBytes(cls, data):
        g = Size()
        for n in range(10):
            g.sizes.append([data[n*4:(n+1)*4], data[40+n*4:40+(n+1)*4]])
        return g
            
    def setOffset(self, offset):
        self.fileOffset = offset
        
    def getOffset(self):
        return self.fileOffset
        
class EmitterPosition:
    
    def __init__(self):
        self.fileOffset = 0
        self.position = [0, 0, 0]
        
    @classmethod
    def fromBytes(cls, data):
        g = EmitterPosition()
        g.position = [data[0:4], data[4:8], data[8:12]]
        return g
            
    def setOffset(self, offset):
        self.fileOffset = offset
        
    def getOffset(self):
        return self.fileOffset
        
        

class ColorGradient:
    
    def __init__(self):
        self.fileOffset = 0
        self.colors = []
        
    @classmethod
    def fromBytes(cls, data):
        g = ColorGradient()
        for n in range(10):
            g.colors.append([data[n*4:(n+1)*4], data[40+n*12:40+(n+1)*12]])
        return g
            
    def setOffset(self, offset):
        self.fileOffset = offset
        
    def getOffset(self):
        return self.fileOffset
        
def find_all_occurrences(text, substring):
    indices = []
    start_index = 0
    while True:
        index = text.find(substring, start_index)
        if index == -1:
            break
        indices.append(index)
        start_index = index + 1
    return indices
    
class SizeModel(QStandardItemModel):
    
    def __init__(self):
        super().__init__()
        self.setHorizontalHeaderLabels(["Time 1", "Size 1", "Time 2", "Size 2", "Time 3", "Size 3", "Time 4", "Size 4", "Time 5", "Size 5", "Time 6", "Size 6", "Time 7", "Size 7", "Time 8", "Size 8", "Time 9", "Size 9", "Time 10", "Size 10"])
        self.sizes = []

    def setFileData(self, fileData):
        self.clear()
        self.sizes.clear()
        self.file = MemoryStream()
        self.file.write(fileData)
        self.setHorizontalHeaderLabels(["Time 1", "Size 1", "Time 2", "Size 2", "Time 3", "Size 3", "Time 4", "Size 4", "Time 5", "Size 5", "Time 6", "Size 6", "Time 7", "Size 7", "Time 8", "Size 8", "Time 9", "Size 9", "Time 10", "Size 10"])
        offsets = [x-400 for x in find_all_occurrences(fileData, bytes.fromhex("FFFFFFFF0C00000008000000"))]
        root = self.invisibleRootItem()
        for offset in offsets:
            size = Size.fromBytes(fileData[offset:offset+80])
            size.setOffset(offset)
            self.sizes.append(size)
            arr = []
            for i in range(10):
                timeData = struct.unpack("<f", size.sizes[i][0])[0]
                timeItem = QStandardItem(str(timeData))
                if i == 0:
                    timeItem.setData(size)
                sizeData = struct.unpack('<f', size.sizes[i][1])[0]
                sizeItem = QStandardItem(str(sizeData))
                arr.append(timeItem)
                arr.append(sizeItem)
            root.appendRow(arr)
            
    def writeFileData(self, outFile):
        for size in self.sizes:
            offset = size.getOffset()
            outFile.seek(offset)
            for index, s in enumerate(size.sizes):
                outFile.seek(offset + index*4)
                outFile.write(s[0])
                outFile.seek(offset + 40 + index*4)
                outFile.write(s[1])
                
                outFile.seek(offset - 80 + index*4)
                outFile.write(s[0])
                outFile.seek(offset - 40 + index*4)
                outFile.write(s[1])

    def setData(self, index, value, role=Qt.EditRole):
        size = self.itemFromIndex(index.siblingAtColumn(0)).data()
        i = int(index.column()/2)
        data = ast.literal_eval(value)
        if index.column() % 2 == 1:
            size.sizes[i][1] = struct.pack("<f", data)
        else:
            size.sizes[i][0] = struct.pack("<f", data)
        
        return super().setData(index, value, role)

class LifetimeModel(QStandardItemModel):
    
    def __init__(self):
        super().__init__()
        self.setHorizontalHeaderLabels(["Min", "Max"])
        self.lifetime = [0, 0]

    def setFileData(self, fileData):
        self.clear()
        self.lifetime[0] = struct.unpack("<f", fileData[4:8])[0]
        self.lifetime[1] = struct.unpack("<f", fileData[8:12])[0]
        self.setHorizontalHeaderLabels(["Min", "Max"])
        root = self.invisibleRootItem()
        minItem = QStandardItem(str(self.lifetime[0]))
        maxItem = QStandardItem(str(self.lifetime[1]))
        root.appendRow([minItem, maxItem])
            
    def writeFileData(self, outFile):
        outFile.seek(4)
        outFile.write(struct.pack("<ff", *self.lifetime))

    def setData(self, index, value, role=Qt.EditRole):
        i = int(index.column()/2)
        data = float(ast.literal_eval(value))
        if index.column() % 2 == 1:
            self.lifetime[1] = data
        else:
            self.lifetime[0] = data
        
        return super().setData(index, value, role)
        
class PositionModel(QStandardItemModel):
    
    def __init__(self):
        super().__init__()
        self.setHorizontalHeaderLabels(["x offset", "y offset", "z offset"])
        self.positions = []
        
    def setFileData(self, fileData):
        self.clear()
        self.setHorizontalHeaderLabels(["x offset", "y offset", "z offset"])
        offsets = [x+84 for x in find_all_occurrences(fileData, bytes.fromhex("FFFFFFFFFFFFFFFF00000000FFFFFFFF00000000FFFFFFFF030576F2030576F200000000"))]
        root = self.invisibleRootItem()
        for offset in offsets:
            position = EmitterPosition.fromBytes(fileData[offset:offset+12])
            position.setOffset(offset)
            self.positions.append(position)
            xData = struct.unpack("<f", position.position[0])[0]
            yData = struct.unpack("<f", position.position[1])[0]
            zData = struct.unpack("<f", position.position[2])[0]
            xItem = QStandardItem(str(xData))
            xItem.setData(position)
            yItem = QStandardItem(str(yData))
            zItem = QStandardItem(str(zData))
            root.appendRow([xItem, yItem, zItem])
            
    def writeFileData(self, outFile):
        for position in self.positions:
            outFile.seek(position.getOffset())
            outFile.write(position.position[0])
            outFile.write(position.position[1])
            outFile.write(position.position[2])
            
    def setData(self, index, value, role=Qt.EditRole):
        position = self.itemFromIndex(index.siblingAtColumn(0)).data()
        data = ast.literal_eval(value)
        position.position[index.column()] = struct.pack("<f", data)
        return super().setData(index, value, role)
    
class OpacityGradientModel(QStandardItemModel):
    
    def __init__(self):
        super().__init__()
        self.file = MemoryStream()
        self.setHorizontalHeaderLabels(["Time 1", "Opacity 1", "Time 2", "Opacity 2", "Time 3", "Opacity 3", "Time 4", "Opacity 4", "Time 5", "Opacity 5", "Time 6", "Opacity 6", "Time 7", "Opacity 7", "Time 8", "Opacity 8", "Time 9", "Opacity 9", "Time 10", "Opacity 10"])
        self.gradients = []

    def setFileData(self, fileData):
        self.clear()
        self.gradients.clear()
        self.file = MemoryStream()
        self.file.write(fileData)
        self.setHorizontalHeaderLabels(["Time 1", "Opacity 1", "Time 2", "Opacity 2", "Time 3", "Opacity 3", "Time 4", "Opacity 4", "Time 5", "Opacity 5", "Time 6", "Opacity 6", "Time 7", "Opacity 7", "Time 8", "Opacity 8", "Time 9", "Opacity 9", "Time 10", "Opacity 10"])
        offsets = [x-240 for x in find_all_occurrences(fileData, bytes.fromhex("FFFFFFFF0C00000008000000"))]
        root = self.invisibleRootItem()
        for offset in offsets:
            gradient = OpacityGradient.fromBytes(fileData[offset:offset+80])
            gradient.setOffset(offset)
            self.gradients.append(gradient)
            arr = []
            for i in range(10):
                timeData = struct.unpack("<f", gradient.opacities[i][0])[0]
                timeItem = QStandardItem(str(timeData))
                if i == 0:
                    timeItem.setData(gradient)
                opacityData = struct.unpack('<f', gradient.opacities[i][1])[0]
                opacityItem = QStandardItem(str(opacityData))
                arr.append(timeItem)
                arr.append(opacityItem)
            root.appendRow(arr)
            
    def writeFileData(self, outFile):
        for gradient in self.gradients:
            offset = gradient.getOffset()
            outFile.seek(offset)
            for index, opacity in enumerate(gradient.opacities):
                outFile.seek(offset + index*4)
                outFile.write(opacity[0])
                outFile.seek(offset + 40 + index*4)
                outFile.write(opacity[1])
                
                outFile.seek(offset - 80 + index*4)
                outFile.write(opacity[0])
                outFile.seek(offset - 40 + index*4)
                outFile.write(opacity[1])

    def setData(self, index, value, role=Qt.EditRole):
        gradient = self.itemFromIndex(index.siblingAtColumn(0)).data()
        i = int(index.column()/2)
        data = ast.literal_eval(value)
        if index.column() % 2 == 1:
            gradient.opacities[i][1] = struct.pack("<f", data)
        else:
            gradient.opacities[i][0] = struct.pack("<f", data)
        
        return super().setData(index, value, role)
    
class ColorGradientModel(QStandardItemModel):
    
    def __init__(self):
        super().__init__()
        self.file = MemoryStream()
        self.setHorizontalHeaderLabels(["Time 1", "Color 1", "Time 2", "Color 2", "Time 3", "Color 3", "Time 4", "Color 4", "Time 5", "Color 5", "Time 6", "Color 6", "Time 7", "Color 7", "Time 8", "Color 8", "Time 9", "Color 9", "Time 10", "Color 10"])
        self.gradients = []

    def setFileData(self, fileData):
        self.clear()
        self.gradients.clear()
        self.file = MemoryStream()
        self.file.write(fileData)
        self.setHorizontalHeaderLabels(["Time 1", "Color 1", "Time 2", "Color 2", "Time 3", "Color 3", "Time 4", "Color 4", "Time 5", "Color 5", "Time 6", "Color 6", "Time 7", "Color 7", "Time 8", "Color 8", "Time 9", "Color 9", "Time 10", "Color 10"])
        offsets = [x-160 for x in find_all_occurrences(fileData, bytes.fromhex("FFFFFFFF0C00000008000000"))]
        root = self.invisibleRootItem()
        for offset in offsets:
            gradient = ColorGradient.fromBytes(fileData[offset:offset+160])
            gradient.setOffset(offset)
            self.gradients.append(gradient)
            arr = []
            for i in range(10):
                timeData = struct.unpack("<f", gradient.colors[i][0])[0]
                timeItem = QStandardItem(str(timeData))
                if i == 0:
                    timeItem.setData(gradient)
                colorData = struct.unpack('<fff', gradient.colors[i][1])
                colorItem = QStandardItem(str(colorData))
                arr.append(timeItem)
                arr.append(colorItem)
            root.appendRow(arr)
            
    def writeFileData(self, outFile):
        for gradient in self.gradients:
            offset = gradient.getOffset()
            outFile.seek(offset)
            for index, color in enumerate(gradient.colors):
                outFile.seek(offset + index*4)
                outFile.write(color[0])
                outFile.seek(40 + offset + index*12)
                outFile.write(color[1])

    def setData(self, index, value, role=Qt.EditRole):
        gradient = self.itemFromIndex(index.siblingAtColumn(0)).data()
        i = int(index.column()/2)
        data = ast.literal_eval(value)
        if index.column() % 2 == 1:
            gradient.colors[i][1] = struct.pack("<fff", *data)
        else:
            gradient.colors[i][0] = struct.pack("<f", data)
        
        return super().setData(index, value, role)
        
class OpacityTable(QTableView):
    
    def __init__(self, parent=None):
        super().__init__(parent)
		
class ColorTable(QTableView):
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()
        
    def initUI(self):
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.showContextMenu)
        self.contextMenuColorPickerAction = QAction("Color Picker")
        self.contextMenuColorPickerAction.triggered.connect(self.showColorPicker)
        self.contextMenu = QMenu(self)
        
    def showColorPicker(self, pos):
        assert(len(self.selectedIndexes()) == 1)
        index = self.selectedIndexes()[0]
        colorTuple = ast.literal_eval(self.model().itemFromIndex(index).text())
        color = QColor(*colorTuple)
        selectedColor = QColorDialog.getColor(initial=color, parent=self, title="Select New Color")
        try:
            colorTuple = selectedColor.toTuple()[0:3]
            self.model().setData(index, str(colorTuple))
        except:
            pass
        
    def showContextMenu(self, pos):
        self.contextMenu.clear()
        if not self.selectedIndexes() or len(self.selectedIndexes()) > 1:
            return
        if self.selectedIndexes()[0].column() % 2 == 1:
            self.contextMenu.addAction(self.contextMenuColorPickerAction)
            global_pos = self.mapToGlobal(pos)
            self.contextMenu.exec(global_pos)
		
class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("HD2 Particle Modder")
        self.resize(720, 720)
        
        self.initComponents()
        self.connectComponents()
        self.layoutComponents()
        
        
    def initComponents(self):
        self.initMenuBar()
        self.initColorView()
        self.initOpacityView()
        self.initLifetimeView()
        self.initSizeView()
        self.initPositionView()
        self.initTabWidget()
        
    def connectComponents(self):
        self.fileOpenArchiveAction.triggered.connect(self.load_archive)
        self.fileSaveArchiveAction.triggered.connect(self.saveArchive)
        
    def layoutComponents(self):
        pass
        self.setMinimumSize(300, 200)
        self.layout = QVBoxLayout()

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.colorView)
        
        self.layout.addWidget(self.tabWidget)
        
        layout = QVBoxLayout()
        layout.addWidget(self.colorView)
        self.colorTab.setLayout(layout)
        layout = QVBoxLayout()
        layout.addWidget(self.opacityView)
        self.opacityTab.setLayout(layout)
        layout = QVBoxLayout()
        layout.addWidget(self.lifetimeView)
        self.lifetimeTab.setLayout(layout)
        layout = QVBoxLayout()
        layout.addWidget(self.sizeView)
        self.sizeTab.setLayout(layout)
        layout = QVBoxLayout()
        layout.addWidget(self.positionView)
        self.positionTab.setLayout(layout)
        
        self.tabWidget.addTab(self.colorTab, "Color")
        self.tabWidget.addTab(self.opacityTab, "Opacity")
        self.tabWidget.addTab(self.lifetimeTab, "Lifetime")
        self.tabWidget.addTab(self.sizeTab, "Size Scale")
        self.tabWidget.addTab(self.positionTab, "Emitter Offset")
        
        widget = QWidget()
        widget.setLayout(self.layout)
        self.setCentralWidget(widget)
        
    def initColorView(self):
        self.colorView = ColorTable(self)
        self.colorViewModel = ColorGradientModel()
        self.colorView.setModel(self.colorViewModel)
        
    def initOpacityView(self):
        self.opacityView = OpacityTable(self)
        self.opacityViewModel = OpacityGradientModel()
        self.opacityView.setModel(self.opacityViewModel)
        
    def initLifetimeView(self):
        self.lifetimeView = QTableView(self)
        self.lifetimeViewModel = LifetimeModel()
        self.lifetimeView.setModel(self.lifetimeViewModel)
        
    def initSizeView(self):
        self.sizeView = QTableView(self)
        self.sizeViewModel = SizeModel()
        self.sizeView.setModel(self.sizeViewModel)
        
    def initPositionView(self):
        self.positionView = QTableView(self)
        self.positionViewModel = PositionModel()
        self.positionView.setModel(self.positionViewModel)
        
    def initTabWidget(self):
        self.tabWidget = QTabWidget(self)
        self.colorTab = QWidget(self.tabWidget)
        self.opacityTab = QWidget(self.tabWidget)
        self.lifetimeTab = QWidget(self.tabWidget)
        self.sizeTab = QWidget(self.tabWidget)
        self.positionTab = QWidget(self.tabWidget)
        
    def initMenuBar(self):
        menu_bar = self.menuBar()
        
        self.file_menu = menu_bar.addMenu("File")
        
        self.fileOpenArchiveAction = QAction("Open", self)
        self.fileSaveArchiveAction = QAction("Save", self)
        
        self.file_menu.addAction(self.fileOpenArchiveAction)
        self.file_menu.addAction(self.fileSaveArchiveAction)

    def load_archive(self, initialdir: str | None = '', archive_file: str | None = ""):
        if not archive_file:
            archive_file = QFileDialog.getOpenFileName(self, "Select archive", str(initialdir), "All Files (*.*)")
            archive_file = archive_file[0]
        if not archive_file:
            return
        self.name = archive_file
        with open(archive_file, "rb") as f:
            self.data = f.read()
            self.colorViewModel.setFileData(self.data)
            self.opacityViewModel.setFileData(self.data)
            self.lifetimeViewModel.setFileData(self.data)
            self.sizeViewModel.setFileData(self.data)
            self.positionViewModel.setFileData(self.data)
            
    def saveArchive(self, initialdir: str | None = '', archive_file: str | None = ""):
        if not archive_file:
            archive_file = QFileDialog.getSaveFileName(self, "Select archive", self.name)
            archive_file = archive_file[0]
        if not archive_file:
            return
        with open(archive_file, "wb") as f:
            data = MemoryStream()
            data.write(self.data)
            self.colorViewModel.writeFileData(data)
            self.lifetimeViewModel.writeFileData(data)
            self.opacityViewModel.writeFileData(data)
            self.sizeViewModel.writeFileData(data)
            self.positionViewModel.writeFileData(data)
            f.write(data.data)
        
def get_dark_mode_palette( app=None ):
    
    darkPalette = app.palette()
    darkPalette.setColor( QPalette.Window, QColor( 53, 53, 53 ) )
    darkPalette.setColor( QPalette.WindowText, Qt.white )
    darkPalette.setColor( QPalette.Disabled, QPalette.WindowText, QColor( 127, 127, 127 ) )
    darkPalette.setColor( QPalette.Base, QColor( 42, 42, 42 ) )
    darkPalette.setColor( QPalette.AlternateBase, QColor( 66, 66, 66 ) )
    darkPalette.setColor( QPalette.ToolTipBase, QColor( 53, 53, 53 ) )
    darkPalette.setColor( QPalette.ToolTipText, Qt.white )
    darkPalette.setColor( QPalette.Text, Qt.white )
    darkPalette.setColor( QPalette.Disabled, QPalette.Text, QColor( 127, 127, 127 ) )
    darkPalette.setColor( QPalette.Dark, QColor( 35, 35, 35 ) )
    darkPalette.setColor( QPalette.Shadow, QColor( 20, 20, 20 ) )
    darkPalette.setColor( QPalette.Button, QColor( 53, 53, 53 ) )
    darkPalette.setColor( QPalette.ButtonText, Qt.white )
    darkPalette.setColor( QPalette.Disabled, QPalette.ButtonText, QColor( 127, 127, 127 ) )
    darkPalette.setColor( QPalette.BrightText, Qt.red )
    darkPalette.setColor( QPalette.Link, QColor( 42, 130, 218 ) )
    darkPalette.setColor( QPalette.Highlight, QColor( 42, 130, 218 ) )
    darkPalette.setColor( QPalette.Disabled, QPalette.Highlight, QColor( 80, 80, 80 ) )
    darkPalette.setColor( QPalette.HighlightedText, Qt.white )
    darkPalette.setColor( QPalette.Disabled, QPalette.HighlightedText, QColor( 127, 127, 127 ), )
    
    return darkPalette
        
if __name__ == "__main__":
    app = QApplication([])
    app.setStyle("Fusion")
    app.setPalette(get_dark_mode_palette(app))
    
    window = MainWindow()
    
    window.show()
    
    app.exec()