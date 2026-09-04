"""Este archivo tiene el mismo contenido que el notebook "fireRescueSimulation.ipynb" (lógica de simulación de Flashpoint Firerescue),
pero este archivo puede ser importado por el servidor para que pueda tener su propio modelo y variables a usar cuando Unity le haga requests.
"""

from dataclasses import dataclass

import numpy as np
from mesa import Model
from mesa.space import SingleGrid


@dataclass
class CellWalls:
    # 2 = intacta, 1 = dañada, 0 = destruida/inexistente
    up: int = 0
    down: int = 0
    left: int = 0
    right: int = 0


@dataclass
class CellDoors:
    # 2 = cerrada, 1 = abierta, 0 = destruida/inexistente
    up: int = 0
    down: int = 0
    left: int = 0
    right: int = 0


class EnvironmentManager(Model):
    OPPOSITE_DIRECTIONS = {
        "up": "down",
        "down": "up",
        "left": "right",
        "right": "left",
    }
    NEIGHBOR_OFFSETS = {
        "up": (-1, 0),
        "down": (1, 0),
        "left": (0, -1),
        "right": (0, 1),
    }

    def __init__(self, columns, rows, wall_layout=None, door_layout=None):
        super().__init__()
        self.columns = columns
        self.rows = rows
        self._total_damage_markers = 0
        self.walls = [[CellWalls() for _ in range(columns)] for _ in range(rows)]
        self.doors = [[CellDoors() for _ in range(columns)] for _ in range(rows)]

        if wall_layout:
            self.load_wall_layout(wall_layout)
        if door_layout:
            self.load_door_layout(door_layout)

    def load_wall_layout(self, wall_layout):
        for wall in wall_layout:
            self._set_wall(
                wall["row"], wall["column"], wall["direction"], wall["state"]
            )

    def _set_wall(self, row, column, direction, value):
        setattr(self.walls[row][column], direction, value)
        drow, dcolumn = self.NEIGHBOR_OFFSETS[direction]
        nrow, ncolumn = row + drow, column + dcolumn
        if 0 <= nrow < self.rows and 0 <= ncolumn < self.columns:
            opposite = self.OPPOSITE_DIRECTIONS[direction]
            setattr(self.walls[nrow][ncolumn], opposite, value)

    def load_door_layout(self, door_layout):
        for door in door_layout:
            self._set_door(
                door["row"], door["column"], door["direction"], door["state"]
            )

    def _set_door(self, row, column, direction, value):
        setattr(self.walls[row][column], direction, 0)
        setattr(self.doors[row][column], direction, value)
        drow, dcolumn = self.NEIGHBOR_OFFSETS[direction]
        nrow, ncolumn = row + drow, column + dcolumn
        if 0 <= nrow < self.rows and 0 <= ncolumn < self.columns:
            opposite = self.OPPOSITE_DIRECTIONS[direction]
            setattr(self.walls[nrow][ncolumn], opposite, 0)
            setattr(self.doors[nrow][ncolumn], opposite, value)

    @property
    def total_damage_markers(self):
        return self._total_damage_markers

    def damage_wall(self, row, column, direction):
        if direction not in self.NEIGHBOR_OFFSETS:
            raise ValueError(f"Dirección inválida: {direction}")

        cell = self.walls[row][column]
        current_value = getattr(cell, direction)
        if current_value > 0:
            setattr(cell, direction, current_value - 1)
            self._total_damage_markers += 1

        drow, dcolumn = self.NEIGHBOR_OFFSETS[direction]
        nrow, ncolumn = row + drow, column + dcolumn
        if 0 <= nrow < self.rows and 0 <= ncolumn < self.columns:
            opposite = self.OPPOSITE_DIRECTIONS[direction]
            neighbor = self.walls[nrow][ncolumn]
            neighbor_value = getattr(neighbor, opposite)
            if neighbor_value > 0:
                setattr(neighbor, opposite, neighbor_value - 1)

    def toggle_door(self, row, column, direction):
        current_value = getattr(self.doors[row][column], direction)
        if current_value == 0:
            raise ValueError("No existe una puerta en esa posición")
        new_value = 1 if current_value == 2 else 2
        setattr(self.doors[row][column], direction, new_value)

        drow, dcolumn = self.NEIGHBOR_OFFSETS[direction]
        nrow, ncolumn = row + drow, column + dcolumn
        if 0 <= nrow < self.rows and 0 <= ncolumn < self.columns:
            opposite = self.OPPOSITE_DIRECTIONS[direction]
            setattr(self.doors[nrow][ncolumn], opposite, new_value)

    def destroy_door(self, row, column, direction):
        setattr(self.doors[row][column], direction, 0)
        drow, dcolumn = self.NEIGHBOR_OFFSETS[direction]
        nrow, ncolumn = row + drow, column + dcolumn
        if 0 <= nrow < self.rows and 0 <= ncolumn < self.columns:
            opposite = self.OPPOSITE_DIRECTIONS[direction]
            setattr(self.doors[nrow][ncolumn], opposite, 0)

    def getBarrier(self, row, column, direction):
        if getattr(self.walls[row][column], direction) > 0:
            return "wall"
        if getattr(self.doors[row][column], direction) == 2:
            return "closedDoor"
        if getattr(self.doors[row][column], direction) == 1:
            return "openedDoor"
        return None


initial_wall_layout = (
    [{"row": 0, "column": column, "direction": "down", "state": 2} for column in range(1, 9)]
    + [{"row": row, "column": 0, "direction": "right", "state": 2} for row in range(1, 7)]
    + [{"row": 6, "column": column, "direction": "down", "state": 2} for column in range(1, 9)]
    + [{"row": row, "column": 8, "direction": "right", "state": 2} for row in range(1, 7)]
    + [{"row": 4, "column": column, "direction": "down", "state": 2} for column in range(1, 9)]
    + [{"row": row, "column": 7, "direction": "right", "state": 2} for row in range(5, 7)]
    + [
        {"row": 3, "column": 6, "direction": "right", "state": 2},
        {"row": 4, "column": 2, "direction": "right", "state": 2},
        {"row": 4, "column": 6, "direction": "right", "state": 2},
        {"row": 3, "column": 2, "direction": "right", "state": 2},
        {"row": 5, "column": 5, "direction": "right", "state": 2},
        {"row": 6, "column": 5, "direction": "right", "state": 2},
    ]
    + [{"row": row, "column": 3, "direction": "right", "state": 2} for row in range(1, 3)]
    + [{"row": row, "column": 5, "direction": "right", "state": 2} for row in range(1, 3)]
    + [{"row": 3, "column": column, "direction": "up", "state": 2} for column in range(3, 9)]
)


initial_door_layout = (
    [
        {"row": 1, "column": 3, "direction": "right", "state": 2},
        {"row": 2, "column": 5, "direction": "right", "state": 2},
        {"row": 3, "column": 2, "direction": "right", "state": 2},
        {"row": 4, "column": 4, "direction": "down", "state": 2},
        {"row": 4, "column": 6, "direction": "right", "state": 2},
        {"row": 3, "column": 8, "direction": "up", "state": 2},
        {"row": 6, "column": 5, "direction": "right", "state": 2},
        {"row": 6, "column": 7, "direction": "right", "state": 2},
    ]
    + [
        {"row": 0, "column": 6, "direction": "down", "state": 2},
        {"row": 3, "column": 1, "direction": "left", "state": 2},
        {"row": 6, "column": 3, "direction": "down", "state": 2},
        {"row": 4, "column": 8, "direction": "right", "state": 2},
    ]
)


class FireRescueModel(Model):
    def __init__(self, columns, rows, num_players):
        super().__init__()
        self.columns = columns
        self.rows = rows
        self.num_players = num_players
        self.FigthersGrid = SingleGrid(columns, rows, torus=False)
        self.fireCells = np.zeros((rows, columns), dtype=int)
        self.environment = EnvironmentManager(
            columns, rows, initial_wall_layout, initial_door_layout
        )

        initial_fires = [
            (2, 2), (2, 3), (3, 2), (3, 3), (3, 4),
            (3, 5), (4, 4), (5, 6), (5, 7), (6, 6),
        ]
        for row, column in initial_fires:
            self.fireCells[row, column] = 2

    def advanceFire(self):
        row = self.random.randrange(1, self.rows - 1)
        column = self.random.randrange(1, self.columns - 1)

        if self.fireCells[row, column] == 0:
            self.fireCells[row, column] = 2 if self.check_adjacentFires(row, column) else 1
        elif self.fireCells[row, column] == 1:
            self.fireCells[row, column] = 2
        elif self.fireCells[row, column] == 2:
            self.explosion(row, column)
        return row, column

    def check_adjacentFires(self, row, column):
        neighbors = [
            (row - 1, column, "up"),
            (row + 1, column, "down"),
            (row, column - 1, "left"),
            (row, column + 1, "right"),
        ]
        for neighbor_row, neighbor_column, direction in neighbors:
            if 0 <= neighbor_row < self.rows and 0 <= neighbor_column < self.columns:
                barrier = self.environment.getBarrier(row, column, direction)
                if self.fireCells[neighbor_row, neighbor_column] == 2 and barrier in (None, "openedDoor"):
                    return True
        return False

    def explosion(self, row, column):
        neighbors = [
            (row - 1, column, "up"),
            (row + 1, column, "down"),
            (row, column - 1, "left"),
            (row, column + 1, "right"),
        ]
        for neighbor_row, neighbor_column, direction in neighbors:
            barrier = self.environment.getBarrier(row, column, direction)
            if barrier == "wall":
                self.environment.damage_wall(row, column, direction)
            elif barrier == "closedDoor":
                self.environment.destroy_door(row, column, direction)
            else:
                if barrier == "openedDoor":
                    self.environment.destroy_door(row, column, direction)
                if 0 <= neighbor_row < self.rows and 0 <= neighbor_column < self.columns:
                    neighbor_state = self.fireCells[neighbor_row, neighbor_column]
                    if neighbor_state in (0, 1):
                        self.fireCells[neighbor_row, neighbor_column] = 2
                    elif neighbor_state == 2:
                        self.shockwave(neighbor_row, neighbor_column, direction)

    def shockwave(self, row, column, direction):
        drow, dcolumn = self.environment.NEIGHBOR_OFFSETS[direction]
        current_row = row
        current_column = column

        while True:
            barrier = self.environment.getBarrier(current_row, current_column, direction)
            if barrier == "wall":
                self.environment.damage_wall(current_row, current_column, direction)
                return
            if barrier == "closedDoor":
                self.environment.destroy_door(current_row, current_column, direction)
                return
            if barrier == "openedDoor":
                self.environment.destroy_door(current_row, current_column, direction)

            next_row = current_row + drow
            next_column = current_column + dcolumn
            if not (0 <= next_row < self.rows and 0 <= next_column < self.columns):
                return

            next_state = self.fireCells[next_row, next_column]
            if next_state in (0, 1):
                self.fireCells[next_row, next_column] = 2
                return

            current_row = next_row
            current_column = next_column
