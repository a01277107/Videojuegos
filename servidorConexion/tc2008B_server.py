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
#para probar
test_step = 0


def get_barrier_states():
    wall_states = []
    door_states = []
    processed_edges = set()
    directions = ("up", "down", "left", "right")

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

                if edge_key in processed_edges:
                    continue

                processed_edges.add(edge_key)

                wall_state = getattr(
                    model.environment.walls[row][column],
                    direction
                )
                door_state = getattr(
                    model.environment.doors[row][column],
                    direction
                )

                if wall_state > 0:
                    wall_states.append({
                        "row": row,
                        "column": column,
                        "direction": direction,
                        "state": wall_state,
                    })
                elif door_state > 0:
                    door_states.append({
                        "row": row,
                        "column": column,
                        "direction": direction,
                        "state": door_state,
                    })

    return wall_states, door_states


def get_board_state(last_fireAdvance=None):
    #Prepara formato tipo json con la información que se envía a Unity
    wall_states, door_states = get_barrier_states()
    poi_states = []
    victim_visual_index = 0
    for poi_id, poi in enumerate(model.pois):
        visual_index = -1
        if poi.type == "victim":
            visual_index = victim_visual_index
            victim_visual_index += 1

        poi_states.append({
            "id": poi_id,
            "row": poi.row,
            "column": poi.column,
            "type": poi.type,
            "active": poi.active,
            "revealed": poi.revealed,
            "visualIndex": visual_index,
        })

    firefighter_states = []
    for player, firefighter in enumerate(model.firefighters):
        firefighter_states.append({
            "player": player,
            "row": firefighter.row,
            "column": firefighter.column,
        })

    state = {
        "rows": model.rows,
        "columns": model.columns,
        "turn": turn,
        #Se deben aplanar las matrices como lista para el formato ([row, column] es row * columns + column)
        "fires": model.fireCells.flatten().tolist(),
        "walls": wall_states,
        "doors": door_states,
        "pois": poi_states,
        "firefighters": firefighter_states,
    }
    #obtener las coordenadas donde cayó el fireAdvance
    if last_fireAdvance is not None:
        state["advancedRow"] = last_fireAdvance[0]
        state["advancedColumn"] = last_fireAdvance[1]
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
        #actualmente la única ruta de request "state" debe ser obtener el estado del tablero
        if self.path not in ("/", "/state"):
            self._send_json({"error": "Ruta no encontrada"}, status=404)
            return
        #Consultar el estado del tablero
        self._send_json(get_board_state())

    def do_POST(self):
        global model, turn, test_step #para probar
        #obtener tamaño de post de unity
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length: #si existe, recibir los bytes de respuesta (rfile)
            self.rfile.read(content_length)

        #para pruebas: ruta de post "step" que ejecuta el advanceFire
        if self.path in ("/", "/step"):
            advanced_cell = model.advanceFire() #generar advanceFire
            turn += 1
            self._send_json(get_board_state(advanced_cell)) #obtener nuevo estado del tablero
            return

        #ruta temporal para probar actualización de elementos en Unity
        if self.path == "/test":
            if test_step == 0:
                #dañar una pared intacta
                model.environment.damage_wall(4, 2, "right")
            elif test_step == 1:
                #volver a dañar la misma pared para destruirla
                model.environment.damage_wall(4, 2, "right")
            elif test_step == 2:
                #abrir una puerta cerrada
                model.environment.toggle_door(4, 4, "down")
            elif test_step == 3:
                #mover el primer bombero a otra casilla
                firefighter = model.firefighters[0]
                model.FigthersGrid.move_agent(
                    firefighter,
                    (0, 7)
                )
                firefighter.row = 7
                firefighter.column = 0
            elif test_step == 4:
                #revelar el primer POI sin eliminarlo
                model.pois[0].revealed = True
            elif test_step == 5:
                #convertirlo temporalmente en falsa alarma
                model.pois[0].type = "falseAlarm"
            elif test_step == 6:
                #retirar el POI
                model.pois[0].active = False
            else:
                #reiniciar todo para volver a hacer la prueba
                model = FireRescueModel(COLUMNS, ROWS, NUM_PLAYERS)
                test_step = 0
                self._send_json(get_board_state())
                return
            test_step += 1
            self._send_json(get_board_state())
            return
        
        #ruta de post "reset" que permite reiniciar simulación
        if self.path == "/reset":
            test_step = 0 #para probar
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
