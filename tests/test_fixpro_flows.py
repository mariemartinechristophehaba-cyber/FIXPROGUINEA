"""Tests des flux console complets et du routage du menu principal."""

from unittest.mock import MagicMock, patch

import pytest

import fixpro


def _inputs(monkeypatch, reponses):
    it = iter(reponses)
    monkeypatch.setattr("builtins.input", lambda *a: next(it))


# --------------------------------------------------------------------------
# enregistrer_intervention
# --------------------------------------------------------------------------
def test_enregistrer_intervention_confirmee(monkeypatch):
    _inputs(monkeypatch, ["1", "2", "100000", "O"])
    curseur, connexion = MagicMock(), MagicMock()
    curseur.lastrowid = 5

    fixpro.enregistrer_intervention(curseur, connexion)

    # insertion intervention + insertion notification
    assert curseur.execute.call_count == 2


def test_enregistrer_intervention_annulee(monkeypatch):
    _inputs(monkeypatch, ["1", "2", "100000", "N"])
    curseur, connexion = MagicMock(), MagicMock()

    fixpro.enregistrer_intervention(curseur, connexion)

    curseur.execute.assert_not_called()


# --------------------------------------------------------------------------
# evaluer_intervention (boucle de saisie de la note)
# --------------------------------------------------------------------------
def test_evaluer_intervention_reessaie_sur_note_invalide(monkeypatch):
    # note "abc" (ValueError), "7" (hors bornes), puis "4" (valide)
    _inputs(monkeypatch, ["10", "1", "2", "abc", "7", "4", "Excellent"])
    curseur, connexion = MagicMock(), MagicMock()

    fixpro.evaluer_intervention(curseur, connexion)

    # insertion évaluation + insertion notification
    assert curseur.execute.call_count == 2


def test_evaluer_intervention_commentaire_par_defaut(monkeypatch):
    _inputs(monkeypatch, ["10", "1", "2", "5", ""])
    curseur, connexion = MagicMock(), MagicMock()

    fixpro.evaluer_intervention(curseur, connexion)

    valeurs = curseur.execute.call_args_list[0][0][1]
    assert "Pas de commentaire" in valeurs


# --------------------------------------------------------------------------
# effectuer_paiement (chemin valide)
# --------------------------------------------------------------------------
def test_effectuer_paiement_valide_cree_notification(monkeypatch):
    _inputs(monkeypatch, ["7", "30000", "3"])  # mobile_money
    curseur, connexion = MagicMock(), MagicMock()
    curseur.fetchone.return_value = (2,)  # artisan_id

    fixpro.effectuer_paiement(curseur, connexion)

    # insert paiement + update intervention + select artisan + insert notif
    assert curseur.execute.call_count == 4


# --------------------------------------------------------------------------
# chercher_artisan (avec résultats)
# --------------------------------------------------------------------------
def test_chercher_artisan_avec_resultats(monkeypatch, capsys):
    _inputs(monkeypatch, ["9.5", "-13.7", "1", "50"])
    curseur = MagicMock()
    curseur.fetchall.return_value = [
        (1, "Diallo", "Amadou", "620000001", 9.51, -13.71),
    ]

    fixpro.chercher_artisan(curseur)

    out = capsys.readouterr().out
    assert "Diallo" in out and "artisan(s) trouvé(s)" in out


# --------------------------------------------------------------------------
# voir_avis_artisan (avec avis)
# --------------------------------------------------------------------------
def test_voir_avis_artisan_avec_avis(monkeypatch, capsys):
    _inputs(monkeypatch, ["1"])
    curseur = MagicMock()
    # 1er fetchone: infos artisan ; 2e fetchone: moyenne/nombre (via obtenir_moyenne_evaluations)
    curseur.fetchone.side_effect = [
        ("Diallo", "Amadou", "Plombier", "Kaloum"),
        (4.5, 2),
    ]
    curseur.fetchall.return_value = [
        (5, "Parfait", "01/01/2024"),
        (4, "Bien", "02/01/2024"),
    ]

    fixpro.voir_avis_artisan(curseur)

    out = capsys.readouterr().out
    assert "Diallo" in out and "Parfait" in out


def test_voir_avis_artisan_sans_avis(monkeypatch, capsys):
    _inputs(monkeypatch, ["1"])
    curseur = MagicMock()
    curseur.fetchone.side_effect = [
        ("Diallo", "Amadou", "Plombier", "Kaloum"),
        (0, 0),
    ]
    curseur.fetchall.return_value = []

    fixpro.voir_avis_artisan(curseur)

    assert "Pas d'avis" in capsys.readouterr().out


def test_voir_notifications_avec_resultats(monkeypatch, capsys):
    _inputs(monkeypatch, ["1", "client"])
    curseur = MagicMock()
    curseur.fetchall.return_value = [
        (10, "Titre A", "Message A", False, "01/01/2024 10:00"),
    ]

    fixpro.voir_notifications(curseur)

    out = capsys.readouterr().out
    assert "Titre A" in out
    # notification non lue -> marquée comme lue (UPDATE)
    assert any("UPDATE" in str(c[0][0]) for c in curseur.execute.call_args_list)


# --------------------------------------------------------------------------
# Routage du menu principal
# --------------------------------------------------------------------------
@pytest.mark.parametrize("choix,cible", [
    ("1", "inscription_artisan"),
    ("2", "inscription_client"),
    ("3", "chercher_artisan"),
    ("4", "enregistrer_intervention"),
    ("5", "evaluer_intervention"),
    ("6", "effectuer_paiement"),
    ("7", "voir_notifications"),
    ("8", "voir_avis_artisan"),
])
def test_menu_route_vers_bonne_fonction(monkeypatch, choix, cible):
    _inputs(monkeypatch, [choix, "9"])
    connexion = MagicMock()
    with patch.object(fixpro, cible) as fonction:
        fixpro.menu_principal(MagicMock(), connexion)
    fonction.assert_called_once()


# --------------------------------------------------------------------------
# main()
# --------------------------------------------------------------------------
def test_main_connexion_echoue(monkeypatch):
    import mysql.connector
    monkeypatch.setattr(fixpro, "connecter_bd", MagicMock(side_effect=mysql.connector.Error("ko")))
    with pytest.raises(SystemExit):
        fixpro.main()


def test_main_lance_le_menu(monkeypatch):
    connexion = MagicMock()
    monkeypatch.setattr(fixpro, "connecter_bd", MagicMock(return_value=(connexion, "localhost", "FixPro")))
    with patch.object(fixpro, "menu_principal") as menu:
        fixpro.main()
    menu.assert_called_once()
