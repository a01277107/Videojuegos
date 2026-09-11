using UnityEngine;
using UnityEngine.InputSystem;

public class CameraSwitcher : MonoBehaviour
{
    public Camera topCamera;
    public Camera camera3D;

    void Start()
    {
        topCamera.gameObject.SetActive(true);
        camera3D.gameObject.SetActive(false);
    }

    void Update()
    {
        if (Keyboard.current != null && Keyboard.current.cKey.wasPressedThisFrame)
        {
            CambiarCamara();
        }
    }

    void CambiarCamara()
    {
        bool usandoSuperior = topCamera.gameObject.activeSelf;

        topCamera.gameObject.SetActive(!usandoSuperior);
        camera3D.gameObject.SetActive(usandoSuperior);
    }
}