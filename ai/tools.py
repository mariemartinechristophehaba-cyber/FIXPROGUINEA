"""Outils securises que l'assistant peut appeler.

Chaque outil est une fonction controlee. L'IA ne modifie jamais
directement la base de donnees.
"""

import db


def _conn():
    """Obtient une connexion via le module db."""
    return db.connect()


def get_current_user_context(user_id):
    """Retourne les informations autorisees d'un utilisateur."""
    conn = _conn()
    try:
        user = conn.execute("SELECT id, role, full_name, phone FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            return None
        return dict(user)
    finally:
        conn.close()


def get_active_request(client_id):
    """Retourne la demande active d'un client si elle existe."""
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT * FROM requests WHERE client_id = ? AND status NOT IN ('COMPLETED','CANCELLED','REJECTED') "
            "ORDER BY created_at DESC LIMIT 1",
            (client_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_request_status(request_id):
    """Retourne le statut d'une demande."""
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT id, reference, status, title, artisan_id, client_id FROM requests WHERE id = ?",
            (request_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_technician_for_request(request_id):
    """Retourne les informations publiques du technicien attribue."""
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT u.id, u.full_name, u.profession, u.phone, u.latitude, u.longitude "
            "FROM requests r JOIN users u ON r.artisan_id = u.id "
            "WHERE r.id = ?",
            (request_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_available_technicians(service, location=None):
    """Retourne la liste des techniciens actifs et verifies pour un metier."""
    conn = _conn()
    try:
        sql = ("SELECT id, full_name, profession, city, quartier "
               "FROM users WHERE role = 'technician' AND account_status = 'ACTIVE' "
               "AND is_verified = 1 AND is_active = 1")
        params = []
        if service:
            sql += " AND profession = ?"
            params.append(service)
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def create_support_ticket(client_id, subject, message):
    """Cree un ticket support pour escalade humaine."""
    conn = _conn()
    try:
        ticket_id = conn.execute(
            "INSERT INTO admin_tickets (client_id, subject, message, status) VALUES (?, ?, ?, 'open')",
            (client_id, subject, message)).lastrowid
        conn.commit()
        return ticket_id
    finally:
        conn.close()


# Liste des outils documentes pour l'IA
AVAILABLE_TOOLS = {
    "get_current_user_context": {
        "description": "Informations de base du compte connecte",
        "params": {"user_id": "int"},
        "returns": "dict ou None",
    },
    "get_active_request": {
        "description": "Demande en cours d'un client",
        "params": {"client_id": "int"},
        "returns": "dict ou None",
    },
    "get_request_status": {
        "description": "Statut d'une demande par son id",
        "params": {"request_id": "int"},
        "returns": "dict ou None",
    },
    "get_technician_for_request": {
        "description": "Technicien attribue a une demande",
        "params": {"request_id": "int"},
        "returns": "dict ou None",
    },
    "get_available_technicians": {
        "description": "Techniciens disponibles pour un metier",
        "params": {"service": "str", "location": "str optionnel"},
        "returns": "liste de dict",
    },
    "create_support_ticket": {
        "description": "Cree un ticket support",
        "params": {"client_id": "int", "subject": "str", "message": "str"},
        "returns": "int (ticket_id)",
    },
}
