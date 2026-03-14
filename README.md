# BaillConnect — Intégration Home Assistant

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![Validation](https://github.com/jocelynlopez/baillconnect-ha/actions/workflows/validate.yml/badge.svg)](https://github.com/jocelynlopez/baillconnect-ha/actions/workflows/validate.yml)
[![Tests](https://github.com/jocelynlopez/baillconnect-ha/actions/workflows/tests.yml/badge.svg)](https://github.com/jocelynlopez/baillconnect-ha/actions/workflows/tests.yml)

Intégration **Home Assistant** pour piloter votre système de climatisation gainable
**BAILLZONING®** via le module connecté **IDC-WEB BAILLCONNECT®**.

---

## Prérequis

- Un compte actif sur [baillconnect.com](https://www.baillconnect.com)
- Un module IDC-WEB BAILLCONNECT installé et connecté au cloud
- Home Assistant **2024.1** ou plus récent
- **HACS** installé ([guide d'installation HACS](https://hacs.xyz/docs/setup/download))

---

## Installation via HACS

### Méthode recommandée (bouton direct)

[![Ouvrir votre instance Home Assistant et ajouter un dépôt personnalisé HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jocelynlopez&repository=baillconnect-ha&category=integration)

### Méthode manuelle

1. Ouvrez HACS dans Home Assistant
2. Cliquez sur **Intégrations** → menu ⋮ → **Dépôts personnalisés**
3. Ajoutez l'URL : `https://github.com/jocelynlopez/baillconnect-ha`
   - Catégorie : **Intégration**
4. Cliquez sur **Ajouter**
5. Cherchez **BaillConnect** dans HACS et cliquez **Télécharger**
6. **Redémarrez Home Assistant**

---

## Configuration

1. Allez dans **Paramètres → Appareils & Services → Ajouter une intégration**
2. Cherchez **BaillConnect**
3. Renseignez votre **adresse e-mail** et **mot de passe** baillconnect.com
4. L'ID de régulation est détecté automatiquement.
   Si ce n'est pas le cas, récupérez-le depuis l'URL du portail web
   (ex. `https://www.baillconnect.com/regulations/`**`123`**)
5. Cliquez **Valider**

---

## Entités créées

### Entités `climate` (une par thermostat)

| Entité | Description |
|--------|-------------|
| `climate.baillconnect_<nom>` | Contrôle complet du thermostat |

**Fonctionnalités exposées :**

| Propriété HA | Source API | Notes |
|---|---|---|
| `current_temperature` | `thermostats[n].temperature` | Lecture seule |
| `target_temperature` | `setpoint_hot/cool_t1/t2` | Selon mode + preset |
| `hvac_mode` | `uc_mode` | Modifiable via th1 uniquement |
| `preset_mode` | `t1_t2` | `confort` / `eco` |
| `fan_mode` | `ui_fan` | Disponible sur th1 uniquement |

**Modes HVAC disponibles :**

| Mode HA | Valeur API | Description |
|---------|-----------|-------------|
| `off` | 0 | Arrêt |
| `cool` | 1 | Froid |
| `heat` | 2 | Chauffage |
| `dry` | 3 | Déshumidification |

**Presets :**

| Preset | Description |
|--------|-------------|
| `confort` | Consigne T1 (confort) |
| `eco` | Consigne T2 (économie) |

> **Important :** Le mode HVAC global ne peut être changé que depuis le thermostat `th1`.
> Les autres thermostats affichent le mode mais ne peuvent pas le modifier.

### Entités `sensor` par thermostat

| Entité | Description | Unité |
|--------|-------------|-------|
| `sensor.<nom>_temperature` | Température ambiante | °C |
| `sensor.<nom>_battery` | Batterie faible | `Oui` / `Non` |
| `sensor.<nom>_connected` | Connexion thermostat | `Connecté` / `Déconnecté` |
| `sensor.<nom>_motor_state` | État volet | `Ouvert` / `Fermé` |

### Entités `sensor` niveau régulation

| Entité | Description |
|--------|-------------|
| `sensor.baillconnect_fan_speed` | Vitesse ventilateur (`auto`, `low`, `medium`, `high`) |
| `sensor.baillconnect_circuit_on` | Circuit physiquement actif (`Actif` / `Inactif`) |
| `sensor.baillconnect_error_code` | Code erreur (0 = pas d'erreur) |
| `sensor.baillconnect_idc_connected` | Module IDC-WEB connecté au cloud |

---

## Trouver votre Regulation ID

Si l'auto-découverte échoue :

1. Connectez-vous sur [baillconnect.com](https://www.baillconnect.com)
2. Naviguez vers votre installation
3. L'URL contient l'ID : `https://www.baillconnect.com/regulations/`**`123`**`/...`
   → Entrez `123`

---

## Dépannage

### L'intégration ne trouve pas mon installation

- Vérifiez que vos identifiants sont corrects en vous connectant manuellement sur le portail
- Essayez de supprimer et recréer l'intégration
- Entrez manuellement votre Regulation ID (voir section ci-dessus)

### Les entités sont indisponibles

- Vérifiez que le module IDC-WEB est allumé et connecté à Internet
- Consultez la valeur du sensor `idc_connected`
- Regardez les logs Home Assistant : **Paramètres → Système → Journaux**
  et filtrez sur `baillconnect`

### Erreur d'authentification après un moment

L'intégration gère la reconnexion automatique en cas d'expiration de session.
Si l'erreur persiste, supprimez et recréez l'intégration.

### Le mode HVAC ne change pas depuis un thermostat autre que th1

C'est normal — l'API BAILLCONNECT pilote le mode global uniquement via le thermostat 1.
Utilisez l'entité `climate` du thermostat `th1` pour changer le mode.

---

## Mise à jour

1. Dans HACS, la mise à jour s'affiche automatiquement quand une nouvelle version est disponible
2. Cliquez **Mettre à jour**
3. Redémarrez Home Assistant

---

## Contribution

Les contributions sont les bienvenues !

1. Forkez le dépôt
2. Créez une branche : `git checkout -b feature/ma-fonctionnalite`
3. Commitez vos modifications
4. Ouvrez une Pull Request

### Lancer les tests localement

```bash
pip install pytest pytest-asyncio pytest-homeassistant-custom-component aiohttp beautifulsoup4
pytest tests/ -v
```

---

## Licence

MIT — voir [LICENSE](LICENSE)
