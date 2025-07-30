import uuid


def generate_ticket_number():
    """Generate a random ticket number using UUID"""
    return f"TCK-{uuid.uuid4().hex[:8].upper()}"
