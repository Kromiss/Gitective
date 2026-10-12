# Gitective — Spécification technique

Contrôle des Merge Requests GitLab

Version : 1.8 (brouillon) — 12/10/2026

## 1. Objet

**Gitective** (Git + detective) est une application de bureau permettant de contrôler le respect du process sur les Merge Requests (MR) des dépôts GitLab choisis par l'utilisateur, et de détecter les commits poussés sans MR.

## 2. Contraintes techniques

| Réf. | Exigence |
|---|---|
| CT-01 | Langage : Python 3.11 minimum. |
| CT-02 | Bibliothèque standard uniquement (aucun module externe, aucun téléchargement). Ex. : `tkinter`, `urllib`, `json`, `re`, `ssl`, `sqlite3`, `webbrowser`, `datetime`, `threading`, `unittest`. |
| CT-03 | Système cible : Windows, Python déjà installé sur le poste. |
| CT-04 | GitLab auto-hébergé : URL de l'instance configurable. |
| CT-05 | Authentification par Personal Access Token GitLab, droits `read_api` uniquement. |
| CT-06 | Token et paramètres stockés en clair dans `config.json`, à côté de l'application. |
| CT-09 | IHM : `tkinter` + `ttk` (inclus dans Python). |
| CT-07 | Dates affichées et filtrées dans le fuseau horaire local du PC. |
| CT-08 | Vérification SSL active par défaut ; option de configuration pour la désactiver. |
| CT-10 | Données GitLab stockées dans une base locale SQLite unique, `gitective.db`, à côté de l'application (voir section 11). C'est le seul cache de l'application. |

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
| Pondération des règles fixes (RC-03, RC-04, RC-05) | 25 chacune |
| Seuils de couleur du score | vert = 100 %, orange ≥ 50 %, rouge < 50 % |
| Correspondances personnes ↔ comptes | aucune |
| Requêtes GitLab simultanées (1 à 16) | 6 |
| Thème | Default |
| Rafraîchissement automatique de la Vue d'ensemble | 5 minutes |
| Derniers filtres utilisés (état, dates, auteurs, mergeurs, dépôts, taille de page) | Mergées « Depuis hier », 20 |
| Vue de l'onglet Statistiques (par personne / par dépôt) | Par personne |
| Largeurs de colonnes modifiées | aucune (ajustement au titre) |

`config.json` ne contient que des paramètres ; les données lues depuis GitLab sont dans `gitective.db`.

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
| OC-09 | Bouton « Vider la base locale » : supprime toutes les données de `gitective.db` après confirmation (voir CH-10). |

### 5.2 Thèmes (DA)

| Réf. | Thème | Description |
|---|---|---|
| TH-00 | Default | Thème par défaut. Sombre et soigné : fond bleu nuit, cartes ardoise, accent turquoise, scores menthe / ambre / corail, coins arrondis. |
| TH-01 | Clair | Classique et minimaliste. |
| TH-02 | Sombre | Classique et minimaliste. |
| TH-03 | Windows 95 | Gris, reliefs biseautés, police système rétro. |
| TH-04 | Matrix | Fond noir, texte vert, police monospace. |

Chaque thème définit : fonds, textes, bordures, rayons des coins, police, couleurs OK / KO / N/A et couleurs des niveaux de score, dégradé d'intensité (merges par jour). Thèmes non modifiables. Appliqués via `ttk.Style` et la grille personnalisée.

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
| AV-07 | Images stockées dans `gitective.db` (contenu binaire) ; retéléchargées au bouton Rafraîchir. |

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
| FI-01 | Filtre d'état exclusif (un seul à la fois) : **Mergées**, **Ouvertes**, **Fermées**, **Commits directs** (voir section 10). |
| FI-02 | **Mergées** : filtre entre deux dates, appliqué sur la date de merge. |
| FI-03 | Saisie des dates au format `JJ/MM/AAAA`, journées entières : date de début 00:00:00 → date de fin 23:59:59 incluses. |
| FI-04 | **Mergées** : raccourci « Depuis hier » = hier 00:00 → maintenant. |
| FI-05 | **Ouvertes** et **Fermées** : aucun filtre de date, liste complète. |
| FI-06 | Les derniers filtres sont mémorisés dans `config.json` et restaurés au lancement. |
| FI-07 | Sans filtre mémorisé, la vue de lancement est **Mergées « Depuis hier »**. |
| FI-08 | Les MR en brouillon (Draft) sont exclues : ni affichées, ni comptées. |
| FI-09 | Filtre par auteur, sélection multiple (tous par défaut). S'applique aussi à l'état Commits directs et à l'onglet Statistiques. |
| FI-10 | Raccourci **F5** = Rafraîchir. |
| FI-11 | Filtre par dépôt, sélection multiple parmi les dépôts suivis (tous par défaut). S'applique aussi à l'état Commits directs. Mémorisé comme les autres filtres (FI-06). |
| FI-12 | Recherche texte instantanée, insensible à la casse : MR (titre, description, auteur, mergeur, dépôt, branches) et état Commits directs (message, SHA, auteur, dépôt). Non mémorisée. |
| FI-13 | Filtre par mergeur, sélection multiple regroupée par personne (toutes par défaut), parmi les mergeurs des MR chargées. Actif uniquement pour l'état **Mergées** (grisé sinon). Se combine avec le filtre auteur (ET). Mémorisé (FI-06). |

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
| Pipeline vert | OK vert / KO rouge / N/A gris |
| Score | Pourcentage, couleur vert / orange / rouge selon seuils |

| Réf. | Exigence |
|---|---|
| TA-01 | Survol d'une cellule KO : infobulle affichant le détail de l'erreur (ex. « PROJ-12 (titre) ≠ PROJ-21 (lien) »). |
| TA-02 | Clic sur un en-tête de colonne : tri sur toute la liste filtrée (croissant / décroissant), puis repagination. |
| TA-03 | Score moyen affiché en en-tête, calculé sur toute la liste filtrée. |
| TA-04 | Largeur des colonnes : à l'ouverture, chaque colonne s'ajuste pour afficher son titre en entier sur une ligne. L'utilisateur peut la modifier en glissant la bordure de l'en-tête ; un double-clic sur la bordure revient à l'ajustement automatique. Les largeurs modifiées sont mémorisées dans `config.json`, par tableau (MR, Commits directs, Statistiques par personne, Statistiques par dépôt). S'applique aux quatre tableaux. |

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

Les regex du lien et du n° de ticket de RC-03 sont dans un bloc dédié « Correspondance ticket » de l'onglet Config.

**Détail de RC-05 :**

| Réf. | Exigence |
|---|---|
| PI-01 | Source : statuts du commit de tête de la MR (champ `sha`), lus via `GET /projects/:id/repository/commits/:sha/statuses?all=true`. Couvre GitLab CI et les CI externes qui publient leurs résultats dans GitLab (ex. Jenkins via le plugin GitLab, étape `gitlabCommitStatus` / `updateGitlabCommitStatus`). Aucun appel direct à Jenkins. |
| PI-02 | Pour chaque nom de statut, seul le dernier statut créé avant la date de merge est retenu. Il est OK s'il est `success` et terminé avant la date de merge. |
| PI-03 | Les statuts marqués `allow_failure` sont ignorés. |
| PI-04 | Infobulle du KO : nom du statut et cas (« jenkins : failed », « jenkins : en cours au merge », « aucun statut CI »). |
| PI-05 | Une requête par MR mergée, en parallèle (CH-06). Le résultat d'une MR mergée ne change plus : stocké en base, jamais relu. |
| PI-06 | La case « CI attendue » est réglée par dépôt (SD-08). Décochée, RC-05 est N/A pour toutes les MR du dépôt et n'est pas requêtée. |

**Score** = somme des pondérations des critères OK (règles personnalisées actives + RC-03 + RC-04 + RC-05) / somme des pondérations des critères applicables (hors N/A) × 100.

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
| ST-02 | Une ligne par personne auteur ou mergeur d'au moins une MR, ou auteur d'au moins un commit direct : nombre de MR créées, nombre de MR mergées, score moyen (vide sans MR créée), nombre de KO par critère (règles personnalisées actives, RC-03, RC-04, RC-05), nombre de commits directs (ST-15). |
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
| SR-02 | Colonnes : Dépôt, MR créées, MR mergées, score moyen, nombre de KO par critère (règles personnalisées actives, RC-03, RC-04, RC-05), commits directs, délai création → merge (ST-14). |
| SR-03 | Le filtre auteur restreint les MR et commits directs comptés (seuls ceux des personnes sélectionnées). |
| SR-04 | Courbe d'évolution du score moyen par semaine : une courbe globale + une courbe par dépôt sélectionné dans le filtre dépôts. Mêmes règles que ST-10. |
| SR-05 | Clic sur un dépôt : bascule vers la vue par personne, filtrée sur ce dépôt. |

## 9. Vue d'ensemble

Onglet de supervision, purement graphique, pensé pour un affichage permanent : comprendre l'état des dépôts d'un coup d'œil.

| Réf. | Exigence |
|---|---|
| VE-01 | Onglet « Vue d'ensemble », premier onglet, affiché au lancement. Aucun élément cliquable, aucun filtre : couvre tous les dépôts suivis, MR hors Draft. |
| VE-02 | Tient sans défilement sur un écran 1920 × 1080. Raccourci **F11** : plein écran activé / désactivé. |
| VE-03 | Rafraîchissement automatique (CH-05) toutes les N minutes, réglable dans l'onglet Config (défaut 5). En-tête : heure de la dernière synchronisation et délai avant la prochaine. |
| VE-04 | Disposition : colonne de gauche (≈ un tiers) = fil des derniers merges, puis merges par jour ; à droite, trois niveaux : score moyen + qualité par semaine / classement des dépôts / règles enfreintes + MR créées et mergées. |
| VE-05 | **Derniers merges**, élément principal : 20 dernières MR mergées, de la plus récente à la plus ancienne, groupées par jour. Ligne : heure de merge, titre, dépôt, auteur → mergeur, pastille de score colorée. Groupe « Aujourd'hui » mis en évidence ; nombre de merges du jour en grand dans l'en-tête. Les plus anciennes sont coupées si la place manque. |
| VE-06 | **Merges par jour** : semaine en cours et semaine précédente, lundi → dimanche. Chaque case affiche le nombre de merges, teintée selon l'intensité ; total par semaine. Jours à venir en pointillés. |
| VE-07 | **Score moyen** : MR mergées des 30 derniers jours, couleur selon les seuils, écart en points avec les 30 jours précédents, barre 0 – 100. |
| VE-08 | **Qualité des MR mergées** : 12 dernières semaines complètes, barres empilées du nombre de MR à 100 %, 50 – 99 % et < 50 %. |
| VE-09 | **Classement des dépôts** : score moyen sur 30 jours, tri décroissant, rang, barre et valeur colorées. Réparti sur deux colonnes pour afficher 12 à 20 dépôts. |
| VE-10 | **Règles enfreintes** : nombre de KO par critère actif (règles personnalisées, RC-03, RC-04, RC-05) sur 30 jours, tri décroissant. |
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

## 11. Chargement, base locale et rafraîchissement

| Réf. | Exigence |
|---|---|
| CH-01 | Les appels GitLab s'exécutent en tâche de fond ; l'IHM reste réactive. |
| CH-02 | Indicateur de chargement visible pendant les appels. |
| CH-03 | Base locale persistante `gitective.db` (SQLite, `sqlite3`) : projets accessibles, MR, commits de MR, commits des branches surveillées, résultats de détection hors MR, statuts CI, membres et branches protégées, utilisateurs et avatars. Le changement de page, de tri ou de filtre lit la base sans réinterroger GitLab. |
| CH-04 | Un changement de filtre ou de dates ne déclenche une requête GitLab que pour la partie de la période absente de la base. |
| CH-05 | Bouton **Rafraîchir** : mise à jour incrémentale depuis la dernière synchronisation de chaque dépôt (MR via `updated_after`, commits via `since`) et retéléchargement des avatars. |
| CH-06 | Les requêtes « une par commit » (commits hors MR) et « une par MR » (règles sur les commits, RC-05, ST-12) partent en parallèle ; le nombre de requêtes simultanées se règle dans l'onglet Config (1 à 16, défaut 6). |
| CH-07 | Les règles sont évaluées localement à partir des données en base : modifier une règle, une pondération ou une correspondance de personnes recalcule l'affichage sans requête GitLab. |
| CH-08 | Mode hors ligne : si l'instance est injoignable, l'application affiche les données en base et un bandeau indique la date de dernière synchronisation. |
| CH-09 | Données immuables jamais relues : commits d'une MR mergée, statuts CI d'une MR mergée (PI-05), résultat de détection d'un commit (CO-08). |
| CH-10 | La base est liée à l'URL de l'instance. Un changement d'URL dans l'onglet Config propose de vider la base. |
| CH-11 | La base porte un numéro de version de schéma ; une version de l'application plus récente migre le schéma au démarrage. |
| CH-12 | Accès concurrents : une connexion SQLite par thread ; les écritures sont faites par les tâches de fond, en transactions. |

## 12. Gestion des erreurs

| Réf. | Exigence |
|---|---|
| ER-01 | Notification par bandeau coloré dans l'application, refermable. |
| ER-02 | Message clair et spécifique : token invalide ou expiré, droits insuffisants, réseau coupé / instance injoignable, erreur de certificat SSL, dépôt ou branche introuvable. |
| ER-03 | Une erreur n'interrompt pas l'application ; l'utilisateur peut corriger puis rafraîchir. |
| ER-04 | Toutes les erreurs passent par le bandeau de notification (pas de fichier de log). |
| ER-05 | Limitation de débit GitLab (HTTP 429) et timeout réseau (30 s) : 3 nouvelles tentatives automatiques après 2, 4 puis 8 s, puis notification. Valeurs fixes. |
| ER-06 | Base locale illisible, corrompue ou verrouillée : notification, et proposition de la recréer (resynchronisation complète depuis GitLab). |

## 13. Architecture du code

### 13.1 Principes

| Réf. | Exigence |
|---|---|
| AR-01 | Découpage par couches : `api`, `core`, `ui`, `config`. Une couche ne dépend que des couches inférieures (`ui` → `core` → `api`). `core` dépend uniquement de l'interface forge (13.3), jamais de `GitLabClient` directement. |
| AR-02 | Code, noms et commentaires en anglais. |
| AR-03 | Commentaires synthétiques et logiques : docstring courte pour chaque module, classe et fonction publique ; commentaire en ligne uniquement pour la logique non évidente. |
| AR-04 | Annotations de type partout. |
| AR-05 | Tests unitaires avec `unittest` : règles de contrôle (dont RC-05), classe API (réponses HTTP simulées), base locale (base SQLite en mémoire). |
| AR-06 | `README.md` en anglais : prérequis, installation, configuration, utilisation. |

### 13.2 Arborescence

```
gitective/
├── main.py                 # Entry point
├── README.md               # Installation and usage (English)
├── config.json             # Created on first launch
├── gitective.db            # Local SQLite store (CH-03)
├── gitective/
│   ├── assets/
│   │   ├── logo.svg        # Logo source
│   │   ├── logo.png        # In-app logo
│   │   └── logo.ico        # Window icon
│   ├── api/
│   │   ├── forge.py        # ForgeClient protocol (forge-neutral interface)
│   │   ├── client.py       # GitLabClient: GitLab implementation of ForgeClient
│   │   ├── models.py       # Project, MergeRequest, Commit, CommitStatus, User, ProtectedBranch (dataclasses)
│   │   └── errors.py       # Forge error hierarchy
│   ├── core/
│   │   ├── storage.py      # SQLite store: schema, migrations, queries
│   │   ├── sync.py         # Incremental synchronisation forge → store
│   │   ├── rules.py        # Custom rules, RC-03, RC-04, RC-05 and score
│   │   ├── orphan_commits.py # Commits-without-MR detection
│   │   ├── project_list.py # Accessible projects (stored)
│   │   ├── mergers.py      # Who can merge into the watched branches
│   │   ├── stats.py        # Per-person and per-repository statistics, overview figures, lead time
│   │   ├── merge_requests.py # MR loading and evaluation
│   │   ├── parallel.py     # Concurrent forge lookups
│   │   ├── search.py       # Text search
│   │   ├── people.py       # Account-to-person mapping
│   │   ├── avatars.py      # Avatar download, storage, initials fallback
│   │   └── dates.py        # Date parsing, "since yesterday", local timezone
│   ├── config/
│   │   └── settings.py     # Load/save config.json, defaults
│   └── ui/
│       ├── app.py          # Main window, tabs (Overview first)
│       ├── data_tab.py     # Base class of the MR, Commits and Statistics tabs
│       ├── mr_tab.py       # Merge Requests tab
│       ├── commits_view.py # Direct commits view of the MR tab
│       ├── settings_tab.py # Config tab, connection test, rule tester
│       ├── dialogs.py      # Rule, repository and person dialogs
│       ├── stats_tab.py    # Statistics tab, per-person / per-repository switch
│       ├── overview_tab.py # Overview tab: read-only dashboard, auto-refresh, F11
│       ├── chart.py        # Weekly score line chart (Canvas)
│       ├── wizard.py       # First-launch wizard
│       ├── themes.py       # Default, Light, Dark, Windows 95, Matrix
│       ├── filters.py      # State/date filters, refresh button
│       ├── grid.py         # Custom colored grid, sorting, tooltips
│       ├── pagination.py   # Pager
│       ├── notifications.py# Error banner
│       └── worker.py       # Background tasks and progress
└── tests/
    ├── test_rules.py
    ├── test_client.py
    ├── test_mergers.py
    ├── test_storage.py
    └── test_project_list.py
```

### 13.3 Interface forge et classe API GitLab

L'interface `ForgeClient` (`typing.Protocol`) décrit les opérations dont `core` a besoin, en termes neutres. `GitLabClient` en est l'implémentation GitLab ; un adaptateur pour une autre forge (GitHub, Gitea…) pourra être ajouté sans modifier `core` ni `ui`.

| Réf. | Exigence |
|---|---|
| API-01 | Construction : URL de l'instance, token, option de vérification SSL. |
| API-02 | Basée sur `urllib.request` ; en-tête `PRIVATE-TOKEN`. |
| API-03 | Gestion transparente de la pagination GitLab. |
| API-04 | Renvoie des objets métier typés et neutres (`Project`, `MergeRequest`, `Commit`, `CommitStatus`, `User`, `ProtectedBranch`), pas de JSON brut ni de champ propre à GitLab. |
| API-05 | Lève des exceptions dédiées, définies au niveau de l'interface : authentification, droits, ressource introuvable, réseau, SSL. |
| API-06 | Méthodes minimales : lister les projets accessibles ; lister les MR d'un projet (état, dates, mises à jour depuis une date) ; lister les commits d'une MR ; lister les commits d'une branche (dates) ; lister les MR associées à un commit ; lister les statuts CI d'un commit ; lister les membres d'un projet avec leur niveau d'accès ; lister les branches protégées d'un projet. |
| API-07 | `GitLabClient` reste générique et réutilisable, indépendant de l'application. |

## 14. Jalons

| Jalon | Contenu |
|---|---|
| J1 | Application exécutée par Python installé (périmètre de ce document). |
| J2 (futur) | Exécutable Windows autonome. |

## 15. Points ouverts

| Point | Statut |
|---|---|
| Onglet Statistiques réservé à un mode admin | Reporté à une version ultérieure, mode d'implémentation à définir. |
