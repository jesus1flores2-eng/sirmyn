# app/utils/auth.py

from functools import wraps
from flask import session, redirect, url_for, flash, abort

# Decorador generalizado
def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if 'user_id' not in session:
                flash('Debes iniciar sesión', 'warning')
                return redirect(url_for('auth.login'))
            if role and session.get('role') != role:
                flash('No tienes permiso para acceder a esta página', 'danger')
                return redirect(url_for('auth.login'))
            return f(*args, **kwargs)
        return wrapped
    return decorator

# Decorador específico para roles (puede usarse además del anterior si se prefiere)
def role_required(role):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if 'role' not in session or session['role'] != role:
                flash('No tienes permiso para acceder a esta página', 'danger')
                return redirect(url_for('auth.login'))
            return f(*args, **kwargs)
        return wrapped
    return decorator
