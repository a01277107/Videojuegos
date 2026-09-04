// Cliente de Unity que hace requests y obtiene la información de la simulación para proyectarse en los gráficos de Unity

using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Networking;

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
    [Header("Prefabs")]
    [SerializeField] private GameObject firePrefab;
    [SerializeField] private GameObject smokePrefab;
    [SerializeField] private Transform effectsContainer; //contenedor de fuegos y humos
    [SerializeField] private Vector3 prefabEulerRotation = Vector3.zero; //añadir los GamObjects sin rotación
    [SerializeField] private bool clearContainerOnStart = true;

    //diccionario de los contenidos (GameObjects) que existen
    private readonly Dictionary<int, CellVisual> activeVisuals =
        new Dictionary<int, CellVisual>();
    private bool requestInProgress; //evita que se hagan dos petciciones simultáneas

    //clase para obtener/guardar contenido de las celdas en Unity
    private class CellVisual
    {
        public int state; //representa si es fuego o humo
        public GameObject gameObject; //objeto creado en unity
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
}
