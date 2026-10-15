# Gitective — Spécification technique

Contrôle des Merge Requests GitLab

Version : 1.12 (brouillon) — 15/10/2026

## 1. Objet

**Gitective** (Git + detective) est une application de bureau permettant de contrôler le respect du process sur les Merge Requests (MR) des dépôts GitLab choisis par l'utilisateur, de détecter les commits poussés sans MR, et de préparer une livraison multi-dépôts (changelog, branche et tag poussés). L'interface s'adapte aux droits du token : profil **Développeur** ou **Mergeur** (5.7).

## 2. Contraintes techniques

| Réf. | Exigence |
|---|---|
| CT-01 | Langage : Python 3.11 minimum. |
| CT-02 | Bibliothèque standard uniquement (aucun module externe, aucun téléchargement). Ex. : `tkinter`, `urllib`, `json`, `re`, `ssl`, `sqlite3`, `webbrowser`, `datetime`, `threading`, `subprocess`, `unittest`. |
| CT-03 | Système cible : Windows, Python déjà installé sur le poste. |
| CT-04 | GitLab auto-hébergé : URL de l'instance configurable. |
| CT-05 | Authentification API par Personal Access Token GitLab, droits `read_api` uniquement. Les opérations Git de la Livraison (clone, push) utilisent les identifiants Git du poste (LI-29). |
| CT-06 | Token et paramètres stockés en clair dans `config.json`, à côté de l'application. |
| CT-09 | IHM : `tkinter` + `ttk` (inclus dans Python). |
| CT-07 | Dates affichées et filtrées dans le fuseau horaire local du PC. |
| CT-08 | Vérification SSL active par défaut ; option de configuration pour la désactiver. |
| CT-11 | Git for Windows installé sur le poste, requis uniquement pour les clones et le push de l'onglet Livraison (11.4). |
| CT-10 | Données GitLab stockées dans une base locale SQLite unique, `gitective.db`, à côté de l'application (voir section 12). C'est le seul cache de l'application. |

## 3. Configuration

Fichier `config.json`, dans le dossier de l'application, contenant :

| Paramètre | Valeur par défaut |
|---|---|
| URL de l'instance GitLab | — |
| Token personnel | — |
| Vérification SSL | activée |
| Dépôts sélectionnés (sauvegardés depuis l'IHM) | aucun |
| Branche surveillée par dépôt (commits hors MR) | — |
| CI attendue, par dépôt (RC-05) | non |
| Règles personnalisées (voir 7.1) | 2 règles pré-remplies : « Titre conforme », « Lien ticket » |
| Correspondance ticket : regex du lien et regex du n° de ticket | — |
| Pondération des règles fixes (RC-03, RC-04, RC-05, RC-06) | 25 chacune |
| Règle RC-06 « Mergée par l'assigné » active (case à cocher) | non |
| Seuils de couleur du score | vert = 100 %, orange ≥ 50 %, rouge < 50 % |
| Correspondances personnes ↔ comptes | aucune |
| Requêtes GitLab simultanées (1 à 16) | 6 |
| Thème | Default |
| Synchronisation automatique de la base (CH-13) | 5 minutes |
| Notifications de bureau (NO-01) : nouveaux merges / MR qui me sont assignées ou en relecture / mes MR mergées | activées / activées / activées |
| Derniers filtres utilisés (état, dates, auteurs, mergeurs, assignés, relecteurs, brouillons, dépôts, taille de page) | Mergées « Depuis hier », 20 |
| Vue de l'onglet Statistiques (par personne / par dépôt) | Par personne |
| Largeurs de colonnes modifiées | aucune (ajustement au titre) |
| Largeur du panneau de détail (DE-02) | 420 px |
| Livraison en cours : mode, nom, dépôts, branches de départ et tags (voir 11.1) | aucune, mode Version |
| Dossier des clones (LI-24) | — |
| Nom de branche par mode, suivi du Tag actuel (LI-25) | Version : `version/` ; Release : `release/` |
| Protocole de clone : HTTPS ou SSH (LI-29) | HTTPS |
| Chemin de l'exécutable `git` (LI-28) | `git` (PATH) |
| Changelog : commits hors MR inclus (LI-21) | oui |

`config.json` ne contient que des paramètres ; les données lues depuis GitLab sont dans `gitective.db`. Le profil (5.7) n'est pas un paramètre : il est recalculé depuis GitLab.

## 4. Sélection des dépôts

| Réf. | Exigence |
|---|---|
| SD-01 | L'IHM récupère depuis GitLab la liste des projets accessibles avec le token. |
| SD-02 | L'utilisateur coche les dépôts à contrôler. |
| SD-03 | La sélection est sauvegardée dans `config.json`. |
| SD-04 | La liste des projets accessibles est stockée dans `gitective.db`, avec sa date de lecture. Si elle existe pour l'instance configurée, la fenêtre de sélection s'ouvre instantanément depuis la base. |
| SD-05 | Bouton « Recharger la liste » : relit la liste depuis GitLab et met la base à jour. Les coches en cours sont conservées. |
| SD-06 | Lecture GitLab : 100 projets par page, réponse allégée (`simple=true`), pages 2 à N lues en parallèle selon le réglage de requêtes simultanées (CH-06). |
| SD-07 | Recherche instantanée dans la liste ; les dépôts cochés sont affichés en tête. Liste affichable pour plusieurs milliers de dépôts sans ralentissement. |
| SD-08 | Pour chaque dépôt coché : case « CI attendue » (RC-05), à côté de la branche surveillée. |

## 5. Onglet Config, thèmes et identité

### 5.1 Onglet Config

| Réf. | Exigence |
|---|---|
| OC-01 | Onglet « Config » dans l'application, permettant de modifier tous les paramètres de la section 3. |
| OC-02 | Token : champ masqué + bouton « Afficher ». |
| OC-03 | Enregistrement dans `config.json`. |
| OC-04 | Choix du thème parmi une liste figée (voir 5.2) ; s'applique à tous les onglets, Vue d'ensemble comprise. |
| OC-05 | Bouton « Tester la connexion » : vérifie URL + token, résultat affiché par le bandeau de notification. |
| OC-06 | Testeur de regex : saisie d'exemples (titre, description, branches, messages de commits), affichage immédiat OK / KO de chaque règle active et de RC-03 avec le n° de ticket extrait. |
| OC-07 | Validation des regex avant enregistrement ; une regex invalide bloque l'enregistrement et est signalée par le bandeau. |
| OC-08 | Gestion des correspondances personnes ↔ comptes (voir 5.4). |
| OC-10 | Bloc « Livraison » : nom de branche par mode (LI-25), validé selon les règles Git avant enregistrement ; protocole de clone ; chemin de `git` avec bouton « Tester » (affiche la version de Git). |
| OC-11 | Affichage en lecture seule de l'utilisateur du token et du profil détecté (Développeur / Mergeur, avec la liste des dépôts où il peut merger). Bloc « Notifications » (trois cases, NO-01) ; en profil Développeur, seule la case « Ma MR mergée » est affichée. |
| OC-12 | Case « Lancer Gitective au démarrage de Windows (réduit) » : ajoute ou retire une entrée dans la clé de registre de l'utilisateur `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` (module `winreg`, sans droits administrateur), qui lance `pythonw main.pyw --minimized`. L'application démarre réduite dans la barre des tâches, synchronisation et notifications actives. Réglage lu dans le registre, pas dans `config.json` ; case grisée hors Windows. |
| OC-09 | Bouton « Vider la base locale » : supprime toutes les données de `gitective.db` après confirmation (voir CH-10). |

### 5.2 Thèmes (DA)

| Réf. | Thème | Description |
|---|---|---|
| TH-00 | Default | Thème par défaut. Sombre et soigné : fond bleu nuit, cartes ardoise, accent turquoise, scores menthe / ambre / corail, coins arrondis. |
| TH-01 | Clair | Classique et minimaliste. |
| TH-02 | Sombre | Classique et minimaliste. |
| TH-03 | Windows 95 | Gris, reliefs biseautés, police système rétro. |
| TH-04 | Matrix | Fond noir, texte vert, police monospace. |

Chaque thème définit : fonds, textes, bordures, rayons des coins, police, accent et accent secondaire, couleurs OK / KO / N/A et couleurs des niveaux de score, dégradé d'intensité (merges par jour). Thèmes non modifiables. Appliqués via `ttk.Style` et la grille personnalisée.

Les couleurs OK / KO / N/A sont adaptées à chaque thème (ex. Matrix : vert vif / vert sombre / gris). Les libellés texte « OK », « KO », « N/A » restent affichés pour garantir la lisibilité quelle que soit la couleur.

Badges (6.5) : fond, bordure, coins et police des cartes du thème ; icône Assigné (merge) en couleur d'accent, icône Relecteur (œil) en accent secondaire ; pastille des nouvelles en couleur « score rouge » ; badge à 0 en couleur N/A. Icônes et libellés identiques dans tous les thèmes, dessinés en `Canvas` (pas de police d'icônes).

| Thème | Accent / accent secondaire | Pastille | Forme des badges |
|---|---|---|---|
| Default | turquoise / bleu clair | corail | coins arrondis |
| Clair | bleu / violet | rouge | coins légèrement arrondis, fond blanc |
| Sombre | bleu / violet clair | rouge | coins légèrement arrondis, fond gris foncé |
| Windows 95 | bleu marine / sarcelle | rouge vif | bouton biseauté en relief, coins carrés, police système |
| Matrix | vert vif / vert pâle | vert vif, texte noir | coins carrés, police monospace ; badges distingués par l'icône et le libellé |

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
| AV-07 | Images stockées dans `gitective.db` (contenu binaire) ; retéléchargées au bouton Rafraîchir. |

### 5.6 Assistant de premier lancement

| Réf. | Exigence |
|---|---|
| AS-01 | Affiché au premier lancement (absence de `config.json`). |
| AS-02 | Étapes : URL de l'instance → token → test de connexion → choix des dépôts. |
| AS-03 | Passable à tout moment ; relançable depuis l'onglet Config. |

### 5.7 Profil Développeur / Mergeur

L'interface dépend des droits du compte propriétaire du token.

| Réf. | Exigence |
|---|---|
| PR-01 | L'utilisateur du token est lu via `GET /user` (ID, nom, administrateur ou non) au test de connexion, au démarrage et à chaque changement de token. |
| PR-02 | Profil **Mergeur** si l'utilisateur peut merger sur la branche surveillée d'au moins un dépôt suivi ; sinon profil **Développeur**. Dépôt sans branche surveillée : ignoré (comme ST-11). |
| PR-03 | Droit de merge sur un dépôt : même calcul que ST-11 — membres du projet (héritage des groupes inclus, `GET /projects/:id/members/all`) croisés avec les règles de branche protégée de la branche surveillée (rôle minimal autorisé à merger, utilisateurs nommés ; branche non protégée : Developer et plus). Administrateur de l'instance (`is_admin` de `GET /user`) : Mergeur. Ces lectures fonctionnent avec `read_api`. |
| PR-04 | Profil recalculé à chaque synchronisation (CH-05, CH-13) et à l'ajout ou au retrait d'un dépôt suivi ; un changement de profil s'applique immédiatement, sans redémarrage. |
| PR-05 | Profil **Développeur** : IHM actuelle, sans la colonne « Nouvelle » ni les MR de dépôts non suivis (6.4), sans les badges (6.5) ; seule notification de bureau : « Ma MR mergée » (NO-09). |
| PR-06 | Profil **Mergeur** : IHM du Développeur + suivi de ses MR à merger dans l'état Ouvertes (6.4), badges et toutes les notifications de bureau. |
| PR-07 | Instance injoignable (CH-08) : dernier profil connu, stocké en base. |

### 5.8 Notifications de bureau

| Réf. | Exigence |
|---|---|
| NO-01 | Trois types, chacun activable dans l'onglet Config : **nouveau merge** (MR mergée sur un dépôt suivi) et **MR assignée / relecture demandée** (MR ou rôle de l'utilisateur qui apparaît, 6.4, tous dépôts), en profil Mergeur ; **ma MR mergée** (NO-09), tous profils. |
| NO-08 | Le titre de la notification indique le rôle : « MR assignée », « Relecture demandée » ou « MR assignée + relecture ». |
| NO-09 | **Ma MR mergée** : MR d'un dépôt suivi dont l'utilisateur du token est l'auteur (comparaison par personne, 5.4), passée à l'état mergé depuis la synchronisation précédente. Titre « Votre MR a été mergée » ; contenu NO-03, mergeur compris. Une MR qui déclencherait aussi « nouveau merge » ne produit qu'une notification, celle-ci. Données déjà synchronisées (CH-05) : aucune requête supplémentaire. Limite : MR des dépôts non suivis non couvertes. |
| NO-02 | Affichage : petite fenêtre `tkinter` sans bordure (`Toplevel`, `overrideredirect`, `-topmost`), dans le coin bas-droit de l'écran, aux couleurs du thème. Visible par-dessus les autres applications, y compris quand Gitective est réduit. Disparaît après 8 s ; survol = reste affichée. |
| NO-03 | Contenu : type, titre de la MR, puis les personnes sur leur propre ligne (« auteur → mergeur » pour un merge, « par auteur » pour une MR assignée ou en relecture), puis le dépôt avec, à droite, le score de la MR (« Score 75 % », pastille aux couleurs de son niveau, seuils de la section 3). Le liseré gauche et le libellé du type prennent la couleur du niveau de score ; une synthèse (NO-05), sans score propre, garde la couleur de son type. Score calculé localement à la synchronisation (CH-07). Clic = ouverture de la MR dans le navigateur ; croix = fermeture ; roue crantée sous la croix (NO-10). |
| NO-10 | Roue crantée « ⚙ » en haut à droite, sous la croix, sur chaque notification (synthèses comprises). Clic : Gitective restauré et mis au premier plan, onglet Config ouvert et défilé jusqu'au bloc « Notifications », bloc et cases visibles du profil mis en surbrillance (bordure, titre et libellés en couleur d'accent du thème) pendant 6 s ; la notification se ferme. Aucun réglage n'est modifié. |
| NO-04 | Détection après chaque synchronisation (CH-13 ou Rafraîchir), par comparaison avec la base avant synchronisation. Pas de notification pour ses propres merges ni à la toute première synchronisation. |
| NO-05 | Au plus 3 notifications empilées ; au-delà, une notification de synthèse (ex. « 7 nouveaux merges »), clic = ouverture de Gitective sur l'onglet Merge Requests. |
| NO-06 | En complément, la fenêtre réduite clignote dans la barre des tâches (`FlashWindowEx` via `ctypes`, bibliothèque standard) pour les MR assignées. |
| NO-07 | Limites : Gitective doit être lancé (réduit accepté, fermé non) ; les notifications n'apparaissent pas dans le centre de notifications Windows (nécessiterait un module externe, CT-02). |

## 6. Filtres et affichage des MR

### 6.1 Filtres

| Réf. | Exigence |
|---|---|
| FI-01 | Filtre d'état exclusif (un seul à la fois) : **Mergées**, **Ouvertes**, **Fermées**, **Commits directs** (voir section 10). |
| FI-02 | **Mergées** : filtre entre deux dates, appliqué sur la date de merge. |
| FI-03 | Saisie des dates au format `JJ/MM/AAAA`, journées entières : date de début 00:00:00 → date de fin 23:59:59 incluses. |
| FI-04 | **Mergées** : raccourci « Depuis hier » = hier 00:00 → maintenant. |
| FI-05 | **Ouvertes** et **Fermées** : aucun filtre de date, liste complète. |
| FI-06 | Les derniers filtres sont mémorisés dans `config.json` et restaurés au lancement. |
| FI-07 | Sans filtre mémorisé, la vue de lancement est **Mergées « Depuis hier »**. |
| FI-08 | MR en brouillon (Draft) : affichées dans l'onglet Merge Requests (états **Ouvertes** et **Fermées**), jamais comptées ailleurs (score moyen TA-03, Statistiques, Vue d'ensemble, badges, notifications). |
| FI-16 | Indicateur Draft : étiquette « BROUILLON » devant le titre, couleur N/A du thème, et ligne entière en texte atténué. Infobulle : « MR en brouillon : pas prête à merger ». Score affiché pour information. |
| FI-17 | Filtre **Brouillons**, choix exclusif : **Inclus** (défaut), **Exclus**, **Seulement**. Actif pour **Ouvertes** et **Fermées** (grisé sinon, une MR mergée n'étant jamais en brouillon). Se combine avec les autres filtres (ET). Mémorisé (FI-06). Le clic sur un badge (BA-02) le remet à « Inclus ». |
| FI-09 | Filtre par auteur, sélection multiple (tous par défaut). Actif pour tous les états (**Mergées**, **Ouvertes**, **Fermées**, **Commits directs**), jamais grisé ; liste des auteurs construite depuis les MR (ou commits) de l'état affiché. S'applique aussi à l'onglet Statistiques. |
| FI-10 | Raccourci **F5** = Rafraîchir. |
| FI-11 | Filtre par dépôt, sélection multiple parmi les dépôts suivis (tous par défaut). S'applique aussi à l'état Commits directs. Mémorisé comme les autres filtres (FI-06). |
| FI-12 | Recherche texte instantanée, insensible à la casse : MR (titre, description, auteur, mergeur, dépôt, branches) et état Commits directs (message, SHA, auteur, dépôt). Non mémorisée. |
| FI-13 | Filtre par mergeur, sélection multiple regroupée par personne (toutes par défaut), parmi les mergeurs des MR chargées. Actif uniquement pour l'état **Mergées** (grisé sinon). Se combine avec le filtre auteur (ET). Mémorisé (FI-06). |
| FI-14 | Filtre par **assigné**, sélection multiple regroupée par personne (tous par défaut), parmi les assignés des MR chargées, plus l'entrée « Non assignée ». Actif pour les états **Mergées**, **Ouvertes** et **Fermées** (grisé pour Commits directs). Une MR est retenue si l'un de ses assignés est sélectionné. Mémorisé (FI-06). |
| FI-15 | Filtre par **relecteur**, mêmes règles que FI-14 (entrée « Sans relecteur », mêmes états). Les filtres auteur, assigné, relecteur et dépôt se combinent (ET). Données déjà lues par la synchronisation (champs assignés et relecteurs des MR, CH-03) : aucune requête supplémentaire. |

### 6.2 Tableau

Grille personnalisée (cellules colorées individuellement). Colonnes :

| Colonne | Contenu |
|---|---|
| Dépôt | Nom du dépôt de la MR |
| Titre | Titre de la MR — **simple clic = ouverture de la MR dans le navigateur web par défaut** |
| Auteur | Auteur de la MR |
| Assignés | Personnes assignées à la MR, séparées par des virgules (vide si aucune) |
| Relecteurs | Relecteurs de la MR, séparés par des virgules (vide si aucun) |
| Mergeur | Utilisateur ayant mergé (vide si non mergée) ; signalé s'il n'est pas l'assigné (TA-05) |
| Date de création | Heure locale |
| Date de merge | Heure locale (vide si non mergée) |
| Une colonne par règle personnalisée active | OK vert / KO rouge |
| Correspondance ticket | OK vert / KO rouge |
| Non mergée par l'auteur | OK vert / KO rouge / N/A gris |
| Pipeline vert | OK vert / KO rouge / N/A gris |
| Mergée par l'assigné | OK vert / KO rouge / N/A gris — colonne présente seulement si RC-06 est active |
| Nouvelle | Pastille (profil Mergeur, état Ouvertes uniquement, AM-04) |
| Score | Pourcentage, couleur vert / orange / rouge selon seuils |

| Réf. | Exigence |
|---|---|
| TA-01 | Survol d'une cellule KO : infobulle affichant le détail de l'erreur (ex. « PROJ-12 (titre) ≠ PROJ-21 (lien) »). |
| TA-02 | Clic sur un en-tête de colonne : tri sur toute la liste filtrée (croissant / décroissant), puis repagination. |
| TA-03 | Score moyen affiché en en-tête, calculé sur toute la liste filtrée. |
| TA-05 | Mergée par un non-assigné : si la MR a au moins un assigné et que le mergeur n'est aucun d'eux (comparaison par personne, 5.4), la cellule Mergeur est mise en évidence (couleur d'avertissement du thème + icône « ≠ ») ; infobulle : « Mergée par X, assignée à Y ». Affiché que RC-06 soit active ou non ; le score n'est impacté que par RC-06. MR sans assigné : pas de signalement. |
| TA-04 | Largeur des colonnes : à l'ouverture, chaque colonne s'ajuste pour afficher son titre en entier sur une ligne. L'utilisateur peut la modifier en glissant la bordure de l'en-tête ; un double-clic sur la bordure revient à l'ajustement automatique. Les largeurs modifiées sont mémorisées dans `config.json`, par tableau (MR, Commits directs, Statistiques par personne, Statistiques par dépôt, Livraison). S'applique aux cinq tableaux. |

### 6.3 Pagination

| Réf. | Exigence |
|---|---|
| PA-01 | Nombre total de MR affiché. |
| PA-02 | Navigation par pages, comme une page web. |
| PA-03 | Taille de page choisie dans l'IHM : 20 / 50 / 100, défaut 20. |

### 6.4 Mes MR à merger (profil Mergeur)

Objectif : voir d'un coup d'œil les merges qu'il reste à faire, sans onglet supplémentaire : tout passe par l'état **Ouvertes** de l'onglet Merge Requests.

| Réf. | Exigence |
|---|---|
| AM-01 | Pas de sous-onglet. Les deux badges (6.5) mènent à l'état **Ouvertes** filtré sur l'utilisateur du token, comme assigné ou comme relecteur (BA-02). |
| AM-02 | Données : à chaque synchronisation (CH-05, CH-13), lecture des MR ouvertes, brouillons compris, de **tous les dépôts** accessibles au token (suivis ou non), dont l'utilisateur est **assigné** ou **relecteur** : `GET /merge_requests?scope=all&state=opened&assignee_id=<moi>` et `…&reviewer_id=<moi>` (2 requêtes paginées, `read_api`). Une MR qui quitte ces résultats (mergée, fermée, désassignée) n'est plus comptée. |
| AM-08 | En profil Mergeur, l'état **Ouvertes** inclut ces MR même si leur dépôt n'est pas suivi : nom du dépôt suivi de « (non suivi) », dépôt proposé dans le filtre dépôts. Règles évaluées comme pour un dépôt suivi. |
| AM-07 | Rôle visible : les colonnes Assignés et Relecteurs (6.2) affichent le nom de l'utilisateur en gras, couleur d'accent du thème. Les filtres Assigné et Relecteur (FI-14, FI-15) proposent l'utilisateur en tête de liste sous la forme « Moi (nom) ». |
| AM-04 | Une MR est **nouvelle** pour un rôle (assigné ou relecteur) si l'utilisateur a reçu ce rôle depuis le dernier clic sur le badge correspondant ; une MR qui quitte l'état brouillon redevient nouvelle pour ses rôles (elle devient prête à merger). Pastille dans la colonne « Nouvelle » de l'état Ouvertes. Les couples MR / rôle déjà vus sont stockés en base ; le clic sur un badge marque vus les couples de son rôle uniquement. Les MR qui étaient nouvelles au moment du clic gardent leur pastille jusqu'au clic suivant, pour rester repérables dans la liste affichée. |
| AM-06 | Score coloré et infobulles KO (TA-01) disponibles avant le merge ; RC-04, RC-05 et RC-06 sont N/A (MR non mergée). |

### 6.5 Badges des MR en attente (profil Mergeur)

| Réf. | Exigence |
|---|---|
| BA-01 | Deux badges côte à côte en haut à droite de la fenêtre, visibles sur tous les onglets : **Assigné** et **Relecteur**, chacun avec son icône (merge / œil) et son libellé, aux couleurs du thème (5.2). Chacun affiche le nombre de MR ouvertes, hors brouillons, où l'utilisateur a ce rôle, et une pastille du nombre de nouvelles de ce rôle (AM-04), masquée à 0. Une MR aux deux rôles compte dans les deux badges. Survol : détail (ex. « 3 assignées, dont 1 nouvelle ; 1 brouillon »). |
| BA-02 | Clic sur un badge : onglet Merge Requests, état **Ouvertes**, filtre Assigné = l'utilisateur (badge Assigné) ou filtre Relecteur = l'utilisateur (badge Relecteur), l'autre de ces deux filtres remis à « tous » ; filtres auteur, dépôt et recherche remis à « tous », brouillons « Inclus ». Les filtres restent ensuite modifiables et sont mémorisés normalement (FI-06). Les MR du rôle deviennent vues (AM-04). |
| BA-03 | Le titre de la fenêtre (et donc la barre des tâches) reprend le total des nouvelles des deux rôles, une MR aux deux rôles comptant une fois : « Gitective (3) ». |
| BA-04 | Mis à jour après chaque synchronisation (CH-13, Rafraîchir) et au clic sur un badge. |

### 6.6 Panneau de détail d'une MR

Objectif : comprendre une MR et savoir si elle peut être mergée sans ouvrir GitLab. Tous profils, états Mergées, Ouvertes et Fermées.

| Réf. | Exigence |
|---|---|
| DE-01 | Ouverture : clic sur une ligne du tableau MR, hors colonne Titre (le clic sur le titre ouvre toujours GitLab, 6.2). La ligne sélectionnée est surlignée (fond de sélection + liseré d'accent à gauche). Flèches haut / bas : MR précédente / suivante, panneau mis à jour. Fermeture : croix ou Échap. |
| DE-02 | Panneau à droite du tableau, sur toute la hauteur de la zone tableau + pagination ; largeur par défaut 420 px, réglable en glissant son bord gauche, mémorisée dans `config.json`. Défilement vertical propre au panneau. Le tableau, les filtres et la pagination restent visibles et utilisables. |
| DE-03 | Panneau ouvert : les colonnes de règles (personnalisées, RC-03 à RC-06) sont masquées dans le tableau, leur détail étant dans le panneau ; Score reste affiché. Elles réapparaissent à la fermeture. |
| DE-04 | **En-tête** : titre (« BROUILLON » devant s'il y a lieu), puis `!iid · dépôt · branche source → branche cible` en police monospace, croix de fermeture. Étiquettes : état de merge (« Prête à merger » vert / « Pas prête à merger » corail, MR ouvertes uniquement), ancienneté (jours ouvrés, ST-14), « Nouvelle » (AM-04), « Mergée le … par … » pour une MR mergée, « Fermée le … » pour une MR fermée. |
| DE-05 | **Prête à merger ?** (MR ouvertes) : une ligne par point, icône OK / avertissement / KO aux couleurs du thème : conflits ; pipeline (dernier statut, nom du job ou de la CI) ; discussions bloquantes non résolues (nombre) ; approbations (reçues / requises, noms des approbateurs) ; retard de la branche source sur la cible (nombre de commits). « Pas prête » dès qu'un point est KO. |
| DE-06 | **Personnes** : auteur, assignés, relecteurs, mergeur si mergée ; l'utilisateur affiché « Moi » en couleur d'accent ; noms par personne (5.4). |
| DE-07 | **Score** : pourcentage coloré, puis une ligne par critère actif avec OK / KO / N/A ; le détail de chaque KO (TA-01) est écrit sous la ligne, sans survol. Critères N/A regroupés sur une ligne. |
| DE-08 | **Pipeline** : statut et âge du dernier pipeline du commit de tête ; jobs en échec (nom, statut, durée) ; pour le premier job en échec, les 3 à 8 dernières lignes significatives de son log, en monospace. Masqué s'il n'y a pas de pipeline. |
| DE-09 | **Discussions non résolues** : nombre, puis pour chacune l'auteur, l'emplacement (fichier:ligne ou « description ») et le début du premier message (2 lignes max). Masqué s'il n'y en a pas. |
| DE-10 | **Fichiers modifiés** : nombre, puis les fichiers triés par volume de changement, lignes ajoutées en vert / retirées en corail, monospace ; 5 premiers affichés, « + N autres fichiers » au-delà (clic = liste complète). Le diff détaillé reste dans GitLab. |
| DE-11 | Bouton « Ouvrir dans GitLab » en bas du panneau. |
| DE-12 | Données (`read_api`) : lues à l'ouverture du panneau, en tâche de fond ; la dernière copie en base s'affiche aussitôt. MR ouverte : relue une fois par synchronisation (CH-13), à la première ouverture qui suit. MR mergée ou fermée : relue seulement si la MR a changé (`updated_at`). Seule la fin du log du premier job en échec est conservée. Hors ligne : dernières données en base, avec leur date de lecture. |
| DE-13 | Approbations : nombre reçu et noms disponibles sur toutes les éditions ; nombre requis seulement si l'édition GitLab le fournit, sinon ligne « Approuvée par … » sans total. |

## 7. Règles de contrôle du process

### 7.1 Règles personnalisées

L'utilisateur ajoute autant de règles qu'il le souhaite dans l'onglet Config.

| Réf. | Exigence |
|---|---|
| RP-01 | Une règle = nom, champ inspecté, regex, condition, pondération, case « Active ». |
| RP-02 | Champs inspectables : titre, description, branche source, branche cible, messages des commits de la MR. |
| RP-03 | Condition : « doit correspondre » ou « ne doit pas correspondre ». |
| RP-04 | Messages de commits : OK seulement si **tous** les commits de la MR respectent la condition ; l'infobulle du KO liste les SHA fautifs. Nécessite une requête GitLab par MR (stockée en base, voir CH-09). |
| RP-05 | Une règle désactivée n'est ni affichée, ni comptée dans le score. |
| RP-06 | Chaque règle active a sa colonne OK / KO dans le tableau, compte dans le score selon sa pondération et dans les statistiques (nombre de KO). |
| RP-07 | Règles pré-remplies à la création : « Titre conforme » (titre, doit correspondre) et « Lien ticket » (description, doit correspondre), regex à compléter. Elles remplacent les anciennes RC-01 et RC-02. |
| RP-08 | Regex validées avant enregistrement (OC-07). Une règle active sans regex est KO (« regex non configurée »). |

### 7.2 Règles fixes

| Réf. | Critère | OK si | KO si | N/A si |
|---|---|---|---|---|
| RC-03 | Correspondance ticket | Le n° extrait du titre = le n° extrait du lien. | N° différents, ou absent du titre ou du lien (infobulle précisant le cas). | — |
| RC-04 | Non mergée par l'auteur | Mergeur et auteur sont des personnes différentes (voir 5.4). | Même personne, quel que soit le compte. | MR non mergée. |
| RC-05 | Pipeline vert | Au moment du merge, tous les statuts CI du dernier commit de la MR sont terminés en succès. | Au moins un statut en échec, annulé, ou encore en cours au moment du merge ; ou aucun statut. | MR non mergée, ou dépôt sans « CI attendue ». |
| RC-06 | Mergée par l'assigné (activable, désactivée par défaut) | Le mergeur est l'un des assignés de la MR (comparaison par personne, 5.4). | Le mergeur n'est aucun des assignés (infobulle : « Mergée par X, assignée à Y »). | MR non mergée, ou MR sans assigné. |

Les regex du lien et du n° de ticket de RC-03 sont dans un bloc dédié « Correspondance ticket » de l'onglet Config. Le bloc « Règles fixes » de l'onglet Config affiche la pondération de RC-03 à RC-06 et la case « Active » de RC-06.

**Détail de RC-05 :**

| Réf. | Exigence |
|---|---|
| PI-01 | Source : statuts du commit de tête de la MR (champ `sha`), lus via `GET /projects/:id/repository/commits/:sha/statuses?all=true`. Couvre GitLab CI et les CI externes qui publient leurs résultats dans GitLab (ex. Jenkins via le plugin GitLab, étape `gitlabCommitStatus` / `updateGitlabCommitStatus`). Aucun appel direct à Jenkins. |
| PI-02 | Pour chaque nom de statut, seul le dernier statut créé avant la date de merge est retenu. Il est OK s'il est `success` et terminé avant la date de merge. |
| PI-03 | Les statuts marqués `allow_failure` sont ignorés. |
| PI-04 | Infobulle du KO : nom du statut et cas (« jenkins : failed », « jenkins : en cours au merge », « aucun statut CI »). |
| PI-05 | Une requête par MR mergée, en parallèle (CH-06). Le résultat d'une MR mergée ne change plus : stocké en base, jamais relu. |
| PI-06 | La case « CI attendue » est réglée par dépôt (SD-08). Décochée, RC-05 est N/A pour toutes les MR du dépôt et n'est pas requêtée. |

RC-06 désactivée : ni colonne, ni score, ni statistiques (comme RP-05).

**Score** = somme des pondérations des critères OK (règles personnalisées actives + RC-03 + RC-04 + RC-05 + RC-06 si active) / somme des pondérations des critères applicables (hors N/A) × 100.

## 8. Statistiques

### 8.1 Commun

| Réf. | Exigence |
|---|---|
| ST-01 | Onglet dédié « Statistiques », avec un sélecteur **Par personne / Par dépôt** qui bascule entre deux tableaux. La vue choisie est mémorisée dans `config.json`. |
| ST-03 | MR prises en compte : tous états (mergées, ouvertes, fermées), hors Draft. |
| ST-04 | Filtres propres à l'onglet, communs aux deux vues : période sur la date de création, dépôts (sélection multiple parmi les dépôts suivis). |
| ST-05 | Période : deux dates `JJ/MM/AAAA` + raccourcis « 7 jours », « 30 jours », « Mois en cours », « Année en cours » + bouton « Total » (sans limite de date). |
| ST-06 | Le filtre par auteur (FI-09) s'applique aussi à cet onglet. |
| ST-07 | Tri par colonne, dans les deux vues. |
| ST-14 | Délais (ST-08, ST-12, SR-02) : médiane, en jours ouvrés (samedi et dimanche exclus, heure locale), une décimale (ex. 1,3 j). Survol : infobulle avec moyenne, minimum, maximum et nombre de MR. |

### 8.2 Vue par personne

| Réf. | Exigence |
|---|---|
| ST-02 | Une ligne par personne auteur ou mergeur d'au moins une MR, ou auteur d'au moins un commit direct : nombre de MR créées, nombre de MR mergées, score moyen (vide sans MR créée), nombre de KO par critère (règles personnalisées actives, RC-03, RC-04, RC-05, RC-06 si active), nombre de commits directs (ST-15). |
| ST-08 | Colonne « Délai création → merge » par personne (MR dont elle est l'auteur), calculé sur les MR mergées uniquement (voir ST-14). |
| ST-09 | Courbe d'évolution du score moyen par semaine, dessinée en `Canvas` : une courbe globale + une courbe par personne sélectionnée dans le filtre auteurs. |
| ST-10 | Semaine d'une MR déterminée par sa date de création ; la courbe suit les filtres de l'onglet (période, dépôts, auteurs) et les couleurs du thème. |
| ST-11 | Colonne « Rôle » : **Mergeur** si la personne (l'un de ses comptes) a le droit de merger sur la branche surveillée d'au moins un dépôt de l'onglet, **Dev** sinon. Survol de « Mergeur » : infobulle listant ces dépôts. Droits calculés via l'API : membres du projet (héritage des groupes inclus) croisés avec les règles de branche protégée (rôle minimal, utilisateurs nommés ; règle la plus permissive si plusieurs correspondent). Branche non protégée : Developer et plus. Non pris en compte : droits accordés à un groupe (Premium), administrateurs de l'instance. Dépôt sans branche surveillée : ignoré. Triable. |
| ST-12 | Colonne « Délai dernier commit → merge » (réactivité des mergeurs) : pour chaque MR mergée par la personne, date de merge − date du dernier commit de la MR (`committed_date` le plus récent). Une requête par MR mergée (commits de la MR, en parallèle, stockés en base). « N/A » si la personne n'est pas Mergeur (ST-11), « — » si elle n'a rien mergé sur la période. Limite connue : un rebase juste avant le merge réécrit la date du dernier commit et sous-estime le délai. |
| ST-13 | Les mergeurs apparaissent même sans MR créée sur la période ; leur délai couvre les MR de tous les auteurs, quel que soit le filtre auteur (qui ne filtre que les lignes affichées). |
| ST-15 | Colonne « Commits directs » : nombre de commits hors MR (section 10) dont la personne est l'auteur (PE-03), sur les branches surveillées des dépôts de l'onglet, date de commit dans la période. Si la détection n'a pas encore couvert toute la période, elle est lancée avec la barre de progression (CO-08). |

### 8.3 Vue par dépôt

| Réf. | Exigence |
|---|---|
| SR-01 | Second tableau : une ligne par dépôt suivi retenu par le filtre dépôts. |
| SR-02 | Colonnes : Dépôt, MR créées, MR mergées, score moyen, nombre de KO par critère (règles personnalisées actives, RC-03, RC-04, RC-05, RC-06 si active), commits directs, délai création → merge (ST-14). |
| SR-03 | Le filtre auteur restreint les MR et commits directs comptés (seuls ceux des personnes sélectionnées). |
| SR-04 | Courbe d'évolution du score moyen par semaine : une courbe globale + une courbe par dépôt sélectionné dans le filtre dépôts. Mêmes règles que ST-10. |
| SR-05 | Clic sur un dépôt : bascule vers la vue par personne, filtrée sur ce dépôt. |

## 9. Vue d'ensemble

Onglet de supervision, purement graphique, pensé pour un affichage permanent : comprendre l'état des dépôts d'un coup d'œil.

| Réf. | Exigence |
|---|---|
| VE-01 | Onglet « Vue d'ensemble », premier onglet, affiché au lancement. Aucun élément cliquable, aucun filtre : couvre tous les dépôts suivis, MR hors Draft. |
| VE-02 | Tient sans défilement sur un écran 1920 × 1080. Raccourci **F11** : plein écran activé / désactivé. |
| VE-03 | Redessinée après chaque synchronisation automatique (CH-13). En-tête : heure de la dernière synchronisation et délai avant la prochaine. |
| VE-04 | Disposition : colonne de gauche (≈ un tiers) = fil des derniers merges, puis merges par jour ; à droite, trois niveaux : score moyen + qualité par semaine / classement des dépôts / règles enfreintes + MR créées et mergées. |
| VE-05 | **Derniers merges**, élément principal : jusqu'à 40 dernières MR mergées, de la plus récente à la plus ancienne, groupées par jour. Ligne : heure de merge, titre, dépôt, auteur → mergeur, pastille de score colorée. Dès que les merges du jour ne tiennent pas sur deux lignes chacun, chaque merge passe sur une seule ligne, pour voir d'un coup une journée chargée (10 à 15 merges) ; le titre est coupé (45 caractères au plus, avec « … ») pour que le dépôt et les personnes restent toujours visibles. Groupe « Aujourd'hui » mis en évidence ; nombre de merges du jour en grand dans l'en-tête. Les plus anciennes sont coupées si la place manque. |
| VE-06 | **Merges par jour** : semaine en cours et semaine précédente, lundi → dimanche. Chaque case affiche le nombre de merges, teintée selon l'intensité ; total par semaine. Jours à venir en pointillés. |
| VE-07 | **Score moyen** : MR mergées des 30 derniers jours, couleur selon les seuils, écart en points avec les 30 jours précédents, barre 0 – 100. |
| VE-08 | **Qualité des MR mergées** : 12 dernières semaines complètes, barres empilées du nombre de MR à 100 %, 50 – 99 % et < 50 %. |
| VE-09 | **Classement des dépôts** : score moyen sur 30 jours, tri décroissant, rang, barre et valeur colorées. Réparti sur deux colonnes pour afficher 12 à 20 dépôts. |
| VE-10 | **Règles enfreintes** : nombre de KO par critère actif (règles personnalisées, RC-03, RC-04, RC-05, RC-06 si active) sur 30 jours, tri décroissant. |
| VE-11 | **MR créées / mergées** : 12 dernières semaines complètes, deux courbes, axe vertical gradué en nombre de MR. |
| VE-12 | Calculs locaux depuis `gitective.db`, sans requête GitLab supplémentaire. Dessin en `Canvas` et `ttk`, aux couleurs, rayons et police du thème actif (5.2). |

## 10. Commits directs (état de l'onglet Merge Requests)

Objectif : détecter les commits poussés directement sur une branche, sans passer par une MR.

| Réf. | Exigence |
|---|---|
| CO-01 | État « Commits directs » du filtre d'état de l'onglet Merge Requests (FI-01) ; il n'y a plus d'onglet séparé. Le tableau affiche alors les colonnes ci-dessous ; filtre mergeur, score et score moyen sont masqués. |
| CO-02 | Branche contrôlée : une par dépôt, définie dans `config.json`. |
| CO-03 | Période : champs de dates et raccourci « Depuis hier » du filtre (communs avec l'état Mergées). |
| CO-04 | Date utilisée : date de commit (heure locale). |
| CO-05 | Un commit est « hors MR » s'il n'est associé à aucune MR dans GitLab. Les commits de merge générés par une MR ne sont pas signalés. |
| CO-06 | Colonnes : Dépôt, Branche, SHA court, Message, Auteur, Date de commit. |
| CO-07 | Clic sur un commit : ouverture de sa page GitLab dans le navigateur. |
| CO-08 | La détection interroge GitLab commit par commit : une barre de progression est affichée. Les longues périodes sont acceptées. Le résultat de chaque commit est stocké en base : un commit déjà vérifié n'est jamais réinterrogé. |
| CO-09 | Pagination identique aux MR (20 / 50 / 100 par page, taille commune). |

## 11. Livraison

Objectif : préparer une livraison composée de plusieurs dépôts : calculer les MR mergées depuis le tag précédent de chaque dépôt, produire le changelog Markdown, puis cloner les dépôts en local et y pousser une branche de livraison (nom configuré + Tag actuel) et le Tag actuel.

### 11.1 Modes, composition et clones

| Réf. | Exigence |
|---|---|
| LI-01 | Onglet « Livraison », placé après l'onglet Statistiques. |
| LI-02 | Champ « Nom de la livraison » (ex. « 2026.10 »), repris en titre du changelog et dans le message des tags annotés (LI-35). |
| LI-23 | Sélecteur de mode **Version** / **Release**. Chaque mode a ses propres modèles de nom de branche et de nom de tag (LI-25) ; le reste du fonctionnement est identique (voir point ouvert, section 16). Le mode choisi est mémorisé. |
| LI-24 | Champ « Dossier des clones » (bouton « Parcourir… ») : chemin local dans lequel chaque dépôt est cloné, dans un sous-dossier portant le chemin GitLab du dépôt (ex. `<dossier>/groupe/depot`). Mémorisé dans `config.json`. |
| LI-03 | Bouton « Ajouter un dépôt » : choix parmi les dépôts suivis (SD-02), avec recherche instantanée. Un dépôt ne peut être ajouté qu'une fois. Chaque ligne a un bouton « Retirer » et peut être déplacée (haut / bas) : l'ordre des lignes est celui des sections du changelog. |
| LI-37 | Proposition du Tag actuel : le Tag précédent avec le **mineur incrémenté** et le patch remis à 0, préfixe et suffixe conservés (ex. `v1.3.2` → `v1.4.0`, `1.3` → `1.4`, `app-2.7.1` → `app-2.8.0`). Le numéro reconnu est le premier motif `majeur.mineur[.patch]` du nom. Recalculée quand le Tag précédent change, tant que l'utilisateur n'a pas modifié le Tag actuel à la main. Tag précédent vide ou sans numéro reconnu : Tag actuel vide, à saisir. |
| LI-26 | Pour chaque dépôt : liste déroulante **Branche de départ**, parmi les branches du dépôt. Par défaut : branche par défaut du dépôt dans GitLab (`default_branch`, en général `main`). |
| LI-04 | Pour chaque dépôt : deux listes déroulantes **Tag précédent** et **Tag actuel**, avec recherche par saisie. Tags triés du plus récent au plus ancien (date du commit pointé), date affichée à côté du nom. |
| LI-27 | Le **Tag actuel** est **propre à chaque dépôt** (chaque dépôt a son propre numéro) et saisissable librement : s'il n'existe pas dans le dépôt, il est marqué « nouveau » et doit être créé avec le bouton « Créer le tag » (LI-35) avant de pouvoir pousser. Il est pré-rempli par le Tag précédent incrémenté du mineur (LI-37), modifiable. Nom validé selon les règles Git (`git check-ref-format`). |
| LI-05 | À l'ajout d'un dépôt : Tag précédent = tag le plus récent ; Tag actuel = proposition LI-37 (nouveau tag). Dépôt sans tag : Tag précédent vide = depuis le premier commit. |
| LI-06 | Contrôle : le Tag précédent doit être un ancêtre du Tag actuel (ou, pour un nouveau tag, de la tête de la branche de départ). Sinon la ligne est signalée en erreur (infobulle) et exclue du changelog et du push. Aucun commit dans la différence : section « Aucun changement ». |
| LI-07 | La composition (mode, nom, dépôts, ordre, branches de départ, tags) est mémorisée dans `config.json` et restaurée au lancement. Bouton « Nouvelle livraison » : vide la composition après confirmation. |
| LI-08 | Tags et branches lus via `GET /projects/:id/repository/tags?order_by=updated` et `GET /projects/:id/repository/branches`, stockés en base ; relus au bouton Rafraîchir (CH-05) et au bouton « Recharger les tags » de l'onglet. |
| LI-25 | Noms, réglés dans l'onglet Config, par mode. **Branche de livraison** = nom de branche configurable du mode, suivi du Tag actuel du dépôt : `<nom de branche><tag actuel>` (le séparateur fait partie du nom configuré). Défauts : Version = `version/`, Release = `release/` ; ex. Release + tag `v1.4.0` → `release/v1.4.0`. La branche de livraison est donc propre à chaque dépôt : affichée par dépôt, en lecture seule, recalculée à chaque changement du Tag actuel. Nom final validé selon les règles Git. |

### 11.2 Détermination des MR

| Réf. | Exigence |
|---|---|
| LI-09 | Commits de la différence : `GET /projects/:id/repository/commits?ref_name=<précédent>..<cible>` (syntaxe de plage Git, paginée). Cible = Tag actuel s'il existe sur GitLab ; sinon SHA du commit du tag créé localement (LI-35) ; sinon tête de la branche de départ (aperçu avant création du tag). |
| LI-10 | Une MR mergée est retenue si son commit de merge (`merge_commit_sha`), son commit de squash (`squash_commit_sha`) ou l'un de ses commits figure dans la différence. Couvre les merges avec commit de merge, squash et fast-forward. |
| LI-11 | Rattachement local d'abord, depuis les MR et commits de MR en base. Les commits restants sont interrogés via « MR associées à un commit » (même requête et même résultat stocké que CO-05 / CH-09), en parallèle (CH-06), avec barre de progression. |
| LI-12 | Une MR n'apparaît qu'une fois par dépôt, même si plusieurs de ses commits sont dans la différence. Seules les MR à l'état mergé sont retenues. |
| LI-13 | Commits de la différence rattachés à aucune MR, hors commits de merge : listés à part comme **commits hors MR** de la livraison. |
| LI-14 | Le résultat est stocké en base, indexé par les SHA du Tag précédent et de la cible : non recalculé tant qu'ils pointent sur les mêmes commits ; recalculé si un tag a été déplacé ou si la branche de départ a avancé. |
| LI-15 | Les filtres de l'onglet Merge Requests (auteur, mergeur, dépôt, dates, recherche) ne s'appliquent pas : le changelog est toujours complet. |

### 11.3 Affichage et changelog

| Réf. | Exigence |
|---|---|
| LI-16 | Tableau de la livraison (grille personnalisée, TA-02 et TA-04) : Dépôt, N° de ticket, Titre (clic = ouverture de la MR), Auteur, Mergeur, Date de merge, Score. Puis les commits hors MR : Dépôt, SHA court (clic = ouverture du commit), Message, Auteur, Date de commit. Total MR et commits hors MR par dépôt et global. |
| LI-17 | Les MR dont le score est inférieur à 100 % restent incluses ; le score coloré et l'infobulle des critères KO permettent de les repérer avant livraison. |
| LI-18 | N° de ticket extrait du titre par la regex de RC-03 ; vide si absent. |
| LI-19 | Aperçu du changelog en texte, mis à jour à chaque changement de composition. |
| LI-20 | Changelog au format **Markdown** uniquement. Structure : titre `#` (mode, nom de la livraison, date du jour) ; puis une section `##` par dépôt, dans l'ordre de composition, « Dépôt : tag précédent → tag actuel (N MR) » ; dans chaque section, MR triées par date de merge, une ligne de liste par MR : `[N° ticket] Titre ([!iid](lien MR), auteur)` ; puis, si l'option est cochée, sous-section `###` « Commits hors MR » : `SHA court Message (auteur)`. Dépôt sans MR : « Aucune MR ». |
| LI-21 | Option : inclusion des commits hors MR (cochée par défaut), mémorisée dans `config.json`. |
| LI-22 | Boutons « Copier » (presse-papiers, via `tkinter`) et « Enregistrer… » (fichier `.md`, nom proposé à partir du mode et du nom de la livraison). |

### 11.4 Clones locaux et push

| Réf. | Exigence |
|---|---|
| LI-28 | Opérations Git exécutées par l'exécutable `git` du poste (Git for Windows), via `subprocess`, en tâche de fond (CH-01), dans le clone du dépôt. Chemin de `git` configurable (défaut : `git` trouvé dans le `PATH`). Aucune saisie interactive (`GIT_TERMINAL_PROMPT=0`) : un identifiant manquant produit une erreur. |
| LI-29 | Clone : bouton « Cloner » par dépôt et « Tout cloner ». Clone absent : `git clone` depuis l'URL du dépôt (HTTPS ou SSH, choix dans l'onglet Config). Clone présent : vérification que son `origin` est bien ce dépôt (sinon erreur, rien n'est modifié), puis `git fetch --tags --prune`. Authentification : identifiants Git du poste (gestionnaire d'identifiants Windows ou clé SSH) ; le token de l'application reste en `read_api` (CT-05). |
| LI-35 | Création du tag : bouton « Créer le tag » par dépôt et « Tout créer », actifs pour les Tag actuels marqués « nouveau ». Séquence : fetch (LI-29) ; création locale du Tag actuel, tag annoté (message : « <mode> <nom de la livraison> »), sur la tête de `origin/<branche de départ>`. Le tag n'est pas poussé par cette action. Le changelog du dépôt est recalculé sur le commit tagué (LI-09). |
| LI-36 | Un tag créé localement et pas encore poussé peut être supprimé par le bouton « Supprimer le tag local » (après confirmation), pour corriger un nom ou repartir d'un commit plus récent. Un tag déjà poussé n'est jamais supprimé (LI-32). |
| LI-30 | Push : bouton « Pousser » par dépôt et « Tout pousser », actifs seulement si le Tag actuel existe (créé localement par LI-35, ou déjà présent sur GitLab). Le push ne crée jamais de tag. Séquence : fetch (LI-29) ; création de la branche de livraison `<nom de branche><tag actuel>` (LI-25) sur le commit du Tag actuel ; `git push origin <branche> <tag>`. |
| LI-31 | Avant tout push, une fenêtre de confirmation liste, par dépôt, les commandes qui seront exécutées (branche de livraison, commit de départ, tag, distant). Rien n'est poussé sans validation. |
| LI-32 | Sécurité : jamais de push forcé ni de suppression de branche ou de tag distant. Branche de livraison déjà existante sur le distant : réutilisée si elle pointe sur le commit attendu, sinon erreur. Tag déjà existant sur le distant et pointant ailleurs : erreur. Clone avec des modifications locales non commitées : erreur, rien n'est modifié. |
| LI-33 | Colonne **État Git** par dépôt : Non cloné / Cloné / Tag créé (local) / Poussé / Erreur (infobulle avec la sortie d'erreur de `git`). Après un push réussi, les tags et branches du dépôt sont relus (LI-08) et le Tag actuel n'est plus marqué « nouveau ». |
| LI-34 | Le commit livré est figé à la création du tag (LI-35) : le changelog et la branche de livraison portent sur le commit tagué, même si la branche de départ avance ensuite. |

## 12. Chargement, base locale et rafraîchissement

| Réf. | Exigence |
|---|---|
| CH-01 | Les appels GitLab s'exécutent en tâche de fond ; l'IHM reste réactive. |
| CH-02 | Indicateur de chargement visible pendant les appels. |
| CH-03 | Base locale persistante `gitective.db` (SQLite, `sqlite3`) : projets accessibles, MR (dont assignés et relecteurs), commits de MR, commits des branches surveillées, résultats de détection hors MR, statuts CI, membres et branches protégées, utilisateurs et avatars, tags, branches, résultats de livraison (LI-14), utilisateur du token et profil (5.7), détails de MR du panneau (état de merge, approbations, discussions, pipeline et jobs, fin des logs en échec, fichiers modifiés, DE-12), MR ouvertes de tous les dépôts où l'utilisateur est assigné ou relecteur, et couples MR / rôle déjà vus (AM-02, AM-04). Les clones locaux (11.4) sont hors base, dans le dossier des clones. Le changement de page, de tri ou de filtre lit la base sans réinterroger GitLab. |
| CH-04 | Un changement de filtre ou de dates ne déclenche une requête GitLab que pour la partie de la période absente de la base. |
| CH-05 | Bouton **Rafraîchir** : mise à jour incrémentale depuis la dernière synchronisation de chaque dépôt (MR via `updated_after`, commits via `since`), relecture des tags, retéléchargement des avatars et recalcul du profil (PR-04). |
| CH-13 | **Synchronisation automatique**, tous profils : toutes les N minutes (réglable dans l'onglet Config, défaut 5), même fenêtre réduite, la mise à jour incrémentale des MR et commits de CH-05 et le recalcul du profil s'exécutent en tâche de fond (tags et avatars : au bouton Rafraîchir uniquement). Puis rafraîchissement de l'affichage, des badges (BA-04) et des notifications (NO-04). Ignorée si une synchronisation est déjà en cours. Instance injoignable : nouvel essai au cycle suivant, bandeau CH-08. |
| CH-06 | Les requêtes « une par commit » (commits hors MR, livraison) et « une par MR » (règles sur les commits, RC-05, ST-12) partent en parallèle ; le nombre de requêtes simultanées se règle dans l'onglet Config (1 à 16, défaut 6). |
| CH-07 | Les règles sont évaluées localement à partir des données en base : modifier une règle, une pondération ou une correspondance de personnes recalcule l'affichage sans requête GitLab. |
| CH-08 | Mode hors ligne : si l'instance est injoignable, l'application affiche les données en base et un bandeau indique la date de dernière synchronisation. |
| CH-09 | Données immuables jamais relues : commits d'une MR mergée, statuts CI d'une MR mergée (PI-05), résultat de détection d'un commit (CO-08, LI-11). |
| CH-10 | La base est liée à l'URL de l'instance. Un changement d'URL dans l'onglet Config propose de vider la base. |
| CH-11 | La base porte un numéro de version de schéma ; une version de l'application plus récente migre le schéma au démarrage. |
| CH-12 | Accès concurrents : une connexion SQLite par thread ; les écritures sont faites par les tâches de fond, en transactions. |

## 13. Gestion des erreurs

| Réf. | Exigence |
|---|---|
| ER-01 | Notification par bandeau coloré dans l'application, refermable. |
| ER-02 | Message clair et spécifique : token invalide ou expiré, droits insuffisants, réseau coupé / instance injoignable, erreur de certificat SSL, dépôt, branche ou tag introuvable, Git absent, échec d'une commande Git (clone, fetch, push refusé, identifiants manquants) avec la sortie de `git`. |
| ER-03 | Une erreur n'interrompt pas l'application ; l'utilisateur peut corriger puis rafraîchir. |
| ER-04 | Toutes les erreurs passent par le bandeau de notification (pas de fichier de log). Les erreurs de la synchronisation automatique (CH-13) ne déclenchent pas de notification de bureau. |
| ER-05 | Limitation de débit GitLab (HTTP 429) et timeout réseau (30 s) : 3 nouvelles tentatives automatiques après 2, 4 puis 8 s, puis notification. Valeurs fixes. |
| ER-06 | Base locale illisible, corrompue ou verrouillée : notification, et proposition de la recréer (resynchronisation complète depuis GitLab). |

## 14. Architecture du code

### 14.1 Principes

| Réf. | Exigence |
|---|---|
| AR-01 | Découpage par sujet, en trois niveaux : **`forge`** (requêtes GitLab) ← **métier** (`database`, `review`, `reporting`, `release`, `shared`, `settings`) ← **`ui`**. Un niveau ne dépend que des niveaux inférieurs. Le métier dépend uniquement de l'interface `ForgeClient` (14.3), jamais de `GitLabClient` ; seule l'IHM crée le client. |
| AR-07 | `forge` est isolé : il n'importe que la bibliothèque standard et ses propres modules. Il peut être copié tel quel dans un autre projet. |
| AR-08 | Noms explicites : un dossier par sujet, un fichier par fonctionnalité, nommé avec les termes de l'IHM (ex. `direct_commits.py` pour l'état « Commits directs »). Les tests reprennent les mêmes dossiers. |
| AR-02 | Code, noms et commentaires en anglais. |
| AR-03 | Commentaires synthétiques et logiques : docstring courte pour chaque module, classe et fonction publique ; commentaire en ligne uniquement pour la logique non évidente. |
| AR-04 | Annotations de type partout. |
| AR-05 | Tests unitaires avec `unittest` : règles de contrôle (dont RC-05 et RC-06), classe API (réponses HTTP simulées), base locale (base SQLite en mémoire), calcul de livraison (rattachement merge / squash / fast-forward, commits hors MR, nouveau tag, incrément du mineur), génération du changelog, opérations Git (dépôts temporaires locaux et distant nu, ignorés si Git est absent ; refus des cas de LI-32), profil (PR-03 : niveaux d'accès, branche protégée, `developers_can_merge`, administrateur), MR ouvertes de l'utilisateur (tous dépôts, rôles assigné / relecteur / les deux), détection des nouveautés (AM-02, AM-04, NO-04, NO-09) et données du panneau de détail (état « prête à merger », extraction de la fin des logs, comptage des lignes des fichiers modifiés, DE-05 à DE-10). |
| AR-06 | `README.md` en anglais : prérequis, installation, configuration, utilisation. |

### 14.2 Arborescence

```
gitective/
├── main.py / main.pyw          # Entry points
├── README.md                   # Installation and usage (English)
├── config.json                 # Created on first launch
├── gitective.db                # Local SQLite store (CH-03)
├── docs/
│   └── specification_controle_MR.md
├── gitective/
│   ├── assets/                 # logo.svg, logo.png, logo.ico
│   ├── forge/                  # GitLab requests, isolated (AR-07)
│   │   ├── protocol.py         # ForgeClient: forge-neutral interface
│   │   ├── gitlab_client.py    # GitLabClient: GitLab implementation
│   │   ├── models.py           # Project, MergeRequest, Commit, CommitStatus, User, ProtectedBranch, Branch, Tag
│   │   └── errors.py           # Forge error hierarchy
│   ├── database/               # Local store and synchronisation
│   │   ├── store.py            # SQLite schema, migrations, queries
│   │   ├── sync.py             # Incremental sync, auto-sync timer, change detection
│   │   └── project_list.py     # Accessible projects (stored)
│   ├── review/                 # MR control
│   │   ├── rules.py            # Custom rules, RC-03 to RC-06 and score
│   │   ├── mr_evaluation.py    # MR loading and evaluation
│   │   ├── mr_detail.py        # Detail panel data: merge readiness, approvals, discussions, pipeline jobs, changed files
│   │   ├── direct_commits.py   # Commits pushed without MR
│   │   ├── merge_rights.py     # Who can merge into the watched branches
│   │   └── profile.py          # Token user, Developer / Merger profile, my open MRs, "new" flags
│   ├── reporting/              # Figures shown to the user
│   │   ├── statistics.py       # Per-person and per-repository statistics, lead times
│   │   └── overview_figures.py # Overview tab figures
│   ├── release/                # Release tab logic
│   │   ├── release_diff.py     # MRs and orphan commits between two tags
│   │   ├── changelog.py        # Markdown changelog
│   │   ├── local_git.py        # git clone, fetch, branch, annotated tag, push (subprocess)
│   │   └── naming.py           # Branch name per mode, minor-bump tag, ref name validation
│   ├── shared/                 # Cross-cutting helpers
│   │   ├── dates.py            # Date parsing, "since yesterday", local timezone
│   │   ├── people.py           # Account-to-person mapping
│   │   ├── search.py           # Text search
│   │   ├── parallel.py         # Concurrent forge lookups
│   │   └── avatars.py          # Avatar download, storage, initials fallback
│   ├── settings/
│   │   └── config_file.py      # Load/save config.json, defaults
│   └── ui/
│       ├── app.py              # Main window, tabs, badges, window title count
│       ├── themes.py           # Default, Light, Dark, Windows 95, Matrix
│       ├── background.py       # Background tasks and progress
│       ├── first_launch_wizard.py
│       ├── tabs/
│       │   ├── data_tab.py     # Base class of the data tabs
│       │   ├── overview.py     # Overview, F11
│       │   ├── merge_requests.py # MR tab, filters, open MRs of other repos, "new" column
│       │   ├── mr_detail_panel.py # Side panel with the selected MR details (6.6)
│       │   ├── direct_commits.py # Direct commits view of the MR tab
│       │   ├── statistics.py   # Per-person / per-repository switch
│       │   ├── release.py      # Composition, tags, changelog, clone / push
│       │   └── config.py       # Config tab, connection test, rule tester, profile, notifications
│       ├── components/
│       │   ├── grid.py         # Custom colored grid, sorting, tooltips
│       │   ├── pagination.py
│       │   ├── chart.py        # Weekly score line chart (Canvas)
│       │   ├── filter_bar.py   # State, dates, repositories, people, drafts filters
│       │   ├── dialogs.py      # Rule, repository and person dialogs
│       │   └── widgets.py      # Multi-select, scrollable frame, small widgets
│       └── alerts/
│           ├── error_banner.py # In-app error banner
│           ├── desktop_toast.py # Desktop notifications and taskbar flash (ctypes)
│           └── badges.py       # Assignee and reviewer badges (Canvas icons)
└── tests/                      # Same folders as gitective/
    ├── factories.py
    ├── forge/       test_gitlab_client.py
    ├── database/    test_store.py, test_project_list.py
    ├── review/      test_rules.py, test_pipeline.py, test_merge_rights.py, test_profile.py, test_mr_detail.py
    ├── reporting/   test_statistics.py, test_overview_figures.py
    ├── shared/      test_parallel.py, test_search.py
    └── release/     test_release_diff.py, test_local_git.py
```

### 14.3 Interface forge et classe API GitLab

L'interface `ForgeClient` (`typing.Protocol`) décrit les opérations dont le métier a besoin, en termes neutres. `GitLabClient` en est l'implémentation GitLab ; un adaptateur pour une autre forge (GitHub, Gitea…) pourra être ajouté sans modifier le métier ni `ui`.

| Réf. | Exigence |
|---|---|
| API-01 | Construction : URL de l'instance, token, option de vérification SSL. |
| API-02 | Basée sur `urllib.request` ; en-tête `PRIVATE-TOKEN`. |
| API-03 | Gestion transparente de la pagination GitLab. |
| API-04 | Renvoie des objets métier typés et neutres (`Project`, `MergeRequest`, `Commit`, `CommitStatus`, `User`, `ProtectedBranch`, `Branch`, `Tag`), pas de JSON brut ni de champ propre à GitLab. |
| API-05 | Lève des exceptions dédiées, définies au niveau de l'interface : authentification, droits, ressource introuvable, réseau, SSL. |
| API-06 | Méthodes minimales : lire l'utilisateur du token ; lister les projets accessibles ; lire le niveau d'accès du token sur un projet ; lister les MR d'un projet (état, dates, mises à jour depuis une date) ; lister les MR ouvertes de toute l'instance où un utilisateur est assigné, ou relecteur ; lister les commits d'une MR ; lister les commits d'une branche (dates) ; lister les MR associées à un commit ; lister les statuts CI d'un commit ; lister les membres d'un projet avec leur niveau d'accès ; lister les branches protégées d'un projet ; lister les tags d'un projet ; lister les branches d'un projet ; lire une branche (protégée, merge autorisé aux développeurs) ; lister les commits entre deux références ; pour le panneau de détail (6.6) : lire une MR (état de merge détaillé, conflits, retard sur la cible), lister ses approbations, ses discussions, ses fichiers modifiés (lignes ajoutées / retirées), les jobs d'un pipeline et la fin du log d'un job. `Project` porte la branche par défaut et les URL de clone HTTPS / SSH ; `MergeRequest` porte ses assignés et relecteurs ; `User` porte l'indicateur administrateur. |
| API-07 | `GitLabClient` reste générique et réutilisable, indépendant de l'application. |

## 15. Jalons

| Jalon | Contenu |
|---|---|
| J1 | Application exécutée par Python installé (périmètre de ce document). |
| J2 (futur) | Exécutable Windows autonome. |

## 16. Points ouverts

| Point | Statut |
|---|---|
| Onglet Statistiques réservé à un mode admin | Reporté à une version ultérieure, mode d'implémentation à définir. Le profil Mergeur (5.7) pourrait servir de base. |
| Changelog : regroupement par ticket ou par type de MR (fonctionnalité / correctif, via labels ou préfixe de titre) | À décider. |
| Livraison : différences entre les modes Version et Release au-delà des modèles de noms (branche de départ, calcul, contenu du changelog, dépôts concernés) | Hypothèse retenue : seuls les modèles de nom de branche et de tag diffèrent. À confirmer. |
| Livraison : valeurs par défaut des noms de branche | Défauts proposés en LI-25, à confirmer. |
| Changelog : lien vers le ticket (URL du gestionnaire de tickets construite à partir du n° extrait) | À décider. |
| Notifications « nouveau merge » : réservées au profil Mergeur | Hypothèse retenue. À confirmer (utile aussi aux développeurs ?). « Ma MR mergée » est disponible pour tous les profils (NO-09). |
