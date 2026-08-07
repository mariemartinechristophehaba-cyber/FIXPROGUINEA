"""Tests de la couche console / affichage de FixPro.

Les fonctions interactives (``input``) et la connexion sont simulées.
"""

from unittest.mock import MagicMock, patch

import fixpro


# --------------------------------------------------------------------------
# connecter_bd
# --------------------------------------------------------------------------
def test_connecter_bd_utilise_les_variables_env(monkeypatch):
    monkeypatch.setenv("FIXPRO_DB_HOST", "db.example.com")
    monkeypatch.setenv("FIXPRO_DB_USER", "u")
    monkeypatch.setenv("FIXPRO_DB_PASS", "p")
    monkeypatch.setenv("FIXPRO_DB_NAME", "FixProTest")

    with patch("fixpro.mysql.connector.connect", return_value=MagicMock()) as connect:
        connexion, host, name = fixpro.connecter_bd()

    connect.assert_called_once_with(host="db.example.com", user="u", password="p", database="FixProTest")
    assert host == "db.example.com"
    assert name == "FixProTest"


def test_connecter_bd_valeurs_par_defaut(monkeypatch):
    for var in ("FIXPRO_DB_HOST", "FIXPRO_DB_USER", "FIXPRO_DB_PASS", "FIXPRO_DB_NAME"):
        monkeypatch.delenv(var, raising=False)

    with patch("fixpro.mysql.connector.connect", return_value=MagicMock()) as connect:
        _, host, name = fixpro.connecter_bd()

    connect.assert_called_once_with(host="localhost", user="root", password="", database="FixPro")
    assert (host, name) == ("localhost", "FixPro")


# --------------------------------------------------------------------------
# Méthodes d'affichage (couvrent les branches de print sans effet de bord)
# --------------------------------------------------------------------------
def test_afficher_profil_artisan(capsys):
    a = fixpro.Artisan("Diallo", "Amadou", "620", "Plombier", "Kaloum", 9.5, -13.7, 50000)
    a.afficher_profil()
    out = capsys.readouterr().out
    assert "Diallo" in out and "Plombier" in out


def test_afficher_details_intervention(capsys):
    interv = fixpro.Intervention(1, 2, 100000)
    interv.afficher_details()
    out = capsys.readouterr().out
    assert "Commission FixPro" in out


def test_afficher_evaluation(capsys):
    ev = fixpro.Evaluation(1, 1, 1, 4, "super")
    ev.afficher_evaluation()
    out = capsys.readouterr().out
    assert "super" in out


def test_afficher_details_paiement(capsys):
    p = fixpro.Paiement(1, 5000, "especes")
    p.afficher_details()
    out = capsys.readouterr().out
    assert "especes" in out


def test_afficher_notification(capsys):
    n = fixpro.Notification(1, "artisan", "Titre", "Message")
    n.afficher_notification()
    out = capsys.readouterr().out
    assert "Titre" in out and "NOUVELLE" in out


# --------------------------------------------------------------------------
# Flux console avec input() simulé
# --------------------------------------------------------------------------
def test_inscription_client_sauvegarde(monkeypatch):
    reponses = iter(["Camara", "620000000", "9.5", "-13.7"])
    monkeypatch.setattr("builtins.input", lambda *a: next(reponses))
    curseur, connexion = MagicMock(), MagicMock()

    fixpro.inscription_client(curseur, connexion)

    curseur.execute.assert_called_once()
    connexion.commit.assert_called_once()


def test_inscription_artisan_metier_par_defaut(monkeypatch):
    # choix métier "9" -> "Métier inconnu"
    reponses = iter(["Diallo", "Amadou", "620", "9", "Kaloum", "9.5", "-13.7", "50000"])
    monkeypatch.setattr("builtins.input", lambda *a: next(reponses))
    curseur, connexion = MagicMock(), MagicMock()

    fixpro.inscription_artisan(curseur, connexion)

    valeurs = curseur.execute.call_args[0][1]
    assert "Métier inconnu" in valeurs


def test_chercher_artisan_aucun_resultat(monkeypatch, capsys):
    reponses = iter(["9.5", "-13.7", "1", "10"])
    monkeypatch.setattr("builtins.input", lambda *a: next(reponses))
    curseur = MagicMock()
    curseur.fetchall.return_value = []

    fixpro.chercher_artisan(curseur)

    assert "Aucun artisan" in capsys.readouterr().out


def test_effectuer_paiement_methode_invalide(monkeypatch, capsys):
    reponses = iter(["1", "5000", "9"])  # choix paiement "9" invalide
    monkeypatch.setattr("builtins.input", lambda *a: next(reponses))
    curseur, connexion = MagicMock(), MagicMock()

    fixpro.effectuer_paiement(curseur, connexion)

    assert "Méthode de paiement invalide" in capsys.readouterr().out
    curseur.execute.assert_not_called()


def test_voir_notifications_aucune(monkeypatch, capsys):
    reponses = iter(["1", "artisan"])
    monkeypatch.setattr("builtins.input", lambda *a: next(reponses))
    curseur = MagicMock()
    curseur.fetchall.return_value = []

    fixpro.voir_notifications(curseur)

    assert "Aucune notification" in capsys.readouterr().out


def test_voir_avis_artisan_introuvable(monkeypatch, capsys):
    reponses = iter(["99"])
    monkeypatch.setattr("builtins.input", lambda *a: next(reponses))
    curseur = MagicMock()
    curseur.fetchone.return_value = None

    fixpro.voir_avis_artisan(curseur)

    assert "Artisan non trouvé" in capsys.readouterr().out


def test_menu_principal_quitter(monkeypatch, capsys):
    reponses = iter(["9"])
    monkeypatch.setattr("builtins.input", lambda *a: next(reponses))
    connexion = MagicMock()

    fixpro.menu_principal(MagicMock(), connexion)

    connexion.close.assert_called_once()
    assert "Au revoir" in capsys.readouterr().out


def test_menu_principal_option_invalide_puis_quitter(monkeypatch, capsys):
    reponses = iter(["0", "9"])
    monkeypatch.setattr("builtins.input", lambda *a: next(reponses))

    fixpro.menu_principal(MagicMock(), MagicMock())

    assert "Option invalide" in capsys.readouterr().out
