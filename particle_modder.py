import ast
import os
import time
import struct
from functools import partial
import xml.etree.cElementTree as ET

from PySide6.QtCore import Qt, QRect, QAbstractItemModel, Signal, QXmlStreamWriter, QXmlStreamReader
from PySide6.QtCharts import QLineSeries, QChart, QChartView, QValueAxis
from PySide6.QtGui import QStandardItem, QStandardItemModel, QPalette, QColor, QAction, QShortcut, QKeySequence, QIcon, QDoubleValidator, QValidator, QPen, QIntValidator
from PySide6.QtWidgets import QApplication, QMainWindow, QMenu, QHBoxLayout, QVBoxLayout, \
    QWidget, QSplitter, QFileDialog, QTabWidget, QColorDialog, QTableView, QStyledItemDelegate, QStyle, QToolButton, QStatusBar, QLabel, QMessageBox, QFileSystemModel, QLineEdit, QTreeWidget, QTreeWidgetItem
from scipy.spatial.transform import Rotation
from PySide6.QtGui import QUndoCommand, QUndoStack

VERSION = 2.0

class EmitterPosition:

    def __init__(self):
        self.fileOffset = 0
        self.position = [0, 0, 0]

    @classmethod
    def fromBytes(cls, data):
        g = EmitterPosition()
        g.position = list(struct.unpack("<fff", data[0:12]))
        return g
        
    def to_bytes(self):
        return struct.pack("<fff", *self.position)

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
        
    def to_bytes(self):
        rot_mat = self.rotation.as_matrix()
        row1 = struct.pack("<fff", *rot_mat[0])
        row2 = struct.pack("<fff", *rot_mat[1])
        row3 = struct.pack("<fff", *rot_mat[2])
        zero_as_bytes = bytearray(4)
        return row1 + zero_as_bytes + row2 + zero_as_bytes + row3 + zero_as_bytes

    def getRotationMatrix(self):
        return self.rotation.as_matrix()

    def getQuaternion(self):
        return self.rotation.as_quat()

    def setOffset(self, offset):
        self.fileOffset = offset

    def getOffset(self):
        return self.fileOffset

class Visualizer:
    
    BILLBOARD = 0
    LIGHT = 1
    MESH = 2
    
    def __init__(self):
        pass
    
    def from_memory_stream(self, stream):
        self.visualizer_type = stream.uint32_read()
        if self.visualizer_type == Visualizer.BILLBOARD:
            self.unk1 = stream.uint32_read()
            self.unk2 = stream.uint32_read()
            self.material_id = stream.uint64_read()
            self.data = stream.read(240)
        elif self.visualizer_type == Visualizer.LIGHT:
            self.data = stream.read(256)
        elif self.visualizer_type == Visualizer.MESH:
            self.unit_id = stream.uint64_read()
            self.mesh_id = stream.uint64_read()
            self.material_id = stream.uint64_read()
            self.data = stream.read(224)
            
    def write_to_memory_stream(self, stream):
        if self.visualizer_type == Visualizer.BILLBOARD:
            data = struct.pack("<IIIQ", self.visualizer_type, self.unk1, self.unk2, self.material_id) + self.data
            stream.write(data)
        elif self.visualizer_type == Visualizer.LIGHT:
            data = struct.pack("<I", self.visualizer_type) + self.data
            stream.write(data)
        elif self.visualizer_type == Visualizer.MESH:
            data = struct.pack("<IQQQ", self.visualizer_type, self.unit_id, self.mesh_id, self.material_id) + self.data
            stream.write(data)
        
class Graph:
    def __init__(self):
        pass
        
    def from_memory_stream(self, stream):
        self.x = [stream.float32_read() for _ in range(10)]
        self.y = [stream.float32_read() for _ in range(10)]
        
    def write_to_memory_stream(self, stream):
        stream.write(struct.pack("<ffffffffff", *self.x))
        stream.write(struct.pack("<ffffffffff", *self.y))
        
class ColorGraph:
    def __init__(self):
        pass
        
    def from_memory_stream(self, stream):
        self.x = [stream.float32_read() for _ in range(10)]
        self.y = [[stream.float32_read() for _ in range(3)] for _ in range(10)]
        
    def write_to_memory_stream(self, stream):
        stream.write(struct.pack("<ffffffffff", *self.x))
        for color in self.y:
            stream.write(struct.pack("<fff", *color))
            
class BurstEmitterGraph:
    
    def __init__(self):
        self.times = []
        self.num_particles = []
        
    def from_memory_stream(self, stream):
        for _ in range(10):
            self.times.append(stream.float32_read())
            self.num_particles.append((stream.uint32_read(), stream.uint32_read()))
        
    def write_to_memory_stream(self, stream):
        for i in range(10):
            stream.write(struct.pack("<fII", self.times[i], self.num_particles[i][0], self.num_particles[i][1]))

class Emitter:
    
    BURST = 0x0C
    RATE = 0x0B
    
    def __init__(self):
        pass
        
    def from_memory_stream(self, stream):
        self.emitter_type = stream.uint32_read()
        if self.emitter_type == Emitter.BURST:
            burst_graph = BurstEmitterGraph()
            burst_graph.from_memory_stream(stream)
            self.burst_graph = burst_graph
        elif self.emitter_type == Emitter.RATE:
            self.initial_rate_min = stream.float32_read()
            self.initial_rate_max = stream.float32_read()
            rate_graph = Graph()
            rate_graph.from_memory_stream(stream)
            self.rate_graph = rate_graph
            
    def write_to_memory_stream(self, stream):
        stream.advance(4)
        if self.emitter_type == Emitter.BURST:
            self.burst_graph.write_to_memory_stream(stream)
        elif self.emitter_type == Emitter.RATE:
            stream.write(struct.pack("<ff", self.initial_rate_min, self.initial_rate_max))
            self.rate_graph.write_to_memory_stream(stream)
        

class ParticleSystem:
    def __init__(self):
        self.scale_graphs = []
        self.opacity_graphs = []
        self.color_graphs = []
        self.color_graph_offsets = []
        self.other_graph_offsets = []
        self.other_graphs = []
        self.emitter_offsets = []
        self.emitters = []
        self.visualizer = None
        self.offset = 0
        self.max_num_particles = 0
        
    def is_rendering(self):
        return self.non_rendering == 0
        
    def from_memory_stream(self, stream):
        self.scale_graphs.clear()
        self.opacity_graphs.clear()
        self.color_graphs.clear()
        self.color_graph_offsets.clear()
        self.other_graphs.clear()
        self.other_graph_offsets.clear()
        self.emitters.clear()
        self.offset = stream.tell()
        self.max_num_particles = stream.uint32_read()
        self.num_components = stream.uint32_read()
        self.unk1 = stream.read(68)
        #self.advance(4)
        #self.advance(64)
        self.non_rendering = stream.uint32_read()
        self.unk2 = stream.read(40)
        # rotation
        self.rotation = EmitterRotation.fromBytes(stream.read(48))
        # position
        self.position = EmitterPosition.fromBytes(stream.read(12))
        self.unk3 = stream.read(52)
        self.component_list_offset = stream.uint32_read()
        self.unk4 = stream.read(4)
        self.emitter_offset = stream.uint32_read()
        self.unk5 = stream.read(8)
        self.visualizer_offset = stream.uint32_read()
        self.size = stream.uint32_read()
        if not self.is_rendering():
            stream.seek(self.offset + self.size)
            return
        if self.visualizer_offset == self.size:
            stream.seek(self.offset + self.size)
            return
            
        # get emitters
        stream.seek(self.offset + self.emitter_offset)
        stop = False
        while not stop:
            emitter_type = stream.uint32_read()
            while emitter_type not in [Emitter.BURST, Emitter.RATE]:
                emitter_type = stream.uint32_read()
                if stream.tell() >= self.offset + self.visualizer_offset:
                    stop = True
                    break
            if not stop:
                stream.advance(-4)
                offset = stream.tell()
                emitter = Emitter()
                emitter.from_memory_stream(stream)
                if stream.tell() >= self.offset + self.visualizer_offset:
                    break
                self.emitters.append(emitter)
                self.emitter_offsets.append(offset)
            
        # get visualizer
        stream.seek(self.offset + self.visualizer_offset)
        visualizer = Visualizer()
        visualizer.from_memory_stream(stream)
        self.visualizer = visualizer
        
        # get graphs
        while stream.tell() < self.offset + self.size:
            while stream.uint32_read() == 0x00:
                if stream.tell() == self.offset + self.size:
                    break
            stream.advance(-4)
            if stream.tell() + 16 > self.offset + self.size:
                break
            component_type = [stream.uint32_read() for _ in range(4)]
            if component_type[0] == 0x04 and component_type[1] >= 0x20: # graph
                stream.advance(4)
                self.other_graph_offsets.append(stream.tell())
                unk_graph = Graph()
                unk_graph.from_memory_stream(stream)
                unk_graph.from_memory_stream(stream)
                self.other_graphs.append(unk_graph)
            elif component_type[0] == 0x05 and component_type[1] >= 0x20: # color graph
                # color graph
                stream.advance(-4)
                self.color_graph_offsets.append(stream.tell())
                scale = Graph()
                scale.from_memory_stream(stream)
                scale.from_memory_stream(stream)
                self.scale_graphs.append(scale)
                opacity = Graph()
                opacity.from_memory_stream(stream)
                opacity.from_memory_stream(stream)
                self.opacity_graphs.append(opacity)
                color = ColorGraph()
                color.from_memory_stream(stream)
                self.color_graphs.append(color)
            elif component_type[1] == 0x05 and component_type[2] >= 0x20: # color graph
                self.color_graph_offsets.append(stream.tell())
                scale = Graph()
                scale.from_memory_stream(stream)
                scale.from_memory_stream(stream)
                self.scale_graphs.append(scale)
                opacity = Graph()
                opacity.from_memory_stream(stream)
                opacity.from_memory_stream(stream)
                self.opacity_graphs.append(opacity)
                color = ColorGraph()
                color.from_memory_stream(stream)
                self.color_graphs.append(color)  
            elif component_type[0] == 0x0F and component_type[1] >= 0x20: # color graph, no scale
                stream.advance(-4)
                self.color_graph_offsets.append(stream.tell())
                scale = None
                #scale.from_memory_stream(stream)
                #scale.from_memory_stream(stream)
                self.scale_graphs.append(scale)
                opacity = Graph()
                opacity.from_memory_stream(stream)
                opacity.from_memory_stream(stream)
                self.opacity_graphs.append(opacity)
                color = ColorGraph()
                color.from_memory_stream(stream)
                self.color_graphs.append(color)
            elif component_type[0] == 0x0B: # some float data
                stream.advance(12)
            else:
                continue
            
        stream.seek(self.offset + self.size)
        
    def write_to_memory_stream(self, stream):
        stream.write(struct.pack("<II", self.max_num_particles, self.num_components))
        stream.write(self.unk1)
        stream.write(struct.pack("<I", self.non_rendering))
        stream.write(self.unk2)
        stream.write(self.rotation.to_bytes())
        stream.write(self.position.to_bytes())
        stream.write(self.unk3)
        stream.write(struct.pack("<I", self.component_list_offset))
        stream.write(self.unk4)
        stream.write(struct.pack("<I", self.emitter_offset))
        stream.write(self.unk5)
        stream.write(struct.pack("<II", self.visualizer_offset, self.size))
        if self.non_rendering != 0:
            stream.seek(self.offset + self.size)
            return
        if self.visualizer_offset == self.size:
            stream.seek(self.offset + self.size)
            return
            
        for index, offset in enumerate(self.emitter_offsets):
            stream.seek(offset)
            self.emitters[index].write_to_memory_stream(stream)
            
        stream.seek(self.offset + self.visualizer_offset)
        self.visualizer.write_to_memory_stream(stream)
        for index, offset in enumerate(self.color_graph_offsets):
            stream.seek(offset)
            if self.scale_graphs[index] is not None:
                self.scale_graphs[index].write_to_memory_stream(stream)
                self.scale_graphs[index].write_to_memory_stream(stream)
            self.opacity_graphs[index].write_to_memory_stream(stream)
            self.opacity_graphs[index].write_to_memory_stream(stream)
            self.color_graphs[index].write_to_memory_stream(stream)
        for index, offset in enumerate(self.other_graph_offsets):
            stream.seek(offset)
            self.other_graphs[index].write_to_memory_stream(stream)
            self.other_graphs[index].write_to_memory_stream(stream)
        
        
class ParticleEffectVariable:
    def __init__(self):
        self.name_hash = 0
        self.x = 0
        self.y = 0
        self.z = 0

class ParticleEffect:
    def __init__(self):
        self.variables = []
        self.particle_systems = []
        self.min_lifetime = 0
        self.max_lifetime = 0
        self.num_variables = 0
        self.num_particle_systems = 0
        
    def from_memory_stream(self, stream):
        self.variables.clear()
        self.particle_systems.clear()
        magic = stream.uint32_read()
        if magic != 0x6E:
            return
        self.min_lifetime = stream.float32_read()
        self.max_lifetime = stream.float32_read()
        stream.advance(8)
        self.num_variables = stream.uint32_read()
        self.num_particle_systems = stream.uint32_read()
        stream.advance(44)
        for _ in range(self.num_variables):
            new_var = ParticleEffectVariable()
            new_var.name_hash = stream.uint32_read()
            self.variables.append(new_var)
        for variable in self.variables:
            variable.x = stream.float32_read()
            variable.y = stream.float32_read()
            variable.z = stream.float32_read()
        for _ in range(self.num_particle_systems):
            new_system = ParticleSystem()
            new_system.from_memory_stream(stream)
            self.particle_systems.append(new_system)
            
    def write_to_memory_stream(self, stream):
        stream.seek(4)
        stream.write(struct.pack("<ff", self.min_lifetime, self.max_lifetime))
        stream.advance(8)
        stream.write(self.num_variables.to_bytes(4, byteorder="little"))
        stream.write(self.num_particle_systems.to_bytes(4, byteorder="little"))
        stream.advance(44)
        for variable in self.variables:
            stream.write(struct.pack("<I", variable.name_hash))
        for variable in self.variables:
            stream.write(struct.pack("<fff", variable.x, variable.y, variable.z))
        for particle_system in self.particle_systems:
            stream.seek(particle_system.offset)
            particle_system.write_to_memory_stream(stream)

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
        
    def float32_read(self):
        return self.read_format('f', 4)


class EmitterView(QWidget):
    
    def __init__(self, emitters: list[Emitter], parent=None):
        super().__init__(parent)
        
        self.emitters = emitters
        
        self.layout = QVBoxLayout()
        
        for emitter in sorted(self.emitters, key=lambda e: e.emitter_type):
            if emitter.emitter_type == Emitter.RATE:
                chart = QChart()
                chart.setTitle("Rate over time")
                series = QLineSeries()
                series.setName("Rate")
                pen = QPen(0xFF0000)
                pen.setWidth(5)
                series.setPen(pen)
                for x, y in zip(emitter.rate_graph.x, emitter.rate_graph.y):
                    if not x == 10000:
                        series.append(x, y)
                chart.addSeries(series)
                chart.legend().hide()
                chart.createDefaultAxes()
                chart.axes(Qt.Orientation.Horizontal)[0].setRange(0, 1)
                chart.axes(Qt.Orientation.Horizontal)[0].setTickCount(2)
                chart.axes(Qt.Orientation.Vertical)[0].setRange(0, 1)
                chart.axes(Qt.Orientation.Vertical)[0].setTickCount(2)
                chartView = QChartView(chart)
                chartView.setFixedWidth(200)
                chartView.setFixedHeight(200)
                self.emitterLayout = QHBoxLayout()
                self.emitterLayout2 = QVBoxLayout()
                emitterLabel = QLabel(f"Rate Emitter", self)
                self.emitterLayout.addWidget(emitterLabel)
                emitterLabelMin = QLabel("Min: ", self)
                emitterLabelMax = QLabel("Max: ", self)
                emitterEditMin = QLineEdit(self)
                emitterEditMin.setFixedWidth(130)
                emitterEditMin.setText(str(emitter.initial_rate_min))
                emitterEditMin.setValidator(QDoubleValidator())
                emitterEditMax = QLineEdit(self)
                emitterEditMax.setFixedWidth(130)
                emitterEditMax.setText(str(emitter.initial_rate_max))
                emitterEditMax.setValidator(QDoubleValidator())
                self.emitterLayout.addWidget(emitterLabelMin)
                self.emitterLayout.addWidget(emitterEditMin)
                self.emitterLayout.addWidget(emitterLabelMax)
                self.emitterLayout.addWidget(emitterEditMax)
                self.emitterLayout.addStretch(1)
                self.emitterLayout2.addLayout(self.emitterLayout)
                self.emitterLayout2.addWidget(chartView)
                self.layout.addLayout(self.emitterLayout2)
            elif emitter.emitter_type == Emitter.BURST:
                self.emitterLayout = QVBoxLayout()
                emitterLabel = QLabel(f"Burst Emitter", self)
                self.emitterLayout.addWidget(emitterLabel)
                self.titleLayout = QHBoxLayout()
                self.titleLayout.addWidget(QLabel("Time"))
                self.titleLayout.addWidget(QLabel("Min Burst"))
                self.titleLayout.addWidget(QLabel("Max Burst"))
                self.emitterLayout.addLayout(self.titleLayout)
                for time, value in zip(emitter.burst_graph.times, emitter.burst_graph.num_particles):
                    min = value[0]
                    max = value[1]
                    self.rowLayout = QHBoxLayout()
                    timeEdit = QLineEdit()
                    timeEdit.setText(str(time))
                    timeEdit.setValidator(QDoubleValidator())
                    self.rowLayout.addWidget(timeEdit)
                    minEdit = QLineEdit()
                    minEdit.setText(str(min))
                    minEdit.setValidator(QIntValidator())
                    self.rowLayout.addWidget(minEdit)
                    maxEdit = QLineEdit()
                    maxEdit.setText(str(max))
                    maxEdit.setValidator(QIntValidator())
                    self.rowLayout.addWidget(maxEdit)
                    self.emitterLayout.addLayout(self.rowLayout)
                self.layout.addLayout(self.emitterLayout)
        self.layout.addStretch(1)
        self.setLayout(self.layout)
        
        # def setData
        
class ParticleSystemView(QWidget):
    
    '''
    Container for showing a particle system. Includes visualizer, color graph, opacity graph, scale graph, rotation, and position
    '''
    
    def __init__(self, particleSystem, trailSpawner = -1, parent=None):
        super().__init__(parent)
        self.particleSystem = particleSystem
        
        self.layout = QVBoxLayout()
        
        self.emitterView = EmitterView(self.particleSystem.emitters)
        
        if trailSpawner == -1:
            self.visualizerView = VisualizerView(self.particleSystem.visualizer)
            self.layout.addWidget(self.visualizerView)
            
        else:
            self.trailSpawnerLabel = QLabel(f"Trail Spawner for Particle System {trailSpawner}", parent=self)
            self.layout.addWidget(self.trailSpawnerLabel)
            
        self.layout.addWidget(self.emitterView)
        
        self.layout.addStretch(1)
        self.setLayout(self.layout)
        
class ParticleEffectView(QWidget):
    '''
    Container for showing a particle effect. Includes tab widget for each particle system plus info about the overall effect (lifetime)
    '''
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout()
        
        # particle effect data
        lifetimeWidth = 100
        self.lifetimeWidget = QWidget(self)
        self.lifetimeLayout = QHBoxLayout()
        self.lifetimeLabel1 = QLabel("Lifetime: ", self)
        self.lifetimeLabel2 = QLabel(" - ", self)
        self.lifetimeLabel3 = QLabel(" seconds", self)
        self.lifetimeValidator = QDoubleValidator()
        self.lifetimeMinEdit = QLineEdit(self)
        self.lifetimeMinEdit.setValidator(self.lifetimeValidator)
        self.lifetimeMinEdit.editingFinished.connect(self.setLifetime)
        self.lifetimeMinEdit.setFixedWidth(lifetimeWidth)
        self.lifetimeMaxEdit = QLineEdit(self)
        self.lifetimeMaxEdit.setValidator(self.lifetimeValidator)
        self.lifetimeMaxEdit.editingFinished.connect(self.setLifetime)
        self.lifetimeMaxEdit.setFixedWidth(lifetimeWidth)
        self.lifetimeLayout.addWidget(self.lifetimeLabel1)
        self.lifetimeLayout.addWidget(self.lifetimeMinEdit)
        self.lifetimeLayout.addWidget(self.lifetimeLabel2)
        self.lifetimeLayout.addWidget(self.lifetimeMaxEdit)
        self.lifetimeLayout.addWidget(self.lifetimeLabel3)
        self.lifetimeLayout.addStretch(1)
        self.lifetimeWidget.setLayout(self.lifetimeLayout)
        
        self.layout.addWidget(self.lifetimeWidget)
        
        # tabs for the particle systems
        self.tabWidget = QTabWidget(self)
                
        self.layout.addWidget(self.tabWidget)
                
        self.setLayout(self.layout)
        
    def loadData(self, particleEffect):
        self.particleEffect = particleEffect
        
        self.lifetimeMinEdit.setText(str(self.particleEffect.min_lifetime))
        self.lifetimeMaxEdit.setText(str(self.particleEffect.max_lifetime))
        
        self.tabWidget.clear()
        count = 0
        for particleSystem in self.particleEffect.particle_systems:
            if particleSystem.is_rendering():
                if particleSystem.visualizer_offset != particleSystem.size:
                    particleSystemView = ParticleSystemView(particleSystem)
                    self.tabWidget.addTab(particleSystemView, f"Particle System {count}")
                else:
                    particleSystemView = ParticleSystemView(particleSystem, trailSpawner=count+1)
                    self.tabWidget.addTab(particleSystemView, f"Particle System {count}")
                count += 1
        
    def setLifetime(self):
        self.particleEffect.min_lifetime = float(self.lifetimeMinEdit.text())
        self.particleEffect.max_lifetime = float(self.lifetimeMaxEdit.text())

class BigIntValidator(QDoubleValidator):
    def __init__(self, bottom=float('-inf'), top=float('inf')):
        super(BigIntValidator, self).__init__(bottom, top, 0)
        self.setNotation(QDoubleValidator.StandardNotation)

    def validate(self, text, pos):
        if text.endswith('.'):
            return QValidator.Invalid, text, pos
        return super(BigIntValidator, self).validate(text, pos)
        
class VisualizerView(QWidget):
    
    def __init__(self, visualizer, parent=None):
        super().__init__(parent)
        lineWidth = 160
        self.int32Max = (2**32)-1
        self.int64Max = (2**64)-1
        self.layout = QVBoxLayout()
        self.visualizer = visualizer
        self.materialIdLabel = self.unitIdLabel=self.meshIdLabel = None
        self.materialIdEdit = self.unitIdEdit = self.meshIdEdit = None
        self.visualizerLabel = QLabel("", parent=self)
        
        self.int32Validator = BigIntValidator(0, self.int32Max)
        self.int64Validator = BigIntValidator(0, self.int64Max)
        if self.visualizer.visualizer_type == Visualizer.BILLBOARD:
            # material ID
            self.materialIdLabel = QLabel(f"Material: ", parent=self)
            self.materialIdEdit = QLineEdit(f"{self.visualizer.material_id}", parent=self)
            self.materialIdEdit.setFixedWidth(lineWidth)
            self.materialIdEdit.editingFinished.connect(self.materialIdChanged)
            self.materialIdEdit.setValidator(self.int64Validator)
            self.visualizerLabel.setText("Visualizer Type: Billboard")
        elif self.visualizer.visualizer_type == Visualizer.LIGHT:
            # no IDs
            self.visualizerLabel.setText("Visualizer Type: Light")
        elif self.visualizer.visualizer_type == Visualizer.MESH:
            # material, unit, and mesh ID
            self.materialIdEdit = QLineEdit(f"{self.visualizer.material_id}", parent=self)
            self.materialIdEdit.setValidator(self.int64Validator)
            self.materialIdEdit.editingFinished.connect(self.materialIdChanged)
            self.materialIdEdit.setFixedWidth(lineWidth)
            self.materialIdLabel = QLabel(f"Material: ", parent=self)
            
            self.unitIdEdit = QLineEdit(f"{self.visualizer.unit_id}", parent=self)
            self.unitIdEdit.setValidator(self.int64Validator)
            self.unitIdEdit.editingFinished.connect(self.unitIdChanged)
            self.unitIdEdit.setFixedWidth(lineWidth)
            self.unitIdLabel = QLabel(f"Unit: ", parent=self)
            
            self.meshIdEdit = QLineEdit(f"{self.visualizer.mesh_id}", parent=self)
            self.meshIdEdit.editingFinished.connect(self.meshIdChanged)
            self.meshIdEdit.setValidator(self.int64Validator)
            self.meshIdEdit.setFixedWidth(lineWidth)
            self.meshIdLabel = QLabel(f"Mesh: ", parent=self)
            
            self.visualizerLabel.setText("Visualizer Type: Mesh")
            
        self.layout.addWidget(self.visualizerLabel, alignment=Qt.AlignTop | Qt.AlignLeft)
        for label, edit in zip([self.materialIdLabel, self.unitIdLabel, self.meshIdLabel], [self.materialIdEdit, self.unitIdEdit, self.meshIdEdit]):
            if label is not None and edit is not None:
                layout = QHBoxLayout()
                layout.addWidget(label)
                layout.addWidget(edit)
                layout.addStretch(1)
                self.layout.addLayout(layout)
        self.layout.addStretch(1)
            
        self.setLayout(self.layout)
            
    def meshIdChanged(self):
        newId = int(self.meshIdEdit.text())
        self.visualizer.mesh_id = newId & self.int32Max
        
    def materialIdChanged(self):
        newId = int(self.materialIdEdit.text())
        self.visualizer.material_id = newId & self.int64Max
        
    def unitIdChanged(self):
        newId = int(self.unitIdEdit.text())
        self.visualizer.unit_id = newId & self.int64Max
        
        
class GraphView(QWidget):
    def __init__(self, graph):
        pass
        
class LifetimeView(QWidget):
    def __init__(self, particleEffect):
        pass
        

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
        
class LoadedFilesWindow(QWidget):
    
    loadFile = Signal(str, MemoryStream, ParticleEffect)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout()
        
        self.treeWidget = QTreeWidget(self)
        self.treeWidget.setHeaderLabels(["Loaded Files"])
        
        self.layout.addWidget(self.treeWidget)
        
        self.setLayout(self.layout)
        
    def addFile(self, filepath, fileData, effect, note=""):
        fileWidget = LoadedFileWidget(filepath, fileData, effect, note=note)
        fileWidget.openClicked.connect(self.load)
        fileWidget.removeClicked.connect(self.remove)
        item = QTreeWidgetItem(self.treeWidget)
        fileWidget.item = item
        self.treeWidget.setItemWidget(item, 0, fileWidget)
        
    def getAllLoadedFiles(self):
        fileWidgets = []
        root = self.treeWidget.invisibleRootItem()
        for i in range(root.childCount()):
            fileWidgets.append(self.treeWidget.itemWidget(root.child(i), 0))
        return fileWidgets
        
    def remove(self, item):
        (item.parent() or self.treeWidget.invisibleRootItem()).removeChild(item)
        
    def load(self, filepath: str, fileData: MemoryStream, particleEffect: ParticleEffect):
        self.loadFile.emit(filepath, fileData, particleEffect)
        
    def clear(self):
        self.treeWidget.clear()
        
        
class LoadedFileWidget(QWidget):
    
    openClicked = Signal(str, MemoryStream, ParticleEffect)
    removeClicked = Signal(QTreeWidgetItem)
    
    def __init__(self, filepath, fileData, effect, note="", parent=None):
        super().__init__(parent)
        self.filepath = filepath
        self.fileData = fileData
        self.particleEffect = effect
        self.note = note
        
        self.layout = QHBoxLayout()
        
        self.selectButton = QToolButton()
        self.selectButton.setText("open")
        self.selectButton.clicked.connect(self.load)
        self.nameLabel = QLabel(os.path.basename(self.filepath), parent=self)
        self.noteEdit = QLineEdit(parent=self)
        self.noteEdit.setText(self.note)
        self.noteEdit.editingFinished.connect(self.setNote)
        self.noteEdit.setPlaceholderText("Set note...")
        self.removeButton = QToolButton()
        self.removeButton.setText("\u2715")
        self.removeButton.clicked.connect(self.remove)
        
        self.layout.addWidget(self.selectButton)
        self.layout.addWidget(self.nameLabel)
        self.layout.addWidget(self.noteEdit)
        #self.layout.addStretch(1)
        self.layout.addWidget(self.removeButton)
        self.setLayout(self.layout)
        
    def setNote(self):
        self.note = self.noteEdit.text()
        
    def remove(self):
        self.removeClicked.emit(self.item)
        
    def load(self):
        self.openClicked.emit(self.filepath, self.fileData, self.particleEffect)


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"HD2 Particle Modder - Version {VERSION}")
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
        self.initFilesWindow()
        self.initParticleView()
        #self.initColorView()
        #self.initOpacityView()
        #self.initLifetimeView()
        #self.initSizeView()
        #self.initPositionView()
        #self.initRotationView()

    def connectComponents(self):
        self.fileOpenArchiveAction.triggered.connect(self.load_archive)
        self.fileSaveArchiveAction.triggered.connect(self.saveArchive)
        self.fileSaveProjectAction.triggered.connect(self.saveProject)
        self.fileLoadProjectAction.triggered.connect(self.loadProject)
        
        self.loadedFilesWindow.loadFile.connect(self.loadFromStream)

    def layoutComponents(self):
        self.setMinimumSize(300, 200)
        self.layout = QVBoxLayout()
        
        self.splitter = QSplitter(Qt.Horizontal)
        #self.splitter.addWidget(self.colorView)

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
        self.splitter.addWidget(self.loadedFilesWindow)
        self.splitter.addWidget(self.particleEffectView)
        self.layout.addWidget(self.splitter)
        self.layout.addStretch(1)
        #self.layout.addWidget(self.tabWidget)

        # Color tab layout
        #layout = QVBoxLayout()
        #buttonLayout = QHBoxLayout()
        #buttonLayout.addWidget(self.hideTimeColumnsBtn)
        #self.hideTimeColumnsBtn.setToolTip("Toggle visibility of time columns")
        #buttonLayout.addWidget(self.pickColorBtn)
        #layout.addLayout(buttonLayout)
        #layout.addWidget(self.colorView)
        #self.colorTab.setLayout(layout)

        # Opacity tab layout
        #layout = QVBoxLayout()
        #opacityButtonLayout = QHBoxLayout()
        #opacityButtonLayout.addWidget(self.hideOpacityTimeColumnsBtn)
        #self.hideOpacityTimeColumnsBtn.setToolTip("Toggle visibility of time columns")
        #layout.addLayout(opacityButtonLayout)
        #layout.addWidget(self.opacityView)
        #self.opacityTab.setLayout(layout)

        # Lifetime tab layout
        #layout = QVBoxLayout()
        #layout.addWidget(self.lifetimeView)
        #self.lifetimeTab.setLayout(layout)

        # Size Scale tab layout
        #layout = QVBoxLayout()
        #sizeButtonLayout = QHBoxLayout()
        #sizeButtonLayout.addWidget(self.hideSizeTimeColumnsBtn)
        #self.hideSizeTimeColumnsBtn.setToolTip("Toggle visibility of time columns")
        #layout.addLayout(sizeButtonLayout)
        #layout.addWidget(self.sizeView)
        #self.sizeTab.setLayout(layout)

        #layout = QVBoxLayout()
        #layout.addWidget(self.positionView)
        #self.positionTab.setLayout(layout)

        #layout = QVBoxLayout()
        #layout.addWidget(self.rotationView)
        #self.rotationTab.setLayout(layout)

        #self.tabWidget.addTab(self.colorTab, "Color")
        #self.tabWidget.addTab(self.opacityTab, "Opacity")
        #self.tabWidget.addTab(self.lifetimeTab, "Lifetime")
        #self.tabWidget.addTab(self.sizeTab, "Size Scale")
        #self.tabWidget.addTab(self.positionTab, "Emitter Offset")
        #self.tabWidget.addTab(self.rotationTab, "Emitter Rotation")

        widget = QWidget()
        widget.setLayout(self.layout)
        self.setCentralWidget(widget)
        
    def initParticleView(self):
        self.particleEffectView = ParticleEffectView(self)
        
    def initFilesWindow(self):
        self.loadedFilesWindow = LoadedFilesWindow(self)

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
        #self.colorTab = QWidget(self.tabWidget)
        #self.opacityTab = QWidget(self.tabWidget)
        #self.lifetimeTab = QWidget(self.tabWidget)
        #self.sizeTab = QWidget(self.tabWidget)
        #self.positionTab = QWidget(self.tabWidget)
        #self.rotationTab = QWidget(self.tabWidget)

    def initMenuBar(self):
        menu_bar = self.menuBar()

        self.file_menu = menu_bar.addMenu("File")

        self.fileOpenArchiveAction = QAction("Open", self)
        self.fileSaveArchiveAction = QAction("Save", self)
        self.fileSaveAllFilesAction= QAction("Save All", self)
        self.fileLoadProjectAction = QAction("Open Project File", self)
        self.fileSaveProjectAction = QAction("Save Project File", self)

        self.file_menu.addAction(self.fileOpenArchiveAction)
        self.file_menu.addAction(self.fileSaveArchiveAction)
        self.file_menu.addAction(self.fileSaveAllFilesAction)
        self.file_menu.addAction(self.fileLoadProjectAction)
        self.file_menu.addAction(self.fileSaveProjectAction)

        self.edit_menu = menu_bar.addMenu("Edit")
        self.undo_action = self.undoStack.createUndoAction(self, "Undo")
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.redo_action = self.undoStack.createRedoAction(self, "Redo")
        self.redo_action.setShortcut(QKeySequence.Redo)
        self.edit_menu.addAction(self.undo_action)
        self.edit_menu.addAction(self.redo_action)
        
    def loadFromStream(self, filepath: str, stream: MemoryStream, particleEffect: ParticleEffect):
        self.particleEffectData = stream
        self.particleEffect = particleEffect
        self.reloadData()
        self.setLoadedFileLabels(filepath)
        
    def setLoadedFileLabels(self, filepath):
        self.statusBar().showMessage(f"Loaded: {os.path.basename(filepath)}", 5000)
        stat = os.stat(filepath)
        modified_time = time.strftime('%Y-%m-%d %H:%M', time.localtime(stat.st_mtime))
        self.name = os.path.basename(filepath)
        self.filenameLabel.setText(f"{os.path.basename(filepath)} — last modified: {modified_time}")
        
    def reloadData(self):
        self.particleEffectView.loadData(self.particleEffect)
                
    def saveProject(self, initialdir: str | None = '', outputFile: str | None = ""):
        if not outputFile:
            outputFile = QFileDialog.getSaveFileName(self, "Save File", str(initialdir), "Particle Mod (*.pmod)")
            outputFile = outputFile[0]
        if not outputFile:
            return
        loadedFiles = self.loadedFilesWindow.getAllLoadedFiles()
        root = ET.Element("root")
        project = ET.SubElement(root, "project", name="default project")
        projectFiles = ET.SubElement(project, "project_files")
        for fileWidget in loadedFiles:
            file = ET.SubElement(projectFiles, "file")
            ET.SubElement(file, "filepath").text = fileWidget.filepath
            ET.SubElement(file, "note").text = fileWidget.note
        tree = ET.ElementTree(root)
        tree.write(outputFile)
        
    def saveProjectFiles(self):
        projectFiles = self.loadedFilesWindow.getAllLoadedFiles()
        for fileWidget in loadedFiles:
            path = fileWidget.filepath
            stream = fileWidget.fileData
            particleEffect = fileWidget.particleEffect
            stream.seek(0)
            particleEffect.write_to_memory_stream(stream)
            with open(path, 'wb') as f:
                f.write(stream.data)
        self.statusBar().showMessage(f"Saved all particle files", 3000)
        
    def loadProject(self, initialdir: str | None = '', projectFile: str | None = ""):
        if not projectFile:
            projectFile = QFileDialog.getOpenFileName(self, "Select Project File", str(initialdir), "Particle Mod (*.pmod)")
            projectFile = projectFile[0]
        if not projectFile:
            return
        self.clearLoadedFiles()
        tree = ET.parse(projectFile)
        root = tree.getroot()
        for project in root:
            projectFiles = project.find('project_files')
            for file in projectFiles:
                filepath = file.find('filepath').text
                if not os.path.exists(filepath):
                    continue
                note = file.find('note').text
                with open(filepath, 'rb') as f:
                    fileData = MemoryStream(f.read())
                particleEffect = ParticleEffect()
                particleEffect.from_memory_stream(fileData)
                self.addLoadedFile(filepath, fileData, particleEffect, note)
            break # support for multiple projects may be added later
            
    def clearLoadedFiles(self):
        self.loadedFilesWindow.clear()
        
    def addLoadedFile(self, filepath: str, fileData: MemoryStream, particleEffect: ParticleEffect, note: str=""):
        self.loadedFilesWindow.addFile(filepath, fileData, particleEffect, note)

    def load_archive(self, initialdir: str | None = '', archive_file: str | None = ""):
        if not archive_file:
            archive_file = QFileDialog.getOpenFileName(self, "Select archive", str(initialdir), "All Files (*.*)")
            archive_file = archive_file[0]
        if not archive_file:
            return
        if os.path.splitext(archive_file)[1] == ".pmod":
            self.loadProject(projectFile = archive_file)
            return
        self.name = archive_file
        with open(archive_file, "rb") as f:
            self.particleEffectData = MemoryStream(f.read())
        self.particleEffect = ParticleEffect()
        self.particleEffect.from_memory_stream(self.particleEffectData)
        self.reloadData()
        self.addLoadedFile(archive_file, self.particleEffectData, self.particleEffect)
        self.setLoadedFileLabels(archive_file)
        '''    
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
        '''
        
        
    def saveArchive(self, initialdir: str | None = '', archive_file: str | None = ""):
        if not archive_file:
            archive_file = QFileDialog.getSaveFileName(self, "Select archive", self.name)
            archive_file = archive_file[0]
        if not archive_file:
            return
        with open(archive_file, "wb") as f:
            self.particleEffect.write_to_memory_stream(self.particleEffectData)
            f.write(self.particleEffectData.data)
            #data = MemoryStream()
            #data.write(self.data)
            #self.colorViewModel.writeFileData(data)
            #self.lifetimeViewModel.writeFileData(data)
            #self.opacityViewModel.writeFileData(data)
            #self.sizeViewModel.writeFileData(data)
            #self.positionViewModel.writeFileData(data)
            #self.rotationViewModel.writeFileData(data)
            #f.write(data.data)

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