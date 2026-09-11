"""Modelo importable de la simulación de Flash Point: Fire Rescue para el servidor HTTP y Unity."""

from collections import deque
from dataclasses import dataclass

from mesa import Agent, Model
from mesa.space import MultiGrid

import numpy as np
import heapq #se usa una cola de prioridad para implementar el algoritmo A*

#costos de acciones (fijos)
MOVE_SPACE = 1
MOVE_SPACE_W_FIRE = 2
USE_DOOR = 1
DAMAGE_WALL = 2 #revisar daño vs romper
CARRY_VICTIM = 2
REMOVE_SMOKE = 1
FIRE_TO_SMOKE = 1
REMOVE_FIRE = 2

# Ajuste de bid por daño estructural de la ruta
building_damage_multiplier = 1

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

#Clase para representar un punto de interés del tablero (víctima, fuego, peligro, etc.)
@dataclass
class POI:
    row: int
    column: int
    type: str
    priority: int = 0
    active: bool = True
    revealed: bool = False #si un bombero ya investigó este POI y conoce su tipo
    assigned_to: object = None
    rescued: bool = False #si fue rescatada
    lost: bool = False #si no fue rescatada y fue pérdida

#Prioridad centralizada por tipo de objetivo de subasta (a mayor valor, mayor prioridad)
OBJECTIVE_PRIORITY = {
    "victim": 100,
    "fire": 50,
}

#Objetivo ligero para representar una celda con fuego real (fireCells == 2) ante la subasta,
#sin duplicar el estado del fuego: se sincroniza a partir de fireCells, nunca al revés
@dataclass
class FireObjective:
    row: int
    column: int
    type: str = "fire"
    priority: int = OBJECTIVE_PRIORITY["fire"]
    active: bool = True
    assigned_to: object = None

#Calcular cuántos marcadores de daño estructural implican las acciones planeadas de una ruta
def calculateRouteDamage(routeActions):
    return sum(
        action[4]
        for action in routeActions
        if action[0] == "damageWall"
    )

class FirefighterAgent(Agent):
    def __init__(self, model, row, column):
        super().__init__(model)
        self.row = row
        self.column = column
        self.objective = None
        self.actionQueue = deque()
        self.route = None
        self.routeCost = None
        self.routeActions = None

        self.carryingVictim = None
        self.rescueExit = None

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

        return True

    def extinguishFire(self, row, column, removeFire=False):
        #comprobar casillas
        if not (0 <= row < self.model.rows and 0 <= column < self.model.columns):
            return False
        distance = (abs(row - self.row) + abs(column - self.column))
        if distance > 1:
            return False
        #extingue desde una celda adyacente, comprobar que no hay barrera
        if distance == 1:
            direction = self.getDirection(self.row,self.column,row,column)
            barrier = self.model.environment.getBarrier(self.row,self.column,direction)
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

    def setObjective(self, row, column):
        if not (0 <= row < self.model.rows and 0 <= column < self.model.columns):
            return False

        self.objective = (row, column)
        return True

    def setObjectivePOI(self, poi):
        return self.setObjective(poi.row, poi.column)

    def planFireObjective(self, objective):
        if (not objective.active or objective.type != "fire" or self.model.fireCells[objective.row, objective.column] != 2):
            return None

        fireRow = objective.row
        fireColumn = objective.column
        candidatePositions = [] #posiciones desde las cuales se puede intentar extinguir

        #el bombero ya está en la celda con fuego (puede extinguir desde ahí)
        if (self.row, self.column) == (fireRow, fireColumn):
            candidatePositions.append((fireRow, fireColumn))

        for drow, dcolumn in self.model.environment.NEIGHBOR_OFFSETS.values(): #casillas adyacentes al fuego
            candidateRow = fireRow + drow
            candidateColumn = fireColumn + dcolumn
            if not (
                0 <= candidateRow < self.model.rows
                and 0 <= candidateColumn < self.model.columns
            ):
                continue
            #no extinguir desde otra celda con fuego
            if self.model.fireCells[candidateRow, candidateColumn] == 2:
                continue
            #añadir a posiciones para extinguir
            candidatePositions.append((candidateRow, candidateColumn))
        bestPlan = None
        for attackRow, attackColumn in candidatePositions:
            #obtainRoute con A* calcula ruta a la posición desde donde atacará el fuego (no al fuego)
            routeData = self.obtainRoute(attackRow, attackColumn)
            if routeData is None:
                continue
            route, routeCost, routeActions = routeData
            #la posición de ataque NO es el propio fuego (no debe estar en la ruta)
            if ((attackRow, attackColumn) != (fireRow, fireColumn) and (fireRow, fireColumn) in route):
                continue

            extraCost = 0
            extraActions = []
            #revisar si hay bareras entre el fuego y el bombero cuando ya está al lado
            if (attackRow, attackColumn) != (fireRow, fireColumn):
                direction = self.getDirection(attackRow,attackColumn,fireRow,fireColumn)
                barrier = self.model.environment.getBarrier(attackRow,attackColumn,direction)
                #hay puerta cerrada, abrirla
                if barrier == "closedDoor":
                    extraCost += USE_DOOR
                    extraActions.append(("useDoor",attackRow,attackColumn,direction))
                #hay pared, destruirla
                elif barrier == "wall":
                    wallState = getattr(self.model.environment.walls[attackRow][attackColumn],direction)
                    extraCost += DAMAGE_WALL * wallState
                    extraActions.append(("damageWall",attackRow,attackColumn,direction,wallState))
            #apagar el fuego
            extraCost += REMOVE_FIRE
            extraActions.append(("EXTINGUISH",fireRow,fireColumn,True))
            #hacer plan con costo y acciones originales de la ruta + añadidos
            totalCost = routeCost + extraCost 
            totalActions = routeActions + extraActions
            plan = (totalCost, route, totalActions)
            if (bestPlan is None or totalCost < bestPlan[0]):
                bestPlan = plan
        return bestPlan #regresar plan completo para el objetivo

    def calculateBid(self, objective):
        if not objective.active: #el objetivo no está activo
            return None

        #objetivo de tipo apagar incendio, usar propia función
        if objective.type == "fire":
            bid_data = self.planFireObjective(objective)
        else:
            #objetivo de tipo revelar POI, obtainRoute original
            route_data = self.obtainRoute(objective.row,objective.column)
            if route_data is None:
                return None
            route, cost, actions = route_data
            bid_data = (cost, route, actions)

        if bid_data is None:
            return None

        existing_bid, route, routeActions = bid_data

        #multiplicar el daño que hace la ruta por el factor de importancia del daño
        route_damage = calculateRouteDamage(routeActions)
        damage_cost = route_damage * building_damage_multiplier
        bid = existing_bid + damage_cost #sumarle ese daño total al costo para que sea menos atractiva la oferta

        return bid, route, routeActions #devolver oferta con costo ajustado, ruta y acciones

    #función para obtener las salidas disponibles (para poder sacar a víctimas)
    def getRescueExits(self):
        exits = []
        # Parte superior
        for column in range(1, self.model.columns - 1):
            barrier = self.model.environment.getBarrier(1,column,"up")
            if barrier != "wall":
                exits.append((0, column))
        # Parte inferior
        for column in range(1, self.model.columns - 1):
            barrier = self.model.environment.getBarrier(self.model.rows - 2,column,"down")
            if barrier != "wall":
                exits.append((self.model.rows - 1, column))
        # Lado izquierdo
        for row in range(1, self.model.rows - 1):
            barrier = self.model.environment.getBarrier(row,1,"left")
            if barrier != "wall":
                exits.append((row, 0))
        # Lado derecho
        for row in range(1, self.model.rows - 1):
            barrier = self.model.environment.getBarrier(row, self.model.columns - 2, "right")
            if barrier != "wall":
                exits.append((row, self.model.columns - 1))
        return exits

    #elegir la salida más barata con el mismo A* de obtainRoute()
    def planRescueRoute(self):
        if self.carryingVictim is None:
            return None

        exits = self.getRescueExits()
        bestRouteData = None
        bestExit = None

        for exitRow, exitColumn in exits:
            routeData = self.obtainRoute(
                exitRow,
                exitColumn,
                carryingVictim=True
            )
            if routeData is None:
                continue
            route, cost, actions = routeData
            if (bestRouteData is None or cost < bestRouteData[1]):
                bestRouteData = routeData
                bestExit = (exitRow, exitColumn)
        if bestRouteData is None:
            self.rescueExit = None
            return None
        route, cost, actions = bestRouteData
        self.rescueExit = bestExit
        self.objective = bestExit
        self.route = route
        self.routeCost = cost
        self.routeActions = actions
        return bestRouteData

    #Calcular con A* la ruta hacia self.objective y guardarla, sin ejecutar movimientos ni tocar actionQueue
    def planRouteToObjective(self):
        if self.objective is None:
            return None

        objectiveRow, objectiveColumn = self.objective
        route_data = self.obtainRoute(objectiveRow, objectiveColumn)
        if route_data is None:
            self.route = None
            self.routeCost = None
            self.routeActions = None
            return None

        route, cost, actions = route_data
        self.route = route
        self.routeCost = cost
        self.routeActions = actions
        return route_data

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

    #Liberar el objetivo y plan actual del bombero, incluyendo la asignación guardada en POI o FireObjective
    def _clearFirefighterObjective(self):
        objective_position = self.objective
        if objective_position is not None:
            for poi in self.model.pois:
                if (
                    poi.active
                    and (poi.row, poi.column) == objective_position
                    and poi.assigned_to == self.unique_id
                ):
                    poi.assigned_to = None

            for fire_objective in self.model.getActiveFireObjectives():
                if (
                    (fire_objective.row, fire_objective.column) == objective_position
                    and fire_objective.assigned_to == self.unique_id
                ):
                    fire_objective.assigned_to = None

        self.objective = None
        self.route = None
        self.routeCost = None
        self.routeActions = None
        self.actionQueue.clear()

    #Noquear al bombero alcanzado por fuego, perder víctima cargada y moverlo a una salida disponible
    def knockout(self):
        if self.knockedDown:
            return

        self.knockedDown = True

        if self.carryingVictim is not None:
            victim = self.carryingVictim
            victim.active = False
            victim.revealed = True
            victim.assigned_to = None
            victim.lost = True
            self.carryingVictim = None

        self.rescueExit = None
        self._clearFirefighterObjective()

        exits = self.getRescueExits()
        if exits:
            exit_row, exit_column = exits[0]
            self.model.FigthersGrid.move_agent(self, (exit_column, exit_row))
            self.row = exit_row
            self.column = exit_column

    #Convertir self.route (calculada por A*) en acciones pendientes; no ejecuta ni consume AP
    def generateActionQueue(self):
        if not self.routeActions:
            self.actionQueue = deque()
            return self.actionQueue

        self.actionQueue = deque(self.routeActions)

        return self.actionQueue

    #Ejecutar actionQueue mientras haya acciones y AP suficientes; lo no ejecutado permanece pendiente
    def executeActionQueue(self):
        while self.actionQueue and self.action_points > 0:

            action = self.actionQueue[0]
            actionType = action[0]

            if actionType == "EXTINGUISH":
                row, column = action[1:3] #slice con posición del fuego
                if len(action) > 3: #quitar fuego por completo de acuerdo a acción
                    removeFire = action[3]
                else: #solo convertir a humo de acuerdo a acción
                    removeFire = False
                if not self.extinguishFire(row,column,removeFire):
                    break
                self.actionQueue.popleft() #sí pudo apagar el fuego, se elimina de la queue

                #el fuego ya desapareció, el objetivo terminó
                if (self.objective == (row, column) and self.model.fireCells[row, column] == 0):
                    self.objective = None
                    self.route = None
                    self.routeCost = None
                    self.routeActions = None

                    #eliminar fuego de fuegos activos (tomando que la celda ya no tiene estado = 2)
                    self.model.getActiveFireObjectives()
                    self.actionQueue.clear() #liberar queue de acciones del objetivo
                continue

            # Abrir puerta
            if actionType == "useDoor":
                row, column, direction = action[1:4]

                # La acción debe ejecutarse desde la celda para la que fue planeada
                if (self.row, self.column) != (row, column):
                    break

                barrier = self.model.environment.getBarrier(row,column,direction)

                # La puerta sigue cerrada: abrirla y gastar AP
                if barrier == "closedDoor":
                    if USE_DOOR > self.action_points:
                        break

                    self.model.environment.toggle_door(
                        row,
                        column,
                        direction
                    )

                    self.action_points -= USE_DOOR
                    self.actionQueue.popleft()
                    continue

                # Si alguien ya abrió o destruyó la puerta,
                # esta acción ya no es necesaria
                elif barrier in ("openedDoor", None):
                    self.actionQueue.popleft()
                    continue

                # Si ahora hay otra barrera, el plan ya no es válido
                else:
                    break
            # Dañar pared
            if actionType == "damageWall":
                row, column, direction, plannedWallState = action[1:5]

                # La acción debe ejecutarse desde la celda para la que fue planeada
                if (self.row, self.column) != (row, column):
                    break

                currentWallState = getattr(
                    self.model.environment.walls[row][column],
                    direction
                )

                # Si la pared ya fue destruida, esta acción ya no es necesaria
                if currentWallState == 0:
                    self.actionQueue.popleft()
                    continue

                # Cada golpe a la pared cuesta DAMAGE_WALL AP
                if DAMAGE_WALL > self.action_points:
                    break

                self.model.environment.damage_wall(row,column,direction)
                self.action_points -= DAMAGE_WALL

                # Revisar el estado DESPUÉS del golpe
                currentWallState = getattr(
                    self.model.environment.walls[row][column],
                    direction
                )

                # Solo quitamos la acción cuando la pared quedó destruida
                if currentWallState == 0:
                    self.actionQueue.popleft()

                continue

            if actionType == "moveSpace":
                cost = MOVE_SPACE

            elif actionType == "moveSpaceWithFire":
                cost = MOVE_SPACE_W_FIRE

            elif actionType == "moveSpaceCarryingVictim":
                cost = CARRY_VICTIM

            else:
                break

            row, column, direction = action[1:4]

            # La acción debe ejecutarse desde la celda para la que fue planeada
            if (self.row, self.column) != (row, column):
                break

            drow, dcolumn = self.model.environment.NEIGHBOR_OFFSETS[direction]
            newRow = row + drow
            newColumn = column + dcolumn

            #revisar si apareció un fuego en siguiente casilla y reaccionar
            destinationHasFire = (self.model.fireCells[newRow, newColumn] == 2)
            #tenía planeado moverse ahí sin haber fuego
            unexpectedFire = (destinationHasFire and actionType in ("moveSpace", "moveSpaceCarryingVictim"))

            if unexpectedFire:
                #esperar si no hay AP suficientes para eliminar completamente el fuego
                if self.action_points < REMOVE_FIRE:
                    break
                #apagar el fuego y continuar con la cola de forma normal
                if not self.extinguishFire(newRow,newColumn,removeFire=True):
                    break
                continue

            if actionType == "moveSpace":
                cost = MOVE_SPACE
            elif actionType == "moveSpaceWithFire":
                cost = MOVE_SPACE_W_FIRE
            else:
                cost = CARRY_VICTIM

            # No hay suficientes AP
            if cost > self.action_points:
                break

            # No se puede terminar el turno sobre fuego
            if (
                actionType == "moveSpaceWithFire"
                and self.action_points - cost == 0
            ):
                break

            wasCarryingVictim = self.carryingVictim is not None

            # moveTo todavía valida límites, paredes y puertas
            if not self.moveTo(newRow, newColumn):
                break

            self.action_points -= cost
            self.actionQueue.popleft()

            #si este movimiento descubrió una víctima, investigatePOI() ya calculó la ruta de rescate y se sustituye la cola anterior por ese nuevo plan
            if (not wasCarryingVictim and self.carryingVictim is not None):
                self.generateActionQueue()
                continue

            reachedExterior = (
                newRow == 0
                or newRow == self.model.rows - 1
                or newColumn == 0
                or newColumn == self.model.columns - 1
            )
            if actionType == "moveSpaceCarryingVictim" and reachedExterior:
                victim = self.carryingVictim
                victim.rescued = True
                victim.active = False
                victim.assigned_to = None
                self.carryingVictim = None
                self.rescueExit = None
                self.objective = None
                self.route = None
                self.routeCost = None
                self.routeActions = None
                self.actionQueue.clear()
                
        return self.actionQueue

    def getNeighbourMoves(self, row, column, carryingVictim=False): #función para obtener el costo y acciones de moverse de su celda en cada una de las cuatro direcciones
        neighbors = []
        directions = ["up", "down", "left", "right"]
        for direction in directions:
            drow, dcolumn = self.model.environment.NEIGHBOR_OFFSETS[direction] #diferencia de celda según dirección de mov
            neighRow = row + drow #número de fila del vecino
            neighColumn = column + dcolumn #número de columna del vecino
            if (0 <= neighRow < self.model.rows and 0 <= neighColumn < self.model.columns): #verificar que casilla entre en tablero
                cost, actions = self.cellMoveCost(row, column, direction, carryingVictim) #obtener costo de acciones para moverse a una casilla
                if cost is not None:
                    neighbors.append((neighRow, neighColumn, cost, actions)) #guardarlo en arreglo de vecinos
        return neighbors #devolver arreglo con costo y acciones de los 4 vecinos

    def cellMoveCost(self, row, column, direction, carryingVictim=False): #función para obtener costo de acciones para moverse a una casilla
        cost = 0 #costo de acciones
        actions = [] #acciones a guardar para ese movimiento
        drow, dcolumn = self.model.environment.NEIGHBOR_OFFSETS[direction] #diferencia de celda según dirección de mov
        newRow = row + drow #nuevo número de fila
        newColumn = column + dcolumn #nuevo número de columna
        if not (0 <= newRow < self.model.rows and 0 <= newColumn < self.model.columns): #verificar que casilla entre en tablero
            return None, []
        #si carga una víctima nunca puede ser transportada hacia una celda con fuego
        if (
            carryingVictim
            and self.model.fireCells[newRow, newColumn] == 2
        ):
            return None, []
        #identificar si se está pasando de adentro de la casa a afuera (necesario para rescatar a la víctima)
        currentOutside = (
            row == 0
            or row == self.model.rows - 1
            or column == 0
            or column == self.model.columns - 1
        )

        newOutside = (
            newRow == 0
            or newRow == self.model.rows - 1
            or newColumn == 0
            or newColumn == self.model.columns - 1
        )
        barrier = self.model.environment.getBarrier(row, column, direction)
        #si está cargando una víctima, no rompe una pared exterior para salir para evitar daño excesivo
        if (
            carryingVictim
            and currentOutside != newOutside
            and barrier == "wall"
        ):
            return None, []
        
        if barrier is None or barrier == "openedDoor": #sin barrera o puerta abierta
            if carryingVictim:
                cost += CARRY_VICTIM
                actions.append(
                    ("moveSpaceCarryingVictim", row, column, direction))
            elif self.model.fireCells[newRow, newColumn] == 2: #revisar si hay fuego en nueva celda para sumar costo correcto
                cost += MOVE_SPACE_W_FIRE #añadir al costo total
                actions.append(
                    ("moveSpaceWithFire", row, column, direction)) #añadir acción al arreglo
            else: #no hay fuego, diferente costo
                cost += MOVE_SPACE
                actions.append(
                    ("moveSpace", row, column, direction))

        elif barrier == "closedDoor":
            cost += USE_DOOR
            actions.append(
                ("useDoor", row, column, direction))
            if carryingVictim:
                cost += CARRY_VICTIM
                actions.append(
                    ("moveSpaceCarryingVictim", row, column, direction))
            elif self.model.fireCells[newRow, newColumn] == 2:
                cost += MOVE_SPACE_W_FIRE
                actions.append(
                    ("moveSpaceWithFire", row, column, direction))
            else:
                cost += MOVE_SPACE
                actions.append(
                    ("moveSpace", row, column, direction))

        elif barrier == "wall":
            wallState = getattr(
                self.model.environment.walls[row][column], direction)
            cost += DAMAGE_WALL * wallState
            actions.append(
                ("damageWall", row, column, direction, wallState))
            if carryingVictim:
                cost += CARRY_VICTIM
                actions.append(
                    ("moveSpaceCarryingVictim", row, column, direction))
            elif self.model.fireCells[newRow, newColumn] == 2:
                cost += MOVE_SPACE_W_FIRE
                actions.append(
                    ("moveSpaceWithFire", row, column, direction))
            else:
                cost += MOVE_SPACE
                actions.append(
                    ("moveSpace", row, column, direction))

        return cost, actions #devolver costo y acciones de movimiento de celda

    #función de heurística para usar en algoritmo A*: f = g + h
    def heuristicEstimation(self, row, column, objectiveRow, objectiveColumn):
        return (abs(row - objectiveRow) + abs(column - objectiveColumn)) #diferencia absoluta entre casilla y objetivo

    def obtainRoute(self, objectiveRow, objectiveColumn, carryingVictim=False): #algoritmo para obtener ruta con su costo basado en algoritmo A*
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
            currentTotalCost, currentPosition = heapq.heappop(pending) #sacar casilla de menor costo primero
            if currentPosition == objective: #ya llegó a la casilla objetivo
                break
            currentRow, currentColumn = currentPosition
            neighbors = self.getNeighbourMoves(currentRow, currentColumn, carryingVictim) #obtener vecinos de la casilla actual con función
            for neighborRow, neighborColumn, moveCost, actions in neighbors:
                neighbor = neighborRow, neighborColumn #posición del vecino
                gCost = moveCost + gCosts[currentPosition] #para cada vecino, obtener el costo acumulado
                hCost = self.heuristicEstimation(neighborRow, neighborColumn, objectiveRow, objectiveColumn) #obtener costo heurístico

                #no se había llegado antes a esa casilla o se encontró un menor costo para ella
                if neighbor not in gCosts or gCost < gCosts[neighbor]:
                    gCosts[neighbor] = gCost #actualizar costo acumulado/real g de casilla
                    origin[neighbor] = currentPosition #añadir casilla previa para llegar a ella
                    neighSumCost = gCost + hCost #real + heurística = costo f
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
        for i in range(len(route) - 1): #recorrer hasta penúltima casilla
            firstPosition = route[i]
            secondPosition = route[i + 1]
            firstRow, firstColumn = firstPosition
            secondRow, secondColumn = secondPosition
            direction = self.getDirection(firstRow, firstColumn, secondRow, secondColumn)
            cost, movements = self.cellMoveCost(firstRow, firstColumn, direction, carryingVictim) #obtener acciones/movimientos
            routeMovements.extend(movements) #añadirlo a movimientos de la ruta

        return route, gCosts[objective], routeMovements #regresar ruta, costo y movimientos

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

        # POIs iniciales de ejemplo (row, column); la prioridad se decide según el tipo centralizado en OBJECTIVE_PRIORITY
        self.pois = []
        initialPOIs = [
            (2, 4),
            (5, 1),
            (5, 8),
        ]
        for row, column in initialPOIs:
            poi_type = self.drawPOIType()
            self.addPOI(row, column, poi_type, OBJECTIVE_PRIORITY.get(poi_type, 0))

        # Objetivos de incendio para la subasta, sincronizados de forma perezosa contra fireCells (ver getActiveFireObjectives)
        self.fireObjectives = {}

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
    def addPOI(self, row, column, type, priority=0):
        if not (0 <= row < self.rows and 0 <= column < self.columns):
            return False

        for poi in self.pois:
            if poi.active and poi.row == row and poi.column == column and poi.type == type:
                return False

        self.pois.append(POI(row, column, type, priority))
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
        poi.assigned_to = None

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
            self.addPOI(row,column,poi_type,OBJECTIVE_PRIORITY.get(poi_type, 0))
            new_poi = self.pois[-1]

            #si aparece debajo de un bombero se revela
            for firefighter in self.firefighters:
                if (firefighter.row == row and firefighter.column == column):
                    self.investigatePOI(new_poi,firefighter)
                    break    

    #devolver los objetivos de incendio activos a partir de fireCells (solo fuego, no humo) y conservar su asignación
    def getActiveFireObjectives(self):
        active_positions = {
            (row, column)
            for row in range(self.rows)
            for column in range(self.columns)
            if self.fireCells[row, column] == 2
        }

        for position in list(self.fireObjectives):
            if position not in active_positions:
                del self.fireObjectives[position]

        for row, column in active_positions:
            if (row, column) not in self.fireObjectives:
                self.fireObjectives[(row, column)] = FireObjective(row, column)

        return list(self.fireObjectives.values())

    #Revelar un POI oculto; una alarma falsa se retira del tablero, una víctima permanece activa hasta ser rescatada
    def investigatePOI(self, poi, firefighter=None):
        if not poi.active or poi.revealed:
            return False

        poi.revealed = True

        # Alarma falsa: simplemente desaparece
        if poi.type == "falseAlarm":
            self.removePOI(poi)
            return True

        # Víctima: se asigna automáticamente al bombero que la descubrió
        if poi.type == "victim" and firefighter is not None:

            # Por ahora cada bombero solo puede cargar una víctima
            if firefighter.carryingVictim is None:

                # Si la víctima estaba asignada a otro bombero por una subasta
                # anterior, cancelar ese objetivo
                for other_firefighter in self.firefighters:
                    if (
                        other_firefighter is not firefighter
                        and other_firefighter.objective == (poi.row, poi.column)
                    ):
                        other_firefighter.objective = None
                        other_firefighter.route = None
                        other_firefighter.routeCost = None
                        other_firefighter.routeActions = None
                        other_firefighter.actionQueue.clear()

                poi.assigned_to = firefighter.unique_id
                firefighter.carryingVictim = poi
                firefighter.rescueExit = None

                # El objetivo anterior termina: ahora su prioridad es rescatar
                firefighter.objective = None
                firefighter.route = None
                firefighter.routeCost = None
                firefighter.routeActions = None
                firefighter.planRescueRoute()

        return True

    #POIs (víctima/alarma falsa) e incendios activos son objetivos de la subasta, los objetivos ya asignados no vuelven a entrar en la ronda
    def runPOIAuction(self):
        #obtener prioridad (POIs ocultos se tratan como prioritarios (víctimas))
        def getAuctionPriority(objective):
            if (isinstance(objective, POI) and not objective.revealed):
                return OBJECTIVE_PRIORITY["victim"]
            return objective.priority

        # Obtener todos los objetivos todavía no asignados
        candidate_objectives = []
        for objective in (self.getActivePOIs() + self.getActiveFireObjectives()):
            if objective.assigned_to is None:
                candidate_objectives.append(objective)

        # Ordenar por prioridad
        candidate_objectives.sort(key=getAuctionPriority, reverse=True)

        assigned_firefighters = set()
        results = []

        for objective in candidate_objectives:
            available_firefighters = [
                firefighter for firefighter in self.firefighters
                if firefighter.unique_id not in assigned_firefighters
                and firefighter.objective is None
                and not firefighter.knockedDown #un bombero noqueado no participa hasta recuperarse en su siguiente turno
            ]

            if not available_firefighters:
                break

            bids = []
            for firefighter in available_firefighters:
                bid_data = firefighter.calculateBid(objective)

                if bid_data is not None:
                    cost, route, actions = bid_data

                    bids.append(
                        (
                            cost,
                            firefighter.unique_id,
                            firefighter,
                            route,
                            actions
                        )
                    )

            if not bids:
                continue

            winning_bid, _, winner, winning_route, winning_actions = min(
                bids,
                key=lambda offer: (offer[0], offer[1])
            )

            if winner.setObjectivePOI(objective):
                objective.assigned_to = winner.unique_id
                assigned_firefighters.add(winner.unique_id)

                winner.route = winning_route
                winner.routeCost = winning_bid
                winner.routeActions = winning_actions

                results.append({
                    "poi": objective,
                    "firefighter": winner,
                    "bid": winning_bid,
                    "route": winning_route,
                    "routeCost": winning_bid,
                    "actions": winning_actions
                })

        return results

    def updateObjectiveAssignments(self):
        #Sincronizar objetivos de incendio activos contra fireCells antes de validar asignaciones
        active_fire_objectives = {
            (objective.row, objective.column): objective
            for objective in self.getActiveFireObjectives()
        }
        active_pois = {
            (poi.row, poi.column): poi
            for poi in self.getActivePOIs()
        }

        for firefighter in self.firefighters:
            # Un bombero cargando una víctima sigue en ruta de rescate; no es parte de la subasta
            if firefighter.carryingVictim is not None:
                continue

            if firefighter.objective is None:
                continue

            poi = active_pois.get(firefighter.objective)
            fireObjective = active_fire_objectives.get(firefighter.objective)

            stillValid = (
                (poi is not None and poi.assigned_to == firefighter.unique_id)
                or (fireObjective is not None and fireObjective.assigned_to == firefighter.unique_id)
            )

            if stillValid:
                continue

            # El objetivo fue completado o ya no existe: liberar al bombero para la siguiente subasta
            firefighter.objective = None
            firefighter.route = None
            firefighter.routeCost = None
            firefighter.routeActions = None
            firefighter.actionQueue.clear()

    def runObjectiveCycle(self):
        #sincronizar objetivos y liberar bomberos cuyo objetivo ya no es válido
        self.updateObjectiveAssignments()

        #la subasta existente sigue siendo quien determina nuevas asignaciones
        results = self.runPOIAuction()

        #generar actionQueue solo para los objetivos recién asignados (la subasta ya calculó ruta, costo y acciones)
        for result in results:
            result["firefighter"].generateActionQueue()

        return results

    def resolveVictimsInFire(self):
        for poi in self.pois: #recorrer todos los POIs
            if not poi.active:
                continue
            if self.fireCells[poi.row, poi.column] != 2: #no hay fuego en casilla
                continue
            
            #si hay/llegó fuego a la casilla, se desactiva el POI
            poi.revealed = True
            poi.active = False
            poi.assigned_to = None
            #si es víctima: perdida
            if poi.type == "victim":
                poi.lost = True
                #dejar de cargarla y eliminar objetivo de rescatarla/sacarla
                for firefighter in self.firefighters:
                    if firefighter.carryingVictim is poi:
                        firefighter.carryingVictim = None
                        firefighter.rescueExit = None
                        firefighter.objective = None
                        firefighter.route = None
                        firefighter.routeCost = None
                        firefighter.routeActions = None
                        firefighter.actionQueue.clear()
    
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
        #evaluar objetivos y agentes libres, realizar nuevas subastas
        self.runObjectiveCycle()

        firefighter.startTurn() #sumar APs
        firefighter.executeActionQueue() #ejecutar su queue de acciones para objetivo
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
