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


def get_conversation_history(conversation_id, limit=20):
    """Retourne les derniers messages d'une conversation."""
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT sender_role, content FROM conversation_messages "
            "WHERE conversation_id = ? ORDER BY id DESC LIMIT ?",
            (conversation_id, limit)).fetchall()
        history = []
        for row in reversed(rows):
            history.append({
                "role": "user" if row["sender_role"] == "client" else "assistant",
                "content": row["content"],
            })
        return history
    finally:
        conn.close()


def get_request_full(request_id):
    """Retourne une demande avec son technicien et ses messages."""
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT r.*, t.full_name AS technician_name, t.phone AS technician_phone "
            "FROM requests r LEFT JOIN users t ON r.artisan_id = t.id "
            "WHERE r.id = ?",
            (request_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_request(client_id, title, description, category, address, urgency,
                   latitude=0.0, longitude=0.0):
    """Cree une demande d'intervention."""
    import fixpro_app
    conn = _conn()
    now = fixpro_app.datetime.now(fixpro_app.timezone.utc).isoformat()
    try:
        ref = fixpro_app._generate_fixpro_reference(conn)
        req_id = fixpro_app._insert_id(
            conn,
            "INSERT INTO requests (client_id, reference, title, description, category, address, "
            "status, urgency, quote_amount, budget, latitude, longitude, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?)",
            (client_id, ref, title, description, category, address,
             fixpro_app.MISSION_STATUS_REQUESTED, urgency,
             latitude, longitude, now, now))
        fixpro_app._log_intervention_history(
            conn, req_id, None, fixpro_app.MISSION_STATUS_REQUESTED,
            "Assistant FixPro", "Demande creee par l'assistant IA", label="Nouvelle demande")
        conn.commit()
        return req_id
    finally:
        conn.close()


def cancel_request(request_id, client_id):
    """Annule une demande si elle appartient au client et n'a pas debute."""
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT client_id, status FROM requests WHERE id = ?",
            (request_id,)).fetchone()
        if not row:
            return (False, "Demande introuvable.")
        if row["client_id"] != client_id:
            return (False, "Acces refuse.")
        if row["status"] in (fixpro_app.MISSION_STATUS_IN_PROGRESS, fixpro_app.MISSION_STATUS_COMPLETED):
            return (False, "Impossible d'annuler une mission en cours ou terminee.")
        conn.execute(
            "UPDATE requests SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (fixpro_app.MISSION_STATUS_CANCELLED, request_id))
        conn.commit()
        return (True, "Demande annulee.")
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
