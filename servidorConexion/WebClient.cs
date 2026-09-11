// Cliente de Unity que hace requests y obtiene la información de la simulación para proyectarse en los gráficos de Unity

using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Networking;

using TMPro;

[Serializable]
public class BarrierState //clase para arreglo de barreras (puertas y paredes)
{
    public int row;
    public int column;
    public string direction;
    public int state;
}

[Serializable]
public class POIState //clase para arreglo de POIs
{
    public int id;
    public int row;
    public int column;
    public string type;
    public bool active;
    public bool revealed;
    public int visualIndex;
}

[Serializable]
public class FirefighterState //clase para arreglo de bomberos
{
    public int player;
    public int row;
    public int column;
}

//clase formada a partir del JSON que manda mesa del estado del tablero: guarda los arreglos de la clase de cada gameObject (objeto o agente)
[Serializable] //convertibles desde o hacia JSON
public class BoardState
{
    public int rows;
    public int columns;
    public int turn;
    public int currentFirefighterIndex;
    public bool gameOver;
    public string gameResult;
    public int rescuedVictims;
    public int lostVictims;
    public int structuralDamage;
    public int[] fires;
    public BarrierState[] walls;
    public BarrierState[] doors;
    public POIState[] pois;
    public FirefighterState[] firefighters;
}

public class WebClient : MonoBehaviour
{
    [Header("Servidor")] //títulos para variables en inspector
    [SerializeField] private string serverUrl = "http://localhost:8585";
    [Header("Tablero")]
    //variables de posición en tablero modificables en inspector
    [SerializeField] private Transform boardOrigin; //origen del tablero
    [SerializeField] private float cellSize = 10f; //tamaño de celdas en el tablero
    [SerializeField] private float effectHeight = 2f; //altura en 'y' de los fuegos/humos
    [SerializeField] private float poiHeight = 1f;
    [SerializeField] private float firefighterHeight = 1f;
    [SerializeField] private float wallHeight = 0f;
    [SerializeField] private float doorHeight = 0f;
    [Header("Prefabs")]
    [SerializeField] private GameObject firePrefab;
    [SerializeField] private GameObject smokePrefab;
    [SerializeField] private GameObject wallPrefab;
    [SerializeField] private GameObject damagedWallPrefab;
    [SerializeField] private GameObject closedDoorPrefab;
    [SerializeField] private GameObject openedDoorPrefab;
    [SerializeField] private GameObject poiPrefab;
    [SerializeField] private GameObject falseAlarmPrefab;
    [SerializeField] private GameObject[] victimPrefabs;
    [SerializeField] private GameObject[] firefighterPrefabs;
    [SerializeField] private Transform effectsContainer; //contenedor de fuegos y humos
    [SerializeField] private Transform barriersContainer;
    [SerializeField] private Transform poisContainer;
    [SerializeField] private Transform firefightersContainer;
    [SerializeField] private Vector3 prefabEulerRotation = Vector3.zero; //añadir los GameObjects sin rotación
    [SerializeField] private Vector3 poiEulerRotation = Vector3.zero;
    [SerializeField] private Vector3 firefighterEulerRotation = Vector3.zero;
    [SerializeField] private Vector3 horizontalBarrierEulerRotation = Vector3.zero;
    [SerializeField] private Vector3 verticalBarrierEulerRotation = new Vector3(0f, 90f, 0f);
    [SerializeField] private bool clearContainerOnStart = true;
    [Header("Canvas")] //elementos del Canvas de retroalimentación al usuario
    [SerializeField] private TMP_Text rescuedVictimsText;
    [SerializeField] private TMP_Text structuralDamageText;

    //diccionarios de los contenidos gráficos (GameObjects) que existen (objetos y agentes)
    private readonly Dictionary<int, EffectVisual> activeEffectVisuals =
        new Dictionary<int, EffectVisual>();
    private readonly Dictionary<string, BarrierVisual> activeBarrierVisuals =
        new Dictionary<string, BarrierVisual>();
    private readonly Dictionary<int, POIVisual> activePOIVisuals =
        new Dictionary<int, POIVisual>();
    private readonly Dictionary<int, GameObject> activeFirefighterVisuals =
        new Dictionary<int, GameObject>();
    private bool requestInProgress; //evita que se hagan dos petciciones simultáneas
    [SerializeField] private float stepInterval = 1.5f; //tiempo entre turnos (steps) de la simulación
    private bool simulationGameOver = false;
    private Coroutine simulationCoroutine;

    //clase para obtener/guardar contenido de las celdas en Unity
    private class EffectVisual
    {
        public int state; //representa si es fuego o humo
        public GameObject gameObject; //objeto creado en unity
    }

    private class BarrierVisual
    {
        public string type; //representa si es pared o puerta
        public int state; //representa su estado (dañanada, abierta, etc.)
        public GameObject gameObject;
    }

    private class POIVisual
    {
        public string type; //representa si es víctima o falsa alarma
        public bool revealed; //si ya fue revelado o no
        public int visualIndex;
        public GameObject gameObject;
    }

    private void Start() //Se llama automáticamente al inicio de la simulación
    { //quitar los objetos que existen antes de empezar simulación
        if (clearContainerOnStart && effectsContainer != null)
        { 
            foreach (Transform child in effectsContainer)
            {
                Destroy(child.gameObject);
            }
        }

        if (clearContainerOnStart && barriersContainer != null)
        {
            foreach (Transform child in barriersContainer)
            {
                Destroy(child.gameObject);
            }
        }

        if (clearContainerOnStart && poisContainer != null)
        {
            foreach (Transform child in poisContainer)
            {
                Destroy(child.gameObject);
            }
        }

        if (clearContainerOnStart && firefightersContainer != null)
        {
            foreach (Transform child in firefightersContainer)
            {
                Destroy(child.gameObject);
            }
        }

        // Obtener tablero inicial
        LoadInitialState();
    }

    //obtener estado inicial del tablero
    public void LoadInitialState()
    {
        if (!requestInProgress)
        {
            StartCoroutine(RequestState());
        }
    }

    //ejecutar un step completo de la simulación de Mesa y actualizar Unity
    public void StepSimulation()
    {
        if (!requestInProgress)
        {
            StartCoroutine(RequestStep());
        }
    }
    
    //iniciar simulación automática
    public void StartAutomaticSimulation()
    {
        if (simulationCoroutine == null) //evitar iniciar dos ciclos al mismo tiempo
        {
            simulationCoroutine = StartCoroutine(RunSimulation());
        }
    }


    //detener simulación automática manualmente
    public void StopAutomaticSimulation()
    {
        if (simulationCoroutine != null)
        {
            StopCoroutine(simulationCoroutine);
            simulationCoroutine = null;
        }
    }

    //ejecutar steps hasta que la partida termine
    private IEnumerator RunSimulation()
    {
        while (!simulationGameOver)
        {
            //esperar a que Mesa haga el step y Unity recibe el estado nuevo
            yield return StartCoroutine(RequestStep());
            //si el step terminó la partida, se detiene la corrutina para pedir actualizaciones
            if (simulationGameOver)
            {
                break;
            }
            //esperar antes del siguiente step para visualizarlo, con intervaloe establecido
            yield return new WaitForSeconds(stepInterval);
        }
        simulationCoroutine = null;
        Debug.Log("Simulación automática terminada.");
    }

    //reiniciar simulación
    public void ResetSimulation()
    {
        StopAutomaticSimulation(); //detener simulación y dar fin a juego
        simulationGameOver = false;
        if (!requestInProgress)
        {
            StartCoroutine(RequestReset());
        }
    }

    //corrutina para obtener el estado actual del tablero sin avanzar la simulación
    private IEnumerator RequestState()
    {
        requestInProgress = true;

        using (UnityWebRequest request = UnityWebRequest.Get(serverUrl + "/state"))
        { //asincrónico: manda la petición y retoma una vez que llega la respuesta
            yield return request.SendWebRequest(); //mandar petición
            HandleResponse(request); //manejar respuesta
        }

        requestInProgress = false;
    }

    //corrutina para ejecutar un step completo de Mesa y recibir el nuevo estado
    private IEnumerator RequestStep()
    {
        requestInProgress = true;

        using (UnityWebRequest request = CreateJsonPost(serverUrl + "/step"))
        { //asincrónico: manda la petición y retoma una vez que llega la respuesta
            yield return request.SendWebRequest(); //mandar petición
            HandleResponse(request); //manejar respuesta
        }

        requestInProgress = false;
    }

    private IEnumerator RequestReset()
    {
        requestInProgress = true;
        //usa ruta de "reset"
        //crear solicitud con JSON de post
        using (UnityWebRequest request = CreateJsonPost(serverUrl + "/reset"))
        {//asincrónico: manda la petición y retoma una vez que llega la respuesta
            yield return request.SendWebRequest();
            HandleResponse(request);
        }
        requestInProgress = false;
    }

    //función para crear JSON de los posts
    private UnityWebRequest CreateJsonPost(string url)
    {
        UnityWebRequest request = new UnityWebRequest(url, "POST"); //crear petición
        byte[] body = System.Text.Encoding.UTF8.GetBytes("{}"); //hacer body del JSON post vacío
        request.uploadHandler = new UploadHandlerRaw(body); //para enviar al servidor
        request.downloadHandler = new DownloadHandlerBuffer();
        request.SetRequestHeader("Content-Type", "application/json");
        return request;
    }

    //función para manejar respuestas del servidor
    private void HandleResponse(UnityWebRequest request)
    {
        if (request.result != UnityWebRequest.Result.Success) //manejador de error
        {
            Debug.LogError("No se pudo conectar con Mesa: " + request.error);
            return;
        }
        //convierte JSON recibido a clase de estado del tablero
        BoardState state = JsonUtility.FromJson<BoardState>(
            request.downloadHandler.text
        );

        if (state == null || state.fires == null) //si no se recibieron fireCells
        {
            Debug.LogError("La respuesta del servidor no contiene fireCells.");
            return;
        }
        //guardar si la simulación terminó en este turno o no
        simulationGameOver = state.gameOver;
        //usa estado nuevo para aplicarlo a la matriz de objetos de fuego y a arreglos de los demás objetos y agentes
        ApplyFireMatrix(state);
        ApplyBarriers(state);
        ApplyPOIs(state);
        ApplyFirefighters(state);
        ApplyGameFeedback(state);
        Debug.Log(
            "Turno de simulación recibido: " + state.turn
            + " | Rescatadas: " + state.rescuedVictims
            + " | Perdidas: " + state.lostVictims
            + " | Daño: " + state.structuralDamage
        );

        if (state.gameOver)
        {
            Debug.Log("Partida terminada: " + state.gameResult);
        }
    }

    private void ApplyFireMatrix(BoardState boardState)
    {
        int expectedCells = boardState.rows * boardState.columns;
        if (boardState.fires.Length != expectedCells) //revisar que la matriz de fuego sea de la longitud del tablero
        {
            Debug.LogError(
                "Tamaño de matriz inválido. Se esperaban " + expectedCells
                + " celdas y llegaron " + boardState.fires.Length + "."
            );
            return;
        }
        //recorrer filas y columnas
        for (int row = 0; row < boardState.rows; row++)
        {
            for (int column = 0; column < boardState.columns; column++)
            { //obtener índice de arreglo correspondiente a fila y columna
                int index = row * boardState.columns + column;
                //modificar contenido de la celda de acuerdo a estado del tablero
                UpdateEffectVisual(row, column, index, boardState.fires[index]);
            }
        }
    }

    private void UpdateEffectVisual(int row, int column, int index, int state)
    { //obtener del diccionario el contenido de la celda si existe en currentVisual
        if (activeEffectVisuals.TryGetValue(index, out EffectVisual currentVisual))
        {
            if (currentVisual.state == state) //si la casilla mantuvo su estado
            {
                return;
            }
            // si cambió de estado se destruye el gamObject actual
            Destroy(currentVisual.gameObject);
            activeEffectVisuals.Remove(index);
        }

        GameObject selectedPrefab = null;
        if (state == 2) //fuego, añadir prefab de fuego
        {
            selectedPrefab = firePrefab;
        }
        else if (state == 1) //humo, añadir prefab de humo
        {
            selectedPrefab = smokePrefab;
        }

        if (selectedPrefab == null)
        {
            return;
        }
        //instanciar selectedPrefab seleccionado como GameObject en el contenedor seleccionado, o en objeto con webclient
        Transform parent = effectsContainer != null ? effectsContainer : transform;
        GameObject visual = Instantiate(
            selectedPrefab, //prefab correspondiente
            GridToWorld(row, column), //en coordenadas correspondientes del tablero de Unity
            Quaternion.Euler(prefabEulerRotation), //sin rotación inicial
            parent //en contenedor padre
        );
        //guardar nuevo GameObject instanciado en diccionario
        activeEffectVisuals[index] = new EffectVisual
        {
            state = state,
            gameObject = visual
        };
    }

    private void ApplyBarriers(BoardState boardState) 
    { //se usan llaves de las barreras existentes y activas para evitar duplicados (en mesa eran atributos de 2 celdas, no una)
        HashSet<string> receivedKeys = new HashSet<string>(); 

        if (boardState.walls != null)
        { //usa arreglo paredes de clase de barreras en clase del estado del tablero
            foreach (BarrierState wallState in boardState.walls)
            {
                UpdateBarrierVisual(wallState, "wall", receivedKeys); //manda actualizar cada uno
            }
        }

        if (boardState.doors != null)
        { //usa arreglo puertas de clase de barreras en clase del estado del tablero
            foreach (BarrierState doorState in boardState.doors)
            {
                UpdateBarrierVisual(doorState, "door", receivedKeys);
            }
        }
        //eliminar barreras que ya no están activas 
        List<string> removedKeys = new List<string>();
        foreach (KeyValuePair<string, BarrierVisual> barrier in activeBarrierVisuals) //revisa todo el diccionario de barreras
        {
            if (!receivedKeys.Contains(barrier.Key)) //la barrera ya no se encuentra en llave en las recibidas (inactiva)
            {
                Destroy(barrier.Value.gameObject); //destruir el gameobject y quitar del diccionaro
                removedKeys.Add(barrier.Key);
            }
        }

        foreach (string key in removedKeys)
        {
            activeBarrierVisuals.Remove(key);
        }
    }

    private void UpdateBarrierVisual(
        BarrierState barrierState,
        string type,
        HashSet<string> receivedKeys)
    {
        string key = GetBarrierKey(
            barrierState.row,
            barrierState.column,
            barrierState.direction
        );
        receivedKeys.Add(key);

        GameObject selectedPrefab = null;
        float height = 0f;

        if (type == "wall")
        {
            height = wallHeight;
            if (barrierState.state == 2) //estado normal, añadir pared normal
            {
                selectedPrefab = wallPrefab;
            }
            else if (barrierState.state == 1) //estado dañado, añadir pared dañada
            {
                selectedPrefab = damagedWallPrefab != null
                    ? damagedWallPrefab
                    : wallPrefab;
            }
        }
        else if (type == "door")
        {
            height = doorHeight;
            if (barrierState.state == 2) //estado cerrado, cambiar a puerta cerrada
            {
                selectedPrefab = closedDoorPrefab;
            }
            else if (barrierState.state == 1) //estado abierto, cambiar a puerta abierta
            {
                selectedPrefab = openedDoorPrefab;
            }
        }

        if (activeBarrierVisuals.TryGetValue(key, out BarrierVisual currentVisual))
        {
            if (currentVisual.type == type && currentVisual.state == barrierState.state) //el objeto permaneció igual
            {
                currentVisual.gameObject.transform.position = BarrierGridToWorld(
                    barrierState.row,
                    barrierState.column,
                    barrierState.direction,
                    height
                );
                currentVisual.gameObject.transform.rotation = BarrierRotation(
                    barrierState.direction
                );
                return;
            }
            //cambio el objeto o su estado, quitar el anterior
            Destroy(currentVisual.gameObject);
            activeBarrierVisuals.Remove(key);
        }

        if (selectedPrefab == null)
        {
            return;
        }

        Transform parent = barriersContainer != null ? barriersContainer : transform;
        GameObject visual = Instantiate(
            selectedPrefab, //añadir nuevo prefab correspondiente
            BarrierGridToWorld(
                barrierState.row,
                barrierState.column,
                barrierState.direction,
                height
            ),
            BarrierRotation(barrierState.direction),
            parent
        );

        activeBarrierVisuals[key] = new BarrierVisual //añadir nuevo gameobject a diccionario de barreras activas
        {
            type = type,
            state = barrierState.state,
            gameObject = visual
        };
    }

    //actualizar contadores del canvas de la simulación
    private void ApplyGameFeedback(BoardState boardState)
    {
        if (rescuedVictimsText != null)
        {
            rescuedVictimsText.text =
                "Rescatadas: " + boardState.rescuedVictims + " / 7";
        }

        if (structuralDamageText != null)
        {
            structuralDamageText.text =
                "Daño: " + boardState.structuralDamage + " / 24";
        }
    }

    //función para crear las llaves de las barreras y obtener la misma llave para 2 celdas de mesa que comparten una pared (evitando duplicados)
    private string GetBarrierKey(int row, int column, string direction)
    {
        if (direction == "up")
        {
            return "H_" + row + "_" + column;
        }
        if (direction == "down")
        {
            return "H_" + (row + 1) + "_" + column;
        }
        if (direction == "left")
        {
            return "V_" + row + "_" + column;
        }
        return "V_" + row + "_" + (column + 1);
    }

    private Quaternion BarrierRotation(string direction) //quitar rotación?
    {
        if (direction == "up" || direction == "down")
        {
            return Quaternion.Euler(horizontalBarrierEulerRotation);
        }
        return Quaternion.Euler(verticalBarrierEulerRotation);
    }

    private void ApplyPOIs(BoardState boardState) //usa arreglo de clase POIs en clase del estado del tablero
    {
        if (boardState.pois == null)
        {
            return;
        }

        foreach (POIState poiState in boardState.pois)
        {
            UpdatePOIVisual(poiState); //manda actualizar cada uno
        }
    }

    private void UpdatePOIVisual(POIState poiState)
    {
        if (!poiState.active) //eliminar POIs que ya no están activos (ya no existen)
        {
            if (activePOIVisuals.TryGetValue(poiState.id, out POIVisual inactiveVisual))
            {
                Destroy(inactiveVisual.gameObject); //eliminar y quitar de diccionario
                activePOIVisuals.Remove(poiState.id);
            }
            return;
        }

        GameObject selectedPrefab = null;
        if (!poiState.revealed)
        {
            selectedPrefab = poiPrefab; //si no ha sido revelado permanece igual
        }
        else if (poiState.type == "victim")
        {
            if (victimPrefabs != null && victimPrefabs.Length > 0)
            {
                int prefabIndex = poiState.visualIndex % victimPrefabs.Length;
                selectedPrefab = victimPrefabs[prefabIndex]; //si es víctima se cambia a una de las víctimas
            }
        }
        else
        {
            selectedPrefab = falseAlarmPrefab; //si no, se cambia falsa alarma
        }

        if (selectedPrefab == null)
        {
            return;
        }

        if (activePOIVisuals.TryGetValue(poiState.id, out POIVisual currentVisual))
        {
            if (currentVisual.revealed == poiState.revealed //si sigue siendo mismo tipo y en misma lugar, se queda
                && currentVisual.type == poiState.type
                && currentVisual.visualIndex == poiState.visualIndex)
            {
                currentVisual.gameObject.transform.position = POIGridToWorld(
                    poiState.row,
                    poiState.column
                );
                return;
            }
            //si cambió, se elimina gameobject anterior
            Destroy(currentVisual.gameObject);
            activePOIVisuals.Remove(poiState.id);
        }

        Transform parent = poisContainer != null ? poisContainer : transform;
        GameObject visual = Instantiate(
            selectedPrefab, //se añade el nuevo gameobject si cambió
            POIGridToWorld(poiState.row, poiState.column),
            Quaternion.Euler(poiEulerRotation),
            parent
        );

        activePOIVisuals[poiState.id] = new POIVisual //se añade al diccionario de POIs
        {
            type = poiState.type,
            revealed = poiState.revealed,
            visualIndex = poiState.visualIndex,
            gameObject = visual
        };
    }

    private void ApplyFirefighters(BoardState boardState) //usa arreglo de clase bomberos en clase del estado del tablero
    {
        if (boardState.firefighters == null)
        {
            return;
        }

        foreach (FirefighterState firefighterState in boardState.firefighters)
        {
            UpdateFirefighterVisual(firefighterState); //manda actualizar cada uno
        }
    }

    private void UpdateFirefighterVisual(FirefighterState firefighterState)
    {
        if (firefighterPrefabs == null //si los prefabs de bombero no están asignados para el num de jugadores
            || firefighterState.player < 0
            || firefighterState.player >= firefighterPrefabs.Length)
        {
            return;
        }

        if (activeFirefighterVisuals.TryGetValue(
            firefighterState.player,
            out GameObject currentVisual))
        {
            currentVisual.transform.position = FirefighterGridToWorld(
                firefighterState.row,
                firefighterState.column
            );
            return;
        }

        GameObject selectedPrefab = firefighterPrefabs[firefighterState.player];
        if (selectedPrefab == null)
        {
            return;
        }

        Transform parent = firefightersContainer != null ? firefightersContainer : transform;
        GameObject visual = Instantiate(
            selectedPrefab,
            FirefighterGridToWorld(firefighterState.row, firefighterState.column),
            Quaternion.Euler(firefighterEulerRotation),
            parent
        );

        activeFirefighterVisuals[firefighterState.player] = visual;
    }

    private Vector3 GridToWorld(int row, int column)
    {
        //usar origen del tablero o 0,0,0
        Vector3 origin = boardOrigin != null ? boardOrigin.position : Vector3.zero;
        //convertir a coordenadas de fuegos al tablero de Unity: al centro (mitad) de las celdas y con altura 'y' determinada
        return new Vector3(
            origin.x + column * cellSize + cellSize / 2f,
            origin.y + effectHeight,
            origin.z - row * cellSize - cellSize / 2f
        );
    }

    private Vector3 BarrierGridToWorld(
        int row,
        int column,
        string direction,
        float height)
    {
        Vector3 origin = boardOrigin != null ? boardOrigin.position : Vector3.zero;

        float x = origin.x + column * cellSize + cellSize / 2f;
        float z = origin.z - row * cellSize - cellSize / 2f;

        if (direction == "up")
        {
            z = origin.z - row * cellSize;
        }
        else if (direction == "down")
        {
            z = origin.z - (row + 1) * cellSize;
        }
        else if (direction == "left")
        {
            x = origin.x + column * cellSize;
        }
        else if (direction == "right")
        {
            x = origin.x + (column + 1) * cellSize;
        }

        return new Vector3(
            x,
            origin.y + height,
            z
        );
    }

    private Vector3 POIGridToWorld(int row, int column) //convertir coord POIs a coordenadas del tablero de Unity
    {
        Vector3 origin = boardOrigin != null ? boardOrigin.position : Vector3.zero;
        return new Vector3(
            origin.x + column * cellSize + cellSize / 2f,
            origin.y + poiHeight,
            origin.z - row * cellSize - cellSize / 2f
        );
    }

    private Vector3 FirefighterGridToWorld(int row, int column) //convertir coord bomberos a coordenadas del tablero de Unity
    {
        Vector3 origin = boardOrigin != null ? boardOrigin.position : Vector3.zero;
        return new Vector3(
            origin.x + column * cellSize + cellSize / 2f,
            origin.y + firefighterHeight,
            origin.z - row * cellSize - cellSize / 2f
        );
    }
}
