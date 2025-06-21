import ast
import os
import time
import struct
from functools import partial

from PySide6.QtCore import Qt, QRect, QAbstractItemModel
from PySide6.QtGui import QStandardItem, QStandardItemModel, QPalette, QColor, QAction, QShortcut, QKeySequence, QIcon
from PySide6.QtWidgets import QApplication, QMainWindow, QMenu, QHBoxLayout, QVBoxLayout, \
    QWidget, QSplitter, QFileDialog, QTabWidget, QColorDialog, QTableView, QStyledItemDelegate, QStyle, QToolButton, QStatusBar, QLabel, QMessageBox
from scipy.spatial.transform import Rotation
from PySide6.QtGui import QUndoCommand, QUndoStack




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

class SetDataCommand(QUndoCommand):
    def __init__(self, model, index, new_value, description="Edit Cell"):
        super().__init__(description)
        self.model = model
        self.index = index
        self.row = index.row()
        self.column = index.column()
        self.new_value = new_value
        self.old_value = index.data()

    def undo(self):
        self.model.blockSignals(True)
        self.model.setData(self.model.index(self.row, self.column), self.old_value)
        self.model.blockSignals(False)

    def redo(self):
        self.model.blockSignals(True)
        self.model.setData(self.model.index(self.row, self.column), self.new_value)
        self.model.blockSignals(False)

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

class EmitterRotation:

    def __init__(self):
        self.fileOffset = 0
        self.rotation = None

    @classmethod
    def fromBytes(cls, data):
        g = EmitterRotation()
        g.rotation = Rotation.from_matrix([
            list(struct.unpack("<fff", data[0:12])),
            list(struct.unpack("<fff", data[16:28])),
            list(struct.unpack("<fff", data[32:44]))
        ])
        return g

    def getRotationMatrix(self):
        return self.rotation.as_matrix()

    def getQuaternion(self):
        return self.rotation.as_quat()

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
    def __init__(self, undo_stack=None):
        super().__init__()
        self.undo_stack = undo_stack
        self.setHorizontalHeaderLabels(["Time 1", "Size 1", "Time 2", "Size 2", "Time 3", "Size 3", "Time 4", "Size 4", "Time 5", "Size 5", "Time 6", "Size 6", "Time 7", "Size 7", "Time 8", "Size 8", "Time 9", "Size 9", "Time 10", "Size 10"])
        self.sizes = []

    def setFileData(self, fileData):
        self.clear()
        self.sizes.clear()
        self.setHorizontalHeaderLabels(["Time 1", "Size 1", "Time 2", "Size 2", "Time 3", "Size 3", "Time 4", "Size 4", "Time 5", "Size 5", "Time 6", "Size 6", "Time 7", "Size 7", "Time 8", "Size 8", "Time 9", "Size 9", "Time 10", "Size 10"])
        offsets = [x-400 for x in find_all_occurrences(fileData, bytes.fromhex("FFFFFFFF0C00000008"))]
        offsets.extend([x-400 for x in find_all_occurrences(fileData, bytes.fromhex("FFFFFFFF0C00000001"))])
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
        if role == Qt.EditRole and self.undo_stack:
            class Command(QUndoCommand):
                def __init__(self, model, index, value):
                    super().__init__("Edit Size")
                    self.model = model
                    self.index = index
                    self.old = index.data()
                    self.new = value

                def undo(self): self.model._apply(index=self.index, value=self.old)
                def redo(self): self.model._apply(index=self.index, value=self.new)

            self.undo_stack.push(Command(self, index, value))
            return True
        return self._apply(index, value)

    def _apply(self, index, value):
        size = self.itemFromIndex(index.siblingAtColumn(0)).data()
        i = int(index.column() / 2)
        data = ast.literal_eval(value)
        if index.column() % 2 == 1:
            size.sizes[i][1] = struct.pack("<f", data)
        else:
            size.sizes[i][0] = struct.pack("<f", data)
        return super().setData(index, value, Qt.EditRole)

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

class RotationModel(QStandardItemModel):

    def __init__(self):
        super().__init__()
        self.setHorizontalHeaderLabels(["x axis", "y axis", "z axis"])
        self.rotations = []

    def setFileData(self, fileData):
        self.clear()
        self.rotations.clear()
        self.setHorizontalHeaderLabels(["x axis", "y axis", "z axis"])
        offsets = [x+36 for x in find_all_occurrences(fileData, bytes.fromhex("FFFFFFFFFFFFFFFF00000000FFFFFFFF00000000FFFFFFFF030576F2030576F200000000"))]
        root = self.invisibleRootItem()
        for offset in offsets:
            rotation = EmitterRotation.fromBytes(fileData[offset:offset+48])
            rotation.setOffset(offset)
            self.rotations.append(rotation)
            eulerAngles = rotation.rotation.as_euler('xyz', degrees=True)
            xData, yData, zData = eulerAngles
            xItem = QStandardItem(str(xData))
            xItem.setData(rotation)
            yItem = QStandardItem(str(yData))
            zItem = QStandardItem(str(zData))
            root.appendRow([xItem, yItem, zItem])

    def writeFileData(self, outFile):
        for rotation in self.rotations:
            rotationMatrix = rotation.getRotationMatrix()
            #quaternion = rotation.getQuaternion()
            outFile.seek(rotation.getOffset())
            for index, row in enumerate(rotationMatrix):
                for data in row:
                    outFile.write(struct.pack("<f", data))
                outFile.advance(4)
                #outFile.write(struct.pack("<f", quaternion[index]))

    def setData(self, index, value, role=Qt.EditRole):
        rotation = self.itemFromIndex(index.siblingAtColumn(0)).data()
        data = ast.literal_eval(value)
        euler = rotation.rotation.as_euler('xyz', degrees=True)
        euler[index.column()] = data
        rotation.rotation = Rotation.from_euler('xyz', euler, degrees=True)
        return super().setData(index, value, role)

class PositionModel(QStandardItemModel):

    def __init__(self):
        super().__init__()
        self.setHorizontalHeaderLabels(["x offset", "y offset", "z offset"])
        self.positions = []

    def setFileData(self, fileData):
        self.clear()
        self.positions.clear()
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
    def __init__(self, undo_stack=None):
        super().__init__()
        self.undo_stack = undo_stack
        self.file = MemoryStream()
        self.setHorizontalHeaderLabels(["Time 1", "Opacity 1", "Time 2", "Opacity 2", "Time 3", "Opacity 3", "Time 4", "Opacity 4", "Time 5", "Opacity 5", "Time 6", "Opacity 6", "Time 7", "Opacity 7", "Time 8", "Opacity 8", "Time 9", "Opacity 9", "Time 10", "Opacity 10"])
        self.gradients = []

    def setFileData(self, fileData):
        self.clear()
        self.gradients.clear()
        self.file = MemoryStream()
        self.file.write(fileData)
        self.setHorizontalHeaderLabels(["Time 1", "Opacity 1", "Time 2", "Opacity 2", "Time 3", "Opacity 3", "Time 4", "Opacity 4", "Time 5", "Opacity 5", "Time 6", "Opacity 6", "Time 7", "Opacity 7", "Time 8", "Opacity 8", "Time 9", "Opacity 9", "Time 10", "Opacity 10"])
        offsets = [x-240 for x in find_all_occurrences(fileData, bytes.fromhex("FFFFFFFF0C00000008"))]
        offsets.extend([x-240 for x in find_all_occurrences(fileData, bytes.fromhex("FFFFFFFF0C00000001"))])
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
        if role == Qt.EditRole and self.undo_stack:
            class Command(QUndoCommand):
                def __init__(self, model, index, value):
                    super().__init__("Edit Opacity")
                    self.model = model
                    self.index = index
                    self.old = index.data()
                    self.new = value

                def undo(self): self.model._apply(index=self.index, value=self.old)
                def redo(self): self.model._apply(index=self.index, value=self.new)

            self.undo_stack.push(Command(self, index, value))
            return True
        return self._apply(index, value)

    def _apply(self, index, value):
        gradient = self.itemFromIndex(index.siblingAtColumn(0)).data()
        i = int(index.column() / 2)
        data = ast.literal_eval(value)
        if index.column() % 2 == 1:
            gradient.opacities[i][1] = struct.pack("<f", data)
        else:
            gradient.opacities[i][0] = struct.pack("<f", data)
        return super().setData(index, value, Qt.EditRole)

class ColorGradientModel(QStandardItemModel):
    def __init__(self, undo_stack=None):
        super().__init__()
        self.undo_stack = undo_stack
        self.file = MemoryStream()
        self.setHorizontalHeaderLabels(["Time 1", "Color 1", "Time 2", "Color 2", "Time 3", "Color 3", "Time 4", "Color 4", "Time 5", "Color 5", "Time 6", "Color 6", "Time 7", "Color 7", "Time 8", "Color 8", "Time 9", "Color 9", "Time 10", "Color 10"])
        self.gradients = []

    def setFileData(self, fileData):
        self.clear()
        self.gradients.clear()
        self.file = MemoryStream()
        self.file.write(fileData)
        self.setHorizontalHeaderLabels(["Time 1", "Color 1", "Time 2", "Color 2", "Time 3", "Color 3", "Time 4", "Color 4", "Time 5", "Color 5", "Time 6", "Color 6", "Time 7", "Color 7", "Time 8", "Color 8", "Time 9", "Color 9", "Time 10", "Color 10"])
        offsets = [x-160 for x in find_all_occurrences(fileData, bytes.fromhex("FFFFFFFF0C00000008"))]
        offsets.extend([x-160 for x in find_all_occurrences(fileData, bytes.fromhex("FFFFFFFF0C00000001"))])
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
        if role == Qt.EditRole and self.undo_stack:
            class Command(QUndoCommand):
                def __init__(self, model, index, value):
                    super().__init__("Edit Color")
                    self.model = model
                    self.index = index
                    self.old = index.data()
                    self.new = value

                def undo(self): self.model._apply(index=self.index, value=self.old)
                def redo(self): self.model._apply(index=self.index, value=self.new)

            self.undo_stack.push(Command(self, index, value))
            return True
        return self._apply(index, value)

    def _apply(self, index, value):
        gradient = self.itemFromIndex(index.siblingAtColumn(0)).data()
        i = int(index.column() / 2)
        data = ast.literal_eval(value)
        if index.column() % 2 == 1:
            gradient.colors[i][1] = struct.pack("<fff", *data)
        else:
            gradient.colors[i][0] = struct.pack("<f", data)
        return super().setData(index, value, Qt.EditRole)

class OpacityTable(QTableView):

    def __init__(self, parent=None):
        super().__init__(parent)
        paste_shortcut = QShortcut(QKeySequence("Ctrl+V"), self)
        paste_shortcut.activated.connect(self.pasteFromClipboard)

        
    def pasteFromClipboard(self):
        clipboard = QApplication.clipboard()
        text = clipboard.text().strip()
        if not text:
            return

        selected = self.selectedIndexes()
        if not selected:
            return

        model: QAbstractItemModel = self.model()

        rows = text.split('\n')
        if len(rows) == 1 and '\t' not in text:
            # Single value: apply to all selected cells
            for index in selected:
                if index.isValid():
                    model.setData(index, text)
        else:
            # Multi-value paste starting from top-left
            data = [row.split('\t') for row in rows]
            top_left = sorted(selected, key=lambda idx: (idx.row(), idx.column()))[0]
            start_row = top_left.row()
            start_col = top_left.column()

            for r, row_data in enumerate(data):
                for c, cell in enumerate(row_data):
                    model_index = model.index(start_row + r, start_col + c)
                    if model_index.isValid():
                        model.setData(model_index, cell)

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

        # Add Ctrl+V shortcut
        paste_shortcut = QShortcut(QKeySequence("Ctrl+V"), self)
        paste_shortcut.activated.connect(self.pasteFromClipboard)

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

    def triggerColorPickerFromButton(self):
        selected = self.selectedIndexes()
        if len(selected) != 1:
            QMessageBox.warning(self, "Invalid Selection", "Please select one color cell.")
            return
        index = selected[0]
        if index.column() % 2 == 0:
            QMessageBox.warning(self, "Invalid Cell", "Please select a color cell (odd-numbered column).")
            return
        self.showColorPicker(None)  # We ignore 'pos' in showColorPicker anyway


    def showContextMenu(self, pos):
        self.contextMenu.clear()
        if not self.selectedIndexes() or len(self.selectedIndexes()) > 1:
            return
        if self.selectedIndexes()[0].column() % 2 == 1:
            self.contextMenu.addAction(self.contextMenuColorPickerAction)
            global_pos = self.mapToGlobal(pos)
            self.contextMenu.exec(global_pos)

    def pasteFromClipboard(self):
        clipboard = QApplication.clipboard()
        text = clipboard.text().strip()
        if not text:
            return

        selected = self.selectedIndexes()
        if not selected:
            return

        model: QAbstractItemModel = self.model()

        rows = text.split('\n')
        if len(rows) == 1 and '\t' not in text:
            # Single value: apply to all selected cells
            for index in selected:
                if index.isValid():
                    model.setData(index, text)
        else:
            # Multi-value paste starting from top-left
            data = [row.split('\t') for row in rows]
            top_left = sorted(selected, key=lambda idx: (idx.row(), idx.column()))[0]
            start_row = top_left.row()
            start_col = top_left.column()

            for r, row_data in enumerate(data):
                for c, cell in enumerate(row_data):
                    model_index = model.index(start_row + r, start_col + c)
                    if model_index.isValid():
                        model.setData(model_index, cell)

class ColorSwatchDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        text = index.data()
        if not text:
            super().paint(painter, option, index)
            return

        # Clean and parse RGB
        cleaned_text = text.strip().lstrip("(").rstrip(")")

        try:
            parts = [float(x.strip()) for x in cleaned_text.split(",")]
            if len(parts) != 3:
                raise ValueError("Not 3 components")
            r, g, b = [max(0, min(255, int(c))) for c in parts]
            color = QColor(r, g, b)
        except Exception:
            super().paint(painter, option, index)
            return

        # Draw selection background if selected
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())

        # Draw color swatch
        swatch_size = 16
        swatch_rect = QRect(
            option.rect.left() + 4,
            option.rect.center().y() - swatch_size // 2,
            swatch_size,
            swatch_size
        )
        painter.setPen(Qt.black)
        painter.setBrush(color)
        painter.drawRect(swatch_rect)

        # Draw the RGB text next to the swatch
        text_rect = QRect(
            swatch_rect.right() + 6,
            option.rect.top(),
            option.rect.width() - swatch_size - 10,
            option.rect.height()
        )
        painter.setPen(
            option.palette.highlightedText().color()
            if option.state & QStyle.State_Selected
            else Qt.black
        )
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, text)

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("HD2 Particle Modder - Version 2.0")
        self.setWindowIcon(QIcon("assets/icon.png"))
        self.resize(1100, 700)
        self.undoStack = QUndoStack(self)

        self.hidden_columns = {
            'color': set(),
            'opacity': set(),
            'size': set()
        }
        self.setStatusBar(QStatusBar(self))
        self.initComponents()
        self.filenameLabel = QLabel("No file loaded")
        self.connectComponents()
        self.layoutComponents()

    def initComponents(self):
        self.initMenuBar()
        self.initTabWidget()
        self.initColorView()
        self.initOpacityView()
        self.initLifetimeView()
        self.initSizeView()
        self.initPositionView()
        self.initRotationView()

    def connectComponents(self):
        self.fileOpenArchiveAction.triggered.connect(self.load_archive)
        self.fileSaveArchiveAction.triggered.connect(self.saveArchive)

    def layoutComponents(self):
        self.setMinimumSize(300, 200)
        self.layout = QVBoxLayout()

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.colorView)

        # Floating header strip widget
        filenameStrip = QWidget(self)
        filenameStripLayout = QHBoxLayout()
        filenameStripLayout.setContentsMargins(8, 4, 8, 4)

        self.filenameLabel.setText("No file loaded")
        self.filenameLabel.setStyleSheet("font-weight: bold; font-size: 12px; color: white; text-decoration: none;")

        self.openFileBtn = QToolButton(self)
        self.openFileBtn.setText("Open")
        self.openFileBtn.clicked.connect(lambda: self.load_archive())

        self.saveFileBtn = QToolButton(self)
        self.saveFileBtn.setText("Save")
        self.saveFileBtn.clicked.connect(lambda: self.saveArchive())

        filenameStripLayout.addWidget(self.filenameLabel)
        filenameStripLayout.addStretch()
        filenameStripLayout.addWidget(self.openFileBtn)
        filenameStripLayout.addWidget(self.saveFileBtn)

        filenameStrip.setLayout(filenameStripLayout)
        filenameStrip.setStyleSheet("""
            background-color: #434343;
        """)
        self.layout.addWidget(filenameStrip)

        self.layout.addWidget(self.tabWidget)

        # Color tab layout
        layout = QVBoxLayout()
        buttonLayout = QHBoxLayout()
        buttonLayout.addWidget(self.hideTimeColumnsBtn)
        self.hideTimeColumnsBtn.setToolTip("Toggle visibility of time columns")
        buttonLayout.addWidget(self.pickColorBtn)
        layout.addLayout(buttonLayout)
        layout.addWidget(self.colorView)
        self.colorTab.setLayout(layout)

        # Opacity tab layout
        layout = QVBoxLayout()
        opacityButtonLayout = QHBoxLayout()
        opacityButtonLayout.addWidget(self.hideOpacityTimeColumnsBtn)
        self.hideOpacityTimeColumnsBtn.setToolTip("Toggle visibility of time columns")
        layout.addLayout(opacityButtonLayout)
        layout.addWidget(self.opacityView)
        self.opacityTab.setLayout(layout)

        # Lifetime tab layout
        layout = QVBoxLayout()
        layout.addWidget(self.lifetimeView)
        self.lifetimeTab.setLayout(layout)

        # Size Scale tab layout
        layout = QVBoxLayout()
        sizeButtonLayout = QHBoxLayout()
        sizeButtonLayout.addWidget(self.hideSizeTimeColumnsBtn)
        self.hideSizeTimeColumnsBtn.setToolTip("Toggle visibility of time columns")
        layout.addLayout(sizeButtonLayout)
        layout.addWidget(self.sizeView)
        self.sizeTab.setLayout(layout)

        layout = QVBoxLayout()
        layout.addWidget(self.positionView)
        self.positionTab.setLayout(layout)

        layout = QVBoxLayout()
        layout.addWidget(self.rotationView)
        self.rotationTab.setLayout(layout)

        self.tabWidget.addTab(self.colorTab, "Color")
        self.tabWidget.addTab(self.opacityTab, "Opacity")
        self.tabWidget.addTab(self.lifetimeTab, "Lifetime")
        self.tabWidget.addTab(self.sizeTab, "Size Scale")
        self.tabWidget.addTab(self.positionTab, "Emitter Offset")
        self.tabWidget.addTab(self.rotationTab, "Emitter Rotation")

        widget = QWidget()
        widget.setLayout(self.layout)
        self.setCentralWidget(widget)

    def initColorView(self):
        self.colorView = ColorTable(self)
        self.colorViewModel = ColorGradientModel(self.undoStack)
        self.colorView.setModel(self.colorViewModel)

        delegate = ColorSwatchDelegate()
        self.colorView.setItemDelegate(delegate)

        self.pickColorBtn = QToolButton(self.colorTab)
        self.pickColorBtn.setText("Color Picker")
        self.pickColorBtn.setToolTip("Open Color Picker for selected color cell")
        self.pickColorBtn.clicked.connect(self.colorView.triggerColorPickerFromButton)


        self.hideTimeColumnsBtn = QToolButton(self.colorTab)
        self.hideTimeColumnsBtn.setText("Toggle Time Columns")
        self.hideTimeColumnsBtn.clicked.connect(self.toggleTimeColumns)

    def toggleTimeColumns(self):
        for col in range(self.colorViewModel.columnCount()):
            header = self.colorViewModel.headerData(col, Qt.Horizontal)
            if isinstance(header, str) and header.lower().startswith("time"):
                hidden = self.colorView.isColumnHidden(col)
                self.colorView.setColumnHidden(col, not hidden)
                if not hidden:
                    self.hidden_columns['color'].add(col)
                else:
                    self.hidden_columns['color'].discard(col)

    def initOpacityView(self):
        self.opacityView = OpacityTable(self)
        self.opacityViewModel = OpacityGradientModel(self.undoStack)
        self.opacityView.setModel(self.opacityViewModel)

        self.hideOpacityTimeColumnsBtn = QToolButton(self.opacityTab)
        self.hideOpacityTimeColumnsBtn.setText("Toggle Time Columns")
        self.hideOpacityTimeColumnsBtn.clicked.connect(self.toggleOpacityTimeColumns)

    def toggleOpacityTimeColumns(self):
        for col in range(self.opacityViewModel.columnCount()):
            header = self.opacityViewModel.headerData(col, Qt.Horizontal)
            if isinstance(header, str) and header.lower().startswith("time"):
                hidden = self.opacityView.isColumnHidden(col)
                self.opacityView.setColumnHidden(col, not hidden)
                if not hidden:
                    self.hidden_columns['opacity'].add(col)
                else:
                    self.hidden_columns['opacity'].discard(col)

    def initSizeView(self):
        self.sizeView = QTableView(self)
        self.sizeViewModel = SizeModel(self.undoStack)
        self.sizeView.setModel(self.sizeViewModel)

        self.hideSizeTimeColumnsBtn = QToolButton(self.sizeTab)
        self.hideSizeTimeColumnsBtn.setText("Toggle Time Columns")
        self.hideSizeTimeColumnsBtn.clicked.connect(self.toggleSizeTimeColumns)

    def toggleSizeTimeColumns(self):
        for col in range(self.sizeViewModel.columnCount()):
            header = self.sizeViewModel.headerData(col, Qt.Horizontal)
            if isinstance(header, str) and header.lower().startswith("time"):
                hidden = self.sizeView.isColumnHidden(col)
                self.sizeView.setColumnHidden(col, not hidden)
                if not hidden:
                    self.hidden_columns['size'].add(col)
                else:
                    self.hidden_columns['size'].discard(col)

    def applyHiddenColumns(self, key, tableView):
        for col in range(tableView.model().columnCount()):
            tableView.setColumnHidden(col, col in self.hidden_columns[key])

    def initLifetimeView(self):
        self.lifetimeView = QTableView(self)
        self.lifetimeViewModel = LifetimeModel()
        self.lifetimeView.setModel(self.lifetimeViewModel)

    def initPositionView(self):
        self.positionView = QTableView(self)
        self.positionViewModel = PositionModel()
        self.positionView.setModel(self.positionViewModel)

    def initRotationView(self):
        self.rotationView = QTableView(self)
        self.rotationViewModel = RotationModel()
        self.rotationView.setModel(self.rotationViewModel)

    def initTabWidget(self):
        self.tabWidget = QTabWidget(self)
        self.colorTab = QWidget(self.tabWidget)
        self.opacityTab = QWidget(self.tabWidget)
        self.lifetimeTab = QWidget(self.tabWidget)
        self.sizeTab = QWidget(self.tabWidget)
        self.positionTab = QWidget(self.tabWidget)
        self.rotationTab = QWidget(self.tabWidget)

    def initMenuBar(self):
        menu_bar = self.menuBar()

        self.file_menu = menu_bar.addMenu("File")

        self.fileOpenArchiveAction = QAction("Open", self)
        self.fileSaveArchiveAction = QAction("Save", self)

        self.file_menu.addAction(self.fileOpenArchiveAction)
        self.file_menu.addAction(self.fileSaveArchiveAction)

        self.edit_menu = menu_bar.addMenu("Edit")
        self.undo_action = self.undoStack.createUndoAction(self, "Undo")
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.redo_action = self.undoStack.createRedoAction(self, "Redo")
        self.redo_action.setShortcut(QKeySequence.Redo)
        self.edit_menu.addAction(self.undo_action)
        self.edit_menu.addAction(self.redo_action)

    def load_archive(self, initialdir: str | None = '', archive_file: str | None = ""):
        if not archive_file:
            archive_file = QFileDialog.getOpenFileName(self, "Select archive", str(initialdir), "All Files (*.*)")
            archive_file = archive_file[0]
            self.filenameLabel.setText(f"File: {os.path.basename(archive_file)}")
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
            self.rotationViewModel.setFileData(self.data)

            # Reapply hidden column states
            self.applyHiddenColumns('color', self.colorView)
            self.applyHiddenColumns('opacity', self.opacityView)
            self.applyHiddenColumns('size', self.sizeView)
            self.statusBar().showMessage(f"Loaded: {os.path.basename(self.name)}", 5000)
            stat = os.stat(archive_file)
            modified_time = time.strftime('%Y-%m-%d %H:%M', time.localtime(stat.st_mtime))

            self.filenameLabel.setText(f"{os.path.basename(archive_file)} — last modified: {modified_time}")

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
            self.rotationViewModel.writeFileData(data)
            f.write(data.data)

            self.statusBar().showMessage(f"Saved: {os.path.basename(archive_file)}", 5000)

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            filename = url.toLocalFile()
            if os.path.isfile(filename):
                self.load_archive(archive_file=filename)

    def dragEnterEvent(self, event):
        for url in event.mimeData().urls():
            if not os.path.isfile(url.toLocalFile()):
                event.ignore()
                return
        event.accept()

    def dragMoveEvent(self, event):
        for url in event.mimeData().urls():
            if not os.path.isfile(url.toLocalFile()):
                event.ignore()
                return
        event.accept()

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