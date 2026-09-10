# Videojuegos: simulación gráfica de juego de mesa

En este repositorio se encuentran los archivos correspondientes al proyecto de simulación del juego de mesa "Flash Point Fire Rescue" del Equipo 1, para la materia de "Modelación de sistemas multiagentes con gráficas computacionales".

Integrantes del equipo:
Isabella Montiel A01278286
Santiago Acosta A01277107
Ana Sofía Moreno A01707156

## Main
Dentro de la rama de main se encuentra el pdf del instructivo del juego que se busca simular y los diagramas de estado del bombero (agente), el modelo y el juego como tal. 
## Develop
Actualmente, el código aceptado para la simulación se encuentra en la rama develop. Se realizó en un archivo de tipo Jupyter Notebook (.ipynb) para poder realizar pruebas y visualizaciones.
## Unity
Los archivos correspondientes a los gráficos para la simulación, creados en Unity, se encuentran exclusivamente en la rama de "Unity".
## servidorPython
En la rama de servidorPython se encuentran los archivos necesarios para realizar la conexión entre Unity y mesa, incluyendo el de Unity como cliente, el del servidor de pyhton, y un archivo copia de la simulación de mesa en .py para ser importado por el servidor.

Para la realización de este proyecto se hizo uso del programa Unity para los gráficos de la simulación y de Mesa con pyhton para la programación del modelo con multiagentes.

## Uso de IA generativa
Para el desarrollo y la codificación de este proyecto se hizo uso de las herramientas de Inteligencia Artificial de "Claude sonnet" y "ChatGPT Plus" como guía para la implementación correcta de los algoritmos seleccionados, la identificación y corrección de errores en el código, y la generación de casos de prueba específicos para determinadas partes del código a lo largo de su desarrollo. Además, tratándose de herramientas de código nuevas o no previamente implementadas por el equipo, se declara el uso particular de estas herramientas de IA para generar:
+ Funciones correctas de serialización y deserialización en formato JSON de los objetos y agentes de la simulación para poder intercambiar los datos entre el servidor Pyhton y Unity
+ Un HashSet que permitiera manejar llaves únicas para las paredes de la simulación y así evitar manejar duplicados, así como un código para la generación de llaves canónicas
+ Uso de @dataclass para crear clases con estados y propiedades (sin funciones propias) sin la necesidad de hacer un constructor, para objetos complejos de la simulación
+ Uso de lambda y una función como llave o criterio para ordenar los elementos de un arreglo
