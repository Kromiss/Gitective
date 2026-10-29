# Gitective — Spécification technique

Contrôle des Merge Requests GitLab

Version : 1.25 (brouillon) — 29/10/2026

## 1. Objet

**Gitective** (Git + detective) est une application de bureau permettant de contrôler le respect du process sur les Merge Requests (MR) des dépôts GitLab choisis par l'utilisateur, de détecter les commits poussés sans MR, et de suivre les branches (actives, mortes, mergées non supprimées) et les tags de ces dépôts, et de lister les MR qui séparent deux tags. Deux éditions sont livrées : **admin** (complète) et **user** (conforme RGPD, sans chiffres ni noms par personne, section 18). Dans une édition, toutes les fonctions sont disponibles pour tous les utilisateurs, en français ou en anglais (5.9).

## 2. Contraintes techniques

| Réf. | Exigence |
|---|---|
| CT-01 | Langage : Python 3.11 minimum. |
| CT-02 | Bibliothèque standard uniquement (aucun module externe, aucun téléchargement). Ex. : `tkinter`, `urllib`, `json`, `re`, `ssl`, `sqlite3`, `webbrowser`, `datetime`, `threading`, `unittest`. Les outils de build (PyInstaller, LV-04) servent uniquement à la livraison GitHub, jamais à l'application. |
| CT-03 | Système cible : Windows, Python déjà installé sur le poste. |
| CT-04 | GitLab auto-hébergé : URL de l'instance configurable. |
| CT-05 | Authentification API par Personal Access Token GitLab, droits `read_api` uniquement. |
| CT-06 | Token et paramètres stockés en clair dans `config.json`, à côté de l'application. |
| CT-09 | IHM : `tkinter` + `ttk` (inclus dans Python). |
| CT-07 | Dates affichées et filtrées dans le fuseau horaire local du PC. |
| CT-08 | Vérification SSL active par défaut ; option de configuration pour la désactiver. |
| CT-10 | Données GitLab stockées dans une base locale SQLite unique, `gitective.db`, à côté de l'application (voir section 13). C'est le seul cache de l'application. |

## 3. Configuration

Fichier `config.json`, dans le dossier de l'application, contenant :

| Paramètre | Valeur par défaut |
|---|---|
| URL de l'instance GitLab | — |
| Token personnel | — |
| Vérification SSL | activée |
| Langue (5.9) | Français |
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
| Notifications de bureau (NO-01) : nouveaux merges / MR qui me sont assignées ou en relecture / mes MR mergées / toutes les nouvelles MR (NO-11) | activées / activées / activées / **désactivée** |
| Derniers filtres utilisés de l'onglet Merge Requests (état, dates, auteurs, mergeurs, assignés, relecteurs, brouillons, dépôts, taille de page) | Mergées « Depuis hier », 20 |
| Branches : regex d'exclusion (BR-05) | `^(main\|master\|develop.*)$` |
| Branches : seuil « branche morte », en jours calendaires (BR-04) | 30 |
| Derniers filtres de l'onglet Branches (auteurs, dépôts, états) | tous, états « Active », « Morte », « Mergée non supprimée » |
| Derniers filtres de l'onglet Tags (dépôts, période) | tous, « Total » |
| Lignes de comparaison de tags (dépôt, current, référence, TC-02) | aucune |
| Vue de l'onglet Statistiques (par personne / par dépôt) | Par personne |
| Largeurs de colonnes modifiées | aucune (ajustement au titre) |
| Largeur du panneau de détail (DE-02, TG-07) | 420 px |

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
| OC-01 | Onglet « Config » dans l'application, permettant de modifier tous les paramètres de la section 3, répartis en trois sous-onglets (OC-14). |
| OC-02 | Token : champ masqué + bouton « Afficher ». |
| OC-03 | Enregistrement dans `config.json`. |
| OC-04 | Choix du thème parmi une liste figée (voir 5.2) ; s'applique à tous les onglets, Vue d'ensemble comprise. |
| OC-05 | Bouton « Tester la connexion » : vérifie URL + token, résultat affiché par le bandeau de notification. |
| OC-06 | Testeur de regex : saisie d'exemples (titre, description, branches, messages de commits), affichage immédiat OK / KO de chaque règle active et de RC-03 avec le n° de ticket extrait. |
| OC-07 | Validation des regex avant enregistrement ; une regex invalide bloque l'enregistrement et est signalée par le bandeau. |
| OC-08 | Gestion des correspondances personnes ↔ comptes (voir 5.4). |
| OC-10 | Bloc « Branches » : regex d'exclusion (BR-05, validée par OC-07) et seuil « branche morte » en jours calendaires (BR-04, entier ≥ 1). |
| OC-11 | Affichage en lecture seule de l'utilisateur du token (PR-01). Bloc « Notifications » : quatre cases (NO-01), dont « Toutes les nouvelles MR » (NO-11), décochée par défaut. |
| OC-13 | Liste « Langue » : Français / English (5.9). |
| OC-09 | Bouton « Vider la base locale » : supprime toutes les données de `gitective.db` après confirmation (voir CH-10). |
| OC-14 | Trois sous-onglets, au plus deux colonnes chacun. **Général** : Connexion GitLab, Dépôts suivis | Apparence (thème, langue), Notifications, Personnes. **Règles** : Règles personnalisées, Correspondance ticket, Pondérations et seuils | Testeur de règles. **Avancé** : Réseau et synchronisation (SSL, requêtes simultanées, période), Onglet Branches | Démarrage (assistant), Base locale. Le dernier sous-onglet ouvert est mémorisé (`config_view`). |
| OC-15 | Modifications non enregistrées : comparaison du formulaire avec la configuration enregistrée. Point « • » sur chaque sous-onglet modifié, nombre de modifications sur « Enregistrer (N) », résumé dans la barre du bas (« N modification(s) non enregistrée(s) · Général, Règles »). Sans modification, « Enregistrer » et « Annuler les modifications » sont grisés. Les champs du testeur ne comptent pas. |
| OC-16 | Aide : une icône ⓘ à côté de chaque réglage ; au survol, une infobulle explique le réglage et donne sa valeur par défaut. |
| OC-17 | Quitter l'onglet Config avec des modifications en attente ouvre une fenêtre : « Rester dans Config », « Ignorer les modifications » (le formulaire revient à la configuration enregistrée) ou « Enregistrer » (on reste dans Config si l'enregistrement échoue ou est refusé). |

### 5.2 Thèmes (DA)

| Réf. | Thème | Description |
|---|---|---|
| TH-00 | Default | Thème par défaut. Sombre et soigné : fond bleu nuit, cartes ardoise, accent turquoise, scores menthe / ambre / corail, coins arrondis. |
| TH-01 | Clair | Classique et minimaliste. |
| TH-02 | Sombre | Classique et minimaliste. |
| TH-03 | Windows 95 | Gris, reliefs biseautés, police système rétro. Adouci pour ménager les yeux : cartes blanc cassé (`#F4F4EE`), texte quasi noir, couleurs de niveau et OK / KO / N/A en teintes pâles avec texte foncé (contraste ≥ 6:1), liens bleu marine. |
| TH-04 | Matrix | Fond noir, police monospace, tout en vert mais lisible : trois intensités de texte (titres vert vif `#33FF66` précédés de « > », texte courant `#8CE6A0`, texte secondaire `#4FA866`), liens soulignés. Niveaux distingués par la luminosité : bon = vert vif, moyen = vert atténué, faible et KO = **vidéo inverse** (fond vert vif, texte noir). Barres et grands chiffres du niveau faible en vert vif rayé. Sous-titres raccourcis pour ne pas chevaucher les titres. |
| TH-05 | Daltonien | Pour la deutéranopie et la protanopie. Sombre (fond `#0E1117`), accent lavande. Niveaux de score bleu ciel (bon) / jaune (moyen) / vermillon (faible), palette Okabe-Ito, distincts aussi par la luminosité. OK bleu, KO vermillon. Comme tous les thèmes, porte les **indicateurs de forme** (5.2.1). |

Chaque thème définit : fonds, textes, bordures, rayons des coins, police, accent et accent secondaire, couleurs OK / KO / N/A et couleurs des niveaux de score (aussi utilisées par les merges par jour, VE-06). Thèmes non modifiables. Appliqués via `ttk.Style` et la grille personnalisée.

Les couleurs OK / KO / N/A sont adaptées à chaque thème (ex. Matrix : vert vif / vidéo inverse / vert atténué). Les libellés texte « OK », « KO », « N/A » restent affichés pour garantir la lisibilité quelle que soit la couleur.

#### 5.2.1 Indicateurs de forme (tous les thèmes)

La couleur n'est jamais le seul indice : tous les thèmes dessinent les indicateurs ci-dessous.

| Réf. | Exigence |
|---|---|
| TF-01 | Chaque score coloré porte une **jauge à 3 barres montantes** dessinée en `Canvas` : 3 barres pleines = bon, 2 = moyen, 1 = faible, les autres dans une couleur neutre. Dans les pastilles du tableau MR et des Statistiques, le fil des derniers merges, les cases des merges par jour, le score moyen (grande jauge), le classement des dépôts. Dans les libellés Tk (score moyen de l'onglet MR, panneau de détail, comparaison de tags, notifications), la jauge est écrite en caractères : `▮▮▮`, `▮▮▯`, `▮▯▯`. |
| TF-02 | Qualité par semaine (VE-08) et sa légende : bon en aplat, moyen à points, faible rayé. Rayures **verticales** de 2 px tous les 5 px et points de 1 px, dessinés en rectangles calés sur des pixels entiers : motif régulier, sans escalier ni moiré, quelles que soient la taille de la fenêtre et la mise à l'échelle de Windows (le `stipple` de Tk n'est pas fiable sous Windows). |
| TF-03 | Courbes : la première série en trait plein, les suivantes en tirets (motifs Tk `-`, `.`, `-.`, `-..`, gérés sous Windows) ; « Créées » en tirets dans « MR créées / mergées ». Légendes avec le même trait. |
| TF-04 | Test : les trois couleurs de niveau, simulées pour deutéranope et protanope (matrices de Machado 2009), restent séparées d'un écart CIELAB ΔE > 20 ; pour tous les thèmes, le texte des pastilles, OK / KO / N/A, le texte courant et le texte atténué gardent un contraste ≥ 4,5:1 ; Matrix : bon plus lumineux que moyen, faible en vidéo inverse. |

Badges (6.5) : fond, bordure, coins et police des cartes du thème ; icône Assigné (merge) en couleur d'accent, icône Relecteur (œil) en accent secondaire, icône Auteur (crayon) en couleur de texte ; pastille des nouvelles en couleur « score rouge » ; badge à 0 en couleur N/A. Icônes et libellés identiques dans tous les thèmes, dessinés en `Canvas` (pas de police d'icônes).

| Thème | Accent / accent secondaire | Pastille | Forme des badges |
|---|---|---|---|
| Default | turquoise / bleu clair | corail | coins arrondis |
| Clair | bleu / violet | rouge | coins légèrement arrondis, fond blanc |
| Sombre | bleu / violet clair | rouge | coins légèrement arrondis, fond gris foncé |
| Windows 95 | bleu marine / sarcelle | rouge vif | bouton biseauté en relief, coins carrés, police système |
| Matrix | vert vif / vert pâle | vert vif, texte noir | coins carrés, police monospace ; badges distingués par l'icône et le libellé |
| Daltonien | lavande / blanc lavande | vermillon, texte sombre | coins arrondis |

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
| PE-03 | Pour les commits hors MR et les derniers commits des branches et tags (sans ID GitLab), on associe aussi à la personne des noms et/ou e-mails Git. |
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

### 5.7 Utilisateur du token

Les profils Développeur / Mergeur (v1.14) sont supprimés : badges, MR des dépôts non suivis, colonne « Nouvelle » et notifications sont disponibles pour tous. Le droit de merge reste calculé pour la colonne « Rôle » des Statistiques (ST-11).

| Réf. | Exigence |
|---|---|
| PR-01 | L'utilisateur du token est lu via `GET /user` (ID, nom) au test de connexion, au démarrage et à chaque changement de token. Il sert à « Moi » (AM-07), aux badges (6.5) et aux notifications (5.8). |
| PR-07 | Instance injoignable (CH-08) : dernier utilisateur connu, stocké en base. |

### 5.8 Notifications de bureau

| Réf. | Exigence |
|---|---|
| NO-01 | Quatre types, chacun activable dans l'onglet Config : **nouveau merge** (MR mergée sur un dépôt suivi) ; **MR assignée / relecture demandée** (MR ou rôle de l'utilisateur qui apparaît, 6.4, tous dépôts) ; **ma MR mergée** (NO-09) ; **nouvelle MR** (NO-11, désactivée par défaut). |
| NO-08 | Le titre de la notification indique le rôle : « MR assignée », « Relecture demandée » ou « MR assignée + relecture ». |
| NO-09 | **Ma MR mergée** : MR d'un dépôt suivi dont l'utilisateur du token est l'auteur (comparaison par personne, 5.4), passée à l'état mergé depuis la synchronisation précédente. Titre « Votre MR a été mergée » ; contenu NO-03, mergeur compris. Une MR qui déclencherait aussi « nouveau merge » ne produit qu'une notification, celle-ci. Données déjà synchronisées (CH-05) : aucune requête supplémentaire. Limite : MR des dépôts non suivis non couvertes. |
| NO-11 | **Nouvelle MR** : MR d'un dépôt suivi, de n'importe quel auteur, apparue à l'état ouvert hors brouillon depuis la synchronisation précédente, ou sortie de l'état brouillon (elle devient prête à merger). Titre « Nouvelle MR » ; contenu NO-03 (« par auteur »). Une MR qui déclencherait aussi « MR assignée / relecture demandée » ne produit qu'une notification, cette dernière. Données déjà synchronisées (CH-05) : aucune requête supplémentaire. Limite : « temps réel » = au rythme de la synchronisation automatique (CH-13, réglable) ; MR des dépôts non suivis non couvertes. |
| NO-02 | Affichage : petite fenêtre `tkinter` sans bordure (`Toplevel`, `overrideredirect`, `-topmost`), dans le coin bas-droit de l'écran, aux couleurs du thème. Visible par-dessus les autres applications, y compris quand Gitective est réduit. Disparaît après 8 s ; survol = reste affichée. |
| NO-03 | Contenu : type, titre de la MR, puis les personnes sur leur propre ligne (« auteur → mergeur » pour un merge, « par auteur » pour une MR assignée, en relecture ou nouvelle), puis le dépôt avec, à droite, le score de la MR (« Score 75 % », pastille aux couleurs de son niveau, seuils de la section 3). Le liseré gauche et le libellé du type prennent la couleur du niveau de score ; une synthèse (NO-05), sans score propre, garde la couleur de son type. Score calculé localement à la synchronisation (CH-07). Clic = ouverture de la MR dans le navigateur ; croix = fermeture ; roue crantée sous la croix (NO-10). |
| NO-10 | Roue crantée « ⚙ » en haut à droite, sous la croix, sur chaque notification (synthèses comprises). Clic : Gitective restauré et mis au premier plan, onglet Config ouvert et défilé jusqu'au bloc « Notifications », bloc et cases mis en surbrillance (bordure, titre et libellés en couleur d'accent du thème) pendant 6 s ; la notification se ferme. Aucun réglage n'est modifié. |
| NO-04 | Détection après chaque synchronisation (CH-13 ou Rafraîchir), par comparaison avec la base avant synchronisation. Pas de notification pour ses propres merges ni ses propres MR, ni à la toute première synchronisation. |
| NO-05 | Au plus 3 notifications empilées ; au-delà, une notification de synthèse (ex. « 7 nouveaux merges », « 5 nouvelles MR »), clic = ouverture de Gitective sur l'onglet Merge Requests. |
| NO-06 | En complément, la fenêtre réduite clignote dans la barre des tâches (`FlashWindowEx` via `ctypes`, bibliothèque standard) pour les MR assignées. |
| NO-07 | Limites : Gitective doit être lancé (réduit accepté, fermé non) ; les notifications n'apparaissent pas dans le centre de notifications Windows (nécessiterait un module externe, CT-02). |

### 5.9 Langue

| Réf. | Exigence |
|---|---|
| LG-01 | Deux langues : Français (défaut) et English, choisies dans l'onglet Config (OC-13), enregistrées dans `config.json`. |
| LG-02 | Appliquée au redémarrage : après changement, le bandeau indique « Redémarrez Gitective pour appliquer la langue » (texte dans les deux langues). |
| LG-03 | Couvre tous les textes de l'application : onglets, libellés, infobulles, bandeau d'erreurs, notifications de bureau, assistant de premier lancement, textes copiés (BR-08, TC-09), noms des règles fixes. Non traduits : textes saisis par l'utilisateur (noms de règles personnalisées, de personnes) et données GitLab. Les règles pré-remplies (RP-07) prennent leur nom dans la langue active à leur création. |
| LG-04 | Formats identiques dans les deux langues : dates `JJ/MM/AAAA`, virgule décimale. Seules les unités sont traduites (« j » / « d »). |
| LG-05 | Implémentation : `gitective/shared/i18n.py`, fonction de traduction `t(texte, **paramètres)` ; les textes sont écrits en français dans le code et servent de clé au dictionnaire anglais `gitective/shared/translations_en.py` (paramètres nommés) ; clé absente en anglais : texte français. Langue choisie dans `main.py` avant l'import de l'IHM. Un test vérifie que chaque texte a sa version anglaise, avec les mêmes paramètres. |

## 6. Filtres et affichage des MR

### 6.1 Filtres

| Réf. | Exigence |
|---|---|
| FI-01 | Filtre d'état exclusif (un seul à la fois) : **Mergées**, **Ouvertes**, **Fermées**, **Toutes** (FI-21), **Commits directs** (voir section 10). |
| FI-02 | **Mergées** : filtre entre deux dates, appliqué sur la date de merge. |
| FI-03 | Saisie des dates au format `JJ/MM/AAAA`, journées entières : date de début 00:00:00 → date de fin 23:59:59 incluses. |
| FI-04 | **Mergées** : raccourci « Depuis hier » = hier 00:00 → maintenant. |
| FI-19 | **Mergées** et **Commits directs** : bouton « Total » = période sans limite de date, même logique que le bouton « Total » des Statistiques (ST-05). Les champs de dates sont vidés. Seule la partie de l'historique absente de la base est chargée (CH-04), avec la barre de progression ; pour Commits directs, la détection (CO-08) couvre tout l'historique de la branche surveillée. Mémorisé (FI-06). |
| FI-05 | **Ouvertes** et **Fermées** : aucun filtre de date, liste complète. |
| FI-21 | **Toutes** : MR mergées, ouvertes et fermées ensemble, brouillons compris. Les dates, « Depuis hier » et « Total » filtrent sur la **date de création**. Colonne « État » (Mergée / Ouverte / Fermée), triable, présente dans cet état uniquement, après Titre. Les filtres auteur, mergeur (seules les MR mergées ont un mergeur), assigné, relecteur, dépôt et brouillons s'appliquent. Données déjà en base (CH-03) ; seule la partie de la période absente est lue (CH-04). Les MR des dépôts non suivis (AM-08) restent propres à l'état Ouvertes. |
| FI-06 | Les derniers filtres sont mémorisés dans `config.json` et restaurés au lancement. |
| FI-07 | Sans filtre mémorisé, la vue de lancement est **Mergées « Depuis hier »**. |
| FI-18 | Bouton **« Réinitialiser les filtres »**, à côté du bouton Rafraîchir. Conserve l'état affiché, la taille de page et le tri. Remet à « tous » les filtres auteur, mergeur, assigné, relecteur et dépôt ; brouillons à « Inclus » ; recherche vidée ; dates à « Depuis hier » (Mergées, Commits directs). Aucune requête GitLab hors CH-04. Le résultat est mémorisé (FI-06). |
| FI-08 | MR en brouillon (Draft) : affichées dans l'onglet Merge Requests (états **Ouvertes**, **Fermées** et **Toutes**), jamais comptées ailleurs (score moyen TA-03, Statistiques, Vue d'ensemble, badges, notifications). |
| FI-16 | Indicateur Draft : étiquette « BROUILLON » devant le titre, couleur N/A du thème, et ligne entière en texte atténué. Infobulle : « MR en brouillon : pas prête à merger ». Score affiché pour information. |
| FI-17 | Filtre **Brouillons**, choix exclusif : **Inclus** (défaut), **Exclus**, **Seulement**. Actif pour **Ouvertes**, **Fermées** et **Toutes** (grisé sinon, une MR mergée n'étant jamais en brouillon). Se combine avec les autres filtres (ET). Mémorisé (FI-06). Le clic sur un badge (BA-02) le remet à « Inclus ». |
| FI-09 | Filtre par auteur, sélection multiple (tous par défaut), avec l'utilisateur en tête de liste sous la forme « Moi (nom) » (comme AM-07). Actif pour tous les états (**Mergées**, **Ouvertes**, **Fermées**, **Commits directs**), jamais grisé ; liste des auteurs construite depuis les MR (ou commits) de l'état affiché. S'applique aussi à l'onglet Statistiques. |
| FI-10 | Raccourci **F5** = Rafraîchir. |
| FI-11 | Filtre par dépôt, sélection multiple parmi les dépôts suivis (tous par défaut). S'applique aussi à l'état Commits directs. Mémorisé comme les autres filtres (FI-06). |
| FI-12 | Recherche texte instantanée, insensible à la casse : MR (titre, description, auteur, mergeur, dépôt, branches, SHA) et état Commits directs (message, SHA, auteur, dépôt). Non mémorisée. |
| FI-20 | Recherche par SHA (FI-12), par préfixe, **dès 1 caractère**, sur : commit de merge (`merge_commit_sha`), commit de squash (`squash_commit_sha`), commit de tête (`sha`) et commits de la MR présents en base (RP-04, ST-12). Aucune requête supplémentaire. Limite : les commits d'une MR dont les commits n'ont jamais été lus ne sont pas trouvés. |
| FI-13 | Filtre par mergeur, sélection multiple regroupée par personne (toutes par défaut), parmi les mergeurs des MR chargées. Actif pour les états **Mergées** et **Toutes** (grisé sinon ; dans Toutes, il ne garde que des MR mergées). Se combine avec le filtre auteur (ET). Mémorisé (FI-06). |
| FI-14 | Filtre par **assigné**, sélection multiple regroupée par personne (tous par défaut), parmi les assignés des MR chargées, plus l'entrée « Non assignée ». Actif pour les états **Mergées**, **Ouvertes**, **Fermées** et **Toutes** (grisé pour Commits directs). Une MR est retenue si l'un de ses assignés est sélectionné. Mémorisé (FI-06). |
| FI-15 | Filtre par **relecteur**, mêmes règles que FI-14 (entrée « Sans relecteur », mêmes états). Les filtres auteur, assigné, relecteur et dépôt se combinent (ET). Données déjà lues par la synchronisation (champs assignés et relecteurs des MR, CH-03) : aucune requête supplémentaire. |

### 6.2 Tableau

Grille personnalisée (cellules colorées individuellement). Colonnes :

| Colonne | Contenu |
|---|---|
| Dépôt | Nom du dépôt de la MR |
| Titre | Titre de la MR — **simple clic = ouverture de la MR dans le navigateur web par défaut** |
| État | Mergée / Ouverte / Fermée — état **Toutes** uniquement (FI-21) |
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
| Nouvelle | Pastille (état Ouvertes uniquement, AM-04) |
| Score | Pourcentage, couleur vert / orange / rouge selon seuils |

| Réf. | Exigence |
|---|---|
| TA-01 | Survol d'une cellule KO : infobulle affichant le détail de l'erreur (ex. « PROJ-12 (titre) ≠ PROJ-21 (lien) »). |
| TA-02 | Clic sur un en-tête de colonne : tri sur toute la liste filtrée (croissant / décroissant), puis repagination. |
| TA-03 | Score moyen affiché en en-tête, calculé sur toute la liste filtrée. |
| TA-05 | Mergée par un non-assigné : si la MR a au moins un assigné et que le mergeur n'est aucun d'eux (comparaison par personne, 5.4), la cellule Mergeur est mise en évidence (couleur d'avertissement du thème + icône « ≠ ») ; infobulle : « Mergée par X, assignée à Y ». Affiché que RC-06 soit active ou non ; le score n'est impacté que par RC-06. MR sans assigné : pas de signalement. |
| TA-04 | Largeur des colonnes : à l'ouverture, chaque colonne s'ajuste pour afficher son titre en entier sur une ligne. L'utilisateur peut la modifier en glissant la bordure de l'en-tête ; un double-clic sur la bordure revient à l'ajustement automatique. Les largeurs modifiées sont mémorisées dans `config.json`, par tableau (MR, Commits directs, Statistiques par personne, Statistiques par dépôt, Branches, Tags). S'applique aux six tableaux. |

### 6.3 Pagination

| Réf. | Exigence |
|---|---|
| PA-01 | Nombre total de MR affiché. |
| PA-02 | Navigation par pages, comme une page web. |
| PA-03 | Taille de page choisie dans l'IHM : 20 / 50 / 100, défaut 20. |

### 6.4 Mes MR (assignées, en relecture, créées)

Objectif : voir d'un coup d'œil les merges qu'il reste à faire et ses propres MR en cours, sans onglet supplémentaire : tout passe par l'état **Ouvertes** de l'onglet Merge Requests.

| Réf. | Exigence |
|---|---|
| AM-01 | Pas de sous-onglet. Les trois badges (6.5) mènent à l'état **Ouvertes** filtré sur l'utilisateur du token, comme assigné, relecteur ou auteur (BA-02). |
| AM-02 | Données : à chaque synchronisation (CH-05, CH-13), lecture des MR ouvertes, brouillons compris, de **tous les dépôts** accessibles au token (suivis ou non), dont l'utilisateur est **assigné** ou **relecteur** : `GET /merge_requests?scope=all&state=opened&assignee_id=<moi>` et `…&reviewer_id=<moi>` (2 requêtes paginées, `read_api`). Une MR qui quitte ces résultats (mergée, fermée, désassignée) n'est plus comptée. |
| AM-09 | **Mes MR créées** : MR ouvertes des dépôts suivis dont l'utilisateur est l'auteur (comparaison par personne, 5.4, tous ses comptes), lues en base (CH-05) : aucune requête supplémentaire. Limite : MR des dépôts non suivis non couvertes. |
| AM-08 | L'état **Ouvertes** inclut les MR d'AM-02 même si leur dépôt n'est pas suivi : nom du dépôt suivi de « (non suivi) », dépôt proposé dans le filtre dépôts. Règles évaluées comme pour un dépôt suivi. |
| AM-07 | Rôle visible : les colonnes Assignés et Relecteurs (6.2) affichent le nom de l'utilisateur en gras, couleur d'accent du thème. Les filtres Auteur, Assigné et Relecteur (FI-09, FI-14, FI-15) proposent l'utilisateur en tête de liste sous la forme « Moi (nom) ». |
| AM-04 | Une MR est **nouvelle** pour un rôle (assigné ou relecteur) si l'utilisateur a reçu ce rôle depuis le dernier clic sur le badge correspondant ; une MR qui quitte l'état brouillon redevient nouvelle pour ses rôles (elle devient prête à merger). Pastille dans la colonne « Nouvelle » de l'état Ouvertes. Les couples MR / rôle déjà vus sont stockés en base ; le clic sur un badge marque vus les couples de son rôle uniquement. Les MR qui étaient nouvelles au moment du clic gardent leur pastille jusqu'au clic suivant, pour rester repérables dans la liste affichée. Pas de notion de « nouvelle » pour le rôle auteur. |
| AM-06 | Score coloré et infobulles KO (TA-01) disponibles avant le merge ; RC-04, RC-05 et RC-06 sont N/A (MR non mergée). |

### 6.5 Badges des MR en attente

| Réf. | Exigence |
|---|---|
| BA-01 | Trois badges côte à côte en haut à droite de la fenêtre, visibles sur tous les onglets : **Assigné**, **Relecteur** et **Auteur**, chacun avec son icône (merge / œil / crayon) et son libellé, aux couleurs du thème (5.2). Chacun affiche le nombre de MR ouvertes, hors brouillons, où l'utilisateur a ce rôle. Assigné et Relecteur ajoutent une pastille du nombre de nouvelles de ce rôle (AM-04), masquée à 0. Une MR à plusieurs rôles compte dans chaque badge concerné. Survol : détail (ex. « 3 assignées, dont 1 nouvelle ; 1 brouillon », « 4 MR ouvertes ; 2 brouillons »). |
| BA-02 | Clic sur un badge : onglet Merge Requests, état **Ouvertes**, filtre du rôle du badge (Assigné, Relecteur ou Auteur) = l'utilisateur, les deux autres de ces trois filtres remis à « tous » ; filtres dépôt et recherche remis à « tous », brouillons « Inclus ». Les filtres restent ensuite modifiables et sont mémorisés normalement (FI-06). Badges Assigné et Relecteur : les MR du rôle deviennent vues (AM-04). |
| BA-03 | Le titre de la fenêtre (et donc la barre des tâches) reprend le total des nouvelles des rôles assigné et relecteur, une MR aux deux rôles comptant une fois : « Gitective (3) ». |
| BA-04 | Mis à jour après chaque synchronisation (CH-13, Rafraîchir) et au clic sur un badge. |

### 6.6 Panneau de détail d'une MR

Objectif : comprendre une MR et savoir si elle peut être mergée sans ouvrir GitLab. États Mergées, Ouvertes et Fermées.

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
| RP-01 | Une règle = nom, champ inspecté, regex, groupe à récupérer (RP-09), condition, pondération, case « Active ». |
| RP-02 | Champs inspectables : titre, description, branche source, branche cible, messages des commits de la MR. |
| RP-03 | Condition : « doit correspondre » ou « ne doit pas correspondre ». |
| RP-04 | Messages de commits : OK seulement si **tous** les commits de la MR respectent la condition ; l'infobulle du KO liste les SHA fautifs. Nécessite une requête GitLab par MR (stockée en base, voir CH-09). |
| RP-05 | Une règle désactivée n'est ni affichée, ni comptée dans le score. |
| RP-06 | Chaque règle active a sa colonne OK / KO dans le tableau, compte dans le score selon sa pondération et dans les statistiques (nombre de KO). |
| RP-07 | Règles pré-remplies à la création : « Titre conforme » (titre, doit correspondre) et « Lien ticket » (description, doit correspondre), regex à compléter. Elles remplacent les anciennes RC-01 et RC-02. |
| RP-08 | Regex validées avant enregistrement (OC-07). Une règle active sans regex est KO (« regex non configurée »). |
| RP-09 | **Groupe à récupérer** sur chaque regex qui lit une valeur : règles personnalisées, lien ticket et n° de ticket (RC-03). 0 (défaut) = toute la correspondance, N = le groupe capturant N (ex. `(#)(\d+)` sur « #42 » : groupe 2 = « 42 »). Le groupe doit exister dans la regex, sinon l'enregistrement est refusé (OC-07). Règle « doit correspondre » : la valeur récupérée est affichée par le testeur ; règle « ne doit pas correspondre » : elle est citée dans le KO. Un groupe facultatif non trouvé compte comme absent. Pas de groupe pour la regex d'exclusion des branches (filtre, aucune valeur lue). |

### 7.2 Règles fixes

| Réf. | Critère | OK si | KO si | N/A si |
|---|---|---|---|---|
| RC-03 | Correspondance ticket | Le n° extrait du titre = le n° extrait du lien. | N° différents, ou absent du titre ou du lien (infobulle précisant le cas). | — |
| RC-04 | Non mergée par l'auteur | Mergeur et auteur sont des personnes différentes (voir 5.4). | Même personne, quel que soit le compte. | MR non mergée. |
| RC-05 | Pipeline vert | Au moment du merge, tous les statuts CI du dernier commit de la MR sont terminés en succès. | Au moins un statut en échec, annulé, ou encore en cours au moment du merge ; ou aucun statut. | MR non mergée, ou dépôt sans « CI attendue ». |
| RC-06 | Mergée par l'assigné (activable, désactivée par défaut) | Le mergeur est l'un des assignés de la MR (comparaison par personne, 5.4). | Le mergeur n'est aucun des assignés (infobulle : « Mergée par X, assignée à Y »). | MR non mergée, ou MR sans assigné. |

Les regex du lien et du n° de ticket de RC-03, chacune avec son groupe à récupérer (RP-09), sont dans un bloc dédié « Correspondance ticket » de l'onglet Config. N° du lien : avec un groupe ≥ 1 sur la regex du lien, la valeur de ce groupe est directement le n° de ticket (ex. `(issues\/)(\d+)` groupe 2 sur « …/issues/75 » = « 75 ») ; avec le groupe 0, la regex du n° de ticket cherche le n° dans le lien trouvé. Le n° du titre est toujours extrait par la regex du n° de ticket. Le bloc « Règles fixes » de l'onglet Config affiche la pondération de RC-03 à RC-06 et la case « Active » de RC-06.

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
| ST-01 | Onglet dédié « Statistiques », avec un sélecteur **Par personne / Par dépôt** qui bascule entre deux tableaux. La vue choisie est mémorisée dans `config.json`. Édition user : vue Par dépôt seule (ED-03). |
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
| ST-11 | Colonne « Rôle » : **Mergeur** si la personne (l'un de ses comptes) a le droit de merger sur la branche surveillée d'au moins un dépôt de l'onglet, **Dev** sinon. Survol de « Mergeur » : infobulle listant ces dépôts. Droits calculés via l'API : membres du projet (héritage des groupes inclus, `GET /projects/:id/members/all`) croisés avec les règles de branche protégée (rôle minimal, utilisateurs nommés ; règle la plus permissive si plusieurs correspondent). Branche non protégée : Developer et plus. Non pris en compte : droits accordés à un groupe (Premium), administrateurs de l'instance. Dépôt sans branche surveillée : ignoré. Triable. |
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
| VE-01 | Onglet « Vue d'ensemble », premier onglet, affiché au lancement. Seules les lignes des derniers merges sont cliquables (VE-14) ; aucun filtre : couvre tous les dépôts suivis, MR hors Draft. |
| VE-02 | Tient sans défilement sur un écran 1920 × 1080. Raccourci **F11** : plein écran activé / désactivé. |
| VE-13 | Multi-écran : le plein écran (F11) occupe l'écran sur lequel se trouve la fenêtre (celui qui en contient la plus grande partie), pas l'écran principal. Sous Windows : écran lu via `ctypes` (`MonitorFromWindow`, `GetMonitorInfoW`), fenêtre sans bordure placée sur toute la surface de cet écran, au-dessus de la barre des tâches. Second F11 : taille et position d'avant restaurées. Hors Windows : attribut `-fullscreen` de Tk. |
| VE-03 | Redessinée après chaque synchronisation automatique (CH-13). En-tête : heure de la dernière synchronisation et délai avant la prochaine. |
| VE-04 | Disposition : colonne de gauche (≈ un tiers) = fil des derniers merges, puis merges par jour ; à droite, trois niveaux : score moyen + qualité par semaine / classement des dépôts / règles enfreintes + MR créées et mergées. |
| VE-05 | **Derniers merges**, élément principal : jusqu'à 40 dernières MR mergées, de la plus récente à la plus ancienne, groupées par jour. Ligne : heure de merge, titre, dépôt, auteur → mergeur (édition admin uniquement, ED-02), pastille de score colorée. Dès que les merges du jour ne tiennent pas sur deux lignes chacun, chaque merge passe sur une seule ligne, pour voir d'un coup une journée chargée (10 à 15 merges) ; le titre est coupé (45 caractères au plus, avec « … ») pour que le dépôt et les personnes restent toujours visibles. Groupe « Aujourd'hui » mis en évidence ; nombre de merges du jour en grand dans l'en-tête. Les plus anciennes sont coupées si la place manque. |
| VE-14 | Clic sur une ligne des derniers merges : onglet Merge Requests, état **Mergées**, période réglée sur le jour du merge, autres filtres remis à zéro comme FI-18 (auteur, mergeur, assigné, relecteur, dépôt, recherche), tri par date de merge décroissante ; la page contenant la MR est affichée, sa ligne est sélectionnée et son panneau de détail ouvert (DE-01). Ces filtres sont mémorisés normalement (FI-06). Survol de la ligne : curseur main et fond de survol du thème. Aucune requête GitLab (MR déjà en base). |
| VE-06 | **Merges par jour** : semaine en cours et semaine précédente, lundi → dimanche. Chaque case affiche le nombre de merges ; son fond prend la couleur du niveau (vert / orange / rouge, seuils de la section 3, mêmes couleurs que les pastilles de score) du score moyen des MR mergées ce jour-là ; jour sans merge : fond neutre. Total par semaine. Jours à venir en pointillés. |
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
| CO-03 | Période : champs de dates, raccourci « Depuis hier » et bouton « Total » (FI-19) du filtre (communs avec l'état Mergées). |
| CO-04 | Date utilisée : date de commit (heure locale). |
| CO-05 | Un commit est « hors MR » s'il n'est associé à aucune MR dans GitLab. Les commits de merge générés par une MR ne sont pas signalés. |
| CO-06 | Colonnes : Dépôt, Branche, SHA court, Message, Auteur, Date de commit. |
| CO-07 | Clic sur un commit : ouverture de sa page GitLab dans le navigateur. |
| CO-08 | La détection interroge GitLab commit par commit : une barre de progression est affichée. Les longues périodes sont acceptées. Le résultat de chaque commit est stocké en base : un commit déjà vérifié n'est jamais réinterrogé. |
| CO-09 | Pagination identique aux MR (20 / 50 / 100 par page, taille commune). |

## 11. Branches

Objectif : identifier rapidement les branches ouvertes, mortes ou mergées non supprimées, pour relancer leur auteur (création de MR ou suppression).

| Réf. | Exigence |
|---|---|
| BR-01 | Onglet « Branches », placé après l'onglet Merge Requests. Couvre les dépôts suivis. |
| BR-02 | Colonnes : Dépôt ; Branche (clic = ouverture de la branche dans GitLab) ; **Dernier commit** au format `JJ/MM/AAAA (N j)`, N = jours calendaires écoulés depuis la date de commit (`committed_date`, heure locale), tri par date ; Auteur du dernier commit (personne, PE-03) ; MR liées ; État. |
| BR-03 | **MR liées** : toutes les MR en base du même dépôt dont la branche source est cette branche, `!iid` séparés par des virgules, ouvertes d'abord puis par date de création décroissante. Chaque `!iid` est cliquable (ouverture de la MR dans GitLab) ; survol : titre et état de la MR. Recherche locale uniquement, aucune requête. Limite : une MR hors de la période synchronisée n'est pas trouvée. |
| BR-04 | **État**, un seul par branche, dans cet ordre de priorité : **Supprimée** (absente de GitLab, BR-10 ; ligne en texte atténué) ; **Mergée non supprimée** (indicateur `merged` de GitLab, ou au moins une MR liée mergée) ; **Morte** (dernier commit plus vieux que le seuil, défaut 30 jours calendaires, réglable dans Config ; couleur « score rouge » du thème) ; **Active** sinon. |
| BR-05 | Branches exclues du tableau : branche par défaut du dépôt, branches protégées, branches dont le nom correspond à la regex d'exclusion (onglet Config, défaut `^(main\|master\|develop.*)$`, insensible à la casse). |
| BR-06 | Filtres, combinés (ET) : **Nom** (texte instantané, « contient », insensible à la casse, non mémorisé) ; **Auteur** (sélection multiple par personne, comme FI-09) ; **Dépôts** (sélection multiple parmi les dépôts suivis) ; **État** (sélection multiple, défaut : Active, Morte, Mergée non supprimée). Auteur, dépôts et état mémorisés dans `config.json`. |
| BR-07 | En-tête : nombre total de branches filtrées et décompte par état. Tri TA-02, largeurs TA-04, pagination 6.3. |
| BR-08 | Bouton **« Copier la liste »** : copie dans le presse-papiers (via `tkinter`) les branches filtrées, groupées par auteur (personne), en texte Markdown : un titre par personne, puis une ligne par branche `dépôt · branche · dernier commit (N j) · état · MR liées`. |
| BR-09 | Aucune action d'écriture sur GitLab (token `read_api`, CT-05) : la suppression ou la création de MR se fait dans GitLab. |
| BR-10 | Données : `GET /projects/:id/repository/branches` (nom, dernier commit : SHA, date, nom et e-mail de l'auteur ; `merged`, `protected`, `default`). Liste complète relue à chaque synchronisation (CH-05, CH-13) et comparée à la base : nouvelles branches ajoutées, branches modifiées mises à jour, branche absente de GitLab gardée en base et marquée **supprimée** (date de constat). Une branche recréée sous le même nom redevient active. |

## 12. Tags

Objectif : consulter les tags des dépôts suivis et leurs informations sans ouvrir GitLab.

| Réf. | Exigence |
|---|---|
| TG-01 | Onglet « Tags », placé après l'onglet Branches. Couvre les dépôts suivis. Deux sous-onglets : **Parcourir** (TG-02 à TG-09) et **Comparer** (12.1). Le sous-onglet affiché est mémorisé. |
| TG-02 | Colonnes : Dépôt ; Tag (clic = ouverture de la page du tag dans GitLab) ; Message ; Notes de release ; Date (date du commit pointé, heure locale) ; Commit (SHA court, clic = ouverture du commit) ; Auteur du commit (personne, PE-03). Tri par défaut : date décroissante. |
| TG-03 | **Message** (message du tag annoté, vide pour un tag léger) et **Notes de release** (description de la release GitLab associée, vide s'il n'y en a pas) : deux colonnes distinctes, première ligne seulement, texte complet en infobulle et dans le panneau. |
| TG-04 | Filtres, combinés (ET) : **Dépôts** (sélection multiple parmi les dépôts suivis) ; **Recherche texte** (nom, message, notes de release, SHA par préfixe dès 1 caractère ; non mémorisée) ; **Période** sur la date (deux dates `JJ/MM/AAAA`, raccourcis et bouton « Total » comme ST-05 ; défaut « Total »). Dépôts et période mémorisés. |
| TG-05 | Tag supprimé de GitLab (TG-08) : gardé, étiquette « SUPPRIMÉ » devant le nom, ligne en texte atténué. |
| TG-06 | En-tête : nombre total de tags filtrés. Tri TA-02, largeurs TA-04, pagination 6.3. |
| TG-07 | **Panneau de détail** : mêmes mécanismes que DE-01 et DE-02 (clic sur la ligne hors colonnes cliquables, ligne surlignée, flèches haut / bas, Échap, largeur réglable et mémorisée, commune avec le panneau des MR). Contenu : **en-tête** (nom, dépôt, type annoté / léger, date, « SUPPRIMÉ » s'il y a lieu, croix) ; **message** complet du tag ; **commit pointé** (SHA, titre, auteur, date ; MR dont c'est le commit de merge, de squash ou de tête, si elle est en base, cliquable) ; **release GitLab** (nom et notes complètes en texte brut, masqué s'il n'y en a pas) ; **pipeline du tag** (statut et âge du dernier pipeline de la référence du tag, jobs en échec, fin du log du premier job en échec, comme DE-08 ; masqué s'il n'y en a pas) ; bouton « Ouvrir dans GitLab ». |
| TG-08 | Données : `GET /projects/:id/repository/tags` (nom, message, commit pointé, release associée). Liste complète relue à chaque synchronisation (CH-05, CH-13) et comparée à la base, comme BR-10 : tag absent de GitLab gardé et marqué supprimé. |
| TG-09 | Pipeline du tag (`GET /projects/:id/pipelines?ref=<tag>`, puis jobs et fin de log) : lu à l'ouverture du panneau, en tâche de fond, dernière copie en base affichée aussitôt (comme DE-12). Relu si le tag pointe sur un autre commit ou si le pipeline n'est pas terminé ; un pipeline terminé n'est plus relu. |

### 12.1 Comparer des tags

Objectif : lister les MR livrées entre deux versions, sur un ou plusieurs dépôts, pour préparer ou vérifier une livraison.

| Réf. | Exigence |
|---|---|
| TC-01 | Sous-onglet **Comparer** de l'onglet Tags : un tableau de lignes de comparaison, à gauche, et un panneau de détail à droite (mêmes mécanismes que DE-01 et DE-02 : ligne surlignée, flèches haut / bas, Échap, largeur commune). |
| TC-02 | Bouton **« + Ajouter une ligne »**. Une ligne = **Dépôt** (liste des dépôts suivis), **Current** (tag ou branche du dépôt) et **Référence** (tag ou branche protégée du dépôt). Un même dépôt peut figurer sur plusieurs lignes. Croix de suppression en bout de ligne. Les lignes sont mémorisées dans `config.json` et retrouvées au lancement. |
| TC-03 | Choix de Current et Référence : listes déroulantes avec recherche, construites depuis la base (TG-08, BR-10) : tags non supprimés du dépôt, du plus récent au plus ancien, puis ses branches non supprimées : toutes pour Current, seulement les branches protégées (indicateur GitLab `protected`) pour Référence. Le panneau de détail indique la nature de chaque côté (tag, branche, branche protégée). Changer de dépôt vide les deux choix. |
| TC-04 | Calcul lancé dès que Current et Référence sont choisis, en tâche de fond, ligne par ligne ; indicateur « Calcul… » sur la ligne. Aucun bouton à cliquer. |
| TC-05 | **Commits de l'écart** : `GET /projects/:id/repository/commits?ref_name=<référence>..<current>` (commits présents dans Current et absents de Référence, d'après le graphe Git, quelles que soient les dates), paginé, sans les diffs. **Divergence** : même requête dans l'autre sens (`<current>..<référence>`). |
| TC-06 | **Commits → MR**, sans requête d'abord : SHA de merge, de squash ou de tête d'une MR en base, puis commits des MR en base (RP-04, ST-12) ; pour les commits restants, `GET /projects/:id/repository/commits/:sha/merge_requests`, une requête par commit, en parallèle (CH-06), résultat stocké une fois pour toutes (comme CO-08). Une MR est comptée une fois même si plusieurs de ses commits sont dans l'écart. Les commits sans MR sont gardés à part. |
| TC-07 | Colonnes de la ligne : Dépôt, Current, Référence, **Date current** et **Date référence** (date du commit pointé, heure locale), **MR** (nombre), **Commits hors MR** (nombre), **Score moyen** des MR (couleur selon les seuils), **Divergence** (pastille d'avertissement avec le nombre de commits de Référence absents de Current, vide sinon). Ligne en erreur si un tag ou une branche n'existe plus (« v2.3.0 introuvable »). |
| TC-08 | **Panneau de détail** (clic sur une ligne) : en-tête `dépôt · référence → current` ; liste des **MR** de l'écart, triées par date de merge décroissante : titre cliquable (ouverture dans GitLab), `!iid`, auteur → mergeur, date de merge, pastille de score ; section **Commits sans MR** (SHA court cliquable, titre, auteur, date) ; section **Divergence**, en couleur d'avertissement, si Référence a des commits absents de Current : « Présents dans la référence mais absents de current », avec les MR et commits concernés. Sections vides masquées. |
| TC-09 | Bouton **« Copier en Markdown »** : toutes les lignes calculées, un titre par ligne (`dépôt : référence → current`), puis une ligne par MR (`!iid titre — auteur`), puis les commits sans MR. Copie via le presse-papiers `tkinter`. |
| TC-10 | Données stockées : les commits de l'écart et leurs MR sont stockés par couple (SHA de Référence, SHA de Current) : une comparaison déjà calculée s'affiche sans requête. Current sur une branche : recalculé quand la tête de la branche change (BR-10). Un tag déplacé sur un autre commit est recalculé. |
| TC-11 | Limites : un commit cherry-pické change de SHA et n'est pas relié à sa MR d'origine (il apparaît dans « Commits sans MR ») ; deux tags très éloignés peuvent demander de nombreuses requêtes la première fois (barre de progression sur la ligne) ; les deux références doivent appartenir au même dépôt. |

## 13. Chargement, base locale et rafraîchissement

| Réf. | Exigence |
|---|---|
| CH-01 | Les appels GitLab s'exécutent en tâche de fond ; l'IHM reste réactive. |
| CH-02 | Indicateur de chargement visible pendant les appels. |
| CH-03 | Base locale persistante `gitective.db` (SQLite, `sqlite3`) : projets accessibles, MR (dont assignés et relecteurs), commits de MR, commits des branches surveillées, résultats de détection hors MR, statuts CI, membres et branches protégées, utilisateurs et avatars, branches (dernier commit, indicateurs, date de suppression constatée, BR-10), tags (message, release, commit pointé, date de suppression constatée, TG-08), pipelines des tags (TG-09), commits et MR des comparaisons de tags et MR liées à chaque commit (TC-06, TC-10), utilisateur du token (5.7), détails de MR du panneau (état de merge, approbations, discussions, pipeline et jobs, fin des logs en échec, fichiers modifiés, DE-12), MR ouvertes de tous les dépôts où l'utilisateur est assigné ou relecteur, et couples MR / rôle déjà vus (AM-02, AM-04). Le changement de page, de tri ou de filtre lit la base sans réinterroger GitLab. |
| CH-04 | Un changement de filtre ou de dates ne déclenche une requête GitLab que pour la partie de la période absente de la base. |
| CH-05 | Bouton **Rafraîchir** : mise à jour incrémentale depuis la dernière synchronisation de chaque dépôt (MR via `updated_after`, commits via `since`), relecture des branches et des tags (BR-10, TG-08) et retéléchargement des avatars. |
| CH-13 | **Synchronisation automatique** : toutes les N minutes (réglable dans l'onglet Config, défaut 5), même fenêtre réduite, la mise à jour incrémentale des MR et commits de CH-05 et la relecture des branches et des tags (BR-10, TG-08) s'exécutent en tâche de fond (avatars : au bouton Rafraîchir uniquement). Puis rafraîchissement de l'affichage, des badges (BA-04) et des notifications (NO-04). Ignorée si une synchronisation est déjà en cours. Instance injoignable : nouvel essai au cycle suivant, bandeau CH-08. |
| CH-06 | Les requêtes « une par commit » (commits hors MR) et « une par MR » (règles sur les commits, RC-05, ST-12) partent en parallèle, comme les lectures de branches et tags des différents dépôts ; le nombre de requêtes simultanées se règle dans l'onglet Config (1 à 16, défaut 6). |
| CH-07 | Les règles sont évaluées localement à partir des données en base : modifier une règle, une pondération ou une correspondance de personnes recalcule l'affichage sans requête GitLab. Idem pour la regex d'exclusion et le seuil des branches. |
| CH-08 | Mode hors ligne : si l'instance est injoignable, l'application affiche les données en base et un bandeau indique la date de dernière synchronisation. |
| CH-09 | Données immuables jamais relues : comparaison de deux commits (TC-10), MR d'un commit (TC-06), commits d'une MR mergée, statuts CI d'une MR mergée (PI-05), résultat de détection d'un commit (CO-08), pipeline terminé d'un tag (TG-09). |
| CH-10 | La base est liée à l'URL de l'instance. Un changement d'URL dans l'onglet Config propose de vider la base. |
| CH-11 | La base porte un numéro de version de schéma ; une version de l'application plus récente migre le schéma au démarrage. |
| CH-12 | Accès concurrents : une connexion SQLite par thread ; les écritures sont faites par les tâches de fond, en transactions. |

## 14. Gestion des erreurs

| Réf. | Exigence |
|---|---|
| ER-01 | Notification par bandeau coloré dans l'application, refermable. |
| ER-02 | Message clair et spécifique : token invalide ou expiré, droits insuffisants, réseau coupé / instance injoignable, erreur de certificat SSL, dépôt, branche ou tag introuvable. |
| ER-03 | Une erreur n'interrompt pas l'application ; l'utilisateur peut corriger puis rafraîchir. |
| ER-04 | Toutes les erreurs passent par le bandeau de notification (pas de fichier de log). Les erreurs de la synchronisation automatique (CH-13) ne déclenchent pas de notification de bureau. |
| ER-05 | Limitation de débit GitLab (HTTP 429) et timeout réseau (30 s) : 3 nouvelles tentatives automatiques après 2, 4 puis 8 s, puis notification. Valeurs fixes. |
| ER-06 | Base locale illisible, corrompue ou verrouillée : notification, et proposition de la recréer (resynchronisation complète depuis GitLab). |

## 15. Architecture du code

### 15.1 Principes

| Réf. | Exigence |
|---|---|
| AR-01 | Découpage par sujet, en trois niveaux : **`forge`** (requêtes GitLab) ← **métier** (`database`, `review`, `repository`, `reporting`, `shared`, `settings`) ← **`ui`**. Un niveau ne dépend que des niveaux inférieurs. Le métier dépend uniquement de l'interface `ForgeClient` (15.3), jamais de `GitLabClient` ; seule l'IHM crée le client. |
| AR-07 | `forge` est isolé : il n'importe que la bibliothèque standard et ses propres modules. Il peut être copié tel quel dans un autre projet. |
| AR-08 | Noms explicites : un dossier par sujet, un fichier par fonctionnalité, nommé avec les termes de l'IHM (ex. `direct_commits.py` pour l'état « Commits directs »). Les tests reprennent les mêmes dossiers. |
| AR-02 | Code, noms et commentaires en anglais. Les textes affichés passent tous par `shared/i18n.py` (LG-05). |
| AR-03 | Commentaires synthétiques et logiques : docstring courte pour chaque module, classe et fonction publique ; commentaire en ligne uniquement pour la logique non évidente. |
| AR-04 | Annotations de type partout. |
| AR-05 | Tests unitaires avec `unittest` : règles de contrôle (dont RC-05 et RC-06), classe API (réponses HTTP simulées), base locale (base SQLite en mémoire), recherche (dont SHA par préfixe, FI-20), droits de merge (ST-11 : niveaux d'accès, branche protégée, `developers_can_merge`), MR ouvertes de l'utilisateur (tous dépôts, rôles assigné / relecteur / les deux, MR créées pour le badge Auteur), détection des nouveautés (AM-02, AM-04, NO-04, NO-09, NO-11), données du panneau de détail (état « prête à merger », extraction de la fin des logs, comptage des lignes des fichiers modifiés, DE-05 à DE-10), branches (état et priorité, exclusions, MR liées, liste copiée, comparaison avec la base et marquage supprimé, BR-03 à BR-10) et tags (comparaison avec la base, MR du commit pointé, TG-07, TG-08), comparaison de tags (commits → MR sans requête puis par requête, MR comptée une fois, divergence, texte copié, recalcul d'une branche dont la tête a changé, TC-05 à TC-10), traductions (mêmes clés et mêmes paramètres en français et en anglais, LG-05), édition user (blocs admin retirés, chaque fichier reste du Python valide, ED-05). |
| AR-06 | `README.md` en anglais : prérequis, installation, configuration, utilisation. |

### 15.2 Arborescence

```
gitective/
├── main.py / main.pyw          # Entry points
├── .github/workflows/release.yml # Release on every push to main (18.3)
├── tools/make_edition.py       # Builds the admin or user edition (ED-05)
├── README.md                   # Installation and usage (English)
├── config.json                 # Created on first launch
├── gitective.db                # Local SQLite store (CH-03)
├── docs/
│   ├── specification_controle_MR.md
│   └── README_user.md          # README of the user edition: GitLab token only (ED-06)
├── gitective/
│   ├── assets/                 # logo.svg, logo.png, logo.ico
│   ├── forge/                  # GitLab requests, isolated (AR-07)
│   │   ├── protocol.py         # ForgeClient: forge-neutral interface
│   │   ├── gitlab_client.py    # GitLabClient: GitLab implementation
│   │   ├── models.py           # Project, MergeRequest, Commit, CommitStatus, User, ProtectedBranch, Branch, Tag, Pipeline, Job
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
│   │   └── my_mrs.py           # Token user, my open MRs (assignee, reviewer, author), "new" flags
│   ├── repository/             # Branches and tags tabs logic
│   │   ├── branches.py         # Branch state, exclusions, related MRs, copied list, deleted marking
│   │   ├── tags.py             # Tag list, deleted marking, pointed-commit MR, tag pipeline
│   │   └── tag_compare.py      # Commits and MRs between two references, divergence, copied text
│   ├── reporting/              # Figures shown to the user
│   │   ├── statistics.py       # Per-person and per-repository statistics, lead times
│   │   └── overview_figures.py # Overview tab figures
│   ├── shared/                 # Cross-cutting helpers
│   │   ├── dates.py            # Date parsing, "since yesterday", local timezone
│   │   ├── i18n.py             # Language choice and translation function (5.9)
│   │   ├── translations_en.py  # English texts, keyed by the French text
│   │   ├── people.py           # Account-to-person mapping
│   │   ├── search.py           # Text and SHA prefix search
│   │   ├── parallel.py         # Concurrent forge lookups
│   │   └── avatars.py          # Avatar download, storage, initials fallback
│   ├── settings/
│   │   └── config_file.py      # Load/save config.json, defaults
│   └── ui/
│       ├── app.py              # Main window, tabs, badges, window title count, F11 on the current monitor
│       ├── themes.py           # Default, Light, Dark, Windows 95, Matrix
│       ├── background.py       # Background tasks and progress
│       ├── first_launch_wizard.py
│       ├── tabs/
│       │   ├── data_tab.py     # Base class of the data tabs
│       │   ├── overview.py     # Overview, latest merges clickable (VE-14)
│       │   ├── merge_requests.py # MR tab, filters, reset, "Total", open MRs of other repos, "new" column
│       │   ├── mr_detail_panel.py # Side panel with the selected MR details (6.6)
│       │   ├── direct_commits.py # Direct commits view of the MR tab
│       │   ├── branches.py     # Branches tab, filters, copy list
│       │   ├── tags.py         # Tags tab: Parcourir / Comparer sub-tabs, filters
│       │   ├── tag_compare.py  # Comparer sub-tab: comparison lines, detail panel, copy (12.1)
│       │   ├── tag_detail_panel.py # Side panel with the selected tag details (TG-07)
│       │   ├── statistics.py   # Per-person / per-repository switch
│       │   └── config.py       # Config tab, connection test, rule tester, branches, token user, notifications, language
│       ├── components/
│       │   ├── gauge.py        # Colour-blind theme: 3-bar gauges, hatches, dots, dash patterns (5.2.1)
│       │   ├── grid.py         # Custom colored grid, sorting, tooltips
│       │   ├── pagination.py
│       │   ├── side_panel.py   # Shared side panel frame: resize, scroll, keyboard navigation
│       │   ├── chart.py        # Weekly score line chart (Canvas)
│       │   ├── filter_bar.py   # State, dates, repositories, people, drafts filters
│       │   ├── dialogs.py      # Rule, repository and person dialogs
│       │   └── widgets.py      # Multi-select, scrollable frame, small widgets
│       └── alerts/
│           ├── error_banner.py # In-app error banner
│           ├── desktop_toast.py # Desktop notifications and taskbar flash (ctypes)
│           └── badges.py       # Assignee, reviewer and author badges (Canvas icons)
└── tests/                      # Same folders as gitective/
    ├── factories.py
    ├── forge/       test_gitlab_client.py
    ├── database/    test_store.py, test_project_list.py
    ├── review/      test_rules.py, test_pipeline.py, test_merge_rights.py, test_my_mrs.py, test_mr_detail.py
    ├── repository/  test_branches.py, test_tags.py, test_tag_compare.py
    ├── reporting/   test_statistics.py, test_overview_figures.py
    ├── shared/      test_parallel.py, test_search.py, test_i18n.py
    └── tools/       test_make_edition.py   (not shipped)
```

### 15.3 Interface forge et classe API GitLab

L'interface `ForgeClient` (`typing.Protocol`) décrit les opérations dont le métier a besoin, en termes neutres. `GitLabClient` en est l'implémentation GitLab ; un adaptateur pour une autre forge (GitHub, Gitea…) pourra être ajouté sans modifier le métier ni `ui`.

| Réf. | Exigence |
|---|---|
| API-01 | Construction : URL de l'instance, token, option de vérification SSL. |
| API-02 | Basée sur `urllib.request` ; en-tête `PRIVATE-TOKEN`. |
| API-03 | Gestion transparente de la pagination GitLab. |
| API-04 | Renvoie des objets métier typés et neutres (`Project`, `MergeRequest`, `Commit`, `CommitStatus`, `User`, `ProtectedBranch`, `Branch`, `Tag`, `Pipeline`, `Job`), pas de JSON brut ni de champ propre à GitLab. |
| API-05 | Lève des exceptions dédiées, définies au niveau de l'interface : authentification, droits, ressource introuvable, réseau, SSL. |
| API-06 | Méthodes minimales : lire l'utilisateur du token ; lister les projets accessibles ; lire le niveau d'accès du token sur un projet ; lister les MR d'un projet (état, dates, mises à jour depuis une date) ; lister les MR ouvertes de toute l'instance où un utilisateur est assigné, ou relecteur ; lister les commits d'une MR ; lister les commits d'une branche (dates) ou d'un intervalle `référence..current` (TC-05) ; lister les MR associées à un commit ; lister les statuts CI d'un commit ; lister les membres d'un projet avec leur niveau d'accès ; lister les branches protégées d'un projet ; lister les branches d'un projet (dernier commit, mergée, protégée, par défaut) ; lister les tags d'un projet (message, commit pointé, release associée) ; lire une branche (protégée, merge autorisé aux développeurs) ; lister les pipelines d'une référence ; pour le panneau de détail (6.6) : lire une MR (état de merge détaillé, conflits, retard sur la cible), lister ses approbations, ses discussions, ses fichiers modifiés (lignes ajoutées / retirées), les jobs d'un pipeline et la fin du log d'un job. `Project` porte la branche par défaut ; `MergeRequest` porte ses assignés, ses relecteurs et les SHA de tête, de merge et de squash. |
| API-07 | `GitLabClient` reste générique et réutilisable, indépendant de l'application. |

## 16. Jalons

| Jalon | Contenu |
|---|---|
| J1 | Application exécutée par Python installé (périmètre de ce document). |
| J2 | Exécutable Windows autonome, livré par la release GitHub (section 18). |

## 17. Points ouverts

| Point | Statut |
|---|---|
| Onglet Statistiques réservé à un mode admin | Tranché en v1.25 : éditions admin et user (section 18). |

## 18. Éditions et livraison

### 18.1 Éditions admin et user

| Réf. | Exigence |
|---|---|
| ED-01 | Deux éditions construites depuis le même code : **admin** (complète) et **user** (conformité RGPD : aucun chiffre ni classement par personne). L'édition est figée à la construction, non réglable dans `config.json`. Elle est affichée dans l'en-tête (VR-03). |
| ED-02 | Édition user, **Vue d'ensemble** : les derniers merges (VE-05) n'affichent pas « auteur → mergeur ». Le reste de l'onglet ne nomme personne et ne change pas. |
| ED-03 | Édition user, **Statistiques** : vue Par dépôt seule. Ni sélecteur Par personne / Par dépôt, ni filtre Personnes (FI-09 ne s'applique pas à l'onglet, SR-03 sans objet), ni clic sur un dépôt (SR-05, colonne Dépôt en texte simple). Les commits des MR mergées et les droits de merge ne sont pas lus (ST-11, ST-12 sans objet). |
| ED-04 | Le reste de l'IHM est identique dans les deux éditions (onglet Merge Requests, Branches, Tags, notifications, badges, Config). |
| ED-05 | Le code propre à l'admin est **retiré** de l'édition user, pas masqué : il est placé dans des blocs `# admin:begin` / `# admin:end` (code, tests, textes anglais), que `tools/make_edition.py` supprime. Blocs non imbriqués ; le code qui reste fonctionne seul. Un test vérifie que chaque fichier reste du Python valide une fois les blocs retirés ; les tests sont relancés dans chaque édition construite. |
| ED-06 | README de l'édition user : uniquement la création du token GitLab `read_api` (`docs/README_user.md`). L'édition admin garde le README complet. |

### 18.2 Versions

| Réf. | Exigence |
|---|---|
| VR-01 | **Version du logiciel** `X.Y.Z` dans `gitective/__init__.py`, augmentée à chaque modification selon son ampleur (majeure / normale / mineure). |
| VR-02 | **Numéro de livraison** `AAAA.MM.JJ-N` : date du push (heure de Paris) et compteur du jour à partir de 1. C'est le tag Git de la release. |
| VR-03 | En-tête de la fenêtre, à côté du nom : version, numéro de livraison, édition (« v1.2.0 · 2026.10.29-1 · user »). Lancé depuis le dépôt Git : « v1.2.0 · admin ». |

### 18.3 Livraison

| Réf. | Exigence |
|---|---|
| LV-01 | Déclencheur : chaque push sur `main` (GitHub Actions, runner Windows, Python 3.11). Chaque PR vers `develop` ou `main` exécute les mêmes tests et builds, sans publier. Tests en échec et erreurs de build repris en annotations GitHub. |
| LV-02 | Étapes : tests, numéro de livraison, construction des deux éditions (tests relancés dans chacune), publication. Un échec arrête la livraison. |
| LV-03 | Release GitHub publique, tag VR-02, titre « Gitective X.Y.Z (AAAA.MM.JJ-N) », notes générées depuis les PR. Quatre fichiers : `Gitective-admin.exe`, `Gitective-admin.zip`, `Gitective-user.exe`, `Gitective-user.zip`. |
| LV-04 | `.zip` : code source de l'édition, à lancer avec Python 3.11+ (comme J1). `.exe` : PyInstaller, un seul fichier, sans console, icône `logo.ico` ; `config.json` et `gitective.db` sont créés à côté de l'exe. |
| LV-05 | Limites : exe non signé (alerte SmartScreen ou antivirus possible) ; release publique, édition admin téléchargeable par tous (elle ne contient aucune donnée, celles-ci viennent du token GitLab). |

### 18.4 Branches Git

| Réf. | Exigence |
|---|---|
| BG-01 | `main` = livraisons, `develop` = intégration. Les branches `feature/…` ou `fix/…` partent de `develop`, PR vers `develop` mergée en squash, branche supprimée automatiquement au merge. |
| BG-02 | Livraison : PR `develop` → `main` mergée en **merge commit** (pas en squash, sinon les deux branches divergent). |
| BG-03 | `main` et `develop` sont protégées contre la suppression (ruleset GitHub). |
