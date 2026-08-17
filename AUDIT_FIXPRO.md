# Audit FixPro Guinée — Phase 0

**Date** : 2026-08-18  
**Branche active** : `feature/responsive-ux-improvements`  
**Objectif** : analyser l'état actuel sans modifier le code.  

---

## 1. Architecture et stack technique

| Composant | Technologie | État |
|---|---|---|
| Backend | Flask 3.1, Python 3.12 | Stable, 73 routes dans `fixpro_app.py` |
| ORM | Aucun, SQL brut via `db.py` | Léger, bien testé, mais verbeux |
| Frontend web | Jinja2 + CSS | Deux systèmes coexistent |
| Admin dashboard | Next.js 14 | Présent, connecté par API key |
| Mobile | Flutter 3.12, supabase_flutter | Code présent, non audité en détail |
| Base de données | SQLite local / Supabase PostgreSQL prod | `db.py` unifie les deux |
| Auth | Sessions Flask + Google OAuth (Authlib) | En place client et admin |
| Paiement | Aucune API externe | Mock enregistré en base `pending` |
| Déploiement | Vercel serverless | `api/index.py` exposant `app` |
| CI/CD | GitHub Actions | Tests + deploy Vercel |
| Rate limiting | Flask-Limiter | Sur routes sensibles |

**Constat** : l'application est un monolithe Flask de plus de 3 100 lignes avec toutes les routes. Aucun blueprint. C'est acceptable pour un MVP mais la dette technique s'accumule.

---

## 2. Base de données

### 2.1 Schéma

Fichiers : `schema.sql`, `schema_sqlite.sql`, `migrations/`

Tables principales :
- `users` (clients, artisans, admins)
- `service_categories`
- `requests` (demandes d'intervention)
- `messages` (chat lié à une demande)
- `payments`
- `reviews`
- `technician_documents`
- `technician_locations`
- `artisan_portfolio`
- `admin_tickets` / `admin_messages` (support)
- `admin_logs`
- `settings`

### 2.2 Ce qui fonctionne

- Clés étrangères et `ON DELETE CASCADE/SET NULL` présentes.
- Index sur `users.email`, `users.phone`, `users.role`, `requests.client_id`, `requests.artisan_id`, `requests.status`, `messages.request_id`, `payments.request_id`.
- `db.py` traduit automatiquement `?` en `%s` pour PostgreSQL.

### 2.3 Problèmes

| Fichiers | Problème | Gravité | Impact | Risque | Solution | P |
|---|---|---|---|---|---|---|
| `schema_*.sql`, `users` | `email` non obligatoire, `phone` obligatoire. OK pour Guinée. | FAIBLE | - | - | Conserver | P2 |
| `schema_*.sql`, `requests` | `status` en TEXT sans contrainte d'enum. N'importe quelle valeur peut être injectée. | ÉLEVÉ | États incohérents possibles | Transitions illégales | Ajouter CHECK ou normaliser en Python | P1 |
| `schema_*.sql`, `payments` | `status` TEXT, pas de workflow de paiement validé. | ÉLEVÉ | Paiements non confirmés | Fausse confiance client | Implémenter vrai statut + validation externe | P0 |
| `fixpro_app.py` | Documents et photos stockés en base64 dans `users.photo_url`, `technician_documents.content_base64`, `artisan_portfolio.photo_url`. | ÉLEVÉ | Base lourde, coûts Supabase, latence | Base qui grossit rapidement | Migrer vers stockage objet (Supabase Storage / S3) | P0 |
| `db.py` | Aucun pool de connexions. | MOYEN | Latence en production | Saturation si trafic élevé | Utiliser psycopg2 pool ou SQLAlchemy pool | P2 |

---

## 3. Authentification et autorisations

### 3.1 Ce qui fonctionne

- `login_required` et `admin_required` décorateurs présents.
- CSRF via `flask_wtf` dans les formulaires.
- Mots de passe hachés avec Werkzeug.
- Google OAuth client + admin.
- `check_artisan_verification()` redirige les artisans non vérifiés.

### 3.2 Problèmes

| Fichiers | Problème | Gravité | Impact | Risque | Solution | P |
|---|---|---|---|---|---|---|
| `config.py` | `ADMIN_PASSWORD` fallback en développement. Si `FLASK_ENV` mal configuré en prod, passe `admin`. | ÉLEVÉ | Contournement admin | Fuite de droits | Supprimer fallback en prod, forcer variables | P1 |
| `fixpro_app.py`, `admin_login` | Admin login utilise `ADMIN_EMAILS` + `ADMIN_PASSWORD` si OAuth absent. Pas de 2FA. | MOYEN | Usurpation admin | Accès non autorisé | Documenter fortement, restreindre variables | P2 |
| `fixpro_app.py`, `get_current_user()` | Récupère `user_id` en session. Pas de vérification `is_active`. | MOYEN | Utilisateur suspendu peut rester connecté | Accès non autorisé | Vérifier `is_active` à chaque requête | P1 |
| `fixpro_app.py`, `can_access_request()` | Existe mais ne couvre pas tous les endpoints. | ÉLEVÉ | Fuite de données | IDOR | Auditer chaque endpoint `/<int:request_id>` | P1 |

### 3.3 Vérification d'IDOR (aperçu)

Routes concernées par un audit approfondi nécessaire :
- `/requests/<int:request_id>`
- `/requests/<int:request_id>/accept`
- `/requests/<int:request_id>/quote`
- `/requests/<int:request_id>/payment`
- `/requests/<int:request_id>/payment/process`
- `/requests/<int:request_id>/complete`
- `/api/messages/<int:request_id>`
- `/tickets/<int:ticket_id>`
- `/admin/artisans/<int:artisan_id>`
- `/admin/document/<int:doc_id>`

---

## 4. Système de demandes (parcours client)

### 4.1 États actuels

`requests.status` : `pending`, `assigned`, `in_progress`, `completed`, `cancelled`.
`requests.quote_status` : `none`, `pending`, `accepted`, `rejected`.

### 4.2 Problèmes

| Fichiers | Problème | Gravité | Impact | Risque | Solution | P |
|---|---|---|---|---|---|---|
| `fixpro_app.py`, `request_new()` | Acceptation automatique d'un artisan proche. Pas de choix client. | ÉLEVÉ | UX faible, pas de contrôle client | Mauvais matching | Permettre choix explicite ou confirmation | P1 |
| `fixpro_app.py`, `accept_request()` | Technicien peut accepter n'importe quelle `pending`. Vérification `can_access_request` OK mais pas de vérification artisan_id. | MOYEN | Technicien accepte mauvaise demande | Interventions incorrectes | Vérifier que la demande n'est pas déjà assignée | P1 |
| `templates/request_detail.html` | ETA affichée en dur `07 min`. | MOYEN | Information fausse | Mésinformation client | Connecter à la géolocalisation réelle | P2 |
| `fixpro_app.py`, `propose_quote()` | Devis proposé par technicien sans validation client. | MOYEN | Prix non validé | Litiges | Workflow acceptation devis | P2 |

---

## 5. Paiement

### 5.1 Architecture actuelle

Fichier : `fixpro_app.py` lignes 2717–2798.

- Moyens acceptés : `orange_money`, `mtn_mobile_money`, `card`, `cash`, `mobile_money`.
- Le backend insère un paiement `pending` dans `payments` sans vérification externe.
- Commission de 10 % calculée côté serveur.

### 5.2 Problèmes

| Fichiers | Problème | Gravité | Impact | Risque | Solution | P |
|---|---|---|---|---|---|---|
| `fixpro_app.py`, `process_payment()` | Paiement enregistré sans API Orange Money. N'importe quel client peut marquer un paiement. | CRITIQUE | Marketplace non viable sans paiement réel | Fraude massive | Intégrer API Orange Money en sandbox ou workflow manuel avec vérification | P0 |
| `fixpro_app.py` | `paid_to_artisan_at` jamais mis à jour automatiquement. | ÉLEVÉ | Technicien jamais payé | Désertion | Ajouter workflow admin de libération | P0 |
| `schema_*.sql`, `payments` | Aucune contrainte UNIQUE sur `reference`. | MOYEN | Doubles paiements possibles | Perte financière | Ajouter `UNIQUE(reference)` | P1 |

---

## 6. Géolocalisation

### 6.1 Ce qui fonctionne

- `technician_locations` stocke position du technicien.
- API `POST /api/technicien/position` et `GET /api/technicien/<id>/position`.
- `calculate_distance()` basé sur Haversine.
- `_geocode_zone()` a une carte statique quartier/ville → lat/lon.

### 6.2 Problèmes

| Fichiers | Problème | Gravité | Impact | Risque | Solution | P |
|---|---|---|---|---|---|---|
| `fixpro_app.py`, `_geocode_zone()` | Dictionnaire statique limité. | MOYEN | Localisations approximatives | Mauvais matching | Intégrer Nominatim ou Google Geocoding | P2 |
| `templates/request_form.html` | Ligne "Votre position" affiche `user.quartier or user.city` sans GPS. | MOYEN | Adresse fausse si client déménagé | Mauvaise intervention | Demander GPS + adresse manuelle | P1 |
| `templates/request_detail.html` | Carte SVG statique. | MOYEN | Aucune position temps réel | Mésinformation | Connecter API position technicien | P2 |

---

## 7. UX / UI / Responsive

### 7.1 Systèmes de design

| Fichier | Utilisateurs |
|---|---|
| `api/static/css/app.css` | `login.html` (avant modif), `dashboard_client.html`, `admin_*.html`, `landing.css` (indirect), `register.html` |
| `api/static/css/design-v2.css` | `index.html`, `artisans.html`, `artisan_detail.html`, `request_form.html`, `request_detail.html`, `requests.html`, `conversations.html`, `tickets.html`, `ticket_detail.html`, `register_artisan.html`, `client_signup.html`, `login.html` (après modif) |
| `api/static/css/landing.css` | `landing.html` |

**Constat majeur** : deux design systems coexistent. L'expérience n'est pas cohérente d'une page à l'autre.

### 7.2 Problèmes détaillés

| Fichiers | Problème | Gravité | Impact | Risque | Solution | P |
|---|---|---|---|---|---|---|
| `templates/index.html` | Lien vers `register_artisan` avec `step=1` (wizard supprimé). Route 404. | CRITIQUE | Inscription technicien cassée depuis landing | Perte d'inscriptions | Corriger en `url_for('register_artisan')` | P0 |
| `templates/index.html` | Emoji `🔧` comme icône technicien. | MOYEN | Non conforme `AGENTS.md` | Affichage incohérent | Remplacer par SVG | P1 |
| `templates/request_form.html` | Emojis `📍`, `📷`, `✓` dans le formulaire. | MOYEN | Non conforme | - | Remplacer par SVG/texte | P1 |
| `templates/request_detail.html` | Emojis `✓` dans le stepper. Plusieurs occurrences. | MOYEN | Non conforme | - | Remplacer par SVG/texte | P1 |
| `templates/artisans.html` | `fx-tabbar` interne en plus du `tabbar` global de `base.html`. | ÉLEVÉ | Double navigation sur mobile | Confusion UX | Supprimer `fx-tabbar` ou unifier | P1 |
| `templates/base.html` | Sidebar + appbar + topbar + mobile-nav + tabbar + fx-tabbar. Beaucoup d'éléments. | ÉLEVÉ | Chevauchements possibles | Confusion | Simplifier la navigation | P1 |
| `templates/artisans.html` | `clientLoc` statique `"Conakry"`. | MOYEN | Mauvaise localisation affichée | UX faible | Connecter vraie position ou fallback | P2 |
| `templates/request_detail.html` | Map SVG statique. Pas de données temps réel. | MOYEN | Fausse carte | Méfiance client | Connecter positions | P2 |
| `api/static/css/design-v2.css` | Media query desktop ne faisait que border-radius avant la dernière modification. Reste à vérifier sur toutes les pages. | MOYEN | Bandes vides sur desktop | UX desktop mauvaise | Adapter page par page | P1 |
| `templates/login.html` | Refondu en design-v2. À valider en déploiement preview. | FAIBLE | Régression possible | - | Tester responsive | P2 |
| `templates/client_signup.html` | Email obligatoire. En Guinée beaucoup d'utilisateurs n'ont pas d'email. | MOYEN | Abandon inscription | Perte clients | Rendre email facultatif | P1 |
| `templates/pending.html` | Emoji `⏳`. | FAIBLE | Non conforme | - | Remplacer par SVG | P2 |
| `templates/dashboard_client.html` | Encore en `app.css`. Style sombre. | ÉLEVÉ | Cohérence visuelle cassée | UX amateur | Migrer design-v2 | P1 |
| `templates/landing.html` | Dépend de `landing.css`. Bien conçu mais palette légèrement différente. | FAIBLE | Micro-incohérence | - | Harmoniser variables | P3 |

### 7.3 Responsive

Points de rupture à tester : 320, 375, 390, 430, 768, 1024, 1440 px.

Constats statiques :
- `design-v2.css` est mobile-first.
- `.fx-screen` étendu à 960 px en desktop après la dernière PR.
- Formulaires `.fx-narrow` restent 560 px, confortables.
- `landing.css` a son propre responsive, à auditer séparément.
- `app.css` responsive non vérifié sur toutes les pages.

---

## 8. Mobile

| Fichiers | Problème | Gravité | Solution | P |
|---|---|---|---|---|
| `templates/base.html` | `tabbar` apparaît sur toutes les pages connectées. Conflit avec `fx-tabbar`. | ÉLEVÉ | Unifier | P1 |
| `templates/artisans.html` | `fx-tab-ic` est un carré gris sans icône. | MOYEN | Ajouter SVG | P2 |
| `design-v2.css` | `fx-chip` 7 px vertical, 11 px font. Peut être juste. | FAIBLE | Augmenter padding | P3 |
| `design-v2.css` | `fx-tab` 9.5 px font. Petit. | FAIBLE | 10.5 px minimum | P2 |

---

## 9. Application Flutter

Fichier : `mobile/pubspec.yaml`

- Dépendances : `supabase_flutter`, `http`.
- Aucun code audité.
- Points à vérifier : authentification, endpoints appelés, gestion offline, upload photos.

---

## 10. Dashboard admin

| Fichiers | Problème | Gravité | Solution | P |
|---|---|---|---|---|
| `admin-nextjs/` | Dashboard Next.js existe. Connexion par `ADMIN_API_KEY`. | MOYEN | Vérifier CORS + sécurité clé | P2 |
| `templates/admin_*.html` | Templates Flask admin sombres, séparés. | MOYEN | Maintenir ou migrer ? | P2 |
| `fixpro_app.py`, routes admin | Pas de vérification `admin_required` sur toutes les routes `admin/*` ? | ÉLEVÉ | Vérifier chaque route | P1 |

---

## 11. Tests

### 11.1 Couverture actuelle

Fichier : `tests/test_app.py`

Classes de tests :
- `HealthAndSecurityTests`
- `ClientRegistrationTests`
- `ArtisanRegistrationTests`
- `RequestWorkflowTests`
- `MessagingTests`
- `GeolocationTests`
- `AdminPanelTests`
- `DatabaseLayerTests`
- `ConfigurationTests`

**Résultat** : `42 passed` (dernier run).

### 11.2 Manques critiques

- Aucun test IDOR sur `/requests/<id>`.
- Aucun test de vérification de paiement.
- Aucun test d'upload malveillant.
- Aucun test de l'API admin.
- Aucun test du wizard technicien actuel.
- Aucun test du wizard client.

---

## 12. Ce qui fonctionne et ne PAS casser

1. **Authentification sessions + Google OAuth** : stable, tests OK.
2. **CRUD demandes** : création, devis, acceptation, completion, annulation fonctionnent.
3. **Chat par demande** : `messages` lié à `request_id`, `api/messages` fonctionne.
4. **Support tickets** : `admin_tickets` + `admin_messages` opérationnel.
5. **Vérification artisan** : admin peut valider/refuser via API Next.js.
6. **Rate limiting** : actif sur inscriptions sensibles.
7. **CSRF** : présent dans les formulaires principaux.
8. **Base de données SQLite/PostgreSQL** : `db.py` fonctionne pour les deux.
9. **Vercel deployment** : `api/index.py` expose `app`.
10. **Tests pytest** : 42 passent, base temporaire propre.
11. **Design v2** : pages refondues sont modernes et mobiles.

---

## 13. Bugs critiques déjà identifiés

1. `templates/index.html` → `register_artisan` avec `step=1` (route supprimée). **P0**.
2. Paiement non vérifié, n'importe quel client peut enregistrer un paiement. **P0**.
3. Uploads base64 en base de données. **P0/P1**.
4. Double navigation mobile (`tabbar` + `fx-tabbar`). **P1**.
5. `dashboard_client.html` en thème sombre incohérent. **P1**.
6. Manque de vérification `is_active` sur `get_current_user()`. **P1**.
7. `requests.status` sans contrainte d'enum. **P1**.
8. `client_signup.html` email obligatoire. **P1**.
9. Géolocalisation client non vraiment utilisée. **P1**.
10. ETA statique 07 min. **P2**.

---

## 14. Feuille de route recommandée

### Phase 1 — Stabilisation (branche existante ou `feature/stabilisation`)

1. Corriger `index.html` lien `register_artisan` sans `step`.
2. Remplacer tous les emojis dans les templates par SVG/texte.
3. Unifier la navigation mobile (supprimer doublon `tabbar`/`fx-tabbar`).
4. Migrer `dashboard_client.html` en design-v2.
5. Vérifier `login.html` refondu en responsive.
6. Ajouter `aria-label` sur icônes sans texte.

### Phase 2 — Sécurité et qualité

7. Auditer IDOR sur toutes les routes `/requests/<id>`.
8. Vérifier `is_active` dans `get_current_user()`.
9. Ajouter tests manquants critiques.
10. Restreindre `ADMIN_PASSWORD` en production.

### Phase 3 — Fonctionnalités

11. Paiement Orange Money sandbox.
12. Stockage objet pour uploads.
13. Géolocalisation client GPS + adresse manuelle.
14. Matching par score classique.
15. Dashboard technicien complet.

### Phase 4 — Intelligence

16. Diagnostic par texte.
17. Matching avancé.
18. Recommandations.

---

## 15. Top 10 problèmes

| # | Problème | Gravité | Priorité | Fichiers |
|---|---|---|---|---|
| 1 | Lien `register_artisan` cassé sur accueil | CRITIQUE | P0 | `templates/index.html` |
| 2 | Paiement non vérifié | CRITIQUE | P0 | `fixpro_app.py`, `payment_page.html` |
| 3 | Uploads base64 en base | ÉLEVÉ | P0 | `fixpro_app.py`, templates |
| 4 | Double navigation mobile | ÉLEVÉ | P1 | `templates/base.html`, `templates/artisans.html` |
| 5 | `dashboard_client.html` en ancien thème | ÉLEVÉ | P1 | `templates/dashboard_client.html` |
| 6 | Risque IDOR sur demandes | ÉLEVÉ | P1 | `fixpro_app.py` |
| 7 | Email obligatoire client | ÉLEVÉ | P1 | `templates/client_signup.html`, `fixpro_app.py` |
| 8 | `is_active` non vérifié | MOYEN | P1 | `fixpro_app.py` |
| 9 | `requests.status` sans contrainte | ÉLEVÉ | P1 | `schema_*.sql`, `fixpro_app.py` |
| 10 | Emojis dans plusieurs templates | MOYEN | P1 | `templates/*.html` |

---

## 16. Top 10 améliorations

| # | Amélioration | P | Complexité | Dépendances |
|---|---|---|---|---|
| 1 | Corriger accueil + émojis | P0 | Faible | - |
| 2 | Unifier navigation mobile | P1 | Moyenne | `base.html`, `artisans.html` |
| 3 | Migrer `dashboard_client.html` design-v2 | P1 | Moyenne | `design-v2.css` |
| 4 | Refonte formulaire demande (adresse GPS) | P1 | Élevée | JS geoloc |
| 5 | Paiement Orange Money sandbox | P0 | Élevée | API externe |
| 6 | Stockage objet uploads | P0 | Élevée | Supabase Storage |
| 7 | Audit + tests IDOR | P1 | Moyenne | - |
| 8 | Machine à états scellée | P1 | Moyenne | DB + backend |
| 9 | Dashboard technicien complet | P1 | Moyenne | Templates + routes |
| 10 | Matching par score | P2 | Élevée | Géoloc + avis |

---

## 17. Dépendances entre tâches

```
P0 accueil + emojis
    ├── P1 unification navigation
    │   └── P1 dashboard_client design-v2
    ├── P1 responsive login/client_signup
    │   └── P1 test responsive
    └── P1 formulaire demande GPS
        └── P2 matching

P0 paiement
    └── P1 stockage objet
        └── P1 avis + réputation

P1 audit IDOR
    └── P1 tests IDOR
        └── P2 nouvelles fonctionnalités
```

---

## 18. Risques avant les grosses modifications

### Migration `dashboard_client.html`

- Risque : `home-searchbar`, `home-categories`, `home-grid`, `_artisan_card.html` dépendent de `app.css`/`landing.css`.
- Mitigation : conserver les classes existantes ou migrer toutes les macro-cartes en design-v2.

### Paiement Orange Money

- Risque : credentials, coût, sandbox non toujours disponible.
- Mitigation : commencer par workflow manuel avec vérification admin.

### Stockage objet

- Risque : Supabase Storage non configuré, fichiers Vercel en lecture seule.
- Mitigation : utiliser `public` bucket signé + URLs stables.

### Unification navigation

- Risque : routes actives (`active`) basées sur `request.endpoint`.
- Mitigation : tester chaque route après fusion.

---

## 19. Synthèse

FixPro a une base solide : Flask, tests, design v2, authentification. Les fondations sont OK.

**Blocs les plus fragiles** :
1. Paiement (non vérifié).
2. Uploads base64 en base.
3. Cohérence UI/UX.
4. Sécurité IDOR non testée.
5. Géolocalisation non connectée.

**Recommandation** : stabiliser l'UI et corriger les liens cassés en Phase 1, puis sécuriser avant d'ajouter des fonctionnalités. Le paiement réel est le verrou critique pour un lancement.

---

*Fin de l'audit — aucun fichier de code n'a été modifié.*
