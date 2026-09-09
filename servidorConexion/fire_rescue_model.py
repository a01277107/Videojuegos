"""Este archivo tiene el mismo contenido que el notebook "fireRescueSimulation.ipynb" (lógica de simulación de Flashpoint Firerescue),
pero este archivo puede ser importado por el servidor para que pueda tener su propio modelo y variables a usar cuando Unity le haga requests.
"""

from dataclasses import dataclass
from collections import deque

import numpy as np
from mesa import Model, Agent
from mesa.space import SingleGrid

import heapq

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
        if current_value > 0: #la pared aún existe
            setattr(cell, direction, current_value - 1) #añadirle 1 marcador de daño
            self._total_damage_markers += 1 #sumar un marcador de daño al contador total

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

#Clase para representar un punto de interés del tablero (víctima, fuego, peligro, etc.)
@dataclass
class POI:
    row: int
    column: int
    type: str
    priority: int = 0
    active: bool = True
    revealed: bool = False #si un bombero ya investigó este POI y conoce su tipo

class FirefighterAgent(Agent):
    def __init__(self, model, row, column):
        super().__init__(model)
        self.row = row
        self.column = column
        self.objective = None
        self.actionQueue = deque()

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

        row_difference = row - self.row
        column_difference = column - self.column
        direction_by_offset = {
            (-1, 0): "up",
            (1, 0): "down",
            (0, -1): "left",
            (0, 1): "right",
        }
        direction = direction_by_offset.get((row_difference, column_difference))
        if direction is None:
            return False

        barrier = self.model.environment.getBarrier(self.row, self.column, direction)
        if barrier in ("wall", "closedDoor"):
            return False

        self.model.FigthersGrid.move_agent(self, (column, row))
        self.row = row
        self.column = column
        return True

    def setObjective(self, row, column):
        if not (0 <= row < self.model.rows and 0 <= column < self.model.columns):
            return False

        self.objective = (row, column)
        return True

    def getNeighbourMoves(self, row, column): #función para obtener el costo y acciones de moverse de su celda en cada una de las cuatro direcciones
        neighbors = []
        directions = ["up", "down", "left", "right"]
        for direction in directions:
            drow, dcolumn = self.model.environment.NEIGHBOR_OFFSETS[direction] #diferencia de celda según dirección de mov
            neighRow = row + drow #número de fila del vecino
            neighColumn = column + dcolumn #número de columna del vecino
            if (0 <= neighRow < self.model.rows and 0 <= neighColumn < self.model.columns): #verificar que casilla entre en tablero
                cost, actions = self.cellMoveCost(row, column, direction) #obtener costo y acciones de mov de función
                neighbors.append((neighRow, neighColumn, cost, actions)) #guardarlo en arreglo de vecinos
        return neighbors #devolver arreglo con costo y acciones de los 4 vecinos

    def cellMoveCost(self, row, column, direction): #función para obtener costo de acciones para moverse a una casilla
        cost = 0 #costo de acciones
        actions = [] #acciones a guardar para ese movimiento
        drow, dcolumn = self.model.environment.NEIGHBOR_OFFSETS[direction] #diferencia de celda según dirección de mov
        newRow = row + drow #nuevo número de fila
        newColumn = column + dcolumn #nuevo número de columna
        if not (0 <= newRow < self.model.rows and 0 <= newColumn < self.model.columns): #verificar que casilla entre en tablero
            return None, []
        barrier = self.model.environment.getBarrier(row, column, direction)
        if barrier is None or barrier == "openedDoor": #sin barrera o puerta abierta
            if self.model.fireCells[newRow, newColumn] == 2: #revisar si hay fuego en nueva celda para sumar costo correcto
                cost += MOVE_SPACE_W_FIRE #añadir al costo total
                actions.append(("moveSpaceWithFire", row, column, direction)) #añadir acción al arreglo
            else: #no hay fuego, diferente costo
                cost += MOVE_SPACE
                actions.append(("moveSpace", row, column, direction))
        elif barrier == "closedDoor": #hay una puerta cerrada, añadir costo de abrir la puerta y de moverse
            cost += USE_DOOR
            actions.append(("useDoor", row, column, direction))
            if self.model.fireCells[newRow, newColumn] == 2:
                cost += MOVE_SPACE_W_FIRE
                actions.append(("moveSpaceWithFire", row, column, direction))
            else:
                cost += MOVE_SPACE
                actions.append(("moveSpace", row, column, direction))
        elif barrier == "wall": #hay una pared, añadir costo de dañar pared y de moverse
            wallState = getattr(self.model.environment.walls[row][column], direction)
            cost += DAMAGE_WALL * wallState #revisar estado de pared para obtener costo total de romper la pared (2 daños)
            actions.append(("damageWall", row, column, direction, wallState))
            if self.model.fireCells[newRow, newColumn] == 2:
                cost += MOVE_SPACE_W_FIRE
                actions.append(("moveSpaceWithFire", row, column, direction))
            else:
                cost += MOVE_SPACE
                actions.append(("moveSpace", row, column, direction))

        return cost, actions #devolver el costo y las acciones del movimiento de celda

    #función de heurística para usar en algoritmo A*: f = g + h
    def heuristicEstimation(self, row, column, objectiveRow, objectiveColumn):
        return (abs(row - objectiveRow) + abs(column - objectiveColumn)) #diferencia absoluta entre casilla y objetivo

    def obtainRoute(self, objectiveRow, objectiveColumn): #algoritmo para obtener ruta con su costo basado en algoritmo A*
        start = (self.row, self.column)
        objective = (objectiveRow, objectiveColumn)
        pending = [] #casillas pendientes de revisar
        origin = {} #de qué casilla venía el bombero
        gCosts = {start: 0} #costo acumulado (real) en fórmula A*
        #en la casilla en la que empieza el costo total de la fórmula es solo el heurístico
        initialTotalCost = self.heuristicEstimation(self.row, self.column, objectiveRow, objectiveColumn)

        #se usa una cola de prioridad para así poder revisar las opciones de menor costo primero
        heapq.heappush(pending, (initialTotalCost, start))
        while pending: #mientras la cola no esté vacía
            currentTotalCost, currentPosition = heapq.heappop(pending) #sacar casilla de menor costo
            if currentPosition == objective: #ya llegó a la casilla objetivo
                break
            currentRow, currentColumn = currentPosition
            neighbors = self.getNeighbourMoves(currentRow, currentColumn) #obtener vecinos de la casilla actual con función
            for neighborRow, neighborColumn, moveCost, actions in neighbors:
                neighbor = neighborRow, neighborColumn #posición del vecino
                gCost = moveCost + gCosts[currentPosition] #para cada vecino, obtener el costo acumulado (casilla previa + costo a vecino)
                hCost = self.heuristicEstimation(neighborRow, neighborColumn, objectiveRow, objectiveColumn) #obtener costo heurísitco del vecino

                #no se había llegado antes a esa casilla o se encontró un menor costo para ella
                if neighbor not in gCosts or gCost< gCosts[neighbor]:
                    gCosts[neighbor] = gCost  #actualizar costo acumulado/real g de casilla
                    origin[neighbor] = currentPosition #añadir casilla previa para llegar a ella
                    neighSumCost = gCost + hCost #real + heurística (costo f)
                    heapq.heappush(pending, (neighSumCost, neighbor)) #añadirla a la cola con su costo total f
                
        if objective not in gCosts: #asegurar que se encontró una ruta al objetivo
            return None
        #reconstruir la ruta
        route = [objective]
        currentPosition = objective
        while currentPosition != start:
            currentPosition = origin[currentPosition] #retroceder 1 casilla
            route.append(currentPosition) #agregar a la ruta
        route.reverse() #invertir orden de las casillas agregadas

        #guardar también los movimientos y acciones
        routeMovements = []
        for i in range (len(route) - 1): #recorrer hasta penúltima casilla (para mov a última)
            firstPosition = route[i]
            secondPosition = route[i + 1]
            firstRow, firstColumn = firstPosition
            secondRow, secondColumn = secondPosition
            direction = self.getDirection(firstRow, firstColumn, secondRow, secondColumn)
            cost, movements = self.cellMoveCost(firstRow, firstColumn, direction) #obtener acciones/movimientos de una casilla a la otra
            routeMovements.extend(movements) #añadirlo a movs de la ruta

        return route, gCosts[objective], routeMovements #regresar ruta (casillas), su costo acumulado y movimientos/acciones necesarias

class FireRescueModel(Model):
    def __init__(self, columns, rows, num_players):
        super().__init__()

        self.columns = columns
        self.rows = rows

        # Grid para los bomberos (agentes)
        self.FigthersGrid = SingleGrid(columns, rows, torus=False)

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

        # POIs iniciales de ejemplo (row, column, type, priority)
        self.pois = []
        initialPOIs = [
            (2, 4, "victim", 10),
            (5, 1, "victim", 10),
            (5, 8, "victim", 10),
        ]
        for row, column, poi_type, priority in initialPOIs:
            self.addPOI(row, column, poi_type, priority)


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
                return
            #Hay puerta cerrada: la destruye y no continúa
            elif barrier == "closedDoor":
                self.environment.destroy_door(
                    current_row,
                    current_column,
                    direction
)
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
                return
            #Hay espacio vacío: se convierte en fuego y termina
            if self.fireCells[next_row, next_column] == 0:
                self.fireCells[next_row, next_column] = 2
                return
            #Hay humo: se convierte en fuego y termina
            elif self.fireCells[next_row, next_column] == 1:
                self.fireCells[next_row, next_column] = 2
                return
            #Hay fuego, la onda sigue avanzando
            elif self.fireCells[next_row, next_column] == 2:
                current_row = next_row
                current_column = next_column


    #Validar posición y crear un POI; no se pueden crear duplicados activos del mismo tipo en la misma celda
    def addPOI(self, row, column, type, priority=0):
        if not (0 <= row < self.rows and 0 <= column < self.columns):
            return False

        for poi in self.pois:
            if poi.active and poi.row == row and poi.column == column and poi.type == type:
                return False

        self.pois.append(POI(row, column, type, priority))
        return True

    #Devolver únicamente los POIs todavía activos
    def getActivePOIs(self):
        return [poi for poi in self.pois if poi.active]

    #Desactivar un POI sin eliminarlo de self.pois, para conservar el historial
    def removePOI(self, poi):
        poi.active = False

    #Devolver los POIs activos ubicados en una celda específica
    def getPOIsAt(self, row, column):
        return [poi for poi in self.pois if poi.active and poi.row == row and poi.column == column]

    #Revelar un POI oculto y resolverlo de inmediato (se retira permanentemente del tablero)
    def investigatePOI(self, poi):
        if not poi.active or poi.revealed:
            return False

        poi.revealed = True
        self.removePOI(poi)
        return True

