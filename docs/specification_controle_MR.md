# Gitective — Spécification technique

Contrôle des Merge Requests GitLab

Version : 1.3 (brouillon) — 08/10/2026

## 1. Objet

**Gitective** (Git + detective) est une application de bureau permettant de contrôler le respect du process sur les Merge Requests (MR) des dépôts GitLab choisis par l'utilisateur, et de détecter les commits poussés sans MR.

## 2. Contraintes techniques

| Réf. | Exigence |
|---|---|
| CT-01 | Langage : Python 3.11 minimum. |
| CT-02 | Bibliothèque standard uniquement (aucun module externe, aucun téléchargement). Ex. : `tkinter`, `urllib`, `json`, `re`, `ssl`, `webbrowser`, `datetime`, `threading`, `unittest`. |
| CT-03 | Système cible : Windows, Python déjà installé sur le poste. |
| CT-04 | GitLab auto-hébergé : URL de l'instance configurable. |
| CT-05 | Authentification par Personal Access Token GitLab, droits `read_api` uniquement. |
| CT-06 | Token et paramètres stockés en clair dans `config.json`, à côté de l'application. |
| CT-09 | IHM : `tkinter` + `ttk` (inclus dans Python). |
| CT-07 | Dates affichées et filtrées dans le fuseau horaire local du PC. |
| CT-08 | Vérification SSL active par défaut ; option de configuration pour la désactiver. |

## 3. Configuration

Fichier `config.json`, dans le dossier de l'application, contenant :

| Paramètre | Valeur par défaut |
|---|---|
| URL de l'instance GitLab | — |
| Token personnel | — |
| Vérification SSL | activée |
| Dépôts sélectionnés (sauvegardés depuis l'IHM) | aucun |
| Branche surveillée par dépôt (commits hors MR) | — |
| Règles personnalisées (voir 7.1) | 2 règles pré-remplies : « Titre conforme », « Lien ticket » |
| Correspondance ticket : regex du lien et regex du n° de ticket | — |
| Pondération des règles fixes (RC-03, RC-04) | 25 chacune |
| Seuils de couleur du score | vert = 100 %, orange ≥ 50 %, rouge < 50 % |
| Correspondances personnes ↔ comptes | aucune |
| Thème | Clair |
| Derniers filtres utilisés (état, dates, auteurs, dépôts, taille de page) | Mergées « Depuis hier », 20 |
| Largeurs de colonnes modifiées | aucune (ajustement au titre) |

## 4. Sélection des dépôts

| Réf. | Exigence |
|---|---|
| SD-01 | L'IHM récupère depuis GitLab la liste des projets accessibles avec le token. |
| SD-02 | L'utilisateur coche les dépôts à contrôler. |
| SD-03 | La sélection est sauvegardée dans `config.json`. |

## 5. Onglet Config, thèmes et identité

### 5.1 Onglet Config

| Réf. | Exigence |
|---|---|
| OC-01 | Onglet « Config » dans l'application, permettant de modifier tous les paramètres de la section 3. |
| OC-02 | Token : champ masqué + bouton « Afficher ». |
| OC-03 | Enregistrement dans `config.json`. |
| OC-04 | Choix du thème parmi une liste figée (voir 5.2). |
| OC-05 | Bouton « Tester la connexion » : vérifie URL + token, résultat affiché par le bandeau de notification. |
| OC-06 | Testeur de regex : saisie d'exemples (titre, description, branches, messages de commits), affichage immédiat OK / KO de chaque règle active et de RC-03 avec le n° de ticket extrait. |
| OC-07 | Validation des regex avant enregistrement ; une regex invalide bloque l'enregistrement et est signalée par le bandeau. |
| OC-08 | Gestion des correspondances personnes ↔ comptes (voir 5.4). |

### 5.2 Thèmes (DA)

| Réf. | Thème | Description |
|---|---|---|
| TH-01 | Clair | Classique et minimaliste. |
| TH-02 | Sombre | Classique et minimaliste. |
| TH-03 | Windows 95 | Gris, reliefs biseautés, police système rétro. |
| TH-04 | Matrix | Fond noir, texte vert, police monospace. |

Chaque thème définit : fonds, textes, bordures, police, couleurs OK / KO / N/A et couleurs des niveaux de score. Thèmes non modifiables. Appliqués via `ttk.Style` et la grille personnalisée.

Les couleurs OK / KO / N/A sont adaptées à chaque thème (ex. Matrix : vert vif / vert sombre / gris). Les libellés texte « OK », « KO », « N/A » restent affichés pour garantir la lisibilité quelle que soit la couleur.

### 5.3 Identité visuelle

| Réf. | Exigence |
|---|---|
| ID-01 | Nom : **Gitective**. |
| ID-02 | Logo original : renard détective avec lunettes et chapeau, style distinct du logo GitLab (marque déposée, non réutilisée). |
| ID-03 | Logo réalisé par Claude : SVG source, style simple et plat, converti en `logo.png` (affichage dans l'IHM) et `logo.ico` (icône de fenêtre Windows). |
| ID-04 | Fichiers livrés dans `gitective/assets/`. |

### 5.4 Personnes et comptes multiples

Une même personne peut posséder plusieurs comptes GitLab (changements de comptes dans l'entreprise).

| Réf. | Exigence |
|---|---|
| PE-01 | Dans l'onglet Config, on crée une personne (nom affiché) et on lui associe un ou plusieurs comptes GitLab, choisis dans une liste. |
| PE-02 | Un compte est identifié par son ID utilisateur GitLab. |
| PE-03 | Pour les commits hors MR (sans ID GitLab), on associe aussi à la personne des noms et/ou e-mails Git. |
| PE-04 | Les tableaux affichent le nom de la personne (colonnes Auteur, Mergeur, Auteur de commit). |
| PE-05 | Filtre par auteur et statistiques regroupés par personne. |
| PE-06 | RC-04 compare des personnes : MR mergée par un autre compte de son auteur = KO. |
| PE-07 | Un compte sans correspondance est affiché sous son nom GitLab et traité comme une personne à part. |

### 5.5 Avatars

| Réf. | Exigence |
|---|---|
| AV-01 | Avatar récupéré via le champ `avatar_url` de l'utilisateur GitLab. |
| AV-02 | Affiché dans l'onglet Statistiques et dans la gestion des personnes (onglet Config). |
| AV-03 | Formats affichables : PNG et GIF (limite de `tkinter` sans module externe). |
| AV-04 | Avatar JPEG, introuvable ou injoignable : pastille ronde avec les initiales, couleur stable par personne. |
| AV-05 | Personne à plusieurs comptes : avatar du compte le plus récent (ID utilisateur GitLab le plus élevé). |
| AV-06 | Redimensionnement par facteur entier uniquement (`tkinter`) : taille d'affichage approximative. |
| AV-07 | Cache sur disque, dans un dossier `avatars/` à côté de l'application ; retéléchargé au bouton Rafraîchir. |

### 5.6 Assistant de premier lancement

| Réf. | Exigence |
|---|---|
| AS-01 | Affiché au premier lancement (absence de `config.json`). |
| AS-02 | Étapes : URL de l'instance → token → test de connexion → choix des dépôts. |
| AS-03 | Passable à tout moment ; relançable depuis l'onglet Config. |

## 6. Filtres et affichage des MR

### 6.1 Filtres

| Réf. | Exigence |
|---|---|
| FI-01 | Filtre d'état exclusif (un seul à la fois) : **Mergées**, **Ouvertes**, **Fermées**. |
| FI-02 | **Mergées** : filtre entre deux dates, appliqué sur la date de merge. |
| FI-03 | Saisie des dates au format `JJ/MM/AAAA`, journées entières : date de début 00:00:00 → date de fin 23:59:59 incluses. |
| FI-04 | **Mergées** : raccourci « Depuis hier » = hier 00:00 → maintenant. |
| FI-05 | **Ouvertes** et **Fermées** : aucun filtre de date, liste complète. |
| FI-06 | Les derniers filtres sont mémorisés dans `config.json` et restaurés au lancement. |
| FI-07 | Sans filtre mémorisé, la vue de lancement est **Mergées « Depuis hier »**. |
| FI-08 | Les MR en brouillon (Draft) sont exclues : ni affichées, ni comptées. |
| FI-09 | Filtre par auteur, sélection multiple (tous par défaut). S'applique aussi à l'onglet Commits hors MR. |
| FI-10 | Raccourci **F5** = Rafraîchir. |
| FI-11 | Filtre par dépôt, sélection multiple parmi les dépôts suivis (tous par défaut). S'applique aussi à l'onglet Commits hors MR. Mémorisé comme les autres filtres (FI-06). |

### 6.2 Tableau

Grille personnalisée (cellules colorées individuellement). Colonnes :

| Colonne | Contenu |
|---|---|
| Dépôt | Nom du dépôt de la MR |
| Titre | Titre de la MR — **simple clic = ouverture de la MR dans le navigateur web par défaut** |
| Auteur | Auteur de la MR |
| Mergeur | Utilisateur ayant mergé (vide si non mergée) |
| Date de création | Heure locale |
| Date de merge | Heure locale (vide si non mergée) |
| Une colonne par règle personnalisée active | OK vert / KO rouge |
| Correspondance ticket | OK vert / KO rouge |
| Non mergée par l'auteur | OK vert / KO rouge / N/A gris |
| Score | Pourcentage, couleur vert / orange / rouge selon seuils |

| Réf. | Exigence |
|---|---|
| TA-01 | Survol d'une cellule KO : infobulle affichant le détail de l'erreur (ex. « PROJ-12 (titre) ≠ PROJ-21 (lien) »). |
| TA-02 | Clic sur un en-tête de colonne : tri sur toute la liste filtrée (croissant / décroissant), puis repagination. |
| TA-03 | Score moyen affiché en en-tête, calculé sur toute la liste filtrée. |
| TA-04 | Largeur des colonnes : à l'ouverture, chaque colonne s'ajuste pour afficher son titre en entier sur une ligne. L'utilisateur peut la modifier en glissant la bordure de l'en-tête ; un double-clic sur la bordure revient à l'ajustement automatique. Les largeurs modifiées sont mémorisées dans `config.json`, par tableau (MR, Commits, Statistiques). S'applique aux trois tableaux. |

### 6.3 Pagination

| Réf. | Exigence |
|---|---|
| PA-01 | Nombre total de MR affiché. |
| PA-02 | Navigation par pages, comme une page web. |
| PA-03 | Taille de page choisie dans l'IHM : 20 / 50 / 100, défaut 20. |

## 7. Règles de contrôle du process

### 7.1 Règles personnalisées

L'utilisateur ajoute autant de règles qu'il le souhaite dans l'onglet Config.

| Réf. | Exigence |
|---|---|
| RP-01 | Une règle = nom, champ inspecté, regex, condition, pondération, case « Active ». |
| RP-02 | Champs inspectables : titre, description, branche source, branche cible, messages des commits de la MR. |
| RP-03 | Condition : « doit correspondre » ou « ne doit pas correspondre ». |
| RP-04 | Messages de commits : OK seulement si **tous** les commits de la MR respectent la condition ; l'infobulle du KO liste les SHA fautifs. Nécessite une requête GitLab par MR (mise en cache). |
| RP-05 | Une règle désactivée n'est ni affichée, ni comptée dans le score. |
| RP-06 | Chaque règle active a sa colonne OK / KO dans le tableau, compte dans le score selon sa pondération et dans les statistiques (nombre de KO). |
| RP-07 | Règles pré-remplies à la création : « Titre conforme » (titre, doit correspondre) et « Lien ticket » (description, doit correspondre), regex à compléter. Elles remplacent les anciennes RC-01 et RC-02. |
| RP-08 | Regex validées avant enregistrement (OC-07). Une règle active sans regex est KO (« regex non configurée »). |

### 7.2 Règles fixes

| Réf. | Critère | OK si | KO si | N/A si |
|---|---|---|---|---|
| RC-03 | Correspondance ticket | Le n° extrait du titre = le n° extrait du lien. | N° différents, ou absent du titre ou du lien (infobulle précisant le cas). | — |
| RC-04 | Non mergée par l'auteur | Mergeur et auteur sont des personnes différentes (voir 5.4). | Même personne, quel que soit le compte. | MR non mergée. |

Les regex du lien et du n° de ticket de RC-03 sont dans un bloc dédié « Correspondance ticket » de l'onglet Config.

**Score** = somme des pondérations des critères OK (règles personnalisées actives + RC-03 + RC-04) / somme des pondérations des critères applicables (hors N/A) × 100.

## 8. Statistiques par auteur

| Réf. | Exigence |
|---|---|
| ST-01 | Onglet dédié « Statistiques ». |
| ST-02 | Une ligne par auteur : nombre de MR, score moyen, nombre de KO par critère (règles personnalisées actives, RC-03, RC-04). |
| ST-03 | MR prises en compte : tous états (mergées, ouvertes, fermées), hors Draft. |
| ST-04 | Filtres propres à l'onglet : période sur la date de création, dépôts (sélection multiple parmi les dépôts suivis). |
| ST-05 | Période : deux dates `JJ/MM/AAAA` + raccourcis « 7 jours », « 30 jours », « Mois en cours », « Année en cours » + bouton « Total » (sans limite de date). |
| ST-06 | Le filtre par auteur (FI-09) s'applique aussi à cet onglet. |
| ST-07 | Tri par colonne. |
| ST-08 | Colonne « Délai moyen création → merge » par personne, en jours avec une décimale (ex. 2,2 j), calculé sur les MR mergées uniquement. |
| ST-09 | Courbe d'évolution du score moyen par semaine, dessinée en `Canvas` : une courbe globale + une courbe par personne sélectionnée dans le filtre auteurs. |
| ST-10 | Semaine d'une MR déterminée par sa date de création ; la courbe suit les filtres de l'onglet (période, dépôts, auteurs) et les couleurs du thème. |

## 9. Commits hors MR

Objectif : détecter les commits poussés directement sur une branche, sans passer par une MR.

| Réf. | Exigence |
|---|---|
| CO-01 | Onglet séparé « Commits hors MR ». |
| CO-02 | Branche contrôlée : une par dépôt, définie dans `config.json`. |
| CO-03 | Période : mêmes dates que le filtre MR. Si l'état Ouvertes / Fermées est actif, les dernières dates saisies s'appliquent. |
| CO-04 | Date utilisée : date de commit (heure locale). |
| CO-05 | Un commit est « hors MR » s'il n'est associé à aucune MR dans GitLab. Les commits de merge générés par une MR ne sont pas signalés. |
| CO-06 | Colonnes : Dépôt, SHA court, Message, Auteur, Date de commit. |
| CO-07 | Clic sur un commit : ouverture de sa page GitLab dans le navigateur. |
| CO-08 | La détection interroge GitLab commit par commit : une barre de progression est affichée. Les longues périodes sont acceptées. |

## 10. Chargement, cache et rafraîchissement

| Réf. | Exigence |
|---|---|
| CH-01 | Les appels GitLab s'exécutent en tâche de fond ; l'IHM reste réactive. |
| CH-02 | Indicateur de chargement visible pendant les appels. |
| CH-03 | Cache en mémoire pour la session : le changement de page ou de tri ne réinterroge pas GitLab. |
| CH-04 | Un changement de filtre ou de dates déclenche une nouvelle requête. |
| CH-05 | Bouton **Rafraîchir** : vide le cache et recharge les données. |

## 11. Gestion des erreurs

| Réf. | Exigence |
|---|---|
| ER-01 | Notification par bandeau coloré dans l'application, refermable. |
| ER-02 | Message clair et spécifique : token invalide ou expiré, droits insuffisants, réseau coupé / instance injoignable, erreur de certificat SSL, dépôt ou branche introuvable. |
| ER-03 | Une erreur n'interrompt pas l'application ; l'utilisateur peut corriger puis rafraîchir. |
| ER-04 | Toutes les erreurs passent par le bandeau de notification (pas de fichier de log). |
| ER-05 | Limitation de débit GitLab (HTTP 429) et timeout réseau (30 s) : 3 nouvelles tentatives automatiques après 2, 4 puis 8 s, puis notification. Valeurs fixes. |

## 12. Architecture du code

### 12.1 Principes

| Réf. | Exigence |
|---|---|
| AR-01 | Découpage par couches : `api`, `core`, `ui`, `config`. Une couche ne dépend que des couches inférieures (`ui` → `core` → `api`). |
| AR-02 | Code, noms et commentaires en anglais. |
| AR-03 | Commentaires synthétiques et logiques : docstring courte pour chaque module, classe et fonction publique ; commentaire en ligne uniquement pour la logique non évidente. |
| AR-04 | Annotations de type partout. |
| AR-05 | Tests unitaires avec `unittest` : règles de contrôle et classe API (réponses HTTP simulées). |
| AR-06 | `README.md` en anglais : prérequis, installation, configuration, utilisation. |

### 12.2 Arborescence

```
gitective/
├── main.py                 # Entry point
├── README.md               # Installation and usage (English)
├── config.json             # Created on first launch
├── avatars/                # Avatar disk cache
├── gitective/
│   ├── assets/
│   │   ├── logo.svg        # Logo source
│   │   ├── logo.png        # In-app logo
│   │   └── logo.ico        # Window icon
│   ├── api/
│   │   ├── client.py       # GitLabClient: generic GitLab REST API wrapper
│   │   ├── models.py       # Project, MergeRequest, Commit, User (dataclasses)
│   │   └── errors.py       # GitLabError hierarchy
│   ├── core/
│   │   ├── rules.py        # Custom rules, RC-03, RC-04 and score
│   │   ├── orphan_commits.py # Commits-without-MR detection
│   │   ├── cache.py        # Session cache
│   │   ├── stats.py        # Per-author statistics, lead time, weekly scores
│   │   ├── people.py       # Account-to-person mapping
│   │   ├── avatars.py      # Avatar download, disk cache, initials fallback
│   │   └── dates.py        # Date parsing, "since yesterday", local timezone
│   ├── config/
│   │   └── settings.py     # Load/save config.json, defaults
│   └── ui/
│       ├── app.py          # Main window, tabs
│       ├── settings_tab.py # Config tab, connection test, regex tester
│       ├── stats_tab.py    # Per-author statistics
│       ├── chart.py        # Weekly score line chart (Canvas)
│       ├── wizard.py       # First-launch wizard
│       ├── themes.py       # Light, Dark, Windows 95, Matrix
│       ├── filters.py      # State/date filters, refresh button
│       ├── grid.py         # Custom colored grid, sorting, tooltips
│       ├── pagination.py   # Pager
│       ├── notifications.py# Error banner
│       └── worker.py       # Background tasks and progress
└── tests/
    ├── test_rules.py
    └── test_client.py
```

### 12.3 Classe API GitLab

Classe `GitLabClient`, générique et réutilisable, indépendante de l'application.

| Réf. | Exigence |
|---|---|
| API-01 | Construction : URL de l'instance, token, option de vérification SSL. |
| API-02 | Basée sur `urllib.request` ; en-tête `PRIVATE-TOKEN`. |
| API-03 | Gestion transparente de la pagination GitLab. |
| API-04 | Renvoie des objets métier typés (`Project`, `MergeRequest`, `Commit`, `User`), pas de JSON brut. |
| API-05 | Lève des exceptions dédiées : authentification, droits, ressource introuvable, réseau, SSL. |
| API-06 | Méthodes minimales : lister les projets accessibles ; lister les MR d'un projet (état, dates) ; lister les commits d'une MR ; lister les commits d'une branche (dates) ; lister les MR associées à un commit. |

## 13. Jalons

| Jalon | Contenu |
|---|---|
| J1 | Application exécutée par Python installé (périmètre de ce document). |
| J2 (futur) | Exécutable Windows autonome. |

## 14. Points ouverts

Aucun.
