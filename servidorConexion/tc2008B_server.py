"""Servidor HTTP que conecta el modelo de Mesa del archivo importable .py con Unity para manejar requests"""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import logging

#Importar modelo de "fire_rescue_model.py"
from fire_rescue_model import FireRescueModel

COLUMNS = 10
ROWS = 8
NUM_PLAYERS = 6

#Inicializar modelo/partida 1 sola vez
model = FireRescueModel(COLUMNS, ROWS, NUM_PLAYERS)
turn = 0


def get_barrier_states():
    wall_states = [] #arreglo con paredes
    door_states = [] #arreglo con puertas
    processed_edges = set() #set de llaves de barreras ya procesadas
    directions = ("up", "down", "left", "right")
    #crear llave única para cada barrera, importante para no duplicar (2 celdas comparten barrera) y agregar a set
    for row in range(model.rows):
        for column in range(model.columns):
            for direction in directions:
                if direction == "up":
                    edge_key = ("horizontal", row, column)
                elif direction == "down":
                    edge_key = ("horizontal", row + 1, column)
                elif direction == "left":
                    edge_key = ("vertical", row, column)
                else:
                    edge_key = ("vertical", row, column + 1)

                if edge_key in processed_edges: #si ya existe la llave, no hace nada
                    continue

                processed_edges.add(edge_key) #agregar la nueva llave

                wall_state = getattr( #obtener pared, estado y dirección
                    model.environment.walls[row][column],
                    direction
                )
                door_state = getattr( #obtener puerta, estado y dirección
                    model.environment.doors[row][column],
                    direction
                )

                if wall_state > 0: #sí hay una pared, se agrega a su arreglo
                    wall_states.append({
                        "row": row,
                        "column": column,
                        "direction": direction,
                        "state": wall_state,
                    })
                elif door_state > 0: #sí hay una puerta, se agrega a su arreglo
                    door_states.append({
                        "row": row,
                        "column": column,
                        "direction": direction,
                        "state": door_state,
                    })

    return wall_states, door_states  #devolver arreglos de paredes y puertas


def get_board_state():
    #Prepara formato tipo json con la información que se envía a Unity
    wall_states, door_states = get_barrier_states() #obtener barreras con función aparte
    poi_states = [] #arreglo para guardar los POIs
    victim_visual_index = 0

    for poi_id, poi in enumerate(model.pois): #recorrer todos los POIs del modelo
        visual_index = -1
        if poi.type == "victim": #si el POI es de tipo víctima
            visual_index = victim_visual_index #se le asigna el siguiente visual de víctima
            victim_visual_index += 1

        poi_states.append({ #agregar el nuevo POI con sus atributos al arreglo de POIs
            "id": poi_id,
            "row": poi.row,
            "column": poi.column,
            "type": poi.type,
            "active": poi.active,
            "revealed": poi.revealed,
            "visualIndex": visual_index,
        })

    firefighter_states = []
    for player, firefighter in enumerate(model.firefighters): #recorrer todos los bomberos del modelo
        firefighter_states.append({ #agregarlos al arreglo de bomberos con sus atributos
            "player": player,
            "row": firefighter.row,
            "column": firefighter.column,
        })

    state = { #estado del tablero completo (incluye los arreglos de todos los objetos y agentes)
        "rows": model.rows,
        "columns": model.columns,
        "turn": turn,
        "currentFirefighterIndex": model.current_firefighter_index,
        "gameOver": model.game_over,
        "gameResult": model.game_result if model.game_result is not None else "",
        "rescuedVictims": model.countRescuedVictims(),
        "lostVictims": model.countLostVictims(),
        "structuralDamage": model.environment.total_damage_markers,
        #Se debe aplanar la matriz de fuego como lista para el formato ([row, column] es row * columns + column)
        "fires": model.fireCells.flatten().tolist(),
        "walls": wall_states,
        "doors": door_states,
        "pois": poi_states,
        "firefighters": firefighter_states,
    }

    #devuelve el formato con la información del estado del tablero
    return state


class Server(BaseHTTPRequestHandler):
    def _send_json(self, data, status=200): #recibe data en los parámetros al llamar a la función
        #generar JSON con los datos y luego convertir a bytes para enviar por HTTP
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        #información de tipo de respuesta para Unity
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        #enviar los bytes de respuesta (wfile)
        self.wfile.write(body)

    def do_GET(self):
        #la ruta "state" obtiene el estado actual del tablero sin avanzar la simulación
        if self.path != "/state":
            self._send_json({"error": "Ruta no encontrada"}, status=404)
            return

        #Consultar el estado del tablero
        self._send_json(get_board_state())

    def do_POST(self):
        global model, turn

        #obtener tamaño de post de unity
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length: #si existe, recibir los bytes de respuesta (rfile)
            self.rfile.read(content_length)

        #ruta "step": ejecuta un turno completo del modelo de Mesa
        if self.path == "/step":
            #si la partida ya terminó, no se vuelve a modificar el modelo
            if not model.game_over:
                model.step()
                turn += 1

            #Unity recibe el estado completo resultante del step
            self._send_json(get_board_state())
            return

        #ruta "reset" que permite reiniciar simulación
        if self.path == "/reset":
            #vuelve a crear modelo/tablero/partida
            model = FireRescueModel(COLUMNS, ROWS, NUM_PLAYERS)
            turn = 0
            self._send_json(get_board_state())
            return

        #no debe de haber otra ruta post
        self._send_json({"error": "Ruta no encontrada"}, status=404)

    #imprimir rutas para debuggear
    def log_message(self, format, *args):
        logging.info("%s - %s", format % args)


#Definir función que inicia el servidor
def run(server_class=HTTPServer, handler_class=Server, port=8585):
    logging.basicConfig(level=logging.INFO)
    server_address = ("", port)
    httpd = server_class(server_address, handler_class)
    logging.info("Starting http://localhost:%s", port)

    try:
        httpd.serve_forever() #mantener servidor funcionando
    except KeyboardInterrupt: #detenerlo con crash
        pass

    httpd.server_close()
    logging.info("Stopped")


#ejecuta archivo al ser llamado directamente
if __name__ == "__main__":
    from sys import argv #obtener argumentos de la terminal
    run(port=int(argv[1])) if len(argv) == 2 else run() #correr si obtiene lo necesario (llamada y puerto)
