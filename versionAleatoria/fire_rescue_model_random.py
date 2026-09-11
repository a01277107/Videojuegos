"""Modelo importable de la simulación de Flash Point: Fire Rescue con bomberos de comportamiento ALEATORIO.

Esta versión conserva TODAS las reglas del juego original (paredes, puertas, fuego/humo,
explosiones, ondas de choque, POIs, rescate de víctimas, KO de bomberos y condiciones de
victoria/derrota). La única diferencia es que los bomberos ya NO planean rutas óptimas
con A* ni participan en un sistema de subasta de objetivos: en cada turno, cada bombero
elige de forma aleatoria una acción válida entre las que puede pagar con sus puntos de
acción (AP), hasta quedarse sin AP o sin acciones posibles.
"""

from dataclasses import dataclass

from mesa import Agent, Model
from mesa.space import MultiGrid

import numpy as np

#costos de acciones (fijos)
MOVE_SPACE = 1
MOVE_SPACE_W_FIRE = 2
USE_DOOR = 1
DAMAGE_WALL = 2 #revisar daño vs romper
CARRY_VICTIM = 2
REMOVE_SMOKE = 1
FIRE_TO_SMOKE = 1
REMOVE_FIRE = 2

#Clase para representar los estados de las paredes de una celda
@dataclass
class CellWalls:
    #Estado de las 4 paredes de una celda: 2 = intacta, 1 = dañada, 0 = destruida/inexistente
    up: int = 0
    down: int = 0
    left: int = 0
    right: int = 0

#Clase para representar el estado de las posibles puertas de una celda (ocupan el mismo borde que una pared)
@dataclass
class CellDoors:
    #Estado de las 4 puertas de una celda: 2 = cerrada, 1 = abierta, 0 = destruida/inexistente
    up: int = 0
    down: int = 0
    left: int = 0
    right: int = 0

#Clase especializda para crear y modificar estado de paredes y puertas (entorno)
class EnvironmentManager(Model):
    MAX_DAMAGE_MARKERS = 24 #mantener control del max de daños que puede llegar a haber
    #Guardar dirección opuesta para sincronizar daños con la celda que comparte la pared/puerta
    OPPOSITE_DIRECTIONS = {"up": "down", "down": "up", "left": "right", "right": "left"}
    #Desplazamiento necesario (drow, dcolumn) hacia la celda vecina según la ubicación de la pared en la celda
    NEIGHBOR_OFFSETS = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}

    def __init__(self, columns, rows, wall_layout=None, door_layout=None):
        super().__init__()

        self.columns = columns
        self.rows = rows
        self._total_damage_markers = 0 #contador de marcadores de daño
        self.walls = [ #usar clase de paredes creada para cada casilla del grid
            [CellWalls() for _ in range(columns)]
            for _ in range(rows)
        ]
        self.doors = [ #usar clase de puertas creada para cada casilla del grid
            [CellDoors() for _ in range(columns)]
            for _ in range(rows)
        ]

        if wall_layout: #añadir paredes iniciales
            self.load_wall_layout(wall_layout)

        if door_layout: #añadir puertas iniciales (siempre inician cerradas)
            self.load_door_layout(door_layout)

    def load_wall_layout(self, wall_layout):
        #Desempaquetar paredes iniciales. Cada entrada es un diccionario {row, column, direction, state}
        for wall in wall_layout:
            self._set_wall(
                wall["row"],
                wall["column"],
                wall["direction"],
                wall["state"]
            )

    #Establecer pared del layout
    def _set_wall(self, row, column, direction, value):
        setattr(self.walls[row][column], direction, value)

        #obtener celda con la que comparte pared
        drow, dcolumn = self.NEIGHBOR_OFFSETS[direction]
        nrow, ncolumn = row + drow, column + dcolumn
        if 0 <= nrow < self.rows and 0 <= ncolumn < self.columns:
            opposite = self.OPPOSITE_DIRECTIONS[direction]
            setattr(self.walls[nrow][ncolumn], opposite, value) #sincronizar pared con esa celda

    def load_door_layout(self, door_layout):
        #Desempaquetar puertas iniciales. Cada entrada es un diccionario {row, column, direction, state}
        for door in door_layout:
            self._set_door(
                door["row"],
                door["column"],
                door["direction"],
                door["state"]
            )

    #Establecer puerta del layout (reemplaza cualquier pared que existiera en ese mismo borde)
    def _set_door(self, row, column, direction, value):
        setattr(self.walls[row][column], direction, 0) #el borde deja de ser una pared
        setattr(self.doors[row][column], direction, value)

        #obtener celda con la que comparte la puerta
        drow, dcolumn = self.NEIGHBOR_OFFSETS[direction]
        nrow, ncolumn = row + drow, column + dcolumn
        if 0 <= nrow < self.rows and 0 <= ncolumn < self.columns:
            opposite = self.OPPOSITE_DIRECTIONS[direction]
            setattr(self.walls[nrow][ncolumn], opposite, 0)
            setattr(self.doors[nrow][ncolumn], opposite, value) #sincronizar puerta con esa celda

    @property #crear atributo a partir de función. Para número de marcadores de daño
    def total_damage_markers(self):
        return self._total_damage_markers

    #Dañar pared (sincronizando las 2 celdas que la comparten)
    def damage_wall(self, row: int, column: int, direction: str):
        if direction not in self.NEIGHBOR_OFFSETS:
            raise ValueError(f"Dirección inválida: {direction}")

        cell = self.walls[row][column]
        current_value = getattr(cell, direction)
        #la pared aún existe y no se ha excedido el max de marcadores de daño
        if (current_value > 0 and self._total_damage_markers < self.MAX_DAMAGE_MARKERS):
            setattr(cell, direction, current_value - 1) #añadirle 1 marcador de daño
            self._total_damage_markers += 1 #sumar un marcador de daño al contador total
        else: #evita exceder marcadores de daño
            return

        #obtener celda con la que comparte pared para añadirle el daño también
        drow, dcolumn = self.NEIGHBOR_OFFSETS[direction]
        nrow, ncolumn = row + drow, column + dcolumn
        if 0 <= nrow < self.rows and 0 <= ncolumn < self.columns:
            opposite = self.OPPOSITE_DIRECTIONS[direction]
            neighbor = self.walls[nrow][ncolumn]
            neighbor_value = getattr(neighbor, opposite)
            if neighbor_value > 0:
                setattr(neighbor, opposite, neighbor_value - 1)

    #Abrir/cerrar una puerta. Un bombero en la celda gasta 1 PA para llamar a este método (se gestiona fuera de esta clase)
    def toggle_door(self, row: int, column: int, direction: str):
        current_value = getattr(self.doors[row][column], direction)
        if current_value == 0:
            raise ValueError("No existe una puerta en esa posición")

        new_value = 1 if current_value == 2 else 2 #alternar entre abierta (1) y cerrada (2)
        setattr(self.doors[row][column], direction, new_value)

        #sincronizar el nuevo estado con la celda vecina que comparte la puerta
        drow, dcolumn = self.NEIGHBOR_OFFSETS[direction]
        nrow, ncolumn = row + drow, column + dcolumn
        if 0 <= nrow < self.rows and 0 <= ncolumn < self.columns:
            opposite = self.OPPOSITE_DIRECTIONS[direction]
            setattr(self.doors[nrow][ncolumn], opposite, new_value)

    #Destruir una puerta (por una explosión u onda de choque, no genera marcadores de daño)
    def destroy_door(self, row: int, column: int, direction: str):
        setattr(self.doors[row][column], direction, 0) #el marco destruido se trata como pared destruida/abierta

        drow, dcolumn = self.NEIGHBOR_OFFSETS[direction]
        nrow, ncolumn = row + drow, column + dcolumn
        if 0 <= nrow < self.rows and 0 <= ncolumn < self.columns:
            opposite = self.OPPOSITE_DIRECTIONS[direction]
            setattr(self.doors[nrow][ncolumn], opposite, 0)

    #Función para que el modelo o los agentes obtengan si hay una pared, puerta abierta o cerrada
    def getBarrier(self, row, column, direction):
        if getattr(self.walls[row][column], direction) > 0:
            return "wall"
        elif getattr(self.doors[row][column], direction) == 2:
            return "closedDoor"
        elif getattr(self.doors[row] [column], direction) == 1:
            return "openedDoor"
        else:
            return None

#Paredes iniciales del tablero (2 = intacta), coordenadas de acuerdo a la gráfica
initial_wall_layout = (
    #Paredes exteriores
    [{"row": 0, "column": column, "direction": "down", "state": 2} for column in range(1, 9)] +
    [{"row": row, "column": 0, "direction": "right", "state": 2} for row in range(1, 7)] +
    [{"row": 6, "column": column, "direction": "down", "state": 2} for column in range(1, 9)] +
    [{"row": row, "column": 8, "direction": "right", "state": 2} for row in range(1, 7)] +

    #Paredes interiores
    [{"row": 4, "column": column, "direction": "down", "state": 2} for column in range(1, 9)] +
    [{"row": row, "column": 7, "direction": "right", "state": 2} for row in range(5, 7)] +
    [
        {"row": 3, "column": 6, "direction": "right", "state": 2},
        {"row": 4, "column": 2, "direction": "right", "state": 2},
        {"row": 4, "column": 6, "direction": "right", "state": 2},
        {"row": 3, "column": 2, "direction": "right", "state": 2},
        {"row": 5, "column": 5, "direction": "right", "state": 2},
        {"row": 6, "column": 5, "direction": "right", "state": 2},
    ] +
    [{"row": row, "column": 3, "direction": "right", "state": 2} for row in range(1, 3)] +
    [{"row": row, "column": 5, "direction": "right", "state": 2} for row in range(1, 3)] +
    [{"row": 3, "column": column, "direction": "up", "state": 2} for column in range(3, 9)]
)

#Puertas iniciales del tablero (siempre inician cerradas, state = 2), ubicadas sobre bordes que antes eran pared
initial_door_layout = (
    #Puertas intermedias (comunican habitaciones interiores entre sí)
    [
        {"row": 1, "column": 3, "direction": "right", "state": 2},
        {"row": 2, "column": 5, "direction": "right", "state": 2},
        {"row": 3, "column": 2, "direction": "right", "state": 2},
        {"row": 4, "column": 4, "direction": "down", "state": 2},
        {"row": 4, "column": 6, "direction": "right", "state": 2},
        {"row": 3, "column": 8, "direction": "up", "state": 2},
        {"row": 6, "column": 5, "direction": "right", "state": 2},
        {"row": 6, "column": 7, "direction": "right", "state": 2},
    ] +
    #Puertas de entrada (comunican el interior del edificio con el exterior)
    [
        {"row": 0, "column": 6, "direction": "down", "state": 2},
        {"row": 3, "column": 1, "direction": "left", "state": 2},
        {"row": 6, "column": 3, "direction": "down", "state": 2},
        {"row": 4, "column": 8, "direction": "right", "state": 2},
    ]
)

#Clase para representar un punto de interés del tablero (víctima o alarma falsa)
@dataclass
class POI:
    row: int
    column: int
    type: str
    active: bool = True
    revealed: bool = False #si un bombero ya investigó este POI y conoce su tipo
    rescued: bool = False #si fue rescatada
    lost: bool = False #si no fue rescatada y fue pérdida

class FirefighterAgent(Agent):
    def __init__(self, model, row, column):
        super().__init__(model)
        self.row = row
        self.column = column

        self.carryingVictim = None

        self.max_action_points = 4
        self.action_points = self.max_action_points
        self.saved_action_points = 0
        self.knockedDown = False #indicar si el bombero fue noqueado por fuego

    #función para obtener dirección de mov de acuerdo a diferencia de coordenada de 2 casillas
    def getDirection(self, firstRow, firstColumn, secondRow, secondColumn):
        rowDifference = secondRow - firstRow
        columnDifference = secondColumn - firstColumn
        directionByOffset = {
            (-1, 0): "up",
            (1, 0): "down",
            (0, -1): "left",
            (0, 1): "right"
        }
        return directionByOffset.get((rowDifference, columnDifference))

    def moveTo(self, row, column):
        if not (0 <= row < self.model.rows and 0 <= column < self.model.columns):
            return False

        direction = self.getDirection(self.row, self.column, row, column)
        if direction is None:
            return False

        barrier = self.model.environment.getBarrier(self.row, self.column, direction)
        if barrier in ("wall", "closedDoor"):
            return False

        #nunca permitir mover una víctima hacia una celda con fuego: considerar fuego que apareció después
        if (self.carryingVictim is not None and self.model.fireCells[row, column] == 2):
            return False

        self.model.FigthersGrid.move_agent(self, (column, row))
        self.row = row
        self.column = column

        # Si está cargando una víctima, moverla junto con el bombero
        if self.carryingVictim is not None:
            self.carryingVictim.row = row
            self.carryingVictim.column = column

        #Investigar automáticamente los POIs activos de la celda a la que llegó el bombero
        for poi in self.model.getPOIsAt(row, column):
            self.model.investigatePOI(poi, self)

        #si llegó al exterior cargando una víctima, se rescata de inmediato
        self._checkVictimRescue(row, column)

        return True

    #Si el bombero cargando una víctima llegó a una celda del borde del tablero, la rescata
    def _checkVictimRescue(self, row, column):
        if self.carryingVictim is None:
            return

        isExterior = (
            row == 0
            or row == self.model.rows - 1
            or column == 0
            or column == self.model.columns - 1
        )
        if isExterior:
            victim = self.carryingVictim
            victim.rescued = True
            victim.active = False
            self.carryingVictim = None

    def extinguishFire(self, row, column, removeFire=False):
        #comprobar casillas
        if not (0 <= row < self.model.rows and 0 <= column < self.model.columns):
            return False
        distance = (abs(row - self.row) + abs(column - self.column))
        if distance > 1:
            return False
        #extingue desde una celda adyacente, comprobar que no hay barrera
        if distance == 1:
            direction = self.getDirection(self.row, self.column, row, column)
            barrier = self.model.environment.getBarrier(self.row, self.column, direction)
            if barrier in ("wall", "closedDoor"): #hay barrera, no puede extinguir
                return False

        currentState = self.model.fireCells[row, column]
        if currentState == 1:
            newState = 0
            cost = REMOVE_SMOKE
        elif currentState == 2:
            newState = 0 if removeFire else 1
            cost = REMOVE_FIRE if removeFire else FIRE_TO_SMOKE
        else:
            return False

        if cost > self.action_points:
            return False

        self.model.fireCells[row, column] = newState
        self.action_points -= cost
        return True

    #función para obtener las salidas disponibles (para poder sacar a víctimas cuando un bombero es noqueado)
    def getRescueExits(self):
        exits = []
        # Parte superior
        for column in range(1, self.model.columns - 1):
            barrier = self.model.environment.getBarrier(1, column, "up")
            if barrier != "wall":
                exits.append((0, column))
        # Parte inferior
        for column in range(1, self.model.columns - 1):
            barrier = self.model.environment.getBarrier(self.model.rows - 2, column, "down")
            if barrier != "wall":
                exits.append((self.model.rows - 1, column))
        # Lado izquierdo
        for row in range(1, self.model.rows - 1):
            barrier = self.model.environment.getBarrier(row, 1, "left")
            if barrier != "wall":
                exits.append((row, 0))
        # Lado derecho
        for row in range(1, self.model.rows - 1):
            barrier = self.model.environment.getBarrier(row, self.model.columns - 2, "right")
            if barrier != "wall":
                exits.append((row, self.model.columns - 1))
        return exits

    #Iniciar turno: sumar AP guardados del turno anterior a los 4 AP base
    def startTurn(self):
        self.action_points = self.max_action_points + self.saved_action_points
        self.saved_action_points = 0

    #Terminar turno: guardar AP no utilizados, respetando el máximo acumulable
    def endTurn(self):
        #un bombero no puede finalizar el turno si está noqueado o sobre fuego
        if self.knockedDown or self.model.fireCells[self.row, self.column] == 2:
            return False

        self.saved_action_points = min(self.action_points, self.max_action_points)
        self.action_points = 0
        return True

    #Noquear al bombero alcanzado por fuego, perder víctima cargada y moverlo a una salida disponible
    def knockout(self):
        if self.knockedDown:
            return

        self.knockedDown = True

        if self.carryingVictim is not None:
            victim = self.carryingVictim
            victim.active = False
            victim.revealed = True
            victim.lost = True
            self.carryingVictim = None

        exits = self.getRescueExits()
        if exits:
            exit_row, exit_column = exits[0]
            self.model.FigthersGrid.move_agent(self, (exit_column, exit_row))
            self.row = exit_row
            self.column = exit_column

    #Recolectar todas las acciones válidas y pagables (con los AP actuales) desde la posición actual
    def _getPossibleActions(self):
        options = []
        row, column = self.row, self.column

        #1) Extinguir la celda propia si tiene humo o fuego
        currentState = self.model.fireCells[row, column]
        if currentState == 1 and REMOVE_SMOKE <= self.action_points:
            options.append(("extinguish", row, column, False, REMOVE_SMOKE))
        elif currentState == 2:
            if FIRE_TO_SMOKE <= self.action_points:
                options.append(("extinguish", row, column, False, FIRE_TO_SMOKE))
            if REMOVE_FIRE <= self.action_points:
                options.append(("extinguish", row, column, True, REMOVE_FIRE))

        #2) Revisar cada una de las 4 direcciones para mover, abrir puerta, dañar pared o extinguir adyacente
        for direction, (drow, dcolumn) in self.model.environment.NEIGHBOR_OFFSETS.items():
            newRow, newColumn = row + drow, column + dcolumn
            if not (0 <= newRow < self.model.rows and 0 <= newColumn < self.model.columns):
                continue

            barrier = self.model.environment.getBarrier(row, column, direction)

            if barrier == "wall":
                wallState = getattr(self.model.environment.walls[row][column], direction)
                if wallState > 0 and DAMAGE_WALL <= self.action_points:
                    options.append(("damageWall", direction, DAMAGE_WALL))
                continue

            if barrier == "closedDoor":
                if USE_DOOR <= self.action_points:
                    options.append(("openDoor", direction, USE_DOOR))
                continue

            # Sin barrera o puerta abierta: se puede mover o extinguir la celda vecina
            destinationHasFire = (self.model.fireCells[newRow, newColumn] == 2)

            if self.carryingVictim is not None:
                #nunca mover una víctima hacia el fuego
                if not destinationHasFire and CARRY_VICTIM <= self.action_points:
                    options.append(("move", direction, CARRY_VICTIM))
            else:
                moveCost = MOVE_SPACE_W_FIRE if destinationHasFire else MOVE_SPACE
                #no se puede terminar el movimiento (y por lo tanto el turno) sobre una celda con fuego
                if destinationHasFire and self.action_points - moveCost == 0:
                    pass
                elif moveCost <= self.action_points:
                    options.append(("move", direction, moveCost))

            #extinguir humo/fuego de la celda vecina sin moverse hacia ella
            neighborState = self.model.fireCells[newRow, newColumn]
            if neighborState == 1 and REMOVE_SMOKE <= self.action_points:
                options.append(("extinguish", newRow, newColumn, False, REMOVE_SMOKE))
            elif neighborState == 2:
                if FIRE_TO_SMOKE <= self.action_points:
                    options.append(("extinguish", newRow, newColumn, False, FIRE_TO_SMOKE))
                if REMOVE_FIRE <= self.action_points:
                    options.append(("extinguish", newRow, newColumn, True, REMOVE_FIRE))

        return options

    #Ejecutar la acción aleatoria elegida; regresa True si sí se pudo ejecutar
    def _executeAction(self, action):
        kind = action[0]

        if kind == "extinguish":
            _, row, column, removeFire, _cost = action
            return self.extinguishFire(row, column, removeFire)

        if kind == "move":
            _, direction, cost = action
            if cost > self.action_points:
                return False
            drow, dcolumn = self.model.environment.NEIGHBOR_OFFSETS[direction]
            newRow, newColumn = self.row + drow, self.column + dcolumn
            if not self.moveTo(newRow, newColumn):
                return False
            self.action_points -= cost
            return True

        if kind == "openDoor":
            _, direction, cost = action
            if cost > self.action_points:
                return False
            self.model.environment.toggle_door(self.row, self.column, direction)
            self.action_points -= cost
            return True

        if kind == "damageWall":
            _, direction, cost = action
            if cost > self.action_points:
                return False
            self.model.environment.damage_wall(self.row, self.column, direction)
            self.action_points -= cost
            return True

        return False

    #Jugar el turno completo: elegir y ejecutar acciones aleatorias válidas hasta agotar AP u opciones
    def playTurn(self):
        if self.knockedDown:
            return

        while self.action_points > 0:
            options = self._getPossibleActions()
            if not options:
                break

            action = self.model.random.choice(options)
            if not self._executeAction(action):
                break

class FireRescueModel(Model):
    def __init__(self, columns, rows, num_players):
        super().__init__()

        self.columns = columns
        self.rows = rows

        #control de la simulación: win/loose y turno de bombero inicial
        self.current_firefighter_index = 0
        self.game_over = False
        self.game_result = None

        # Grid para los bomberos (agentes)
        self.FigthersGrid = MultiGrid(columns, rows, torus=False)

        # Matriz para los objetos de tipo fuego/humo
        self.fireCells = np.zeros((rows, columns), dtype=int)

        # Manejador de paredes y puertas, cargado con las coordenadas iniciales del tablero
        self.environment = EnvironmentManager(columns, rows, initial_wall_layout, initial_door_layout)

        # Crear bomberos en las primeras celdas disponibles del tablero
        self.firefighters = []
        for row in range(rows):
            for column in range(columns):
                if len(self.firefighters) == num_players:
                    break
                firefighter = FirefighterAgent(self, row, column)
                self.FigthersGrid.place_agent(firefighter, (column, row))
                self.firefighters.append(firefighter)
            if len(self.firefighters) == num_players:
                break

        if len(self.firefighters) < num_players:
            raise ValueError("No hay suficientes celdas para colocar a todos los bomberos")

        # Coordenadas de fuegos existentes al inicio del juego (row, column)
        initialFires = [
            (2, 2),
            (2, 3),
            (3, 2),
            (3, 3),
            (3, 4),
            (3, 5),
            (4, 4),
            (5, 6),
            (5, 7),
            (6, 6)
        ]

        for row, column in initialFires:
            self.fireCells[row, column] = 2  # 2 equivale a fuego

        # Mazo de tipos de POI del juego de mesa: 10 víctimas y 5 alarmas falsas, en orden aleatorio
        self._poi_type_deck = ["victim"] * 10 + ["falseAlarm"] * 5
        self.random.shuffle(self._poi_type_deck)

        # POIs iniciales de ejemplo (row, column)
        self.pois = []
        initialPOIs = [
            (2, 4),
            (5, 1),
            (5, 8),
        ]
        for row, column in initialPOIs:
            poi_type = self.drawPOIType()
            self.addPOI(row, column, poi_type)

    def advanceFire(self):
        # Simula el tiro de dados para ir a la casilla donde debe avanzar el fuego
        row = self.random.randrange(1, self.rows - 1)
        column = self.random.randrange(1, self.columns - 1)

        if self.fireCells[row, column] == 0:
            # No hay ni fuego ni humo en la casilla
            if self.check_adjacentFires(row, column):
                self.fireCells[row, column] = 2
                # Si hay fuegos adyacentes se añade fuego
            else:
                self.fireCells[row, column] = 1
                # Si no hay fuegos adyacentes se añade humo

        elif self.fireCells[row, column] == 1:
            # Hay humo en la casilla, se añade fuego
            self.fireCells[row, column] = 2

        elif self.fireCells[row, column] == 2:
            # Hay fuego en la casilla, se genera una explosión
            self.explosion(row, column)

        #revisar si el avance del fuego dejó a algún bombero sobre fuego
        self._resolveFirefighterKOs()

    def check_adjacentFires(self, row, column):
        # Coordenadas adyacentes dentro de la matriz
        neighbors = [
            (row - 1, column, "up"),
            (row + 1, column, "down"),
            (row, column - 1, "left"),
            (row, column + 1, "right")
        ]

        for neighbor_row, neighbor_column, direction in neighbors:
            # Revisa que la coordenada esté dentro de la matriz
            if (0 <= neighbor_row < self.rows and 0 <= neighbor_column < self.columns):
                barrier = self.environment.getBarrier(row, column, direction)
                #revisar que haya fuego en la coordenada Y que no haya una pared o puerta cerrada
                if self.fireCells[neighbor_row, neighbor_column] == 2 and (barrier == None or barrier == "openedDoor"):
                    return True

        return False

    def explosion(self, row, column):
        # Coordenadas adyacentes de la celda de la explosión dentro de la matriz
        neighbors = [
            (row - 1, column, "up"),
            (row + 1, column, "down"),
            (row, column - 1, "left"),
            (row, column + 1, "right")
        ]
        for neighbor_row, neighbor_column, direction in neighbors:
            barrier = self.environment.getBarrier(row, column, direction)
            #Hay pared: la explosión la daña y no continúa
            if barrier == "wall":
                self.environment.damage_wall(row, column, direction)
            #Hay puerta cerrada: la destruye y no continúa
            elif barrier == "closedDoor":
                self.environment.destroy_door(row, column, direction)
            else:
                #Puerta abierta: la explosión la destruye, pero sí continúa
                if barrier == "openedDoor":
                    self.environment.destroy_door(row, column, direction)
                if (0 <= neighbor_row < self.rows and
                    0 <= neighbor_column < self.columns):
                    #Hay celda vacía: se convierte en fuego
                    if self.fireCells[neighbor_row, neighbor_column] == 0:
                        self.fireCells[neighbor_row, neighbor_column] = 2
                    #Hay humo: se convierte en fuego
                    elif self.fireCells[neighbor_row, neighbor_column] == 1:
                        self.fireCells[neighbor_row, neighbor_column] = 2
                    #Hay fuego: comienza shockwave en esa dirección
                    elif self.fireCells[neighbor_row, neighbor_column] == 2:
                        self.shockwave(
                            neighbor_row,
                            neighbor_column,
                            direction
                        )

        #revisar si la explosión dejó a algún bombero sobre fuego
        self._resolveFirefighterKOs()

    def shockwave(self, row, column, direction):
        #Obtener drow y dcolumn para seguir avanzando en esa dirección
        drow, dcolumn = self.environment.NEIGHBOR_OFFSETS[direction]
        current_row = row
        current_column = column
        #Mientras siga encontrando fuego (sin encontrar un return)
        while True:
            #Revisar si hay barrera entre la celda actual y la siguiente
            barrier = self.environment.getBarrier(
                current_row,
                current_column,
                direction
            )
            #Hay pared: la explosión la daña y no continúa
            if barrier == "wall":
                self.environment.damage_wall(
                    current_row,
                    current_column,
                    direction
                )
                self._resolveFirefighterKOs()
                return
            #Hay puerta cerrada: la destruye y no continúa
            elif barrier == "closedDoor":
                self.environment.destroy_door(
                    current_row,
                    current_column,
                    direction
                )
                self._resolveFirefighterKOs()
                return
            #Puerta abierta: la explosión la destruye, pero sí continúa
            elif barrier == "openedDoor":
                self.environment.destroy_door(
                    current_row,
                    current_column,
                    direction
                )
            #Obtener la siguiente celda en esa misma dirección
            next_row = current_row + drow
            next_column = current_column + dcolumn
            #Ya salió de la matriz (fin)
            if not (0 <= next_row < self.rows and
                    0 <= next_column < self.columns):
                self._resolveFirefighterKOs()
                return
            #Hay espacio vacío: se convierte en fuego y termina
            if self.fireCells[next_row, next_column] == 0:
                self.fireCells[next_row, next_column] = 2
                self._resolveFirefighterKOs()
                return
            #Hay humo: se convierte en fuego y termina
            elif self.fireCells[next_row, next_column] == 1:
                self.fireCells[next_row, next_column] = 2
                self._resolveFirefighterKOs()
                return
            #Hay fuego, la onda sigue avanzando
            elif self.fireCells[next_row, next_column] == 2:
                current_row = next_row
                current_column = next_column

    #Revisar bomberos alcanzados por fuego y aplicar KO
    def _resolveFirefighterKOs(self):
        for firefighter in self.firefighters:
            if (
                not firefighter.knockedDown
                and self.fireCells[firefighter.row, firefighter.column] == 2
            ):
                firefighter.knockout()

    #Validar posición y crear un POI; no se pueden crear duplicados activos del mismo tipo en la misma celda
    def addPOI(self, row, column, type):
        if not (0 <= row < self.rows and 0 <= column < self.columns):
            return False

        for poi in self.pois:
            if poi.active and poi.row == row and poi.column == column and poi.type == type:
                return False

        self.pois.append(POI(row, column, type))
        return True

    #Sacar aleatoriamente el siguiente tipo de POI del mazo (10 víctimas + 5 alarmas falsas en total)
    def drawPOIType(self):
        if not self._poi_type_deck:
            return None
        return self._poi_type_deck.pop()

    #Devolver únicamente los POIs todavía activos
    def getActivePOIs(self):
        return [poi for poi in self.pois if poi.active]

    #Desactivar un POI sin eliminarlo de self.pois, para conservar el historial
    def removePOI(self, poi):
        poi.active = False

    #Devolver los POIs activos ubicados en una celda específica
    def getPOIsAt(self, row, column):
        return [poi for poi in self.pois if poi.active and poi.row == row and poi.column == column]

    def replenishPOIs(self):
        while (len(self.getActivePOIs()) < 3 and self._poi_type_deck): #hay menos de 3 POIs activos
            row = self.random.randrange(1, self.rows - 1)
            column = self.random.randrange(1, self.columns - 1)
            #ubicar si ya hay POI
            if self.getPOIsAt(row, column):
                continue
            #si hay fuego/humo en la posición donde aparecerá el POI, se retira
            self.fireCells[row, column] = 0
            poi_type = self.drawPOIType()

            if poi_type is None:
                return
            #añadir nuevo POI
            self.addPOI(row, column, poi_type)
            new_poi = self.pois[-1]

            #si aparece debajo de un bombero se revela
            for firefighter in self.firefighters:
                if (firefighter.row == row and firefighter.column == column):
                    self.investigatePOI(new_poi, firefighter)
                    break

    #Revelar un POI oculto; una alarma falsa se retira del tablero, una víctima permanece activa hasta ser rescatada
    def investigatePOI(self, poi, firefighter=None):
        if not poi.active or poi.revealed:
            return False

        poi.revealed = True

        # Alarma falsa: simplemente desaparece
        if poi.type == "falseAlarm":
            self.removePOI(poi)
            return True

        # Víctima: si el bombero que la descubrió no está cargando otra, la recoge
        if poi.type == "victim" and firefighter is not None:
            if firefighter.carryingVictim is None:
                firefighter.carryingVictim = poi

        return True

    def resolveVictimsInFire(self):
        for poi in self.pois: #recorrer todos los POIs
            if not poi.active:
                continue
            if self.fireCells[poi.row, poi.column] != 2: #no hay fuego en casilla
                continue

            #si hay/llegó fuego a la casilla, se desactiva el POI
            poi.revealed = True
            poi.active = False
            #si es víctima: perdida
            if poi.type == "victim":
                poi.lost = True
                #dejar de cargarla
                for firefighter in self.firefighters:
                    if firefighter.carryingVictim is poi:
                        firefighter.carryingVictim = None

    #función para contar víctimas ya rescatadas
    def countRescuedVictims(self):
        return sum(1 for poi in self.pois if poi.type == "victim" and poi.rescued)

    #función para contar víctimas perdidas
    def countLostVictims(self):
        return sum(1 for poi in self.pois if poi.type == "victim" and poi.lost)

    #Función para revisar condiciones win/loose
    def checkGameOver(self):
        #caso de victoria
        if self.countRescuedVictims() >= 7: #min 7 víctimas rescatadas
            self.game_over = True
            self.game_result = "win"
            return True
        #caso de derrota por víctimas perdidas
        if self.countLostVictims() >= 4: #4 víctimas perdidas
            self.game_over = True
            self.game_result = "lost_victims"
            return True
        #derrota por colapso del edificio, máximo 24 marcadores de daño
        if self.environment.total_damage_markers >= self.environment.MAX_DAMAGE_MARKERS:
            self.game_over = True
            self.game_result = "building_collapse"
            return True

        return False

    #step está representando el momento de turno de 1 jugador en el juego con advanceFire
    def step(self):
        if self.game_over: #el juego se terminó porque cumplió win o loose
            return
        #llamar a acción a bombero en turno
        firefighter = self.firefighters[self.current_firefighter_index]
        #si había sufrido KO en este turno se recuperó
        if firefighter.knockedDown:
            firefighter.knockedDown = False

        firefighter.startTurn() #sumar APs
        firefighter.playTurn() #ejecutar acciones aleatorias válidas mientras tenga AP
        turnEnded = firefighter.endTurn() #guardar APs sobrantes
        if not turnEnded:
            return
        #revisar si con sus acciones terminó el juego
        if self.checkGameOver():
            return
        #realizar advanceFire de acuerdo a reglas de juego
        self.advanceFire()
        #revisar si hubo víctimas eliminadas por el fuego y eliminar
        self.resolveVictimsInFire()
        #revisar si con el avance del fuego terminó el juego
        if self.checkGameOver():
            return
        #reponer POIs del tablero si es necesario
        self.replenishPOIs()
        #aumentar índice de bombero en turno para siguiente jugador
        self.current_firefighter_index = (self.current_firefighter_index + 1) % len(self.firefighters)
