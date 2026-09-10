using UnityEngine;
using TMPro;

public class GameUI : MonoBehaviour
{
    // Textos del Canvas
    public TMP_Text victimasCount;
    public TMP_Text damageText;

    // Actualiza el contador de víctimas
    public void ActualizarVictimas(int victimas)
    {
        victimasCount.text = "Víctimas: " + victimas;
    }

    // Actualiza los puntos de daño
    public void ActualizarDamage(int damage)
    {
        damageText.text = "Damage Points: " + damage;
    }
}