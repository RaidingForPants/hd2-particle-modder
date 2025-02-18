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
        
    def setTimeData(self, index, data):
        pass
    
    def setColorData(self, index, data):
        pass
        
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
            self.file.seek(offset)
            for index, color in enumerate(gradient.colors):
                self.file.seek(offset + index*4)
                self.file.write(color[0])
                self.file.seek(40 + offset + index*12)
                self.file.write(color[1])
        outFile.write(self.file.data)

    def setData(self, index, value, role=Qt.EditRole):
        gradient = self.itemFromIndex(index.siblingAtColumn(0)).data()
        i = int(index.column()/2)
        data = ast.literal_eval(value)
        if index.column() % 2 == 1:
            gradient.colors[i][1] = struct.pack("<fff", *data)
        else:
            gradient.colors[i][0] = struct.pack("<f", data)
        
        return super().setData(index, value, role)
		
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
        self.initTableView()
        
    def connectComponents(self):
        self.fileOpenArchiveAction.triggered.connect(self.load_archive)
        self.fileSaveArchiveAction.triggered.connect(self.saveArchive)
        
    def layoutComponents(self):
        pass
        self.setMinimumSize(300, 200)
        self.layout = QVBoxLayout()

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.tableView)
        
        self.layout.addWidget(self.splitter)
        
        widget = QWidget()
        widget.setLayout(self.layout)
        self.setCentralWidget(widget)
        
    def initTableView(self):
        self.tableView = ColorTable(self)
        self.tableViewModel = ColorGradientModel()
        self.tableView.setModel(self.tableViewModel)
        
    def initMenuBar(self):
        menu_bar = self.menuBar()
        
        self.file_menu = menu_bar.addMenu("File")
        
        self.fileOpenArchiveAction = QAction("Open Archive", self)
        self.fileSaveArchiveAction = QAction("Save Archive", self)
        
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
            self.tableViewModel.setFileData(f.read())
            
    def saveArchive(self, initialdir: str | None = '', archive_file: str | None = ""):
        if not archive_file:
            archive_file = QFileDialog.getSaveFileName(self, "Select archive", self.name)
            archive_file = archive_file[0]
        if not archive_file:
            return
        with open(archive_file, "wb") as f:
            self.tableViewModel.writeFileData(f)
        
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