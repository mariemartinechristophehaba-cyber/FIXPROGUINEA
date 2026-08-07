"""Tests unitaires de la logique métier de FixPro.

La connexion MySQL est toujours simulée (mock) : aucun test n'ouvre de
connexion réelle. On vérifie le comportement des classes et fonctions, y
compris les chemins d'erreur (``mysql.connector.Error``).
"""

from unittest.mock import MagicMock

import mysql.connector
import pytest

import fixpro


# --------------------------------------------------------------------------
# Fixtures / helpers
# --------------------------------------------------------------------------
@pytest.fixture
def db():
    """Retourne (curseur, connexion) simulés."""
    curseur = MagicMock(name="curseur")
    connexion = MagicMock(name="connexion")
    return curseur, connexion


def _fail_execute(curseur):
    """Fait lever une erreur MySQL au prochain execute()."""
    curseur.execute.side_effect = mysql.connector.Error("échec simulé")


# --------------------------------------------------------------------------
# Intervention.calculer_commission
# --------------------------------------------------------------------------
class TestInterventionCommission:
    def test_commission_10_pourcent(self):
        interv = fixpro.Intervention(1, 2, 100000)
        assert interv.calculer_commission() == pytest.approx(10000)

    def test_commission_stockee_dans_attribut(self):
        interv = fixpro.Intervention(1, 2, 250000)
        assert interv.commission_fixpro == pytest.approx(25000)

    def test_commission_tarif_zero(self):
        interv = fixpro.Intervention(1, 2, 0)
        assert interv.calculer_commission() == 0

    def test_taux_par_defaut(self):
        interv = fixpro.Intervention(1, 2, 100000)
        assert interv.taux_commission_fixpro == 0.10

    def test_sauvegarder_retourne_lastrowid(self, db):
        curseur, connexion = db
        curseur.lastrowid = 42
        interv = fixpro.Intervention(1, 2, 100000)
        assert interv.sauvegarder(curseur, connexion) == 42
        curseur.execute.assert_called_once()
        connexion.commit.assert_called_once()

    def test_sauvegarder_erreur_retourne_none(self, db):
        curseur, connexion = db
        _fail_execute(curseur)
        interv = fixpro.Intervention(1, 2, 100000)
        assert interv.sauvegarder(curseur, connexion) is None
        connexion.rollback.assert_called_once()


# --------------------------------------------------------------------------
# Evaluation.valider_note
# --------------------------------------------------------------------------
class TestEvaluationValiderNote:
    @pytest.mark.parametrize("note", [1, 2, 3, 4, 5])
    def test_notes_valides(self, note):
        ev = fixpro.Evaluation(1, 1, 1, note, "ok")
        assert ev.valider_note() is True

    @pytest.mark.parametrize("note", [0, -1, 6, 10, 100])
    def test_notes_invalides(self, note):
        ev = fixpro.Evaluation(1, 1, 1, note, "ok")
        assert ev.valider_note() is False

    def test_sauvegarder_refuse_note_invalide(self, db):
        curseur, connexion = db
        ev = fixpro.Evaluation(1, 1, 1, 6, "trop haut")
        assert ev.sauvegarder(curseur, connexion) is False
        curseur.execute.assert_not_called()

    def test_sauvegarder_note_valide(self, db):
        curseur, connexion = db
        ev = fixpro.Evaluation(1, 1, 1, 4, "bien")
        assert ev.sauvegarder(curseur, connexion) is True
        curseur.execute.assert_called_once()
        connexion.commit.assert_called_once()

    def test_sauvegarder_erreur_sql(self, db):
        curseur, connexion = db
        _fail_execute(curseur)
        ev = fixpro.Evaluation(1, 1, 1, 4, "bien")
        assert ev.sauvegarder(curseur, connexion) is False
        connexion.rollback.assert_called_once()


# --------------------------------------------------------------------------
# Paiement.valider_paiement / effectuer_paiement
# --------------------------------------------------------------------------
class TestPaiement:
    @pytest.mark.parametrize("methode", ["virement", "especes", "mobile_money"])
    def test_methodes_valides(self, methode):
        p = fixpro.Paiement(1, 5000, methode)
        assert p.valider_paiement() is True

    def test_methode_invalide(self):
        p = fixpro.Paiement(1, 5000, "bitcoin")
        assert p.valider_paiement() is False

    @pytest.mark.parametrize("montant", [0, -1, -5000])
    def test_montant_non_positif(self, montant):
        p = fixpro.Paiement(1, montant, "especes")
        assert p.valider_paiement() is False

    def test_effectuer_paiement_invalide_ne_touche_pas_bd(self, db):
        curseur, connexion = db
        p = fixpro.Paiement(1, 5000, "carte")
        assert p.effectuer_paiement(curseur, connexion) is False
        curseur.execute.assert_not_called()

    def test_effectuer_paiement_valide(self, db):
        curseur, connexion = db
        p = fixpro.Paiement(7, 30000, "mobile_money")
        assert p.effectuer_paiement(curseur, connexion) is True
        # insertion paiement + update intervention
        assert curseur.execute.call_count == 2
        connexion.commit.assert_called_once()
        assert p.statut == "effectué"

    def test_effectuer_paiement_erreur_sql(self, db):
        curseur, connexion = db
        _fail_execute(curseur)
        p = fixpro.Paiement(7, 30000, "mobile_money")
        assert p.effectuer_paiement(curseur, connexion) is False
        connexion.rollback.assert_called_once()


# --------------------------------------------------------------------------
# calculer_distance (Haversine)
# --------------------------------------------------------------------------
class TestCalculerDistance:
    def test_meme_point_distance_nulle(self):
        assert fixpro.calculer_distance(9.54, -13.67, 9.54, -13.67) == pytest.approx(0, abs=1e-9)

    def test_distance_connue_conakry_kindia(self):
        # Conakry ~ (9.641, -13.578), Kindia ~ (10.057, -12.865) : ~90 km
        d = fixpro.calculer_distance(9.641, -13.578, 10.057, -12.865)
        assert d == pytest.approx(90, abs=10)

    def test_symetrie(self):
        d1 = fixpro.calculer_distance(9.5, -13.7, 9.6, -13.6)
        d2 = fixpro.calculer_distance(9.6, -13.6, 9.5, -13.7)
        assert d1 == pytest.approx(d2)

    def test_distance_un_degre_latitude(self):
        # 1 degré de latitude ≈ 111 km
        d = fixpro.calculer_distance(0, 0, 1, 0)
        assert d == pytest.approx(111.19, abs=1)

    def test_distance_positive(self):
        d = fixpro.calculer_distance(9.5, -13.7, 10.0, -13.0)
        assert d > 0


# --------------------------------------------------------------------------
# trouver_artisans_proches
# --------------------------------------------------------------------------
class TestTrouverArtisansProches:
    def _curseur_avec(self, rows):
        curseur = MagicMock()
        curseur.fetchall.return_value = rows
        return curseur

    def test_filtre_par_distance_max(self):
        # client à (9.5, -13.7)
        rows = [
            (1, "Diallo", "Amadou", "620000001", 9.51, -13.71),   # proche
            (2, "Bah", "Fatou", "620000002", 12.0, -16.0),        # loin
        ]
        curseur = self._curseur_avec(rows)
        res = fixpro.trouver_artisans_proches(9.5, -13.7, "Plombier", curseur, distance_max=10)
        assert [a["id"] for a in res] == [1]

    def test_tri_par_distance_croissante(self):
        rows = [
            (1, "Loin", "X", "1", 9.6, -13.7),
            (2, "Proche", "Y", "2", 9.505, -13.7),
            (3, "Moyen", "Z", "3", 9.55, -13.7),
        ]
        curseur = self._curseur_avec(rows)
        res = fixpro.trouver_artisans_proches(9.5, -13.7, "Plombier", curseur, distance_max=100)
        distances = [a["distance"] for a in res]
        assert distances == sorted(distances)
        assert res[0]["nom"] == "Proche"

    def test_aucun_artisan(self):
        curseur = self._curseur_avec([])
        res = fixpro.trouver_artisans_proches(9.5, -13.7, "Plombier", curseur)
        assert res == []

    def test_requete_filtre_par_metier(self):
        curseur = self._curseur_avec([])
        fixpro.trouver_artisans_proches(9.5, -13.7, "Electricien", curseur)
        args = curseur.execute.call_args[0]
        assert args[1] == ("Electricien",)


# --------------------------------------------------------------------------
# obtenir_moyenne_evaluations
# --------------------------------------------------------------------------
class TestObtenirMoyenne:
    def test_aucune_evaluation(self):
        curseur = MagicMock()
        curseur.fetchone.return_value = (None, 0)
        assert fixpro.obtenir_moyenne_evaluations(1, curseur) == (0, 0)

    def test_moyenne_arrondie(self):
        curseur = MagicMock()
        curseur.fetchone.return_value = (4.333333, 3)
        moyenne, nombre = fixpro.obtenir_moyenne_evaluations(1, curseur)
        assert moyenne == 4.3
        assert nombre == 3

    def test_moyenne_entiere(self):
        curseur = MagicMock()
        curseur.fetchone.return_value = (5.0, 2)
        assert fixpro.obtenir_moyenne_evaluations(1, curseur) == (5.0, 2)


# --------------------------------------------------------------------------
# Sauvegardes simples : Artisan / Client / Notification
# --------------------------------------------------------------------------
class TestSauvegardes:
    def test_artisan_sauvegarder_succes(self, db):
        curseur, connexion = db
        a = fixpro.Artisan("Diallo", "Amadou", "620", "Plombier", "Kaloum", 9.5, -13.7, 50000)
        assert a.sauvegarder(curseur, connexion) is True
        curseur.execute.assert_called_once()
        connexion.commit.assert_called_once()

    def test_artisan_taux_commission_defaut(self):
        a = fixpro.Artisan("Diallo", "Amadou", "620", "Plombier", "Kaloum", 9.5, -13.7, 50000)
        assert a.taux_commission == 10

    def test_artisan_sauvegarder_erreur(self, db):
        curseur, connexion = db
        _fail_execute(curseur)
        a = fixpro.Artisan("Diallo", "Amadou", "620", "Plombier", "Kaloum", 9.5, -13.7, 50000)
        assert a.sauvegarder(curseur, connexion) is False
        connexion.rollback.assert_called_once()

    def test_client_sauvegarder_succes(self, db):
        curseur, connexion = db
        c = fixpro.Client("Camara", "620", 9.5, -13.7)
        assert c.sauvegarder(curseur, connexion) is True
        connexion.commit.assert_called_once()

    def test_client_sauvegarder_erreur(self, db):
        curseur, connexion = db
        _fail_execute(curseur)
        c = fixpro.Client("Camara", "620", 9.5, -13.7)
        assert c.sauvegarder(curseur, connexion) is False
        connexion.rollback.assert_called_once()

    def test_notification_sauvegarder_succes(self, db):
        curseur, connexion = db
        n = fixpro.Notification(1, "artisan", "Titre", "Message")
        assert n.sauvegarder(curseur, connexion) is True
        assert n.lue is False
        connexion.commit.assert_called_once()

    def test_notification_sauvegarder_erreur(self, db):
        curseur, connexion = db
        _fail_execute(curseur)
        n = fixpro.Notification(1, "artisan", "Titre", "Message")
        assert n.sauvegarder(curseur, connexion) is False
