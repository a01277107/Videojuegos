// Cliente de Unity que hace requests y obtiene la información de la simulación para proyectarse en los gráficos de Unity

using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Networking;

[Serializable]
public class BarrierState
{
    public int row;
    public int column;
    public string direction;
    public int state;
}

[Serializable]
public class POIState
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
public class FirefighterState
{
    public int player;
    public int row;
    public int column;
}

//clase formada a partir del JSON que manda mesa del estado del tablero
[Serializable] //convertibles desde o hacia JSON
public class BoardState
{
    public int rows;
    public int columns;
    public int turn;
    public int advancedRow;
    public int advancedColumn;
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

    //diccionario de los contenidos (GameObjects) que existen
    private readonly Dictionary<int, CellVisual> activeVisuals =
        new Dictionary<int, CellVisual>();
    private readonly Dictionary<string, BarrierVisual> activeBarrierVisuals =
        new Dictionary<string, BarrierVisual>();
    private readonly Dictionary<int, POIVisual> activePOIVisuals =
        new Dictionary<int, POIVisual>();
    private readonly Dictionary<int, GameObject> activeFirefighterVisuals =
        new Dictionary<int, GameObject>();
    private bool requestInProgress; //evita que se hagan dos petciciones simultáneas

    //clase para obtener/guardar contenido de las celdas en Unity
    private class CellVisual
    {
        public int state; //representa si es fuego o humo
        public GameObject gameObject; //objeto creado en unity
    }

    private class BarrierVisual
    {
        public string type;
        public int state;
        public GameObject gameObject;
    }

    private class POIVisual
    {
        public string type;
        public bool revealed;
        public int visualIndex;
        public GameObject gameObject;
    }

    private void Start() //Se llama automáticamente al inicio de la simulación
    {
        if (clearContainerOnStart && effectsContainer != null)
        { //quitar los objetos que existen antes de empezar simulaciób
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
            StartCoroutine(RequestState(false));
        }
    }

    //para probar: cambiar manualmente elementos del tablero
    public void TestConnection()
    {
        if (!requestInProgress)
        {
            StartCoroutine(RequestTest());
        }
    }

    //para pruebas: ejecutar manualmente advanceFire
    public void AdvanceFire()
    {
        if (!requestInProgress)
        {
            StartCoroutine(RequestState(true));
        }
    }

    //reiniciar simulación
    public void ResetSimulation()
    {
        if (!requestInProgress)
        {
            StartCoroutine(RequestReset());
        }
    }

    //para probar
    private IEnumerator RequestTest()
{
    requestInProgress = true;

    using (UnityWebRequest request = CreateJsonPost(serverUrl + "/test"))
    {
        yield return request.SendWebRequest();
        HandleResponse(request);
    }

    requestInProgress = false;
}

    //corrutina para obtener estado del tablero (con o sin advanceFire)
    private IEnumerator RequestState(bool advanceFire)
    {
        requestInProgress = true;
        //si advanceFire = true usa ruta step, si no usa ruta state
        string route = advanceFire ? "/step" : "/state";
        //crear solicitud. Si advanceFire = crea JSON de post, si no hace solicitud get
        using (UnityWebRequest request = advanceFire
            ? CreateJsonPost(serverUrl + route)
            : UnityWebRequest.Get(serverUrl + route))
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
        //usa estado nuevo para aplicarlo a la matriz de objetos de fuego
        ApplyFireMatrix(state);
        ApplyBarriers(state);
        ApplyPOIs(state);
        ApplyFirefighters(state);
        Debug.Log("Turno de fuego recibido: " + state.turn);
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
                UpdateCellVisual(row, column, index, boardState.fires[index]);
            }
        }
    }

    private void UpdateCellVisual(int row, int column, int index, int state)
    { //obtener del diccionario el contenido de la celda si existe en currentVisual
        if (activeVisuals.TryGetValue(index, out CellVisual currentVisual))
        {
            if (currentVisual.state == state) //si la casilla mantuvo su estado
            {
                return;
            }
            // si cambió de estado se destruye el gamObject actual
            Destroy(currentVisual.gameObject);
            activeVisuals.Remove(index);
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
        activeVisuals[index] = new CellVisual
        {
            state = state,
            gameObject = visual
        };
    }

    private void ApplyBarriers(BoardState boardState)
    {
        HashSet<string> receivedKeys = new HashSet<string>();

        if (boardState.walls != null)
        {
            foreach (BarrierState wallState in boardState.walls)
            {
                UpdateBarrierVisual(wallState, "wall", receivedKeys);
            }
        }

        if (boardState.doors != null)
        {
            foreach (BarrierState doorState in boardState.doors)
            {
                UpdateBarrierVisual(doorState, "door", receivedKeys);
            }
        }

        List<string> removedKeys = new List<string>();
        foreach (KeyValuePair<string, BarrierVisual> barrier in activeBarrierVisuals)
        {
            if (!receivedKeys.Contains(barrier.Key))
            {
                Destroy(barrier.Value.gameObject);
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
            if (barrierState.state == 2)
            {
                selectedPrefab = wallPrefab;
            }
            else if (barrierState.state == 1)
            {
                selectedPrefab = damagedWallPrefab != null
                    ? damagedWallPrefab
                    : wallPrefab;
            }
        }
        else if (type == "door")
        {
            height = doorHeight;
            if (barrierState.state == 2)
            {
                selectedPrefab = closedDoorPrefab;
            }
            else if (barrierState.state == 1)
            {
                selectedPrefab = openedDoorPrefab;
            }
        }

        if (activeBarrierVisuals.TryGetValue(key, out BarrierVisual currentVisual))
        {
            if (currentVisual.type == type && currentVisual.state == barrierState.state)
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

            Destroy(currentVisual.gameObject);
            activeBarrierVisuals.Remove(key);
        }

        if (selectedPrefab == null)
        {
            return;
        }

        Transform parent = barriersContainer != null ? barriersContainer : transform;
        GameObject visual = Instantiate(
            selectedPrefab,
            BarrierGridToWorld(
                barrierState.row,
                barrierState.column,
                barrierState.direction,
                height
            ),
            BarrierRotation(barrierState.direction),
            parent
        );

        activeBarrierVisuals[key] = new BarrierVisual
        {
            type = type,
            state = barrierState.state,
            gameObject = visual
        };
    }

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

    private Quaternion BarrierRotation(string direction)
    {
        if (direction == "up" || direction == "down")
        {
            return Quaternion.Euler(horizontalBarrierEulerRotation);
        }
        return Quaternion.Euler(verticalBarrierEulerRotation);
    }

    private void ApplyPOIs(BoardState boardState)
    {
        if (boardState.pois == null)
        {
            return;
        }

        foreach (POIState poiState in boardState.pois)
        {
            UpdatePOIVisual(poiState);
        }
    }

    private void UpdatePOIVisual(POIState poiState)
    {
        if (!poiState.active)
        {
            if (activePOIVisuals.TryGetValue(poiState.id, out POIVisual inactiveVisual))
            {
                Destroy(inactiveVisual.gameObject);
                activePOIVisuals.Remove(poiState.id);
            }
            return;
        }

        GameObject selectedPrefab = null;
        if (!poiState.revealed)
        {
            selectedPrefab = poiPrefab;
        }
        else if (poiState.type == "victim")
        {
            if (victimPrefabs != null && victimPrefabs.Length > 0)
            {
                int prefabIndex = poiState.visualIndex % victimPrefabs.Length;
                selectedPrefab = victimPrefabs[prefabIndex];
            }
        }
        else
        {
            selectedPrefab = falseAlarmPrefab;
        }

        if (selectedPrefab == null)
        {
            return;
        }

        if (activePOIVisuals.TryGetValue(poiState.id, out POIVisual currentVisual))
        {
            if (currentVisual.revealed == poiState.revealed
                && currentVisual.type == poiState.type
                && currentVisual.visualIndex == poiState.visualIndex)
            {
                currentVisual.gameObject.transform.position = POIGridToWorld(
                    poiState.row,
                    poiState.column
                );
                return;
            }

            Destroy(currentVisual.gameObject);
            activePOIVisuals.Remove(poiState.id);
        }

        Transform parent = poisContainer != null ? poisContainer : transform;
        GameObject visual = Instantiate(
            selectedPrefab,
            POIGridToWorld(poiState.row, poiState.column),
            Quaternion.Euler(poiEulerRotation),
            parent
        );

        activePOIVisuals[poiState.id] = new POIVisual
        {
            type = poiState.type,
            revealed = poiState.revealed,
            visualIndex = poiState.visualIndex,
            gameObject = visual
        };
    }

    private void ApplyFirefighters(BoardState boardState)
    {
        if (boardState.firefighters == null)
        {
            return;
        }

        foreach (FirefighterState firefighterState in boardState.firefighters)
        {
            UpdateFirefighterVisual(firefighterState);
        }
    }

    private void UpdateFirefighterVisual(FirefighterState firefighterState)
    {
        if (firefighterPrefabs == null
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
        //convertir a coordenadas del tablero de Unity: al centro (mitad) de las celdas y con altura 'y' determinada
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

    private Vector3 POIGridToWorld(int row, int column)
    {
        Vector3 origin = boardOrigin != null ? boardOrigin.position : Vector3.zero;
        return new Vector3(
            origin.x + column * cellSize + cellSize / 2f,
            origin.y + poiHeight,
            origin.z - row * cellSize - cellSize / 2f
        );
    }

    private Vector3 FirefighterGridToWorld(int row, int column)
    {
        Vector3 origin = boardOrigin != null ? boardOrigin.position : Vector3.zero;
        return new Vector3(
            origin.x + column * cellSize + cellSize / 2f,
            origin.y + firefighterHeight,
            origin.z - row * cellSize - cellSize / 2f
        );
    }
}
