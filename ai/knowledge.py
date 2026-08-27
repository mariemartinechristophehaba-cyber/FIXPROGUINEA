"""Base de connaissances FixPro pour l'assistant IA.

Cette base est separee du code de conversation pour rester maintenable.
"""

_FIXPRO_KNOWLEDGE = {
    "presentation": (
        "FixPro met en relation des clients avec des techniciens verifies a Conakry "
        "(plombiers, electriciens, frigoristes, serruriers, menuisiers, peintres, "
        "macons, chauffagistes, agents de nettoyage). Le client decrit son probleme, "
        "FixPro trouve le professionnel adapte et suit la mission jusqu'a sa fin."
    ),
    "fonctionnement_demande": (
        "Le client decrit son probleme. L'assistant identifie le metier, "
        "l'urgence et la localisation. Une fois les informations necessaires recueillies "
        "et confirmees, FixPro cree une demande d'intervention et attribue un technicien."
    ),
    "fonctionnement_mission": (
        "Une demande devient une mission avec un statut. Les statuts principaux sont : "
        "REQUESTED, ASSIGNED, ACCEPTED, EN_ROUTE, ARRIVED, IN_PROGRESS, COMPLETED, CANCELLED, "
        "PENDING_ACCEPTANCE. Le client et le technicien peuvent suivre l'evolution."
    ),
    "attribution": (
        "L'attribution prend en compte la profession, la localisation du client, "
        "la position GPS des techniciens si elle est disponible, leur statut actif "
        "et leur disponibilite. L'IA ne choisit pas elle-meme le technicien : le backend "
        "selectionne le mieux adapte."
    ),
    "prix": (
        "FixPro ne fixe pas les prix. Chaque technicien etablit son devis "
        "apres diagnostic. Le client voit le devis et le confirme avant le debut "
        "des travaux."
    ),
    "paiement": (
        "Le paiement est gere par l'equipe FixPro. Les modes acceptes incluent "
        "Orange Money, MTN Mobile Money et carte bancaire. L'IA ne peut pas confirmer "
        "qu'un paiement a ete effectue sans consulter le backend."
    ),
    "annulation": (
        "Une demande peut etre annulee tant qu'elle n'a pas commence. Le client "
        "doit confirmer son souhait d'annulation. L'IA demande confirmation avant "
        "d'appeler l'outil d'annulation."
    ),
    "compte_client": (
        "Un client peut s'inscrire avec un email, un telephone et un mot de passe. "
        "La connexion se fait via email/telephone et mot de passe ou Google OAuth."
    ),
    "compte_technicien": (
        "Un technicien s'inscrit avec ses informations, son metier, sa zone "
        "d'intervention et ses documents. Son compte est en attente de validation "
        "administrative avant d'etre actif."
    ),
    "notifications": (
        "FixPro notifie les clients et les techniciens par email et dans l'application "
        "lors d'attributions, de changements de statut, de nouveaux messages et de "
        "demandes de validation."
    ),
    "dashboard_admin": (
        "L'administrateur supervise les demandes, les techniciens, les validations "
        "et les logs via un dashboard Next.js securise."
    ),
    "securite": (
        "L'IA n'accede jamais directement a la base de donnees. Elle appelle des "
        "outils backend controles. Elle ne revele pas les donnees d'autrui et ne "
        "confirme jamais une action non effectuee."
    ),
}


def get_knowledge(topic):
    """Retourne un texte de connaissance sur un theme FixPro."""
    return _FIXPRO_KNOWLEDGE.get(topic, _FIXPRO_KNOWLEDGE["presentation"])


def all_knowledge():
    """Retourne l'ensemble des connaissances pour enrichir le system prompt."""
    return "\n\n".join(f"{k} : {v}" for k, v in _FIXPRO_KNOWLEDGE.items())
